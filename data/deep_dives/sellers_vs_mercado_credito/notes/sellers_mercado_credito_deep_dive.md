# Deep dive documental — Sellers e Mercado Crédito

Gerado em `2026-05-13 09:44` a partir exclusivamente de artefatos locais do repositório.

## Resumo executivo

A varredura cobriu sete veículos: três Sellers e quatro Mercado Crédito. Foram combinados três níveis de evidência: (i) inventário CVM/regulatory_knowledge, (ii) PDFs efetivamente existentes em `data/raw/<cnpj>/`, e (iii) caches locais de IME quando disponíveis. Documentos inventariados sem PDF local foram mantidos como lacuna documental, sem inferência de conteúdo.

| grupo | cnpj | fundo | documentos_inventariados | pdfs_locais_analisaveis | documentos_sem_pdf_local | paginas_pdf_locais | quebra_por_categoria |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | 33.254.370/0001-04 | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 75 | 30 | 45 | 1282 | assembleia: 16; evento: 1; outro: 45; regulamento: 13 |
| Mercado Crédito | 37.511.828/0001-14 | MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 73 | 39 | 34 | 1951 | assembleia: 26; evento: 1; outro: 34; regulamento: 12 |
| Mercado Crédito | 41.970.012/0001-26 | MERCADO CRÉDITO II BRASIL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA | 78 | 40 | 38 | 2964 | assembleia: 15; emissao: 2; evento: 1; outro: 38; regulamento: 22 |
| Mercado Crédito | 28.472.333/0001-32 | Mercado Crédito Merchant Fundo de Investimento em Direitos Creditórios | 52 | 14 | 38 | 539 | assembleia: 10; evento: 1; outro: 38; regulamento: 3 |
| Sellers | 63.572.282/0001-11 | SELLER 3 FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO DE RESP LIMITADA | 10 | 10 | 0 | 488 | assembleia: 3; emissao: 3; regulamento: 4 |
| Sellers | 50.473.039/0001-02 | SELLER FIDC SEGMENTO MEIOS DE PAGAMENTO DE RESPONSABILIDADE LIMITADA | 44 | 21 | 23 | 1047 | assembleia: 6; emissao: 7; outro: 23; regulamento: 8 |
| Sellers | 55.471.753/0001-77 | SELLER II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS SEGMENTO MEIOS DE PAGAMENTO RESP LTDA | 28 | 13 | 15 | 491 | assembleia: 3; emissao: 2; evento: 3; outro: 15; regulamento: 5 |

### Principais conclusões suportadas pela base local

- Sellers possui curadoria mais completa já estruturada para emissões, subordinação mínima, índices de cobertura e cronogramas de amortização, com suplementos e atas locais cobrindo a formação das séries.
- Mercado Crédito tem maior volume de documentos locais e muitos eventos de assembleia/regulamento, mas os documentos de rating, informes trimestrais e demonstrações financeiras aparecem majoritariamente apenas no inventário, sem PDF local baixado nesta base.
- Em ambos os grupos, vários gatilhos são monitoráveis apenas parcialmente pelo IME: o IME traz PL, direitos creditórios, caixa, PDD, atraso por bucket e cotas, mas não traz de forma padronizada fatores de ponderação, valor presente contratual, reservas regulatórias completas, cronogramas futuros e condições de elegibilidade no nível de contrato.
- Nenhuma métrica contratual deve ser automatizada como breach duro sem validação do texto-fonte mais recente e parametrização manual quando a fonte exige fator, reserva, covenant ou definição não observável no IME.

## Metodologia e rastreabilidade

Para cada PDF local, o script extraiu texto por página com `pypdf` e registrou evidências por tema. Cada linha de evidência contém CNPJ, fundo, documento, página, termos encontrados e trecho. Quando a extração de texto falhou, a linha foi classificada como lacuna/OCR necessário.

Arquivos gerados:
- `reports/sellers_mercado_credito_document_inventory.csv`
- `reports/sellers_mercado_credito_document_coverage.csv`
- `reports/sellers_mercado_credito_pdf_evidence.csv`
- `reports/sellers_mercado_credito_document_by_document_digest.csv`
- `reports/sellers_mercado_credito_emissions.csv`
- `reports/sellers_mercado_credito_emissions_raw.csv`
- `reports/sellers_mercado_credito_triggers_criteria.csv`
- `reports/sellers_mercado_credito_threshold_versions.csv`
- `reports/sellers_mercado_credito_eligibility_criteria.csv`
- `reports/sellers_mercado_credito_timeline.csv`
- `reports/sellers_mercado_credito_regulation_changes.csv`
- `reports/sellers_mercado_credito_assembly_events.csv`
- `reports/sellers_mercado_credito_cotistas_related_parties.csv`
- `reports/sellers_mercado_credito_amortizations.csv`
- `reports/sellers_mercado_credito_pricing_economics.csv`
- `reports/sellers_mercado_credito_cessions_credit_rights.csv`
- `reports/sellers_mercado_credito_governance_operational.csv`
- `reports/sellers_mercado_credito_performance_metrics.csv`

## Digest documento a documento

Cada documento inventariado recebeu status próprio. Para PDFs locais, a tabela aponta categorias de evidência e páginas onde houve hits; para documentos sem PDF local, o status fica como lacuna, sem interpretação.

| grupo | nome_curto | cnpj | data_referencia | categoria | tipo_documento | documento_id | status_auditoria | page_count | categorias_com_evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 23/10/2020 | outro | Relatório de Agência de Rating | 157108 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/11/2020 11:00 | assembleia | AGE | 135822 | PDF analisado | 5.0 | alteracoes_assembleias: 5; amortizacao: 2; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 2; governanca_operacional: 5; performance_risco: 2 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | regulamento | Regulamento | 135821 | PDF analisado | 113.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2020 | outro | Informe Trimestral | 146340 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | outro | Relatório de Agência de Rating | 146344 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | outro | Demonstrações Financeiras | 166929 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 15/02/2021 | outro | Relatório de Agência de Rating | 157110 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | outro | Informe Trimestral | 173096 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | outro | Informe Trimestral | 173101 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2021 | outro | Relatório de Agência de Rating | 173098 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | outro | Informe Trimestral | 205041 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | outro | Informe Trimestral | 208366 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2021 | outro | Relatório de Agência de Rating | 205027 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2021 | outro | Informe Trimestral | 235040 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | outro | Relatório de Agência de Rating | 235044 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | outro | Relatório de Agência de Rating | 235878 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | outro | Informe Trimestral | 270880 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | outro | Informe Trimestral | 321401 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2021 | outro | Demonstrações Financeiras | 510926 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | outro | Informe Trimestral | 304904 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | outro | Informe Trimestral | 373768 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | outro | Informe Trimestral | 340650 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | outro | Informe Trimestral | 373901 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | outro | Informe Trimestral | 376748 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | outro | Informe Trimestral | 410062 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2022 | outro | Informe Trimestral | 415493 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/12/2022 | outro | Relatório de Agência de Rating | 410762 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2022 | outro | Demonstrações Financeiras | 565264 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2023 | outro | Informe Trimestral | 454622 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2023 | outro | Relatório de Agência de Rating | 457230 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 13/04/2023 18:00 | assembleia | AGE | 444985 | PDF analisado | 103.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 14/04/2023 23:59 | assembleia | AGE | 436942 | PDF analisado | 10.0 | alteracoes_assembleias: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 4; emissoes: 1; governanca_operacional: 5; preco_economia: 3 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | regulamento | Instrumento Particular de Alteração do Regulamento | 448299 | PDF analisado | 97.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | evento | Fato Relevante | 448302 | PDF analisado | 1.0 | cotistas_partes_relacionadas: 1; direitos_creditorios_cessoes: 1; governanca_operacional: 1 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2023 | outro | Informe Trimestral | 507575 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2023 | outro | Relatório de Agência de Rating | 499533 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2023 | outro | Informe Trimestral | 552045 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 23/09/2023 23:59 | assembleia | AGO | 517767 | PDF analisado | 4.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 4; direitos_creditorios_cessoes: 2; governanca_operacional: 4 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 24/09/2023 23:59 | assembleia | AGO | 528403 | PDF analisado | 1.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 1; direitos_creditorios_cessoes: 1; governanca_operacional: 1 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2023 | outro | Informe Trimestral | 607588 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 18/12/2023 23:59 | assembleia | AGO | 566552 | PDF analisado | 4.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 4; governanca_operacional: 4 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 18/12/2023 23:59 | assembleia | AGO | 572987 | PDF analisado | 1.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 1; governanca_operacional: 1 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | outro | Relatório de Agência de Rating | 607607 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | outro | Demonstrações Financeiras | 643226 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2024 | outro | Informe Trimestral | 653128 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/03/2024 | outro | Relatório de Agência de Rating | 664505 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2024 | outro | Informe Trimestral | 714174 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 15/06/2024 23:59 | assembleia | AGE | 674485 | PDF analisado | 4.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 4; direitos_creditorios_cessoes: 2; governanca_operacional: 4 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 17/06/2024 10:00 | assembleia | AGO | 681860 | PDF analisado | 1.0 | alteracoes_assembleias: 1; cotistas_partes_relacionadas: 1; direitos_creditorios_cessoes: 1; governanca_operacional: 1 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/06/2024 | outro | Relatório de Agência de Rating | 709466 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 10:00 | assembleia | AGE | 732139 | PDF analisado | 100.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | regulamento | Regulamento | 732140 | PDF analisado | 95.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 12/2020 | outro | Informe Trimestral | 149747 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 31/12/2020 | outro | Demonstrações Financeiras | 259351 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/2021 | outro | Informe Trimestral | 180899 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 06/2021 | outro | Informe Trimestral | 206633 | Inventariado sem PDF local |  |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 09:00 | assembleia | AGE | 196309 | PDF analisado | 12.0 | alteracoes_assembleias: 5; amortizacao: 1; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; governanca_operacional: 5; preco_economia: 1 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 | regulamento | Regulamento | 206963 | PDF analisado | 71.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/07/2021 | regulamento | Instrumento Particular de Alteração do Regulamento | 201177 | PDF analisado | 72.0 | alteracoes_assembleias: 5; amortizacao: 5; cotistas_partes_relacionadas: 5; direitos_creditorios_cessoes: 5; emissoes: 5; governanca_operacional: 5; performance_risco: 5; preco_ec… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | outro | Outros Documentos | 207363 | Inventariado sem PDF local |  |  |

_Exibindo 60 de 360 linhas. Ver CSV para a tabela completa._

## 1. Mapeamento das emissões

A tabela consolidada abaixo vem das curadorias locais já existentes e preserva a coluna de fonte. Campos vazios significam ausência na extração documental local, não inexistência econômica.

