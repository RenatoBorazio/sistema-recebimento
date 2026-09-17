import streamlit as st
import pandas as pd
import datetime
import io
from sqlalchemy import text

st.set_page_config(page_title="Controle de Estoque", page_icon="📉", layout="wide")

st.title("📉 Previsão de Ruptura e Venda Perdida")
st.markdown("Projete a cobertura do estoque e analise o impacto financeiro de rupturas com base na sua venda diária média.")

# --- CONEXÃO COM O BANCO DE DADOS NA NUVEM ---
conn = st.connection("supabase", type="sql")

def safe_numeric(series):
    s = series.astype(str).str.strip()
    s = s.apply(lambda x: x.replace('.', '').replace(',', '.') if ',' in x else x)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

def obter_primeira_coluna(df, nomes_possiveis):
    for nome in nomes_possiveis:
        if nome in df.columns: return nome
    return None

@st.cache_data(ttl=300)
def carregar_dados():
    erros_log = []
    
    # 1. Carregar SB1 (Cadastro e Preço de Venda)
    try:
        df_cols_cad = conn.query("SELECT * FROM cadastro_produtos LIMIT 1", ttl=0)
        colunas_reais_cad = df_cols_cad.columns.tolist()
        colunas_upper_cad = [str(c).upper().strip() for c in colunas_reais_cad]
        
        def acha_nome_real_cad(nomes_possiveis):
            for i, c_up in enumerate(colunas_upper_cad):
                if c_up in nomes_possiveis:
                    return f'"{colunas_reais_cad[i]}"' 
            return None

        c_int_sql = acha_nome_real_cad(['CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO', 'CÓDIGO', 'PRODUTO', 'B1_COD'])
        c_desc_sql = acha_nome_real_cad(['DESCRIÇÃO SB1', 'DESCRICAO SB1', 'DESCRICAO', 'DESCRIÇÃO', 'NOME', 'B1_DESC'])
        c_preco_sql = acha_nome_real_cad(['PRECO VENDA', 'PREÇO VENDA', 'ULTIMO PRECO', 'ULT. PRECO', 'CUSTO STAND', 'CUSTO STAND.', 'PRC TABELA', 'CUSTO'])

        df_cad = pd.DataFrame()
        if c_int_sql:
            cols_to_fetch_cad = [c for c in [c_int_sql, c_desc_sql, c_preco_sql] if c]
            query_cad = f"SELECT {', '.join(cols_to_fetch_cad)} FROM cadastro_produtos"
            
            df_cad_raw = conn.query(query_cad, ttl=0).astype(str)
            df_cad_raw.columns = [str(c).upper().strip() for c in df_cad_raw.columns]
            
            c_i = obter_primeira_coluna(df_cad_raw, ['CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO', 'CÓDIGO', 'PRODUTO', 'B1_COD'])
            c_d = obter_primeira_coluna(df_cad_raw, ['DESCRIÇÃO SB1', 'DESCRICAO SB1', 'DESCRICAO', 'DESCRIÇÃO', 'NOME', 'B1_DESC'])
            c_p = obter_primeira_coluna(df_cad_raw, ['PRECO VENDA', 'PREÇO VENDA', 'ULTIMO PRECO', 'ULT. PRECO', 'CUSTO STAND', 'CUSTO STAND.', 'PRC TABELA', 'CUSTO'])

            df_cad['CODIGO'] = df_cad_raw[c_i].replace(r'\.0$', '', regex=True).str.strip()
            df_cad['DESCRIÇÃO'] = df_cad_raw[c_d].astype(str).str.strip() if c_d else "S/D"
            df_cad['PRECO_VENDA'] = safe_numeric(df_cad_raw[c_p]) if c_p else 0.0
        else:
            erros_log.append("SB1: Coluna de código/produto não encontrada.")
    except Exception as e: 
        df_cad = pd.DataFrame()
        erros_log.append(f"Falha ao conectar no SB1: {str(e)}")

    # 2. Carregar Estoque Atual
    try:
        df_est_raw = conn.query("SELECT * FROM estoque_inicial", ttl=0).astype(str)
        df_est_raw.columns = [str(c).upper().strip() for c in df_est_raw.columns]
        c_filial = obter_primeira_coluna(df_est_raw, ['FILIAL', 'B2_FILIAL', 'B7_FILIAL', 'COD FILIAL', 'CÓDIGO FILIAL'])
        c_prod = obter_primeira_coluna(df_est_raw, ['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO INTERNO', 'CODIGO', 'CÓDIGO', 'B2_COD', 'B7_COD', 'ITEM', 'COD. PRODUTO'])
        c_saldo = obter_primeira_coluna(df_est_raw, ['SALDO INICIAL', 'SALDO', 'QTD INICIAL', 'QUANTIDADE', 'B2_QATU', 'B7_QUANT', 'QTD', 'SALDO ATUAL', 'ESTOQUE'])
        
        df_est = pd.DataFrame()
        if c_prod and c_saldo:
            df_est['FILIAL'] = df_est_raw[c_filial].astype(str).replace(r'\.0$', '', regex=True).str.strip() if c_filial else ""
            df_est['CODIGO'] = df_est_raw[c_prod].astype(str).replace(r'\.0$', '', regex=True).str.strip()
            df_est['SALDO'] = safe_numeric(df_est_raw[c_saldo])
            
            df_est = df_est.groupby(['FILIAL', 'CODIGO'])['SALDO'].sum().reset_index()
        else:
            erros_log.append("Estoque: As colunas Produto e Saldo não foram encontradas.")
    except Exception as e:
        df_est = pd.DataFrame()
        erros_log.append(f"Falha ao conectar no Estoque Inicial: {str(e)}")

    # 3. Carregar SD2
    try:
        df_cols = conn.query("SELECT * FROM sd2_saidas LIMIT 1", ttl=0)
        colunas_reais = df_cols.columns.tolist()
        colunas_upper = [str(c).upper().strip() for c in colunas_reais]
        
        def acha_nome_real(nomes_possiveis):
            for i, c_up in enumerate(colunas_upper):
                if c_up in nomes_possiveis:
                    return f'"{colunas_reais[i]}"' 
            return None

        c_filial_sql = acha_nome_real(['FILIAL', 'D2_FILIAL'])
        c_prod_sql = acha_nome_real(['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO', 'CÓDIGO'])
        c_qtd_sql = acha_nome_real(['QUANTIDADE', 'QTD', 'D2_QUANT'])
        c_emissao_sql = acha_nome_real(['EMISSAO', 'EMISSÃO', 'DATA', 'D2_EMISSAO'])

        df_sd2 = pd.DataFrame()
        if c_prod_sql and c_emissao_sql:
            cols_to_fetch = [c for c in [c_filial_sql, c_prod_sql, c_qtd_sql, c_emissao_sql] if c]
            query_str = f"SELECT {', '.join(cols_to_fetch)} FROM sd2_saidas"
            
            df_sd2_raw = conn.query(query_str, ttl=0).astype(str)
            df_sd2_raw.columns = [str(c).upper().strip() for c in df_sd2_raw.columns]
            
            c_f = obter_primeira_coluna(df_sd2_raw, ['FILIAL', 'D2_FILIAL'])
            c_p = obter_primeira_coluna(df_sd2_raw, ['PRODUTO', 'CÓDIGO INTERNO', 'CODIGO', 'CÓDIGO'])
            c_q = obter_primeira_coluna(df_sd2_raw, ['QUANTIDADE', 'QTD', 'D2_QUANT'])
            c_e = obter_primeira_coluna(df_sd2_raw, ['EMISSAO', 'EMISSÃO', 'DATA', 'D2_EMISSAO'])

            df_sd2['FILIAL'] = df_sd2_raw[c_f].replace(r'\.0$', '', regex=True).str.strip() if c_f else ""
            df_sd2['CODIGO'] = df_sd2_raw[c_p].replace(r'\.0$', '', regex=True).str.strip()
            
            datas_limpas = df_sd2_raw[c_e].str.split(' ').str[0] 
            datas_convertidas = pd.to_datetime(datas_limpas, format='%d/%m/%Y', errors='coerce')
            datas_convertidas = datas_convertidas.fillna(pd.to_datetime(datas_limpas, format='%Y-%m-%d', errors='coerce'))
            
            df_sd2['DATA_VENDA'] = datas_convertidas
            df_sd2['QTD_VENDIDA'] = safe_numeric(df_sd2_raw[c_q]) if c_q else 1.0
        else:
            erros_log.append("SD2: As colunas de Produto ou Emissao não foram encontradas.")
    except Exception as e: 
        df_sd2 = pd.DataFrame()
        erros_log.append(f"Falha ao conectar no SD2: {str(e)}")

    # 4. Curva ABC
    try:
        df_curva_raw = conn.query("SELECT * FROM base_curva_abc", ttl=0).astype(str)
        df_curva_raw.columns = [str(c).upper().strip() for c in df_curva_raw.columns]
        c_cod_curva = obter_primeira_coluna(df_curva_raw, ['CODIGO', 'CÓDIGO'])
        c_curva = obter_primeira_coluna(df_curva_raw, ['CURVA', 'CURVA ABC'])
        c_fil_curva = obter_primeira_coluna(df_curva_raw, ['FILIAL', 'LOJA'])
        
        df_curva = pd.DataFrame()
        if c_cod_curva and c_curva:
            df_curva['CODIGO'] = df_curva_raw[c_cod_curva].astype(str).replace(r'\.0$', '', regex=True).str.strip()
            df_curva['CURVA'] = df_curva_raw[c_curva].astype(str).str.strip().str.upper()
            df_curva['FILIAL'] = df_curva_raw[c_fil_curva].astype(str).replace(r'\.0$', '', regex=True).str.strip() if c_fil_curva else ""
    except: df_curva = pd.DataFrame()

    return df_cad, df_est, df_sd2, df_curva, erros_log

