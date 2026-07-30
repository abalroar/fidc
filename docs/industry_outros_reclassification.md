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

## Resultado desta rodada

A fila cobriu **2.158 CNPJs** exibidos como `Outros` nas quatro competências.
Foram lidas **121.414 páginas**: 1.930 CNPJs concluídos pelo regulamento, 45 por
documentos complementares e 183 sem documento com camada de texto.

| Status | CNPJs | PL máximo observado |
|---|---:|---:|
| `aprovado` | 1.437 | R$ 245,75 bi |
| `em_revisao` | 520 | R$ 76,36 bi |
| `pendente` | 194 | R$ 12,70 bi |
| `rejeitado` | 7 | R$ 2,15 bi |

Das 1.437 aprovações, **453 saem de `Outros`** (R$ 71,7 bi de PL máximo) — 247
para `Agro, Indústria e Comércio`, 202 para `Financeiro` e 4 para
`Fomento Mercantil`. As **984** restantes permanecem em `Outros` porque é onde o
risco descrito cabe, mas deixam de ser indistintas: 699 com foco
`Poder Público`, 156 com `Recuperação` e 129 multicarteira com evidência.

Efeito no mix analítico, comparado à fotografia oficial ANBIMA:

| Competência | Outros oficial | Outros curado | Redução | Cobertura do PL por decisão aprovada |
|---|---:|---:|---:|---:|
| dez/23 | R$ 171,9 bi (37,2%) | R$ 135,5 bi (29,3%) | R$ 36,4 bi | 72,5% |
| dez/24 | R$ 261,6 bi (38,3%) | R$ 202,8 bi (29,7%) | R$ 58,7 bi | 71,8% |
| dez/25 | R$ 371,2 bi (44,6%) | R$ 281,0 bi (33,7%) | R$ 90,2 bi | 67,9% |
| jun/26 | R$ 355,7 bi (40,4%) | R$ 246,5 bi (28,0%) | R$ 109,3 bi | 66,4% |

A rodada anterior havia reduzido `Outros` em R$ 56,0 bi em jun/26; esta rodada
leva a redução a R$ 109,3 bi e derruba a participação do bucket de 40,4% para
28,0% do patrimônio da competência.

O ledger analítico passou de 137 para **2.299 decisões** por CNPJ, todas com
evidência, página, justificativa, nível de confiança e trilha de auditoria.

## Revisão automática

`report_fidc_outros_reclassification.py` grava
`industry_outros_consistency_review.csv` com os casos que merecem olhar humano,
ordenados pelo patrimônio envolvido:

- **50** focos minoritários dentro do mesmo gestor e mesmo foco oficial — quando
  um gestor tem três ou mais fundos com o mesmo foco oficial e apenas um recebeu
  destino diferente dos demais;
- **13** famílias de fundos irmãos (`JC 4870` e `JC 4870 IV`, por exemplo) com
  Tipos ANBIMA divergentes entre si;
- mudanças de Tipo oficial fechadas com confiança apenas média, listadas pelas
  25 maiores.

## Continuidade

O pipeline nunca reinicia o trabalho. A fila exclui todo CNPJ que já tenha
decisão no ledger, e `apply_fidc_documentary_decisions.py` preserva aprovações
existentes: sobrescrever uma aprovação exige `--allow-override` acompanhado de
`--override-reason`, que fica gravado nas notas e na auditoria.

## Republicação do bundle pendente

O bundle Office publicado em `data/industry_study/generated_revision/` registra
os hashes SHA-256 do ledger e da auditoria de taxonomia no momento da
publicação, e a aplicação falha fechada quando a curadoria muda depois disso.
Como esta rodada alterou o ledger, o bundle publicado ficou defasado e
`test_industry_exports_are_valid_office_files` acusa
`curadoria ou auditoria de Outros mudou após a publicação; regenere o bundle`.

A regeneração não pôde ser executada nesta sessão porque o renderizador
`scripts/build_fidc_revision_artifacts.mjs` depende de `@oai/artifact-tool`, que
não está presente no runtime Node deste ambiente. Em um ambiente com o runtime
disponível, basta:

```
python3 scripts/publish_fidc_revision_bundle.py \
    --input-workbook <workbook-base.xlsx> --skip-download
```

O ledger em si está íntegro: `assert_taxonomy_review_ledger_matches_audit`
reproduz as 2.299 decisões a partir da trilha de auditoria.

## Normalização de espaços em branco

A trilha de auditoria é reexecutada pela normalização do próprio módulo, que
colapsa sequências de espaços. Uma decisão gravada com espaço duplo na evidência
deixa de ser reproduzível por sua própria trilha sem que nada da decisão tenha
mudado. `apply_fidc_documentary_decisions.py` passou a normalizar os campos na
gravação, e `normalize_taxonomy_ledger_whitespace.py` reescreveu as 555 decisões
já gravadas que tinham essa característica — apenas espaços mudaram, e cada
reescrita ficou registrada na auditoria.

## Limitações

A conclusão descreve o mandato permitido pelo documento. A materialidade efetiva
de cada família depende da carteira observada em cada competência. Nome de fundo
não é evidência e não determina classificação em nenhuma etapa.
