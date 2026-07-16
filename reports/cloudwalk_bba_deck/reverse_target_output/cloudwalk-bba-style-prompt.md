# Prompt reverso para gerar o short deck Itaú BBA

Você é um analista sênior de crédito estruturado e designer de apresentações executivas. Gere um PPTX 16:9, em português, com no máximo 3 slides, usando apenas dados fornecidos em CSV/JSON e sem criar capa.

Objetivo: transformar uma memória de cálculo de custo financeiro de FIDCs em um short deck executivo no estilo Itaú BBA: denso, limpo, institucional, com tabelas e gráficos compactos.

Design obrigatório:
- Fundo off-white claro; tipografia Arial/Calibri; títulos no topo com logo pequeno à esquerda.
- Paleta: preto para barras/totais/headers, laranja Itaú para destaque/mezanino, cinza para subordinada/apoio, verde para aumentos/captações, vermelho para reduções/amortizações.
- Cada slide deve ter 2 a 4 caixas grandes com borda fina arredondada; o título de cada caixa fica encostado na borda superior, com uma linha horizontal continuando à direita.
- Tabelas: header preto com fonte branca; linha Total preta com fonte branca; valores negativos em vermelho; valores positivos em verde.
- Gráficos: simples, nativos/editáveis quando possível, com rótulos diretos e pouca legenda. Não usar cards decorativos, hero, gradientes ou ilustrações.
- Rodapé corporativo em todas as páginas: fonte, CloudWalk | Corporativo | Interno, número da página e logo pequeno.

Estrutura de slides:
1. Metodologia + breakdown por FIDC:
   - Título com a conclusão: custo financeiro FIDC recomposto, custo bruto, custo líquido e TPV estimado.
   - Painel esquerdo: fluxo metodológico em 5 etapas: Informe Mensal CVM; saldos mensais; tipo de cota; caixa/LFT; CDI B3. Ao lado de cada etapa, explicar em uma linha como entra no motor.
   - Resultado no rodapé do painel esquerdo: custo bruto e custo líquido após carry de caixa/LFT.
   - Painel direito: tabela fundo a fundo com FIDC, saldo médio, CDI+ ponderado, faixa CDI+ e custo do ano.
   - Bloco final: fórmula de TPV antecipado = (365 / prazo médio) x estoque médio de recebíveis, com duration e TPV.

2. Evolução FIDCs:
   - Painel superior: waterfall do PL de 2025: PL inicial + captações - amortizações + accrual/rentabilidade = PL final. Usar preto para totais, verde para aumento, vermelho para redução.
   - Ao lado: tabela de amortizações 2025 por FIDC, ordenada do maior para o menor, com total.
   - Painel inferior esquerdo: capital stack agregado comparando 31/12/25 vs data atual, empilhado por Sênior, Mezanino e Subordinada; incluir seta verde mostrando aumento de PL.
   - Painel inferior direito: captações 2026 por FIDC/mês/série/classe, com total.

3. Prognóstico / run-rate 2026:
   - Painel superior esquerdo: amortizações programadas em 2026 por fundo em barras horizontais.
   - Painel superior direito: duration jan-abr/26, com gráfico mensal e tabela por FIDC mostrando duration e estoque médio.
   - Painel inferior esquerdo: custo financeiro bruto YTD jan-abr/26 em barras mensais e tabela por FIDC com YTD e anualizado.
   - Painel inferior direito: CDI+ implícito bruto comparando 2025FY vs 2026 run-rate, em bps e com a taxa CDI+ textual acima de cada barra.

Regras analíticas:
- Citar quando a fonte é IME/CVM, documentos regulatórios locais, B3/Cetip MediaCDI ou input manual.
- CDI sempre mensal composto quando houver dado mensal.
- Não usar saldo médio anual único para custo mensal se houver captação/amortização intraperíodo; usar saldos por trecho/mês.
- Amortizações 2025 devem vir dos eventos efetivos reportados no IME/CVM quando o objetivo for reconciliar PL; amortizações futuras podem vir de cronogramas documentais, claramente rotuladas como programadas.
- Não inventar dado faltante: colocar asterisco e nota metodológica curta.
