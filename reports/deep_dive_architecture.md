# Deep Dive - arquitetura e prompt operacional

## Objetivo

A aba `Deep Dive` consome pacotes offline já curados e versionados no repositório. Ela não baixa dados, não consulta CVM e não executa LLM no Streamlit. O fluxo esperado é:

1. extração/curadoria offline via terminal;
2. geração de tabelas auditáveis em CSV;
3. empacotamento em `data/deep_dives/<deep_dive_id>/`;
4. commit/push do pacote;
5. renderização no app e exportação PPTX editável.

## Referência visual

O padrão é research institucional: fundo branco, tabela como elemento central, cabeçalho escuro, tipografia Calibri/sem serifa, uso restrito de laranja para destaque e rodapé técnico discreto. A estética vem de alinhamento, densidade controlada e rastreabilidade, não de ornamento.

## Estrutura de pacote

Cada pacote deve conter:

- `manifest.json`: metadados, fundos, tabelas, fonte, confidencialidade e warnings.
- `tables/*.csv`: matrizes ou tabelas fonte com dados já formatados para apresentação.
- `evidence/*.csv`: evidências documentais ou inventários de suporte.
- `notes/*.md`: relatório narrativo ou memória de curadoria.

O app lista todos os pacotes encontrados em `data/deep_dives/*/manifest.json`.

## Componentes implementados

- `services/deep_dive_models.py`: dataclasses do manifesto e tabelas.
- `services/deep_dive_store.py`: descoberta, leitura e filtro por carteira.
- `services/deep_dive_ppt_export.py`: exportação PPTX editável com tabelas reais.
- `tabs/tab_deep_dive.py`: UI Streamlit minimalista para seleção, visualização e exportação.
- `scripts/build_deep_dive_package.py`: empacotador do estudo Sellers vs Mercado Crédito.

## Contrato verificado em 2026-05-28

A curadoria de novos fundos precisa reproduzir o contrato real já consumido pela aba e pela aba de Monitoramento, não apenas gerar um relatório narrativo.

### Pacote Deep Dive

O manifesto padrão aponta para quatro tabelas mínimas:

- `comparison_main`: matriz primeira coluna `Nome`, demais colunas = fundos.
- `structural_costs`: tabela fonte de administração/gestão.
- `emissions`: cronograma de emissões.
- `thresholds`: regulamento mais recente e critérios monitoráveis.

Tabelas adicionais podem existir quando a diligência pedir: `key_findings`, `cedentes_sacados_origem`, `source_vehicle_trace`, `document_inventory`, `fundonet_document_inventory`.

### Linhas obrigatórias do comparativo

Todos os pacotes atuais usam as mesmas 31 linhas em `comparison_main.csv`:

1. Grupo
2. CNPJ
3. Páginas locais analisadas
4. Última competência IME
5. PL (R$ mm)
6. Direitos creditórios / PL
7. Vencidos Over 30d / crédito
8. Vencidos Over 60d / crédito
9. Vencidos Over 90d / crédito
10. Vencidos Over 180d / crédito
11. Vencidos Over 360d / crédito
12. PDD / crédito
13. PDD / vencidos
14. Cotas sênior / PL
15. Cotas mezanino / PL
16. Cotas subordinadas / PL
17. Séries/classes emitidas identificadas
18. Volume emitido identificado (R$ mm)
19. Primeira emissão identificada
20. Última emissão identificada
21. Emissões detectadas (data, classe, preço e volume)
22. Remuneração-alvo por emissão detectada
23. Amortização/vencimento por emissão detectada
24. Regulamento-base dos thresholds
25. Alocação mínima em DCs
26. Subordinação mínima
27. Evento de avaliação por atraso
28. Liquidação/vencimento por atraso
29. Cobertura mínima PDD
30. Reserva/caixa mínimo
31. Hedges permitidos

### Emissões e pagamentos

`tables/emissions.csv` deve ter: `Fundo`, `CNPJ`, `Data`, `Classe/Série`, `Tipo`, `Qtd cotas`, `Preço/VNU`, `Volume identificado (R$ mm)`, `Remuneração-alvo`, `Amortização/vencimento`, `Fonte`.

O perfil curado em `data/regulatory_profiles/<slug>_cotas_emissoes_pagamentos.csv` deve preservar a granularidade de due diligence: data de deliberação, emissão/primeira integralização, encerramento/oferta, quantidade, volume, VNU, remuneração, juros, amortização principal, status/evidência e fonte.

### Critérios monitoráveis e qualitativos

`data/regulatory_profiles/<slug>_criteria_monitoraveis_ime.csv` deve ter: `Fundo`, `CNPJ`, `Critério`, `Chave`, `Limite/regra`, `Monitorabilidade IME`, `Métrica IME / proxy`, `Condição de alerta sugerida`, `Observação técnica`, `Fonte`, `Status curadoria`.

Chaves já usadas incluem: `credit_rights_allocation_min`, `subordination_ratio_min`, `default_rate_evaluation_event`, `default_rate_early_maturity`, `pdd_coverage_min`, `minimum_cash_ratio`, `permitted_hedges`, `concentration_limits`, `eligibility_criteria`, `repurchase_indemnity`, `credit_rights_tax_allocation`, `cash_sweep_amortization`, `servicer_identification`, `source_vehicle_trace`.

A diligência deve cobrir critérios de elegibilidade, cessão, recompra/substituição/indenização, concentração, derivativos, reservas, eventos de avaliação/liquidação, vencimento antecipado, chargeback/cancelamento, cross default, troca de gestor/administrador/prestadores e waivers.

### Monitoramento e IME

A aba Deep Dive atualiza ao vivo as linhas de IME quando existem no comparativo: competência, PL, Dir Cred / PL, Over 30/60/90/180/360, PDD, PDD / vencidos e composição de cotas por PL.

A aba Monitoramento avalia proxies via `build_monitoring_tables`: Dir Cred / PL, Over 30/60/90/180/360, PDD / Crédito, PDD / Venc Total, Recompras / Crédito, Cotas SR/MZ/Sub / PL, PL, caixa/disponibilidades e derivativos agregados. O resultado operacional deve distinguir OK, Alerta, Sem dado, Referência e Qualitativo.

### Prompt operacional

O prompt copy-paste canônico está em `docs/fidc/monitoramento/prompt_deep_dive_nova_carteira.md` e é lido pela aba Deep Dive no expander "Prompt para atualizar Deep Dives". Ele exige que o agente atue como advogado de mercado de capitais, estruturador de renda fixa e engenheiro Python, lendo a documentação completa antes de preencher as tabelas.

## Critérios de validação

- o pacote aparece na aba `Deep Dive`;
- a tabela mantém cabeçalho e colunas alinhados;
- campos ausentes aparecem como `—`;
- o PPTX abre sem erro e usa tabelas editáveis;
- nenhuma rotina do app busca dados externos para renderizar o Deep Dive.
