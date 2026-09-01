# Revisão da diretoria de 01/09/2026

Publicação datada em Dados da Indústria → Dados e exportações. O PPTX completo mantém 39 slides e altera 4, 5, 6, 34, 38 e 39. O suplemento de três lâminas contém prestadores, saldo/emissões e a decisão PF/PJ.

## Reprodução

1. Execute scripts/build_fidc_requested_revision.py com data/industry_study e um diretório de saída para as bases.
2. Use os PPTXs da release anterior como template-starter.pptx nos workspaces completo e compacto.
3. Execute scripts/build_fidc_requested_revision_artifacts.mjs com o runtime da skill Presentations. Use --full para o arquivo de 39 slides.
4. Renderize os dois PPTXs, execute slides_test.py e rode qa/audit_delivery.py.
5. Execute scripts/prepare_fidc_requested_revision_release.py. O script valida hashes das entradas, bases, PPTXs e QA, prepara o ZIP em staging, valida o contrato de consumo e promove a pasta datada por rename.
6. Teste o download anônimo do site e compare o SHA-256 ao release.json.

## Decisões congeladas

- PF/PJ: 24 CNPJs; Sólido e BizCapital permanecem em Financeiro.
- Saldo exibido: cenário sem TAPSO e Sistema Petrobras.
- Séries e emissões: taxonomia congelada em jun/26, retroaplicada.
- Emissões: CNPJ do fundo, depois classe, depois N/D; FIC fora; 2023 escalado ANBIMA.
- Exposição efetiva PF/PJ, divisão PF/PJ e total de devedores: N/D.

O prompt completo de atualização futura está em docs/prompt_atualizacao_pfpj_industria_fidc.md e dentro do pacote publicado.
