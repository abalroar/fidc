# Estudo da industria de FIDCs — base CVM (dados abertos)

**Data-base:** 2026-05 · **Serie:** 201301 a 202606 · **Gerado em:** 2026-07-08T03:48:48+00:00

> Relatorio gerado por `scripts/build_fidc_industry_study.py` a partir do dataset
> oficial *FIDC — Documentos: Informe Mensal* (Portal de Dados Abertos da CVM) e do
> cadastro `registro_fundo_classe`. Todos os agregados sao reconstruiveis a partir
> de `data/industry_study/`.

---

## 1. Sumario executivo

- **PL da industria: R$ 958,5 bi** em 2026-05, distribuido em
  4.224 veiculos reportantes (4.200 classes
  RCVM 175 + 24 fundos ainda no regime legado), de
  4.219 fundos unicos.
- **Crescimento:** +22,5% em 12 meses; +340,2% vs dez/2020 (PL em dez/2019 era R$ 237,4 bi).
- **Captacao:** R$ 353,9 bi de captacao bruta e R$ 219,6 bi de
  captacao liquida nos 12 meses ate 2026-05 (Tab X.4 do informe mensal).
- **Base de investidores:** 445.664 contas de cotistas
  (conceito de contas por classe/serie, nao CPFs unicos).
- **Numero de veiculos** cresceu +243,4% desde dez/2020.
- **Inadimplencia ajustada (DC vencidos e nao pagos / carteira, limitada a carteira
  de cada veiculo):** 5,8% em 2026-05
  (ex-FIDC NP: 5,8%; bruta, com NPL a valor
  de face: 8,0%).
- **Cotas subordinadas** respondem por 31,7% do valor
  total de cotas (inclui estruturas mono-classe subordinadas; ver metodologia).
- **Concentracao de administradores:** top 5 = 52,4%,
  top 10 = 71,3%,
  HHI = 0,074.
- **FIC-FIDC:** R$ 78,6 bi do PL total sao veiculos identificados
  como FIC-FIDC pela razao social — ha dupla contagem economica potencial; PL ex-FIC:
  R$ 879,9 bi.
- **Condominio:** 70,8% do PL em
  condominio fechado; 29,2% aberto.

## 2. Definicao e arcabouco regulatorio

FIDC e o fundo que destina a maior parte do patrimonio a direitos creditorios
(ICVM 356/489, hoje Anexo Normativo II da **Resolucao CVM 175**). Pontos que afetam
diretamente a leitura dos numeros:

1. **RCVM 175 (vigente para FIDCs desde out/2023, adaptacao ao longo de 2024):**
   a unidade regulatoria passou de *fundo* para *fundo -> classe -> subclasse*, com
   CNPJ proprio por classe. No informe mensal, veiculos adaptados reportam por
   classe (`TP_FUNDO_CLASSE = "Classe"`); nao adaptados seguem por fundo.
2. **Acesso ao varejo:** a RCVM 175 permitiu cotas de FIDC para o publico geral
   (antes restritas a investidores qualificados), um dos motores do crescimento
   da base de cotistas desde 2024.
3. **Responsabilidades:** administrador e gestor sao prestadores essenciais;
   custodia, registro/escrituracao e verificacao de lastro seguem regras proprias
   do Anexo II. No dado aberto, o administrador vem no proprio informe mensal;
   gestor e custodiante vem do cadastro.
4. **Informe mensal (fonte deste estudo):** entrega mensal obrigatoria, com
   retificacoes; competencias recentes mudam ate estabilizar.

## 3. Evolucao da industria