| Fundo | CNPJ | Cota/Classe | Classe/Série | Tipo | Data deliberação | Data emissão / 1ª integralização | Quantidade | Volume | Remuneração | Amortização principal | Fonte |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SELLER | 50.473.039/0001-02 | Sênior 1ª série |  | Sênior | 22/05/2023 | 31/05/2023 | 1.000.000 | R$ 1.000.000.000 | DI + 1,60% a.a. (252 d.u.) | 15/12/2025: 25,00%; 15/01/2026: 33,33%; 15/02/2026: 50,00%; 15/03/2026: 100,00% | 468755 p.3; 471622 p.2; 467929 pp.115-117 |
| SELLER | 50.473.039/0001-02 | Sênior 2ª série |  | Sênior | 22/05/2023 | 31/05/2023 | 500.000 | R$ 500.000.000 | DI + 1,80% a.a. (252 d.u.) | 15/04/2026: 50,00%; 15/05/2026: 100,00% | 468755 p.3; 471622 p.2; 467929 pp.118-120 |
| SELLER | 50.473.039/0001-02 | Sênior 3ª série |  | Sênior | 23/11/2023 | Não identificada nos PDFs baixados | 200.000 | R$ 200.000.000 | Não identificada nos PDFs baixados | Não identificado | 558803 pp.4-5; 559856 pp.1-2 |
| SELLER | 50.473.039/0001-02 | Sênior 4ª série |  | Sênior | 23/11/2023 | Não identificada nos PDFs baixados | 100.000 | R$ 100.000.000 | Não identificada nos PDFs baixados | Não identificado | 558803 pp.4-5; 559856 pp.1-2 |
| SELLER | 50.473.039/0001-02 | Subordinada Júnior (emissão 2023) |  | Subordinada Júnior | 23/11/2023 | Não identificada nos PDFs baixados | Não informada | R$ 200.000.000 | Residual / sem parâmetro definido | Pode ser extraordinária se respeitado o índice de subordinação e caixa excedente; sem calendário fixo | 558803 p.4 |
| SELLER | 50.473.039/0001-02 | Sênior 5ª série |  | Sênior | 19/05/2025 e 26/05/2025 | 29/05/2025 | 1.500.000 | R$ 1.500.000.000 | DI + 0,85% a.a. (252 d.u.) | 15/12/2027: 16,67%; 15/01/2028: 20,00%; 15/02/2028: 25,00%; 15/03/2028: 33,33%; 15/04/2028: 50,00%; 15/05/2028: 100,00% | 909546 p.9; 912093 pp.3-5; 912172 p.2; 932137 p.2 |
| SELLER II | 55.471.753/0001-77 | Subordinada Júnior inicial |  | Subordinada Júnior | 10/06/2024 | Não identificada nos PDFs baixados | 50.000 | Até R$ 50.000.000 | Residual / sem parâmetro definido | Sem calendário fixo identificado | 691281 p.2 |
| SELLER II | 55.471.753/0001-77 | Sênior 1ª série |  | Sênior | 25/07/2024; aditivo 26/07/2024 | Não textual; distribuição encerrada em 06/08/2024 | 1.000.000 | R$ 1.000.000.000 | DI + 0,85% a.a. (252 d.u.) | 15/02/2027 a 15/07/2027: 1/6 do VNU em cada mês | 705139 pp.3-5; 705145; 706203; 714216 pp.1-2 |
| SELLER II | 55.471.753/0001-77 | Subordinada Júnior adicional |  | Subordinada Júnior | 06/09/2024 | Não identificada nos PDFs baixados | Até 10.000 | Não fixado; depende do VNU em vigor | Residual / sem parâmetro definido | Sem calendário fixo identificado | 733048 pp.1-3 |
| SELLER 3 | 63.572.282/0001-11 | Subordinada Júnior - emissão aprovada em 05/01/2026 |  | Subordinada Júnior | 05/01/2026 | Não identificada nos PDFs baixados | 2.000 | R$ 2.000.000 | Residual / sem parâmetro definido | Sem calendário fixo identificado | 1080485 pp.1-2 |
| SELLER 3 | 63.572.282/0001-11 | Subordinada Júnior - 2ª emissão |  | Subordinada Júnior | 12/01/2026 | 12/01/2026 | Total dividido pelo VNU das juniores em vigor | R$ 16.000.000 | Residual / sem parâmetro definido | Sem calendário fixo identificado | 1080490 pp.1-3 |
| SELLER 3 | 63.572.282/0001-11 | Sênior 1ª série |  | Sênior | 21/01/2026 | 05/02/2026 | 1.500.000 | R$ 1.500.000.000 | DI + 0,65% a.a. (252 d.u.) | 15/09/2028: 16,6667%; 15/10/2028: 20,0000%; 15/11/2028: 25,0000%; 15/12/2028: 33,3333%; 15/01/2029: 50,0000%; 15/02/2029: 100,0000% | 1089840 pp.1-2; 1089845 pp.151-153; 1101975 p.2; 1104314 pp.1-2 |
| SELLER 3 | 63.572.282/0001-11 | Subordinada Júnior - 3ª emissão |  | Subordinada Júnior | 21/01/2026 | Não identificada nos PDFs baixados | Não informada | Até R$ 195.000.000 | Residual / sem parâmetro definido | Sem calendário fixo identificado | 1089840 p.2 |
| Mercado Crédito Merchant Fundo de Investimento em Direitos Creditórios | 28.472.333/0001-32 | Cotas Seniores da 2ª (segunda) Série |  | Sênior | 06/11/2020 11:00 | Não identificada na extração offline |  | R$ 140.000.00,00 |  | 5º, da Instrução da CVM nº 356, de 17 de dezembro de 2001, conforme alterada, e item 18.2.4 do regulamento do Fundo (“Regulamento”). ORDEM DO DIA: Deliberar, nos termos do Capítul… | 135822_assembleia_assembleia_135822_2020-11-06.pdf · ID 135822 · 06/11/2020 11:00 |
| Mercado Crédito Merchant Fundo de Investimento em Direitos Creditórios | 28.472.333/0001-32 | Cotas Seniores |  | Sênior | 16/11/2020 | Não identificada na extração offline |  |  | _____ 2 SP - 23542534v1 ÍNDICE REGULAMENTO 4 CONDOMÍNIO E PRAZO DE DURAÇÃO 4 POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 4 CRITÉRIOS DE ELEGIBILIDADE, CONDIÇÕES DE CESSÃO E… | ES DE CESSÃO E AQUISIÇÃO 7 FATORES DE RISCO 12 ADMINISTRADORA 21 OBRIGAÇÕES, VEDAÇÕES E RESPONSABILIDADES DA ADMINISTRADORA 21 REMUNERAÇÃO DA ADMINISTRADORA 24 SUBSTITUIÇÃO E RENÚ… | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 · 16/11/2020 |
| Mercado Crédito Merchant Fundo de Investimento em Direitos Creditórios | 28.472.333/0001-32 | Cotas Seniores |  | Sênior | 13/04/2023 18:00 | Não identificada na extração offline |  |  | Gestora aditarão todos os contratos vigentes envolvendo o Fundo, conforme aplicável, para que a Nova Gestora passe a figurar como instituição gestora e, quando for o caso, represe… | Cotas .............................................................................................................................................................................… | 444985_assembleia_assembleia_444985_2023-04-13.pdf · ID 444985 · 13/04/2023 18:00 |
| Mercado Crédito Merchant Fundo de Investimento em Direitos Creditórios | 28.472.333/0001-32 | Cotas Seniores |  | Sênior | 19/04/2023 | Não identificada na extração offline |  |  | .............................................12 Administradora ....................................................................................................................… | Cotas .............................................................................................................................................................................… | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 · 19/04/2023 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Cotas Seniores na forma do Suplemento constante no Anexo II da p |  | Sênior | 13/08/2021 16:00 | Não identificada na extração offline |  | R$ 100.000.00,00 | ento do Fundo, para incluir novas atividades cuja responsabilidade é da Gestora; b) alteração do Capítulo 10 do Regulamento do Fundo, para definição da Relação Mínima de Subordina… | as atividades cuja responsabilidade é da Gestora; b) alteração do Capítulo 10 do Regulamento do Fundo, para definição da Relação Mínima de Subordinação, entre outros pequenos ajus… | 211844_assembleia_assembleia_211844_2021-08-13.pdf · ID 211844 · 13/08/2021 16:00 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Cotas Seniores referente à Segunda Série de Cotas Seniores do Fu |  | Sênior | 30/08/2023 09:00 | Não identificada na extração offline |  | R$ 1.000,00 |  |  | 519065_assembleia_assembleia_519065_2023-08-30.pdf · ID 519065 · 30/08/2023 09:00 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Cotas Seniores da Segunda Série do Fundo |  | Sênior | 03/09/2024 11:00 | Não identificada na extração offline |  | R$ 1.000,00 | oeda corrente nacional, pelo valor nominal unitário. Sendo, R$ 50.00 0.000,00 (cinquenta milhões de reais) integralizados no ato de subscrição e duas tranches de R$ 15.000.000,00… | ão positiva do CDI, acrescida de um spread de 4,5% a.a. (quatro inteiros e cinco décimos por cento) ao ano, sendo certo que os benchmarks previstos nos itens (i) e (ii) acima são… | 749010_assembleia_assembleia_749010_2024-09-03.pdf · ID 749010 · 03/09/2024 11:00 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Cotas Seniores |  | Sênior | 30/04/2025 13:00 | Não identificada na extração offline |  | R$ 1.000,00 | de capital a serem realizadas pelo Administrador, nos termos dos respectivos Compromissos de Investimento, Boletins de Subscrição e do Regulamento , conforme o caso. VI. Prazo de… | va emissão, as quais serão objeto de colocação privada, sem intermediação de instituição financeira integrante do sistema brasileiro de distribuição de valores mobiliários, cujos… | 914383_assembleia_assembleia_914383_2025-04-30.pdf · ID 914383 · 30/04/2025 13:00 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Cotas Seniores |  | Sênior | 03/03/2026 13:00 | Não identificada na extração offline |  | R$ 1.000,00 | das pela Administradora, conforme orientação da Gestora em alinhamento com o Mercado Pago, nos termos dos respectivos Compromissos de Investimento, Boletins de Subscrição , do Apê… | b forma de capitalização composta, com base em um ano de 252 (duzentos e cinquenta e dois) Dias Úteis da Meta de Remuneração. VIII. Remuneração Sênior: A Remuneração Sênior será p… | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf · ID 1128337 · 03/03/2026 13:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 |  |  |  | 25/05/2021 10:00 | Não identificada na extração offline |  | R$ 400.000.000,00 |  | icardo Donisete Stabile, Rodrigo Martins Cavalcante, Jessica Bezerra Da Silva, Douglas Shibayama, Raccelli Portela Santonastaso e Marcos Moretti. Para verificar as assinaturas vá… | 179557_assembleia_assembleia_179557_2021-05-25.pdf · ID 179557 · 25/05/2021 10:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 |  |  |  | 30/12/2021 10:00 | Não identificada na extração offline |  | R$ 5.756.250,46 | ), conforme lista de presença arquivada junto à Administradora, e a representante da Administradora. 3. COMPOSIÇÃO DA MESA: Presidente: Isabella Uno; Secretário: Rafael Polifemi.… | o valor do Patrimônio Líquido do Fundo, observado o valor mínimo mensal de R$30.000,00 (trinta mil reais).” (vi) a alteração do item 19.2 do Regulamento d o Fundo, o qua l passará… | 296735_assembleia_assembleia_296735_2021-12-30.pdf · ID 296735 · 30/12/2021 10:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | Cotas Seniores (conforme definido no Regulamento) |  | Sênior | 29/04/2022 10:00 | Não identificada na extração offline |  | R$ 500.000.000,00 |  | o Regulamento do Fundo (Limites de Concentração), o qual passará a vigorar com a redação constante do Anexo B a esta Ata; e 2 (iv) mediante a aprovação dos itens anteriores, conse… | 297780_assembleia_assembleia_297780_2022-04-29.pdf · ID 297780 · 29/04/2022 10:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 |  |  |  | 14/10/2022 17:00 | Não identificada na extração offline |  | R$ 42.297.479,55 | ”), conforme lista de presença arquivada junto à Administradora, e a representante da Administradora. 3. COMPOSIÇÃO DA MESA: Presidente: Isabella Uno; Secretário: Juliana Gurzoni.… | ii) a alteração da redação do s itens 19.2, 19.3 e 19.4 do Capítulo Dezenove do Regulamento do Fundo, de forma a restar clara a forma de alocação dos recursos do Fundo, os quais p… | 366672_assembleia_assembleia_366672_2022-10-14.pdf · ID 366672 · 14/10/2022 17:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | COTAS SENIORES 110 |  | Sênior | 12/09/2023 | Não identificada na extração offline |  |  | nos termos do Contrato de Gestão. “Relatório de Acompanhamento” Relatório mensal a ser elaborado e disponibilizado pelo Gestor aos Cotistas e ao Administrador até o 16º (décimo se… | ITÓRIOS 48 CAPÍTULO NOVE – DOS CRITÉRIOS DE AVALIAÇÃO DOS DIREITOS CREDITÓRIOS E DOS ATIVOS FINANCEIROS INTEGRANTES DA CARTEIRA DO FUNDO 50 CAPÍTULO DEZ - DAS CARACTERÍSTICAS, DIR… | 521557_regulamento_regulamento_521557_2023-09-12.pdf · ID 521557 · 12/09/2023 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | Cotas Seniores da Primeira |  | Sênior | 12/09/2023 10:00 | Não identificada na extração offline |  | R$250,00 | erador igual ao número de dias a partir da data do Evento de Pagamento Qualificado até a Data Limite de Investimento em Direitos Creditórios e um denominador igual a 360 (trezento… | forma da presente ata de Assembleia Geral Extraordinária de Cotistas (“Ata”), sobre: (i) a alteração dos itens (iv) e (vi) da Cláusula 7.4 do Regulamento; (ii) a alteração do item… | 521510_assembleia_assembleia_521510_2023-09-12.pdf · ID 521510 · 12/09/2023 10:00 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | COTAS SENIORES 110 |  | Sênior | 10/06/2024 | Não identificada na extração offline |  |  | Pago nos termos do Contrato de Gestão. “Relatório de Acompanhamento” Relatório mensal a ser elaborado e disponibilizado pelo Gestor aos Cotistas e ao Administrador até o 16º (déci… | ITÓRIOS 48 CAPÍTULO NOVE – DOS CRITÉRIOS DE AVALIAÇÃO DOS DIREITOS CREDITÓRIOS E DOS ATIVOS FINANCEIROS INTEGRANTES DA CARTEIRA DO FUNDO 50 CAPÍTULO DEZ - DAS CARACTERÍSTICAS, DIR… | 678673_regulamento_regulamento_678673_2024-06-10.pdf · ID 678673 · 10/06/2024 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | cotas seniores na Cota Sênior |  | Sênior | 12/07/2024 10:00 | Não identificada na extração offline |  |  |  | teração da definição de “Alteração de Controle” prevista no Regulamento do Fundo para ajustar a previsão de controle da MeLi sobre o Mercado Pago, para incluir previsão de alteraç… | 699514_assembleia_assembleia_699514_2024-07-12.pdf · ID 699514 · 12/07/2024 10:00 |

_Exibindo 30 de 187 linhas. Ver CSV para a tabela completa._

## 2. Preço e economia das emissões

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.2 | \bremunera[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO, PRAZO DE DURAÇÃO E CLASSIFICAÇÃO DO FUNDO 4 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 5 3. FATORES DE RISCO 11 4. PRESTADORES DE SERV… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.16 | \bremunera[cç][aã]o\b | ...o. Nos termos do artigo 18 da Resolução CVM nº 175 e do artigo 1.368-D, inciso I, do Código Civil, os Cotistas da Classe do Fundo terão sua responsabilidade limitada ao valor p… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.23 | \bremunera[cç][aã]o\b | ... amortizadas de acordo com o estabelecido neste Regulamento e nos respectivos Apêndices e/ou nos respectivos Suplementos. No entanto, há eventos que podem ensejar a antecipação… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.27 | \bremunera[cç][aã]o\b | ... à CVM, por meio de sistema eletrônico disponível na rede mundial de computadores, no prazo de 45 (quarenta e cinco) dias após o encerramento do trimestre civil a que se referi… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.37 | \bremunera[cç][aã]o\b | 37 iv. todos os recibos comprobatórios do pagamento de qualquer encargo do Fundo. 8.2.1 A remuneração devida ao Custodiante em razão dos serviços prestados ao Fundo está incluída… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.2 | \bpre[cç]o de emiss[aã]o\b | ... sujeitas a regulamentação de oferta de valores mobiliários da Resolução CVM nº 160, de 13 de julho de 2022 (“Resolução CVM 160”); b) Público-alvo: Investidores profissionais,… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.6 | \bDI\b, \bmeta de remunera[cç][aã]o\b, \bremunera[cç][aã]o\b, \bspread\b | 2 VII. Meta de Remuneração : A Meta de Remuneração Sênior será correspondente a 100% (cem por cento) da Taxa DI acrescida de “spread” de 2,5% (dois inteiros e cinco décimos por ce… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.7 | \bmeta de remunera[cç][aã]o\b, \bremunera[cç][aã]o\b | 3 Data de Pagamento % da Meta de Remuneração Sênior % da Amortização Sênior 31/dez/27 100,00% 6,25% 31/jan/28 100,00% 6,67% 29/fev/28 100,00% 7,14% 31/mar/28 100,00% 7,69% 30/abr/… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.5 | \bDI\b, \bbenchmark\b, \bmeta de remunera[cç][aã]o\b, \bremunera[cç][aã]o\b | ..., 10º andar, Itaim Bibi, inscrita no CNPJ sob o nº 36.266.751/0001-00 (“Administradora”). 2. Serão emitidas, nos termos deste Suplemento e do Regulamento, até 80.000 (oitenta m… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.6 | \bCDI\b, \bbenchmark\b, \bspread\b | 2 (i) Benchmark Regular: equivalente a 100% (cem por cento) da variação positiva do CDI, acrescida de um spread de 3,5% a.a. (três inteiros e cinco décimos por cento) ao ano, pago… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.7 | \bmeta de remunera[cç][aã]o\b, \bremunera[cç][aã]o\b, \bspread\b | ...l 25.00% 26 30-10-25 Juros + Principal 33.33% 27 30-11-25 Juros + Principal 50.00% 28 30-12-25 Juros + Principal 100.00% V. Data de Pagamento: cada uma das datas apresentadas n… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.8 | \bremunera[cç][aã]o\b | 4 alternativos e não serão , em hipótese nenhuma, buscados pelo Fundo ou aplicados sobre as Cotas Seniores de forma cumulativa. 5. Se o patrimônio do Fundo permitir, e observadas… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.2 | \bremunera[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO E PRAZO DE DURAÇÃO 3 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 3 3. CRITÉRIOS DE ELEGIBILIDADE E CONDIÇÕES DE CESSÃO 6 4. FATORES DE R… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.5 | \bDI\b | ...os Financeiros abaixo relacionados: a) títulos de emissão do Tesouro Nacional; b) operações compromissadas lastr eadas nos títulos mencionados na alínea a) acima; c) certificad… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.16 | \bremunera[cç][aã]o\b | ...res . As Cotas Seniores serão amortizadas de acordo com o estabelecido neste Regulamento e nos respectivos Suplementos. No entanto, há eventos que podem ensejar a antecipação d… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.18 | \bremunera[cç][aã]o\b | ...omo os ativos integrantes das respectivas carteiras e os de emissão ou coobrigação dessas. 6.5 É vedado à Administradora, em nome do Fundo, além do disposto no artigo 36 da Ins… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.26 | \bmeta de remunera[cç][aã]o\b, \bremunera[cç][aã]o\b | ...nte relatório de classificação de risco. 10.2 Cotas Seniores 10.2.1 As Cotas Seniores têm as seguintes características, vantagens, direitos e obrigações comuns: (a) prioridade… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.2 | \bremunera[cç][aã]o\b | ...edação constante no Anexo I da presente Ata , conforme as alterações a seguir ora aprovadas: a) alteração do item 9.2.1 do Regulamento do Fundo, para incluir novas atividades c… |

_Exibindo 18 de 368 linhas. Ver CSV para a tabela completa._

## 3. Cronograma de amortização

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

_Exibindo 25 de 585 linhas. Ver CSV para a tabela completa._

## 4. Alterações via atas e assembleias

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.2 | \bassembleia\b | ...ÇOS ESSENCIAIS 39 9. COTAS 41 10. RENTABILIDADE EXCEDENTE DO FUNDO 46 11. SUBSCRIÇÃO, INTEGRALIZAÇÃO E VALOR DAS COTAS 47 12. AMORTIZAÇÃO E RESGATE DAS COTAS 50 13. ORDEM DE AL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.5 | \baltera[cç][aã]o\b, \bassembleia\b | 5 Suplementos. Para fins de conveniência e, considerando que não serão admitidas a constituição de novas classes de cotas, as referências ao Fundo alcançam a única Classe de Cotas… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.16 | \bassembleia\b | 16 para se retirar antecipadamente do Fundo é a ocorrência de casos de liquidação antecipada da Classe previstos no Regulamento, e deliberação, via Assembleia Geral, sobre a liqui… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.21 | \baltera[cç][aã]o\b | 21 do ônus e gravames sobre os referidos direitos creditórios deixem de produzir os seus regulares efeitos para fins de publicidade a terceiros, poderá ser necessária a efetivação… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.22 | \bassembleia\b | ...g) Riscos e custos de cobrança . Os custos incorridos com eventuais procedimentos judiciais ou extrajudiciais necessários à cobrança dos Direitos Creditórios e dos demais ativo… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.1 | \bassembleia\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA CNPJ/MF nº 33.254.370/0001-04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 3 DE MARÇO D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.2 | \baprovar\b | (i) Aprovar a nova emissão de cotas da 4ª (quarta) série de Cotas Seniores , no valor total de R$ 500.000.000,00 (quinhentos milhões de reais), conforme as características indicad… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.3 | \bassembleia\b | A Administradora e a Gestora foram autorizadas a adotar todas as medidas necessárias para implementar as deliberações aprovadas nesta assembleia, observadas as suas respectivas co… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.4 | \bassembleia\b | Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios realizada em 3 de março de 2026. ANEXO B ATA DA ASSEMBLEIA GERAL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.9 | \bassembleia\b | Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios realizada em 3 de março de 2026. ANEXO C ATA DA ASSEMBLEIA GERAL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.1 | \baltera[cç][aã]o\b, \bassembleia\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 30 DE SETEMBRO DE 2… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.2 | \bassembleia\b | 2 As Partes conferem expressa anuência para que a ata da p resente assembleia seja firmada por meio de assinaturas eletrônicas, nos termos do artigo 10, da Medida Provisória nº 22… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.3 | \bassembleia\b | 3 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. MERCADO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.4 | \bassembleia\b | 4 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. ANEXO I… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.6 | \bassembleia\b | ... (i) e (ii) acima são alternativos e não serão, em hipótese nenhuma, buscados pelo Fundo ou aplicados sobre as Cotas Seniores de forma cumulativa. IV. Condições de Amortização… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.1 | \bassembleia\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 03 D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.2 | \bassembleia\b | ...Fundo Incorporador será realizada na Data de Incorporação, pelo valor contábil de tais bens, direitos e obrigações na respectiva data. 5.1.7. A partir da Data de Incorporação,… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.3 | \bassembleia\b | ...1.9. A Administradora fica autorizada nos limites de suas respectivas atribuições, a tomar todas as medidas necessárias à realização da incorporação ora deliberada. Os Cotistas… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.4 | \bassembleia\b | 4 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS EM 03 DE SETEMBRO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.2 | \bassembleia\b | ...MINISTRADORA 18 8. SUBSTITUIÇÃO E RENÚNCIA DA ADMINISTRADORA 19 9. GESTORA, DISTRIBUIDOR, CUSTODIANTE E AGENTE DE COBRANÇA 20 10. COTAS 25 11. SUBSCRIÇÃO, INTEGRALIZAÇÃO E VALO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.3 | \baltera[cç][aã]o\b, \bassembleia\b | ...tuição e Prazo de Duração 1.1 O Fundo é constituído sob a forma de condomínio fechado, de modo que as Cotas somente serão resgatadas ao término do respectivo prazo de duração d… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.11 | \bassembleia\b | 11 do Fundo previstos no Regulamento, e deliberação, pela Assembleia Geral, sobre a l iquidação antecipada do Fundo. Ocorrendo qualquer uma das hipóteses de liquidação antecipada… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.14 | \bassembleia\b | ... Riscos e custos de cobrança . Os custos incorridos com os procedimentos judiciais ou extrajudiciais necessários à cobrança dos Direitos Creditórios e dos demais ativos integra… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.16 | \bassembleia\b | ...taim Bibi, inscrita no CNPJ/ME sob o nº 36.266.751/0001 -00, autorizada a prestar serviços de administração fiduciária, previstos na Instrução CVM nº 558, de 26 de março de 201… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.1 | \baltera[cç][aã]o\b, \bassembleia\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO CNPJ/ME Nº 33.254.370/0001 -04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 13 DE… |

