# Prompt operacional - Deep Dive regulatório de carteira nova

Use este prompt quando uma nova carteira já tiver sido cadastrada no `portfolios.json` e você precisar que o Mac local faça a leitura parruda dos documentos CVM/Fundos.NET, gere conhecimento regulatório por CNPJ e atualize a ferramenta Streamlit.

Copie a partir da linha abaixo.

---

Você é Codex trabalhando no repositório local `/Users/matheusjprates/fidc`.

## Objetivo

Fazer o Deep Dive regulatório completo de UMA CARTEIRA JÁ EXISTENTE no `portfolios.json`, usando todos os CNPJs associados a essa carteira, e atualizar os dados que alimentam a ferramenta Streamlit:

- aba de Monitoramento/Base regulatória;
- seção `Monitoramento IME`;
- seção `Emissões e calendário de pagamentos`;
- seção `Critérios monitoráveis e qualitativos`;
- seção `Timeline documental CVM`;
- aba `Deep Dive`;
- perfis curados em `data/regulatory_profiles`;
- conhecimento regulatório por fundo em `data/regulatory_knowledge`;
- pacote `data/deep_dives/<deep_dive_id>/`.

Atue simultaneamente como:

- advogado de mercado de capitais;
- estruturador de renda fixa/FIDC;
- analista de crédito estruturado;
- engenheiro Python responsável por preservar o contrato da aplicação.

Leia documentos integralmente quando necessário, reconstrua termos econômicos, traduza regras jurídicas em dados auditáveis e deixe explícito o que é monitorável, parcialmente monitorável ou não monitorável pelo Informe Mensal Estruturado (IME).

## Inputs

Carteira alvo:

```text
[NOME_OU_ID_DA_CARTEIRA_EXISTENTE]
```

Período/competência IME de referência, se aplicável:

```text
[PERIODO_OU_COMPETENCIA]
```

## Regras inegociáveis de escopo

1. Use somente uma carteira já existente no `portfolios.json`.
2. Não crie carteira auxiliar, carteira operacional, carteira consolidada temporária persistente, nem novo registro em `portfolios.json`.
3. Não adicione nem remova fundos da carteira.
4. Processe todos os CNPJs que já estiverem associados à carteira.
5. Se algum CNPJ da carteira não tiver documentos no Fundos.NET/CVM, mantenha o CNPJ na análise e registre lacuna explícita.
6. Se o nome comercial do fundo for ambíguo, use o CNPJ da carteira como fonte de verdade.
7. Não substitua um fundo por aproximação de nome. Exemplo: não trocar `Automax` por `Automotivo` sem CNPJ inequívoco fornecido pelo usuário ou pela carteira.
8. Não faça batch em todas as carteiras.
9. Não regenere pacotes de carteiras não solicitadas.
10. Preserve mudanças alheias no working tree. Nunca reverta arquivos que você não alterou.
11. Use internet/API apenas para CVM/Fundos.NET ou fonte pública indispensável para resolver documento do próprio CNPJ. Não use inferência fraca para preencher dado material.
12. Lacunas devem aparecer como texto, nunca como zero, vazio, média, extrapolação ou suposição.

## Primeiro bloco de trabalho: confirmar escopo

Antes de baixar, extrair ou editar qualquer coisa:

1. Rode `git status --short`.
2. Leia `portfolios.json`.
3. Localize exatamente uma carteira pelo nome ou ID informado.
4. Liste no seu raciocínio operacional:
   - ID da carteira;
   - nome da carteira;
   - todos os CNPJs;
   - display names;
   - assinatura da carteira via `portfolio_basket_signature`.
5. Verifique se já existe pacote Deep Dive compatível com essa carteira usando `services.deep_dive_store.list_deep_dives()` e `deep_dive_matches_portfolio`.
6. Verifique, para cada CNPJ:
   - `data/regulatory_knowledge/<cnpj>.json`;
   - `load_regulatory_profile(cnpj)`;
   - PDFs locais em `data/raw/<cnpj>/`;
   - extrações em `data/regulatory_extractions/<cnpj>/`;
   - caches IME locais.
