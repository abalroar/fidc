# Carteira 1 — 101 fundos, base para preencher o índice de subordinação mínima

Gerado por `scripts/build_carteira1_submin_workbook.py`.

## Arquivos

| Arquivo | Conteúdo |
| --- | --- |
| `carteira1_101_fundos_sub_minima.xlsx` | Workbook com 8 abas (mestre + fontes de apoio) |
| `carteira1_mestre.csv` | Mesma aba mestre em CSV, 101 linhas × 207 colunas |

## Abas

| Aba | Linhas | O que é |
| --- | --- | --- |
| `01_mestre` | 101 | Uma linha por fundo, tudo consolidado. É aqui que se preenche. |
| `02_curadoria_sub_minima` | 101 | Curadoria documental já existente da sub mínima júnior, com texto integral da cláusula |
| `03_criterios_regulamento` | 462 | Critérios estruturados de regulamento (`criteria_structured`) dos fundos da carteira |
| `04_criterios_extraidos_json` | 3.505 | Extração heurística por regulamento em `data/regulatory_knowledge/<cnpj>.json`, com trecho-fonte e fórmula |
| `05_ime_ultimos_12m` | 1.113 | Série dos últimos 12 meses do Informe Mensal Estruturado por fundo |
| `06_taxonomias_long` | 2.117 | Catálogo de dimensões/taxonomias em formato longo, com documento e página de origem |
| `07_documentos` | 1.278 | Inventário documental com `id` e URL do Fundos.NET |
| `08_dicionario` | — | De onde vem cada coluna da aba mestre |

## Como preencher

O bloco `USR_*` (colunas G a Q, destacadas em amarelo) está vazio de propósito:

| Coluna | Preencher com |
| --- | --- |
| `USR_sub_min_pct` | O índice em pontos percentuais (ex.: `4.5`, não `0.045`) |
| `USR_tipo_indice` | Júnior / mezanino / subordinação total / sênior |
| `USR_numerador` | Numerador da razão do regulamento |
| `USR_denominador` | Denominador (PL da classe, PL do fundo, cotas em circulação…) |
| `USR_documento_id` | ID do documento no Fundos.NET |
| `USR_pagina` | Página da cláusula |
| `USR_citacao_regulamento` | Trecho literal |
| `USR_status` | Status da revisão manual |
| `USR_observacao` | Observação livre |

Duas colunas são fórmulas e se resolvem sozinhas ao preencher `USR_sub_min_pct`:

- `USR_folga_pp` = subordinação realizada do IME − mínimo digitado, em p.p.
- `USR_divergencia_vs_curadoria_pp` = mínimo digitado − `cur_sub_min_pct`

## Ponto de partida já disponível

| Situação | Fundos |
| --- | --- |
| Mínimo júnior localizado no regulamento | 47 |
| Mínimo júnior calculado de cláusulas contratuais | 3 |
| Mínimo júnior não isolado (regulamento lido, sem percentual comparável) | 50 |
| Fora do perímetro FIDC (Canaã FIAGRO, regulamento não localizado) | 1 |

Ou seja: 50 dos 101 já chegam com percentual (`cur_sub_min_pct` preenchido) e os
outros 51 chegam com o regulamento identificado, página candidata e o texto que
foi avaliado — o trabalho manual é confirmar os 50 e resolver os 51.

## Unidades — atenção

- `cur_sub_min_pct`, `crit_sub_pct_min/max`, `snap_sub_min_pct_*` estão em **pontos percentuais** (`4.5` = 4,5%).
- `ime_subordinacao_pct` vem do IME como **razão** (`0.2474` = 24,74%). A coluna
  `ime_subordinacao_pp` traz o mesmo valor já em p.p.

## Cobertura das fontes

| Fonte | Fundos cobertos (de 101) |
| --- | --- |
| Curadoria documental da sub mínima | 101 |
| Informe Mensal Estruturado | 100 (falta o Canaã FIAGRO, fora da base FIDC) |
| Snapshot do estudo de indústria | 79 |
| Catálogo de taxonomias/dimensões | 87 |
| Critérios estruturados de subordinação | 37 |
| Extração por regulamento em `regulatory_knowledge` | 27 (19 com limite de subordinação) |
| Decisão de taxonomia curada | 23 |

Colunas totalmente vazias nas fontes foram removidas da aba mestre, exceto o bloco `USR_*`.

## Reproduzir

```bash
python3 scripts/build_carteira1_submin_workbook.py
```
