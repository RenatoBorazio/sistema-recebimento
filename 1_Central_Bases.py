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
    "Códigos de Barras Adicionais": "barras_adicionais"
}


def detectar_separador(arquivo_enviado, encoding):
    """Detecta se o arquivo usa ';' ou ',' olhando a primeira linha.
    Nem todo export do Protheus usa o mesmo separador."""
    arquivo_enviado.seek(0)
    primeira_linha = arquivo_enviado.readline().decode(encoding, errors='ignore')
    arquivo_enviado.seek(0)
    return ';' if primeira_linha.count(';') >= primeira_linha.count(',') else ','


def deduplicar_colunas(colunas):
    """Renomeia colunas repetidas para evitar erro no banco (ex: relatórios
    de estoque que repetem 'Qtd. Fim Mes' uma vez por depósito/filial).
    Segue o mesmo padrão do pandas: 2ª ocorrência vira '.1', 3ª vira '.2', etc."""
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
    
    arquivo_enviado = st.file_uploader(f"Arraste o arquivo para o {nome_amigavel}", type=["csv", "txt", "xlsx"], key=f"up_{nome_tabela}")
    
    if arquivo_enviado is not None:
        if st.button(f"Subir {nome_amigavel} para o Banco", key=f"btn_{nome_tabela}", type="primary"):
            with st.spinner(f"Lendo e formatando {nome_tabela} para a Nuvem..."):
                try:
                    # Motor inteligente: Lê Excel ou CSV
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
                    
                    # --- O RAIO-X DE CABEÇALHOS DO PROTHEUS ---
                    # Identifica se o Pandas leu a linha de metadados do Protheus (ex: SC7 ou Unnamed)
                    precisa_ajustar = any(str(c).lower().startswith('unnamed') or str(c).lower().startswith('sem nome') or str(c).upper() in ['SC7', 'SB1', 'SB2', 'SD1'] for c in df.columns)
                    
                    if precisa_ajustar:
                        # Varre as primeiras 15 linhas buscando onde estão os títulos reais
                        for i in range(min(15, len(df))):
                            linha_atual = " ".join([str(x).upper() for x in df.iloc[i].values])
                            
                            # Palavras-chave que indicam que achamos a linha de títulos de verdade
                            if "PRODUTO" in linha_atual or "CODIGO" in linha_atual or "CÓDIGO" in linha_atual or "NUMERO" in linha_atual or "FILIAL" in linha_atual:
                                # Define esta linha como o novo cabeçalho
                                df.columns = df.iloc[i]
                                # Arranca o lixo que ficou pra cima
                                df = df.iloc[i+1:].reset_index(drop=True)
                                # Limpa colunas nulas criadas sem querer
                                df = df.loc[:, df.columns.notna()]
                                break
                    # ------------------------------------------

                    # Evita erro no banco quando o relatório repete o nome de uma coluna
                    # (ex: 'Qtd. Fim Mes' aparecendo uma vez por depósito/filial)
                    df.columns = deduplicar_colunas(df.columns)

                    df.to_sql(nome_tabela, con=conn.engine, if_exists='replace', index=False)
                    st.success(f"✅ {nome_amigavel} atualizado com sucesso (Cabeçalhos alinhados)!")
                except Exception as e:
                    st.error(f"Erro ao atualizar a base: {e}")
                    
    st.write("---")

st.info("💡 Quando você clica em 'Subir para o Banco', a tabela é atualizada instantaneamente para todos os usuários.")
