# Consolidar os atributos por CNPJ numa tabela única e fazer os slides lerem dela

## Diagnóstico (validado no código, não é hipótese)

A seleção dos slides **já é dinâmica e já respeita a base**. `build_historical_top20_taxonomy_review`
em `services/industry_taxonomy_review.py:1658` parte de `funds`, exclui FIC, aplica
`apply_taxonomy_review_overlay(scoped, actions)`, ordena por PL e corta no rank. Reclassificar um
fundo em `taxonomy_review_actions.csv` **muda a composição do Top 20/Top 15 automaticamente**. Isso
está certo e não deve ser mexido.

O problema é a assimetria do outro lado: **a seleção é calculada, os atributos são nominais.**

Depois que o fundo é selecionado, as colunas de conteúdo — cedente, originador, sacado,
subordinação mínima, preço por cota — vêm de nove arquivos de curadoria, cada um congelado sobre
uma lista nominal de fundos de um episódio passado, cada um com nomes de coluna próprios para o
mesmo fato:

| Arquivo | Linhas | Chave | Como chama o cedente |
|---|---:|---|---|
| `emission_field_audit.csv` | 180 | `bloco` + `tabela` + cnpj | `cedente` |
| `industry_top20_taxonomy_document_review.csv` | 143 | cnpj | — |
| `industry_cnpj_manual_enrichment.csv` | 104 | **raiz de 8 dígitos** | `cedente_originador_literal` |
| `industry_carteira_1_document_curation.csv` | 101 | cnpj | — |
| `industry_flagship_document_curation.csv` | 47 | cnpj | — |
| `card_receivables_curation.csv` | 44 | cnpj | `cedente_originador` |
| `acquiring_reclassification_curation.csv` | 33 | cnpj | — |
| `industry_top20_outros_regulation_review.csv` | 20 | cnpj | — |
| `top20_profile_curation_overrides.csv` | 4 | cnpj | `cedente_originador` |

Nenhum é superconjunto de outro, não há precedência declarada entre eles, e o resultado é
observável: cruzando "Curadoria Top 20" com "Auditoria emissões" no workbook publicado, nos 20
CNPJs presentes nas duas abas, **os 20 divergem**. A Curadoria Top 20 sabe que o cedente da Cielo
são "estabelecimentos credenciados à Cielo" e que o da Venda de Veículos é "Nissan do Brasil e
Renault"; a Auditoria emissões, que é a aba que o deck lê, diz `N/D` para ambos.

Duas consequências mecânicas, ambas verificadas:

1. `emission_field_audit.csv` carrega uma coluna `bloco` com o valor `"slides 10–13"`. O dado sabe
   em que slide mora — e já está desatualizado, porque hoje são os slides 10 a 17.
2. `scripts/build_fidc_revision_artifact_payload.py:860` faz
   `raise ValueError("auditoria dos slides 10–13 diverge dos rankings materializados")` quando o
   conjunto de CNPJs do CSV não bate exatamente com o ranking calculado. Ou seja: **toda
   reclassificação que muda a composição do Top 15 quebra o build**, e a saída é reeditar 120
   linhas na mão — com os fundos entrantes chegando em `N/D`.

Isso é o que faz cada análise nova custar caro e ficar irreplicável. Não é a seleção; é o atributo.

## Objetivo

Um lugar só, com marcação de origem, para os atributos dos mais de 4.000 fundos. Os slides passam a
**filtrar** essa tabela pela regra vigente, em vez de consumir listas nominais.

## Escopo — respeite os limites

**Dentro:** uma tabela de atributos, uma função de resolução, uma view larga materializada, e a
migração dos consumidores que hoje estão quebrados (slides 10–17 e as abas de curadoria que os
alimentam).

**Fora, nesta entrega:** reescrever `tabs/tab_industry_study.py` (16.262 linhas), mexer nos gráficos
vigentes, apagar qualquer arquivo existente, mudar a lógica de seleção/ranking, e introduzir
dimensão de competência em datasets que hoje não têm. Nada disso é necessário para resolver a
dispersão, e tudo isso arrisca o que está de pé.

