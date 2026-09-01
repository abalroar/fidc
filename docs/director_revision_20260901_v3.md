# Revisão da diretoria de 01/09/2026 · v3

Publicação datada em Dados da Indústria → Dados e exportações. O PPTX completo tem 29 slides e o PPTX resumido tem duas lâminas.

## Alterações sobre a v2

- Remoção dos slides 23, 24, 26 e 33.
- Preservação dos slides 17 e 19, com quatro charts nativos recriados para eliminar o alerta de reparação do PowerPoint.
- Remoção dos chips laranja dos antigos slides 14 e 25; os oito blocos metodológicos usam uma caixa de texto por bloco.
- Conversão de títulos e cabeçalhos editoriais para caixa mista.
- Rodapés de fonte e metodologia alinhados à esquerda.
- Remoção de linhas cinza isoladas cuja função já era cumprida por espaço e alinhamento.

## Ordem editorial

1. Slides 1–9: visão da indústria e revisão de saldo, emissões e taxonomia.
2. Slides 10–13: base corrente de emissões CVM/SRE e posição do IBBA nas maiores ofertas.
3. Slides 14–23: ranking ANBIMA/IBBA, com originação, distribuição, visão por produto, FIDC, maiores operações e metodologia.
4. Slides 24–29: conclusões, prestadores, público-alvo, cotistas e apêndice.

## Reprodução e publicação

1. Gere ou recupere a v2 validada.
2. Prepare starter decks com as páginas mantidas e o mapa de edições.
3. Execute `scripts/refine_fidc_requested_revision_v3.mjs` no runtime do `@oai/artifact-tool`.
4. Renderize todas as páginas, execute `slides_test.py` e a verificação de fidelidade ao template.
5. Abra os dois arquivos no Microsoft PowerPoint e confirme abertura sem reparação; inspecione os slides 17 e 19.
6. Monte o ZIP, gere `release.json`, execute os testes do serviço e publique por merge.
7. Baixe anonimamente os três artefatos do site e compare SHA-256 ao manifesto.

O prompt completo está em `docs/prompt_atualizacao_pfpj_industria_fidc_v3.md` e dentro do pacote publicado.
