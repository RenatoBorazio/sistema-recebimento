import streamlit as st
import pandas as pd
import io
from sqlalchemy import create_engine

st.set_page_config(page_title="Central de Bases - Protheus", layout="wide")
st.title("⚙️ Central de Bases (Nuvem)")

st.markdown("""
Faça o upload dos arquivos extraídos do Protheus. 
Cada base sincronizada aqui ficará disponível em tempo real para os módulos de Inventário e Confronto XML.
""")

# --- Configuração do Banco de Dados ---
@st.cache_resource
def init_connection():
    db_url = st.secrets.get("SUPABASE_DB_URL", "sqlite:///banco_nuvem.db")
    return create_engine(db_url)

engine = init_connection()

# --- Funções Auxiliares ---
def detectar_separador(file_bytes):
    """Detecta se o arquivo usa ponto e vírgula, tabulação ou vírgula."""
    amostra = file_bytes.decode('utf-8', errors='ignore')[:1024]
    if ';' in amostra: 
        return ';'
    elif '\t' in amostra: 
        return '\t'
    return ','

def limpar_colunas_duplicadas(df):
    """Deduplicação de colunas repetidas nos relatórios exportados."""
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [
            dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))
        ]
    df.columns = cols
    return df

def processar_arquivo(uploaded_file):
    """Lê o arquivo, ajusta o cabeçalho do Protheus e limpa as colunas."""
    nome_arquivo = uploaded_file.name.lower()
    
    if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
        bytes_data = uploaded_file.getvalue()
        sep = detectar_separador(bytes_data)
        # on_bad_lines='skip' ignora as quebras de metadados no cabeçalho do Protheus
        df = pd.read_csv(io.BytesIO(bytes_data), sep=sep, on_bad_lines='skip', engine='python')
        
    elif nome_arquivo.endswith('.xlsx') or nome_arquivo.endswith('.xls'):
        df = pd.read_excel(uploaded_file)
    else:
        return None

    df.columns = df.columns.str.strip().str.upper()
    df = limpar_colunas_duplicadas(df)
    return df

def salvar_no_banco(df, nome_tabela):
    """Grava os dados no banco configurado via SQLAlchemy."""
    with engine.connect() as conn:
        df.to_sql(nome_tabela, conn, if_exists='replace', index=False)
        conn.commit()

# --- Interface com Abas para Cada Base ---
# Aqui garantimos que todas as bases antigas se mantenham e adicionamos a nova (Curva ABC)
aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "Curva ABC", 
    "Cadastro de Produtos", 
    "Pedidos", 
    "Estoque Inicial", 
    "Notas Pendentes"
])

def renderizar_aba(tipo_base, nome_tabela, aba_context):
    """Função para renderizar o uploader e botão de cada aba individualmente."""
    with aba_context:
        st.subheader(f"Sincronização: {tipo_base}")
        arquivo = st.file_uploader(
            f"Anexe o relatório de {tipo_base} (CSV, TXT, Excel)", 
            type=["csv", "txt", "xlsx", "xls"],
            key=nome_tabela # Garante que cada uploader seja único
        )
        
        if arquivo:
            with st.spinner(f"Processando {tipo_base}..."):
                df = processar_arquivo(arquivo)
                if df is not None:
                    st.success("Leitura concluída! Visualização dos primeiros registros:")
                    st.dataframe(df.head())
                    
                    if st.button(f"Sincronizar {tipo_base} na Nuvem", key=f"btn_{nome_tabela}"):
                        with st.spinner("Gravando no banco de dados..."):
                            try:
                                salvar_no_banco(df, nome_tabela)
                                st.success(f"✅ Base de {tipo_base} atualizada com sucesso no Supabase!")
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
                else:
                    st.error("Formato não suportado ou erro na leitura.")

# Renderizando cada aba com sua respectiva tabela no banco
renderizar_aba("Curva ABC", "base_curva_abc", aba1)
renderizar_aba("Cadastro de Produtos", "base_produtos", aba2)
renderizar_aba("Pedidos", "base_pedidos", aba3)
renderizar_aba("Estoque Inicial", "base_estoque", aba4)
renderizar_aba("Notas Pendentes", "base_notas", aba5)
