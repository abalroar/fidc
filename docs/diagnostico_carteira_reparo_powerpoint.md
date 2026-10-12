# Diagnóstico de abertura no PowerPoint — histórico e resolução

**Resolução atual:** `a5b2e8fb` corrige a concatenação para um único master de notas compatível. Após autorização para retomar, os downloads reais Cloudwalk/MELI/Agis abriram no PowerPoint sem reparo, com 80/33/22 slides. Notas, gráficos, planilhas internas, tabelas e fontes foram preservados. [Validação final e reversão](diagnostico_compatibilidade_office_carteira.md).

O restante deste documento registra a investigação inicial em `ca008e8a`. Naquele estado, o download `carteira-final.pptx` (80 slides) pediu reparo; o alerta foi cancelado e a implementação parou pela regra 9. As hipóteses e apontadores de código abaixo se referem à versão anterior à correção, sem reparação de arquivos pelo Office.

## Conclusão da investigação inicial

O pacote contém **quatro Notes Masters**. O padrão PresentationML admite no máximo **um** por apresentação. Essa incompatibilidade já aparece no deck obtido pela concatenação dos quatro blocos, antes do finalizer, e permanece no arquivo baixado. Os quatro blocos isolados **abriram sem reparo** no PowerPoint; a concatenação desses mesmos blocos **pediu reparo**, com cancelamento sem reparar. Portanto, a origem foi restringida ao **merger**, e a duplicação de Notes Masters é o mecanismo mais provável. A confirmação de toda a cadeia causal exige uma futura correção aprovada, seguida de abertura sem reparo.

