import streamlit as st
import pandas as pd

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

def detectar_separador(arquivo_enviado, encoding):
    """Detecta se o arquivo usa ';' ou ',' olhando as primeiras linhas."""
    arquivo_enviado.seek(0)
    amostra = "".join([arquivo_enviado.readline().decode(encoding, errors='ignore') for _ in range(5)])
    arquivo_enviado.seek(0)
    return ';' if amostra.count(';') >= amostra.count(',') else ','

def deduplicar_colunas(colunas):
    """Renomeia colunas repetidas para evitar erro no banco."""
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

# 3. Criando a interface de upload para cada arquivo
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
                    if arquivo_enviado.name.lower().endswith('.xlsx'):
                        df = pd.read_excel(arquivo_enviado, dtype=str)
                    else:
                        try:
                            sep = detectar_separador(arquivo_enviado, 'utf-8')
                            df = pd.read_csv(arquivo_enviado, dtype=str, encoding='utf-8', sep=sep)
                        except UnicodeDecodeError:
                            arquivo_enviado.seek(0)
                            sep = detectar_separador(arquivo_enviado, 'latin1')
                            df = pd.read_csv(arquivo_enviado, dtype=str, encoding='latin1', sep=sep)
                    
                    # Limpeza Inteligente de Cabeçalhos
                    colunas_atuais = " ".join([str(c).upper() for c in df.columns])
                    tem_chave = any(palavra in colunas_atuais for palavra in ["PRODUTO", "CODIGO", "CÓDIGO", "FILIAL"])
                    precisa_ajustar = not tem_chave
                    
                    if precisa_ajustar:
                        for i in range(min(25, len(df))):
                            linha_atual = " ".join([str(x).upper() for x in df.iloc[i].values])
                            if "PRODUTO" in linha_atual or "CODIGO" in linha_atual or "CÓDIGO" in linha_atual or "FILIAL" in linha_atual:
                                df.columns = df.iloc[i]
                                df = df.iloc[i+1:].reset_index(drop=True)
                                df = df.loc[:, df.columns.notna()]
                                break
                    
                    df.columns = deduplicar_colunas(df.columns)

                    # --- NOVA LÓGICA INCREMENTAL (ANTI-JOIN DE ALTA VELOCIDADE) ---
                    if nome_tabela in ["sd2_saidas", "kardex_movimentos"] and "Incremental" in modo_upload:
                        st.text("🔄 Consultando banco de dados para separar apenas linhas inéditas...")
                        try:
                            df_banco = conn.query(f"SELECT * FROM {nome_tabela}", ttl=0).astype(str)
                            
                            # Limpeza para garantir comparação perfeita
                            df_limpo = df.astype(str).apply(lambda x: x.str.strip())
                            df_banco_limpo = df_banco.apply(lambda x: x.str.strip())
                            
                            # Manter apenas colunas que coincidem nas duas tabelas
                            colunas_comuns = [c for c in df_limpo.columns if c in df_banco_limpo.columns]
                            
                            # Remove duplicadas dentro do arquivo recém-subido
                            df_limpo = df_limpo.drop_duplicates(subset=colunas_comuns)
                            
                            # Pulo do gato: Anti-Join para separar O QUE NÃO EXISTE NO BANCO AINDA
                            df_merge = pd.merge(df_limpo, df_banco_limpo, on=colunas_comuns, how='left', indicator=True)
                            df_inserir = df_merge[df_merge['_merge'] == 'left_only'].drop(columns=['_merge'])
                            
                            if not df_inserir.empty:
                                st.text(f"🚀 Inserindo {len(df_inserir)} novas linhas identificadas...")
                                # Usa APPEND ao invés de REPLACE (nunca derruba a tabela, não dá timeout)
                                df_inserir.to_sql(nome_tabela, con=conn.engine, if_exists='append', index=False, chunksize=5000)
                                st.success(f"✅ {len(df_inserir)} novas linhas incorporadas ao {nome_amigavel} com sucesso!")
                            else:
                                st.success(f"✅ Nenhuma linha nova encontrada. A base já estava totalmente atualizada com os dados deste arquivo!")
                                
                        except Exception as e:
                            # Se a tabela ainda não existe no banco, cria ela pela primeira vez
                            df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=5000)
                            st.success(f"✅ Primeira carga histórica do {nome_amigavel} criada com sucesso!")
                    else:
                        # Tabelas normais ou modo Substituição Completa (Apenas bases pequenas ou setup inicial)
                        df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=10000)
                        st.success(f"✅ {nome_amigavel} atualizado com sucesso (Substituição Completa)!")
                        
                except Exception as e:
                    st.error(f"Erro ao atualizar a base: {e}")
                    
    st.write("---")

st.info("💡 Quando você clica em 'Subir para o Banco', a tabela é atualizada instantaneamente para todos os usuários.")
