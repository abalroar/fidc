# Reclassificação documental do bucket `Outros`

## Por que existe

A curadoria histórica Top 20 fechou 143 CNPJs — os vinte maiores de cada Tipo
ANBIMA exibido em dezembro de 2023, dezembro de 2024, dezembro de 2025 e junho
de 2026. Ela reduziu `Outros` em R$ 56,0 bi em jun/26, mas o bucket continuou
concentrando mais de um terço do patrimônio do mercado, distribuído em uma
cauda longa que o corte por Top 20 não alcança.

Esta rodada estende a mesma metodologia à cauda: a fila passa a conter **todos**
os CNPJs exibidos como `Outros` nas quatro competências, ordenados pelo maior PL
observado, e exclui os que já possuem decisão no ledger analítico.

## Camadas

- `industry_outros_reclassification_queue.csv`: fila por CNPJ, com PL máximo,
  competências observadas, Tipo/Foco oficiais e o indicador `is_np` da CVM.
- `industry_outros_reclassification_conclusions.csv`: conclusão documental por
  CNPJ, com documentos lidos, páginas, trecho decisivo, escores por família,
  status, confiança e justificativa.
- `industry_top20_pending_curation.csv`: encerramento manual dos CNPJs que a
  revisão Top 20 deixou em aberto.
- `taxonomy_review_actions.csv` / `taxonomy_review_audit.csv`: ledger analítico
  e trilha de auditoria já existentes, alimentados por
  `apply_fidc_documentary_decisions.py`.
- Base CVM/ANBIMA: campos oficiais preservados, sem qualquer sobrescrita.

## Aquisição de documentos

Para cada CNPJ o pipeline busca no FundosNet o regulamento mais recente com
status ativo. Quando não há regulamento publicado, ou quando a leitura do
regulamento não fecha a decisão, um segundo passe baixa os documentos
complementares disponíveis — prospectos, suplementos, anexos, atas de
assembleia, comunicados, demonstrações financeiras e informes. Os arquivos ficam
em cache local, de modo que reprocessar a classificação não repete download.

Cada PDF é lido página a página com `pypdf`; quando a camada de texto é
insuficiente, a extração recai em `pdfplumber`. PDF sem texto extraível fica
registrado como limitação explícita e o CNPJ permanece `pendente`.

## Como a decisão é formada

Cada família econômica de direitos creditórios tem vocabulário próprio. Uma
ocorrência vale mais ou menos conforme a seção da página em que aparece:

- páginas que contêm definição, política de investimento, critérios de
  elegibilidade, condições de cessão, objetivo, composição da carteira,
  público-alvo ou anexo descritivo valem **o dobro**;
- páginas de fatores de risco e de cobrança de créditos inadimplidos valem
  **35%**, porque enumeram famílias sem definir o mandato;
- as demais valem 1.

Sobre os escores incide uma tabela de dominância declarada par a par, que
expressa relação econômica e não numérica. A cédula de crédito bancário é o
instrumento que formaliza o financiamento de veículo, e todo regulamento de
consignado cita receitas e entes públicos: quando a família específica ultrapassa
o limiar decisivo, ela absorve a genérica ainda que o vocabulário genérico
apareça com mais frequência. A absorção é limitada por uma tolerância, de modo
que uma família genérica muito mais presente não é apagada.

Precatórios e direitos judiciais privados são famílias distintas: requisitórios
contra entes públicos levam Foco `Poder Público`, enquanto créditos judiciais e
honorários de origem privada levam Foco `Recuperação`. Ambos compartilham a
taxonomia funcional `Judicial/Precatórios/NPL`.

## Estados

| Status | Quando é usado |
|---|---|
| `aprovado` | Uma família domina a definição do lastro, ou o mandato é multicarteira com predominância mensurável de um Tipo ANBIMA. A decisão entra no mix analítico. |
| `em_revisao` | Há líder identificado, mas a família seguinte permanece próxima, ou nenhuma família atingiu evidência suficiente na seção decisiva. Fica registrada com o motivo e não altera o mix. |
| `pendente` | Nenhum documento com camada de texto foi obtido. |
| `rejeitado` | A hipótese de classificar o CNPJ como FIDC direto está incorreta — regulamento de fundo de investimento financeiro sem mecânica de cessão, ou veículo que detém apenas cotas de outros fundos. |

Um mandato que enumera quatro ou mais famílias concorrentes é multicarteira. Se
60% ou mais da evidência concorrente pertencer a um único Tipo ANBIMA, a
classificação fecha nesse tipo com o Foco multicarteira correspondente; caso
contrário permanece em `Outros / Multicarteira Outros`.

## Perímetro

Um regulamento de fundo de investimento financeiro pode mencionar direitos
creditórios, porque pode deter cotas de FIDC. O que ele nunca tem é a mecânica da
cessão: critérios de elegibilidade, condições de cessão, cedente, contrato de
cessão ou documentos comprobatórios. A detecção de perímetro usa exatamente essa
diferença, e não o nome do fundo.

## Continuidade

O pipeline nunca reinicia o trabalho. A fila exclui todo CNPJ que já tenha
decisão no ledger, e `apply_fidc_documentary_decisions.py` preserva aprovações
existentes: sobrescrever uma aprovação exige `--allow-override` acompanhado de
`--override-reason`, que fica gravado nas notas e na auditoria.

## Limitações

A conclusão descreve o mandato permitido pelo documento. A materialidade efetiva
de cada família depende da carteira observada em cada competência. Nome de fundo
não é evidência e não determina classificação em nenhuma etapa.
