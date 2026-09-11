import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import datetime
from sqlalchemy import text 

st.set_page_config(page_title="Recebimento", page_icon="🧾", layout="wide")

st.title("🧾 Módulo de Recebimento")
st.markdown("Auditoria de NFs, Distribuição Inteligente e Validação Final de Importação Protheus (Cloud).")

# --- CONEXÃO COM O BANCO DE DADOS NA NUVEM ---
conn = st.connection("supabase", type="sql")

def salvar_recebimentos_nuvem(df):
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM recebimentos_xml"))
            s.commit()
        df.to_sql("recebimentos_xml", con=conn.engine, if_exists='append', index=False)
    except:
        df.to_sql("recebimentos_xml", con=conn.engine, if_exists='replace', index=False)

def limpar_zeros_pedido(ped):
    p = str(ped).strip()
    if p.lower() in ["none", "nan", "<na>", ""]: return ""
    p = re.sub(r'\.0$', '', p) 
    if p.isdigit(): return str(int(p))
    return p

def obter_primeira_coluna(df, nomes_possiveis):
    for nome in nomes_possiveis:
        if nome in df.columns: return nome
    return None

def carregar_bases():
    try:
        df_cad_raw = conn.query("SELECT * FROM cadastro_produtos", ttl=0).astype(str)
        if not df_cad_raw.empty:
            df_cad_raw.columns = [str(c).upper().strip() for c in df_cad_raw.columns]
            
            c_barras = obter_primeira_coluna(df_cad_raw, ['CÓDIGO DE BARRAS', 'COD BARRAS', 'EAN', 'CODIGO DE BARRAS', 'COD. BARRAS'])
            c_int = obter_primeira_coluna(df_cad_raw, ['CÓDIGO INTERNO', 'CODIGO', 'CÓDIGO', 'PRODUTO', 'CODIGO INTERNO'])
            c_desc = obter_primeira_coluna(df_cad_raw, ['DESCRIÇÃO SB1', 'DESCRICAO SB1', 'DESCRICAO', 'DESCRIÇÃO', 'NOME'])
            c_fator = obter_primeira_coluna(df_cad_raw, ['FATOR', 'FATOR CONV.', 'FATOR CONVERSAO'])
            c_preco = obter_primeira_coluna(df_cad_raw, ['ULT. PRECO', 'ULT. PREÇO', 'ULTIMO PRECO', 'ULTIMO PREÇO', 'CUSTO STAND.', 'CUSTO', 'PRECO VENDA'])
            
            df_cad = pd.DataFrame()
            df_cad['CÓDIGO DE BARRAS'] = df_cad_raw[c_barras].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_barras else ""
            df_cad['CÓDIGO INTERNO'] = df_cad_raw[c_int].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_int else ""
            df_cad['DESCRIÇÃO SB1'] = df_cad_raw[c_desc].astype(str).replace(['nan', 'None', '<NA>'], '').str.strip() if c_desc else ""
            df_cad['FATOR'] = pd.to_numeric(df_cad_raw[c_fator], errors='coerce').fillna(1) if c_fator else 1
            df_cad['ULTIMO PRECO'] = pd.to_numeric(df_cad_raw[c_preco], errors='coerce').fillna(0.0) if c_preco else 0.0
        else:
            df_cad = pd.DataFrame()
    except Exception as e:
        st.error(f"Erro interno ao ler o Cadastro (SB1): {e}")
        df_cad = pd.DataFrame()
        
    try:
        df_pc_raw = conn.query("SELECT * FROM base_pedidos", ttl=0).astype(str)
        if not df_pc_raw.empty:
            df_pc_raw.columns = [str(c).upper().strip() for c in df_pc_raw.columns]
            
            c_num = obter_primeira_coluna(df_pc_raw, ['NUMERO PC', 'NUMERO', 'PEDIDO', 'NÚMERO'])
            c_barras_pc = obter_primeira_coluna(df_pc_raw, ['COD BARRAS', 'EAN', 'BARRAS', 'GTIN', 'CÓDIGO DE BARRAS', 'CODIGO DE BARRAS'])
            c_prc = obter_primeira_coluna(df_pc_raw, ['PRC UNITARIO', 'PRECO UNITARIO', 'PRECO', 'PREÇO', 'UNITARIO', 'VLR.UNIT'])
            c_enc = obter_primeira_coluna(df_pc_raw, ['PED. ENCERR.', 'ENCERR'])
            c_elim = obter_primeira_coluna(df_pc_raw, ['RESID. ELIM.', 'ELIM'])
            c_qtd = obter_primeira_coluna(df_pc_raw, ['QUANTIDADE', 'QTD'])
            c_ent = obter_primeira_coluna(df_pc_raw, ['QTD.ENTREGUE', 'ENTREGUE'])
            c_prod = obter_primeira_coluna(df_pc_raw, ['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO', 'CÓDIGO', 'CÓD. PRODUTO'])

            if not c_num: raise KeyError("Coluna de Pedido não encontrada no PC.")
            if not c_barras_pc: raise KeyError("Coluna de Barras/EAN não encontrada no PC.")

            df_pc = pd.DataFrame()
            df_pc['Numero PC'] = df_pc_raw[c_num].astype(str).str.replace(r'\.0$', '', regex=True).apply(limpar_zeros_pedido)
            df_pc['Cod Barras'] = df_pc_raw[c_barras_pc].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip()
            df_pc['Prc Unitario'] = pd.to_numeric(df_pc_raw[c_prc], errors='coerce').fillna(0.0) if c_prc else 0.0
            df_pc['Produto'] = df_pc_raw[c_prod].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_prod else ""
            
            def calcular_saldo(row):
                enc = str(row.get(c_enc, '')).strip().upper() if c_enc else ''
                elim = str(row.get(c_elim, '')).strip().upper() if c_elim else ''
                if enc == 'E' or elim == 'S': return 0.0
                q = pd.to_numeric(row.get(c_qtd, 0) if c_qtd else 0, errors='coerce')
                e = pd.to_numeric(row.get(c_ent, 0) if c_ent else 0, errors='coerce')
                return (q if pd.notna(q) else 0.0) - (e if pd.notna(e) else 0.0)
                
            df_pc['Saldo Disponivel'] = df_pc_raw.apply(calcular_saldo, axis=1)
        else:
            df_pc = pd.DataFrame()
    except Exception as e:
        st.error(f"Erro interno ao ler a Base de Pedidos (PC): {e}")
        df_pc = pd.DataFrame()
        
    try:
        df_barras = conn.query("SELECT * FROM barras_adicionais", ttl=0).astype(str)
        if not df_barras.empty:
            if 'EAN' in df_barras.columns:
                df_barras['EAN'] = df_barras['EAN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    except Exception as e:
        df_barras = pd.DataFrame()
        
    return df_cad, df_pc, df_barras

df_cad, df_pc, df_barras = carregar_bases()

if df_pc.empty or df_cad.empty:
    st.warning("⚠️ Cofre incompleto. Sincronize o SB1 e o PC (Base de Pedidos) na Central de Bases.")
    st.stop()

def carregar_recebimentos():
    try:
        df = conn.query("SELECT * FROM recebimentos_xml", ttl=0)
        colunas_novas = {
            "Finalizado": False, "Confirmado": False, "Duplicar": False, "Filial": "", "Valor Total XML": 0.0, 
            "Pedido NF": "", "Tipo NF": "N/D", "Data Emissão": "", "Data Finalização": "", "FATOR AJUSTADO": None, 
            "QTDE": 0.0, "FATOR CONVERSÃO": 1, "QTDE REAL": 0.0, "Custo Unitário Real": 0.0, "Ult. Preço (SB1)": 0.0, 
            "Variação Custo (%)": 0.0, "Código Interno": "", "Pedido (Item)": "", "Saldo Pedido (PC)": 0.0, 
            "Custo PC": 0.0, "Produto (SB1)": "", "Avisos": ""
        }
        for col, val in colunas_novas.items():
            if col not in df.columns: df[col] = val
            
        colunas_texto = [
            "Filial", "Nota Fiscal", "Fornecedor", "Produto", "Produto (SB1)", "Pedido XML", "Pedido Global XML", 
            "Pedido NF", "Pedido (Item)", "Código Interno", "Pedido Considerado", "Status", 
            "Ação / Decisão", "Observações", "EAN", "Tipo NF", "Data Emissão", "Data Finalização"
        ]
        
        for col in colunas_texto:
            if col in df.columns:
                if col in ["Pedido XML", "Pedido Global XML", "Pedido NF", "Pedido (Item)", "Pedido Considerado", "EAN", "Nota Fiscal", "Filial"]:
                    df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True)
                df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>'], '')
                
        return df
    except:
        return pd.DataFrame()

