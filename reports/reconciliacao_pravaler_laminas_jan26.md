# Reconciliação Pravaler - Lâminas Jan-26 vs Informe Mensal Estruturado

## Resumo executivo

- PDFs processados: 08417544000165.pdf, 26749095000134.pdf, 34408539000104.pdf, 55983705000168.pdf.
- Escopo: somente competência Jan-26 e somente os indicadores Over 30, Over 60, Over 90, Over 180 e Over 360.
- Resultado: todos os comparativos Over 30/60/90/180 entre lâmina e IME ficaram classificados como `DIVERGENTE`.
- Em todos os quatro FIDCs, o IME calcula NPL Over acumulado a partir dos buckets `VL_INAD_VENC_*` do XML, usando `dc_total_canonico` como denominador; a fonte efetiva foi `malha_vencimento`.
- O Over 360 não aparece nas lâminas; no IME, Jan-26 ficou em `0,00%` para todos os quatro FIDCs.
- Não identifiquei evidência de bug no cálculo acumulado do app nesta auditoria. A divergência parece vir de diferença de definição/denominador/base operacional entre a lâmina Pravaler e o XML do Informe Mensal Estruturado.

## Metodologia de extração

- Os PDFs foram lidos com `pdfplumber`, sem OCR. A extração textual trouxe a seção `Indicadores de Atraso` em todos os arquivos.
- Para cada PDF, identifiquei a seção `Indicadores de Atraso`, a posição da competência `jan/26` ou `jan-26` no gráfico e extraí os quatro percentuais alinhados ao último ponto da série.
- Os dados do IME foram obtidos pelo pipeline existente: `services.ime_loader.load_or_extract_informe` e `services.fundonet_dashboard.build_dashboard_data`, usando Jan-26.
- Para os CNPJs sem cache local, a extração Jan-26 foi executada e persistida em `.cache/fundonet-ime`.

## Metodologia do NPL Over no Informe Mensal

No app, o NPL Over é acumulado, não bucket isolado. A regra implementada em `services/fundonet_dashboard.py` é:
- Over 30 = soma dos buckets `31-60`, `61-90`, `91-120`, `121-150`, `151-180`, `181-360`, `361-720`, `721-1080` e `>1080`.
- Over 60 = soma dos buckets `61-90` em diante.
- Over 90 = soma dos buckets `91-120` em diante.
- Over 180 = soma dos buckets `181-360` em diante.
- Over 360 = soma dos buckets `361-720`, `721-1080` e `>1080`.
- Denominador = `dc_total_canonico`, escolhido por cascata: malha de vencimento -> estoque granular -> agregado item 3. Para estes quatro FIDCs em Jan-26, a fonte efetiva foi `malha_vencimento`.

## Bases IME usadas

| cnpj | fundo | competencia | dc_total_canonico | dc_vencidos_canonico | dc_total_fonte | dc_vencidos_fonte | cache_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 08417544000165 | CRÉDITO UNIVERSITÁRIO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESPONSABILIDADE LIMITADA; | 01/2026 | R$ 1.204.466.756,34 | R$ 17.382.258,54 | malha_vencimento | malha_vencimento | hit |
| 26749095000134 | PRAVALER CRÉDITO UNIVERSITÁRIO II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESP LIMITADAL | 01/2026 | R$ 367.232.509,95 | R$ 4.810.116,65 | malha_vencimento | malha_vencimento | hit |
| 34408539000104 | CREDITO UNIVERSITARIO III FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESPONSABILIDADE LIMITADA | 01/2026 | R$ 470.129.425,36 | R$ 9.534.893,55 | malha_vencimento | malha_vencimento | hit |
| 55983705000168 | CRÉDITO UNIVERSITÁRIO IV FUNDO DE INVESTIMENTO EM DIREITOS  CREDITÓRIOS - RESPONSABILIDADE LIMITADA | 01/2026 | R$ 168.983.313,90 | R$ 2.204.219,49 | malha_vencimento | malha_vencimento | hit |

## Comparativo FIDC a FIDC - atraso / NPL Over

### 08417544000165 - CRÉDITO UNIVERSITÁRIO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESPONSABILIDADE LIMITADA;

| Métrica | Valor na lâmina (%) | Valor no Informe Mensal Estruturado (%) | Diferença em p.p. | Diferença relativa (%) | Status | Observação técnica |
| --- | --- | --- | --- | --- | --- | --- |
| Over 30 | 5,24% | 1,02% | -4,22 p.p. | -80,47% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 60 | 3,89% | 0,79% | -3,10 p.p. | -79,71% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 90 | 3,19% | 0,62% | -2,57 p.p. | -80,65% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 180 | 1,58% | 0,27% | -1,31 p.p. | -83,13% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 360 |  | 0,00% |  |  | AUSENTE NA LÂMINA | Lâmina sem Over 360 |

### 26749095000134 - PRAVALER CRÉDITO UNIVERSITÁRIO II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESP LIMITADAL

