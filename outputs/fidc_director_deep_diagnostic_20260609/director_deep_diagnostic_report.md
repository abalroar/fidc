# Diagnostico profundo FIDC - 2024FY, 2025FY, 2026YTD

Gerado em: 2026-06-09T18:40:57Z.

## Leitura executiva

- Universo CVM de ofertas analisado: 3,865 linhas, 1,636 emissores.
- Documentos locais/FNET cobertos: 764 CNPJs com PDFs, 4,557 regulamentos, 2,734 documentos de emissao.
- Regulamentos efetivamente lidos para matriz tem/nao tem: 764.
- Base de tranches/documentos de emissao no periodo: 526; linhas com CDI+ extraido: 107.

## Como interpretar

- Os agregados CVM medem volume de emissao/registro; a matriz regulatoria mede fundos equal-weight.
- As praticas comuns devem ser lidas por subtipo e por frequencia de fundos, nao apenas por volume.
- Campos de cedentes/sacados sao candidatos extraidos por contexto textual e exigem QA manual antes de uso em memorando juridico.

## Principais proximos usos

- Revisar manualmente a Onda 1 onde `feature_hits_share` for baixo ou documento faltar.
- Validar spreads CDI+ em documentos repetidos para remover duplicatas de anuncio/ata/suplemento.
- Converter os achados em slides: tamanho de mercado, pricing por cota, padroes de subordinação, ranking de prestadores e lacunas competitivas.

## Download incremental FNET

- CNPJs processados para download: 678.
- OK: 677; parcial: 1; erro: 0.

## Top praticas por setor

| setor_n1 | setor_n2 | fundos_com_regulamento | subordination_minimum_share | cash_or_liquidity_reserve_share | revolving_period_share |
| --- | --- | --- | --- | --- | --- |
| Crédito PF | Crédito pessoal/consumo | 141 | 68,79% | 52,48% | 34,75% |
| Não classificado | Revisar manualmente | 109 | 3,67% | 0,92% | 0,92% |
| Crédito PJ | Recebíveis comerciais/multissetorial | 90 | 47,78% | 46,67% | 38,89% |
| Agro | Agro | 81 | 64,20% | 58,02% | 43,21% |
| Crédito PJ | Risco sacado/fornecedores | 56 | 78,57% | 83,93% | 17,86% |
| Crédito PF | Consignado/INSS | 37 | 51,35% | 51,35% | 43,24% |
| Crédito PF | Auto/Veículos | 36 | 52,78% | 30,56% | 19,44% |
| Crédito PJ | CCB/Notas comerciais/Capital de giro | 36 | 50,00% | 33,33% | 33,33% |
| Imobiliário | Imobiliário | 34 | 29,41% | 23,53% | 58,82% |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | 30 | 86,67% | 63,33% | 33,33% |
| Sem oferta CVM mapeada | Sem oferta CVM mapeada | 28 | 60,71% | 57,14% | 75,00% |
| Crédito PF | FGTS | 17 | 70,59% | 64,71% | 47,06% |

## Subordinacao por setor

| setor_n1 | setor_n2 | fundos_com_subordinacao | subordinacao_mediana_pct_equal_weight | subordinacao_p25_pct | subordinacao_p75_pct | valores_comuns |
| --- | --- | --- | --- | --- | --- | --- |
| Sem oferta CVM mapeada | Sem oferta CVM mapeada | 6 | 8,50% | 7,00% | 21,25% | 7% (2); 5% (1); 85% (1); 10% (1); 25% (1) |
| Crédito PF | FGTS | 3 | 5,00% | 4,00% | 45,00% | 5% (1); 85% (1); 3% (1) |
| Crédito PJ | Risco sacado/fornecedores | 3 | 22,00% | 14,75% | 31,00% | 22% (1); 7.5% (1); 40% (1) |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | 3 | 16,00% | 15,75% | 33,00% | 15.5% (1); 16% (1); 50% (1) |
| Crédito PJ | CCB/Notas comerciais/Capital de giro | 2 | 12,50% | 11,25% | 13,75% | 10% (1); 15% (1) |
| Crédito PF | Consignado/INSS | 1 | 14,50% | 14,50% | 14,50% | 14.5% (1) |
| Crédito PF | Crédito estudantil | 1 | 50,00% | 50,00% | 50,00% | 50% (1) |
| Judicial/Precatórios/NPL | Não padronizado/NPL | 1 | 10,00% | 10,00% | 10,00% | 10% (1) |
| Não classificado | Revisar manualmente | 1 | 30,00% | 30,00% | 30,00% | 30% (1) |

## Pricing por setor/cota