| Competencia | PL | Veiculos | Cotistas (contas) | Captacao liquida 12m |
|-------------|----|----------|-------------------|----------------------|
| 2013-12 | R$ 84,5 bi | 430 | 9.410 | R$ -10,3 bi |
| 2015-12 | R$ 84,7 bi | 527 | 12.508 | R$ -3,3 bi |
| 2017-12 | R$ 115,2 bi | 750 | 16.049 | R$ -2,5 bi |
| 2019-12 | R$ 237,4 bi | 1.042 | 25.781 | R$ 68,2 bi |
| 2020-12 | R$ 217,8 bi | 1.230 | 32.936 | R$ -21,0 bi |
| 2021-12 | R$ 308,9 bi | 1.547 | 31.626 | R$ 104,0 bi |
| 2022-12 | R$ 378,9 bi | 1.912 | 48.608 | R$ 44,9 bi |
| 2023-12 | R$ 485,4 bi | 2.404 | 61.735 | R$ 58,1 bi |
| 2024-12 | R$ 731,8 bi | 3.140 | 148.582 | R$ 271,9 bi |
| 2025-12 | R$ 918,1 bi | 4.007 | 387.334 | R$ 185,8 bi |
| 2026-05 | R$ 958,5 bi | 4.224 | 445.664 | R$ 219,6 bi |

Serie mensal completa em `data/industry_study/industry_monthly.csv`
(PL, ativo, carteira, captacoes, resgates, amortizacoes, cotistas, inadimplencia,
subordinacao, recompras, PL aberto/fechado/exclusivo e PL de FIC-FIDC).

Base granular reprodutivel em `data/industry_study/vehicle_monthly.csv.gz`:
uma linha por competencia x veiculo reportante, com PL, administrador, segmento
dominante, fluxos, cotistas, inadimplencia, subordinacao, recompras e chaves
classe/fundo. A qualidade da atualizacao mensal fica em
`data/industry_study/update_audit_monthly.csv`.

## 4. Composicao por tipo de recebivel (2026-05)

Classificacao oficial da Tabela II do informe mensal (carteira de direitos
creditorios por segmento economico):

| Segmento | Carteira | Share |
|----------|----------|-------|
| Financeiro | R$ 311,6 bi | 42,8% |
| Comercial | R$ 116,4 bi | 16,0% |
| Cartao de credito | R$ 77,8 bi | 10,7% |
| Industrial | R$ 74,1 bi | 10,2% |
| Servicos | R$ 70,1 bi | 9,6% |
| Setor publico | R$ 38,8 bi | 5,3% |
| Acoes judiciais | R$ 27,3 bi | 3,7% |
| Agronegocio | R$ 9,3 bi | 1,3% |
| Imobiliario | R$ 3,1 bi | 0,4% |
| Factoring | R$ 0,1 bi | 0,0% |
| Marcas e patentes | R$ 0,0 bi | 0,0% |

Abertura do segmento **Financeiro**:

| Segmento | Carteira | Share |
|----------|----------|-------|
| Financeiro: outros | R$ 225,3 bi | 72,3% |
| Financeiro: credito corporativo | R$ 33,4 bi | 10,7% |
| Financeiro: credito pessoal | R$ 28,0 bi | 9,0% |
| Financeiro: consignado | R$ 19,7 bi | 6,3% |
| Financeiro: veiculos | R$ 3,9 bi | 1,2% |
| Financeiro: middle market | R$ 0,7 bi | 0,2% |
| Financeiro: imobiliario empresarial | R$ 0,3 bi | 0,1% |
| Financeiro: imobiliario residencial | R$ 0,3 bi | 0,1% |

## 5. Mapa competitivo de prestadores (2026-05)

### 5.1 Administradores (fonte: informe mensal, auditavel mes a mes)