with st.spinner("Conectando ao banco de dados e processando as regras de estoque..."):
    df_cad, df_est, df_sd2, df_curva, erros_log = carregar_dados()

if df_est.empty or df_sd2.empty:
    st.error("🚨 Base Incompleta! Sincronize o Estoque e as Saídas (SD2) na Central de Bases.")
    st.stop()

# --- FILTROS LATERAIS ---
with st.sidebar:
    st.header("⚙️ Configurações de Cálculo")
    dias_analise = st.slider("Considerar vendas dos últimos X dias:", min_value=15, max_value=365, value=90, step=15)
    
    st.markdown("---")
    st.markdown("**Regras de Ruptura**")
    cobertura_alvo = st.number_input("Estoque de Segurança (Dias):", min_value=1, max_value=60, value=15, help="Risco de Ruptura se a cobertura for menor que este valor.")
    dias_ruptura = st.number_input("Dias sem venda para Ruptura:", min_value=1, max_value=30, value=3, help="Se o saldo for <= 0, só será classificado como Ruptura se estiver sem vender há pelo menos X dias (ignora vendas no negativo).")
    
    st.markdown("---")
    filiais_disp = sorted([f for f in df_est['FILIAL'].unique() if f.strip() != ""])
    filiais_selecionadas = st.multiselect("Filtrar por Filial:", options=filiais_disp, default=filiais_disp)

