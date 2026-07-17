# Prompt · Revisão do estudo "Indústria de FIDCs" (Executivo + Dados 202607)

Você vai continuar a revisão de dois arquivos definitivos:

- `Industria_FIDC_Executivo_202607.pptx` — deck executivo, 24 slides, 16:9.
- `Industria_FIDC_Dados_202607.xlsx` — workbook auditável com 21 abas (`PL histórico`, `Mix ANBIMA`, `Top 20 Outros`, `Fila curadoria`, `Indústria mensal`, `Rankings ANBIMA`, `Monoestrutura`, `Ofertas anual`, `Posição Itaú`, `Ranking ofertas`, `Cedentes`, `FIDCs >5bi` etc.).

Os arquivos `Industria_FIDC_2026052.pptx/xlsx` e `Industria_FIDC_202605.xlsx` são versões antigas — use só como referência de formato; não copie dados deles.

Regras de trabalho:

- Todo número do deck nasce de uma aba do workbook. Análise nova exige aba nova (com fonte e critério nas primeiras linhas ou em colunas de metadado). Nada de número solto no slide.
- Localize o gerador que produziu esses arquivos e altere o código, regenerando os dois artefatos com os mesmos nomes. Se o gerador não estiver disponível, edite diretamente via python-pptx/openpyxl.
- Ao final, renderize o deck slide a slide (PNG) e inspecione cada página antes de entregar. Repita o ciclo editar→renderizar→inspecionar até o checklist da seção 6 passar inteiro.

---

## 1) Padrão visual — tirar a cara de "feito por IA"

**Paleta única (Itaú BBA)** em gráficos, tabelas e destaques:

- Laranja institucional `#EC7000` — série protagonista / destaque (substituir o atual `#E36C0A`).
- Preto/quase-preto `#1A1A1A` — segunda série e headers de tabela (substituir o azul-marinho `#172A3A`, que hoje aparece em barras e linhas e não é preto).
- Tons de cinza neutros `#585858 / #8C8C8C / #BFBFBF / #E6E6E6` — séries de contexto. Eliminar cinzas azulados herdados (`5B7DB1`, `9AA7BF` etc.).
- Vermelho apenas para valores negativos em tabelas.

**Gráficos de linha (hoje slides 3, 14, 15, 16, 20):**

- Remover TODOS os marcadores de ponto. Hoje o XML tem `<c:marker val="1"/>` sem símbolo definido, e o PowerPoint desenha quadradinhos/losangos em cada ponto — nas séries mensais (65+ pontos) a linha vira uma lagarta de quadrados. Definir por série `<c:marker><c:symbol val="none"/></c:marker>` (python-pptx: `series.marker.style = XL_MARKER_STYLE.NONE`).
- Linha contínua 2–2,25 pt, sem sombra, sem suavização artificial de curva (manter `smooth=0`) — o aspecto liso vem da espessura e da limpeza do plot, não de interpolação.
- Com até 2 séries, rótulo direto na ponta da linha (nome + último valor) em vez de legenda embaixo; legenda só com 3+ séries.

**Plot area (todos os gráficos):**

- Sem borda/moldura na área de plotagem e sem gridlines verticais (hoje os slides 13, 17, 18, 19 e 22 têm o quadriculado default do Excel).
- Manter só gridlines horizontais finas em cinza-claro (`#E6E6E6`), eixo X em cinza, sem tick marks pesados.
- Eixo X de séries mensais: mostrar apenas dezembros (ou 1 rótulo a cada 6 meses), horizontal, sem rotação de 45° — hoje há 65 rótulos girados nos slides 13–16.
- Rótulos de dado apenas onde a leitura exige (última barra, total da pilha); nunca em todos os pontos.

**Títulos e layout:**

- O título de slide não pode colidir com a linha divisória: hoje os títulos de 2 linhas ficam "riscados" nos slides 10, 18, 20, 23 e 24. Reservar altura de 2 linhas na faixa de título ou encurtar o título para caber em 1 linha (~95 caracteres).
- Nenhum slide em branco ou semivazio: eliminar/mesclar slides com mais de ~40% de área útil vazia (hoje: metade inferior do 2, rodapé do 21 e do 24; tabelas esparsas com padding gigante nos 5 e 6). Se o conteúdo não preenche o slide, ele não merece um slide.
- Tabelas: headers sem quebra feia de palavra (hoje "Captaçõe s" e "Amortizaç ões" no slide 13) — ajustar largura de coluna e abreviar ("Captações", "Amort."); zebra sutil; linha de destaque Itaú mantida.

## 2) Texto — banir frases com jeito de IA

Proibido o padrão contrastivo "Não é A; é B" e a meta-narração sobre o próprio método. Ocorrências atuais a reescrever:

- "A leitura é defensável porque separa dado oficial, evidência e inferência" (título do slide 24) → algo como "Metodologia e fontes: CVM, ANBIMA e curadoria documental".
- "Ausência de prestador reduz cobertura, não gera inferência" (slide 24) → "Fundos sem prestador identificado ficam fora do ranking (1,2% do PL)".
- "não transforma dúvida em Outros" (slide 2) e "N/D não é somado a Outros" (slide 4) e "Nunca é convertido silenciosamente em Outros" (slide 24) → dizer uma vez, de forma positiva: "N/D permanece como categoria própria (1,9% do PL)".
- "quantidade e volume contam histórias diferentes" (slide 2) → substituir pelo fato: "os 778 fundos acima de R$ 200 mi concentram 100% do PL elegível; 331 deles têm cotista único".

Regra geral: título = conclusão com número; caveat = nota de rodapé factual, sem negação retórica, sem autoelogio ("auditável", "defensável", "disciplinado"). Não usar reticências dramáticas nem pares "não X, e sim Y".

## 3) Nova ordem do deck

1. Capa
2. Síntese executiva (1 slide denso)
3. **Evolução do PL** — trocar a linha por **barras empilhadas** dez/15→Mai/26: PL ex-FIC (laranja) + parcela FIC-FIDC (cinza) = PL bruto, rótulo do total sobre cada pilha (dados prontos na aba `PL histórico`). Completar a tabela lateral desde 2015 (hoje começa em 2019).
4. **Base investidora** (atual slide 14) — sobe para cá, logo após o PL.
5. **NOVO · PL por tipo ANBIMA em barras (dez/24, dez/25, Mai/26)** — barras agrupadas por tipo (Fomento Mercantil, Agro/Indústria/Comércio, Financeiro, Outros, N/D), em R$ bi, com o delta YoY rotulado, para mostrar qual subtipo cresce mais (base: aba `Mix ANBIMA`; replicar o espírito do gráfico "PL por Classe" do FIDC_Mercado_Dados_ANBIMA, mas em barras).
6. Mix percentual por tipo (atual slide 4).
7. **NOVO · Market share por subtipo ANBIMA entre os líderes** — colunas 100% empilhadas por subtipo: top 10 participantes coloridos (laranja para Itaú quando presente, preto/cinzas para os demais) e o resíduo agregado em "Outros participantes" (base: aba `Rankings ANBIMA`, role administrador; declarar cobertura).
8. Captação líquida (atual 13).
9. Inadimplência (reformulada — seção 4d).
10. Concentração de administradores (atual 16) + rankings gerais adm/gestão/custódia (atuais 7–9).
11. Ranking por tipo/foco ANBIMA — reformulado ou cortado (seção 4e).
12. **Top 20 FIDCs** (antes do Top 20 de Outros) — ranking completo, 20 linhas em UM slide.
13. **Top 20 de Outros** — 20 linhas em UM slide (hoje são 2 slides de 10; consolidar).
14. Monoestrutura + líderes por modelo (reformulados — seção 4c).
15. Ofertas e originação (reformulado — seção 4f).
16. Metodologia e fontes (1 slide, texto seco).
17. **Apêndice: 1 slide de perfil por FIDC do Top 20** (seção 4b).

## 4) Mudanças analíticas obrigatórias

**a) Top 20 FIDCs.** O slide atual (23) lista só 15 fundos e vem depois do Top 20 Outros — inverter a ordem e completar as 20 linhas. Colunas: #, fundo, PL, tipo ANBIMA, segmento documental, administrador, gestor.

**b) Perfil dos 20 maiores FIDCs.** Um slide por fundo no apêndice, com a curadoria da aba "Dados de Carteira" do app: tese em 1 linha, cedente(s), sacado(s)/devedores, tipo de recebível, emissões/classes e séries, prestadores, subordinação, nº de cotistas e eventos relevantes. A aba `FIDCs >5bi` já traz classificação documental com evidência para os maiores — estender o levantamento aos 20 e gravar tudo em aba nova `Perfis Top 20` (um campo por coluna, fonte por campo).

**c) Monoestrutura × Top 20 — responder à pergunta "é PL relevante ou é meia dúzia de tickets?".** Cruzar a base de monoestrutura com o Top 20 e quantificar: dos 34,4% de PL monoestrutura, quanto vem de fundos individualmente gigantes (ex.: FIDC DO SISTEMA PETROBRAS, R$ 60,8 bi — praticamente 100% do PL administrado pelo Banco do Brasil, que tem 1–3 fundos; TAPSO FIDC RL, R$ 40,7 bi na Oliveira Trust). Reportar por player: PL mono, nº de fundos, share do maior fundo (top-1) e dos 3 maiores (top-3). Reescrever o slide "Plataformas integradas e especialistas coexistem entre os líderes" citando fundos nomeados e volumes, não apenas contagem de fundos — a conclusão deve dizer explicitamente se a monoestrutura é fenômeno de plataforma ou de tickets únicos em que um player "leva o combo". Aba nova `Mono x Top20`.