_Exibindo 25 de 529 linhas. Ver CSV para a tabela completa._

## 5. Cotistas e partes relacionadas

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.5 | \bcotistas?\b | ...Geral ou nas situações previstas neste Regulamento. 1.3 O Fundo é classificado como “Fundo de Investimento em Direitos Creditórios”, tipo “Financeiro”, com foco de atuação “Mul… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.6 | \bcedente\b, \bconcentra[cç][aã]o\b, \bcotistas?\b | 6 2.1.1.1 Os Direitos Creditórios Adquiridos e os Ativos Financeiros devem ser registrados, custodiados ou mantidos em conta de depósito diretamente em nome do Fundo, conforme o c… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.7 | \bdevedor\b | ...os no Complemento II a este Regulamento. 2.1.10 Após a aquisição dos Direitos Creditórios Adquiridos, o Fundo instruirá o Agente de Recebimento a direcionar a totalidade dos pa… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.8 | \bpartes? relacionadas?\b | ...ição seja a Mercado Crédito Sociedade de Crédito, Financiamento e Investimento S.A., até o limite de 10% (dez por cento) do Patrimônio Líquido do Fundo; e d) cotas de fundos de… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.9 | \bcedente\b | ...ra e, por consequência, o patrimônio do Fundo, estão sujeitos a diversos riscos, dentre os quais os discriminados no Capítulo 3 deste Regulamento. O investidor, antes de adquir… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.1 | \bcotistas?\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA CNPJ/MF nº 33.254.370/0001-04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 3 DE MARÇO D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.2 | \bcotistas?\b | .../ou mediante chamadas de capital, junto ao seu respectivo agente de custódia e/ou da Administradora na qualidade de escriturador das cotas, observados os termos e condições do… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.3 | \bcotistas?\b | ...por meio de assinaturas eletrônicas, nos termos do artigo 10, da Medida Provisória nº 2200 -2, de 24 de agosto de 2001, devendo, em casos de contingência, ser firmada de forma… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.4 | \bcotistas?\b | Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios realizada em 3 de março de 2026. ANEXO B ATA DA ASSEMBLEIA GERAL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.7 | \bcotistas?\b | .../dez/28 100,00% 25,00% 31/jan/29 100,00% 33,33% 28/fev/29 100,00% 50,00% 31/mar/29 100,00% 100,00% XI. Classificação de Risco: Não haverá classificação de risco. XII. Rentabili… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.1 | \bcotistas?\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 30 DE SETEMBRO DE 2… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.2 | \bcotistas?\b | 2 As Partes conferem expressa anuência para que a ata da p resente assembleia seja firmada por meio de assinaturas eletrônicas, nos termos do artigo 10, da Medida Provisória nº 22… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.3 | \bcotistas?\b | 3 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. MERCADO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.4 | \bcotistas?\b | 4 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. ANEXO I… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.1 | \bcotistas?\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 03 D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.2 | \bcontrolad[ao]r, \bcotistas?\b | 2 5.1. Os Cotistas deliberaram pela aprovação, sem quaisquer restrições ou ressalvas, da incorporação do Fundo Incorporado pelo Fundo Incorporador, com base no fechamento do exped… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.3 | \bcotistas?\b | 3 5.1.9. A Administradora fica autorizada nos limites de suas respectivas atribuições, a tomar todas as medidas necessárias à realização da incorporação ora deliberada. Os Cotista… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.4 | \bcotistas?\b | 4 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS EM 03 DE SETEMBRO… |

