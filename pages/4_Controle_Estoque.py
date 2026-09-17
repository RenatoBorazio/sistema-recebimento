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
        df_cad_raw = conn.query("SELECT * FROM cadastro_produtos", ttl=0).astype(str)
        df_cad_raw.columns = [str(c).upper().strip() for c in df_cad_raw.columns]
        c_int = obter_primeira_coluna(df_cad_raw, ['CÓDIGO INTERNO', 'CODIGO', 'CÓDIGO', 'PRODUTO'])
        c_desc = obter_primeira_coluna(df_cad_raw, ['DESCRIÇÃO SB1', 'DESCRICAO SB1', 'DESCRICAO', 'DESCRIÇÃO', 'NOME'])
        c_preco = obter_primeira_coluna(df_cad_raw, ['PRECO VENDA', 'PREÇO VENDA', 'ULTIMO PRECO', 'ULT. PRECO'])
        
        df_cad = pd.DataFrame()
        if c_int:
            df_cad['CODIGO'] = df_cad_raw[c_int].astype(str).replace(r'\.0$', '', regex=True).str.strip()
            df_cad['DESCRIÇÃO'] = df_cad_raw[c_desc].astype(str).strip() if c_desc else ""
            df_cad['PRECO_VENDA'] = safe_numeric(df_cad_raw[c_preco]) if c_preco else 0.0
    except Exception as e: 
        df_cad = pd.DataFrame()

    # 2. Carregar Estoque Atual (Mapeamento Expandido)
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
            erros_log.append("Estoque: As colunas Produto e Saldo não foram encontradas (Títulos mapeados: PRODUTO, CODIGO, B2_COD, SALDO, B2_QATU, QUANTIDADE, etc).")
    except Exception as e:
        df_est = pd.DataFrame()
        erros_log.append(f"Falha ao conectar no Estoque Inicial: {str(e)}")

    # 3. Carregar SD2 OTIMIZADO
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
            erros_log.append("SD2: As colunas de Produto ou Emissao não foram encontradas na tabela do banco.")
    except Exception as e: 
        df_sd2 = pd.DataFrame()
        erros_log.append(f"Falha ao conectar no SD2: {str(e)}")

    # 4. Curva ABC (Opcional)
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

with st.spinner("Conectando ao banco de dados e processando milhares de registros de venda..."):
    df_cad, df_est, df_sd2, df_curva, erros_log = carregar_dados()

# --- DIAGNÓSTICO DETALHADO DE ALERTAS ---
if df_est.empty and df_sd2.empty:
    st.error("🚨 Faltam DUAS bases no sistema: O **Estoque Inicial** e o **SD2 (Saídas)**. Por favor, suba ambos na Central de Bases.")
    if erros_log:
        with st.expander("🛠️ Ver Logs de Erro do Banco de Dados"):
            for err in erros_log: st.code(err)
    st.stop()
elif df_est.empty:
    st.error("🚨 Falta o **Estoque Inicial**! O sistema achou as vendas, mas não o estoque. Por favor, atualize o Estoque na Central de Bases.")
    if erros_log:
        with st.expander("🛠️ Ver Logs de Erro do Banco de Dados"):
            for err in erros_log: st.code(err)
    st.stop()
elif df_sd2.empty:
    st.error("🚨 Falta a base de **Saídas (SD2)**! O sistema achou o estoque, mas as vendas não foram carregadas.")
    if erros_log:
        with st.expander("🛠️ Ver Logs de Erro do Banco de Dados"):
            for err in erros_log: st.code(err)
    st.stop()

# --- FILTROS LATERAIS ---
with st.sidebar:
    st.header("⚙️ Configurações de Cálculo")
    st.write("Ajuste a janela de tempo para definir a Venda Média Diária.")
    dias_analise = st.slider("Considerar vendas dos últimos X dias:", min_value=15, max_value=365, value=90, step=15)
    
    filiais_disp = sorted([f for f in df_est['FILIAL'].unique() if f.strip() != ""])
    filiais_selecionadas = st.multiselect("Filtrar por Filial:", options=filiais_disp, default=filiais_disp)
    
    cobertura_alvo = st.number_input("Estoque de Segurança (Dias):", min_value=1, max_value=60, value=15, help="Se o estoque cobrir menos dias que isso, será considerado Risco de Ruptura.")

# --- MOTOR DE CÁLCULO DE RUPTURA E PERDA ---
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
    df_master['PRECO_VENDA'] = df_master['PRECO_VENDA'].fillna(0)
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

# --- LÓGICA CORE ---
df_master['DIAS_COBERTURA'] = df_master.apply(
    lambda r: (r['SALDO'] / r['VENDA_DIA']) if (r['VENDA_DIA'] > 0 and r['SALDO'] > 0) else (999 if r['SALDO'] > 0 else 0), axis=1
)

def calcular_perda(row):
    if row['SALDO'] <= 0 and row['VENDA_DIA'] > 0:
        dias_zerado = 0
        if pd.notna(row['ULTIMA_VENDA']):
            dias_zerado = (hoje - row['ULTIMA_VENDA']).days
            if dias_zerado < 0: dias_zerado = 0
        
        perda_diaria_rs = row['VENDA_DIA'] * row['PRECO_VENDA']
        perda_acumulada_rs = dias_zerado * perda_diaria_rs
        
        return pd.Series([dias_zerado, perda_diaria_rs, perda_acumulada_rs, "Ruptura"])
        
    elif row['SALDO'] > 0 and row['VENDA_DIA'] > 0 and row['DIAS_COBERTURA'] <= cobertura_alvo:
        return pd.Series([0, 0.0, 0.0, "Risco"])
        
    return pd.Series([0, 0.0, 0.0, "OK"])