# --- MOTOR DE CÁLCULO ---
hoje = pd.Timestamp(datetime.date.today())
data_corte = hoje - pd.Timedelta(days=dias_analise)

df_sd2_recente = df_sd2[df_sd2['DATA_VENDA'] >= data_corte]

df_vendas_agg = df_sd2_recente.groupby(['FILIAL', 'CODIGO']).agg(
    TOTAL_VENDIDO=('QTD_VENDIDA', 'sum'),
    ULTIMA_VENDA=('DATA_VENDA', 'max')
).reset_index()

df_vendas_agg['VENDA_DIA'] = df_vendas_agg['TOTAL_VENDIDO'] / dias_analise

df_master = pd.merge(df_est, df_vendas_agg, on=['FILIAL', 'CODIGO'], how='left')
df_master['TOTAL_VENDIDO'] = df_master['TOTAL_VENDIDO'].fillna(0)
df_master['VENDA_DIA'] = df_master['VENDA_DIA'].fillna(0)
df_master['ULTIMA_VENDA'] = df_master['ULTIMA_VENDA'].fillna(pd.NaT)

if not df_cad.empty:
    df_cad_unique = df_cad.drop_duplicates(subset=['CODIGO'])
    df_master = pd.merge(df_master, df_cad_unique[['CODIGO', 'DESCRIÇÃO', 'PRECO_VENDA']], on='CODIGO', how='left')
    df_master['DESCRIÇÃO'] = df_master['DESCRIÇÃO'].fillna("S/D")
    df_master['PRECO_VENDA'] = df_master['PRECO_VENDA'].fillna(0.0)