_Exibindo 18 de 532 linhas. Ver CSV para a tabela completa._

## 6. Direitos creditórios e cessões

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.1 | \bdireitos credit[oó]rios\b | 1 REGULAMENTO DO MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA CNPJ/MF Nº 33.254.370.0001-04 03 de março de 2026 Docusign Envelope ID: C7… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.2 | \bdireitos credit[oó]rios\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO, PRAZO DE DURAÇÃO E CLASSIFICAÇÃO DO FUNDO 4 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 5 3. FATORES DE RISCO 11 4. PRESTADORES DE SERV… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.4 | \bdireitos credit[oó]rios\b | 4 REGULAMENTO DO MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA O “MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSAB… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.5 | \bcess[aã]o\b, \bcondi[cç][oõ]es de cess[aã]o\b, \bcrit[eé]rios? de elegibilidade\b, \bdireitos credit[oó]rios\b | ...ue não serão admitidas a constituição de novas classes de cotas, as referências ao Fundo alcançam a única Classe de Cotas, e vice e versa. 1.2 O funcionamento do Fundo terá iní… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.6 | \bdireitos credit[oó]rios\b | 6 2.1.1.1 Os Direitos Creditórios Adquiridos e os Ativos Financeiros devem ser registrados, custodiados ou mantidos em conta de depósito diretamente em nome do Fundo, conforme o c… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.1 | \bdireitos credit[oó]rios\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA CNPJ/MF nº 33.254.370/0001-04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 3 DE MARÇO D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.4 | \bdireitos credit[oó]rios\b | Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios realizada em 3 de março de 2026. ANEXO B ATA DA ASSEMBLEIA GERAL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.5 | \bdireitos credit[oó]rios\b | 1 SUPLEMENTO DA 4ª SÉRIE DE COTAS SENIORES 1. O presente documento constitui o suplemento nº 01 (“ Suplemento”), referente à 4ª (quarta) Série de cotas seniores de emissão do MERC… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.9 | \bdireitos credit[oó]rios\b | Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios realizada em 3 de março de 2026. ANEXO C ATA DA ASSEMBLEIA GERAL… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.1 | \bdireitos credit[oó]rios\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 30 DE SETEMBRO DE 2… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.3 | \bdireitos credit[oó]rios\b | 3 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. MERCADO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.4 | \bdireitos credit[oó]rios\b | 4 Página integrante da Assembleia Geral de Cotistas do Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. ANEXO I… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.5 | \bdireitos credit[oó]rios\b | 1 Suplemento de Cotas Seniores Mercado Crédito Fundo de Investimento em Direitos Creditórios Não Padronizado CNPJ/MF sob nº 33.254.370/001-04 1. O presente documento constitui o s… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.1 | \bdireitos credit[oó]rios\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 03 D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.2 | \bdireitos credit[oó]rios\b, \bsubstitui[cç][aã]o\b | ...r possuem políticas de investimento e público- alvo compatíveis. 5.1.2. A atividade de administração do Fundo Incorporador será realizada pela Administradora. 5.1.3. As ativida… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.4 | \bdireitos credit[oó]rios\b | 4 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS EM 03 DE SETEMBRO… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.1 | \bdireitos credit[oó]rios\b | REGULAMENTO MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO” CNPJ/ME Nº 33.254.370-0001-04 13 DE AGOSTO DE 2021. |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.2 | \bcess[aã]o\b, \bcondi[cç][oõ]es de cess[aã]o\b, \bcrit[eé]rios? de elegibilidade\b, \bdireitos credit[oó]rios\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO E PRAZO DE DURAÇÃO 3 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 3 3. CRITÉRIOS DE ELEGIBILIDADE E CONDIÇÕES DE CESSÃO 6 4. FATORES DE R… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.3 | \bcess[aã]o\b, \bcondi[cç][oõ]es de cess[aã]o\b, \bcrit[eé]rios? de elegibilidade\b, \bdireitos credit[oó]rios\b | 3 REGULAMENTO DO MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO O “MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO”, d… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.4 | \bcess[aã]o\b, \bdireitos credit[oó]rios\b | 4 do Fundo, conforme o caso, em contas específicas abertas no SELIC, ou em instituições ou entidades autorizadas à prestação desse serviço pelo BACEN ou pela CVM. 2.2 A cada aquis… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.5 | \bcrit[eé]rios? de elegibilidade\b, \bdireitos credit[oó]rios\b | 5 inadimplidos será realizada pelo Custodiante ou prestador de serviço por ele contratado, em todos os casos nos termos da Política de Cobrança, constante do Anexo III do Regulame… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.1 | \bdireitos credit[oó]rios\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO CNPJ/ME Nº 33.254.370/0001 -04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 13 DE… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.4 | \bdireitos credit[oó]rios\b | Página de assinaturas da Ata de Assembleia Geral Extraordinária de Cotistas do MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO realizada em 13 de ago… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 | 365262_regulamento_regulamento_365262_2022-10-14.pdf p.1 | \bdireitos credit[oó]rios\b | 1 REGULAMENTO DO MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO” CNPJ/ME Nº 33.254.370-0001-04 São Paulo, 14 de outubro de 2022 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 | 365262_regulamento_regulamento_365262_2022-10-14.pdf p.2 | \bcess[aã]o\b, \bcondi[cç][oõ]es de cess[aã]o\b, \bcrit[eé]rios? de elegibilidade\b, \bdireitos credit[oó]rios\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO E PRAZO DE DURAÇÃO 3 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 4 3. CRITÉRIOS DE ELEGIBILIDADE E CONDIÇÕES DE CESSÃO 7 4. FATORES DE R… |

