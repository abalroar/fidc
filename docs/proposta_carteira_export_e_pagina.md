# Carteira: página e apresentação

## Escopo e ponto de partida

Refinamento da experiência existente de carteira salva, em `codex/carteira-export-e-pagina`. Preservar nome da carteira, cesta e CNPJs, cálculos, fontes, cache, competência comum, distinções documentais e composição por tema. Sem dependências novas, JavaScript injetado, migração de infraestrutura ou de masters do PowerPoint.

Base de trabalho: `09730513`, que inclui o refinamento local de Estrutura para todas as carteiras; base pública identificada: `06c98683`. O trabalho anterior ainda não integrado será identificado separadamente no PR. O checkout principal e seu WIP permanecem intactos. O anexo é evidência; será preservado.

Leitura de design: ferramenta de crédito para analistas; sóbria, compacta, com dados primeiro. Preservação alta; variação visual 3/10, movimento 1/10, densidade 8/10. Manter fontes e paleta existentes. Aplicar dos skills `design-streamlit-financeiro` e `design-taste-frontend` hierarquia, concisão, consistência e preservação; regras de landing pages e novos frameworks não se aplicam ao escopo autorizado.

## Diagnóstico e decisões transversais

| Ponto / conclusão | Alternativas consideradas | Escolha e benefício | Magnitude | Depois |
|---|---|---|---|---|
| Datas: confirmado que convivem posição comum, última observação, janela carregada, janela visual, geração e leitura documental. | Uma data única artificial; alterar competência comum; hierarquia explícita. | Posição comum é referência do consolidado comparável; histórico mostra janela efetiva e posição individual mostra sua própria competência. Geração é data de consulta, leitura documental fica em metodologia/notas. Uma barra de contexto e detalhes recolhidos. | Local | Proposta financeira sobre fundos defasados, sem mudar regra. |
| Filtro visual: controla históricos mensais, dashboards filtrados, monitor, pesquisa e arquivos; mantém lookback para YoY. O cockpit comparativo tem seu próprio corte comum. | Remover filtro; fundir janelas de cálculo; recolher controle avançado e explicar diferença. | Preservar filtros/cálculos. Reduzir repetição, identificar janela efetiva no histórico e competência do comparativo. Persistir escolhas por carteira. | Local / estrutural no posicionamento | Redefinição de janela ou referência financeira. |
| Zero, ausência e razão inválida: confirmado gráfico vazio com coluna existente toda NaN; acrescentado texto que chama séries zeradas de “sem dados”. | Ocultar zeros por tipo/limiar; manter tudo; compactar ausência e explicar razão inválida. | Zero observado continua zero. Sem valores finitos é ausência. Denominador observado zero permite explicar razão não calculável. Nunca inferir “não aplicável” pelo nome/tipo de fundo. Informar componentes compactados/ausentes. | Local, estrutural na compactação | Supressão por tipo ou limiar. |
| Nomes e CNPJ: repetidos e truncados de modos diferentes. | Cortes de caracteres; nomes legais em toda célula; nome curto canônico. | `short_fund_name` nos títulos, seletores e cabeçalhos. Identificação completa por clique/teclado, metodologia e notas. Identificadores financeiros internos inalterados; desambiguar nomes iguais. | Local | Alterar nome cadastral ou da carteira. |
| Cor: laranja sobrecarregado. | Trocar paleta; aplicar cor financeira arbitrária; restringir papéis. | Laranja para identidade e seleção; texto/bordas neutros; cores de séries estáveis. Variação sem interpretação financeira documentada fica neutra. Exportação secundária. | Cosmética | Nova identidade visual. |
| Tipografia PPT: anexo tem 28 tamanhos explícitos, 6–44 pt, Calibri/Arial; hipótese de 17 tamanhos subestimada. | Novo template; reduzir conteúdo; escala dentro do layout atual. | Calibri e escala curta no fluxo carteira, piso de leitura com paginação em vez de microtexto. Títulos, tabelas e notas com papéis consistentes. | Local | Migração completa de master/layouts/placeholders. |

## Apresentação: problemas confirmados e opções

Anexo: **122 slides**, A 2 / B 73 / C 12 / D 35; 119 gráficos nativos com 119 planilhas incorporadas; 80 tabelas nativas. Apenas D tem notas. Há 20 gráficos sem pontos e 44 inteiramente zero; estes últimos não autorizam apagar informação de crédito.

