from __future__ import annotations

import hashlib

import streamlit as st


st.set_page_config(page_title="Upload de Modelo FIDC", page_icon="📄", layout="wide")

st.title("Upload do modelo financeiro (.xlsm)")
st.markdown(
    """
Este site foi simplificado para você enviar o seu modelo financeiro em formato **.xlsm**.
Assim que o arquivo estiver disponível, poderei analisar a estrutura e ajudar a migrar
as funcionalidades para a plataforma.
"""
)

left, right = st.columns([2, 1], gap="large")

with left:
    st.subheader("1. Envie seu arquivo")
    uploaded_file = st.file_uploader(
        "Selecione um arquivo .xlsm",
        type=["xlsm"],
        accept_multiple_files=False,
        help="O arquivo não é processado ainda — apenas armazenado para análise posterior.",
    )

    if uploaded_file is None:
        st.info("Aguardando o upload do arquivo .xlsm.")
    else:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size_mb = len(file_bytes) / (1024 * 1024)

        st.success("Arquivo recebido com sucesso!")
        st.write(
            {
                "Nome": uploaded_file.name,
                "Tamanho (MB)": f"{file_size_mb:.2f}",
                "SHA256": file_hash,
            }
        )

        st.download_button(
            "Baixar o arquivo enviado",
            data=file_bytes,
            file_name=uploaded_file.name,
            mime="application/vnd.ms-excel.sheet.macroEnabled.12",
        )

with right:
    st.subheader("2. Próximos passos")
    st.markdown(
        """
- Confirmar quais abas e cálculos do modelo precisam ser replicados.
- Mapear entradas, saídas e premissas.
- Transformar a lógica em componentes da nova plataforma.
"""
    )

    st.subheader("3. Checklist")
    st.checkbox("O arquivo contém macros (.xlsm)", value=True, disabled=True)
    st.checkbox("Existe documentação ou notas no arquivo")
    st.checkbox("Há exemplos de saída esperada")

st.divider()

st.caption(
    "Se quiser incluir comentários adicionais, descreva no chat quais partes do modelo são mais críticas."
)
