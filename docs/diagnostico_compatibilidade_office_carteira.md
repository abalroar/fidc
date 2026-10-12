# Compatibilidade com Office — Carteira

**Resolvida em 12/10/2026.** Após a parada exigida pela regra 9 e a autorização explícita para retomar, as duas causas foram isoladas e corrigidas. Os três PPTX e os três Excel analíticos realmente baixados abriram no Office sem pedido de reparo ou recuperação. Nenhum arquivo reparado pelo Office foi usado como entrega.

## Causas e correções

**PowerPoint — `a5b2e8fb`.** Os quatro blocos abriam isolados; a concatenação copiava quatro masters de notas e registrava três na lista da apresentação. A [documentação Microsoft](https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document#notes-master-part) admite no máximo um por pacote. O merger agora reutiliza uma cadeia compatível, conferindo XML, tema, fontes, imagens e referências, e mantém um master, um relacionamento e uma entrada na lista. Cadeias incompatíveis param com diagnóstico. O finalizer perdeu o contorno por cache que tolerava vários masters. Notas exclusivas da capa repetida retirada são conservadas nas referências. [Investigação histórica e resolução](diagnostico_carteira_reparo_powerpoint.md).

**Excel — `6c1297d7`.** O writer analítico aplicava filtro de worksheet e filtro da Table sobre a mesma faixa. A falha também ocorria no arquivo anterior ao contexto de exportação e na versão antiga do produtor. Retirar apenas o filtro de worksheet das folhas com Table resolveu a abertura. Os filtros nativos das tabelas continuam disponíveis; Metodologia e Contexto da exportação conservam os filtros de worksheet. O helper de metadados permanece igual. A hipótese de que a nova aba Contexto era a causa foi descartada como explicação necessária.

As duas correções tratam bugs objetivos dos geradores compartilhados. O recorte RDB por CNPJ e as opções de compactação permanecem exclusivos do fluxo da carteira. Cálculos, cache de dados, competência, integrações e regras financeiras não foram alterados.

## Arquivos efetivamente baixados

| Carteira | PPTX no PowerPoint | Excel analítico no Excel | Dados recebidos e conferidos | PDF do PPTX baixado |
|---|---|---|---|---:|
| Cloudwalk, 11 fundos | Sem reparo; 80 slides | Sem recuperação; 6 abas | Resumo XLSX, base XLSX, CSV ZIP, estrutura XLSX e PPTX | 80 páginas |
| MELI Crédito 0, I e II, 3 fundos | Sem reparo; 33 slides | Sem recuperação; 6 abas | Os cinco arquivos | 33 páginas |
| Agis (Atlas), 1 fundo | Sem reparo; 22 slides | Sem recuperação; 6 abas | Os cinco arquivos | 22 páginas |

Os três PPTX e três Excel analíticos gerados diretamente pelos produtores também abriram sem alerta. O resumo Cloudwalk final baixado abriu no Excel; a abertura individual dos demais resumos/bases finais não foi concluída. Esses arquivos foram conferidos por estrutura, números, tipos, formatos e seleção. Os CSVs do ZIP foram extraídos e comparados.

Capturas: [Cloudwalk PPT](evidencias/carteira_export_e_pagina/cloudwalk_office_powerpoint.png), [Cloudwalk Excel](evidencias/carteira_export_e_pagina/cloudwalk_office_excel.png), [MELI PPT](evidencias/carteira_export_e_pagina/meli_office_powerpoint.png), [Agis PPT](evidencias/carteira_export_e_pagina/agis_office_powerpoint.png), [Agis Excel](evidencias/carteira_export_e_pagina/agis_office_excel.png).

## Preservação e testes

- **PPT:** 492 partes protegidas conferidas byte a byte — 204/174/114 por carteira — preservam gráficos, planilhas internas, mídias, masters visuais, layouts e fontes. Células das tabelas iguais às dos arquivos congelados; nenhuma linha de notas perdida. Foram retiradas somente cópias redundantes da cadeia de notas e temas órfãos dessa cadeia.
- **Excel analítico:** 792 células conservam valor, tipo, formato e estilo, incluindo 88 números nativos e zero válido. Snapshot e RDB mantêm os CNPJs exatos como strings. As quatro tabelas nativas por arquivo permanecem. Os 54 parts originais fora as três declarações necessárias à aba de contexto são idênticos entre versões sem e com contexto.
- **Testes:** 53 no commit Excel isolado, 72 no commit PPT e 271 na regressão integrada. Os quatro arquivos obrigatórios continuam verdes. Incluídos casos de cadeia de notas incompatível, tema/fonte, imagem, URL, equivalência de identificadores locais e notas preservadas.

A prova congelada usa os mesmos insumos. No navegador real, CDI adicional apareceu em oito tabelas Cloudwalk e três MELI pelo resolvedor existente; Agis manteve o benchmark do replay. Retornos das cotas e gráficos financeiros conservados. Pequenas diferenças binárias de serialização do cache CSV em MELI/Agis foram registradas na [matriz](evidencias/carteira_export_e_pagina/matriz.json); não mudam valores exibidos. A fonte diária efetivamente usada por taxa CDI ainda não é persistida no PPTX.

## Histórico e reversão

Em `ca008e8a`, o [PPTX ofereceu Repair](evidencias/carteira_export_e_pagina/reparo_powerpoint.png) e o [Excel ofereceu recuperação](evidencias/carteira_export_e_pagina/reparo_excel.png). Os alertas foram cancelados. Após o cancelamento, o Excel deixou de responder; o usuário confirmou ausência de arquivos com alterações não salvas e autorizou seu reinício. A investigação e os arquivos anteriores permanecem preservados.

Reverter `6c1297d7` restaura o filtro sobreposto do Excel. Reverter `a5b2e8fb` como unidade restaura a concatenação com múltiplos masters de notas; merger e finalizer desse commit precisam voltar juntos. Os dois commits são independentes entre si. Qualquer reversão exige regeneração e nova abertura nativa antes de aceitar os arquivos.

Implementação e validação locais concluídas nos limites acima. PR em rascunho para revisão; merge, publicação e validação do app público permanecem pendentes.