7. Se a carteira não existir, pare e peça o nome/ID correto. Não crie uma carteira para contornar isso.

## Download e inventário documental

Para cada CNPJ da carteira:

1. Consultar Fundos.NET/CVM pelo CNPJ.
2. Inventariar todos os documentos, inclusive:
   - regulamentos;
   - instrumentos de alteração de regulamento;
   - instrumentos de constituição/encerramento;
   - instrumentos de emissão de cotas;
   - anúncios de início e encerramento de oferta;
   - atas de assembleia;
   - fatos relevantes/eventos;
   - informes mensais;
   - informes trimestrais;
   - demonstrações financeiras;
   - relatórios de rating;
   - outros relatórios relevantes.
3. Baixar PDFs regulatórios relevantes para `data/raw/<cnpj>/`.
4. Extrair texto localmente com `pypdf`/`pdfplumber`.
5. Quando PDF não tiver texto extraível, registrar `PDF sem texto extraível / OCR necessário`.
6. Manter contagem de:
   - documentos inventariados;
   - PDFs baixados;
   - páginas locais analisáveis;
   - documentos sem PDF local;
   - documentos com erro de extração.

Comando base esperado, adaptando apenas o config temporário da carteira:

```bash
./.venv/bin/python scripts/build_regulatory_knowledge.py \
  --config tmp/<portfolio_id>_funds.yaml \
  --extractor local \
  --max-pages 350 \
  --force
```

O arquivo `tmp/<portfolio_id>_funds.yaml` deve ser temporário e não deve ser entregue como artefato permanente, salvo se o usuário pedir.

## Due diligence regulatória obrigatória

Para cada fundo/CNPJ, extraia e qualifique:

1. Regulamento vigente e versões anteriores relevantes.
2. Política de investimento.
3. Ativos permitidos.
4. Ativos vedados.
5. Público-alvo.
6. Prazo de duração.
7. Classes e subclasses de cotas.
8. Prioridade de pagamentos/waterfall.
9. Critérios de elegibilidade dos direitos creditórios.
10. Condições de cessão.
11. Condições de recompra.
12. Substituição de direitos creditórios.
13. Indenização.
14. Coobrigação.
15. Vícios de lastro.
16. Limites de concentração por cedente.
17. Limites por sacado/devedor.
18. Limites por grupo econômico.
19. Limites por originador/endossante.
20. Limites por tipo de ativo.
21. Limites por partes relacionadas.
22. Derivativos/hedge permitidos, limites e finalidade.
23. Subordinação mínima.
24. Relação mínima/razão de garantia.
25. Índice de cobertura.
26. Reservas.
27. Caixa mínimo.
28. Cash sweep.
29. Eventos de avaliação.
30. Eventos de liquidação.
31. Vencimento antecipado.
32. Aceleração ou amortização extraordinária.
33. Waivers.
34. Gatilhos de atraso/inadimplência.
35. Gatilhos de PDD/provisão.
36. Recompras.
37. Diluição.
38. Chargeback.
39. Cancelamento.
40. Fraude.
41. Pré-pagamento.
42. Contestação.
43. Cross default/cross acceleration do cedente/originador/endossante/grupo econômico.
44. Troca, renúncia ou substituição de gestor.
45. Troca, renúncia ou substituição de administrador.
46. Troca de custodiante.
47. Troca de agente de cobrança/recebimento.
48. Troca de escriturador.
49. Troca de servicer/prestadores essenciais.
50. Rating e agência, quando houver.
51. Taxas de administração, gestão, custódia e demais prestadores.
52. Alterações materiais entre versões documentais.

Toda conclusão material precisa ter fonte:

- arquivo;
- ID CVM/Fundos.NET;
- data de referência;
- tipo de documento;
- página/seção/cláusula quando disponível;
- trecho curto auditável quando necessário.

## Emissões e calendário de pagamentos

Para cada emissão, classe, série ou subclasse, reconstrua:

