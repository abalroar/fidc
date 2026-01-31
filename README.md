# Upload de Modelo Financeiro (Streamlit)

Aplicação Streamlit simplificada para receber um arquivo **.xlsm** e preparar a migração
para a plataforma.

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
- Oferece o download do arquivo original.

## Próximos passos esperados

- Mapear abas, cálculos e saídas do modelo financeiro.
- Transformar a lógica em componentes da plataforma.