else:
    df_master['DESCRIÇÃO'] = "S/D"
    df_master['PRECO_VENDA'] = 0.0

df_master['CURVA'] = "C"
if not df_curva.empty:
    if 'FILIAL' in df_curva.columns and not df_curva['FILIAL'].eq("").all():
        df_master = pd.merge(df_master, df_curva[['FILIAL', 'CODIGO', 'CURVA']], on=['FILIAL', 'CODIGO'], how='left')
    else:
        df_master = pd.merge(df_master, df_curva[['CODIGO', 'CURVA']], on='CODIGO', how='left')
    
    if 'CURVA_y' in df_master.columns:
        df_master['CURVA'] = df_master['CURVA_y'].fillna("C")
        df_master = df_master.drop(columns=['CURVA_x', 'CURVA_y'])
    elif 'CURVA' in df_master.columns:
        df_master['CURVA'] = df_master['CURVA'].fillna("C")

# --- LÓGICA CORE: DIAS SEM VENDA & COBERTURA ---
df_master['DIAS_COBERTURA'] = df_master.apply(
    lambda r: (r['SALDO'] / r['VENDA_DIA']) if (r['VENDA_DIA'] > 0 and r['SALDO'] > 0) else (999 if r['SALDO'] > 0 else 0), axis=1
)

def classificar_status(row):
    dias_sem_venda = dias_analise # Valor máximo padrão caso nunca tenha vendido
    if pd.notna(row['ULTIMA_VENDA']):
        dias_sem_venda = (hoje - row['ULTIMA_VENDA']).days
        if dias_sem_venda < 0: dias_sem_venda = 0

    perda_diaria = 0.0
    perda_acumulada = 0.0
    status = "Sem Giro"

    # Se zerou e vendia
    if row['SALDO'] <= 0 and row['VENDA_DIA'] > 0:
        if dias_sem_venda >= dias_ruptura:
            perda_diaria = row['VENDA_DIA'] * row['PRECO_VENDA']
            perda_acumulada = dias_sem_venda * perda_diaria
            status = "Ruptura"
        else:
            status = "Venda no Negativo"
            
    # Se tem saldo, mas vende pouco para a cobertura alvo
    elif row['SALDO'] > 0 and row['VENDA_DIA'] > 0 and row['DIAS_COBERTURA'] <= cobertura_alvo:
        status = "Risco"
        
    # Se tem saldo e vende bem
    elif row['SALDO'] > 0 and row['VENDA_DIA'] > 0 and row['DIAS_COBERTURA'] > cobertura_alvo:
        status = "Saudável"
        
    # Se tem saldo, mas nunca vende
    elif row['SALDO'] > 0 and row['VENDA_DIA'] == 0:
        status = "Sem Giro"
        
    return pd.Series([dias_sem_venda, perda_diaria, perda_acumulada, status])