1. Fundo.
2. CNPJ.
3. Classe/série.
4. Tipo de cota.
5. Data de deliberação.
6. Data de emissão ou primeira integralização.
7. Data de início da oferta.
8. Data de encerramento da oferta.
9. Quantidade aprovada/ofertada/distribuída.
10. VNU/preço unitário.
11. Volume máximo/aprovado/distribuído.
12. Remuneração-alvo.
13. Benchmark.
14. Spread aditivo.
15. Taxa DI/CDI + spread.
16. IPCA + spread.
17. Taxa fixa.
18. Fator adicional.
19. Juros.
20. Periodicidade de juros.
21. Carência.
22. Prazo.
23. Vencimento final.
24. Amortização programada.
25. Amortização extraordinária.
26. Datas de pagamento.
27. Rating vinculado à série, quando houver.
28. Fonte documental.
29. Status de curadoria.

Regra crítica para spreads:

- Se o texto vier como `CDI`, `DI`, `Taxa DI` ou equivalente, normalize como índice + spread aditivo percentual quando o documento permitir.
- Exemplos: `DI + 5,50% a.a.`, `CDI + 7,00% a.a.`, `Taxa DI + 2,20% a.a.`.
- Se a taxa final depender de bookbuilding, suplemento ou ato não localizado, escreva explicitamente:
  - `spread final não localizado`;
  - `sobretaxa definida em bookbuilding`;
  - `sobretaxa definida em ato não localizado`;
  - `sobretaxa definida em suplemento não localizado`;
  - `prazo remetido ao suplemento`;
  - `cronograma fechado não identificado`.

Não deixe remuneração vazia quando a lacuna puder ser descrita.

## Critérios monitoráveis e qualitativos

Monte uma linha por critério material, mesmo que não seja monitorável pelo IME.

Campos obrigatórios:

- `Fundo`
- `CNPJ`
- `Critério`
- `Chave`
- `Limite/regra`
- `Monitorabilidade IME`
- `Métrica IME / proxy`
- `Condição de alerta sugerida`
- `Observação técnica`
- `Fonte`
- `Status curadoria`

Chaves canônicas esperadas, quando aplicáveis:

- `credit_rights_allocation_min`
- `subordination_ratio_min`
- `default_rate_evaluation_event`
- `default_rate_early_maturity`
- `pdd_coverage_min`
- `minimum_cash_ratio`
- `permitted_hedges`
- `concentration_limits`
- `eligibility_criteria`
- `eligibility_criteria_text`
- `repurchase_indemnity`
- `recompras_max`
- `cancellation_rate_max`
- `chargeback_rate_max`
- `cross_default_seller_event`
- `service_provider_replacement_event`
- `credit_rights_tax_allocation`
- `day_trade_ban`
- `minimum_net_worth`
- `cash_sweep_amortization`
- `invested_fund_exposure`
- `servicer_identification`
- `source_vehicle_trace`
- `cnpj_resolution`
- `originator_debtor_granularity`

Classificação de monitorabilidade:

- `monitoravel`: dá para calcular diretamente com métrica IME padronizada.
- `monitoravel com ressalva`: dá para calcular, mas há diferença conceitual relevante.
- `direto com validação`: cálculo direto, mas exige validação de campo/fonte.
- `direto com ressalva`: cálculo direto com restrição documental.
- `direto agregado`: cálculo só em nível agregado.
- `parcial`: o IME ajuda como proxy, mas não replica a regra jurídica.
- `parcial fraco`: proxy distante; útil apenas como alerta preliminar.
- `nao_monitoravel`: IME não possui granularidade ou evento necessário.
- `não usar via IME`: risco de falso conforto; controle deve ser manual/documental.

Regras de julgamento:

- Concentração por sacado, cedente, devedor, endossante ou grupo econômico normalmente é `nao_monitoravel` no IME público se não houver granularidade.
- Derivativos normalmente são `parcial`, porque o IME pode trazer posição agregada, mas não valida finalidade/elegibilidade contratual.
- Reserva/caixa é `parcial` se depender de cronograma de amortização, despesas futuras ou waterfall.
- Recompra pode ser `parcial` via `Recompras / Crédito`, mas não valida motivo jurídico, vício de lastro ou obrigação de indenização.
- Chargeback/cancelamento geralmente é `parcial` ou `nao_monitoravel`, salvo se houver campo/proxy robusto.
- Cross default e troca de prestadores são eventos documentais; em regra `nao_monitoravel`.
- Elegibilidade textual é `nao_monitoravel` ou `parcial fraco`, salvo se a regra for traduzível em métrica IME.