| # | Nome | PL | Share | Veiculos |
|---|------|----|-------|----------|
| 1 | BTG PACTUAL SERVIÇOS FINANCEIROS S/A DTVM | R$ 146,4 bi | 15,3% | 430 |
| 2 | QI CORRETORA DE TÍTULOS E VALORES MOBILIÁRIOS S.A. | R$ 139,2 bi | 14,5% | 821 |
| 3 | OLIVEIRA TRUST DTVM S.A. | R$ 97,7 bi | 10,2% | 156 |
| 4 | BB GESTAO DE RECURSOS DTVM S.A | R$ 60,9 bi | 6,4% | 3 |
| 5 | BANCO DAYCOVAL S.A. | R$ 57,7 bi | 6,0% | 398 |
| 6 | BEM - DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | R$ 51,4 bi | 5,4% | 46 |
| 7 | CBSF DISTRIBUIDORA DE TÍTULOS E VALORES MOBILIÁRIOS S.A. | R$ 43,0 bi | 4,5% | 80 |
| 8 | INTRAG DTVM LTDA. | R$ 31,6 bi | 3,3% | 40 |
| 9 | GENIAL INVESTIMENTOS CORRETORA DE VALORES MOBILIÁRIOS S.A. | R$ 30,8 bi | 3,2% | 83 |
| 10 | HEMERA DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA | R$ 24,5 bi | 2,6% | 127 |
| 11 | BRL TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A. | R$ 22,5 bi | 2,3% | 138 |
| 12 | BANCO GENIAL S.A. | R$ 21,0 bi | 2,2% | 56 |
| 13 | XP INVESTIMENTOS CCTVM S.A. | R$ 17,8 bi | 1,9% | 44 |
| 14 | FINAXIS CORRETORA DE TÍTULOS E VALORES MOBILIÁRIOS S.A. | R$ 17,7 bi | 1,8% | 68 |
| 15 | VORTX DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | R$ 17,0 bi | 1,8% | 177 |

### 5.2 Gestores (fonte: cadastro CVM vigente — foto, nao serie historica)

| # | Nome | PL | Share | Veiculos |
|---|------|----|-------|----------|
| 1 | OLIVEIRA TRUST SERVICER S/A | R$ 74,4 bi | 7,8% | 46 |
| 2 | BB GESTAO DE RECURSOS DTVM S.A | R$ 60,9 bi | 6,4% | 2 |
| 3 | BANCO BRADESCO S.A. | R$ 40,7 bi | 4,2% | 31 |
| 4 | BTG PACTUAL ASSET MANAGEMENT S/A DTVM | R$ 29,8 bi | 3,1% | 43 |
| 5 | SOLIS INVESTIMENTOS S A | R$ 27,2 bi | 2,8% | 112 |
| 6 | GENIAL GESTÃO LTDA. | R$ 27,0 bi | 2,8% | 48 |
| 7 | BANCO BTG PACTUAL S/A | R$ 25,0 bi | 2,6% | 9 |
| 8 | TERCON INVESTIMENTOS S.A. | R$ 24,0 bi | 2,5% | 230 |
| 9 | CBSF TRUST ADMINISTRADORA DE RECURSOS LTDA. | R$ 21,0 bi | 2,2% | 18 |
| 10 | REAG JUS GESTÃO DE ATIVOS JUDICIAIS LTDA. | R$ 16,5 bi | 1,7% | 29 |
| 11 | ITAU UNIBANCO ASSET MANAGEMENT LTDA. | R$ 15,2 bi | 1,6% | 21 |
| 12 | VALORA RENDA FIXA LTDA. | R$ 15,1 bi | 1,6% | 24 |
| 13 | INTEGRAL INVESTIMENTOS LTDA. | R$ 14,1 bi | 1,5% | 20 |
| 14 | VERT GESTORA DE RECURSOS FINANCEIROS LTDA. | R$ 14,0 bi | 1,5% | 45 |
| 15 | KANASTRA ADMINISTRAÇÃO DE RECURSOS LTDA | R$ 13,5 bi | 1,4% | 42 |

### 5.3 Custodiantes (fonte: cadastro CVM `registro_classe` — foto)

