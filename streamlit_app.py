import streamlit as st

st.set_page_config(
    page_title="Airbnb Dashboard",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 Airbnb Dashboard")
st.write("O meu painel de gestão do apartamento.")

ficheiro = st.file_uploader(
    "Seleciona o CSV exportado do Airbnb",
    type=["csv"],
)

if ficheiro is not None:
    st.success("Ficheiro recebido. A análise será adicionada no próximo passo.")