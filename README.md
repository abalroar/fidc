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

## Custo financeiro Cloudwalk

A seção **Custo Cloudwalk** no Streamlit roda o motor de estimativa anual de
despesa financeira dos FIDCs:

- lê as cotas/emissões em `data/regulatory_profiles/cloudwalk_cotas_emissoes_pagamentos.csv`;
- aplica spreads CDI+ parseados dos documentos e overrides de
  `config/cloudwalk_financial_cost_inputs.json`;
- busca o CDI pela infraestrutura B3 TaxaSwap PRE DU252, com opção de CDI
  manual na tela;
- usa cache IME local em `.cache/fundonet-ime` ou os pacotes versionáveis em
  `data/ime_cache/fundonet-ime` para PL, recebíveis e caixa/LFT;
- exibe as três estimativas, o CDI+ implícito, detalhes por FIDC/cota,
  mensalização, premissas e download dos CSVs.

O mesmo cálculo também pode ser rodado por CLI:

```bash
python scripts/run_cloudwalk_financial_cost.py --year 2026
```

Para informar spreads manuais, edite `config/cloudwalk_financial_cost_inputs.json`
em `spreads_cdi_plus_aa` usando a chave `CNPJ|classe`, por exemplo:

```json
{
  "spreads_cdi_plus_aa": {
    "54218673000141|1ª série sênior": 0.012
  }
}
```

## O que o app faz

- Carrega premissas, feriados, curvas e timeline do `model_data.json`.
- Permite ajustar premissas via inputs numéricos e sliders.
- Exibe KPIs, gráficos e tabela da timeline.
- Oferece exportação de resultados em CSV/Excel.

## Dados

O arquivo `model_data.json` contém os dados base extraídos do modelo original
(premissas, feriados, curva CDI/DU e amostra de validação).

## Pipeline Fundos.NET (CVM)

Para automatizar download de **Informes Mensais Estruturados (FIDC)** via endpoint público do Fundos.NET:

```bash
python fundonet_fidc_pipeline.py \
  --cnpj-fundo 12345678000199 \
  --periodo-inicio Jan-25 \
  --periodo-fim Jan-26 \
  --output-dir saida_fundonet
```

Saídas geradas:
- `documentos_filtrados.csv`: metadados dos documentos encontrados.
- `informes_tidy.csv`: campos escalares dos XMLs no formato tidy.
- `estruturas_lista.csv`: estruturas repetitivas (cedentes, classes/séries etc.) em formato tidy.
- `informes_wide.xlsx`: workbook com abas `informes_campos`, `estruturas_lista`, `documentos` e `auditoria`.
- `audit_log.json`: trilha de auditoria da execução.

Observações:
- O script pagina automaticamente o endpoint `pesquisarGerenciadorDocumentosDados`.
- O download é feito por `downloadDocumento?id=...`.
- O filtro funcional usa o tipo FIDC + categoria/tipo oficiais do IME no Fundos.NET.
- O recorte temporal é por competência (`MM/AAAA`), não por data de entrega.