**A mudança tem que ser aditiva.** Arquivo novo, função nova, view nova. Os nove arquivos de
curadoria continuam existindo e sendo lidos por quem já os lê. A migração é consumidor a
consumidor, e cada um só migra quando a view provar que entrega o mesmo ou mais.

## O que construir

### 1. Tabela de atributos, formato longo, append-only

Uma linha por (fundo, campo, observação). Sugestão de colunas, ajuste se fizer sentido:

```
cnpj_fundo, campo, valor, valor_normalizado, competencia_fato, data_observacao,
fonte_tipo, fonte_id, fonte_pagina, trecho, episodio, confianca, status
```

Pontos que importam:

- **`campo` vem de um vocabulário fechado.** Comece pelos cinco que estão quebrando os slides:
  `cedente`, `originador`, `sacado`, `subordinacao_minima_junior`, `preco_cota`. Registre para cada
  um a definição, a unidade e as fontes admissíveis.
- **Ela é povoada por ETL a partir dos nove arquivos existentes**, não por redigitação. Ninguém
  reentra dado. O ETL é reexecutável e idempotente.
- **`episodio` guarda de qual varredura/curadoria a linha veio**, e o escopo daquela varredura
  (quais CNPJs foram olhados) fica registrado como dado. É isso que distingue "varrido e não
  achou" de "nunca varrido" — e é o que torna a consulta replicável sem reconstruir o prompt
  original.
- **Duas datas, não uma:** `competencia_fato` (a que período o valor se refere) e
  `data_observacao` (quando lemos o documento). Um regulamento de 2013 lido agora precisa dos dois.
- **Nunca sobrescreve.** Fonte melhor entra como linha nova; a antiga fica no histórico.

Aproveite o que já existe: `data/industry_study/industry_dimension_catalog.csv.gz` tem 74.398
linhas para 4.289 CNPJs e **já tem o esquema quase certo** (`source_document`, `source_page`,
`source_date`, `confidence_score`, `review_status`). Está subalimentado — `source_page` preenchido
em 0,1%, e `source_layer` só assume `snapshot` e `cedente`, então nenhuma evidência documental
chegou lá. Decida você: estender esse catálogo ou criar a tabela ao lado e absorver o catálogo
depois. Não construa uma terceira coisa paralela.

### 2. Função de resolução com precedência declarada

`resolve(cnpj, campo)` devolve **um** valor e a proveniência dele. A precedência já existe pronta em
`services/carteira_101_document_audit.py` (`SOURCE_PRIORITY`: rating 10 > regulamento 20 >
emissão 25 > assembleia 30 > informe 40 > planilha manual 60) — está presa dentro daquele serviço.
Promova para regra do repositório e aplique num ponto só. Empate resolve pela observação mais
recente.

### 3. View larga materializada

Uma linha por CNPJ, uma coluna por campo, mais as colunas de proveniência. É o que os consumidores
leem. Gerada, nunca editada à mão. As abas largas de curadoria do workbook passam a ser projeções
dela.

### 4. Migrar os slides 10–17

O construtor do deck para de ler `emission_field_audit` e passa a consultar a view, filtrando por
tipo e competência — a mesma regra que já seleciona o ranking. Consequências desejadas:

- Fundo que entra no Top 15 por reclassificação **chega com o que a base souber dele**, em vez de
  `N/D`.
- O `raise ValueError` da linha 860 deixa de existir: não há mais duas listas para sincronizar. No
  lugar dele, um relatório de cobertura por campo.
- A coluna `bloco` com número de slide sai do dado.

Só com a consolidação, e sem nenhuma varredura nova, essas tabelas devem ganhar cedente em cerca de
26 linhas vindas da Tabela I do Informe Mensal (Petrobras, Renault, GM, Hyundai, Honda, Stellantis,
Syngenta, BRF, Havan, Stone, Santander) e mais 20 vindas da prosa que a Curadoria Top 20 já
escreveu. Use isso como sanity check: se a cobertura não subir nessa ordem de grandeza, a junção
está errada.

## Regras de correção