| # | Nome | PL | Share | Veiculos |
|---|------|----|-------|----------|
| 1 | BANCO BTG PACTUAL S/A | R$ 145,7 bi | 15,4% | 429 |
| 2 | QI CORRETORA DE TÍTULOS E VALORES MOBILIÁRIOS S.A. | R$ 138,8 bi | 14,6% | 794 |
| 3 | OLIVEIRA TRUST DTVM S.A. | R$ 116,5 bi | 12,3% | 202 |
| 4 | BANCO DAYCOVAL S.A. | R$ 63,7 bi | 6,7% | 475 |
| 5 | BANCO DO BRASIL S.A. | R$ 60,8 bi | 6,4% | 1 |
| 6 | BANCO BRADESCO S.A. | R$ 49,9 bi | 5,3% | 46 |
| 7 | REAG TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A. | R$ 49,4 bi | 5,2% | 87 |
| 8 | BANCO GENIAL S.A. | R$ 42,8 bi | 4,5% | 125 |
| 9 | HEMERA DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA | R$ 24,6 bi | 2,6% | 129 |
| 10 | BANCO FINAXIS S.A. | R$ 23,0 bi | 2,4% | 82 |
| 11 | ITAU UNIBANCO S.A. | R$ 22,4 bi | 2,4% | 34 |
| 12 | BRL TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A. | R$ 22,3 bi | 2,3% | 137 |
| 13 | LIMINE TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | R$ 22,3 bi | 2,3% | 163 |
| 14 | VORTX DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA. | R$ 16,9 bi | 1,8% | 174 |
| 15 | ID CORRETORA DE TITULOS E VALORES MOBILIARIOS S.A. | R$ 16,5 bi | 1,7% | 290 |

Serie historica de concentracao (HHI, top 5, top 10 por administrador) em
`data/industry_study/concentration_monthly.csv`.

## 6. Base de investidores (2026-05)

| Tipo de cotista | Contas | Share |
|-----------------|--------|-------|
| Outros fundos | 195.838 | 43,9% |
| Outros | 106.859 | 24,0% |
| Pessoa fisica | 96.520 | 21,7% |
| Corretora/distribuidora | 36.123 | 8,1% |
| PJ nao financeira | 5.758 | 1,3% |
| Banco comercial | 1.886 | 0,4% |
| Cotas de FIDC (outros FIDC/FIC-FIDC) | 1.746 | 0,4% |
| Outra PJ financeira | 297 | 0,1% |
| Previdencia fechada (EFPC) | 171 | 0,0% |
| Regime proprio (RPPS) | 156 | 0,0% |
| Investidor nao residente | 147 | 0,0% |
| Clube de investimento | 56 | 0,0% |
| FII | 47 | 0,0% |
| Seguradora | 12 | 0,0% |
| Capitalizacao | 11 | 0,0% |
| Previdencia aberta (EAPC) | 5 | 0,0% |

Nota: o conceito e **contas por classe/serie** (Tab X.1.1), nao investidores
unicos. O mesmo investidor com posicoes em N classes conta N vezes; por isso este
numero nao bate com "contas" da ANBIMA nem com CPFs unicos da B3.

## 7. Qualidade de carteira e risco (2026-05)

- Carteira de direitos creditorios: R$ 670,3 bi.
- **Inadimplencia ajustada: 5,8%**
  (5,8% excluindo FIDCs nao padronizados).
  A leitura "bruta" (8,0%) e distorcida por compradores de
  NPL, que reportam creditos vencidos pelo valor de FACE contra carteira a valor
  contabil — ha veiculos com "inadimplencia" superior a propria carteira, dai o
  ajuste que limita a inadimplencia de cada veiculo a sua carteira.
- Creditos a vencer com parcelas em atraso: R$ 20,8 bi.
- Recompras de DC no mes: R$ 1,9 bi; substituicoes: R$ 0,1 bi.
- Cotas subordinadas / total de cotas: 31,7%. Atencao:
  o numero inclui fundos inteiramente subordinados (estruturas captivas/mono-classe)
  e depende da nomenclatura das series; nao equivale ao "colchao de subordinacao"
  medio de estruturas com cotas senior.

## 8. Por que os numeros nao batem? (CVM x ANBIMA x Uqbar x midia)