def processar_novos_xmls(xml_files, df_existente):
    novos_dados = []
    for file in xml_files:
        tree = ET.parse(file)
        namespaces = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infNFe = tree.getroot().find('.//nfe:infNFe', namespaces)
        
        if infNFe is None: continue
        nNF = infNFe.find('.//nfe:ide/nfe:nNF', namespaces).text
        fornecedor_raw = infNFe.find('.//nfe:emit/nfe:xNome', namespaces).text
        fornecedor = fornecedor_raw[:35].upper() if fornecedor_raw else "N/D"
        
        natOp_node = infNFe.find('.//nfe:ide/nfe:natOp', namespaces)
        nat_op = natOp_node.text.upper() if natOp_node is not None else ""
        if "BONIF" in nat_op: tipo_nf = "Bonificação"
        elif "BRINDE" in nat_op: tipo_nf = "Brinde"
        elif "AMOSTRA" in nat_op: tipo_nf = "Amostra Grátis"
        elif "VENDA" in nat_op or "REVENDA" in nat_op: tipo_nf = "Venda/Revenda"
        else: tipo_nf = natOp_node.text.title() if natOp_node is not None else "N/D"
            
        dhEmi_node = infNFe.find('.//nfe:ide/nfe:dhEmi', namespaces)
        dEmi_node = infNFe.find('.//nfe:ide/nfe:dEmi', namespaces)
        data_emissao = dhEmi_node.text[:10] if dhEmi_node is not None and dhEmi_node.text else (dEmi_node.text[:10] if dEmi_node is not None and dEmi_node.text else "")
        
        dest_cnpj = infNFe.find('.//nfe:dest/nfe:CNPJ', namespaces)
        cnpj_val = dest_cnpj.text if dest_cnpj is not None else ""
        if "000182" in cnpj_val: filial = "1001"
        elif "000263" in cnpj_val: filial = "1002"
        elif "000344" in cnpj_val: filial = "1003"
        elif "000425" in cnpj_val: filial = "1004"
        else: filial = ""
            
        vNF_node = infNFe.find('.//nfe:total/nfe:ICMSTot/nfe:vNF', namespaces)
        v_total_xml = float(vNF_node.text) if vNF_node is not None else 0.0
        
        infCpl = infNFe.find('.//nfe:infAdic/nfe:infCpl', namespaces)
        match = re.search(r'(?:pedido|ped)\b[^\d]*0*(\d{5})\b', infCpl.text if infCpl is not None else "", re.IGNORECASE)
        pedido_global = match.group(1) if match else ""
        
        for i, det in enumerate(infNFe.findall('.//nfe:det', namespaces)):
            prod = det.find('nfe:prod', namespaces)
            xProd = prod.find('nfe:xProd', namespaces).text
            
            ean_node = prod.find('nfe:cEANTrib', namespaces)
            if ean_node is None or not ean_node.text: ean_node = prod.find('nfe:cEAN', namespaces)
            ean = ean_node.text or ""
            ean_clean = str(ean).strip()
            
            qCom = float(prod.find('nfe:qCom', namespaces).text)
            vUnCom = float(prod.find('nfe:vUnCom', namespaces).text)
            
            vDesc_node = prod.find('nfe:vDesc', namespaces)
            if vDesc_node is not None:
                vDesc = float(vDesc_node.text)
                if vDesc > 0 and qCom > 0:
                    vUnCom = vUnCom - (vDesc / qCom)
            
            xPed = prod.find('nfe:xPed', namespaces)
            item_po_raw = xPed.text.strip() if xPed is not None and xPed.text else ""
            item_po = ""
            if item_po_raw:
                po_num = re.sub(r'^0+', '', item_po_raw)
                if po_num.isdigit() and len(po_num) == 5:
                    item_po = po_num
            
            id_item = f"{nNF}_{ean_clean}_{i}_{qCom}_{vUnCom}" 
            
            novos_dados.append({
                "ID": id_item, "Finalizado": False, "Confirmado": False, "Duplicar": False, "Ação / Decisão": "Pendente", 
                "Observações": "", "Avisos": "", "Filial": filial, "Nota Fiscal": str(nNF), "Tipo NF": tipo_nf, 
                "Data Emissão": data_emissao, "Data Finalização": "", "Fornecedor": fornecedor, 
                "Valor Total XML": v_total_xml, "Produto": xProd[:35], "Produto (SB1)": "", "EAN": ean_clean, 
                "Pedido XML": item_po, "Pedido Global XML": pedido_global, "Qt. XML Raw": qCom, 
                "Custo XML Raw": vUnCom, "Pedido NF": "", "Pedido (Item)": "", "Status": "Aguardando", 
                "QTDE": qCom, "FATOR CONVERSÃO": 1, "FATOR AJUSTADO": None, "QTDE REAL": qCom, 
                "Custo Unitário Real": vUnCom, "Ult. Preço (SB1)": 0.0, "Variação Custo (%)": 0.0, 
                "Código Interno": "", "Saldo Pedido (PC)": 0.0, "Custo PC": 0.0
            })
            
    df_novos = pd.DataFrame(novos_dados)
    if not df_novos.empty:
        df_novos['Filial'] = df_novos['Filial'].astype(str)
        if not df_existente.empty:
            ids_fin = df_existente[df_existente['Finalizado'] == True]['ID'].tolist()
            df_novos = df_novos[~df_novos['ID'].isin(ids_fin)]
            return pd.concat([df_existente, df_novos]).drop_duplicates(subset=['ID'], keep='last')
        return df_novos
    return df_existente

