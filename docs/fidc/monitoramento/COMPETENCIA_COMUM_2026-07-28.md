# Competência comum da carteira Cloudwalk — diagnóstico de 28/07/2026

## Conclusão

O bloqueio integral do agregado/PPTX era impreciso. A implementação intersectava as competências dos 11 CNPJs carregados e mantinha no denominador o Cloudwalk Kick Ass II, cancelado em 31/10/2024. O Cloudwalk Bela começou a reportar em 2025; os dois fundos não possuem competência sobreposta na janela atual. A interseção dos 11 ficava vazia.

O ajuste exclui da checagem somente o fundo cancelado antes da competência analisada. O universo atual passa a ter 10 fundos elegíveis e última competência comum em fev/26. Mai/26 e jun/26 permanecem incompletas: Cloudwalk Kick Ass I e Cloudwalk Akira II não possuem informe mensal localizado após fev/26.

## Implementações anteriores

| Fluxo | Rotina | Critério anterior |
|---|---|---|
| Cockpit no carregamento da carteira | `tabs/tab_fidc_monitoring.py::_portfolio_reference_competencia` e `_render_cockpit_tab` | Contagem por competência dos fundos carregados; o cockpit chamava a rotina com cobertura mínima de 100%. Não consultava situação cadastral. Quando nenhuma competência atingia 100%, omitia o comparativo com mensagem genérica. |
| Agregado e PPTX | `services/fundonet_portfolio_dashboard.py::_common_competencias` por meio de `build_portfolio_dashboard_bundle` | Interseção literal de `dashboard.competencias` de todos os dashboards. Não consultava situação cadastral, cancelamento, liquidação, prazo regulatório ou motivo da ausência. A interseção vazia interrompia a construção do bundle antes do botão de PPTX. |

As duas checagens eram distintas e usavam conjuntos de competência derivados da mesma extração Fundos.NET. O critério cadastral e a mensagem agora vêm de `services/portfolio_competence.py` nos dois fluxos.

## Evidência por fundo

Unidade: classe/fundo identificado pelo CNPJ usado no Informe Mensal FIDC. Presença significa registro na Tabela I do arquivo oficial da competência.

| Fundo | CNPJ | Situação cadastral em 28/07/2026 | Mai/26 | Jun/26 | Tratamento |
|---|---|---|---:|---:|---|
| Cloudwalk Kick Ass I | 42.085.816/0001-05 | Em Liquidação desde 27/03/2026; último informe localizado em fev/26 | Não | Não | Elegível; impede mai/26 e jun/26 |
| Cloudwalk Akira I | 42.085.830/0001-09 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk Kick Ass II | 42.102.603/0001-44 | Cancelado em 31/10/2024 | Não | Não | Fora do denominador após out/24 |
| Cloudwalk Akira II | 44.124.617/0001-94 | Em Liquidação desde 16/04/2026; último informe localizado em fev/26 | Não | Não | Elegível; impede mai/26 e jun/26 |
| Cloudwalk Big Picture I | 54.218.673/0001-41 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk Big Picture II | 54.218.941/0001-25 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk Big Picture III | 54.219.179/0001-00 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk Big Picture IV | 54.248.022/0001-02 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk A.I. | 57.609.282/0001-46 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk PI | 60.356.171/0001-80 | Em Funcionamento Normal | Sim | Sim | Elegível |
| Cloudwalk Bela | 62.393.679/0001-83 | Em Funcionamento Normal | Sim | Sim | Elegível |

Cobertura observada em mai/26 e jun/26: 8 reportantes de 10 fundos elegíveis, ou 80% por quantidade. O sistema mantém o denominador de 10; nenhuma ponderação por PL ou materialidade foi aplicada.

## Fontes e atualização

- CVM, cadastro de fundos e classes: `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip`, baixado em 28/07/2026, SHA-256 `177485618af2239f2b451972fb6e46b217580b50a3bf70cdf01938882e415f93`.
- CVM, Informe Mensal FIDC mai/26: `https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202605.zip`, baixado em 28/07/2026, SHA-256 `4cb618761bd89f63509a5df784e4e417432bc941e3eed86b050371f470d27fee`.
- CVM, Informe Mensal FIDC jun/26: `https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202606.zip`, baixado em 28/07/2026, SHA-256 `a9ff9b3933b281507e115df8a664ecfee4580c3d3a9d905bc19a7c60efa013ed`.
- Fundos.NET, extração direta de jan/26 a jun/26 executada em 28/07/2026. A extração confirmou mai/26 e jun/26 para os oito reportantes e confirmou somente jan/26 e fev/26 para Kick Ass I e Akira II. Dois timeouts transitórios foram resolvidos em nova tentativa. Kick Ass II retornou ausência de documentos no intervalo.
- RCVM 175, Anexo Normativo II, art. 27, III: prazo de 15 dias após o fim do mês para o informe mensal.
- Ofício-Circular CVM/SSE 1/2026, item 19: a obrigação periódica permanece durante a liquidação até o cancelamento.
- RCVM 175, Anexo Normativo II, art. 54: o plano de liquidação pode dispensar informações periódicas. Nenhuma evidência local de dispensa específica foi localizada para Kick Ass I ou Akira II.