_Exibindo 25 de 547 linhas. Ver CSV para a tabela completa._

Amostra de critérios de elegibilidade extraídos:

| grupo | nome_curto | cnpj | criterio | descricao |
| --- | --- | --- | --- | --- |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | os da respectiva Data de Aquisição e Pagamento; e (vi) os Direitos Creditórios dos Estabelecimentos Comerciais deverão ser provenientes de Transações de Pagamento realizadas por U… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | is” significa qualquer dia que não seja sábado, domingo, feriado nacional, ou dias em que, por qualquer motivo, não houver expediente bancário na República Federativa do Brasil. “… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | etapas: (i.1) no caso dos Direitos Creditórios dos Estabelecimentos Comerciais, solicitação pelos Estabelecimentos Comerciais, através do Agente de Pagamento e Registro, da cessão… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | da cessão de Direitos Creditórios Elegíveis, nos termos do Contrato de Cessão dos Direitos Creditórios do Mercado Crédito e do Acordo Operacional; (ii) envio do Arquivo de Oferta… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | Creditórios pelo Custodiante, c onforme o fluxo previsto nos respectivos Contratos de Cessão; (iii) envio pelo Custodiante do Arquivo de Retorno confirmando a aquisição dos Direit… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | o e/ou substituído de tempos em tempos, por meio do qual os Estabelecimentos Comerciais (i) aderem aos termos e condições gerais de prestação de serviços pelo Devedor, passando a… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | das pelo Fundo. “Cotistas Subordinados Mezanino” significam os titulares de Cotas Subordinadas Mezanino emitidas pelo Fundo. “Cotistas Subordinados Juniores” significam os titular… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | s da respectiva Data de Aquisição e Pagamento; e (vi) os Direitos Creditórios dos Estabelecimentos Comerciais deverão ser provenientes de Transações de Pagamento realizadas por Us… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | Úteis” significa qualquer dia que não seja sábado, domingo, feriado nacional, ou dias em que, por qualquer motivo, não houver expediente bancário na República Federativa do Brasil… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | e Regulamento. “FGC” é o Fundo Garantidor de Créditos. “Formalização Eletrônica de Cessão” significa o processo (e seus correspondentes arquivos eletrônicos) e a conclusão da ofer… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | s seguintes etapas: (i.1) no caso dos Direitos Creditórios dos Estabelecimentos Comerciais, solicitação pelos Estabelecimentos Comerciais, através do Mercado Pago , da cessão de D… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | Creditórios pelo Custodiante, co nforme o fluxo previsto nos respectivos Contratos de Cessão; (iii) envio pelo Custodiante do Arquivo de Retorno confirmando a aquisição dos Direit… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | o pela prestação de seus serviços de administração, calculada conforme o Artigo 6.3 deste Regulamento. “Taxa DI” significam as taxas médias diárias dos Depósitos Interfinanceiros… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | das pelo Fundo. “Cotistas Subordinados Mezanino” significam os titulares de Cotas Subordinadas Mezanino emitidas pelo Fundo. “Cotistas Subordinados Juniores” significam os titular… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | s da respectiva Data de Aquisição e Pagamento; e (vi) os Direitos Creditórios dos Estabelecimentos Comerciais deverão ser provenientes de Transações de Pagamento realizadas por Us… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | Úteis” significa qualquer dia que não seja sábado, domingo, feriado nacional, ou dias em que, por qualquer motivo, não houver expediente bancário na República Federativa do Brasil… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | e Regulamento. “FGC” é o Fundo Garantidor de Créditos. “Formalização Eletrônica de Cessão” significa o processo (e seus correspondentes arquivos eletrônicos) e a conclusão da ofer… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | s seguintes etapas: (i.1) no caso dos Direitos Creditórios dos Estabelecimentos Comerciais, solicitação pelos Estabelecimentos Comerciais, através do Mercado Pago , da cessão de D… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | Creditórios pelo Custodiante, co nforme o fluxo previsto nos respectivos Contratos de Cessão; (iii) envio pelo Custodiante do Arquivo de Retorno confirmando a aquisição dos Direit… |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Critério de elegibilidade | o pela prestação de seus serviços de administração, calculada conforme o Artigo 6.3 deste Regulamento. “Taxa DI” significam as taxas médias diárias dos Depósitos Interfinanceiros… |

_Exibindo 20 de 395 linhas. Ver CSV para a tabela completa._

## 7. Performance e risco

Performance histórica foi reconstruída apenas quando existia cache local de `Informe Mensal Estruturado`; para CNPJs sem cache, a lacuna fica explícita em `sellers_mercado_credito_performance_metrics.csv`.

| grupo | nome_curto | cnpj | indicador | competencias | ultimo_valor | observacao |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Cotas SR / PL % | 05/2025 a 05/2025 | 0.0 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Cotas Sub / PL % | 05/2025 a 05/2025 | 0.0 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Dir Cred (R$ MM) | 05/2025 a 05/2025 | 1439.8936335399999 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Dir Cred / PL | 05/2025 a 05/2025 | 0.9502306322643146 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | PDD (R$ MM) | 05/2025 a 05/2025 | 198.04261194 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | PDD / Crédito | 05/2025 a 05/2025 | 0.1375397510808554 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | PDD / Venc Total | 05/2025 a 05/2025 | 2.773143432375973 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | PL (R$) | 05/2025 a 05/2025 | 1515309636.05 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Rentabilidade SR % a.m. | 05/2025 a 05/2025 | 1.26 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Rentabilidade Sub % a.m. | 05/2025 a 05/2025 | 0.0 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Vencidos Over 180 d / Crédito | 05/2025 a 05/2025 | 0.01784385554010177 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Vencidos Over 30 d / Crédito | 05/2025 a 05/2025 | 0.042605680649601796 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Vencidos Over 360 d / Crédito | 05/2025 a 05/2025 | 0.0 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Vencidos Over 60 d / Crédito | 05/2025 a 05/2025 | 0.0366975346228115 |  |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | Vencidos Over 90 d / Crédito | 05/2025 a 05/2025 | 0.03197007198846067 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Cotas SR / PL % | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Cotas Sub / PL % | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Dir Cred (R$ MM) | 01/2026 a 12/2025 | 4397.9196846899995 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Dir Cred / PL | 01/2026 a 12/2025 | 0.9401934012706684 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | PDD (R$ MM) | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | PDD / Crédito | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | PDD / Venc Total | 01/2026 a 12/2025 |  |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | PL (R$) | 01/2026 a 12/2025 | 4677675549.25 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Rentabilidade SR % a.m. | 01/2026 a 12/2025 |  |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Rentabilidade Sub % a.m. | 01/2026 a 12/2025 | 3.5 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Vencidos Over 180 d / Crédito | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Vencidos Over 30 d / Crédito | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Vencidos Over 360 d / Crédito | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Vencidos Over 60 d / Crédito | 01/2026 a 12/2025 | 0.0 |  |
| Sellers | Seller FIDC | 50.473.039/0001-02 | Vencidos Over 90 d / Crédito | 01/2026 a 12/2025 | 0.0 |  |

_Exibindo 30 de 49 linhas. Ver CSV para a tabela completa._

## 8. Governança e operacional

| grupo | nome_curto | cnpj | data_referencia | fonte_pagina | termos_encontrados | trecho |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.2 | \badministrador[ae]?\b, \bagente de cobran[cç]a\b, \bcustodiante\b, \bgestor[ae]?\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO, PRAZO DE DURAÇÃO E CLASSIFICAÇÃO DO FUNDO 4 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 5 3. FATORES DE RISCO 11 4. PRESTADORES DE SERV… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.7 | \bagente de cobran[cç]a\b | ...tórios CCB Adquiridos diretamente para uma conta do Fundo, nos termos do respectivo contrato de prestação de serviço a ser firmado com o Agente de Recebimento, enquanto os Dire… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.8 | \badministrador[ae]?\b, \bgestor[ae]?\b | ...rizadas; observado, caso a instituição seja a Mercado Crédito Sociedade de Crédito, Financiamento e Investimento S.A., até o limite de 10% (dez por cento) do Patrimônio Líquido… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.9 | \badministrador[ae]?\b, \bagente de cobran[cç]a\b, \bcustodiante\b, \bgestor[ae]?\b | 9 aquisição de Direitos Creditórios pelo Fundo, se os Direitos Creditórios atendem aos Critérios de Elegibilidade. A Gestora poderá subcontratar um prestador de serviço para, nos… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf p.10 | \bgestor[ae]?\b | ...berta e sem nenhum ônus ou restrição nos termos da legislação aplicável; e c) Não pode ter sido verificada, nos termos dos Documentos de Aquisição, nenhuma hipótese de resoluçã… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.1 | \badministrador[ae]?\b, \bgestor[ae]?\b | ...neiro, na Praia de Botafogo, nº 501, Torre Corcovado, 5º andar – parte, Botafogo, CEP 22250-040, inscrito no Cadastro Nacional da Pessoa Jurídica (“CNPJ/MF”) sob o nº 59.281.25… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.2 | \badministrador[ae]?\b, \bescriturador\b | ...o da Cota apurado na respectiva data de integralização, que será correspondente ao resultado da divisão do valor do Patrimônio Líquido pelo número de Cotas Seniores em circulaç… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.3 | \badministrador[ae]?\b, \bgestor[ae]?\b | A Administradora e a Gestora foram autorizadas a adotar todas as medidas necessárias para implementar as deliberações aprovadas nesta assembleia, observadas as suas respectivas co… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.5 | \badministrador[ae]?\b, \bgestor[ae]?\b | ...4ª (quarta) Série de cotas seniores de emissão do MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA , inscrito no CNPJ/MF sob nº 33.254.37… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/03/2026 13:00 | 1128337_assembleia_assembleia_1128337_2026-03-03.pdf p.8 | \bgestor[ae]?\b | ...s Seniores, relativo às Cotas Seniores da respectiva Série, que corresponde à data do término do prazo de duraçã o da respectiva Série de Cotas Seniores, pelo seu respectivo va… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.1 | \badministrador[ae]?\b, \bgestor[ae]?\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL DE COTISTAS REALIZADA EM 30 DE SETEMBRO DE 2… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.2 | \badministrador[ae]?\b | ...forma impressa. 7. ENCERRAMENTO: Nada mais havendo a trat ar, após lavrada esta ata, de forma sumária, foi aprovada pelos presentes, conforme a lista de presença de cotistas ar… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.3 | \badministrador[ae]?\b, \bgestor[ae]?\b | ...to Fundo de Investimento em Direitos Creditórios Não Padronizados realizada em 30 de setembro de 2024. MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONI… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010_assembleia_assembleia_749010_2024-09-03.pdf p.5 | \badministrador[ae]?\b | ... regulamento disponibilizado na página da CVM na rede mun dial de computadores no endereço www.cvm.gov.br, do qual este Suplemento é parte integrante (“Regulamento”). O Fundo é… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.1 | \badministrador[ae]?\b, \bgestor[ae]?\b | 1 MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADOS CNPJ/MF nº 33.254.370/0001‐04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 03 D… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.2 | \badministrador[ae]?\b, \bsubstitui[cç][aã]o\b | ...ressalvas, da incorporação do Fundo Incorporado pelo Fundo Incorporador, com base no fechamento do expediente bancário do dia 13 de setembro de 2024, podendo ser implementada e… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 19:00 | 731592_assembleia_assembleia_731592_2024-09-03.pdf p.3 | \badministrador[ae]?\b, \bgestor[ae]?\b | 3 5.1.9. A Administradora fica autorizada nos limites de suas respectivas atribuições, a tomar todas as medidas necessárias à realização da incorporação ora deliberada. Os Cotista… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.2 | \badministrador[ae]?\b, \bagente de cobran[cç]a\b, \bcustodiante\b, \bgestor[ae]?\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO E PRAZO DE DURAÇÃO 3 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 3 3. CRITÉRIOS DE ELEGIBILIDADE E CONDIÇÕES DE CESSÃO 6 4. FATORES DE R… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.4 | \bagente de cobran[cç]a\b | ...lativos aos Direitos Creditórios CCB Adquiridos diretamente para a Conta de Arrecadação e/ou para a Conta do Fundo, nos termos do respectivo contrato de prestação de serviço a… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.5 | \badministrador[ae]?\b, \bcustodiante\b, \bgestor[ae]?\b | 5 inadimplidos será realizada pelo Custodiante ou prestador de serviço por ele contratado, em todos os casos nos termos da Política de Cobrança, constante do Anexo III do Regulame… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.6 | \badministrador[ae]?\b, \bagente de cobran[cç]a\b, \bcustodiante\b, \bgestor[ae]?\b | ...rte ou a totalidade de seu patrimônio. A Carteira e, por consequência, seu patrimônio, estão sujeitos a diversos riscos, dentre os quais os discriminados no Capítulo 4 deste Re… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364_regulamento_regulamento_207364_2021-08-13.pdf p.7 | \badministrador[ae]?\b, \bcustodiante\b, \bgestor[ae]?\b | ...u pessoa jurídica inscrita, respectivamente, no Cadastro de Pessoas Físicas ou Cadastro Nacional de Pessoas Jurídicas; e (b) O respectivo Cedente não pode estar inadimplente pe… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.1 | \badministrador[ae]?\b | MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS NÃO PADRONIZADO CNPJ/ME Nº 33.254.370/0001 -04 ATA DA ASSEMBLEIA GERAL EXTRAORDINÁRIA DE COTISTAS REALIZADA EM 13 DE… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844_assembleia_assembleia_211844_2021-08-13.pdf p.2 | \badministrador[ae]?\b, \bgestor[ae]?\b | inclusão dos Anexos VIII e IX no Regulamento do Fundo; (xi) consolidação do Regulamento do Fundo, conforme Anexo I à presente Ata; e ( xii) autorização para a Administradora prati… |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 | 365262_regulamento_regulamento_365262_2022-10-14.pdf p.2 | \badministrador[ae]?\b, \bagente de cobran[cç]a\b, \bcustodiante\b, \bgestor[ae]?\b, \bsubstitui[cç][aã]o\b | 2 Índice 1. FORMA DE CONSTITUIÇÃO E PRAZO DE DURAÇÃO 3 2. POLÍTICA DE INVESTIMENTO E COMPOSIÇÃO DA CARTEIRA 4 3. CRITÉRIOS DE ELEGIBILIDADE E CONDIÇÕES DE CESSÃO 7 4. FATORES DE R… |