| Ponto / conclusão | Alternativas consideradas | Escolha e benefício | Magnitude | Depois |
|---|---|---|---|---|
| RDB: conclusão de MT FGTS/CCB Tudo Serviços e geração 14/08/2026 aparecem em toda carteira; texto invade tabela. | Manter conclusão; apagar slide sem aviso; derivar apenas das evidências da cesta. | Remover afirmação alheia, usar estado documental real e geração atual; paginar tabela e guardar texto integral nas notas. Quando nada localizado, nota explícita: ausência não prova inexistência. | Local, primeiro reparo | Compactação do slide em commit estrutural. |
| Truncamentos no meio de palavras, inclusive emissões. | Cortar mais; diminuir fonte; nome curto e texto integral preservado. | Nomes canônicos; quebra/paginação para conteúdo e notas integrais, sem corte silencioso. | Local | Reescrever fontes documentais. |
| Caminhos `data/raw/...pdf` aparecem nos rodapés C. Sanitizador atual mantém caminhos relativos deliberadamente. | Alterar sanitizador global; corrigir apresentação C. | Rodapé curto por fonte; documento, página, link primário e identificação nas notas. Mudança restrita à apresentação da carteira. | Local | Nova política global de fontes. |
| “R$ 0,0 R$”: bug objetivo no formatador compartilhado. | Caso especial só zero; usar formatador monetário correto existente. | Corrigir unidade duplicada para todos os exports, em commit identificado como bug objetivo. | Local | Nenhum cálculo. |
| PL empilhado CW PI começa em 2.400. | Eixo automático; eixo sempre zero inclusive negativos; origem zero para valores não negativos. | Começar em zero quando a série é não negativa, mantendo negativos representáveis. | Local | Escalas financeiras novas. |
| Rótulos/legendas cortados e labels de KPI em duas linhas. | Reduzir fonte; mostrar todos; reduzir rótulos intermediários. | Rótulos finais legíveis, espaço para legenda e rótulos curtos no fluxo carteira. Dados continuam nos gráficos nativos e tabelas. | Local | Novo desenho de gráfico. |
| Cobertura PDD/NPL plotada sem valores quando denominador zero. | Exibir gráfico vazio; tratar zero como ausência; explicar motivo. | Mensagem contextual e componente compacto; distinguir ausência de denominador zero confirmado. Sem recalcular a razão. | Local | Alteração de métrica. |
| CW Kick Ass I tem fev/26 sob data-base ago/26. | Cortar histórico; usar data global; rotular competência de cada fundo. | Usar competência observada individual nos slides de fundo; consolidado mantém sua regra e histórico sua janela. | Local | Regra nova de competência comum. |
| “avançou 0,0 p.p.” e sínteses sem informação. | Remover todos os bullets; inventar conclusão; estado factual. | “Estável” quando arredondamento não indica variação; conservar conteúdo de crédito material. | Local | Novas conclusões de risco. |
| Duas capas, numerações independentes, títulos “Mercado de FIDCs” e “Soma de FIDCs — Consolidado”. | Alterar defaults; trocar template; costura apenas carteira. | Uma apresentação identificada pelo nome exato da carteira, títulos e rodapés coerentes, numeração final. Parâmetros opcionais com defaults intactos nos compartilhados. | Estrutural, por último | Seções Office e migração de masters. |
| Divisores, quadrantes vazios e tabelas esparsas. Retornos em dois slides são complementares, não duplicados. | Apagar zeros; número fixo; layout conforme componentes observados. | Compactar somente ausência comprovada e repetição literal. Zero permanece explicitamente representado. Usar 1×2/2×2 conforme conteúdo; consolidar retornos quando couber sem microtexto, paginar muitas séries. Divisores redundantes podem sair com fundo identificado em cada slide. | Estrutural, por último | Supressão por limiar, tipo de fundo ou tamanho de PL. |
| Curadoria repete texto igual em colunas; divergências podem ser materiais. | Resumir interpretação; remover critérios; agrupar igualdade literal. | Agrupar apenas conteúdo literalmente igual com identificação explícita dos fundos abrangidos; diferenças e ressalvas integrais continuam. | Estrutural, por último | Síntese documental inferencial. |
| Todos os slides Blank, números fixos, KPIs shapes. | XML novo de seções/campos; migrar masters; notas/estilo incremental. | Preservar objetos nativos e pacote atual; acrescentar notas de evidência e numeração final consistente. Validar PowerPoint real. | Local | Seções, campos automáticos, placeholders/master completo. |

## Página: diagnóstico estendido e escolhas

