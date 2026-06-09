# FIDC Credit Strategy Study - Status 2026-06-09

## Onde estamos

- Foi criada uma base persistente para estudar FIDCs emitidos em 2024 e 2025, com leitura por setor/subtipo, matrizes regulatórias, subordinação, pricing e dados de Informe Mensal CVM.
- O estudo alimenta a aba `Estratégia FIDCs` do Streamlit.
- A base operacional local fica em `data/fidc_credit_strategy/fidc_credit_strategy.sqlite`.
- O SQLite e os CSVs brutos não foram versionados por serem artefatos grandes; o pipeline de geração e este status foram versionados.

## Fontes integradas

- Cadastro CVM de fundos.
- Registro CVM fundo/classe.
- Ofertas de distribuição CVM.
- Informes Mensais FIDC CVM de 2024-01-31 a 2026-04-30.
- Base local de deep diagnostic/regulamentos já extraídos.

## Entregas técnicas

- Consolidação de 7.399 CNPJs/FIDCs.
- 764 matrizes regulatórias lidas.
- Coortes corrigidas:
  - 359 fundos emitidos em 2024 com matriz regulatória.
  - 440 fundos emitidos em 2025 com matriz regulatória.
- Heatmaps de cláusulas `tem/não tem` por setor, subtipo e coorte.
- Métricas equal-weight, ponderadas por PL atual e ponderadas por volume emitido da coorte.
- Subordinação mínima extraída de regulamentos.
- Subordinação atual observada via Informe Mensal CVM, usando valor de cotas sênior, mezanino e subordinadas.
- Pricing de cotas seniores por CDI+, com mediana equal-weight, média ponderada por volume e média ponderada por PL.
- Preço unitário de captações sênior pelo Informe Mensal CVM.
- 975.995 movimentos de cotas processados.
- 309 cortes agregados de preço unitário de cotas.
- 39 ideias comerciais/estruturais automáticas.

## Arquivos principais

- `scripts/build_fidc_credit_strategy_study.py`: pipeline do estudo.
- `services/fidc_credit_strategy.py`: serviço de leitura SQLite.
- `tabs/tab_fidc_credit_strategy.py`: aba Streamlit do estudo.
- `app.py`: inclusão da seção `Estratégia FIDCs`.
- `reports/fidc_credit_strategy_study_20260609.md`: este resumo.

## Validações executadas

- Compilação Python:
  - `.venv/bin/python -m py_compile scripts/build_fidc_credit_strategy_study.py services/fidc_credit_strategy.py tabs/tab_fidc_credit_strategy.py app.py`
- Healthcheck Streamlit:
  - `http://localhost:8503/_stcore/health`
- Smoke test visual no navegador:
  - aba principal carregou;
  - heatmap renderizou;
  - gráfico de subordinação regulatória renderizou;
  - subordinação observada no IME renderizou;
  - pricing sênior renderizou;
  - preço unitário de captações sênior no IME renderizou.

## Próximos passos sugeridos

- Priorizar a fila de review manual por materialidade, começando por fundos com PL alto e matriz incompleta.
- Validar outliers de preço unitário no IME, especialmente médias ponderadas distorcidas por quantidade de cotas reportada.
- Separar visão executiva em PPT com 8 a 12 slides: mercado, padrões de estrutura, pricing, subordinação, oportunidades comerciais e casos prioritários.
- Definir taxonomia final de setores/subtipos com governança: Agro, Crédito PF, Crédito PJ, Risco Sacado, Bancos Emissores, Meios de Pagamento, Imobiliário, Infra/Energia, Judicial/NPL e FIC/Alocador.
- Criar rotinas recorrentes de atualização mensal da base CVM/IME.
- Decidir armazenamento dos artefatos grandes: Git LFS, S3, Drive/SharePoint ou storage interno.
