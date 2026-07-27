# Toma Conta FIDCs — o que mudou nos últimos 30 dias

**Janela:** 27/jun/2026 a 27/jul/2026 (primeiro commit da janela em 29/jun; 29 dias corridos de atividade)
**Repositório:** `abalroar/fidc` (branch `main`)
**Commits na janela:** 244 no total → 206 sem merges (38 merges, 45 PRs referenciados)
**Dos 206:** 83 são commits de desenvolvimento; 123 são salvamentos automáticos da carteira (ver "Ruído" abaixo)

---

## 1. Funcionalidades — antes × agora

### 1.1 Indústria de FIDCs (o grosso do período — módulo novo)

| # | Antes | Agora |
|---|---|---|
| 1 | Não havia série histórica da indústria | Pipeline reconstrói a série mensal desde jan/2013 a partir dos dados abertos da CVM (PL, veículos, cotistas, captação/resgate/amortização, segmentos, inadimplência ajustada, subordinação, concentração de prestadores) |
| 2 | Estudo existia só como CSV + markdown | Aba "Indústria FIDCs" navegável no app, com paleta própria (laranja/preto/cinza) |
| 3 | Sem visão offline do estudo | Dashboard estático HTML gerado pelo pipeline; picos de um mês por veículo passam a ser filtrados |
| 4 | Agregado só no nível "indústria" | Dossiê por fundo, perfis cruzados por dimensão, market share e snapshot por fundo |
| 5 | Documentos e critérios dos fundos não inventariados | Inventário documental + estudo de critérios, com manifests versionados |
| 6 | Curadoria manual, sem rastro | Cockpit de curadoria: fila priorizada, plano de chunking de documentos, atlas de valores por dimensão, registry de heatmaps |
| 7 | Atualizar o mês era refazer tudo | Workflow de delta mensal com ações de revisão registradas |
| 8 | Números do estudo não eram confrontados com fontes públicas | Camada de auditoria de alegações públicas (CVM × ANBIMA × Uqbar) exposta no dashboard |
| 9 | Estado do pipeline invisível no app | Índice de pipeline e indicadores de readiness na interface |
| 10 | Pack executivo ad-hoc | `industry_executive_pack` + `industry_anbima` + export PPT estruturado, com a classificação ANBIMA documentada |
| 11 | Grandes FIDCs sem classificação | Classificação de grandes FIDCs a partir dos próprios documentos + camada de inteligência da indústria |
| 12 | Dashboard e exports saíam de fontes diferentes e divergiam | Payload analítico único alimenta dashboard, deck e xlsx, com manifest e bundle publicável |
| 13 | Sem comparação histórica | Comparações históricas da indústria e caso Atlântico incluídos |
| 14 | Prestadores eram só ranking estático | Análise de atribuição e transição de prestadores + explorador interativo de fluxos (HTML) |
| 15 | Gráficos do PPTX eram imagem | Gráficos nativos e editáveis no PowerPoint |
| 16 | Distribuição de cotistas só em valor absoluto | Gráficos de distribuição normalizada de cotistas |
| 17 | Dados fechavam em maio; cache mensal não invalidava | Base atualizada para junho/2026 e cache invalidado automaticamente na atualização |
| 18 | Deploy quebrava quando o payload mudava de versão | Leitura tolerante a versões do payload, sem quebra entre deploys |
| 19 | Notas dos slides se perdiam na versão web | Notas de slide preservadas no site |
| 20 | Coorte de adquirência restrita, sem CAGR | Coorte ampliada e CAGRs de PL |
| 21 | Sem visão de ofertas/emissões | Ofertas encerradas: rankings, regime de colocação (ICVM 476 / RCVM 160), distribuição de tickets, histórico de prestadores |
| 22 | Emissões de FIDC sem benchmark de mercado | Comparação direta com emissões de renda fixa |
| 23 | Sem cruzamento com crédito bancário | Crédito ampliado do BCB incorporado + curadoria documental das ofertas ("all rites") |
| 24 | Top 15 sem rating | Rating por oferta nos Top 15 |
| 25 | Volume de emissões divergia da ANBIMA sem explicação | Reconciliação explícita de perímetro contra a ANBIMA + nota de perímetro contábil no slide de escala |
| 26 | Taxonomia ANBIMA cobria uma competência | Taxonomia estendida a quatro competências |
| 27 | Deck com lacunas de QA e excesso de variantes | QA fechado e deck/exports simplificados |
| 28 | Sem leitura de private credit | Análise de private credit + regulações dos "outros" do Top 20 |