## Classificação dos critérios

| Critério | Classificação | Diagnóstico e tratamento |
|---|---|---|
| Exigir dado de 100% do universo selecionado | Impreciso e ajustado | O universo incluía fundo cancelado antes da competência. A regra passou a exigir 100% dos fundos elegíveis. |
| Excluir fundo cancelado antes da competência | Correto e adotado | A obrigação encerra no cancelamento. O fundo permanece visível na auditoria, com motivo e data da exclusão. |
| Excluir fundo registrado após a competência | Correto e adotado | A data de registro posterior comprova que o fundo ainda não integrava o universo reportante. Sem data suficiente, o sistema conserva o fundo no denominador. |
| Excluir automaticamente fundo “Em Liquidação” | Ambíguo; requer evidência documental | A situação cadastral mantém a obrigação em regra. A dispensa do art. 54 depende do plano de liquidação. A implementação conserva o fundo no denominador enquanto a dispensa não estiver documentada. |
| Aceitar consolidado parcial por atraso | Ambíguo; requer decisão de produto | A opção estrita preserva comparabilidade e usa a última competência completa. Uma opção por cobertura mínima ou materialidade exigiria limiar por quantidade e PL, identificação de parcialidade em todos os artefatos e aprovação de produto. Nenhuma tolerância econômica foi introduzida. |
| Tratar competência ainda dentro do prazo | Correto e adotado | O sistema identifica o prazo de 15 dias e usa a última competência completa. A mensagem informa que o período recente ainda está no prazo; valores ausentes não são imputados. |
| Mensagem genérica sem fundos responsáveis | Impreciso e ajustado | A mensagem agora lista fundo, CNPJ, situação cadastral, prazo e fundos excluídos do denominador. |

## Critério implementado

1. A competência de referência é a mais recente presente em 100% dos fundos elegíveis.
2. Fundo cancelado em mês anterior à competência ou registrado depois dela fica fora do denominador e permanece na tabela de auditoria, com a evidência temporal da exclusão.
3. Fundo em funcionamento ou em liquidação permanece elegível. Uma futura exclusão por plano de liquidação exige evidência documental específica.
4. Atraso conhecido durante o prazo regulatório não autoriza imputação nem consolidado parcial; a última competência completa continua disponível.
5. Após o prazo, a mensagem identifica os fundos sem informe localizado.
6. O cockpit e o bundle usado pelo PPTX usam a mesma avaliação compartilhada.
7. A seleção de competências do cockpit respeita o período solicitado; competências históricas fora do período não são mais recolocadas por fallback.
8. Cache com competência solicitada ausente consulta novamente o Fundos.NET quando é parcial, quando nunca houve consulta à fonte ou quando a última consulta completa ocorreu há pelo menos 24 horas. O intervalo evita consultas repetidas durante o mesmo prazo regulatório e permite capturar publicação posterior.

## Validação

- Reprodução anterior: 11 dashboards Cloudwalk carregados; `build_portfolio_dashboard_bundle` retornava `ValueError` por interseção vazia.
- Reprodução corrigida: Kick Ass II excluído do denominador; 10 fundos elegíveis; referência em fev/26; cobertura de 8/10 em mar/26, abr/26, mai/26 e jun/26.
- Export real em memória: PPTX gerado com 44.594 bytes, 2 slides e competência fev/26.
- Testes focados: cenários de cancelamento, registro posterior, liquidação, prazo regulatório, renovação de cache, mensagens nominativas, cockpit, bundle e export.
- Suíte integral: 852 testes e 2 subtestes aprovados em 28/07/2026.

## Limitações

- A fotografia cadastral não comprova dispensa aprovada em plano de liquidação. Essa decisão exige documento específico.
- A regra de materialidade permanece pendente de decisão de produto. O código continua estrito em 100% dos elegíveis.
- O diagnóstico de presença usa o Informe Mensal publicado; não atribui causa operacional ao administrador além da ausência observada.
