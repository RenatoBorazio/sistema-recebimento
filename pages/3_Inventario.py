import streamlit as st
import pandas as pd
import io
import datetime
import re

st.set_page_config(page_title="Módulo de Inventário", page_icon="📋", layout="wide")

st.title("📋 Módulo de Inventário")
st.markdown("Cruze Contagens, Apure Divergências e Gerencie os Resultados Consolidados por Período.")

# --- CONEXÃO COM O BANCO DE DADOS NA NUVEM ---
conn = st.connection("supabase", type="sql")

def obter_primeira_coluna(df, nomes_possiveis):
    for nome in nomes_possiveis:
        if nome in df.columns: return nome
    return None

# --- CARREGAR BASES DO COFRE BLINDADAS ---
try:
    df_cad_raw = conn.query("SELECT * FROM cadastro_produtos", ttl=0).astype(str)
    if not df_cad_raw.empty:
        df_cad_raw.columns = [str(c).upper().strip() for c in df_cad_raw.columns]
        c_barras = obter_primeira_coluna(df_cad_raw, ['CÓDIGO DE BARRAS', 'COD BARRAS', 'EAN', 'CODIGO DE BARRAS', 'COD. BARRAS'])
        c_int = obter_primeira_coluna(df_cad_raw, ['CÓDIGO INTERNO', 'CODIGO', 'CÓDIGO', 'PRODUTO', 'CODIGO INTERNO'])
        c_desc = obter_primeira_coluna(df_cad_raw, ['DESCRIÇÃO SB1', 'DESCRICAO SB1', 'DESCRICAO', 'DESCRIÇÃO', 'NOME'])
        c_custo_st = obter_primeira_coluna(df_cad_raw, ['CUSTO STAND', 'CUSTO STAND.', 'ULT. PRECO', 'ULTIMO PRECO', 'PRECO VENDA'])
        
        df_cad = pd.DataFrame()
        df_cad['CÓDIGO DE BARRAS'] = df_cad_raw[c_barras].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_barras else ""
        df_cad['CÓDIGO INTERNO'] = df_cad_raw[c_int].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_int else ""
        df_cad['DESCRIÇÃO SB1'] = df_cad_raw[c_desc].astype(str).replace(['nan', 'None', '<NA>'], '').str.strip() if c_desc else ""
        df_cad['CUSTO STAND'] = pd.to_numeric(df_cad_raw[c_custo_st], errors='coerce').fillna(0.0) if c_custo_st else 0.0
    else:
        df_cad = pd.DataFrame()
except:
    df_cad = pd.DataFrame()