### 1.2 Carteira e rentabilidade dos fundos

| # | Antes | Agora |
|---|---|---|
| 29 | Rentabilidade mensal por fundo indisponível | Rentabilidade mensal restaurada na carteira e no dashboard MELI |
| 30 | Sem janelas padronizadas de retorno | Tabelas de retorno 12M e YTD (`fund_return_matrix`) |
| 31 | Retorno sem referência de mercado | Benchmark CDI e CDI+ implícito por fundo (`fund_return_benchmark`) |
| 32 | Carga do CDI da B3 falhava | CDI carregado via HTTPS da B3, com fallback tratado |
| 33 | Benchmarks não iam para o PPT | Export completo de benchmarks de retorno no PPT |
| 34 | Rentabilidade CVM sem ressalva metodológica | Nota explícita de reinvestimento nas telas e nos exports |
| 35 | Um PPT por aba | Merge de PPTX: export unificado da carteira (`pptx_merge`) |
| 36 | Retornos apareciam depois dos gráficos consolidados | Retornos por fundo vêm primeiro |
| 37 | Busca de carteira só por nome | Acesso e carregamento por CNPJ, com recuperação de carteira corrigida |
| 38 | Rótulos de seção de fundo errados no PPT "Soma de FIDCs" | Rótulos corrigidos |

### 1.3 Custo financeiro do cedente

| # | Antes | Agora |
|---|---|---|
| 39 | Motor rodava apenas o preset CloudWalk hard-coded | Produto: aceita carteira cadastrada ou até 20 CNPJs, com override de spread por série na simulação corrente, escopo validado (`financial_cost_scope`) e estudo técnico documentado |

### 1.4 Glossário e conhecimento FIDC

| # | Antes | Agora |
|---|---|---|
| 40 | Glossário sem evidência rastreável | Glossário revisado contra corpus de 100 fundos, com evidência por termo, change log e metodologia versionados |
| 41 | FIDCs sem classificação setorial | Classificador setorial de FIDCs e práticas |
| 42 | Base regulatória dispersa | Consolidação de análise, glossário e modelagem (inclui PDFs regulatórios: RCVM 160, RCVM 175, RCVM 30) |

### 1.5 Navegação, UI e marca

| # | Antes | Agora |
|---|---|---|
| 43 | CSS e layout espalhados pelas abas | Serviço `dashboard_ui` centraliza estilo; UI simplificada e tendências da indústria restauradas |
| 44 | Marca inconsistente entre telas | Marca "tomaconta FIDCs" centralizada; IBM Plex Sans self-hosted (compatível com Streamlit Cloud); assinatura do cabeçalho traduzida |
| 45 | Navegação e deep dive confusos | Navegação reorganizada e aba de deep dive reescrita, com curadoria documental |

### 1.6 Mercado secundário — entrou e saiu

| # | Antes | Agora |
|---|---|---|
| 46 | Não tinha | Teve por ~5 dias (módulo ANBIMA Feed com OAuth2, página Streamlit, agregação e backfill), e **não tem mais** — removido em 16/jul (`Remove secondary market feature`, −1.124 linhas) |

---

## 2. Estimativa de horas

### 2.1 Metodologia usada

É a que já existe na plataforma, em `services/dev_hours.py` e documentada na própria interface (aba de investimento em desenvolvimento, expander "Como calculamos?"). Parâmetros vigentes em `data/dev_hours_config.json`:

- **Unidade:** commit (data, mensagem, SHA, repo).
- **Deduplicação:** por SHA, depois por `(timestamp em segundos, mensagem normalizada)`.
- **Sessão de trabalho:** nova sessão quando o intervalo entre dois commits passa de **90 min**.
- **Horas entre commits:** `último commit − primeiro commit` de cada sessão. Sessão de 1 commit tem zero hora-base.
- **Overhead:** **+20 min por sessão** (planejamento, contexto, testes, revisão).
- **Total:** horas entre commits + overhead. **Faixa:** mín = horas entre commits; máx = horas entre commits + 1h/sessão.
- **Merges excluídos** (`incluir_merges: false`). PRs não somam horas (evita dupla contagem).

### 2.2 Resultado da metodologia literal

| Métrica | Valor |
|---|---|
| Commits considerados (dedup, sem merges) | 206 |
| Sessões de trabalho | 51 |
| Horas entre commits | 42,4 h |
| Overhead (20 min × 51) | 17,0 h |
| **Total (ponto central)** | **59,4 h** |
| Faixa | 42,4 h – 93,4 h |
| Sessão média | 1,17 h |

Por semana:

| Semana | Horas entre commits | Overhead | Total | Sessões |
|---|---|---|---|---|
| 29/jun | 1,0 | 3,0 | 4,0 | 9 |
| 06/jul | 16,2 | 4,0 | 20,2 | 12 |
| 13/jul | 14,8 | 4,3 | 19,1 | 13 |
| 20/jul | 6,8 | 4,7 | 11,5 | 14 |
| 27/jul | 3,6 | 1,0 | 4,6 | 3 |

### 2.3 Ruído: 123 dos 206 commits não são desenvolvimento

Os commits `Update portfolio ...` (123 na janela, 60% do total) são gravações automáticas do próprio app: alteram **uma linha** de `portfolios.json`, quase sempre apenas o campo `updated_at` (`+1/−1`). São evidência de **uso** do produto, não de construção. Efeito na conta:

- **19 sessões (10,9 h)** contêm exclusivamente esses salvamentos automáticos — nenhum commit de desenvolvimento.
- Nas **12 sessões mistas**, eles esticam o span da sessão para além do trabalho de código.

### 2.4 Estimativa justa

| Cenário | Sessões | Total | Faixa |
|---|---|---|---|
| Metodologia literal (config atual) | 51 | 59,4 h | 42,4 – 93,4 h |
| **Descartando sessões sem nenhum commit de dev** | **32** | **48,5 h** | — |
| Só commits de dev (spans recalculados) | 33 | 38,6 h | 27,6 – 60,6 h |

**Estimativa justa: ≈ 48 h no período, em faixa de 39 h a 59 h.**

O ponto central de 48,5 h é o mais defensável: mantém a metodologia da plataforma intacta e apenas remove as 19 sessões que não têm um único commit de desenvolvimento. Os 38,6 h são o piso (subestima, porque descarta o tempo real gasto entre um commit de dev e um salvamento de carteira feito na mesma sessão de trabalho); os 59,4 h são o teto da leitura literal (superestima, porque cobra 20 min de overhead por sessão que foi só clicar em salvar).

### 2.5 Viés conhecido da metodologia

Em qualquer cenário a estimativa **subestima**, por três razões estruturais:

1. **Trabalho antes do primeiro commit da sessão não é contado.** Uma sessão que começa às 9h e faz o primeiro commit às 11h só passa a contar às 11h.
2. **Sessão de commit único vale zero hora-base** — recebe apenas os 20 min de overhead, ainda que o commit traga milhares de linhas. Na janela há commits isolados de grande porte (ex.: `Add provider attribution and transition analysis`, +136 mil linhas; `Rebuild FIDC industry executive reporting`, 61 arquivos).
3. **Overhead fixo de 20 min** não escala com o tamanho do commit.

O volume da janela ajuda a dimensionar o que os 48 h entregaram: **28 funcionalidades novas ou refeitas no módulo de indústria**, 10 na carteira/rentabilidade, além de custo financeiro, glossário e UI — com testes acompanhando praticamente todo commit de serviço.