_Exibindo 25 de 572 linhas. Ver CSV para a tabela completa._

## 9. Triggers, eventos e monitorabilidade pelo IME

### Evolução documental de limites e thresholds

A tabela abaixo ordena as evidências por fundo, chave canônica e data do documento, marcando alteração de limite quando o par comparação/limite muda.

| grupo | nome_curto | cnpj | data_documento | documento_id | criterio | chave | comparacao | limite | monitorabilidade_ime | mudanca_vs_evidencia_anterior | fonte_pagina |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | 135821 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | primeira evidência local | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | 135821 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | 135821 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | 135821 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 13/04/2023 18:00 | 444985 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 444985_assembleia_assembleia_444985_2023-04-13.pdf · ID 444985 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | 448299 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | 448299 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | 448299 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 13/04/2023 18:00 | 444985 | Cobertura mínima de PDD/provisão | pdd_coverage_min | >= | 20% | monitoravel | primeira evidência local | 444985_assembleia_assembleia_444985_2023-04-13.pdf · ID 444985 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | 448299 | Cobertura mínima de PDD/provisão | pdd_coverage_min | >= | 20% | monitoravel | sem mudança vs evidência anterior | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 10:00 | 732139 | Cobertura mínima de PDD/provisão | pdd_coverage_min | >= | 20% | monitoravel | sem mudança vs evidência anterior | 732139_assembleia_assembleia_732139_2024-09-03.pdf · ID 732139 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Cobertura mínima de PDD/provisão | pdd_coverage_min | >= | 20% | monitoravel | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | 135821 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | primeira evidência local | 135821_regulamento_regulamento_135821_2020-11-16.pdf · ID 135821 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 13/04/2023 18:00 | 444985 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 444985_assembleia_assembleia_444985_2023-04-13.pdf · ID 444985 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | 448299 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 448299_regulamento_regulamento_448299_2023-04-19.pdf · ID 448299 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 10:00 | 732139 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 732139_assembleia_assembleia_732139_2024-09-03.pdf · ID 732139 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 10:00 | 732139 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 732139_assembleia_assembleia_732139_2024-09-03.pdf · ID 732139 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | 732140 | Hedges/derivativos permitidos | permitted_hedges | texto |  | parcial | sem mudança vs evidência anterior | 732140_regulamento_regulamento_732140_2024-09-03.pdf · ID 732140 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/04/2025 | 914386 | Limite de concentração | concentration_limits | >= | 67% | nao_monitoravel | primeira evidência local | 914386_regulamento_regulamento_914386_2025-04-30.pdf · ID 914386 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 | 206963 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | primeira evidência local | 206963_regulamento_regulamento_206963_2021-07-15.pdf · ID 206963 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 | 206963 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 206963_regulamento_regulamento_206963_2021-07-15.pdf · ID 206963 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/07/2021 | 201177 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 201177_regulamento_regulamento_201177_2021-07-30.pdf · ID 201177 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/07/2021 | 201177 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 201177_regulamento_regulamento_201177_2021-07-30.pdf · ID 201177 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 207364_regulamento_regulamento_207364_2021-08-13.pdf · ID 207364 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | 207364 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 207364_regulamento_regulamento_207364_2021-08-13.pdf · ID 207364 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 16:00 | 211844 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | alterou de >= 50% para >= 100% | 211844_assembleia_assembleia_211844_2021-08-13.pdf · ID 211844 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 21/10/2021 | 228026 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | alterou de >= 100% para >= 50% | 228026_regulamento_regulamento_228026_2021-10-21.pdf · ID 228026 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 21/10/2021 | 228026 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 228026_regulamento_regulamento_228026_2021-10-21.pdf · ID 228026 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 29/06/2022 10:00 | 325863 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 325863_assembleia_assembleia_325863_2022-06-29.pdf · ID 325863 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 29/06/2022 10:00 | 325863 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 6% | monitoravel | alterou de >= 50% para >= 6% | 325863_assembleia_assembleia_325863_2022-06-29.pdf · ID 325863 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 29/06/2022 10:00 | 325863 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | alterou de >= 6% para >= 50% | 325863_assembleia_assembleia_325863_2022-06-29.pdf · ID 325863 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 29/06/2022 | 325865 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 325865_regulamento_regulamento_325865_2022-06-29.pdf · ID 325865 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 17:00 | 365260 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | alterou de >= 50% para >= 100% | 365260_assembleia_assembleia_365260_2022-10-14.pdf · ID 365260 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 17:00 | 365260 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | sem mudança vs evidência anterior | 365260_assembleia_assembleia_365260_2022-10-14.pdf · ID 365260 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 17:00 | 365260 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | <= | 10% | monitoravel | alterou de >= 100% para <= 10% | 365260_assembleia_assembleia_365260_2022-10-14.pdf · ID 365260 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 14/10/2022 | 365262 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | alterou de <= 10% para >= 50% | 365262_regulamento_regulamento_365262_2022-10-14.pdf · ID 365262 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 16/03/2023 09:00 | 433414 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | alterou de >= 50% para >= 100% | 433414_assembleia_assembleia_433414_2023-03-16.pdf · ID 433414 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 17/04/2023 09:00 | 447603 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | sem mudança vs evidência anterior | 447603_assembleia_assembleia_447603_2023-04-17.pdf · ID 447603 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 26/04/2023 16:00 | 451292 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | sem mudança vs evidência anterior | 451292_assembleia_assembleia_451292_2023-04-26.pdf · ID 451292 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 26/04/2023 | 451354 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | alterou de >= 100% para >= 50% | 451354_regulamento_regulamento_451354_2023-04-26.pdf · ID 451354 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 26/04/2023 | 451354 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 451354_regulamento_regulamento_451354_2023-04-26.pdf · ID 451354 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/08/2023 | 519058 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 50% | monitoravel | sem mudança vs evidência anterior | 519058_regulamento_regulamento_519058_2023-08-30.pdf · ID 519058 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/08/2023 09:00 | 519065 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | alterou de >= 50% para >= 100% | 519065_assembleia_assembleia_519065_2023-08-30.pdf · ID 519065 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/09/2024 11:00 | 749010 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 100% | monitoravel | sem mudança vs evidência anterior | 749010_assembleia_assembleia_749010_2024-09-03.pdf · ID 749010 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/04/2025 | 914386 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 67% | monitoravel | alterou de >= 100% para >= 67% | 914386_regulamento_regulamento_914386_2025-04-30.pdf · ID 914386 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 19/02/2026 | 1118467 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | >= | 67% | monitoravel | sem mudança vs evidência anterior | 1118467_regulamento_regulamento_1118467_2026-02-19.pdf · ID 1118467 |

_Exibindo 50 de 594 linhas. Ver CSV para a tabela completa._