def recalcular_pendentes(df):
    if df.empty: return df
    pc_pedidos_list = df_pc['Numero PC'].astype(str).unique()
    
    # === A NOVA MEMÓRIA DINÂMICA DE SALDOS (PULO DO GATO 2) ===
    # Isso armazena o saldo consumido por PC e Produto em tempo real
    consumo_pc = {}
    
    # Passo 1: Deduzir previamente o saldo das notas já FINALIZADAS que ainda estão no cache
    for idx, row in df[df['Finalizado'] == True].iterrows():
        po = row.get('Pedido Considerado', '')
        cod = row.get('Código Interno', '')
        qtde_real_fin = float(row.get('QTDE REAL', 0))
        if po and po != "Sem Pedido" and cod:
            chave = f"{po}_{cod}"
            consumo_pc[chave] = consumo_pc.get(chave, 0.0) + qtde_real_fin
    
    # Passo 2: Calcular as notas Pendentes, deduzindo saldo linha a linha
    for idx, row in df.iterrows():
        if row.get('Finalizado', False) == True: continue 
            
        ean_raw = re.sub(r'\.0$', '', str(row.get('EAN', ''))).strip()
        ean_clean = ean_raw.lstrip('0') if ean_raw.lower() not in ['nan', 'none', ''] else ""
        
        qCom = float(row.get('QTDE', 0)) 
        vUnCom = float(row.get('Custo XML Raw', 0)) 
        
        cod_interno_manual = re.sub(r'\.0$', '', str(row.get('Código Interno', ''))).strip()
        cod_interno = cod_interno_manual.lstrip('0') if cod_interno_manual.lower() not in ['nan', 'none', ''] else ""
        
        if not cod_interno and not df_barras.empty and ean_clean and 'EAN' in df_barras.columns:
            m_barra = df_barras[df_barras['EAN'].astype(str).str.lstrip('0') == ean_clean]
            if not m_barra.empty and 'CODIGO INTERNO' in m_barra.columns: 
                cod_interno = str(m_barra['CODIGO INTERNO'].iloc[0]).strip().lstrip('0')
            
        if not cod_interno and not df_cad.empty and ean_clean and 'CÓDIGO DE BARRAS' in df_cad.columns:
            m_cad = df_cad[df_cad['CÓDIGO DE BARRAS'].astype(str).str.lstrip('0') == ean_clean]
            if not m_cad.empty and 'CÓDIGO INTERNO' in m_cad.columns: 
                cod_interno = str(m_cad['CÓDIGO INTERNO'].iloc[0]).strip().lstrip('0')

        ped_item = limpar_zeros_pedido(row.get('Pedido (Item)'))
        ped_nf = limpar_zeros_pedido(row.get('Pedido NF'))
        item_po_xml = limpar_zeros_pedido(row.get('Pedido XML'))
        global_po_xml = limpar_zeros_pedido(row.get('Pedido Global XML'))
        
        if item_po_xml and len(item_po_xml) != 5: item_po_xml = ""
        if global_po_xml and len(global_po_xml) != 5: global_po_xml = ""
        
        final_po = "Sem Pedido"
        if ped_item: final_po = ped_item
        elif ped_nf: final_po = ped_nf
        elif item_po_xml in pc_pedidos_list: final_po = item_po_xml
        elif global_po_xml in pc_pedidos_list: final_po = global_po_xml
        elif item_po_xml: final_po = item_po_xml
        elif global_po_xml: final_po = global_po_xml
        
        status_list = []
        avisos_list = []
        saldo_pc, custo_pc = 0.0, 0.0
        match_pc = pd.DataFrame()
        
        chave_consumo = ""
        
        if final_po != "Sem Pedido":
            if ean_clean:
                match_pc = df_pc[(df_pc['Numero PC'].astype(str) == final_po) & (df_pc['Cod Barras'].astype(str).str.lstrip('0') == ean_clean)]
            
            if not match_pc.empty and not cod_interno and 'Produto' in match_pc.columns:
                cod_interno = str(match_pc['Produto'].iloc[0]).strip().lstrip('0')
                
            if match_pc.empty and cod_interno and 'Produto' in df_pc.columns:
                match_pc = df_pc[(df_pc['Numero PC'].astype(str) == final_po) & (df_pc['Produto'].astype(str).str.lstrip('0') == cod_interno)]
                
            if match_pc.empty: 
                status_list.append("Inexistente no PC")
            else:
                saldo_pc_banco = float(match_pc['Saldo Disponivel'].iloc[0])
                custo_pc = float(match_pc['Prc Unitario'].iloc[0])
                
                chave_consumo = f"{final_po}_{cod_interno}"
                # Calcula o saldo real deduzindo o que as notas/linhas anteriores já consumiram na tela!
                saldo_pc = saldo_pc_banco - consumo_pc.get(chave_consumo, 0.0)
        else: 
            status_list.append("Sem Pedido")

        match_cad = pd.DataFrame()
        fator_cadastro = 1
        ult_preco = 0.0
        desc_sb1 = ""
        
        if not df_cad.empty:
            if ean_clean and 'CÓDIGO DE BARRAS' in df_cad.columns:
                match_cad = df_cad[df_cad['CÓDIGO DE BARRAS'].astype(str).str.lstrip('0') == ean_clean]
            
            if match_cad.empty and cod_interno and 'CÓDIGO INTERNO' in df_cad.columns:
                match_cad = df_cad[df_cad['CÓDIGO INTERNO'].astype(str).str.lstrip('0') == cod_interno]
                
        if not match_cad.empty:
            fator_cadastro = int(match_cad['FATOR'].iloc[0]) if 'FATOR' in match_cad.columns else 1
            ult_preco = float(match_cad['ULTIMO PRECO'].iloc[0]) if 'ULTIMO PRECO' in match_cad.columns else 0.0
            
            if 'DESCRIÇÃO SB1' in df_cad.columns:
                val_desc = match_cad['DESCRIÇÃO SB1'].iloc[0]
                if pd.notna(val_desc) and str(val_desc).strip().lower() not in ['nan', 'none', '<na>', '']:
                    desc_sb1 = str(val_desc).strip()
            
        fator_ajustado = pd.to_numeric(row.get('FATOR AJUSTADO', 0), errors='coerce')
        fator_ativo = fator_cadastro if pd.isna(fator_ajustado) or fator_ajustado <= 0 else int(fator_ajustado)
        
        if fator_ativo <= 0: 
            fator_ativo = 1
            
        qtde_real = qCom * fator_ativo
        custo_unit_real = vUnCom / fator_ativo
        var_custo = ((custo_unit_real / ult_preco) - 1) * 100 if ult_preco > 0 else 0.0
        
        if final_po != "Sem Pedido" and not match_pc.empty:
            if round(qtde_real, 2) > round(saldo_pc, 2): status_list.append("Saldo Insuficiente")
            if round(custo_unit_real, 2) > round(custo_pc, 2): status_list.append("Custo Maior que PC")
            
            # Adiciona o consumo DESTA linha na memória para abater da próxima!
            consumo_pc[chave_consumo] = consumo_pc.get(chave_consumo, 0.0) + qtde_real
            
        if abs(var_custo) > 30.0: avisos_list.append("Preço Destoante (>30%)")
        if fator_ativo > 1: avisos_list.append(f"Conv.(x{fator_ativo})")
            
        df.at[idx, 'FATOR CONVERSÃO'] = fator_cadastro
        df.at[idx, 'QTDE REAL'] = qtde_real
        df.at[idx, 'Custo Unitário Real'] = custo_unit_real
        df.at[idx, 'Ult. Preço (SB1)'] = ult_preco
        df.at[idx, 'Variação Custo (%)'] = var_custo
        df.at[idx, 'Código Interno'] = cod_interno_manual if cod_interno_manual else cod_interno
        df.at[idx, 'Produto (SB1)'] = desc_sb1
        df.at[idx, 'Saldo Pedido (PC)'] = saldo_pc  # Mostra o saldo DISPONÍVEL para esta linha!
        df.at[idx, 'Custo PC'] = custo_pc
        df.at[idx, 'Pedido Considerado'] = final_po
        df.at[idx, 'Avisos'] = " | ".join(avisos_list) if avisos_list else ""
        df.at[idx, 'Status'] = "OK" if not status_list else " | ".join(status_list)
        
    return df