## Monitoramento IME

Use os helpers existentes:

- `build_dashboard_data`;
- `build_monitoring_tables`;
- `read_wide_csv`;
- `load_or_extract_informe`;
- `peek_cached_informe`;
- funções de `tabs/tab_fidc_monitoring.py`.

Métricas padronizadas que podem alimentar proxies:

- PL;
- Direitos creditórios;
- Direitos creditórios / PL;
- Over 30/60/90/180/360 / crédito;
- PDD / Crédito;
- PDD / Venc Total;
- Recompras / Crédito;
- Cotas sênior / PL;
- Cotas mezanino / PL;
- Cotas subordinadas / PL;
- disponibilidades/caixa;
- derivativos agregados.

Separe claramente:

- dado documental offline;
- dado IME ao vivo;
- proxy direto;
- proxy parcial;
- lacuna sem proxy;
- divergência;
- limitação metodológica.

Se o IME não estiver em cache para o período, preserve a due diligence documental e registre `sem competência IME carregada`.

## Custos estruturais

Extraia e normalize, por fundo:

- Administração;
- Gestão;
- Custódia, se disponível;
- Escrituração/controladoria, se disponível;
- mínimo mensal;
- percentual a.a.;
- base de cálculo;
- faixas por PL;
- reajuste/indexador;
- serviços incluídos;
- mudanças entre versões;
- fonte documental.

`structural_costs.csv` deve ter, no mínimo:

- `Fundo`
- `CNPJ`
- `Item`
- `Percentual a.a.`
- `Mínimo mensal`
- `Fonte`
- `Versão vigente / base documental`
- `Mudanças relevantes`
- `Status curadoria`

Sempre deve haver linha de Administração e Gestão por fundo, ainda que como lacuna explícita.

## Persistência esperada

Atualize apenas artefatos necessários para a carteira existente e para os CNPJs dela:

- `data/regulatory_knowledge/<cnpj>.json`
- `data/regulatory_profiles/all_fidcs_cotas_emissoes_pagamentos.csv`
- `data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv`
- `data/regulatory_profiles/structural_costs.csv`, se aplicável
- `reports/regulatory_document_inventory.csv`
- `reports/regulatory_criteria_matrix.csv`
- `reports/regulatory_emissions_timeline.csv`
- `reports/all_fidcs_regulatory_curation_status.csv`
- `data/deep_dives/<deep_dive_id>/manifest.json`
- `data/deep_dives/<deep_dive_id>/tables/comparison_main.csv`
- `data/deep_dives/<deep_dive_id>/tables/emissions.csv`
- `data/deep_dives/<deep_dive_id>/tables/thresholds.csv`
- `data/deep_dives/<deep_dive_id>/tables/structural_costs.csv`
- `data/deep_dives/<deep_dive_id>/evidence/*.csv`
- `data/deep_dives/index.json`

Não persista:

- config temporário em `config/` só para rodar a carteira;
- carteira nova em `portfolios.json`;
- pacote consolidado que não corresponda à carteira existente;
- relatórios temporários de tentativa/resolução, salvo se forem explicitamente pedidos;
- PDFs soltos fora de `data/raw/<cnpj>/`;
- alterações em carteiras não relacionadas.

Se `portfolios.json` tiver diff e o usuário não pediu alteração de carteira, reverta apenas a sua alteração nesse arquivo, preservando mudanças alheias.

## Comandos esperados

Use estes comandos como base, ajustando somente o ID/nome da carteira e o config temporário:

```bash
./.venv/bin/python scripts/build_regulatory_knowledge.py \
  --config tmp/<portfolio_id>_funds.yaml \
  --extractor local \
  --max-pages 350 \
  --force
```