**d) Auditoria da inadimplência ajustada (hoje slide 15).** A série vem da aba `Indústria mensal` (`inad_pct`, `inad_pct_ajustada`, `inad_pct_ajustada_ex_np`). Antes de manter o gráfico, responder no workbook (aba nova `Auditoria inadimplência`, por fundo/competência) e resumir no slide:

- Universo exato: quantos dos ~4.200 veículos reportam carteira de direitos creditórios e inadimplência; % do PL coberto pela métrica.
- Quantos fundos reportam inadimplência > carteira (o gatilho do ajuste): quantidade sobre o total e representatividade sobre o PL; listar os maiores ofensores nomeados.
- Explicar o degrau de jun/24→jul/24: a bruta cai de 14,7% para 9,1% em um mês, enquanto a ajustada vai de 7,7% para 6,7% — decompor por CNPJ quais fundos causam a quebra e o que mudou (reporte, template do Informe Mensal na adaptação à RCVM 175, saída de NPL a valor de face?). O slide precisa de nota explicando a quebra estrutural; sem isso a série longa não é comparável.
- Créditos vencidos >360d: verificar se seguem no numerador (FIDCs não são obrigados a baixar a prejuízo) e mostrar a série ex-NPL (`inad_pct_ajustada_ex_np`) como terceira linha ou nota.
- Fechar com veredito curto no slide: a métrica é observável e comparável? Em que ela é frágil?

**e) Ranking por tipo/foco ANBIMA (slides 10–12).** Hoje são 3 slides confusos. Explicar de onde vem a coluna "Tipo / foco" (fotografia ANBIMA de dez/25 aplicada como ponte cadastral — aba `Rankings ANBIMA`), qual o universo (só focos com PL ≥ R$ 1 bi? Qual % do PL total cada linha cobre? A aba tem `role_pl_coverage` — expor). Se a cobertura por foco for baixa ou a leitura não for defendida com número, reduzir os 3 slides a 1 (os 5–6 focos mais relevantes, com coluna de cobertura) ou mover para apêndice. O título "Os líderes mudam materialmente entre os focos ANBIMA" só fica se o slide mostrar essa mudança de forma legível.

**f) Ofertas, originação e Posição Itaú (slide 22 + abas `Ofertas anual`, `Posição Itaú`, `Ranking ofertas`, `Cedentes`).** Hoje não está claro de onde vem o dado nem o que significam os rótulos. Obrigatório:

- Documentar a linhagem em uma caixa do slide e na aba: fonte = CVM Ofertas Públicas de Distribuição (dados.cvm.gov.br), regime da Resolução CVM 160 (rito automático/ordinário), janela, critério de dedupe, e o mapeamento de cada campo usado: "volume registrado" vs "volume inicial" vs `closed_offers` ("emissão encerrada" = oferta com encerramento comunicado, não é volume liquidado) vs `placed_volume_proxy`.
- Decidir e declarar: esse dado serve como proxy de emissão? Se não for defensável, rotular como "registro de ofertas" e nunca como "emissão".
- A aba `Posição Itaú` (coordenador/administrador/gestor/custodiante, shares e ranks) precisa de coluna de fonte por métrica e de rótulos legíveis; hoje os nomes truncados (`itau_coordinator_with_itau_a...`) são indecifráveis.
- Ranking nominal de originadores cobre 32,7% do volume — manter essa cobertura visível ao lado do ranking.

## 5) Workbook (XLSX)

- Novas abas: `Auditoria inadimplência`, `Mono x Top20`, `Perfis Top 20`, e a base do market share por subtipo. Cada uma com fonte, competência e critério.
- Renomear/descrever colunas crípticas nas abas existentes (ex.: `Posição Itaú`, `Ofertas anual`) — uma linha de dicionário por coluna ou aba `_Dicionário`.
- Manter os nomes dos arquivos: `Industria_FIDC_Dados_202607.xlsx` e `Industria_FIDC_Executivo_202607.pptx`.

## 6) Checklist final (bloqueante)

1. Nenhum gráfico de linha com marcador; nenhuma série com o azul `172A3A`; laranja único `#EC7000`.
2. Nenhum gráfico com moldura de plot area ou gridline vertical; eixos mensais sem 65 rótulos girados.
3. Nenhum título colidindo com o divisor; nenhum header de tabela com palavra quebrada.
4. Nenhum slide em branco ou com mais de ~40% de área vazia no render final.
5. Zero ocorrências de: "não é X, é Y" / "não gera inferência" / "defensável" / "não transforma" / "silenciosamente" / meta-comentário sobre o método fora do slide de metodologia.
6. Top 20 FIDCs vem antes do Top 20 Outros; cada ranking completo em um único slide.
7. Todo número do deck rastreável a uma aba; toda análise nova tem aba própria.
8. Render PNG de todos os slides inspecionado após a última edição.
