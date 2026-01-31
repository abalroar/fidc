# Modelo Financeiro FIDC (Streamlit)

Aplicação Streamlit para rodar o modelo financeiro do FIDC com dados base em
`model_data.json` (sem depender de upload do `.xlsm`).

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

- Carrega premissas, feriados, curvas e timeline do `model_data.json`.
- Permite ajustar premissas via inputs numéricos e sliders.
- Exibe KPIs, gráficos e tabela da timeline.
- Oferece exportação de resultados em CSV/Excel.

## Dados

O arquivo `model_data.json` contém os dados base extraídos do modelo original
(premissas, feriados, curva CDI/DU e amostra de validação).