df_master[['DIAS_SEM_VENDA', 'PERDA_DIARIA_RS', 'PERDA_ACUMULADA_RS', 'STATUS']] = df_master.apply(classificar_status, axis=1)

if filiais_selecionadas:
    df_master = df_master[df_master['FILIAL'].isin(filiais_selecionadas)]

# --- PAINEL DE KPIs EXECUTIVOS ---
st.markdown("### 📊 Resumo de Impacto em Vendas")

df_ruptura = df_master[df_master['STATUS'] == 'Ruptura']
df_risco = df_master[df_master['STATUS'] == 'Risco']
df_negativo = df_master[df_master['STATUS'] == 'Venda no Negativo']

total_skus_ruptura = len(df_ruptura)
perda_diaria_total = df_ruptura['PERDA_DIARIA_RS'].sum()
perda_acumulada_total = df_ruptura['PERDA_ACUMULADA_RS'].sum()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("SKUs em Ruptura (Perdendo Venda)", f"{total_skus_ruptura}", delta=f"Sem giro há +{dias_ruptura}d", delta_color="inverse")
col2.metric("Perda Diária Estimada", f"R$ {perda_diaria_total:,.2f}", delta="Impacto Financeiro", delta_color="inverse")
col3.metric("Perda Acumulada", f"R$ {perda_acumulada_total:,.2f}", help="Venda Média Diária x Dias Sem Venda.")
col4.metric(f"Risco (Cobertura < {cobertura_alvo}d)", f"{len(df_risco)} itens", delta="Atenção Compras", delta_color="off")
col5.metric(f"Venda no Negativo", f"{len(df_negativo)} itens", delta="Furo de Estoque", delta_color="off")

st.divider()

cols_view = [
    'FILIAL', 'CODIGO', 'DESCRIÇÃO', 'CURVA', 'SALDO', 'VENDA_DIA', 
    'DIAS_COBERTURA', 'ULTIMA_VENDA', 'DIAS_SEM_VENDA', 'PERDA_DIARIA_RS', 'PERDA_ACUMULADA_RS'
]

aba_ruptura, aba_risco, aba_negativo, aba_saudavel, aba_sem_giro = st.tabs([
    "🚨 Ruptura Atual (Perdendo Dinheiro)", 
    "⚠️ Risco de Ruptura Futura", 
    "👻 Venda no Negativo",
    "✅ Estoque Saudável", 
    "💤 Sem Giro no Período"
])