def aplicar_salvamento(df_base, lista_edicoes, df_pc, df_cad, df_barras):
    novas_linhas = []
    linhas_a_remover = []
    
    for filial, nf, ped_nf_str, df_ed in lista_edicoes:
        for real_idx, row in df_ed.iterrows():
            ped_item_str = str(row.get('Pedido (Item)', '')).strip()
            
            peds_multiplos = []
            if ',' in ped_item_str: peds_multiplos = [limpar_zeros_pedido(p) for p in ped_item_str.split(',') if p.strip()]
            elif ',' in ped_nf_str and not ped_item_str: peds_multiplos = [limpar_zeros_pedido(p) for p in ped_nf_str.split(',') if p.strip()]
                
            cod_interno_manual = re.sub(r'\.0$', '', str(row.get('Código Interno', ''))).strip()
            cod_interno = cod_interno_manual.lstrip('0') if cod_interno_manual.lower() not in ['nan', 'none', ''] else ""
            
            ean_raw = re.sub(r'\.0$', '', str(df_base.at[real_idx, 'EAN'])).strip()
            ean_clean = ean_raw.lstrip('0') if ean_raw.lower() not in ['nan', 'none', ''] else ""
            
            if not cod_interno and not df_barras.empty and ean_clean and 'EAN' in df_barras.columns:
                m_barra = df_barras[df_barras['EAN'].astype(str).str.lstrip('0') == ean_clean]
                if not m_barra.empty and 'CODIGO INTERNO' in m_barra.columns: 
                    cod_interno = str(m_barra['CODIGO INTERNO'].iloc[0]).strip().lstrip('0')
            if not cod_interno and not df_cad.empty and ean_clean and 'CÓDIGO DE BARRAS' in df_cad.columns:
                m_cad = df_cad[df_cad['CÓDIGO DE BARRAS'].astype(str).str.lstrip('0') == ean_clean]
                if not m_cad.empty and 'CÓDIGO INTERNO' in m_cad.columns: 
                    cod_interno = str(m_cad['CÓDIGO INTERNO'].iloc[0]).strip().lstrip('0')
                    
            if len(peds_multiplos) > 1:
                qtde_xml_raw_total = float(row.get('QTDE', 0))
                
                fator_cadastro = 1
                match_cad = pd.DataFrame()
                if not df_cad.empty:
                    if ean_clean and 'CÓDIGO DE BARRAS' in df_cad.columns:
                        match_cad = df_cad[df_cad['CÓDIGO DE BARRAS'].astype(str).str.lstrip('0') == ean_clean]
                    if match_cad.empty and cod_interno and 'CÓDIGO INTERNO' in df_cad.columns:
                        match_cad = df_cad[df_cad['CÓDIGO INTERNO'].astype(str).str.lstrip('0') == cod_interno]
                        
                if not match_cad.empty: fator_cadastro = int(match_cad['FATOR'].iloc[0]) if 'FATOR' in match_cad.columns else 1
                fator_ajustado = pd.to_numeric(row.get('FATOR AJUSTADO', 0), errors='coerce')
                fator_ativo = fator_cadastro if pd.isna(fator_ajustado) or fator_ajustado <= 0 else int(fator_ajustado)
                
                if fator_ativo <= 0: 
                    fator_ativo = 1
                
                qtde_raw_restante = qtde_xml_raw_total
                linhas_split = []
                
                for i, p in enumerate(peds_multiplos):
                    saldo_pc = 0.0
                    match_pc = pd.DataFrame()
                    if ean_clean:
                        match_pc = df_pc[(df_pc['Numero PC'].astype(str) == p) & (df_pc['Cod Barras'].astype(str).str.lstrip('0') == ean_clean)]
                    if match_pc.empty and cod_interno and 'Produto' in df_pc.columns:
                        match_pc = df_pc[(df_pc['Numero PC'].astype(str) == p) & (df_pc['Produto'].astype(str).str.lstrip('0') == cod_interno)]
                    if not match_pc.empty: saldo_pc = float(match_pc['Saldo Disponivel'].iloc[0])
                    
                    if saldo_pc > 0:
                        consumo_real = min(qtde_raw_restante * fator_ativo, saldo_pc)
                        consumo_raw = consumo_real / fator_ativo
                        
                        if consumo_raw > 0:
                            linhas_split.append((p, consumo_raw))
                            qtde_raw_restante -= consumo_raw
                            if qtde_raw_restante <= 0.001: break
                            
                if qtde_raw_restante > 0.001:
                    linhas_split.append((peds_multiplos[-1], qtde_raw_restante))
                
                if linhas_split:
                    linhas_a_remover.append(real_idx)
                    for i, (p, q_raw) in enumerate(linhas_split):
                        nova_linha = df_base.loc[real_idx].copy()
                        nova_linha['ID'] = str(nova_linha['ID']) + f"_autosplit_{i}"
                        nova_linha['Pedido (Item)'] = p
                        nova_linha['Pedido NF'] = "" 
                        nova_linha['QTDE'] = q_raw
                        nova_linha['Código Interno'] = cod_interno
                        nova_linha['Finalizado'] = row.get('Finalizado', False)
                        nova_linha['Confirmado'] = row.get('Confirmado', False)
                        nova_linha['Data Finalização'] = row.get('Data Finalização', "")
                        nova_linha['Ação / Decisão'] = row.get('Ação / Decisão', 'Pendente')
                        nova_linha['Observações'] = row.get('Observações', '')
                        nova_linha['FATOR AJUSTADO'] = row.get('FATOR AJUSTADO', None)
                        nova_linha['Duplicar'] = False
                        novas_linhas.append(nova_linha)
            else:
                df_base.at[real_idx, 'Pedido NF'] = limpar_zeros_pedido(ped_nf_str) if not ',' in ped_nf_str else ""
                df_base.at[real_idx, 'Código Interno'] = cod_interno
                
                is_finalizado = row.get('Finalizado', False)
                df_base.at[real_idx, 'Finalizado'] = is_finalizado
                df_base.at[real_idx, 'Confirmado'] = row.get('Confirmado', False)
                df_base.at[real_idx, 'Data Finalização'] = str(row.get('Data Finalização', "")).strip()
                df_base.at[real_idx, 'Ação / Decisão'] = row.get('Ação / Decisão', 'Pendente')
                df_base.at[real_idx, 'Observações'] = row.get('Observações', '')
                df_base.at[real_idx, 'FATOR AJUSTADO'] = row.get('FATOR AJUSTADO', None)
                df_base.at[real_idx, 'Pedido (Item)'] = limpar_zeros_pedido(ped_item_str)
                df_base.at[real_idx, 'QTDE'] = row.get('QTDE', 0.0) 
                
                if row.get('Duplicar', False):
                    nova_linha = df_base.loc[real_idx].copy()
                    nova_linha['ID'] = str(nova_linha['ID']) + "_split_manual"
                    nova_linha['Duplicar'] = False
                    nova_linha['Finalizado'] = False
                    nova_linha['Confirmado'] = False
                    nova_linha['Data Finalização'] = ""
                    novas_linhas.append(nova_linha)
                    df_base.at[real_idx, 'Duplicar'] = False
                    
    if linhas_a_remover: df_base = df_base.drop(index=linhas_a_remover)
    if novas_linhas: df_base = pd.concat([df_base, pd.DataFrame(novas_linhas)], ignore_index=True)
        
    return df_base