Fonte primária: [Microsoft — estrutura PresentationML, Notes Master](https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document#notes-master-part), que reproduz o contrato ISO/IEC 29500:2016. A exigência textual é “A package shall contain at most one Notes Master part”.

A premissa anterior de que vários Notes Masters poderiam ser preservados no documento único estava incorreta. Reabrir pelo python-pptx e renderizar no LibreOffice não verifica essa restrição do Office.

## Evidência comparável

| Pacote | Slides | Notes Masters | Entradas na lista da apresentação | Resultado conhecido |
|---|---:|---:|---:|---|
| Baseline Cloudwalk | 122 | 1 | 1 | Abertura nativa verificada pelo agente principal |
| A atual | 2 | 1 | Lista ausente | **Abriu sem reparo** |
| B atual | 46 | 1 | Lista ausente | **Abriu sem reparo** |
| C atual | 11 | 1 | Lista ausente | **Abriu sem reparo** |
| D atual | 21 | 1 | Lista ausente | **Abriu sem reparo** |
| Concatenação atual, antes do finalizer | 80 | 4 | 3 | **PowerPoint pediu reparo** |
| Final congelado | 80 | 4 | 3 | Python-pptx e LibreOffice aceitam; isso é insuficiente para validar o Office |
| Download efetivo | 80 | 4 | 3 | **PowerPoint pediu reparo** |

SHA-256 do download que pediu reparo: `eb078ffebf6f2a3fba2a777f6b546d86caf9edc59b810b6e9699f7defa47fdf5`.

SHA-256 do pré-finalizer que também pediu reparo: `deb1685b6c0c9b2b4808711e70a23ac41bac12216fc2bd45a8acf95839fc8f37`.

A auditoria inicial recompôs o pré-merge apenas em memória, com os quatro blocos congelados. O agente principal salvou o pacote pré-finalizer para o ensaio nativo; **todos os parts têm o mesmo payload** da recomposição em memória. A comparação não supõe igualdade byte a byte de metadados temporais entre a matriz congelada e o download. Nenhum arquivo foi reparado.

## Hipóteses e grau de confiança

| Hipótese | Achado | Confiança como causa do alerta | Ação proposta, sem implementação |
|---|---|---|---|
| Mais de um Notes Master no documento | Quatro parts e quatro relacionamentos; a norma permite um. A situação nasce no merger e é conservada pelo finalizer. | **Alta**; incompatibilidade normativa confirmada, causalidade ainda sem ensaio corretivo | Compartilhar um único Notes Master compatível entre todas as notes slides, preservando integralmente seus textos e referências. |
| Registro parcial dos Notes Masters | `notesMasterIdLst` contém `rId88`, `rId89`, `rId90`; `rId9`, usado pela A e pelas novas notas de capa/referências, não consta. | **Média**, vinculada à primeira hipótese | A lista deve corresponder ao único master escolhido. Adicionar simplesmente uma quarta entrada manteria a violação da cardinalidade. |
| Finalizer introduziu relações quebradas ou IDs duplicados | Não foram encontrados ZIP members duplicados, XML malformado, rIds duplicados no mesmo owner, slide IDs duplicados, shape IDs duplicados no mesmo slide, referências XML r:id não resolvidas ou relacionamentos pendentes. | **Baixa** para essas falhas específicas | Manter esses testes; acrescentar cardinalidade/estrutura PresentationML e abertura nativa. |
| Restauração de native parts criou divergência de master/gráfico | Os **217 parts protegidos** do pré-merge são idênticos no final congelado. Não há delta protegido. A restauração inclui justamente os quatro Notes Masters inválidos como conjunto. | **Baixa** para corrupção introduzida pela cópia; **alta** para conservar o defeito | Preservar charts, embeddings, media e os masters/layouts visuais; tratar separadamente a normalização objetiva do master de notas. |
| IDs de extensão repetidos | Os quatro Notes Masters repetem `p14:creationId=2623252185`, pois são cópias do mesmo template. Há outras extensões herdadas, sem delta de identidade entre pré-merge e final. | **Baixa** como causa independente; reforça a duplicação | Eliminar a duplicação de notes masters, evitando inventar novos GUIDs ou mexer nos IDs de gráficos/slides. |
| Valores do Excel/gráficos foram alterados durante o download | Os charts XML não estão entre os parts diferentes entre final congelado e download. Nos 60 XLSX internos, o delta está só em `docProps/core.xml`; worksheets/dados permanecem iguais. | **Baixa** | Conservar a prova de valores e fontes, sem confundi-la com conformidade de embalagem. |

As probabilidades são classificações qualitativas, não estimativas estatísticas. Nenhuma hipótese equivale à alegação de que o arquivo abre sem reparo.

## Pontos no código

- `services/pptx_merge.py::_register_notes_masters`, linhas 307–337, enumera e registra masters copiados separadamente. O `continue` nas linhas 327–328 também ignora o registro na lista de um master que já possui relacionamento.
- `services/portfolio_ppt_presentation.py::finalize_portfolio_pptx`, linhas 197–202, força um cache para escolher um master dentre vários. Isso contorna a expectativa de singularidade do python-pptx e conserva o conjunto inválido.
- `services/portfolio_ppt_presentation.py::_restore_native_parts`, linhas 169–186, repõe os masters de notas originais junto aos demais parts protegidos. Uma normalização futura não pode ser desfeita por essa restauração.
- `tests/test_portfolio_ppt_document.py::test_finalization_reuses_existing_notes_master_after_merging_documentary_decks`, linha 169, verifica reabertura e preservação byte a byte de vários masters, sem impor o contrato de um único master. A correção desse teste deve ser assumida como mudança intencional de um bug de embalagem.

## Proposta da investigação inicial, posteriormente implementada

Os quatro Notes Masters atuais têm o **mesmo hash de XML** (`970fd6eed1e6c9ce4ccf270a6ed26e381f852de88d22d5eff8cf75f383b85311`). Os temas de notas `theme2` a `theme5` também são idênticos entre si (`3d2fb2883cfcaa95ba6d9bc7d6203b2487dec9c04cf22cc12ee8b899e7f505a5`). Portanto, há uma rota de correção pequena e objetiva: reutilizar a mesma cadeia de notas já existente, alterar apenas os relacionamentos das notes slides para esse master e remover as cópias duplicadas/registro excedente. Não exige migração dos masters/layouts visuais e pode conservar todos os textos das notas.

Uma futura implementação, **somente após autorização para retomar**, deve vir em commit isolado de embalagem Office. Limites propostos: um Notes Master; uma referência de apresentação coerente; notas integrais; nenhuma mudança nos gráficos, séries, números, tabelas ou no Slide Master; entrada com masters de notas distintos e incompatíveis deve parar com diagnóstico explícito, em vez de converter silenciosamente.

Validação para essa eventual retomada: matriz Cloudwalk/MELI/um fundo, comparação dos textos de notas e valores nativos, relações/content-types/cardinalidade, abertura dos blocos e do download final no PowerPoint **sem reparar**. PDF e python-pptx são provas auxiliares. Não será declarado “sem reparo” até a abertura nativa do arquivo realmente baixado.

## Evidências

- [Compatibilidade com Office](diagnostico_compatibilidade_office_carteira.md): causas, correções, validação final e limites.
- [Alerta de reparo no PowerPoint](evidencias/carteira_export_e_pagina/reparo_powerpoint.png): captura da abertura do download final.

O inventário técnico dos pacotes, as capturas da isolação e os logs permanecem no dossiê local de validação. Esse dossiê não integra a documentação pública. A investigação inicial deixou os fontes, os quatro blocos e o download intactos; a correção posterior foi isolada no commit indicado no início.