| Fundo | CNPJ | Critério | Chave | Limite/regra | Limite | Monitorabilidade IME | Métrica IME / proxy | Observação técnica | Fonte |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SELLER | 50.473.039/0001-02 | Índice de Subordinação |  | Cotas Subordinadas Juniores / PL >= 10% |  | direto com validação | Cotas Subordinadas Juniores / PL; no app, Cotas Sub / PL se não houver mezanino | Usar junior/PL, não subordinação total incluindo mezanino. IME precisa reconciliar classes de cotas. | 909547 pp.99,107-108 |
| SELLER | 50.473.039/0001-02 | Índice de Cobertura Sênior |  | Índice >= 1,00 |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Sênior) / Cotas Seniores | IME traz DC, caixa e cotas, mas não traz de forma padronizada Valor Presente pelo contrato, Comissões e fatores por série; exige parâmetros manuais. | 909547 pp.46,61,110 |
| SELLER | 50.473.039/0001-02 | Índice de Cobertura Mezanino |  | Índice >= 1,00 quando houver mezanino |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Mezanino) / (Sênior + Mezanino) | Mesma limitação do Índice de Cobertura Sênior; só aplicar se houver cota mezanino emitida. | 909547 pp.46,61,110 |
| SELLER | 50.473.039/0001-02 | Alocação mínima regulatória |  | Direitos Creditórios Elegíveis / PL >= 50% após 180 dias |  | direto com ressalva | Dir Cred / PL | IME vê direitos creditórios agregados, mas não valida elegibilidade individual. Usar como monitoramento de enquadramento econômico, não prova jurídica final. | 909547 pp.58,115 |
| SELLER | 50.473.039/0001-02 | Alocação mínima tributária |  | Direitos Creditórios Elegíveis / PL >= 67% |  | direto com ressalva | Dir Cred / PL | O texto extraído mostra inconsistência redacional: '67%' com extenso 'cinquenta por cento'. Validar juridicamente antes de alerta duro. | 909547 pp.31 |
| SELLER | 50.473.039/0001-02 | Derivativos |  | Operações com derivativos vedadas |  | direto agregado | MERC_DERIVATIVO / PL ou posições em derivativos | IME só mostra posição agregada; se houver valor, precisa análise do tipo/contraparte, mas para vedação total o alerta é útil. | 909547 pp.58 |
| SELLER | 50.473.039/0001-02 | Reserva de Liquidez |  | Mínimo equivalente a 3 meses de despesas ordinárias |  | parcial | Disponibilidades e Ativos Financeiros; despesas ordinárias precisam input/manual | IME não traz uma linha padronizada de '3 meses de despesas ordinárias' para o cálculo contratual. | 909547 pp.51,103 |
| SELLER | 50.473.039/0001-02 | Reserva de Caixa |  | 100% do próximo pagamento de amortização/remuneração até D-10; acumula desde D-45 |  | parcial | Disponibilidades/Ativos Financeiros vs próximo serviço da dívida | Depende do cronograma de cotas, saldo vivo e remuneração acumulada; IME ajuda, mas não resolve sozinho. | 909547 pp.51,103-104 |
| SELLER | 50.473.039/0001-02 | Inadimplemento de Direitos Creditórios |  | Default de qualquer Direito Creditório por >5 dias pode ser evento de liquidação |  | parcial fraco | Over 1d / Crédito como proxy mensal | A regra é diária e por título; IME mensal por bucket não comprova o evento jurídico. | 909547 pp.114-115 |
| SELLER | 50.473.039/0001-02 | Inconsistência de verificação de lastro |  | >5% da amostra / PL conforme cláusula |  | não usar via IME | Sem métrica IME confiável | Depende de auditoria de documentos comprobatórios, não de Informe Mensal. | 909547 pp.107,112 |
| SELLER 3 | 63.572.282/0001-11 | Índice de Subordinação |  | Cotas Subordinadas Juniores / PL >= 10% |  | direto com validação | Cotas Subordinadas Juniores / PL; no app, Cotas Sub / PL se não houver mezanino | Usar junior/PL, não subordinação total incluindo mezanino. IME precisa reconciliar classes de cotas. | 1089845 pp.99,107-108 |
| SELLER 3 | 63.572.282/0001-11 | Índice de Cobertura Sênior |  | Índice >= 1,00 |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Sênior) / Cotas Seniores | IME traz DC, caixa e cotas, mas não traz de forma padronizada Valor Presente pelo contrato, Comissões e fatores por série; exige parâmetros manuais. | 1089845 pp.46,61,110 |
| SELLER 3 | 63.572.282/0001-11 | Índice de Cobertura Mezanino |  | Índice >= 1,00 quando houver mezanino |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Mezanino) / (Sênior + Mezanino) | Mesma limitação do Índice de Cobertura Sênior; só aplicar se houver cota mezanino emitida. | 1089845 pp.46,61,110 |
| SELLER 3 | 63.572.282/0001-11 | Alocação mínima regulatória |  | Direitos Creditórios Elegíveis / PL >= 50% após 180 dias |  | direto com ressalva | Dir Cred / PL | IME vê direitos creditórios agregados, mas não valida elegibilidade individual. Usar como monitoramento de enquadramento econômico, não prova jurídica final. | 1089845 pp.58,115 |
| SELLER 3 | 63.572.282/0001-11 | Alocação mínima tributária |  | Direitos Creditórios Elegíveis / PL >= 67% |  | direto com ressalva | Dir Cred / PL | O texto extraído mostra inconsistência redacional: '67%' com extenso 'cinquenta por cento'. Validar juridicamente antes de alerta duro. | 1089845 pp.31 |
| SELLER 3 | 63.572.282/0001-11 | Derivativos |  | Operações com derivativos vedadas |  | direto agregado | MERC_DERIVATIVO / PL ou posições em derivativos | IME só mostra posição agregada; se houver valor, precisa análise do tipo/contraparte, mas para vedação total o alerta é útil. | 1089845 pp.58 |
| SELLER 3 | 63.572.282/0001-11 | Reserva de Liquidez |  | Mínimo equivalente a 3 meses de despesas ordinárias |  | parcial | Disponibilidades e Ativos Financeiros; despesas ordinárias precisam input/manual | IME não traz uma linha padronizada de '3 meses de despesas ordinárias' para o cálculo contratual. | 1089845 pp.51,103 |
| SELLER 3 | 63.572.282/0001-11 | Reserva de Caixa |  | 100% do próximo pagamento de amortização/remuneração até D-10; acumula desde D-45 |  | parcial | Disponibilidades/Ativos Financeiros vs próximo serviço da dívida | Depende do cronograma de cotas, saldo vivo e remuneração acumulada; IME ajuda, mas não resolve sozinho. | 1089845 pp.51,103-104 |
| SELLER 3 | 63.572.282/0001-11 | Inadimplemento de Direitos Creditórios |  | Default de qualquer Direito Creditório por >5 dias pode ser evento de liquidação |  | parcial fraco | Over 1d / Crédito como proxy mensal | A regra é diária e por título; IME mensal por bucket não comprova o evento jurídico. | 1089845 pp.114-115 |
| SELLER 3 | 63.572.282/0001-11 | Inconsistência de verificação de lastro |  | >5% da amostra / PL conforme cláusula |  | não usar via IME | Sem métrica IME confiável | Depende de auditoria de documentos comprobatórios, não de Informe Mensal. | 1089845 pp.107,112 |
| SELLER II | 55.471.753/0001-77 | Índice de Subordinação |  | Cotas Subordinadas Juniores / PL >= 33,3% |  | direto com validação | Cotas Subordinadas Juniores / PL; no app, Cotas Sub / PL se não houver mezanino | A extração heurística anterior lia '3,3%'; a página 106 mostra claramente 33,3%. | 704724 pp.106-107 |
| SELLER II | 55.471.753/0001-77 | Índice de Cobertura / Liquidez para novas emissões |  | Índice de Cobertura e Índice de Liquidez >= 1,00 |  | parcial | Proxy com DC, disponibilidades e cotas; fatores manuais | Exige Valor Presente, Comissões e fatores. Fator Sênior da 1ª série = 66,70% no aditivo de 26/07/2024. | 704724 p.104; 705139 p.5 |
| SELLER II | 55.471.753/0001-77 | Alocação mínima regulatória |  | Direitos Creditórios Elegíveis / PL >= 50% após 180 dias |  | direto com ressalva | Dir Cred / PL | IME não valida elegibilidade individual. | 704724 p.61 |
| SELLER II | 55.471.753/0001-77 | Alocação mínima adicional tributária |  | Direitos Creditórios Elegíveis / PL >= 67% |  | direto com ressalva | Dir Cred / PL | O texto extraído também traz inconsistência redacional: '67%' com extenso 'cinquenta por cento'. | 704724 p.61 |
| SELLER II | 55.471.753/0001-77 | PL mínimo operacional |  | PL diário não inferior a R$ 1.000.000 por 90 dias consecutivos |  | direto com ressalva | PL | IME é mensal; não observa 90 dias diários, mas identifica risco evidente. | 704724 p.61 |
| SELLER II | 55.471.753/0001-77 | Derivativos |  | Operações com derivativos vedadas |  | direto agregado | MERC_DERIVATIVO / PL | IME só mostra posição agregada. | 704724 p.61 |
| SELLER II | 55.471.753/0001-77 | Reserva de Liquidez |  | Mínimo equivalente a 3 meses de despesas ordinárias |  | parcial | Disponibilidades; despesas ordinárias precisam input/manual | IME não traz o cálculo contratual completo. | 704724 pp.110-111 |
| SELLER II | 55.471.753/0001-77 | Reserva de Caixa |  | Principal: 100% até D-10, acumula desde D-45; Remuneração: 100% até D-5, acumula desde D-10 |  | parcial | Disponibilidades/Ativos Financeiros vs próximo pagamento | Precisa calendário e saldo vivo; o calendário da sênior 1ª série foi extraído. | 704724 p.111; 705139 p.4 |
| MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA | 33.254.370/0001-04 | Subordinação mínima | subordination_ratio_min | 7% |  | monitoravel | Cotas Sub / PL %, Cotas MZ / PL % e Cotas SR / PL % | O Informe Mensal traz PL e classes/cotas; a subordinação pode ser recalculada por classe quando as cotas reconciliam. \| Extração local heurística; validar manualmente antes de at… | 1128340_regulamento_regulamento_1128340_2026-03-03.pdf · ID 1128340 · 03/03/2026 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | Subordinação mínima | subordination_ratio_min | 7% |  | monitoravel | Cotas Sub / PL %, Cotas MZ / PL % e Cotas SR / PL % | O Informe Mensal traz PL e classes/cotas; a subordinação pode ser recalculada por classe quando as cotas reconciliam. \| Extração local heurística; validar manualmente antes de at… | 1019776_regulamento_regulamento_1019776_2025-10-20.pdf · ID 1019776 · 20/10/2025 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | Alocação mínima em direitos creditórios | credit_rights_allocation_min | 50% |  | monitoravel | Dir Cred / PL | O Informe Mensal traz direitos creditórios e PL. \| Extração local heurística; validar manualmente antes de ativar alerta. \| ca o Mercado Pago, contratado para prestação de servi… | 1019776_regulamento_regulamento_1019776_2025-10-20.pdf · ID 1019776 · 20/10/2025 |
| MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA | 37.511.828/0001-14 | Atraso/Inadimplência - evento de avaliação | default_rate_evaluation_event | 8% |  | monitoravel | Vencidos Over 30/60/90/180/360 d / Crédito | Os buckets de atraso do Informe Mensal permitem recompor NPL Over acumulado por faixa. \| Extração local heurística; validar manualmente antes de ativar alerta. \| Sênior no mês c… | 1019776_regulamento_regulamento_1019776_2025-10-20.pdf · ID 1019776 · 20/10/2025 |
| MERCADO CRÉDITO II BRASIL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA | 41.970.012/0001-26 | Subordinação mínima | subordination_ratio_min | 10% |  | monitoravel | Cotas Sub / PL %, Cotas MZ / PL % e Cotas SR / PL % | O Informe Mensal traz PL e classes/cotas; a subordinação pode ser recalculada por classe quando as cotas reconciliam. \| Extração local heurística; validar manualmente antes de at… | 1077334_regulamento_regulamento_1077334_2025-12-19.pdf · ID 1077334 · 19/12/2025 |
| SELLER | 50.473.039/0001-02 | Índice de Subordinação |  | Cotas Subordinadas Juniores / PL >= 10% |  | direto com validação | Cotas Subordinadas Juniores / PL; no app, Cotas Sub / PL se não houver mezanino | Usar junior/PL, não subordinação total incluindo mezanino. IME precisa reconciliar classes de cotas. | 909547 pp.99,107-108 |
| SELLER | 50.473.039/0001-02 | Índice de Cobertura Sênior |  | Índice >= 1,00 |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Sênior) / Cotas Seniores | IME traz DC, caixa e cotas, mas não traz de forma padronizada Valor Presente pelo contrato, Comissões e fatores por série; exige parâmetros manuais. | 909547 pp.46,61,110 |
| SELLER | 50.473.039/0001-02 | Índice de Cobertura Mezanino |  | Índice >= 1,00 quando houver mezanino |  | parcial | ((VP Direitos Creditórios + Disponibilidades + Comissões) * Fator Mezanino) / (Sênior + Mezanino) | Mesma limitação do Índice de Cobertura Sênior; só aplicar se houver cota mezanino emitida. | 909547 pp.46,61,110 |
| SELLER | 50.473.039/0001-02 | Alocação mínima regulatória |  | Direitos Creditórios Elegíveis / PL >= 50% após 180 dias |  | direto com ressalva | Dir Cred / PL | IME vê direitos creditórios agregados, mas não valida elegibilidade individual. Usar como monitoramento de enquadramento econômico, não prova jurídica final. | 909547 pp.58,115 |
| SELLER | 50.473.039/0001-02 | Alocação mínima tributária |  | Direitos Creditórios Elegíveis / PL >= 67% |  | direto com ressalva | Dir Cred / PL | O texto extraído mostra inconsistência redacional: '67%' com extenso 'cinquenta por cento'. Validar juridicamente antes de alerta duro. | 909547 pp.31 |
| SELLER | 50.473.039/0001-02 | Derivativos |  | Operações com derivativos vedadas |  | direto agregado | MERC_DERIVATIVO / PL ou posições em derivativos | IME só mostra posição agregada; se houver valor, precisa análise do tipo/contraparte, mas para vedação total o alerta é útil. | 909547 pp.58 |
| SELLER | 50.473.039/0001-02 | Reserva de Liquidez |  | Mínimo equivalente a 3 meses de despesas ordinárias |  | parcial | Disponibilidades e Ativos Financeiros; despesas ordinárias precisam input/manual | IME não traz uma linha padronizada de '3 meses de despesas ordinárias' para o cálculo contratual. | 909547 pp.51,103 |