- **Cedente não é originador.** A Tabela I traz o cedente **legal**, que muitas vezes é veículo
  financeiro e não o originador econômico: Multiplica declara QI DTVM, Monee declara QI SCD. São
  campos distintos no vocabulário e não podem colapsar. Se as duas colunas ficarem iguais em massa,
  a junção está errada.
- **Sacado não existe na CVM.** Nenhuma das 17 tabelas do Informe Mensal tem campo de sacado ou
  devedor identificado; só sai de leitura de regulamento. O teto observado, com varredura completa,
  foi 37%. Registre isso como cobertura máxima esperada do campo, para que a lacuna deixe de parecer
  falha.
- **Lacuna continua lacuna.** Sem documento, o valor é `N/D`. Não estime, não interpole, não deduza
  do nome do fundo.
- **Fonte identifica documento.** Onde hoje a fonte é a URL genérica do gerenciador do FundosNet
  (71 linhas do `emission_field_audit`), isso não é evidência — é um "consulte aqui". Trate como
  ausência de fonte.

## Não quebrar o que está de pé

- Rode a suíte antes de começar e guarde a saída como linha de base. Nenhum teste existente pode
  passar a falhar.
- Para cada consumidor migrado, gere um diff campo a campo entre o valor antigo e o resolvido pela
  view, e só troque a leitura depois de explicar cada divergência. Divergência não explicada é
  bloqueio, não é detalhe.
- Os gráficos e as abas do Streamlit não mudam de fonte nesta entrega. Se algum gráfico mudar de
  número, pare e reporte — é sinal de que a view está resolvendo diferente do que o consumidor
  esperava.
- Suba o contrato de teste dos slides de "o cabeçalho existe" para piso de preenchimento por campo
  e por bloco, com o piso calibrado no que a fonte sustenta: alto para cedente, que tem base CVM;
  baixo e explícito para sacado. O teste tem que ficar vermelho se alguém republicar uma coluna
  inteira de `N/D`.

## Delegação

Você fica com o que exige julgamento: o vocabulário de campos, o desenho da tabela e da resolução,
a decisão sobre estender ou não o dimension catalog, o mapeamento dos nove arquivos para o formato
longo, e a análise dos diffs de migração.

**Delegue em effort alto** (raciocínio real, escopo fechado):
- Escrever o ETL de cada arquivo de curadoria para o formato longo, um por vez, com teste de
  contagem de linhas e de CNPJs distintos por arquivo.
- Produzir o diff campo a campo entre valor antigo e valor resolvido, com as divergências
  classificadas por causa.

**Delegue em effort médio:**
- Implementar a função de resolução a partir da tabela de precedência que você definir.
- Materializar a view larga e ligar as abas de curadoria a ela como projeção.
- Escrever os testes de piso de cobertura com os valores que você calibrar.

**Delegue em effort baixo — Luna e Terra:**
- Trocar o casamento por raiz de 8 dígitos por CNPJ de 14 dígitos no enriquecimento manual,
  reportando toda linha que perca correspondência.
- Substituir a URL genérica do gerenciador, onde aparece como fonte, por marcação explícita de
  ausência de fonte.
- Remover a coluna `bloco` com número de slide e ajustar as referências.
- Normalizar CNPJ para 14 dígitos com zero à esquerda em todos os ETLs.
- Reescrever rodapés de slide e textos de Leia-me depois que os números finais existirem.
- Conferir formatação, acentuação, truncamento de célula e ausência de mojibake.
- Rodar a suíte e reportar falhas.

## Entrega

Um relatório com: cobertura por campo antes e depois, em número de fundos e em % do PL; quantos
fundos ganharam atributo só pela consolidação, sem varredura nova; a lista de divergências entre
fontes que a precedência resolveu e como; e o que continua `N/D`, separado em "sem documento",
"campo inexistente na CVM" e "fora do escopo já varrido".

Se em algum ponto a mudança começar a exigir tocar no Streamlit ou nos gráficos para funcionar,
pare e reporte antes de seguir. O objetivo é consolidar, não reconstruir.