| Causa | Efeito pratico |
|-------|----------------|
| **Universo** | CVM = todos os FIDCs registrados que entregam informe (inclui exclusivos, NP e FIC-FIDC). ANBIMA cobre a base informada a autorregulacao (~90% dos fundos, pelo convenio CVM-ANBIMA de jan/2025). Uqbar consolida securitizacao com metodologia proprietaria. |
| **PL vs AUM** | O PL CVM soma classes e fundos legados; soma inclui FIC-FIDC (dupla contagem economica de R$ 78,6 bi na data-base). |
| **Captacao liquida vs emissao** | Captacao liquida (X.4: captacoes - resgates - amortizacoes) nao e "emissoes/ofertas" (ANBIMA) nem "emissoes de mercado primario" (Uqbar). Um FIDC fechado pode emitir muito e amortizar em seguida. |
| **Fundo vs classe** | Pos-RCVM 175 a unidade virou classe. No cadastro CVM, a quase totalidade das classes de FIDC usa o proprio CNPJ do fundo (senior/subordinada viram *subclasses*), entao veiculos reportantes ~ fundos unicos nesta base; contagens de "classes" da ANBIMA seguem outro conceito/universo. |
| **Data-base** | A industria cresce ~2-3% ao mes; comparar nov/2025 com jan/2026 ja distorce. |
| **Contas vs investidores** | Cotistas CVM = contas por classe/serie; ANBIMA reporta contas de outra base; nenhum dos dois e CPF unico. |
| **Competencias em carga** | O ultimo mes do dataset CVM ainda recebe informes e retificacoes por semanas. |

**Numeros de referencia externos** (para reconciliacao; nao recalculados aqui):
ANBIMA reportou PL de R$ 741,1 bi (nov/2025), captacao liquida de R$ 57,6 bi (2025)
e R$ 90,1 bi em emissoes (dez/24-nov/25); Uqbar reportou PL de R$ 767,6 bi (jan/2026)
e emissoes acima de R$ 290 bi (2025). O PL CVM desta base em 2026-05 e
R$ 958,5 bi (R$ 879,9 bi ex-FIC-FIDC) — acima da ANBIMA, como
esperado pela diferenca de universo.

## 9. Metodologia e reprodutibilidade

- **Fonte:** dataset publico *FIDC — Documentos: Informe Mensal* (CVM), tabelas
  I, II, IV, VII, X.1, X.1.1, X.2 e X.4; cadastro `registro_fundo_classe`.
- **Chave:** `CNPJ_FUNDO` ate a adaptacao a RCVM 175; `TP_FUNDO_CLASSE` +
  `CNPJ_FUNDO_CLASSE` depois. Sem sobreposicao entre fundos e classes no dataset.
- **Dedup:** uma linha por CNPJ por competencia (ultima ocorrencia).
- **Inadimplencia:** (`TAB_I2A3` + `TAB_I2B3`) / (`TAB_I2A` + `TAB_I2B`) — creditos
  vencidos e nao pagos sobre carteira de DC (com e sem aquisicao substancial de
  risco). Na versao **ajustada**, a inadimplencia de cada veiculo e limitada a sua
  propria carteira antes da agregacao (corrige NPL reportado a valor de face).
- **Subordinacao:** soma de `QT_COTA x VL_COTA` das series cujo nome contem
  "subordinada" sobre o total (Tab X.2), considerando apenas veiculos cujo valor
  total de cotas fica entre 0 e 3x o proprio PL (filtro de dados corrompidos).
- **Fluxos (Tab X.4):** linhas com valor acima de max(3x PL do veiculo, R$ 2 bi)
  sao descartadas como erro de preenchimento (valor descartado registrado em
  `x4_valor_descartado`).
- **Picos de um mes:** veiculo-mes cujo PL (ou nao de cotistas) supera 20x o mes
  anterior E o seguinte do proprio veiculo e excluido como erro de preenchimento
  (ex.: PL de R$ 101,6 bi reportado por um unico fundo apenas em 2016-05).
- **Limitacoes conhecidas:** gestor/custodiante sao foto do cadastro vigente;
  FIC-FIDC e FIDC-NP identificados por razao social (heuristica); competencias
  recentes sujeitas a revisao; cotistas em base de contas.

Para atualizar: `python scripts/build_fidc_industry_study.py --report`.