try:
    df_barras = conn.query("SELECT * FROM barras_adicionais", ttl=0).astype(str)
    if not df_barras.empty:
        if 'EAN' in df_barras.columns: df_barras['EAN'] = df_barras['EAN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
except:
    df_barras = pd.DataFrame()

try:
    df_est_raw = conn.query("SELECT * FROM estoque_inicial", ttl=0).astype(str)
    if not df_est_raw.empty:
        df_est_raw.columns = [str(c).upper().strip() for c in df_est_raw.columns]
        
        c_filial = obter_primeira_coluna(df_est_raw, ['FILIAL'])
        c_prod = obter_primeira_coluna(df_est_raw, ['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO'])
        c_arm = obter_primeira_coluna(df_est_raw, ['ARMAZEM', 'ARMAZÉM', 'LOCAL'])
        c_saldo = obter_primeira_coluna(df_est_raw, ['SALDO INICIAL', 'SALDO', 'QTD INICIAL', 'QUANTIDADE', 'B2_QATU'])
        c_custo = obter_primeira_coluna(df_est_raw, ['CUSTO UNITARIO', 'CUSTO UNITÁRIO', 'CUSTO', 'CM1', 'B2_CM1'])
        
        df_est = pd.DataFrame()
        df_est['Filial'] = df_est_raw[c_filial].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_filial else ""
        df_est['Produto'] = df_est_raw[c_prod].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_prod else ""
        df_est['Armazem'] = df_est_raw[c_arm].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_arm else "01"
        df_est['Saldo Inicial'] = pd.to_numeric(df_est_raw[c_saldo], errors='coerce').fillna(0.0) if c_saldo else 0.0
        df_est['Custo Unitario'] = pd.to_numeric(df_est_raw[c_custo], errors='coerce').fillna(0.0) if c_custo else 0.0
    else:
        df_est = pd.DataFrame()
except:
    df_est = pd.DataFrame()

try:
    df_sd1_raw = conn.query("SELECT * FROM sd1_pendente", ttl=0).astype(str)
    if not df_sd1_raw.empty:
        df_sd1_raw.columns = [str(c).upper().strip() for c in df_sd1_raw.columns]
        
        c_filial_sd1 = obter_primeira_coluna(df_sd1_raw, ['FILIAL'])
        c_prod_sd1 = obter_primeira_coluna(df_sd1_raw, ['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO'])
        
        df_sd1 = pd.DataFrame()
        df_sd1['Filial'] = df_sd1_raw[c_filial_sd1].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_filial_sd1 else ""
        df_sd1['Produto'] = df_sd1_raw[c_prod_sd1].astype(str).replace(['nan', 'None', '<NA>'], '').str.replace(r'\.0$', '', regex=True).str.strip() if c_prod_sd1 else ""
    else:
        df_sd1 = pd.DataFrame()
except:
    df_sd1 = pd.DataFrame()

def checar_bases():
    faltantes = []
    if df_cad.empty: faltantes.append("SB1")
    if df_est.empty: faltantes.append("Estoque Inicial")
    return faltantes

if checar_bases():
    st.warning(f"⚠️ Cofre incompleto para Inventário. Vá na Central de Bases e sincronize: {', '.join(checar_bases())}")
    st.stop()

def carregar_historico():
    try:
        return conn.query("SELECT * FROM historico_inventario", ttl=0)
    except:
        return pd.DataFrame()

# O PULO DO GATO ESTÁ AQUI: Novo motor super flexível para aceitar "quantidade", "codigo", etc.
def padronizar_colunas(df_bruto, nome_coluna_alvo):
    df = df_bruto.copy()
    colunas_upper = {str(c).upper().strip(): c for c in df.columns}
    
    def obter_chave(nomes_possiveis):
        for nome in nomes_possiveis:
            if nome in colunas_upper: return colunas_upper[nome]
        return None
        
    col_filial = obter_chave(['FILIAL'])
    col_prod = obter_chave(['PRODUTO', 'INFORMAR CODIGO', 'CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO', 'CÓDIGO', 'EAN', 'COD BARRAS'])
    col_cont = obter_chave(['CONTAGEM', 'CONTAGEM 1', 'CONTAGEM 2', 'QTD', 'QUANTIDADE', 'SALDO'])
    col_armazem = obter_chave(['ARMAZEM', 'ARMAZÉM', 'LOCAL'])
    
    if col_filial and col_prod and col_cont:
        cols_extract = [col_filial, col_prod, col_cont]
        if col_armazem: cols_extract.append(col_armazem)
            
        df_ret = df[cols_extract].copy()
        
        renames = {col_filial: 'Filial', col_prod: 'INFORMAR CODIGO', col_cont: nome_coluna_alvo}
        if col_armazem: renames[col_armazem] = 'ARMAZEM'
            
        df_ret = df_ret.rename(columns=renames)
        df_ret['Filial'] = df_ret['Filial'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df_ret['INFORMAR CODIGO'] = df_ret['INFORMAR CODIGO'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        if 'ARMAZEM' in df_ret.columns:
            df_ret['ARMAZEM'] = df_ret['ARMAZEM'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
            df_ret['ARMAZEM'] = df_ret['ARMAZEM'].apply(lambda x: '01' if x in ['NAN', 'NONE', '', 'NAT'] else x)
            df_ret['ARMAZEM'] = df_ret['ARMAZEM'].apply(lambda x: x.zfill(2) if x.isdigit() else x)
        else:
            df_ret['ARMAZEM'] = '01'
            
        return df_ret
    return pd.DataFrame()

# --- MOTOR DO INVENTÁRIO ---
def processar_contagem(df_contagem):
    resultados = []
    
    for idx, row in df_contagem.iterrows():
        filial = str(row.get('Filial', '')).strip().replace('.0', '')
        codigo_informado = str(row.get('INFORMAR CODIGO', '')).strip().replace('.0', '')
        
        armazem = str(row.get('ARMAZEM', '01')).strip().replace('.0', '')
        if armazem.lower() in ['nan', 'none', '']: armazem = '01'
        armazem = armazem.zfill(2)
        
        if not filial or not codigo_informado or codigo_informado.lower() in ['nan', 'none', '']: continue
            
        contagem_1 = pd.to_numeric(row.get('CONTAGEM 1', 0), errors='coerce')
        if pd.isna(contagem_1): contagem_1 = 0.0
            
        val_c2 = row.get('CONTAGEM 2')
        is_recontado = False
        if pd.notna(val_c2) and str(val_c2).strip() != '':
            contagem_2 = pd.to_numeric(val_c2, errors='coerce')
            if pd.isna(contagem_2): contagem_2 = 0.0
            contagem_final = contagem_2
            is_recontado = True
        else:
            contagem_2 = 0.0
            contagem_final = contagem_1
        
        cod_interno = ""
        descricao = ""
        ean_oficial_sb1 = ""
        
        m_cad = df_cad[(df_cad['CÓDIGO DE BARRAS'].astype(str) == codigo_informado) | (df_cad['CÓDIGO INTERNO'].astype(str) == codigo_informado)]
        if not m_cad.empty:
            cod_interno = str(m_cad['CÓDIGO INTERNO'].iloc[0])
            ean_oficial_sb1 = str(m_cad['CÓDIGO DE BARRAS'].iloc[0])
            if 'DESCRIÇÃO SB1' in df_cad.columns:
                descricao = str(m_cad['DESCRIÇÃO SB1'].iloc[0])
        else:
            if not df_barras.empty:
                m_barra = df_barras[df_barras['EAN'].astype(str) == codigo_informado]
                if not m_barra.empty:
                    cod_interno = str(m_barra['CODIGO INTERNO'].iloc[0])
                    m_cad2 = df_cad[df_cad['CÓDIGO INTERNO'].astype(str) == cod_interno]
                    if not m_cad2.empty:
                        ean_oficial_sb1 = str(m_cad2['CÓDIGO DE BARRAS'].iloc[0])
                        if 'DESCRIÇÃO SB1' in df_cad.columns:
                            descricao = str(m_cad2['DESCRIÇÃO SB1'].iloc[0])
        
        if not cod_interno: cod_interno = codigo_informado 
        if not ean_oficial_sb1: ean_oficial_sb1 = codigo_informado 
            
        disponivel = "SIM"
        if not df_sd1.empty:
            match_sd1 = df_sd1[(df_sd1['Filial'].astype(str) == filial) & (df_sd1['Produto'].astype(str) == cod_interno)]
            if not match_sd1.empty: disponivel = "NÃO"
                
        saldo_inicial = 0.0
        custo_unitario = 0.0
        match_est = df_est[(df_est['Filial'].astype(str) == filial) & (df_est['Produto'].astype(str) == cod_interno)]
        
        if not match_est.empty:
            col_arm_est = 'Armazem' if 'Armazem' in df_est.columns else ('ARMAZEM' if 'ARMAZEM' in df_est.columns else None)
            if col_arm_est:
                match_est_arm = match_est[match_est[col_arm_est].astype(str).str.zfill(2) == armazem]
                if not match_est_arm.empty: match_est = match_est_arm
                
            saldo_inicial = float(match_est['Saldo Inicial'].iloc[0])
            custo_unitario = float(match_est['Custo Unitario'].iloc[0])
            
        if custo_unitario <= 0.0:
            m_cad_custo = df_cad[df_cad['CÓDIGO INTERNO'].astype(str) == cod_interno]
            if not m_cad_custo.empty and 'CUSTO STAND' in df_cad.columns:
                custo_unitario = float(m_cad_custo['CUSTO STAND'].iloc[0])
            
        valor_inicial = saldo_inicial * custo_unitario
        divergencia_saldo = contagem_final - saldo_inicial
        divergencia_valor = divergencia_saldo * custo_unitario
        
        perc_div_qtde = (divergencia_saldo / saldo_inicial) if saldo_inicial > 0 else (1.0 if divergencia_saldo > 0 else 0.0)
        perc_div_valor = (divergencia_valor / valor_inicial) if valor_inicial > 0 else (1.0 if divergencia_valor > 0 else 0.0)
        
        resultados.append({
            "FILIAL": filial,
            "ARMAZEM": armazem,
            "INFORMAR CODIGO": codigo_informado,
            "CONTAGEM 1": contagem_1,
            "CONTAGEM 2": contagem_2 if is_recontado else None,
            "CONTAGEM FINAL": contagem_final,
            "CODIGO INTERNO": cod_interno,
            "EAN OFICIAL (SB1)": ean_oficial_sb1,
            "DISPONIVEL PARA INVENTARIO?": disponivel,
            "DESCRIÇÃO": descricao,
            "SALDO INICIAL": saldo_inicial,
            "VALOR INICIAL": round(valor_inicial, 2),
            "CUSTO UNITARIO": round(custo_unitario, 4),
            "DIVERGENCIA DE SALDO": divergencia_saldo,
            "DIVERGENCIA DE VALOR": round(divergencia_valor, 2),
            "%DIV QTDE": perc_div_qtde,
            "%DIV VALOR": perc_div_valor
        })
        
    return pd.DataFrame(resultados)

# --- INTERFACE E TABS ---
aba1, aba2, aba3, aba4 = st.tabs(["📊 Nova Apuração (Dia)", "📈 Resultados Gerenciais (Fixo)", "📅 Reporte Semanal", "🔒 Pendentes (SD1)"])

with st.sidebar:
    st.header("1. Upload de Contagem")
    st.info("Suba os arquivos da loja. Envie a Recontagem se houver.")
    arq_contagem_1 = st.file_uploader("Upload: 1ª Contagem", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    st.divider()
    arq_contagem_2 = st.file_uploader("Upload: 2ª Contagem (Recontagem)", type=["xlsx", "xls", "csv"], accept_multiple_files=True)

df_res_atual = pd.DataFrame()

# --- PROCESSAMENTO SE HOUVER UPLOAD ---
if arq_contagem_1 or arq_contagem_2:
    df_c1 = pd.DataFrame()
    df_c2 = pd.DataFrame()
    
    if arq_contagem_1:
        for file in arq_contagem_1:
            try:
                tmp = pd.read_csv(file, sep=';', encoding='latin1') if file.name.endswith('.csv') else pd.read_excel(file)
                tmp_padrao = padronizar_colunas(tmp, 'CONTAGEM 1')
                df_c1 = pd.concat([df_c1, tmp_padrao], ignore_index=True)
            except: st.error(f"Erro ao ler arquivo: {file.name}")

    if arq_contagem_2:
        for file in arq_contagem_2:
            try:
                tmp = pd.read_csv(file, sep=';', encoding='latin1') if file.name.endswith('.csv') else pd.read_excel(file)
                tmp_padrao = padronizar_colunas(tmp, 'CONTAGEM 2')
                df_c2 = pd.concat([df_c2, tmp_padrao], ignore_index=True)
            except: st.error(f"Erro ao ler arquivo: {file.name}")
            
    df_completo = pd.DataFrame()
    if not df_c1.empty and not df_c2.empty:
        df_completo = pd.merge(df_c1, df_c2, on=['Filial', 'INFORMAR CODIGO', 'ARMAZEM'], how='outer')
    elif not df_c1.empty: df_completo = df_c1
    elif not df_c2.empty:
        df_completo = df_c2
        df_completo = df_completo.rename(columns={'CONTAGEM 2': 'CONTAGEM 1'})
        
    if not df_completo.empty:
        with st.spinner("Realizando o Merge e apurando divergências com Estoque na nuvem..."):
            df_res_atual = processar_contagem(df_completo)

# --- ABA 1: NOVA APURAÇÃO DO DIA ---
with aba1:
    if not df_res_atual.empty:
        st.success("✅ Base de Inventário Processada!")
        st.markdown("### Árvore de Contagens por Filial")
        
        df_view = df_res_atual.copy()
        df_view['%DIV QTDE'] = (df_view['%DIV QTDE'] * 100).map("{:.2f}%".format)
        df_view['%DIV VALOR'] = (df_view['%DIV VALOR'] * 100).map("{:.2f}%".format)
        
        filiais_unicas_atuais = sorted(df_res_atual['FILIAL'].astype(str).unique())
        
        for filial in filiais_unicas_atuais:
            df_filial = df_res_atual[df_res_atual['FILIAL'].astype(str) == filial]
            df_filial_view = df_view[df_view['FILIAL'].astype(str) == filial]
            
            div_rs = df_filial['DIVERGENCIA DE VALOR'].sum()
            div_pcs = df_filial['DIVERGENCIA DE SALDO'].sum()
            
            st.markdown(f"<h3 style='color: #2e7bcf;'>🏢 Filial: {filial}</h3>", unsafe_allow_html=True)
            
            with st.expander(f"📊 Ver Detalhes da Contagem | Divergência: R$ {div_rs:,.2f} ({div_pcs} un)", expanded=True):
                st.dataframe(df_filial_view.drop(columns=['EAN OFICIAL (SB1)', 'FILIAL']), use_container_width=True, hide_index=True)
                
                df_recontagem = df_filial[(df_filial['DIVERGENCIA DE SALDO'] != 0) & (df_filial['DISPONIVEL PARA INVENTARIO?'] == 'SIM')].copy()
                
                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if not df_recontagem.empty:
                        df_export_rec = pd.DataFrame({
                            'FILIAL': df_recontagem['FILIAL'],
                            'ARMAZEM': df_recontagem['ARMAZEM'],
                            'CODIGO INTERNO': df_recontagem['CODIGO INTERNO'],
                            'EAN': df_recontagem['EAN OFICIAL (SB1)'], 
                            'DESCRIÇÃO': df_recontagem['DESCRIÇÃO'],
                            '2ª Contagem': "", 
                            '% DIV QTDE': (df_recontagem['%DIV QTDE'] * 100).map("{:.2f}%".format),
                            '% DIV VALOR': (df_recontagem['%DIV VALOR'] * 100).map("{:.2f}%".format)
                        })
                        output_rec = io.BytesIO()
                        with pd.ExcelWriter(output_rec, engine='openpyxl') as writer:
                            df_export_rec.to_excel(writer, sheet_name=f"Recontagem_{filial}", index=False)
                        
                        st.download_button(
                            f"🔄 Baixar Formulário de Recontagem ({filial})", 
                            data=output_rec.getvalue(), 
                            file_name=f"Planilha_Recontagem_{filial}.xlsx", 
                            type="secondary",
                            use_container_width=True,
                            key=f"btn_rec_{filial}"
                        )
                    else:
                        st.success("🎉 Não há divergências nesta filial! Nenhuma recontagem necessária.")
                        
                with col_btn2:
                    df_protheus_source = df_filial[df_filial['DISPONIVEL PARA INVENTARIO?'] == 'SIM']
                    if not df_protheus_source.empty:
                        df_protheus = pd.DataFrame({
                            'B7_FILIAL': df_protheus_source['FILIAL'],
                            'B7_QUANT': df_protheus_source['CONTAGEM FINAL'],
                            'B7_COD': df_protheus_source['CODIGO INTERNO'],
                            'B7_LOCAL': df_protheus_source['ARMAZEM'].astype(str).str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(2))
                        })
                        
                        output_prot = io.StringIO()
                        df_protheus.to_csv(output_prot, sep=';', index=False, encoding='utf-8-sig')
                        
                        st.download_button(
                            f"🔌 Baixar Arquivo PROTHEUS ({filial})", 
                            data=output_prot.getvalue().encode('utf-8-sig'), 
                            file_name=f"IMPORTACAO_{filial}.csv", 
                            type="primary",
                            use_container_width=True,
                            key=f"btn_prot_{filial}"
                        )
                        
        st.divider()
        st.markdown("### 💾 Ações Globais")
        
        output_base = io.BytesIO()
        with pd.ExcelWriter(output_base, engine='openpyxl') as writer:
            df_res_atual.to_excel(writer, sheet_name="INVENTARIO_CALCULADO", index=False)
        st.download_button("📥 Baixar Base Completa de Todas as Filiais (Para Colar no P9)", data=output_base.getvalue(), file_name="Inventario_Base_Completa.xlsx", type="secondary")

        st.markdown("#### Gravar Resultados no Histórico (Nuvem)")
        st.write("Após revisar, salve esta contagem no banco de dados para alimentar os Resultados Gerenciais.")
        
        col_p1, col_p2, col_p3 = st.columns([1, 1, 2])
        with col_p1:
            periodo_input = st.text_input("Período (Ex: P9, P10):", value="P9")
        with col_p2:
            data_inv_input = st.date_input("Data do Inventário:", value=datetime.date.today())
        with col_p3:
            st.write("")
            st.write("")
            if st.button("Gravar Inventário Oficialmente", type="primary", use_container_width=True):
                df_hist = carregar_historico()
                filiais_atuais = df_res_atual['FILIAL'].astype(str).unique()
                
                if not df_hist.empty:
                    df_hist = df_hist[~((df_hist['PERIODO'].astype(str) == str(periodo_input)) & 
                                        (df_hist['DATA'].astype(str) == str(data_inv_input)) & 
                                        (df_hist['FILIAL'].astype(str).isin(filiais_atuais)))]
                
                df_salvar = df_res_atual.copy()
                df_salvar['DATA'] = str(data_inv_input)
                df_salvar.insert(0, 'PERIODO', str(periodo_input))
                
                df_hist_novo = pd.concat([df_hist, df_salvar], ignore_index=True)
                
                df_hist_novo.to_sql("historico_inventario", con=conn.engine, if_exists='replace', index=False)
                
                st.success(f"Inventário salvo com sucesso no banco de dados corporativo (Período {periodo_input})!")
                st.rerun()
    else:
        st.info("Faça o upload dos arquivos de contagem na barra lateral para iniciar a apuração do dia.")

# --- ABA 2: RESULTADOS GERENCIAIS (SEMPRE FIXA) ---
with aba2:
    df_hist = carregar_historico()
    
    if not df_hist.empty:
        st.markdown("### 📈 Painel Consolidado de Inventários")
        
        periodos_disp = sorted(df_hist['PERIODO'].astype(str).unique())
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            per_selecionado = st.selectbox("Selecione o Período:", options=periodos_disp, index=len(periodos_disp)-1)
        with col_f2:
            visao = st.radio("Selecione a Visão:", options=["Visão Consolidada (Total do Período)", "Visão Detalhada (Por Dia/Filial)"], horizontal=True)
            
        st.divider()
        
        df_filtro = df_hist[(df_hist['PERIODO'].astype(str) == str(per_selecionado)) & (df_hist['DISPONIVEL PARA INVENTARIO?'].astype(str) == 'SIM')].copy()
        
        if not df_filtro.empty:
            resumo_gerencial = []
            
            cols_calc = ['VALOR INICIAL', 'SALDO INICIAL', 'DIVERGENCIA DE SALDO', 'DIVERGENCIA DE VALOR', 'CONTAGEM FINAL']
            for c in cols_calc:
                if c in df_filtro.columns:
                    df_filtro[c] = pd.to_numeric(df_filtro[c], errors='coerce').fillna(0)
                else:
                    df_filtro[c] = 0.0

            if "Consolidada" in visao:
                for filial, group in df_filtro.groupby('FILIAL'):
                    resumo_gerencial.append({
                        "PERÍODO": per_selecionado,
                        "RESULTADOS INVENTÁRIO": filial,
                        "VALOR INICIAL": f"R$ {group['VALOR INICIAL'].sum():,.2f}",
                        "QTD. INICIAL": group['SALDO INICIAL'].sum(),
                        "QTD. CONTAGEM": group['CONTAGEM FINAL'].sum(),
                        "DIV. VALOR R$": f"R$ {group['DIVERGENCIA DE VALOR'].sum():,.2f}",
                        "DIV. SALDO Pçs": group['DIVERGENCIA DE SALDO'].sum(),
                    })
                    
                df_detalhe = df_filtro.groupby(['FILIAL', 'CODIGO INTERNO', 'DESCRIÇÃO'], as_index=False).agg({
                    'SALDO INICIAL': 'sum',
                    'CONTAGEM FINAL': 'sum',
                    'DIVERGENCIA DE SALDO': 'sum',
                    'VALOR INICIAL': 'sum',
                    'DIVERGENCIA DE VALOR': 'sum'
                })
            else:
                for (data, filial), group in df_filtro.groupby(['DATA', 'FILIAL']):
                    try:
                        data_formatada = datetime.datetime.strptime(str(data), '%Y-%m-%d').strftime('%d/%m/%Y')
                    except:
                        data_formatada = str(data)
                        
                    resumo_gerencial.append({
                        "DATA DA CONTAGEM": data_formatada,
                        "RESULTADOS INVENTÁRIO": filial,
                        "VALOR INICIAL": f"R$ {group['VALOR INICIAL'].sum():,.2f}",
                        "QTD. INICIAL": group['SALDO INICIAL'].sum(),
                        "QTD. CONTAGEM": group['CONTAGEM FINAL'].sum(),
                        "DIV. VALOR R$": f"R$ {group['DIVERGENCIA DE VALOR'].sum():,.2f}",
                        "DIV. SALDO Pçs": group['DIVERGENCIA DE SALDO'].sum(),
                    })
                    
                df_detalhe = df_filtro[['DATA', 'FILIAL', 'CODIGO INTERNO', 'DESCRIÇÃO', 'SALDO INICIAL', 'CONTAGEM FINAL', 'DIVERGENCIA DE SALDO', 'VALOR INICIAL', 'DIVERGENCIA DE VALOR']].copy()
            
            st.markdown("### 📋 Resumo Agregado")
            df_resumo_gerencial = pd.DataFrame(resumo_gerencial)
            st.dataframe(df_resumo_gerencial, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("### 🚨 Indicadores de Maior Impacto (Top 5)")
            
            df_detalhe['ABS_DIV_VALOR'] = df_detalhe['DIVERGENCIA DE VALOR'].abs()
            df_detalhe['ABS_DIV_SALDO'] = df_detalhe['DIVERGENCIA DE SALDO'].abs()
            
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.markdown("#### Maiores Variações de Valor (R$)")
                top5_valor = df_detalhe.sort_values(by='ABS_DIV_VALOR', ascending=False).head(5)
                view_top5_valor = top5_valor[['FILIAL', 'CODIGO INTERNO', 'DESCRIÇÃO', 'DIVERGENCIA DE VALOR']].copy()
                view_top5_valor['DIVERGENCIA DE VALOR'] = view_top5_valor['DIVERGENCIA DE VALOR'].apply(lambda x: f"R$ {x:,.2f}")
                st.dataframe(view_top5_valor, use_container_width=True, hide_index=True)
                
            with col_t2:
                st.markdown("#### Maiores Variações de Quantidade")
                top5_saldo = df_detalhe.sort_values(by='ABS_DIV_SALDO', ascending=False).head(5)
                view_top5_saldo = top5_saldo[['FILIAL', 'CODIGO INTERNO', 'DESCRIÇÃO', 'DIVERGENCIA DE SALDO']].copy()
                st.dataframe(view_top5_saldo, use_container_width=True, hide_index=True)
                
            st.markdown("---")
            st.markdown("### 📦 Detalhamento por Produto")
            df_detalhe_view = df_detalhe.drop(columns=['ABS_DIV_VALOR', 'ABS_DIV_SALDO'])
            st.dataframe(df_detalhe_view, use_container_width=True, hide_index=True)
            
            st.divider()
            output_gerencial = io.BytesIO()
            with pd.ExcelWriter(output_gerencial, engine='openpyxl') as writer:
                df_resumo_gerencial.to_excel(writer, sheet_name="Resultados_Gerenciais", index=False)
                df_detalhe_view.to_excel(writer, sheet_name="Detalhamento_por_Produto", index=False)
                df_filtro.to_excel(writer, sheet_name="Base_Analitica_Oficial", index=False)
            st.download_button("📥 Baixar Relatório Gerencial Completo (Excel)", data=output_gerencial.getvalue(), file_name=f"Fechamento_Inventario_{per_selecionado}.xlsx", type="primary")

        else:
            st.info(f"Nenhum dado válido gravado para o período {per_selecionado}.")
    else:
        st.info("O Histórico de Inventário está vazio. Faça uma apuração e grave os resultados para visualizar o painel.")

# --- ABA 3: CALENDÁRIO SEMANAL DE REPORT ---
with aba3:
    st.markdown("### 📅 Gerador de Reporte Semanal")
    st.write("Gere o e-mail padronizado e o calendário de status das contagens. Totalmente automatizado.")
    
    df_hist = carregar_historico()
    
    if not df_hist.empty:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            data_inicio = st.date_input("Data Inicial da Semana:", value=datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()))
        with col_d2:
            data_fim = st.date_input("Data Final da Semana:", value=data_inicio + datetime.timedelta(days=4))
            
        ignorar_fds = st.checkbox("Ignorar Sábado e Domingo no calendário", value=True)
        
        dates = [data_inicio + datetime.timedelta(days=i) for i in range((data_fim - data_inicio).days + 1)]
        if ignorar_fds:
            dates = [d for d in dates if d.weekday() < 5]
            
        if not dates:
            st.warning("Selecione um intervalo válido que contenha dias úteis.")
        else:
            filiais_map = {'1001': 'CAMPESTRE', '1002': 'VILA ALTO', '1003': 'BAETA NEVES', '1004': 'JARDIM'}
            
            filiais_hist = df_hist['FILIAL'].astype(str).str.replace(r'\.0$', '', regex=True).unique().tolist()
            
            filiais_unicas = []
            for f in filiais_hist:
                if f not in filiais_unicas: filiais_unicas.append(f)
            for code in filiais_map.keys():
                if code not in filiais_unicas: filiais_unicas.append(code)
                
            filiais_unicas = sorted(filiais_unicas)
            
            df_hist_limpo = df_hist.copy()
            df_hist_limpo['FILIAL'] = df_hist_limpo['FILIAL'].astype(str).str.replace(r'\.0$', '', regex=True)
            df_hist_limpo['DATA'] = df_hist_limpo['DATA'].astype(str).str.strip()
            
            grid_data = []
            for f_code in filiais_unicas:
                row_data = {"Filial": filiais_map.get(f_code, f"FILIAL {f_code}")}
                for d in dates:
                    d_str = d.strftime('%Y-%m-%d')
                    d_label = d.strftime('%d/%m')
                    
                    teve_contagem = not df_hist_limpo[(df_hist_limpo['FILIAL'] == f_code) & (df_hist_limpo['DATA'] == d_str)].empty
                    
                    if teve_contagem:
                        row_data[d_label] = "OK"
                    else:
                        if d.weekday() in [1, 2, 3]:
                            row_data[d_label] = "FALTOU"
                        else:
                            row_data[d_label] = "LIVRE"
                            
                grid_data.append(row_data)
                
            df_grid = pd.DataFrame(grid_data)
            
            st.markdown("#### ⚙️ Status da Semana (Automático)")
            st.info("O sistema identificou automaticamente os dias obrigatórios e as contagens realizadas.")
            st.dataframe(df_grid, hide_index=True, use_container_width=True)
            
            st.markdown("---")
            st.markdown("#### 📧 E-mail Gerado")
            st.info("💡 Arraste o mouse sobre o quadro tracejado abaixo, aperte **Ctrl+C** e cole direto no corpo do seu Outlook!")
            
            html_cal = """
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; background: #fff; padding: 15px; border: 2px dashed #999; border-radius: 5px;">
                <p>Boa tarde!</p>
                <p>Segue o resumo <span style="background-color: #ffff00; font-weight: bold;">semanal</span> dos inventários.</p>
                <p><b>Em anexo, seguem todos os itens ajustados da semana.</b></p>
                <p>Os ajustes são realizados após o envio da recontagem. Conforme alinhado, caso a contagem ou a recontagem não seja realizada, solicitamos o envio da justificativa correspondente.</p>
                <p>Calendário de contagens e recontagens por filial:</p>
                <table style="border-collapse: collapse; text-align: center; margin-top: 15px;">
                    <tr><th style="border: none;"></th>
            """
            for d in dates:
                html_cal += f'<th colspan="2" style="border: 1px solid #ccc; padding: 8px 15px; background-color: #f2f2f2; font-size: 16px;">{d.day}</th>'
            html_cal += '</tr>\n'
            
            for idx, row in df_grid.iterrows():
                f_name = row['Filial']
                html_cal += f'<tr><td style="border: none; padding: 10px 15px; text-align: right; font-weight: bold; color: #555;">{f_name}</td>'
                
                for d in dates:
                    d_label = d.strftime('%d/%m')
                    status = row[d_label]
                    
                    if status == "OK":
                        cor_bg, cor_texto = '#a9d08e', '#333'
                    elif status == "FALTOU":
                        cor_bg, cor_texto = '#f4b084', '#333'
                    else:
                        cor_bg, cor_texto = '#ffffff', '#999'
                        
                    html_cal += f'<td style="border: 1px solid #ccc; background-color: {cor_bg}; color: {cor_texto}; padding: 8px 12px;">contagem</td>'
                    html_cal += f'<td style="border: 1px solid #ccc; background-color: {cor_bg}; color: {cor_texto}; padding: 8px 12px;">recontagem</td>'
                    
                html_cal += '</tr>\n'
                
            html_cal += '</table><br>'
            html_cal += """
                <table style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif; font-size: 12px; font-weight: bold;">
                    <tr><td style="border: 1px solid #000; padding: 3px 20px;">LEGENDA</td></tr>
                    <tr><td style="border: 1px solid #000; padding: 3px 20px; background-color: #f4b084;">NÃO INVENTARIADO</td></tr>
                    <tr><td style="border: 1px solid #000; padding: 3px 20px; background-color: #a9d08e;">INVENTARIADO - OK</td></tr>
                </table>
                <p>Atenciosamente.</p>
            </div>
            """
            st.markdown(html_cal, unsafe_allow_html=True)
    else:
        st.info("O Histórico de Inventário está vazio. Salve algumas apurações diárias para poder gerar o reporte semanal.")

# --- ABA 4: PENDENTES (TRAVADOS NO SD1) ---
with aba4:
    if not df_res_atual.empty:
        st.markdown("### 🔒 Itens Bloqueados na Contagem Atual (Ainda no SD1)")
        df_travado = df_res_atual[df_res_atual['DISPONIVEL PARA INVENTARIO?'] == 'NÃO']
        
        if not df_travado.empty:
            st.warning(f"Foram encontrados {len(df_travado)} itens na contagem atual que estão pendentes de classificação fiscal (SD1). Eles não compõem os Resultados Gerenciais.")
            st.dataframe(df_travado[["FILIAL", "CODIGO INTERNO", "DESCRIÇÃO", "CUSTO UNITARIO", "CONTAGEM 1"]], use_container_width=True, hide_index=True)
        else:
            st.success("Tudo limpo! Nenhum item da contagem atual estava retido no SD1.")
    else:
        st.info("Faça o upload de uma contagem na barra lateral para verificar se há itens retidos no SD1.")
