st.divider()
st.markdown("### 📊 Atualizar Base da Curva ABC")
st.write("Base utilizada para priorização de inventário e alerta de rupturas no recebimento.")
arq_abc = st.file_uploader("Subir base Curva ABC (Excel)", type=["xlsx", "xls"], key="upload_abc")

if arq_abc:
    if st.button("Sincronizar Curva ABC na Nuvem", type="primary", use_container_width=True):
        with st.spinner("Lendo e enviando Curva ABC para a nuvem..."):
            try:
                df_abc_up = pd.read_excel(arq_abc)
                with conn.session as s:
                    s.execute(text("DELETE FROM curva_abc"))
                    s.commit()
                df_abc_up.to_sql("curva_abc", con=conn.engine, if_exists='replace', index=False)
                st.success("✅ Curva ABC sincronizada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar Curva ABC: {e}")