df_master[['DIAS_ZERADO', 'PERDA_DIARIA_RS', 'PERDA_ACUMULADA_RS', 'STATUS']] = df_master.apply(calcular_perda, axis=1)

if filiais_selecionadas:
    df_master = df_master[df_master['FILIAL'].isin(filiais_selecionadas)]

# --- PAINEL DE KPIs EXECUTIVOS ---
st.markdown("### 📊 Resumo de Impacto em Vendas")

df_ruptura = df_master[df_master['STATUS'] == 'Ruptura']
df_risco = df_master[df_master['STATUS'] == 'Risco']

total_skus_ruptura = len(df_ruptura)
perda_diaria_total = df_ruptura['PERDA_DIARIA_RS'].sum()
perda_acumulada_total = df_ruptura['PERDA_ACUMULADA_RS'].sum()
skus_risco = len(df_risco)

col1, col2, col3, col4 = st.columns(4)
col1.metric("SKUs em Ruptura (Estoque Zero)", f"{total_skus_ruptura} itens", delta="- Crítico", delta_color="inverse")
col2.metric("Perda Diária Atual Estimada", f"R$ {perda_diaria_total:,.2f}", delta="Custo Diário da Ruptura", delta_color="inverse")
col3.metric("Venda Perdida Acumulada", f"R$ {perda_acumulada_total:,.2f}", help="Baseado na Venda Média Diária x Dias desde a Última Venda registrada.")
col4.metric(f"Risco (Cobre < {cobertura_alvo} dias)", f"{skus_risco} itens", delta="Atenção Compras", delta_color="off")

st.divider()

cols_view = [
    'FILIAL', 'CODIGO', 'DESCRIÇÃO', 'CURVA', 'SALDO', 'VENDA_DIA', 
    'DIAS_COBERTURA', 'ULTIMA_VENDA', 'DIAS_ZERADO', 'PERDA_DIARIA_RS', 'PERDA_ACUMULADA_RS'
]

aba_ruptura, aba_risco, aba_saudavel = st.tabs(["🚨 Ruptura Atual (Perdendo Dinheiro)", "⚠️ Risco de Ruptura Futura", "✅ Estoque Saudável / Sem Giro"])

with aba_ruptura:
    st.markdown("#### Produtos Zerados com Giro Confirmado")
    st.write("Estes itens estão com Saldo Zero e possuem histórico de vendas recente. A tabela mostra a estimativa de dinheiro que a loja está deixando de faturar.")
    
    df_view_ruptura = df_ruptura.sort_values(by='PERDA_DIARIA_RS', ascending=False)[cols_view].copy()
    
    df_view_ruptura['ULTIMA_VENDA'] = df_view_ruptura['ULTIMA_VENDA'].dt.strftime('%d/%m/%Y')
    df_view_ruptura['VENDA_DIA'] = df_view_ruptura['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_ruptura['PERDA_DIARIA_RS'] = df_view_ruptura['PERDA_DIARIA_RS'].apply(lambda x: f"R$ {x:,.2f}")
    df_view_ruptura['PERDA_ACUMULADA_RS'] = df_view_ruptura['PERDA_ACUMULADA_RS'].apply(lambda x: f"R$ {x:,.2f}")
    df_view_ruptura['DIAS_COBERTURA'] = "-"
    
    st.dataframe(df_view_ruptura, use_container_width=True, hide_index=True)

with aba_risco:
    st.markdown(f"#### Alerta: Cobertura menor que {cobertura_alvo} dias")
    st.write("Estes itens ainda têm saldo na loja, mas a velocidade de saída é alta. Acione Compras para evitar que entrem em ruptura.")
    
    df_view_risco = df_risco.sort_values(by='DIAS_COBERTURA', ascending=True)[cols_view].drop(columns=['DIAS_ZERADO', 'PERDA_ACUMULADA_RS', 'PERDA_DIARIA_RS', 'ULTIMA_VENDA']).copy()
    
    df_view_risco['VENDA_DIA'] = df_view_risco['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia")
    df_view_risco['DIAS_COBERTURA'] = df_view_risco['DIAS_COBERTURA'].apply(lambda x: f"{x:.1f} dias")
    
    st.dataframe(df_view_risco, use_container_width=True, hide_index=True)

with aba_saudavel:
    st.markdown("#### Produtos Saudáveis ou Sem Saída")
    df_ok = df_master[df_master['STATUS'] == 'OK'].copy()
    df_view_ok = df_ok.sort_values(by='DIAS_COBERTURA', ascending=False)[['FILIAL', 'CODIGO', 'DESCRIÇÃO', 'CURVA', 'SALDO', 'VENDA_DIA', 'DIAS_COBERTURA']].copy()
    
    df_view_ok['VENDA_DIA'] = df_view_ok['VENDA_DIA'].apply(lambda x: f"{x:.2f} un/dia" if x > 0 else "0.00")
    df_view_ok['DIAS_COBERTURA'] = df_view_ok.apply(lambda r: f"{r['DIAS_COBERTURA']:.0f} dias" if r['VENDA_DIA'] != "0.00" else "Sem Giro (999+)", axis=1)
    
    st.dataframe(df_view_ok, use_container_width=True, hide_index=True)

st.divider()
st.markdown("### 📥 Exportar Análise Completa")
output = io.BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_excel = df_master.copy()
    df_excel['ULTIMA_VENDA'] = df_excel['ULTIMA_VENDA'].dt.tz_localize(None)
    df_excel.to_excel(writer, sheet_name="Projecao_Estoque", index=False)
st.download_button("Baixar Excel Completo (Com Previsão de Perdas)", data=output.getvalue(), file_name=f"Projecao_Ruptura_Risco_{datetime.date.today()}.xlsx", type="primary")
