# FIDC Amortização (Streamlit)

App Streamlit para simular cronograma de amortização e waterfall por classes de cotas.

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

## Uso da planilha

O upload da planilha é feito **pela interface**, na barra lateral. Não há caminho fixo em disco.

A planilha, quando enviada, deve conter as abas:

- `Fluxo Base`
- `BMF`
- `Holidays`
- `Vencimentário`

Se alguma aba não existir, o app exibe aviso e segue com defaults.

## Estrutura do projeto

- `app.py`: interface Streamlit (inputs, gráficos, exportações).
- `fidc/excel.py`: leitura da planilha e extração de premissas/outputs/feriados.
- `fidc/model.py`: motor de cálculo (fluxo do ativo, waterfall e KPIs).

## Troubleshooting

- **ModuleNotFoundError**: execute `pip install -r requirements.txt`.
- **Erro ao importar `fidc`**: rode o `streamlit run app.py` na raiz do repo.
- **Erro ao ler Excel**: confirme se as abas obrigatórias existem.
