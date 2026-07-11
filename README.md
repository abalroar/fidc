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

## Estudo da industria de FIDCs (dados abertos CVM)

Pipeline que reconstroi a serie mensal da industria de FIDCs (jan/2013 em diante)
a partir do dataset publico *FIDC — Documentos: Informe Mensal* da CVM e do
cadastro `registro_fundo_classe`:

```bash
python scripts/build_fidc_industry_study.py --report
```

- Baixa/cacheia os zips brutos em `.cache/cvm-industry-study` (nao versionado).
- Grava agregados versionaveis em `data/industry_study/` (PL, veiculos, cotistas,
  captacao/resgate/amortizacao, segmentos de recebiveis, inadimplencia ajustada,
  subordinacao, rankings e concentracao de prestadores, universo por veiculo).
- `--report` renderiza o relatorio executivo `reports/fidc_industry_study.md`
  (com secao "Por que os numeros nao batem?" reconciliando CVM x ANBIMA x Uqbar).
- `--report-only` re-renderiza o relatorio a partir dos CSVs ja gerados.

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

## Mercado Secundário de FIDCs (ANBIMA Feed)

Nova página Streamlit (`pages/mercado_secundario.py`, aparece na barra lateral)
com volume operado, preço e taxa do mercado secundário de cotas de FIDC,
mês a mês (2023–2026), ranking de FIDCs por volume e ágio/deságio implícito.

Fonte: **ANBIMA Feed – Preços & Índices** (OAuth2), dois endpoints:

- `GET /v1/fidc/mercado-secundario` — PU indicativo, `percent_pu_par`, taxas
  (uma data por chamada, sem paginação);
- `GET /v1/reune/negociacoes` — negociações reais (paginado; cobre debêntures,
  CRI, CRA e CFF). FIDC entra como **CFF** — o isolamento é feito **cruzando o
  ISIN** contra o universo do endpoint de preços, nunca só por `tipo_ativo`.
  Dado anonimizado: não há comprador/vendedor, apenas o emissor da cota.

### Credenciais (portal ANBIMA Dev)

1. Entre em <https://developers.anbima.com.br> com seu login.
2. Crie um **aplicativo** (menu "Meus aplicativos" / "Criar aplicativo") — isso
   gera o par `client_id` / `client_secret`.
3. Associe o aplicativo ao produto **Feed – Preços e Índices** (a liberação de
   produção pode exigir aprovação/contratação junto à ANBIMA; o **sandbox** é
   liberado de imediato para testes).
4. Copie `.env.example` para `.env` e preencha `ANBIMA_CLIENT_ID` e
   `ANBIMA_CLIENT_SECRET`. O `.env` está no `.gitignore` — nunca commitar.
5. O token OAuth2 é obtido em runtime por `secondary/auth.py`
   (client credentials, Basic auth). **TODO:** confirmar URL do token e formato
   exatos na seção "Autenticação" do portal — a função é isolada e fácil de
   ajustar.
6. Para testar contra o sandbox, use `ANBIMA_ENV=sandbox`.

### Fluxo de dados

```bash
# 1) Modo de teste: um mês recente (valida auth, campos e cruzamento por ISIN)
python -m secondary.backfill --mes 2026-06

# 2) Sonda um dia antigo (o histórico de 2023 pode não existir; não grava nada)
python -m secondary.backfill --dia 2023-01-16

# 3) Backfill completo (só depois dos passos 1 e 2)
python -m secondary.backfill --inicio 2023-01-01 --fim 2026-12-31

# 4) Agregação -> data/curated/mensal_fidc.parquet
python -m secondary.aggregate
```

Layout dos dados (Hive-style, idempotente por mês; `--force` reprocessa):

```
data/raw/precos_fidc/ano=YYYY/mes=MM/parte.parquet
data/raw/negociacoes/ano=YYYY/mes=MM/parte.parquet
data/curated/mensal_fidc.parquet        # agregado mensal (dashboard)
data/curated/negociacoes_fidc.parquet   # nível negociação (boxplot de ágio/deságio)
```

Métrica-chave: `agio_desagio_impl_pct = (vl_pu_negociado / pu_indicativo − 1) × 100`,
comparando o preço praticado no REUNE com o PU indicativo ANBIMA do mesmo
ISIN+data; `percent_pu_par` (marcação oficial sobre o par) também é agregado.

> **AVISO — rate limit:** produção aceita ~15 req/s e o backfill completo
> (3+ anos × 2 endpoints × ~250 dias úteis/ano, REUNE paginado) gera milhares
> de chamadas. **Alinhe previamente com a ANBIMA** antes de rodar o backfill
> pesado e ajuste `ANBIMA_SLEEP_SECONDS` no `.env`. A profundidade histórica
> real (2023) é incerta: dias sem dado retornam vazio e são tratados como
> normais (liquidez de FIDC é baixa). O calendário usa `pandas.bdate_range`
> com ponto de extensão para feriados B3 (`secondary/backfill.py:FERIADOS_B3`).