_Exibindo 40 de 1019 linhas. Ver CSV para a tabela completa._

## 10. Timeline histórica consolidada

| grupo | nome_curto | cnpj | data_referencia | evento | documento_id | arquivo_local_existe |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 23/10/2020 | Relatório de rating | 157108 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/11/2020 11:00 | Assembleia / deliberação | 135822 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 16/11/2020 | Regulamento / alteração regulatória | 135821 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2020 | Informe trimestral | 146340 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | Relatório de rating | 146344 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | Demonstrações financeiras | 166929 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 15/02/2021 | Relatório de rating | 157110 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | Informe trimestral | 173096 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | Informe trimestral | 173101 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2021 | Relatório de rating | 173098 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | Informe trimestral | 205041 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | Informe trimestral | 208366 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2021 | Relatório de rating | 205027 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2021 | Informe trimestral | 235040 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | Relatório de rating | 235044 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | Relatório de rating | 235878 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | Informe trimestral | 270880 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | Informe trimestral | 321401 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2021 | Demonstrações financeiras | 510926 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | Informe trimestral | 304904 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | Informe trimestral | 373768 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | Informe trimestral | 340650 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | Informe trimestral | 373901 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | Informe trimestral | 376748 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | Informe trimestral | 410062 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2022 | Informe trimestral | 415493 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/12/2022 | Relatório de rating | 410762 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2022 | Demonstrações financeiras | 565264 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2023 | Informe trimestral | 454622 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2023 | Relatório de rating | 457230 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 13/04/2023 18:00 | Assembleia / deliberação | 444985 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 14/04/2023 23:59 | Assembleia / deliberação | 436942 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | Regulamento / alteração regulatória | 448299 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 19/04/2023 | Comunicação / evento | 448302 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2023 | Informe trimestral | 507575 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2023 | Relatório de rating | 499533 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2023 | Informe trimestral | 552045 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 23/09/2023 23:59 | Assembleia / deliberação | 517767 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 24/09/2023 23:59 | Assembleia / deliberação | 528403 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2023 | Informe trimestral | 607588 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 18/12/2023 23:59 | Assembleia / deliberação | 566552 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 18/12/2023 23:59 | Assembleia / deliberação | 572987 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | Relatório de rating | 607607 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | Demonstrações financeiras | 643226 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2024 | Informe trimestral | 653128 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/03/2024 | Relatório de rating | 664505 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2024 | Informe trimestral | 714174 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 15/06/2024 23:59 | Assembleia / deliberação | 674485 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 17/06/2024 10:00 | Assembleia / deliberação | 681860 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/06/2024 | Relatório de rating | 709466 | False |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 10:00 | Assembleia / deliberação | 732139 | True |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/09/2024 | Regulamento / alteração regulatória | 732140 | True |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 12/2020 | Informe trimestral | 149747 | False |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 31/12/2020 | Demonstrações financeiras | 259351 | False |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/2021 | Informe trimestral | 180899 | False |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 06/2021 | Informe trimestral | 206633 | False |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 09:00 | Assembleia / deliberação | 196309 | True |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 15/07/2021 | Regulamento / alteração regulatória | 206963 | True |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/07/2021 | Regulamento / alteração regulatória | 201177 | True |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | Outro documento CVM | 207363 | False |

_Exibindo 60 de 360 linhas. Ver CSV para a tabela completa._

## Comparativo Sellers vs Mercado Crédito

- **Sellers:** 44 PDFs locais analisáveis, 38 documentos inventariados sem PDF local, 288 linhas de critérios/monitorabilidade e 68 linhas de emissões/cronogramas nas curadorias locais.
- **Mercado Crédito:** 123 PDFs locais analisáveis, 155 documentos inventariados sem PDF local, 731 linhas de critérios/monitorabilidade e 119 linhas de emissões/cronogramas nas curadorias locais.
- **Agressividade estrutural:** Sellers tende a explicitar subordinação júnior mínima e índices de cobertura por série; Mercado Crédito apresenta maior customização por veículo/série e maior volume de alterações regulatórias/assembleares.
- **Monitorabilidade:** para ambos, PL, direitos creditórios, atraso por buckets, PDD, cotas e rentabilidade podem ser acompanhados via IME. Índices que dependem de valor presente, fatores de ponderação, reservas ou contratos subjacentes exigem parametrização manual.
- **Transparência documental local:** Mercado Crédito tem mais documentos locais baixados, mas também maior quantidade de documentos relevantes apenas inventariados. Sellers tem curadoria manual mais completa dos suplementos centrais já existente no repositório.
- **Risco operacional de automação:** a diversidade de definições contratuais impede criar gatilhos genéricos sem versionamento por fundo, data de vigência e fonte documental.

## Lacunas e conflitos identificados

Há documentos inventariados sem arquivo local, sobretudo relatórios de rating, informes trimestrais e demonstrações financeiras. Esses documentos não foram interpretados nesta rodada; a ausência não deve ser lida como ausência de evento econômico/jurídico.

| grupo | nome_curto | cnpj | data_referencia | categoria | tipo_documento | documento_id |
| --- | --- | --- | --- | --- | --- | --- |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 23/10/2020 | outro | Relatório de Agência de Rating | 157108 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2020 | outro | Informe Trimestral | 146340 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | outro | Relatório de Agência de Rating | 146344 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2020 | outro | Demonstrações Financeiras | 166929 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 15/02/2021 | outro | Relatório de Agência de Rating | 157110 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | outro | Informe Trimestral | 173096 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2021 | outro | Informe Trimestral | 173101 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2021 | outro | Relatório de Agência de Rating | 173098 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | outro | Informe Trimestral | 205041 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2021 | outro | Informe Trimestral | 208366 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2021 | outro | Relatório de Agência de Rating | 205027 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2021 | outro | Informe Trimestral | 235040 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | outro | Relatório de Agência de Rating | 235044 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/09/2021 | outro | Relatório de Agência de Rating | 235878 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | outro | Informe Trimestral | 270880 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2021 | outro | Informe Trimestral | 321401 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2021 | outro | Demonstrações Financeiras | 510926 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | outro | Informe Trimestral | 304904 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2022 | outro | Informe Trimestral | 373768 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | outro | Informe Trimestral | 340650 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2022 | outro | Informe Trimestral | 373901 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | outro | Informe Trimestral | 376748 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2022 | outro | Informe Trimestral | 410062 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2022 | outro | Informe Trimestral | 415493 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/12/2022 | outro | Relatório de Agência de Rating | 410762 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2022 | outro | Demonstrações Financeiras | 565264 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2023 | outro | Informe Trimestral | 454622 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/03/2023 | outro | Relatório de Agência de Rating | 457230 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2023 | outro | Informe Trimestral | 507575 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 30/06/2023 | outro | Relatório de Agência de Rating | 499533 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 09/2023 | outro | Informe Trimestral | 552045 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 12/2023 | outro | Informe Trimestral | 607588 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | outro | Relatório de Agência de Rating | 607607 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 31/12/2023 | outro | Demonstrações Financeiras | 643226 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 03/2024 | outro | Informe Trimestral | 653128 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/03/2024 | outro | Relatório de Agência de Rating | 664505 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 06/2024 | outro | Informe Trimestral | 714174 |
| Mercado Crédito | Mercado Crédito Merchant FIDC | 28.472.333/0001-32 | 28/06/2024 | outro | Relatório de Agência de Rating | 709466 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 12/2020 | outro | Informe Trimestral | 149747 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 31/12/2020 | outro | Demonstrações Financeiras | 259351 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 03/2021 | outro | Informe Trimestral | 180899 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 06/2021 | outro | Informe Trimestral | 206633 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 13/08/2021 | outro | Outros Documentos | 207363 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 09/2021 | outro | Informe Trimestral | 236959 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 09/2021 | outro | Informe Trimestral | 265200 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/09/2021 | outro | Outros Documentos | 237022 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 30/09/2021 | outro | Relatório de Agência de Rating | 239154 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 12/2021 | outro | Informe Trimestral | 269524 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 31/12/2021 | outro | Relatório de Agência de Rating | 269349 |
| Mercado Crédito | Mercado Crédito FIDC | 33.254.370/0001-04 | 31/12/2021 | outro | Demonstrações Financeiras | 474003 |

_Exibindo 50 de 193 linhas. Ver CSV para a tabela completa._

## Observação de auditoria

Este relatório não substitui leitura jurídica final dos documentos-fonte. Ele organiza evidências documentais locais e aponta onde cada conclusão pode ser verificada. Trechos longos e todos os hits por página estão nos CSVs de evidência; o Markdown mostra apenas amostras para legibilidade.
