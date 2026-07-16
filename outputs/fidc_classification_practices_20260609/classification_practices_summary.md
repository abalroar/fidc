# Classificação setorial e práticas de regulamento de FIDCs

Gerado em UTC: 2026-06-09T17:03:27.909400+00:00

## Escopo

- Ofertas classificadas: 3,865.
- Emissores únicos classificados: 1,636.
- Fundos com critérios regulatórios locais: 56.

## Método

- Classificação setorial: regras auditáveis sobre `valor_mobiliario`, `ativos_alvo`, `descricao_lastro` e `nome_emissor`.
- Confiança alta: regra acionada por campo CVM de ativo/lastro. Confiança média: regra acionada por nome ou texto regulatório local. Confiança baixa: sem regra.
- Práticas regulatórias: amostra documental local em `data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv`; resultados são equal-weight por fundo.
- Subordinação: quando o extrator capturou uma razão maior que 100% mas a observação trazia o percentual de PL subordinado, o script normalizou para o percentual de PL.

## Setores por emissores

| Setor | Subsetor | Emissores | Volume registrado | Volume encerrado | Conf. alta |
|---|---|---:|---:|---:|---:|
| Não classificado | Revisar manualmente | 650 | R$ 70.939.284.988,14 | R$ 53.237.389.567,84 | 0% |
| Agro | Agro | 152 | R$ 33.793.406.745,21 | R$ 30.911.935.991,05 | 80% |
| Judicial/Precatórios/NPL | Não padronizado/NPL | 120 | R$ 10.588.371.932,79 | R$ 7.378.573.031,55 | 21% |
| Crédito PJ | Recebíveis comerciais/multissetorial | 116 | R$ 15.167.786.123,34 | R$ 13.475.026.039,33 | 38% |
| Crédito PF | Consignado/INSS | 114 | R$ 41.858.776.720,91 | R$ 32.473.086.759,92 | 48% |
| FIC/Alocador | FIC de FIDC | 96 | R$ 13.887.426.531,20 | R$ 11.522.746.808,00 | 5% |
| Judicial/Precatórios/NPL | Precatórios/direitos judiciais | 95 | R$ 8.377.773.487,81 | R$ 6.188.071.879,12 | 72% |
| Crédito PJ | CCB/Notas comerciais/Capital de giro | 62 | R$ 19.038.688.463,67 | R$ 16.487.919.056,70 | 100% |
| Crédito PJ | Risco sacado/fornecedores | 59 | R$ 12.369.559.463,58 | R$ 10.264.459.462,96 | 90% |
| Crédito PF | FGTS | 36 | R$ 13.396.095.694,04 | R$ 13.132.595.694,04 | 67% |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | 36 | R$ 36.394.405.653,59 | R$ 35.534.405.653,59 | 92% |
| Imobiliário | Imobiliário | 25 | R$ 2.616.317.923,08 | R$ 2.085.567.902,68 | 76% |
| Crédito PF | Auto/Veículos | 21 | R$ 16.173.434.999,96 | R$ 14.142.434.999,96 | 48% |
| Infra/Energia | Energia/infra | 17 | R$ 6.638.001.031,51 | R$ 6.307.571.031,43 | 41% |
| Meios de Pagamento e Cartões | Bancos Emissores | 16 | R$ 2.611.875.773,34 | R$ 2.499.375.773,34 | 88% |
| Crédito PF | Crédito pessoal/consumo | 15 | R$ 2.398.504.794,49 | R$ 2.027.504.794,40 | 87% |
| Crédito PF | Crédito estudantil | 6 | R$ 2.273.200.000,00 | R$ 2.133.200.000,00 | 100% |

## Subordinação por setor

| Setor | Subsetor | Fundos | Mediana | P25 | P75 | Valores comuns |
|---|---|---:|---:|---:|---:|---|
| Não classificado | Revisar manualmente | 4 | 16% | 7% | 26.25% | 7% (2); 25% (1); 30% (1) |
| Crédito PF | FGTS | 3 | 5% | 4% | 7.5% | 10% (1); 3% (1); 5% (1) |
| Crédito PJ | Risco sacado/fornecedores | 3 | 40% | 23.75% | 42.5% | 40% (1); 45% (1); 7.5% (1) |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | 3 | 16% | 15.75% | 33% | 15.5% (1); 16% (1); 50% (1) |
| Crédito PJ | CCB/Notas comerciais/Capital de giro | 2 | 12.5% | 11.25% | 13.75% | 10% (1); 15% (1) |
| Agro | Agro | 1 | 5% | 5% | 5% | 5% (1) |
| Crédito PF | Consignado/INSS | 1 | 14.5% | 14.5% | 14.5% | 14.5% (1) |
| Crédito PF | Crédito estudantil | 1 | 50% | 50% | 50% | 50% (1) |
| Judicial/Precatórios/NPL | Não padronizado/NPL | 1 | 10% | 10% | 10% | 10% (1) |

## Arquivos

- `fidc_offer_sector_classification.csv`: classificação linha a linha das ofertas.
- `fidc_issuer_sector_classification.csv`: classificação consolidada por emissor.
- `fidc_manual_review_queue_unclassified_issuers.csv`: emissores ainda sem classificação, ordenados por volume.
- `fidc_sector_summary_equal_weight.csv`: resumo por setor via contagem de emissores.
- `fidc_regulatory_practices_long.csv`: critérios regulatórios extraídos, com setor.
- `fidc_subordination_by_fund.csv`: subordinação principal por fundo curado.
- `fidc_subordination_summary_by_sector.csv`: distribuição equal-weight de subordinação por setor.
- `fidc_practice_prevalence_by_sector.csv`: prevalência de práticas extraídas por setor.