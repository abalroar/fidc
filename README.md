# FIDC Amortização (Streamlit)

Aplicação Streamlit para simular o cronograma de amortização e waterfall por classes de cotas.

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt`

```bash
pip install -r requirements.txt
```

## Executar o app

```bash
streamlit run app.py
```

> **Importante:** execute o comando na raiz do repositório (mesma pasta de `app.py`).

## Planilha de referência

O upload é opcional. Quando fornecida, a planilha deve conter as abas:

- `Fluxo Base`
- `BMF`
- `Holidays`
- `Vencimentário`

Se alguma aba estiver ausente, o app mantém os defaults e mostra um aviso.

## Estrutura

- `app.py`: entrypoint do Streamlit.
- `fidc/`: pacote com leitura da planilha (`excel.py`) e motor de cálculo (`model.py`).

## Troubleshooting

- **ModuleNotFoundError:** instale as dependências com `pip install -r requirements.txt`.
- **Erro de import `fidc`:** certifique-se de executar o Streamlit a partir da raiz do repo.
- **Erro ao ler Excel:** verifique se as abas esperadas existem na planilha.