| setor_n1 | setor_n2 | tipo_cota | linhas_tranche | volume_brl | spread_cdi_mediano_aa | share_linhas_com_spread_cdi |
| --- | --- | --- | --- | --- | --- | --- |
| Nao classificado | Sem classificacao | Sênior | 17 | R$ 30.100.025.000 | 5,30% | 11,76% |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | Sênior | 51 | R$ 21.703.600.654 |  | 0,00% |
| Crédito PJ | CCB/Notas comerciais/Capital de giro | Sênior | 10 | R$ 8.810.002.000 |  | 0,00% |
| Meios de Pagamento e Cartões | Arranjos de pagamento/adquirência | Nao identificado | 25 | R$ 8.052.894.206 | 2,98% | 8,00% |
| Nao classificado | Sem classificacao | Nao identificado | 69 | R$ 8.005.083.486 | 1,49% | 5,80% |
| Crédito PF | Consignado/INSS | Sênior | 7 | R$ 4.838.248.988 | 2,40% | 14,29% |
| Não classificado | Revisar manualmente | Nao identificado | 23 | R$ 3.702.983.872 |  | 0,00% |
| Crédito PJ | Risco sacado/fornecedores | Nao identificado | 50 | R$ 3.278.487.022 | 5,50% | 60,00% |
| Agro | Agro | Sênior | 13 | R$ 3.107.000.000 | 2,70% | 53,85% |
| Nao classificado | Sem classificacao | Subordinada | 10 | R$ 2.807.501.000 | 1,28% | 10,00% |
| Crédito PF | Crédito estudantil | Nao identificado | 36 | R$ 2.751.953.016 | 0,00% | 5,56% |
| Crédito PF | FGTS | Nao identificado | 19 | R$ 2.646.297.055 |  | 0,00% |

## Participantes

| setor_n1 | setor_n2 | role | participant | cnpjs_unicos | volume_brl |
| --- | --- | --- | --- | --- | --- |
| Agro | Agro | administrador_cvm | BANCO DAYCOVAL S.A. | 15 | R$ 7.925.971.621 |
| Agro | Agro | administrador_cvm | VORTX DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | 20 | R$ 5.355.596.835 |
| Agro | Agro | administrador_oferta | BANCO DAYCOVAL S.A. | 12 | R$ 8.997.015.232 |
| Agro | Agro | administrador_oferta | VÓRTX DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS LTDA | 10 | R$ 2.626.950.000 |
| Agro | Agro | coordenador_lider | BANCO SANTANDER (BRASIL) S.A. | 1 | R$ 9.400.000.000 |
| Agro | Agro | coordenador_lider | ITAU BBA ASSESSORIA FINANCEIRA S.A | 12 | R$ 4.296.614.000 |
| Agro | Agro | custodiante_cvm | BANCO DAYCOVAL S.A. | 8 | R$ 3.685.650.718 |
| Agro | Agro | custodiante_cvm | HEMERA DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA | 16 | R$ 2.796.183.953 |
| Agro | Agro | custodiante_oferta | BANCO DAYCOVAL S.A. | 12 | R$ 8.997.015.232 |
| Agro | Agro | custodiante_oferta | VÓRTX DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS LTDA | 10 | R$ 2.626.950.000 |
| Agro | Agro | gestor_cvm | ECO GESTÃO DE ATIVOS LTDA | 6 | R$ 7.528.351.797 |
| Agro | Agro | gestor_cvm | FARMTECH GESTÃO DE RECURSOS LTDA. | 6 | R$ 2.386.176.278 |
| Agro | Agro | gestor_oferta | ECO GESTÃO DE ATIVOS LTDA. | 3 | R$ 9.969.466.709 |
| Agro | Agro | gestor_oferta | ITAÚ UNIBANCO S.A. | 2 | R$ 1.810.974.000 |
| Crédito PF | Auto/Veículos | administrador_cvm | BEM - DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | 2 | R$ 4.344.749.195 |
| Crédito PF | Auto/Veículos | administrador_cvm | BANCO DAYCOVAL S.A. | 4 | R$ 3.765.058.182 |
| Crédito PF | Auto/Veículos | administrador_oferta | BANCO DAYCOVAL S.A. | 3 | R$ 4.709.584.000 |
| Crédito PF | Auto/Veículos | administrador_oferta | BRL TRUST DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS S.A. | 1 | R$ 3.000.000.000 |

## Arquivos principais

- `fidc_regulatory_feature_matrix.csv`: matriz tem/nao tem por CNPJ e regulamento.
- `fidc_feature_prevalence_by_sector.csv`: frequencia equal-weight das praticas.
- `fidc_pricing_tranches.csv`: tranches/eventos com volume, tipo de cota e spread extraido.
- `fidc_pricing_summary_by_sector_quota.csv`: resumo para grafico barra+ponto.
- `fidc_market_participants_by_sector.csv`: rankings de prestadores por subtipo.
- `fidc_cedentes_sacados_candidates.csv`: candidatos extraidos de contexto textual.
- `fidc_director_dashboard.html`: dashboard visual local.