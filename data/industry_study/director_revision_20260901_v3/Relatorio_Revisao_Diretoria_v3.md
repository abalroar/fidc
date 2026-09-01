# Revisão da Diretoria — 01/09/2026 · v3

Data-base do saldo: junho de 2026. O cenário exibido nos slides 4–6 exclui FIDC TAPSO e FIDC do Sistema Petrobras. A lista PF/PJ e as demais categorias continuam rastreáveis por CNPJ nos CSVs do pacote.

## Estrutura do PPTX completo

O deck executivo tem **29 slides**. Em relação à v2, foram excluídos os slides 23, 24, 26 e 33. Os slides 17 e 19 foram preservados e seus quatro gráficos de market share foram recriados como charts nativos novos, pois as relações OOXML importadas eram removidas pelo mecanismo de reparação do Microsoft PowerPoint.

A ordem final é:

1. slides 1–13: indústria, saldo, emissões, taxonomia e base corrente CVM/SRE;
2. slides 14–23: ranking ANBIMA/IBBA, com originação, distribuição, visão por produto, FIDC, maiores operações e metodologia de leitura;
3. slides 24–29: conclusões, prestadores, público-alvo, cotistas e apêndice de saldo e tipos.

Os títulos usam caixa mista. Rodapés de fonte e metodologia estão alinhados à esquerda. Foram retiradas linhas cinza isoladas que repetiam separações já dadas por espaço e alinhamento. Os chips laranja dos antigos slides 14 e 25 foram eliminados; cada bloco metodológico do antigo slide 25 passou a usar uma única caixa de texto editável.

## Resultado PF/PJ

Foram preservadas 26 decisões documentais. Sólido, ordem 11, e BizCapital Finpass PME, ordem 26, permanecem em Financeiro. Os demais 24 fundos formam Multicarteira Pulverizado PF/PJ.

- PL integral dos 24 fundos: **R$ 7.102.640.442,08**.
- Participação no PL ex-FIC original de R$ 821,362 bi: **0,86%**.
- Participação no cenário sem TAPSO/Petrobras de R$ 718,611 bi: **0,99%**.
- Financeiro antes da abertura, no universo original: **R$ 323,893 bi**.
- Financeiro após retirar os 24 fundos, no universo original: **R$ 316,791 bi**.
- Financeiro exibido após retirar PF/PJ e TAPSO: **R$ 275,294 bi**.
- Posições positivas reportadas na Tabela VIII: **578**; 5 fundos reportaram 25, 18 reportaram 24 e 1 reportou 21.
- Maior Top1 entre os 24 fundos: **0,4033%** dos direitos creditórios brutos.
- Exposição efetiva PF/PJ dentro do PL: **N/D**.
- Divisão PF versus PJ: **N/D**.
- Número total de devedores: **N/D**.

O regulamento foi lido integralmente para confirmar o mandato de crédito direto PF/PJ e separar produtos mantidos em Financeiro. A proxy Top1 usa a maior posição positiva da Tabela VIII sobre direitos creditórios brutos reconciliados. O critério não exige 25 posições. As posições reportadas não medem o total de devedores.

## Produtos mantidos em Financeiro

Consignado/INSS/FGTS, veículos, imobiliário, adquirência, agenda de recebíveis, cartão/meios de pagamento como produto principal e carteiras sem evidência suficiente permanecem em Financeiro. Sólido e BizCapital permanecem por decisão explícita do usuário.

## Demais categorias

O overlay documental aprovado é aplicado antes da regra de exibição:

- **Precatórios / ações:** Tipo Outros + Foco Poder Público.
- **Multicedente / multisacado:** Tipo Outros + Foco Multicarteira Outros ou Multicedente/Multissacado.
- **Recuperação / NP:** Tipo Outros + Foco Recuperação.
- **N/D:** linha que não fecha em uma categoria após o overlay.

Em jun/26, antes das exclusões de cenário, o mapa contém 511 CNPJs em Precatórios/ações, 351 em Multicedente/multissacado e 93 em Recuperação/NP.

## Novas emissões por setor

As ofertas CVM/SRE encerradas são cruzadas primeiro pelo CNPJ do fundo e depois pelo CNPJ da classe contra o mapa congelado de jun/26. FIC-FIDC fica fora dos setores. Emissor ausente do mapa fica em N/D. Em 2023, o mix observado é escalado ao total encerrado ANBIMA pelo fator **1,652276**.

No 1S26, o volume ex-FIC é **R$ 62,675 bi**:

| Categoria | R$ bi | % |
|---|---:|---:|
| Fomento Mercantil | 5,602 | 8,94% |
| Agro, Indústria e Comércio | 10,745 | 17,14% |
| Financeiro | 37,790 | 60,30% |
| Multicarteira Pulverizado PF/PJ | 2,603 | 4,15% |
| Precatórios / ações | 2,075 | 3,31% |
| Multicedente / multisacado | 1,220 | 1,95% |
| Recuperação / NP | 0,293 | 0,47% |
| N/D | 2,347 | 3,74% |

O PF/PJ do 1S26 contém 16 ofertas de 8 emissores. O N/D contém R$ 1,901 bi de 25 emissores não localizados no ledger de jun/26; a diferença até R$ 2,347 bi inclui emissores localizados cujo Tipo/Foco não fecha em outra categoria. Fundos extintos continuam no fluxo histórico; sem classificação histórica recuperada, ficam em N/D.

O total registrado no 1S26 é R$ 65,488 bi. A diferença de R$ 2,813 bi corresponde a FIC-FIDC fora dos oito setores.

## Regra temporal

A revisão usa uma **taxonomia congelada em jun/26**, retroaplicada aos saldos históricos e às ofertas. Essa escolha gera comparabilidade interna entre barras. Ela não representa necessariamente a classificação vigente em cada data. O prompt do pacote orienta a construir intervalos efetivos quando houver documentação histórica suficiente e exige decisão explícita para qualquer conflito.

## Prestadores e cores

Administração, gestão e custódia preservam o Top 5 verdadeiro e acrescentam Itaú e Kanastra como comparadores. Cada casa mantém a mesma cor nos seis gráficos. Itaú agrega Intrag/Kinea conforme a linhagem documentada; Kanastra agrega Limine conforme a curadoria.

## Validação de entrega

- PPTX completo: 29 slides, sem overflow no `slides_test.py`.
- PPTX resumido: 2 slides, sem overflow no `slides_test.py`.
- Fidelidade ao template: aprovada para os dois arquivos.
- Microsoft PowerPoint para macOS: os dois arquivos abriram diretamente, sem aviso de reparação.
- Slides 17 e 19: charts nativos visíveis no PowerPoint após abertura direta.
- O manifesto registra tamanho e SHA-256 de cada arquivo e de cada membro do ZIP.