| Métrica | Valor na lâmina (%) | Valor no Informe Mensal Estruturado (%) | Diferença em p.p. | Diferença relativa (%) | Status | Observação técnica |
| --- | --- | --- | --- | --- | --- | --- |
| Over 30 | 5,74% | 0,93% | -4,81 p.p. | -83,86% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 60 | 4,24% | 0,70% | -3,54 p.p. | -83,39% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 90 | 3,51% | 0,54% | -2,97 p.p. | -84,64% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 180 | 1,84% | 0,22% | -1,62 p.p. | -87,98% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 360 |  | 0,00% |  |  | AUSENTE NA LÂMINA | Lâmina sem Over 360 |

### 34408539000104 - CREDITO UNIVERSITARIO III FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESPONSABILIDADE LIMITADA

| Métrica | Valor na lâmina (%) | Valor no Informe Mensal Estruturado (%) | Diferença em p.p. | Diferença relativa (%) | Status | Observação técnica |
| --- | --- | --- | --- | --- | --- | --- |
| Over 30 | 5,42% | 1,51% | -3,91 p.p. | -72,21% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 60 | 4,24% | 1,18% | -3,06 p.p. | -72,21% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 90 | 3,71% | 0,92% | -2,79 p.p. | -75,30% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 180 | 2,15% | 0,40% | -1,75 p.p. | -81,58% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 360 |  | 0,00% |  |  | AUSENTE NA LÂMINA | Lâmina sem Over 360 |

### 55983705000168 - CRÉDITO UNIVERSITÁRIO IV FUNDO DE INVESTIMENTO EM DIREITOS  CREDITÓRIOS - RESPONSABILIDADE LIMITADA

| Métrica | Valor na lâmina (%) | Valor no Informe Mensal Estruturado (%) | Diferença em p.p. | Diferença relativa (%) | Status | Observação técnica |
| --- | --- | --- | --- | --- | --- | --- |
| Over 30 | 4,99% | 0,87% | -4,12 p.p. | -82,66% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 60 | 3,35% | 0,63% | -2,72 p.p. | -81,07% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 90 | 2,88% | 0,50% | -2,38 p.p. | -82,75% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 180 | 1,28% | 0,20% | -1,08 p.p. | -84,17% | DIVERGENTE | Diferença > 0,10 p.p.; ver CSV para fonte/fórmula |
| Over 360 |  | 0,00% |  |  | AUSENTE NA LÂMINA | Lâmina sem Over 360 |

## Divergências de atraso / NPL Over

As divergências são grandes e sistemáticas. Em todos os fundos, os percentuais da lâmina são maiores que os percentuais do IME. Como os buckets de aging do XML reconciliam com o total vencido e o app soma cumulativamente as faixas corretas, a evidência aponta para diferença conceitual entre as fontes, não para troca entre bucket isolado e acumulado no app.

### Over 360

A lâmina não traz Over 360. O IME calcula Over 360 como soma dos buckets `361-720`, `721-1080` e `>1080`; em Jan-26 todos esses buckets estão zerados nos quatro FIDCs, portanto Over 360 = `0,00%`.

## Conclusão técnica

- **Erro de cálculo no app:** não comprovado nesta auditoria. O cálculo do app é acumulado e usa os buckets esperados do XML.
- **Diferença de definição:** provável. A lâmina parece usar uma metodologia Pravaler de `Índices de Atraso` que não é diretamente igual ao NPL Over / carteira bruta do Informe Mensal Estruturado.
- **Diferença de denominador/base:** provável. O IME usa `dc_total_canonico` da malha de vencimento; a lâmina não explicita o denominador do gráfico de atraso.
- **Diferença de data-base:** menos provável para o comparativo principal, pois todos os PDFs e caches foram tratados como Jan-26.
- **Dado ausente/granularidade insuficiente:** para reproduzir exatamente a lâmina, falta a regra operacional/denominador dos `Índices de Atraso` do gestor. O XML traz buckets monetários de vencidos, mas não documenta a metodologia da lâmina.

## Arquivos e funções inspecionados

- `services/fundonet_client.py`: listagem/download dos documentos IME no Fundos.NET.
- `services/fundonet_parser.py`: parse do XML do Informe Mensal em `scalar_df` e `list_df`.
- `services/fundonet_service.py`: orquestração da extração, seleção de documentos e geração de CSVs.
- `services/ime_loader.py`: cache persistente `.cache/fundonet-ime`.
- `services/fundonet_export.py`: montagem do CSV wide.
- `services/fundonet_dashboard.py`: base canônica de DCs, buckets de aging e NPL Over acumulado.
- `tabs/tab_fidc_ime.py`: renderização dos gráficos da Visão Executiva e notas metodológicas.

## Scripts/testes executados

- Script local em Python para extrair percentuais dos PDFs com `pdfplumber`.
- `load_or_extract_informe` para Jan-26 dos quatro CNPJs; dois vieram de cache e dois foram extraídos e cacheados.
- `build_dashboard_data` para recomputar os indicadores do dashboard a partir dos CSVs wide/listas/docs.
- Nenhuma correção de app foi implementada nesta etapa.