```bash
./.venv/bin/python scripts/build_curated_regulatory_profiles.py --include-sellers
```

```bash
./.venv/bin/python scripts/build_deep_dive_package.py --portfolio-id <portfolio_id>
```

Se precisar criar ou corrigir extração/parsing, altere os scripts com escopo mínimo:

- `services/regulatory_knowledge.py`
- `scripts/build_regulatory_knowledge.py`
- `scripts/build_curated_regulatory_profiles.py`
- `scripts/build_deep_dive_package.py`
- `tabs/tab_fidc_monitoring.py`, somente se a tela não estiver lendo corretamente dado já gerado
- `tabs/tab_deep_dive.py`, somente se o pacote correto não estiver aparecendo

## Validação obrigatória

Antes de responder, valide:

1. `portfolios.json` não foi alterado, salvo pedido explícito.
2. Não há nova carteira operacional.
3. O pacote Deep Dive gerado corresponde ao `portfolio_id` da carteira existente.
4. `deep_dive_matches_portfolio` retorna verdadeiro para a carteira.
5. `data/deep_dives/index.json` inclui o pacote correto.
6. Cada CNPJ da carteira tem `data/regulatory_knowledge/<cnpj>.json`, ou lacuna explícita se não houver documentos.
7. `load_regulatory_profile(cnpj)` retorna perfil disponível quando houver documentos curáveis.
8. `comparison_main.csv` tem primeira coluna `Nome` e uma coluna por fundo da carteira.
9. `emissions.csv` tem as colunas esperadas e fonte por linha.
10. `thresholds.csv` tem critérios com fonte, chave, monitorabilidade e métrica/proxy.
11. `structural_costs.csv` tem Administração e Gestão por fundo.
12. Nenhuma lacuna material virou zero ou campo vazio.
13. Nenhuma remuneração/spread ficou vazio sem texto de lacuna.
14. O Streamlit consegue enxergar o pacote pela aba Deep Dive.
15. A aba Monitoramento/Base regulatória consegue carregar Base Regulatória, Emissões, Critérios e Timeline para os CNPJs da carteira.

Rode:

```bash
./.venv/bin/python -m py_compile \
  services/regulatory_knowledge.py \
  scripts/build_regulatory_knowledge.py \
  scripts/build_curated_regulatory_profiles.py \
  scripts/build_deep_dive_package.py \
  tabs/tab_deep_dive.py \
  tabs/tab_fidc_monitoring.py
```

```bash
./.venv/bin/python -m unittest tests.test_regulatory_profiles tests.test_deep_dive
```

```bash
git diff --check -- \
  services/regulatory_knowledge.py \
  scripts/build_regulatory_knowledge.py \
  scripts/build_curated_regulatory_profiles.py \
  scripts/build_deep_dive_package.py \
  tabs/tab_deep_dive.py \
  tabs/tab_fidc_monitoring.py \
  data/deep_dives/index.json \
  data/regulatory_profiles/all_fidcs_cotas_emissoes_pagamentos.csv \
  data/regulatory_profiles/all_fidcs_criteria_monitoraveis_ime.csv \
  reports/all_fidcs_regulatory_curation_status.csv \
  reports/regulatory_criteria_matrix.csv \
  reports/regulatory_document_inventory.csv \
  reports/regulatory_emissions_timeline.csv
```

Se `pytest` não existir, diga isso e use `unittest` disponível.

## Entrega esperada

Responda em português, de forma objetiva, com:

- carteira processada;
- CNPJs processados;
- documentos baixados/inventariados por CNPJ;
- pacote Deep Dive atualizado;
- quais seções do Streamlit passam a estar alimentadas;
- principais emissões/spreads/calendários encontrados;
- principais critérios monitoráveis e não monitoráveis;
- lacunas relevantes;
- arquivos alterados;
- validações executadas.

Se algum CNPJ da carteira não puder ser processado, não substitua por outro. Informe:

- CNPJ;
- erro;
- etapa;
- impacto na ferramenta;
- próximo dado necessário.

Não encerre com sugestão genérica. Entregue o status concreto da execução.

---

Fim do prompt.
