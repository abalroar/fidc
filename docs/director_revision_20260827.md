# Revisão da diretoria de 27/08/2026

Publicação datada em **Dados da Indústria → Dados e exportações → Revisão da
Diretoria · 27/08/2026**. O botão **PPTX completo revisado** entrega o arquivo de
39 slides aprovado nesta revisão. Também há três lâminas avulsas e um ZIP com
relatório, bases por CNPJ e verificações.

O botão PPTX do pacote executivo tradicional continua com seus anexos dinâmicos.
O suplemento não substitui `industry_export_bundle.json`, não altera o ledger
aprovado e não apresenta a triagem PF/PJ como pulverização comprovada. A data-base
é junho/2026; o total pulverizado validado permanece N/D.

## Reprodução

1. Executar `scripts/build_fidc_requested_revision.py --output-dir <saída>/bases`
   com o Python do projeto. As entradas são identificadas no manifesto de bases.
2. Usar `prepare_template_starter_deck.mjs` da skill Presentations com o arquivo
   `data/industry_study/generated_revision/industry_executive_revised.pptx` e os
   mapas em `data/industry_study/director_revision_templates/`. Preservar a
   apresentação de origem e produzir `template-starter.pptx` em cada workspace.
3. Executar `scripts/build_fidc_requested_revision_artifacts.mjs` com
   `--workspace <workspace> --data <saída>/bases/revision_payload.json
   --output <saída>/<arquivo.pptx>`. Para a apresentação completa, acrescentar
   `--full`. O runtime recebe `RUNTIME_NODE_MODULES` com `@oai/artifact-tool`.
4. Reconciliar números, renderizar os slides, conferir a apresentação exportada e
   gravar os relatórios de QA. O ZIP versionado contém o relatório e as evidências
   usadas nesta publicação; o ajuste de layout não deve alterar valores.
5. `scripts/prepare_fidc_requested_revision_release.py --source <saída>` confere
   hashes de fontes, bases, PPTX e resultados de QA. Prepara o pacote em staging,
   valida o conjunto e promove a pasta datada por rename. Recusa sobrescrever
   uma release já existente. Uma nova revisão requer nova data/versão.

## Contrato de consumo

`services/industry_requested_revision_export.py` verifica o manifesto, hashes,
tamanhos, quantidade de slides, conteúdo obrigatório e todos os arquivos do ZIP
antes de habilitar os três downloads. Não há cache desses bytes. Em caso de
falha, apenas o bloco da revisão fica indisponível; o pacote tradicional mantém
seu fluxo independente. Os botões usam `on_click="ignore"` para evitar refazer
as demais exportações ao baixar um arquivo materializado.

O teste público final deve baixar o PPTX pelo botão e comparar seu SHA-256 com
`director_revision_20260827/release.json`. Commit, push ou merge não comprovam,
sozinhos, que a aplicação já está servindo o arquivo novo.
