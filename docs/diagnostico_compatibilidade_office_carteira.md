# Compatibilidade com Office — Carteira

A validação nativa encontrou bloqueios no PPTX unificado e no Excel de estrutura baixados. A implementação foi interrompida pela regra 9, com fontes congelados em `ca008e8a`. Nenhuma correção de código ou reparação dos arquivos foi aplicada nesta investigação.

| Arquivo Cloudwalk | Resultado no Office | Evidência pública |
|---|---|---|
| PPTX unificado, 80 slides | PowerPoint ofereceu Repair; abertura cancelada. | [Alerta do PowerPoint](evidencias/carteira_export_e_pagina/reparo_powerpoint.png) |
| Excel de estrutura, emissões e RDB | Excel ofereceu recuperação de conteúdo. | [Alerta do Excel](evidencias/carteira_export_e_pagina/reparo_excel.png) |

Os blocos A/B/C/D do PPT, com 2/46/11/21 slides, abriram separadamente sem reparo. A concatenação desses mesmos blocos já pediu reparo antes da finalização. O pacote contém quatro masters de notas, com três entradas na lista da apresentação; a [documentação Microsoft](https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document#notes-master-part) estabelece no máximo um master de notas por pacote. A responsabilidade dessa incompatibilidade pelo alerta continua como hipótese a confirmar. O [diagnóstico completo do PPT](diagnostico_carteira_reparo_powerpoint.md) reúne a isolação, os hashes e a proposta para decisão.

No Excel, a recuperação não foi autorizada. Foi tentado o cancelamento pelo botão **No**; a chamada retornou timeout, e o estado posterior ainda não foi confirmado. A inspeção do pacote preservou as 66 células numéricas originais e seus formatos, com estilos byte a byte iguais. As oito diferenças textuais são grafias de nomes Cloudwalk entre as sessões; os CNPJs selecionados permanecem iguais. IDs, relações, tipos de conteúdo e referências de visualização não apresentaram inconsistências. Há uma aba nova de contexto. A causa do alerta continua pendente de isolamento nativo; a presença de autoFilter sem nome interno correspondente é apenas uma hipótese estrutural, sem causalidade comprovada. O alerta não foi atribuído a sheetViews.

Os 255 testes passaram, os arquivos foram legíveis pelas bibliotecas de inspeção e o LibreOffice renderizou o PPT Cloudwalk em PDF com 80 páginas. Essas verificações permanecem como evidências auxiliares. A aceitação no Office exige abertura dos arquivos efetivamente baixados sem Repair ou recuperação de conteúdo.

A retomada depende de decisão explícita. A proposta para o PPT é uma correção isolada do merger compartilhado, reutilizando um master de notas compatível e preservando notas, gráficos e planilhas internas; entradas incompatíveis devem parar com diagnóstico. A validação inclui Cloudwalk, MELI e uma carteira de um fundo, com nova abertura no Office. A proposta para o Excel aguarda o diagnóstico. Merge e publicação permanecem pendentes.