| Ponto / conclusão | Alternativas consideradas | Escolha e benefício | Magnitude | Depois |
|---|---|---|---|---|
| Caminho até dados longo, contexto e instruções repetidos nas cinco abas. | Redesenhar tudo; criar índice com JS; reorganizar componentes existentes. | Uma leitura de contexto; instruções operacionais dispensáveis saem; detalhes de competência/fonte/metodologia recolhidos. Dados antes de downloads secundários. Ordem dos gráficos e tabelas por tema preservada. | Local; ordem em commit estrutural final | Scrollspy/barra fixa. |
| Dois controles de período têm funções distintas. “12M” e janela carregada se confundem. | Fundir cálculo e visual; esconder diferença; explicitar janela efetiva. | Preservar cálculo/lookback e seleção visual; controle adicional recolhido, janela efetiva visível sem repetição em cada seção. Explicar histórico reduzido pela competência comum. | Local / estrutural | Corrigir intervalo inclusivo ou regras de cálculo. |
| Exportações têm maior contraste; Preparar/Baixar duplica ação. | Geração eager; download callable sem avisos; fluxo nativo com avisos preservados. | Usar APIs nativas 1.56 e geração sob demanda. Avaliar um clique para dados; para PPT só adotar se falhas e `export_warnings` continuarem visíveis. Alternativa conservadora: preparar e baixar dentro da área secundária compacta. | Local; posicionamento estrutural | Dependência/JS ou fluxo que esconda advertências. |
| Ativo/PL e indicadores zerados repetidos dominam a faixa. | Excluir crédito zerado; mostrar todas as métricas grandes; hierarquia compacta. | Menos KPIs principais (PL, carteira, subordinação); demais números em detalhe existente. Zero de crédito continua em resumo explícito e na aba própria; cobertura inválida com motivo. Variação/referência somente se já disponível e comparável. | Local | Calcular novas variações ou mínimo contratual sem evidência. |
| PL por cota achata subordinação e tem legendas em ordem diferente. | Substituir gráfico; mudar valores; refinar leitura preservando séries. | Preservar PL empilhado e opção percentual; ordem de legenda coerente e ajuda curta sobre composição. Complemento de subordinação só com série já calculada, sem inventar mínimo. | Local | Nova métrica/gráfico sem base existente. |
| Quatro camadas, 12 abas de fundos e “Inadimplência” em lugares diferentes. | Eliminar temas; tabs infinitas; seletor nativo de escopo. | Manter cinco temas reconhecíveis, selecionar escopo de forma compacta e persistente quando muitas opções, resumo de crédito na Estrutura e aprofundamento na aba Inadimplência. | Estrutural, por último | Alterar navegação global do app. |
| Acrescentado: cinco abas e todos os fundos são renderizados mesmo ocultos; Curadoria gera PPT em rerun. | Manter eager; lazy sem guardar escolhas; APIs `open` com estado persistido. | Adotar lazy nativo apenas onde seguro, conservando escolhas não-widget e erro/aviso. Curadoria da carteira pode adiar seu download pesado com opção cujo default mantém demais fluxos. | Local / estrutural | Refatoração de caches ou pipelines. |
| Acrescentado: cockpit não recebe filtro visual; dashboard filtrado mantém summary/latest e pode retornar histórico inteiro se não há interseção. | Recalcular; silenciar; rotular cortes distintos. | Preservar regras e indicar posição individual/comum e janela efetiva real; registrar preocupação financeira separadamente. | Local | Mudança de summary/filtro financeiro. |

## Sequência de commits e validação

1. Este documento, antes de editar fontes.
2. Reparos objetivos isolados: RDB/cópia/fontes, moeda/eixos, estados de dado; novos testes para cada contrato.
3. Nomes, datas, tipografia e opções exclusivas da carteira nos geradores compartilhados.
4. Página: concisão/contexto/ações secundárias, preservação de filtro e advertências.
5. Compactação de slides e costura do documento, separadamente; depois navegação/ordem da página.
6. Evidências antes/depois e PR. Não publicar/mergear nesta etapa.

Validação com os mesmos dados e filtros: Cloudwalk `7681d350f2994945ada0590b0e3703c2` (11), MELI Crédito `57f3418c1e9341e79edeef6086b8c25d` (3), Agis (Atlas) `e12bd979fbc24702bc0c50db169865ab` (1, consolidado = fundo). Supersim tem documentos, mas IME não está no cache local; será registrado como caso adicional sem base mensal, sem simular dado. Carteira 1 (101) é opcional conforme viabilidade.

Guardar por carteira contagem/títulos A/B/C/D, dados numéricos antes/depois, cobertura, componentes compactados e motivo; PPTX e PDF renderizado por LibreOffice disponível, abertura real no PowerPoint, gráficos e tabelas nativos. Na página: screenshots desktop/estreita/mobile, cinco abas, reruns, filtro, nomes longos, ausência/zero e downloads realmente baixados. Excel permanece numérico e auditável.

Baseline dos quatro arquivos de testes obrigatórios em `09730513`: **47 aprovados, 1 falha pré-existente**. `test_complete_portfolio_download_contains_comparison_and_documentary_notes` pressupõe download imediato e chave antiga, incompatíveis com o fluxo sob demanda atual. O commit documental registra a exceção; o teste será atualizado junto da mudança intencional de exportação, conferindo a apresentação produzida e suas notas. Nenhuma falha será descrita como aprovação. Os commits de implementação devem encerrar com os quatro arquivos verdes.

## Limites financeiros registrados

- Não mudar competência comum puxada por fundos defasados nem excluir fundo por conveniência visual.
- Não transformar zero em ausência ou ausência em zero; uma coluna toda NaN não informa “não aplicável”.
- Não recalcular snapshot ao filtrar histórico nem mudar fallback sem interseção nesta rodada.
- Preservar distinções de subordinação reportada, parcelas por cota e mínimo documental; não tratar as três como equivalentes.
- Critério atual de partes indisponíveis no PPT e erros de fonte permanece; o leitor terá aviso explícito.
- Datas em nomes de carteira, como “1T26”, são texto do usuário e não definem corte financeiro.
