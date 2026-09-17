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
    "Saídas / Vendas (SD2)": "sd2_saidas"
}

def detectar_separador(arquivo_enviado, encoding):
    """Detecta se o arquivo usa ';' ou ',' olhando as primeiras linhas."""
    arquivo_enviado.seek(0)
    # Lendo as primeiras 5 linhas para não ser enganado por palavras soltas do Protheus na linha 1
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
    
    # --- MODO INCREMENTAL PARA SD2 ---
    modo_upload = "Substituir Tudo"
    if nome_tabela == "sd2_saidas":
        st.info("💡 Como o SD2 é muito grande, você pode subir apenas a planilha dos dias faltantes. O sistema junta com o histórico e remove as duplicidades automaticamente.")
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
                    # Lê Excel ou CSV mantendo tudo como texto puro
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
                    
                    # --- RAIO-X DE CABEÇALHOS DO PROTHEUS ---
                    precisa_ajustar = any(str(c).lower().startswith('unnamed') or str(c).lower().startswith('sem nome') or str(c).upper() in ['SC7', 'SB1', 'SB2', 'SD1', 'SD2'] for c in df.columns)
                    
                    if precisa_ajustar:
                        for i in range(min(15, len(df))):
                            linha_atual = " ".join([str(x).upper() for x in df.iloc[i].values])
                            if "PRODUTO" in linha_atual or "CODIGO" in linha_atual or "CÓDIGO" in linha_atual or "NUMERO" in linha_atual or "FILIAL" in linha_atual:
                                df.columns = df.iloc[i]
                                df = df.iloc[i+1:].reset_index(drop=True)
                                df = df.loc[:, df.columns.notna()]
                                break
                    
                    df.columns = deduplicar_colunas(df.columns)

                    # --- SALVAMENTO NO BANCO (Lógica Incremental SD2) ---
                    if nome_tabela == "sd2_saidas" and "Incremental" in modo_upload:
                        st.text("🔄 Baixando histórico, mesclando e apagando duplicidades...")
                        try:
                            df_banco = conn.query(f"SELECT * FROM {nome_tabela}", ttl=0).astype(str)
                            # Concatena a base antiga com a planilha nova
                            df_final = pd.concat([df_banco, df])
                            # A mágica da proteção: dropa qualquer linha que seja 100% idêntica (Filial, NF, Data, Qtd)
                            df_final = df_final.drop_duplicates(keep='last')
                            
                            # Chunksize 10000 salva de pacotinho em pacotinho, impedindo que o banco de dados trave por excesso de megabytes
                            df_final.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=10000)
                            st.success(f"✅ Dias novos incorporados ao {nome_amigavel} com sucesso!")
                        except Exception as e:
                            # Se falhar (ex: a tabela SD2 ainda não foi criada no banco de dados)
                            df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=10000)
                            st.success(f"✅ Primeira carga histórica do {nome_amigavel} criada com sucesso!")
                    else:
                        # Tabelas normais ou modo Substituição Completa
                        df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False, chunksize=10000)
                        st.success(f"✅ {nome_amigavel} atualizado com sucesso (Substituição Completa)!")
                        
                except Exception as e:
                    st.error(f"Erro ao atualizar a base: {e}")
                    
    st.write("---")

st.info("💡 Quando você clica em 'Subir para o Banco', a tabela é atualizada instantaneamente para todos os usuários.")
