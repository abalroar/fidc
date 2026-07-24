# Auditoria pública — instrumentos de renda fixa do slide 4

Data da auditoria: 24/jul/2026.

## Escopo medido no slide

O slide 4 usa `oferta_resolucao_160.csv`, arquivo do rito automático da
Resolução CVM 160. O cálculo considera uma oferta por `Numero_Requerimento`,
`Tipo_Oferta = Primária`, `Status_Requerimento = Oferta Encerrada`,
`Data_Encerramento` dentro do período e `Valor_Total_Registrado > 0`.

Os números públicos da ANBIMA combinam informações da ANBIMA e da CVM e são
descritos como captação, emissão ou volume de ofertas encerradas. Esse universo
abrange outros ritos e pode refletir volume efetivamente colocado, revisões de
base e uma regra temporal diferente da data de encerramento usada no slide.

## Comparação anual

Valores em R$ bilhões.

| Ano | Instrumento | Slide 4 | Referência ANBIMA | Diferença | Diferença % |
|---|---|---:|---:|---:|---:|
| 2023 | Debêntures | 223,1 | 236,6 | -13,5 | -5,7% |
| 2023 | CRI | 40,1 | 47,7 | -7,6 | -15,9% |
| 2023 | Notas comerciais | 25,4 | 27,9 | -2,5 | -8,9% |
| 2023 | CRA | 42,3 | 43,3 | -1,0 | -2,3% |
| 2024 | Debêntures | 472,4 | 472,5 | -0,1 | -0,0% |
| 2024 | CRI | 57,7 | 58,9 | -1,2 | -2,1% |
| 2024 | Notas comerciais | 45,8 | 43,6 | +2,2 | +5,0% |
| 2024 | CRA | 41,8 | 41,3 | +0,5 | +1,3% |
| 2025 | Debêntures | 453,7 | 492,8 | -39,1 | -7,9% |
| 2025 | CRI | 54,3 | 49,0 | +5,3 | +10,9% |
| 2025 | Notas comerciais | 53,6 | 51,8 | +1,8 | +3,4% |
| 2025 | CRA | 45,0 | 46,2 | -1,2 | -2,7% |

Referências:

- ANBIMA, apresentação anual de 2024, página 21: tabela comparável para 2023
  e 2024.
- ANBIMA, balanço anual de 2025: debêntures R$ 492,8 bi, notas comerciais
  R$ 51,8 bi, CRI R$ 49,0 bi e CRA R$ 46,2 bi.

## Checkpoint de 2026

O recorte do slide, reexecutado até 31/mai/2026, gera R$ 127,7 bi em
debêntures, R$ 17,2 bi em CRIs, R$ 18,8 bi em notas comerciais e R$ 5,5 bi em
CRAs. A publicação da ANBIMA para o mesmo período informa, respectivamente,
R$ 146,3 bi, R$ 15,7 bi, R$ 17,1 bi e R$ 5,4 bi.

| Instrumento | CVM automático até mai/26 | ANBIMA até mai/26 | Diferença % |
|---|---:|---:|---:|
| Debêntures | 127,7 | 146,3 | -12,7% |
| CRI | 17,2 | 15,7 | +9,5% |
| Notas comerciais | 18,8 | 17,1 | +10,1% |
| CRA | 5,5 | 5,4 | +2,0% |

O slide mostra R$ 148,0 bilhões de debêntures até jun/26, apenas R$ 1,7
bilhão acima da estatística pública da ANBIMA até maio. A série precisa de
reconciliação por requerimento antes de sustentar uma conclusão sobre o
primeiro semestre de 2026.

## Diagnóstico

1. **2024 está materialmente reconciliado.** As diferenças ficam entre 0,0% e
   5,0%, faixa compatível com revisão de base e diferença entre valor registrado
   e volume captado.
2. **2023 apresenta subcobertura relevante.** O arquivo
   `oferta_resolucao_160.csv` representa o rito automático iniciado em 2023; o
   mercado daquele ano ainda contém ofertas de outros ritos. A diferença chega
   a 15,9% em CRIs.
3. **2025 contém divergência material em debêntures e CRIs.** O slide fica
   R$ 39,1 bilhões abaixo da ANBIMA em debêntures e R$ 5,3 bilhões acima em
   CRIs. A comparação requer ponte por oferta, rito e valor colocado.
4. **2026 confirma diferença de perímetro antes do fechamento de junho.** O
   checkpoint de maio diverge 12,7% em debêntures e aproximadamente 10% em CRIs
   e notas comerciais.

## Uso recomendado

O slide pode ser apresentado como recorte de ofertas primárias encerradas no
rito automático da RCVM 160, medidas pelo valor total registrado e pela data de
encerramento. Uma afirmação sobre o mercado total de emissões exige a união
deduplicada dos arquivos `oferta_distribuicao.csv` e
`oferta_resolucao_160.csv`, além da reconciliação do valor registrado com o
volume captado informado pela ANBIMA.

## Fontes públicas

- CVM, conjunto Ofertas Públicas de Distribuição:
  https://dados.cvm.gov.br/dataset/oferta-distrib
- ANBIMA, balanço anual de 2024:
  https://www.anbima.com.br/data/files/56/66/80/A5/DAE849109036A849B82BA2A8/Coletiva_MercadodeCapitais_2024_apresentacao.pdf
- ANBIMA, balanço anual de 2025:
  https://www.anbima.com.br/pt_br/noticias/ofertas-no-mercado-de-capitais-atingem-r-838-8-bilhoes-e-batem-recorde-em-2025-8A2AB2AB9BE369BE019BE74FB44F6E18-00.htm
- ANBIMA, janeiro a maio de 2026:
  https://www.anbima.com.br/pt_br/imprensa/mercado-de-capitais-movimenta-r-283-bilhoes-em-ofertas-puxado-por-fidcs-hibridos-e-acoes-8A2AB2AB9EB9C3A5019ED1B250202429-00.htm