# --- INTERFACE ---
df_recebimentos = carregar_recebimentos()

with st.sidebar:
    st.header("📥 Importar XMLs")
    arquivos_xml = st.file_uploader("Arraste os XMLs aqui", type=["xml"], accept_multiple_files=True)
    if arquivos_xml:
        if st.button("➕ Adicionar XMLs à Base", type="primary", use_container_width=True):
            with st.spinner("Extraindo notas e enviando para a Nuvem..."):
                df_recebimentos = processar_novos_xmls(arquivos_xml, df_recebimentos)
                salvar_recebimentos_nuvem(df_recebimentos)
                st.success("XMLs salvos na Nuvem!")
                st.rerun()

    st.divider()
    st.header("⚙️ Administração")
    if st.button("🗑️ Limpar Notas Pendentes"):
        try:
            df_temp = conn.query("SELECT * FROM recebimentos_xml", ttl=0)
            if not df_temp.empty:
                df_temp = df_temp[df_temp['Finalizado'] == True]
                salvar_recebimentos_nuvem(df_temp)
            st.success("Pendentes removidos da nuvem! Reimporte os XMLs se necessário.")
            st.rerun()
        except:
            st.warning("O banco de dados de recebimentos ainda está vazio.")

if not df_recebimentos.empty:
    df_recebimentos = recalcular_pendentes(df_recebimentos)
    
    aba1, aba2, aba3 = st.tabs(["⏳ Notas Fiscais em Análise", "✅ Recebimentos Finalizados", "⚖️ Auditoria Protheus"])
    
    # === ABA 1: ANÁLISE ===
    with aba1:
        df_pendentes = df_recebimentos[df_recebimentos['Finalizado'] == False].copy()
        
        if not df_pendentes.empty:
            st.markdown("### Árvore de Recebimento por Filial")
            dfs_todas_edicoes = []
            
            df_pendentes['Filial'] = df_pendentes['Filial'].astype(str)
            filiais_unicas = sorted(df_pendentes['Filial'].unique())
            
            for filial in filiais_unicas:
                nome_filial = filial if filial not in ["N/D", "nan", "", "None"] else "Filial Não Identificada"
                st.markdown(f"<h3 style='color: #2e7bcf;'>🏢 Filial: {nome_filial}</h3>", unsafe_allow_html=True)
                
                df_filial = df_pendentes[df_pendentes['Filial'] == filial]
                notas_unicas = df_filial['Nota Fiscal'].unique()
                
                for nf in notas_unicas:
                    df_nf = df_filial[df_filial['Nota Fiscal'] == nf].copy()
                    fornecedor = df_nf['Fornecedor'].iloc[0]
                    v_total = float(df_nf['Valor Total XML'].iloc[0])
                    pedido_nf_atual = df_nf['Pedido NF'].iloc[0]
                    tipo_nf_atual = df_nf['Tipo NF'].iloc[0]
                    
                    itens_com_divergencia = df_nf['Status'].apply(lambda s: str(s).strip() != "OK").any()
                    status_tag = "🔴 [VERIFICAR]" if itens_com_divergencia else "🟢 [LIBERADO]"
                    
                    with st.expander(f"{status_tag} 🧾 NF: {nf} ({tipo_nf_atual}) | 🏷️ Fornec: {fornecedor} | 💰 R$ {v_total:,.2f}", expanded=False):
                        
                        # --- NOVO BOTÃO DE EXCLUIR NF INDIVIDUAL ---
                        col_del, _ = st.columns([2, 8])
                        with col_del:
                            if st.button(f"🗑️ Excluir esta NF ({nf})", key=f"del_btn_{filial}_{nf}"):
                                idx_drop = df_recebimentos[(df_recebimentos['Filial'] == filial) & (df_recebimentos['Nota Fiscal'] == nf) & (df_recebimentos['Finalizado'] == False)].index
                                df_recebimentos = df_recebimentos.drop(index=idx_drop)
                                salvar_recebimentos_nuvem(df_recebimentos)
                                st.rerun()
                        
                        with st.form(key=f"form_nf_{filial}_{nf}"):
                            col1, col2 = st.columns([2, 2])
                            with col1:
                                novo_ped_nf = st.text_input("Pedido Master da NF (Use vírgula para dividir autom.):", value=pedido_nf_atual)
                            
                            cols_view = [
                                "Duplicar", "Ação / Decisão", "Avisos", "Observações", "Pedido Considerado",
                                "Pedido (Item)", "Código Interno", "Produto", "Produto (SB1)", "QTDE", "FATOR CONVERSÃO", 
                                "FATOR AJUSTADO", "QTDE REAL", "Custo Unitário Real", "Ult. Preço (SB1)", 
                                "Variação Custo (%)", "Saldo Pedido (PC)", "Custo PC", "Status"
                            ]
                            
                            df_ed = st.data_editor(
                                df_nf[cols_view],
                                key=f"editor_nf_{filial}_{nf}",
                                column_config={
                                    "Duplicar": st.column_config.CheckboxColumn("Duplicar ➕"),
                                    "Ação / Decisão": st.column_config.SelectboxColumn("Decisão", options=["Pendente", "Liberar Entrada", "Aguardar Correção", "Ajustar Pedido"]),
                                    "Pedido Considerado": st.column_config.TextColumn("Pedido Considerado"),
                                    "Pedido (Item)": st.column_config.TextColumn("Pedido Específico (Item)", help="Vírgulas aqui quebram APENAS esta linha."),
                                    "Código Interno": st.column_config.TextColumn("Código Interno ✏️", help="Editável. Digite o código caso não tenha sido localizado automaticamente."),
                                    "Produto": st.column_config.TextColumn("Produto (XML)"),
                                    "Produto (SB1)": st.column_config.TextColumn("Produto (SB1)"),
                                    "Avisos": st.column_config.TextColumn("Avisos Sistema"),
                                    "QTDE": st.column_config.NumberColumn("QTDE XML (Editar)", format="%.2f"),
                                    "FATOR AJUSTADO": st.column_config.NumberColumn("FATOR AJUSTADO", format="%d", min_value=1),
                                    "Variação Custo (%)": st.column_config.NumberColumn("Var. Custo (%)", format="%.2f %%"),
                                    "Custo Unitário Real": st.column_config.NumberColumn("Custo Líquido XML", format="R$ %.4f"),
                                    "Ult. Preço (SB1)": st.column_config.NumberColumn("Últ. Preço", format="R$ %.4f"),
                                    "Custo PC": st.column_config.NumberColumn("Custo PC", format="R$ %.4f"),
                                    "QTDE REAL": st.column_config.NumberColumn("QTDE REAL (XML)"),
                                    "Saldo Pedido (PC)": st.column_config.NumberColumn("Saldo Disp. (PC)")
                                },
                                disabled=["Pedido Considerado", "Produto", "Produto (SB1)", "Avisos", "FATOR CONVERSÃO", "QTDE REAL", "Custo Unitário Real", "Ult. Preço (SB1)", "Variação Custo (%)", "Saldo Pedido (PC)", "Custo PC", "Status"],
                                use_container_width=True, hide_index=True
                            )
                            dfs_todas_edicoes.append((filial, nf, novo_ped_nf, df_ed))
                            
                            colA, colB = st.columns(2)
                            with colA:
                                btn_salvar = st.form_submit_button(f"💾 Salvar e Recalcular NF ({nf})", use_container_width=True)
                            with colB:
                                btn_fin = st.form_submit_button(f"📥 Finalizar Recebimento ({nf})", type="primary", use_container_width=True)

                            if btn_salvar:
                                df_recebimentos = aplicar_salvamento(df_recebimentos, [(filial, nf, novo_ped_nf, df_ed)], df_pc, df_cad, df_barras)
                                salvar_recebimentos_nuvem(df_recebimentos)
                                st.rerun()
                                
                            if btn_fin:
                                df_ed_fin = df_ed.copy()
                                df_ed_fin['Finalizado'] = True
                                df_recebimentos = aplicar_salvamento(df_recebimentos, [(filial, nf, novo_ped_nf, df_ed_fin)], df_pc, df_cad, df_barras)
                                salvar_recebimentos_nuvem(df_recebimentos)
                                st.rerun()
                                
                        # --- GERADOR DE REPORTE DE DIVERGÊNCIA P/ O SETOR DE COMPRAS ---
                        if itens_com_divergencia:
                            st.markdown("---")
                            st.markdown("#### 🚨 Reporte de Divergência (Acionar Compras)")
                            
                            df_erros = df_nf[df_nf['Status'].apply(lambda s: str(s).strip() != "OK")].copy()
                            
                            lista_erros = []
                            if df_erros['Status'].str.contains('Custo Maior').any(): lista_erros.append("Divergência de custo")
                            if df_erros['Status'].str.contains('Saldo Insuficiente').any(): lista_erros.append("Saldo insuficiente no PC")
                            if df_erros['Status'].str.contains('Sem Pedido').any(): lista_erros.append("Item sem pedido / PC não informado na NF")
                            if df_erros['Status'].str.contains('Inexistente no PC').any(): lista_erros.append("Item inexistente no PC informado")
                            if (df_erros['Código Interno'] == "").any(): lista_erros.append("EANs não cadastrados (Itens não localizados pela descrição)")
                            
                            pcs_nf = [str(p) for p in df_nf['Pedido Considerado'].unique() if str(p) not in ["Sem Pedido", "nan", "", "None"]]
                            pc_str = ", ".join(pcs_nf) if pcs_nf else "Não informado"
                            
                            texto_padrao = f"{fornecedor} | {filial}\n\n"
                            texto_padrao += f"NF {nf} - {tipo_nf_atual}\n"
                            texto_padrao += f"PC {pc_str}\n\n"
                            texto_padrao += ", ".join(lista_erros) + "\n\n"
                            texto_padrao += "Felipe Berti Correa, por gentileza, verificar."
                            
                            col_txt, col_exc = st.columns([1, 1])
                            with col_txt:
                                st.text_area("Copie a mensagem padrão:", value=texto_padrao, height=180, key=f"txt_{nf}")
                            with col_exc:
                                df_export_erros = pd.DataFrame({
                                    'CÓDIGO HATO': df_erros['Código Interno'],
                                    'EAN': df_erros['EAN'],
                                    'PRODUTO XML': df_erros['Produto'],
                                    'nº NF': df_erros['Nota Fiscal'],
                                    'nome fornecedor': df_erros['Fornecedor'],
                                    'filial': df_erros['Filial'],
                                    'QTDE PEDIDO (PC)': df_erros['Saldo Pedido (PC)'],
                                    'QTDE REAL (XML)': df_erros['QTDE REAL'],
                                    'CUSTO PEDIDO (PC)': df_erros['Custo PC'],
                                    'CUSTO REAL (XML)': df_erros['Custo Unitário Real'],
                                    'DIVERGÊNCIA': df_erros['Status']
                                })
                                output_erros = io.BytesIO()
                                with pd.ExcelWriter(output_erros, engine='openpyxl') as writer:
                                    df_export_erros.to_excel(writer, sheet_name="Divergencias", index=False)
                                
                                st.write("Envie a planilha com as divergências completas:")
                                st.download_button(f"📥 Baixar Excel ({filial} - {nf})", data=output_erros.getvalue(), file_name=f"{filial}_{nf}_Divergencias.xlsx", type="secondary", use_container_width=True)
            
            st.divider()
            colA_global, colB_global = st.columns(2)
            with colA_global:
                if st.button("🔄 Salvar e Recalcular TODAS as Notas Acima (Apenas itens fora de formulário)", type="secondary", use_container_width=True):
                    df_recebimentos = aplicar_salvamento(df_recebimentos, dfs_todas_edicoes, df_pc, df_cad, df_barras)
                    salvar_recebimentos_nuvem(df_recebimentos)
                    st.rerun()
            with colB_global:
                if st.button("📥 Finalizar TODAS as Notas Acima (Apenas itens fora de formulário)", type="primary", use_container_width=True):
                    dfs_todas_edicoes_fin = []
                    for filial, nf, ped_nf, df_ed in dfs_todas_edicoes:
                        df_ed_fin = df_ed.copy()
                        df_ed_fin['Finalizado'] = True
                        dfs_todas_edicoes_fin.append((filial, nf, ped_nf, df_ed_fin))
                    df_recebimentos = aplicar_salvamento(df_recebimentos, dfs_todas_edicoes_fin, df_pc, df_cad, df_barras)
                    salvar_recebimentos_nuvem(df_recebimentos)
                    st.rerun()
        else:
            st.info("Nenhuma nota pendente no sistema.")
            
    # === ABA 2: FINALIZADOS / PROTHEUS ===
    with aba2:
        df_finalizados_all = df_recebimentos[df_recebimentos['Finalizado'] == True].copy()
        
        if not df_finalizados_all.empty:
            st.markdown("### 📥 Confirmação Protheus e Relatório Diário")
            st.write("Aqui estão as notas aguardando entrada sistêmica. Clique em Confirmar Entrada para gerar a data no Relatório.")
            
            # --- NOVO FILTRO DE DATAS ---
            # Troca os vazios pela tag "Aguardando Protheus"
            df_finalizados_all['Filtro Data'] = df_finalizados_all['Data Finalização'].apply(lambda x: "Aguardando Protheus" if str(x).strip() == "" else str(x).strip())
            
            datas_disponiveis = sorted(df_finalizados_all['Filtro Data'].unique(), reverse=True)
            
            colF1, colF2 = st.columns([1, 2])
            with colF1:
                datas_selecionadas = st.multiselect("📅 Filtrar por Data de Finalização:", options=datas_disponiveis, default=datas_disponiveis)
                
            st.divider()
            
            df_finalizados = df_finalizados_all[df_finalizados_all['Filtro Data'].isin(datas_selecionadas)]
            
            if not df_finalizados.empty:
                filiais_fin = sorted(df_finalizados['Filial'].unique())
                for filial in filiais_fin:
                    df_filial_fin = df_finalizados[df_finalizados['Filial'] == filial]
                    notas_fin = df_filial_fin['Nota Fiscal'].unique()
                    
                    for nf in notas_fin:
                        df_nf_fin = df_filial_fin[df_filial_fin['Nota Fiscal'] == nf]
                        fornecedor = df_nf_fin['Fornecedor'].iloc[0]
                        v_total = float(df_nf_fin['Valor Total XML'].iloc[0])
                        tipo_nf = df_nf_fin['Tipo NF'].iloc[0]
                        is_confirmada = df_nf_fin['Confirmado'].all()
                        
                        status_fin = "🔵 [CONFIRMADO]" if is_confirmada else "⚪ [AGUARDANDO PROTHEUS]"
                        
                        with st.expander(f"{status_fin} 🧾 NF: {nf} ({tipo_nf}) | 🏷️ Fornec: {fornecedor} | 💰 R$ {v_total:,.2f}", expanded=not is_confirmada):
                            st.dataframe(df_nf_fin[["Pedido Considerado", "Código Interno", "Produto", "Produto (SB1)", "QTDE REAL", "Custo Unitário Real", "Data Finalização"]], use_container_width=True, hide_index=True)
                            
                            hoje = datetime.datetime.now().strftime('%Y-%m-%d')
                            colA, colB, colC = st.columns([1, 1, 1])
                            with colA:
                                if not is_confirmada:
                                    if st.button(f"✅ Confirmar Entrada Protheus ({nf})", key=f"btn_conf_{filial}_{nf}", type="primary", use_container_width=True):
                                        idx_to_update = df_recebimentos[(df_recebimentos['Filial'] == filial) & (df_recebimentos['Nota Fiscal'] == nf) & (df_recebimentos['Finalizado'] == True)].index
                                        df_recebimentos.loc[idx_to_update, 'Confirmado'] = True
                                        df_recebimentos.loc[idx_to_update, 'Data Finalização'] = hoje
                                        salvar_recebimentos_nuvem(df_recebimentos)
                                        st.rerun()
                                else:
                                    if st.button(f"↩️ Desfazer Confirmação ({nf})", key=f"btn_unconf_{filial}_{nf}", use_container_width=True):
                                        idx_to_update = df_recebimentos[(df_recebimentos['Filial'] == filial) & (df_recebimentos['Nota Fiscal'] == nf) & (df_recebimentos['Finalizado'] == True)].index
                                        df_recebimentos.loc[idx_to_update, 'Confirmado'] = False
                                        df_recebimentos.loc[idx_to_update, 'Data Finalização'] = ""
                                        salvar_recebimentos_nuvem(df_recebimentos)
                                        st.rerun()
                            with colC:
                                if st.button(f"🔙 Devolver para Análise ({nf})", key=f"btn_return_{filial}_{nf}", use_container_width=True):
                                    idx_to_update = df_recebimentos[(df_recebimentos['Filial'] == filial) & (df_recebimentos['Nota Fiscal'] == nf) & (df_recebimentos['Finalizado'] == True)].index
                                    df_recebimentos.loc[idx_to_update, 'Finalizado'] = False
                                    df_recebimentos.loc[idx_to_update, 'Confirmado'] = False
                                    df_recebimentos.loc[idx_to_update, 'Data Finalização'] = ""
                                    salvar_recebimentos_nuvem(df_recebimentos)
                                    st.rerun()

                st.divider()
                df_confirmados = df_finalizados[df_finalizados['Confirmado'] == True]
                
                if not df_confirmados.empty:
                    st.markdown("### 📊 Exportação: Relatório Diário de Entradas")
                    relatorio_diario = []
                    for nf, group in df_confirmados.groupby("Nota Fiscal"):
                        filial_g = group['Filial'].iloc[0]
                        data_finalizacao = group['Data Finalização'].iloc[0]
                        tipo = group['Tipo NF'].iloc[0]
                        fornecedor_g = group['Fornecedor'].iloc[0]
                        valor = float(group['Valor Total XML'].iloc[0])
                        
                        pedidos_nf = group['Pedido Considerado'].unique()
                        pedidos_limpos = [str(p) for p in pedidos_nf if str(p) not in ["Sem Pedido", "nan", "", "None"]]
                        n_pedido = ", ".join(pedidos_limpos)
                        
                        relatorio_diario.append({
                            "FILIAL": filial_g,
                            "DATA": data_finalizacao,
                            "NF": str(nf),
                            "TIPO": tipo,
                            "FORNECEDOR": fornecedor_g,
                            "N° PEDIDO": n_pedido,
                            "VALOR": valor
                        })
                        
                    df_export = pd.DataFrame(relatorio_diario)
                    st.dataframe(df_export, use_container_width=True, hide_index=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_export.to_excel(writer, sheet_name="Relatório Diário", index=False)
                    st.download_button("📥 Baixar Relatório Diário (Excel)", data=output.getvalue(), file_name="Relatorio_Entradas_Confirmadas.xlsx", type="primary")
                else:
                    st.info("⚠️ Nenhuma nota das datas selecionadas foi confirmada ainda.")
                    
                st.divider()
                with st.expander("Ver base detalhada de Finalizados (Visão Analítica para TOTVS)"):
                    st.dataframe(df_finalizados[["Filial", "Nota Fiscal", "Tipo NF", "Data Finalização", "Fornecedor", "Pedido Considerado", "Código Interno", "Produto", "Produto (SB1)", "QTDE REAL", "Custo Unitário Real"]], use_container_width=True, hide_index=True)
                    output_det = io.BytesIO()
                    with pd.ExcelWriter(output_det, engine='openpyxl') as writer:
                        df_finalizados.to_excel(writer, sheet_name="Itens Finalizados", index=False)
                    st.download_button("📥 Baixar Base Completa de Itens", data=output_det.getvalue(), file_name="xmls_finalizados_itens.xlsx")
            else:
                st.info("⚠️ Não há notas para a(s) data(s) selecionada(s).")
        else:
            st.info("A gaveta de notas finalizadas está vazia.")

    # === ABA 3: AUDITORIA PROTHEUS ===
    with aba3:
        st.markdown("### ⚖️ Auditoria e Comparação com o Protheus")
        st.write("Faça o upload do Excel exportado pelo TOTVS Protheus para cruzar com o que foi recebido no sistema.")
        arquivo_prot = st.file_uploader("Upload: exp excel protheus.xlsx", type=["xlsx", "xls"])
        
        if arquivo_prot:
            with st.spinner("Lendo e cruzando dados..."):
                try:
                    df_prot = pd.read_excel(arquivo_prot)
                    header_idx = -1
                    
                    for i, r in df_prot.head(50).iterrows():
                        row_str = " ".join([str(val).lower() for val in r.values])
                        if "produto" in row_str and "quantidade" in row_str and "documento" in row_str:
                            header_idx = i
                            break
                            
                    if header_idx != -1:
                        df_prot.columns = df_prot.iloc[header_idx]
                        df_prot = df_prot.iloc[header_idx+1:].reset_index(drop=True)
                        df_prot = df_prot.loc[:, df_prot.columns.notna()]
                        
                        col_doc = next((c for c in df_prot.columns if 'doc' in str(c).lower() and 'orig' not in str(c).lower()), None)
                        col_prod = next((c for c in df_prot.columns if 'prod' in str(c).lower()), None)
                        col_qtde = next((c for c in df_prot.columns if 'quan' in str(c).lower()), None)
                        
                        if col_doc and col_prod and col_qtde:
                            df_prot[col_doc] = df_prot[col_doc].astype(str).str.replace(r'\.0$', '', regex=True)
                            df_prot[col_prod] = df_prot[col_prod].astype(str).str.strip()
                            df_prot[col_qtde] = pd.to_numeric(df_prot[col_qtde], errors='coerce').fillna(0)
                            
                            df_prot_agg = df_prot.groupby([col_doc, col_prod])[col_qtde].sum().reset_index()
                            df_prot_agg.columns = ['Nota Fiscal', 'Código Interno', 'QTDE PROTHEUS']
                            
                            df_rec = df_recebimentos.copy()
                            df_rec['Nota Fiscal'] = df_rec['Nota Fiscal'].astype(str)
                            df_rec_agg = df_rec.groupby(['Nota Fiscal', 'Código Interno'])['QTDE REAL'].sum().reset_index()
                            
                            df_cruzamento = pd.merge(df_rec_agg, df_prot_agg, on=['Nota Fiscal', 'Código Interno'], how='inner')
                            df_cruzamento['Divergência'] = df_cruzamento['QTDE PROTHEUS'] - df_cruzamento['QTDE REAL']
                            
                            def get_status_import(val):
                                if abs(val) < 0.01: return "🟢 Importação OK"
                                return "🔴 Divergência"
                                
                            df_cruzamento['Status Importação'] = df_cruzamento['Divergência'].apply(get_status_import)
                            st.dataframe(df_cruzamento, use_container_width=True, hide_index=True)
                            
                            erros = df_cruzamento[df_cruzamento['Status Importação'] == "🔴 Divergência"]
                            if not erros.empty:
                                st.error(f"Atenção! Encontramos {len(erros)} iten(s) com divergência de quantidade entre o XML e o Protheus.")
                            else:
                                st.success("Parabéns! Todas as quantidades cruzadas bateram perfeitamente.")
                        else:
                            st.warning("Não localizamos as colunas de Documento, Produto e Quantidade no Excel do Protheus.")
                    else:
                        st.warning("Padrão de tabela não reconhecido no Excel enviado.")
                except Exception as e:
                    st.error(f"Erro ao processar arquivo: {str(e)}")
