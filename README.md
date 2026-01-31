# Upload de Modelo Financeiro (Streamlit)

Aplicação Streamlit para receber um arquivo **.xlsm** e gerar um JSON com abas,
intervalos nomeados e fórmulas, facilitando a migração do modelo para a plataforma.

## Requisitos

- Python 3.10+
- Dependências listadas em `requirements.txt`

```bash
pip install -r requirements.txt
```

## Executar

```bash
streamlit run app.py
```

> Execute o comando na raiz do repositório (mesma pasta de `app.py`).

## O que o app faz

- Permite enviar um arquivo `.xlsm`.
- Exibe nome, tamanho e hash do arquivo enviado.
- Extrai abas, intervalos nomeados e fórmulas.
- Oferece o download do JSON com as fórmulas.

## Próximos passos esperados

- Mapear abas, cálculos e saídas do modelo financeiro.
- Transformar a lógica em componentes da plataforma.
