import streamlit as st
import pandas as pd
import io
from sqlalchemy import text

st.set_page_config(page_title="Central de Bases - Protheus", layout="wide")

st.title("⚙️ Central de Bases (Nuvem)")
st.markdown("Faça o upload dos relatórios do Protheus. Eles serão atualizados em tempo real no banco de dados corporativo para toda a equipe.")

# 1. Conectando ao Banco de Dados 
conn = st.connection("supabase", type="sql")

# 2. Mapeamento das bases
bases_esperadas = {
    "Cadastro de Produtos (SB1)": "cadastro_produtos",
    "Base de Pedidos (PC)": "base_pedidos",
    "Estoque Inicial": "estoque_inicial",
    "Notas Pendentes (SD1)": "sd1_pendente",
    "Códigos de Barras Adicionais": "barras_adicionais",
    "Curva ABC": "base_curva_abc",
    "Saídas / Vendas (SD2)": "sd2_saidas",
    "Movimentações (Kardex)": "kardex_movimentos"
}

def carregar_dataframe(arquivo_enviado):
    """Lê o arquivo ignorando os lixos do Protheus nas primeiras linhas"""
    if arquivo_enviado.name.lower().endswith('.xlsx'):
        return pd.read_excel(arquivo_enviado, dtype=str)
    
    # Para CSV e TXT do Protheus
    arquivo_enviado.seek(0)
    bytes_data = arquivo_enviado.read()
    
    # Descobre o Encoding (utf-8 ou latin1)
    encoding = 'utf-8'
    try:
        bytes_data.decode('utf-8')
    except UnicodeDecodeError:
        encoding = 'latin1'
        
    linhas = bytes_data.split(b'\n')
    
    # Detecta o separador correto
    amostra = b"".join(linhas[:10]).decode(encoding, errors='ignore')
    sep = ';' if amostra.count(';') >= amostra.count(',') else ','
    
    # Identifica a linha onde as colunas de verdade começam (ignora a palavra "SD2" sozinha)
    skip_idx = 0
    for i, l in enumerate(linhas):
        if l.decode(encoding, errors='ignore').count(sep) >= 3:
            skip_idx = i
            break
            
    arquivo_enviado.seek(0)
    return pd.read_csv(arquivo_enviado, dtype=str, encoding=encoding, sep=sep, skiprows=skip_idx)

def deduplicar_colunas(colunas):
    contagem = {}
    novas = []
    for c in colunas:
        nome = str(c)
        if nome not in contagem:
            contagem[nome] = 0
            novas.append(nome)
        else:
            contagem[nome] += 1
            novas.append(f"{nome}.{contagem[nome]}")
    return novas

st.divider()

# 3. Criando a interface de upload
for nome_amigavel, nome_tabela in bases_esperadas.items():
    st.subheader(f"Atualizar {nome_amigavel}")
    
    # --- MODO INCREMENTAL ---
    modo_upload = "Substituir Tudo"
    if nome_tabela in ["sd2_saidas", "kardex_movimentos"]:
        st.info(f"💡 Como o {nome_amigavel} costuma ser muito grande, você pode subir apenas a planilha dos dias faltantes. O sistema identificará apenas as linhas novas.")
        modo_upload = st.radio(
            "Modo de atualização:", 
            ["Adicionar Dias Novos (Incremental)", "Substituir Base Completa (Zerar histórico)"],
            key=f"modo_{nome_tabela}"
        )
    
    arquivo_enviado = st.file_uploader(f"Arraste o arquivo para o {nome_amigavel}", type=["csv", "txt", "xlsx"], key=f"up_{nome_tabela}")
    
    if arquivo_enviado is not None:
        if st.button(f"Subir {nome_amigavel} para o Banco", key=f"btn_{nome_tabela}", type="primary"):
            with st.spinner(f"Processando e enviando {nome_tabela} para a Nuvem..."):
                try:
                    # Leitura Antibug
                    df = carregar_dataframe(arquivo_enviado)
                    
                    # Raio-X de Cabeçalhos (Para Excel e sujeiras remanescentes)
                    colunas_atuais = " ".join([str(c).upper() for c in df.columns])
                    tem_chave = any(palavra in colunas_atuais for palavra in ["PRODUTO", "CODIGO", "CÓDIGO", "FILIAL"])
                    
                    if not tem_chave:
                        for i in range(min(25, len(df))):
                            linha_atual = " ".join([str(x).upper() for x in df.iloc[i].values])
                            if "PRODUTO" in linha_atual or "CODIGO" in linha_atual or "CÓDIGO" in linha_atual or "FILIAL" in linha_atual:
                                df.columns = df.iloc[i]
                                df = df.iloc[i+1:].reset_index(drop=True)
                                df = df.loc[:, df.columns.notna()]
                                break
                    
                    df.columns = deduplicar_colunas(df.columns)

                    # --- LÓGICA INCREMENTAL NATIVA NO BANCO ---
                    if nome_tabela in ["sd2_saidas", "kardex_movimentos"] and "Incremental" in modo_upload:
                        st.text("🚀 Injetando os novos dados na nuvem...")
                        df.to_sql(nome_tabela, con=conn.engine, if_exists='append', index=False, chunksize=5000)

                        st.text("🧹 Removendo dados duplicados diretamente no servidor...")
                        df_cols = conn.query(f"SELECT * FROM {nome_tabela} LIMIT 0", ttl=0)
                        colunas_banco = [f'"{str(c)}"' for c in df_cols.columns]
                        group_by_clause = ", ".join(colunas_banco)

                        sql_dedup = f"""
                            DELETE FROM {nome_tabela}
                            WHERE ctid NOT IN (
                                SELECT max(ctid)
                                FROM {nome_tabela}
                                GROUP BY {group_by_clause}
                            );
                        """
                        with conn.session as s:
                            s.execute(text(sql_dedup))
                            s.commit()

                        st.success(f"✅ Arquivo incorporado e duplicidades removidas com sucesso na nuvem!")
                        
                    else:
                        df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=10000)
                        st.success(f"✅ {nome_amigavel} atualizado com sucesso (Substituição Completa)!")
                        
                except Exception as e:
                    st.error(f"Erro ao atualizar a base: {e}")
                    
    st.write("---")