with aba_ruptura:
    st.write(f"Itens com Saldo Zero e que não registram vendas há pelo menos **{dias_ruptura} dias**.")
    df_view_ruptura = df_ruptura.sort_values(by='PERDA_DIARIA_RS', ascending=False)[cols_view].copy()
    
    df_view_ruptura['ULTIMA_VENDA'] = df_view_ruptura['ULTIMA_VENDA'].dt.strftime('%d/%m/%Y')
    df_view_ruptura['VENDA_DIA'] = df_view_ruptura['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_ruptura['PERDA_DIARIA_RS'] = df_view_ruptura['PERDA_DIARIA_RS'].apply(lambda x: f"R$ {x:,.2f}")
    df_view_ruptura['PERDA_ACUMULADA_RS'] = df_view_ruptura['PERDA_ACUMULADA_RS'].apply(lambda x: f"R$ {x:,.2f}")
    df_view_ruptura['DIAS_SEM_VENDA'] = df_view_ruptura['DIAS_SEM_VENDA'].apply(lambda x: f"{x} dias")
    df_view_ruptura['DIAS_COBERTURA'] = "-"
    
    st.dataframe(df_view_ruptura, use_container_width=True, hide_index=True)

with aba_risco:
    st.write(f"Itens com saldo na loja, mas que a velocidade de saída cobre menos que os **{cobertura_alvo} dias** de segurança estabelecidos.")
    df_view_risco = df_risco.sort_values(by='DIAS_COBERTURA', ascending=True)[cols_view].drop(columns=['PERDA_ACUMULADA_RS', 'PERDA_DIARIA_RS', 'ULTIMA_VENDA']).copy()
    
    df_view_risco['VENDA_DIA'] = df_view_risco['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_risco['DIAS_COBERTURA'] = df_view_risco['DIAS_COBERTURA'].apply(lambda x: f"{x:.1f} dias")
    df_view_risco['DIAS_SEM_VENDA'] = df_view_risco['DIAS_SEM_VENDA'].apply(lambda x: f"{x} dias")
    
    st.dataframe(df_view_risco, use_container_width=True, hide_index=True)

with aba_negativo:
    st.write("Itens que estão com Saldo <= 0 no sistema, mas **continuam vendendo** (registraram saída muito recentemente). Isso indica furo de estoque.")
    df_view_neg = df_negativo.sort_values(by='DIAS_SEM_VENDA', ascending=True)[cols_view].drop(columns=['PERDA_ACUMULADA_RS', 'PERDA_DIARIA_RS']).copy()
    
    df_view_neg['ULTIMA_VENDA'] = df_view_neg['ULTIMA_VENDA'].dt.strftime('%d/%m/%Y')
    df_view_neg['VENDA_DIA'] = df_view_neg['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_neg['DIAS_SEM_VENDA'] = df_view_neg['DIAS_SEM_VENDA'].apply(lambda x: f"{x} dias")
    df_view_neg['DIAS_COBERTURA'] = "-"
    
    st.dataframe(df_view_neg, use_container_width=True, hide_index=True)

with aba_saudavel:
    st.write("Itens que registraram vendas no período e possuem saldo suficiente para cobrir os dias de segurança.")
    df_ok = df_master[df_master['STATUS'] == 'Saudável'].copy()
    df_view_ok = df_ok.sort_values(by='DIAS_COBERTURA', ascending=True)[['FILIAL', 'CODIGO', 'DESCRIÇÃO', 'CURVA', 'SALDO', 'VENDA_DIA', 'DIAS_SEM_VENDA', 'DIAS_COBERTURA']].copy()
    
    df_view_ok['VENDA_DIA'] = df_view_ok['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_ok['DIAS_SEM_VENDA'] = df_view_ok['DIAS_SEM_VENDA'].apply(lambda x: f"{x} dias")
    df_view_ok['DIAS_COBERTURA'] = df_view_ok['DIAS_COBERTURA'].apply(lambda r: f"{r:.0f} dias")
    
    st.dataframe(df_view_ok, use_container_width=True, hide_index=True)

with aba_sem_giro:
    st.write(f"Itens com saldo em estoque, mas que não registraram NENHUMA venda nos últimos **{dias_analise} dias** analisados.")
    df_sg = df_master[df_master['STATUS'] == 'Sem Giro'].copy()
    df_view_sg = df_sg.sort_values(by='SALDO', ascending=False)[['FILIAL', 'CODIGO', 'DESCRIÇÃO', 'CURVA', 'SALDO', 'VENDA_DIA', 'DIAS_SEM_VENDA', 'DIAS_COBERTURA']].copy()
    
    df_view_sg['VENDA_DIA'] = "0.00 un/dia"
    df_view_sg['DIAS_SEM_VENDA'] = df_view_sg['DIAS_SEM_VENDA'].apply(lambda x: f"+{x} dias")
    df_view_sg['DIAS_COBERTURA'] = "Sem Giro (999+)"
    
    st.dataframe(df_view_sg, use_container_width=True, hide_index=True)

st.divider()
st.markdown("### 📥 Exportar Análise Completa")
output = io.BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_excel = df_master.copy()
    df_excel['ULTIMA_VENDA'] = df_excel['ULTIMA_VENDA'].dt.tz_localize(None)
    df_excel.to_excel(writer, sheet_name="Projecao_Estoque", index=False)
st.download_button("Baixar Excel Completo (Com Previsão de Perdas)", data=output.getvalue(), file_name=f"Projecao_Ruptura_Risco_{datetime.date.today()}.xlsx", type="primary")
