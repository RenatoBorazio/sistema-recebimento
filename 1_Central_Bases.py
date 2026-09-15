import streamlit as st
import pandas as pd
import io
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Central de Bases - Protheus", layout="wide")
st.title("⚙️ Central de Bases (Nuvem)")

st.markdown("""
Esta central atua como hub, garantindo que os dados sincronizados estejam disponíveis 
instantaneamente para os módulos de Inventário e de Confronto de XML.
""")

# Configuração do banco de dados (Supabase)
# Lembre-se de configurar a variável no seu st.secrets
@st.cache_resource
def init_connection():
    # URL de exemplo; substitua pela string de conexão real do Supabase
    db_url = st.secrets.get("SUPABASE_DB_URL", "sqlite:///banco_nuvem.db")
    return create_engine(db_url)

engine = init_connection()

def detectar_separador(file_bytes):
    """Motor simples para detectar o separador de arquivos TXT/CSV."""
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
    nome_arquivo = uploaded_file.name.lower()
    
    if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
        bytes_data = uploaded_file.getvalue()
        sep = detectar_separador(bytes_data)
        
        # Tratamento para alinhar cabeçalhos do Protheus que contêm metadados no topo
        # on_bad_lines='skip' ajuda a ignorar quebras no cabeçalho inicial
        df = pd.read_csv(io.BytesIO(bytes_data), sep=sep, on_bad_lines='skip', engine='python')
        
    elif nome_arquivo.endswith('.xlsx') or nome_arquivo.endswith('.xls'):
        df = pd.read_excel(uploaded_file)
    else:
        return None

    # Padronização e remoção de duplicatas no cabeçalho
    df.columns = df.columns.str.strip().str.upper()
    df = limpar_colunas_duplicadas(df)
    
    return df

def salvar_no_banco(df, nome_tabela):
    with engine.connect() as conn:
        df.to_sql(nome_tabela, conn, if_exists='replace', index=False)
        conn.commit()

# --- Interface da Aplicação ---

tipo_base = st.selectbox(
    "Selecione a base que deseja sincronizar:",
    ["Curva ABC", "Cadastro de Produtos", "Pedidos", "Estoque Inicial", "Notas Pendentes"]
)

uploaded_file = st.file_uploader(
    f"Faça o upload do arquivo para {tipo_base} (Excel, CSV ou TXT)", 
    type=["csv", "txt", "xlsx", "xls"]
)

if uploaded_file is not None:
    with st.spinner("Processando o arquivo e ajustando cabeçalhos do Protheus..."):
        df = processar_arquivo(uploaded_file)
        
        if df is not None:
            st.success("Arquivo lido e padronizado com sucesso!")
            st.dataframe(df.head())
            
            if st.button("Sincronizar com a Nuvem"):
                with st.spinner(f"Gravando base '{tipo_base}' no Supabase..."):
                    # Mapeamento do nome das tabelas no banco de dados
                    tabelas = {
                        "Curva ABC": "base_curva_abc",
                        "Cadastro de Produtos": "base_produtos",
                        "Pedidos": "base_pedidos",
                        "Estoque Inicial": "base_estoque",
                        "Notas Pendentes": "base_notas"
                    }
                    nome_tabela = tabelas[tipo_base]
                    
                    try:
                        salvar_no_banco(df, nome_tabela)
                        st.success(f"✅ Base '{tipo_base}' sincronizada com sucesso e pronta para uso na equipe!")
                    except Exception as e:
                        st.error(f"Erro ao salvar no banco de dados: {e}")
        else:
            st.error("Formato de arquivo não suportado ou erro durante a leitura.")
