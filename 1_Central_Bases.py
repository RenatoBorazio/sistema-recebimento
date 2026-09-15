import streamlit as st
import pandas as pd
import io
from sqlalchemy import create_engine

st.set_page_config(page_title="Central de Bases - Protheus", layout="wide")
st.title("⚙️ Central de Bases (Nuvem)")

st.markdown("""
Faça o upload dos arquivos extraídos do Protheus. 
Cada base sincronizada aqui ficará disponível em tempo real para os demais módulos do sistema.
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

# --- Função de Renderização Padrão para Uploads ---
def renderizar_bloco_upload(tipo_base, nome_tabela):
    """Gera o componente de upload, preview e botão de sincronização."""
    arquivo = st.file_uploader(
        f"Anexe o relatório: {tipo_base} (CSV, TXT, Excel)", 
        type=["csv", "txt", "xlsx", "xls"],
        key=nome_tabela
    )
    
    if arquivo:
        with st.spinner(f"Processando {tipo_base}..."):
            df = processar_arquivo(arquivo)
            if df is not None:
                st.success("Leitura concluída! Visualização dos primeiros registros:")
                # Mostramos apenas as 3 primeiras linhas para não ocupar muito espaço vertical
                st.dataframe(df.head(3)) 
                
                if st.button(f"Sincronizar {tipo_base} na Nuvem", key=f"btn_{nome_tabela}"):
                    with st.spinner("Gravando no banco de dados..."):
                        try:
                            salvar_no_banco(df, nome_tabela)
                            st.success(f"✅ Base '{tipo_base}' atualizada com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
            else:
                st.error("Formato não suportado ou erro na leitura.")


# --- Estrutura Principal de Abas ---
aba_produtos, aba_pedidos, aba_estoque, aba_notas = st.tabs([
    "📦 Cadastro de Produtos", 
    "🛒 Pedidos", 
    "📦 Estoque Inicial", 
    "🧾 Notas Pendentes"
])

# === ABA 1: CADASTRO DE PRODUTOS ===
with aba_produtos:
    st.markdown("### Bases Relacionadas a Produtos")
    st.info("Importe as planilhas do Protheus referentes ao cadastro central, classificação ABC e códigos de barras extras.")
    
    # Usando st.expander para organizar os 3 campos sem poluir a tela
    with st.expander("1. Planilha de Cadastro Principal (SB1)", expanded=True):
        renderizar_bloco_upload("Cadastro (SB1)", "base_sb1")
        
    with st.expander("2. Planilha da Curva ABC", expanded=False):
        renderizar_bloco_upload("Curva ABC", "base_curva_abc")
        
    with st.expander("3. Planilha de Barras Adicional (SLK)", expanded=False):
        renderizar_bloco_upload("Barras Adicional (SLK)", "base_slk")

# === ABA 2: PEDIDOS ===
with aba_pedidos:
    st.subheader("Sincronização: Pedidos")
    renderizar_bloco_upload("Pedidos", "base_pedidos")

# === ABA 3: ESTOQUE INICIAL ===
with aba_estoque:
    st.subheader("Sincronização: Estoque Inicial")
    renderizar_bloco_upload("Estoque Inicial", "base_estoque")

# === ABA 4: NOTAS PENDENTES ===
with aba_notas:
    st.subheader("Sincronização: Notas Pendentes")
    renderizar_bloco_upload("Notas Pendentes", "base_notas")
