# Próximos passos - diagnóstico profundo de FIDCs

Gerado em UTC: 2026-06-09T17:29:37.154566+00:00

## Onde estamos

- O estudo já tem universo CVM de ofertas 2024FY, 2025FY e 2026YTD.
- A classificação setorial inicial cobre 1.636 emissores, mas 650 ainda estão sem classificação confiável por metadados.
- Há 66 emissores com documentos locais baixados; isso é suficiente para provar metodologia, não para cobrir a indústria inteira.
- A base regulatória local já permite uma primeira matriz de práticas, mas precisa de expansão documental por ondas.

## Review manual por ondas

| Onda | Emissores | Volume registrado | Volume encerrado |
|---|---:|---:|---:|
| Onda 1 - top 50 por volume | 50 | R$ 52.473.860.072,49 | R$ 45.552.910.991,97 |
| Onda 2 - top 150 por volume | 100 | R$ 35.742.929.875,97 | R$ 29.757.664.291,13 |
| Onda 3 - acima de R$100mm | 151 | R$ 24.037.622.830,52 | R$ 17.609.571.576,72 |
| Onda 4 - cauda longa/amostragem | 430 | R$ 14.743.274.719,25 | R$ 10.795.556.223,55 |

## Top não classificados para atacar primeiro

| Rank | CNPJ | Emissor | Volume registrado | Motivo |
|---:|---|---|---:|---|
| 5 | 17250006000110 | RED FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS REAL LP DE RESPONSABILIDADE LIMITADA | R$ 1.800.000.000,00 | sem_classificacao_setorial |
| 12 | 19388423000159 | FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS IOSAN | R$ 1.390.000.000,00 | sem_classificacao_setorial |
| 21 | 22358482000199 | AFINITTY MF FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS FINANCEIROS - RESPONSABILIDADE LIMITADA | R$ 969.998.255,18 | sem_classificacao_setorial |
| 22 | 31570767000180 | FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS TRADEPAY VAREJO I | R$ 944.000.401,90 | sem_classificacao_setorial |
| 26 | 55070804000159 | ESTRATÉGIA VINCULADA II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS - RESPONSABILIDADE LIMITADA | R$ 850.000.000,00 | sem_classificacao_setorial |
| 27 | 41351629000163 | SIFRA LP FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS | R$ 830.000.000,02 | sem_classificacao_setorial |
| 28 | 62627051000103 | TOP 2025 E FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS RESPONSABILIDADE LIMITADA | R$ 826.750.000,00 | sem_classificacao_setorial |
| 29 | 62390922000100 | FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CLT NOW RESPONSABILIDADE LIMITADA | R$ 808.570.000,00 | sem_classificacao_setorial |
| 33 | 53779703000126 | XP CREDIT OPPORTUNITIES FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA | R$ 718.750.000,00 | sem_classificacao_setorial |
| 34 | 57535898000110 | ARTESANAL CRÉDITO ESTRUTURADO II FIDC DE RESPONSABILIDADE LIMITADA | R$ 712.500.000,00 | sem_classificacao_setorial |
| 37 | 50491214000186 | ADGM FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS | R$ 680.000.000,00 | sem_classificacao_setorial |
| 39 | 43721652000128 | NXC CAPITAL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS | R$ 649.999.998,63 | sem_classificacao_setorial |
| 41 | 62682486000142 | MCP FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS DE RESPONSABILIDADE LIMITADA | R$ 601.000.000,05 | sem_classificacao_setorial |
| 42 | 58215693000110 | SEGUE ÁRTICO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS FINANCEIRO RESPONSABILIDADE LIMITADA | R$ 600.000.000,00 | sem_classificacao_setorial |
| 49 | 66057868000136 | AMETISTA III FUNDO DE INVESTIMENTOS EM DIREITOS CREDITORIOS - RESPONSABILIDADE LIMITADA | R$ 548.000.000,00 | sem_classificacao_setorial |

## Saídas analíticas que precisamos produzir

1. **Mapa setorial defendável**: volume por setor e contagem equal-weight de emissores/fundos.
2. **Matriz tem/não tem**: por subtipo, presença de subordinação, mezanino, reserva, revolvência, recompra, concentração, rating, derivativos e gatilhos.
3. **Preço das emissões**: barras de volume por tranche/cota, com ponto de CDI+ x% a.a. quando a remuneração for CDI+.
4. **Mapa de participantes**: administradores, gestores, custodiante, cedentes, sacados/devedores e originadores mais relevantes por subtipo.
5. **Diagnóstico executivo**: padrões de mercado, exceções, lacunas de dados, casos emblemáticos e recomendação de monitoramento contínuo.

## Plano de 1 mês

| Semana | Objetivo | Entregáveis | Métrica de sucesso |
|---|---|---|---|
| Semana 1 | Fechar taxonomia e review manual dos maiores desconhecidos | Top 150 emissores não classificados; ajuste de regras; dashboard v0 de setores e volumes. | Reduzir volume não classificado em pelo menos 50% ou documentar blockers. |
| Semana 2 | Extrair regulamentos e matriz tem/não tem | Matriz regulatória dos top emissores por setor; subordinação, reservas, revolvência, concentração e gatilhos. | Cobrir top 20 por volume de cada macro setor e todos os top 50 overall. |
| Semana 3 | Preço das emissões e prestadores | Base de tranches com volume, tipo de cota, CDI+/%CDI/IPCA+, admins, gestores, custodiante, cedentes/sacados. | Gráficos de barra+ponto por tipo de FIDC e tipo de cota com flags de qualidade. |
| Semana 4 | Narrativa de diretoria e QA | Deck executivo, apêndice metodológico, base auditável, lacunas e recomendações de produto/dados. | Diagnóstico defendável: números agregados + equal-weight + exemplos documentais. |

## Gráficos-alvo para diretoria

- **Stacked bars** por ano e subtipo: volume encerrado vs válido/aberto.
- **Barra + ponto** por emissão/tranche: barra = volume; ponto = CDI+ spread; cor = tipo de cota; facet = subtipo FIDC.
- **Box/violin equal-weight** de subordinação por subtipo, sem ponderar por volume.
- **Heatmap tem/não tem** por subtipo: práticas regulatórias nas linhas e setores nas colunas.
- **Rankings horizontais** de administradores, gestores e custodiante por volume e por número de emissores.
- **Sankey/network** cedente -> FIDC -> sacado/devedor quando documentos nomeiam partes.

## Atenção metodológica

- O agregado por volume conta a história econômica, mas o padrão de mercado deve ser equal-weight por fundo/emissor.
- Não converter `%CDI`, IPCA+ ou taxa pré em CDI+ sem premissa explícita; marcar como regimes separados.
- Toda classificação precisa ter `confidence` e evidência documental ou metadado de origem.
- `Não classificado` é trabalho legítimo: significa que o documento precisa ser lido, não que o fundo seja irrelevante.