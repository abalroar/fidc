# Revisão da diretoria de 01/09/2026 · v2

Publicação datada em Dados da Indústria → Dados e exportações. O PPTX completo tem 33 slides. Ele preserva os antigos slides 1–9 e 24–27, remove os antigos 10–23 e 28–32, restaura 13 slides nativos do estudo ANBIMA/IBBA e mantém os antigos 33–39 como bloco final.

## Ordem editorial congelada

1. Slides 1–9: visão da indústria e revisão de saldo, emissões e taxonomia.
2. Slides 10–13: base corrente de emissões CVM/SRE e posição do IBBA nas maiores ofertas.
3. Slides 14–26: ranking ANBIMA de renda fixa e híbridos, incluindo visão por produto e destaque de FIDC.
4. Slides 27–33: conclusões, prestadores, público-alvo, cotistas e apêndices metodológicos.

O bloco ANBIMA vem de `outputs/deck_unificado/Panorama_FIDCs_com_Ranking_ANBIMA.pptx`, slides 32–42 e 52–53. Os gráficos, tabelas, workbooks incorporados e notas permanecem objetos nativos. O assembler rejeita títulos removidos, confirma os títulos centrais do bloco recuperado, valida a ordem e normaliza IDs legados de eixos sem alterar os dados.

## Decisões de dados preservadas

- PF/PJ: 24 CNPJs; Sólido e BizCapital permanecem em Financeiro.
- Saldo exibido: cenário sem TAPSO e Sistema Petrobras.
- Séries e emissões: taxonomia congelada em jun/26, retroaplicada.
- Emissões: CNPJ do fundo, depois classe, depois N/D; FIC fora; 2023 escalado ANBIMA.
- Exposição efetiva PF/PJ, divisão PF/PJ e total de devedores: N/D.

## Prestadores e cores

Administração, gestão e custódia preservam o Top 5 verdadeiro e acrescentam Itaú e Kanastra como comparadores. A cor identifica a casa de forma estável em todos os gráficos do slide 28:

| Casa | Hex |
|---|---|
| Itaú | `FF5500` |
| Kanastra | `7030A0` |
| QI Tech | `2456D6` |
| BTG Pactual | `1D4080` |
| Oliveira Trust | `7A1F3D` |
| Bradesco | `73787D` |
| Daycoval | `BEC2C5` |
| Genial | `6EC5E9` |
| Tercon | `8D9399` |
| CBSF / REAG | `73C6A1` |
| Finaxis | `5B6065` |
| BRL Trust | `454A4F` |
| Hemera | `30353A` |

## Reprodução e publicação

1. Gere as bases com `scripts/build_fidc_requested_revision.py`.
2. Gere o deck de 39 slides e as três lâminas com `scripts/build_fidc_requested_revision_artifacts.mjs`.
3. Monte o deck final com `scripts/assemble_fidc_requested_revision_v2.py`.
4. Renderize todos os slides, execute `slides_test.py` e `qa/audit_delivery.py`.
5. Execute `scripts/prepare_fidc_requested_revision_release.py`; o script valida hashes, prepara o ZIP em staging, valida o contrato de consumo e promove a pasta datada por rename.
6. Após o merge, baixe anonimamente os três artefatos do site e compare seus SHA-256 ao `release.json`.

O prompt completo de atualização futura está em `docs/prompt_atualizacao_pfpj_industria_fidc_v2.md` e dentro do pacote publicado.
