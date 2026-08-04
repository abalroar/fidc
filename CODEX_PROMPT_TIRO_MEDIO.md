# Tabela única de atributos por CNPJ e ligação dos slides 10–17 — entrega de 1h a 1h30

## Por que agora, e por que este corte

As cinco colunas dos slides 10–17 (Originador, Cedente, Sub. mín., Preço por cota, Sacado) estão
entre 88% e 98% em `N/D`. **A informação já existe no repositório, em outra estrutura, e nunca foi
ligada.** Este é um trabalho de consolidação, não de coleta: nenhuma varredura documental nova é
necessária nesta entrega.

O achado que define o escopo: o payload tem uma coleção chamada `profiles`, com **20 fundos,
100% preenchidos em `cedente_originador`, `sacado_devedor` e `natureza_recebiveis`**, cada um com
`documentos_primarios_ids`, `evidencia`, `fonte`, `data_consulta` e `status_curadoria`. **Os 20 CNPJs
estão dentro do universo dos slides 10–17.** São respostas curadas, em português, com id de
documento — exatamente o que as tabelas precisam:

- `09.195.235/0001-50` Petrobras — cedente: "Empresas integrantes do Sistema Petrobras que cedam
  direitos ao fundo"; sacado: "Pessoas jurídicas às quais as cedentes prestam serviços ou alienam
  bens" (doc 792797)
- `26.287.464/0001-14` TAPSO — cedente: "Estabelecimentos credenciados, representados por
  Stone/Pagar.me"; sacado: "Stone, Pagar.me e demais adquirentes/subadquirentes" (doc 1066031)
- `62.393.679/0001-83` CloudWalk Bela — cedente: "CloudWalk Instituição de Pagamento" (docs 1117954;
  1166893; 993253)

Os slides mostram `N/D` para os três.

## Meta numérica desta entrega

São 120 linhas nas oito tabelas. Situação atual e o que a consolidação sozinha deve produzir:

| Campo | Hoje | Meta | Fonte do ganho |
|---|---:|---:|---|
| Cedente | 14/120 | ≥ 74/120 | `profiles` + Tabela I do Informe Mensal |
| Sacado | 2/120 | ≥ 34/120 | `profiles` |
| Sub. mín. | 7/120 | ≥ 14/120 | curadoria flagship / Carteira 101 |
| Preço por cota | 7/120 | ≥ 12/120 | preços documentais da Carteira 101 |

Se ficar materialmente abaixo disso, a junção está errada. Se ficar muito acima, provavelmente
alguma fonte de baixa confiança vazou — veja a quarentena abaixo.

## Fontes, em ordem de precedência

Use a escala que já existe em `services/carteira_101_document_audit.py` (`SOURCE_PRIORITY`: menor
número ganha). Ela está correta e está presa dentro daquele serviço; promova para regra do
repositório.

1. **`profiles`** — 20 CNPJs, curadoria humana com id de documento e data de consulta. Maior
   confiança para `cedente`, `sacado` e `natureza_recebiveis`.
2. **Tabela I do Informe Mensal**, via `data/industry_study/cedente_triage/202606/fidc_cedentes_top437_202606.csv.gz`
   (campo `cedente_razao_social_consolidada`) — cobre 68 dos 72 CNPJs, 27 com razão social. Fonte
   oficial da CVM para `cedente`.
3. **Carteira 101** — `carteira_101_document_prices` para `preco_cota`,
   `industry_flagship_document_curation.csv` e `industry_carteira_1_document_curation.csv` para
   `subordinacao_minima_junior`. Já vêm com id de documento e página.
4. **`industry_cnpj_manual_enrichment.csv`** — 32 linhas transcritas das fotos, já aplicadas hoje.
   Mantenha, marcadas com `*`, e **corrija o casamento**: hoje é feito por raiz de 8 dígitos do
   CNPJ, o que pode colar o dado de um fundo no fundo irmão do mesmo grupo. Passe para 14 dígitos e
   reporte toda linha que perder correspondência.

### Quarentena — não promova estas duas

`industry_top20_taxonomy_document_review.csv.cedent_originator_explicit` e
`top20_taxonomy_review.cedente_originador` **parecem** preenchidos (29 e 20 linhas no universo dos
slides), mas são fragmentos brutos de extração, truncados no meio da palavra:

```
"Candidato textual para validação (p. 36): VEDOR SERA UTILIZADA"
"Candidato textual para validação (p. 20): ANEXO I AO REGULAMEN"
"p. 5: CNPJ/MF SOB O NO 01.027.058/0001-91, CONTRATADA PELO FUNDO COMO AGENTE PARA AUXILIA"
```

Colocar isso no slide é pior do que `N/D`. Carregue na tabela com status `candidate_extraction` e
prioridade 90 — a escala existente já os coloca por último —, e garanta que a resolução nunca os
eleja quando houver qualquer outra fonte. Se forem a única fonte, o campo permanece `N/D` e a
linha fica visível numa fila de validação.

## O que construir

**1. Tabela de atributos, formato longo, append-only.** Uma linha por (fundo, campo, observação):

```
cnpj_fundo, campo, valor, competencia_fato, data_observacao,
fonte_tipo, fonte_id, fonte_pagina, episodio, confianca, status
```

Vocabulário fechado, só cinco campos nesta entrega: `cedente`, `originador`, `sacado`,
`subordinacao_minima_junior`, `preco_cota`. Povoada por ETL a partir das fontes acima — ninguém
redigita nada. Idempotente e reexecutável. Nunca sobrescreve: fonte melhor entra como linha nova.

Existe `data/industry_study/industry_dimension_catalog.csv.gz`, com 74.398 linhas para 4.289 CNPJs e
esquema quase idêntico ao proposto. Decida se estende ele ou cria a tabela ao lado — mas **não crie
uma terceira estrutura paralela**, e registre a decisão.

**2. Função de resolução.** `resolve(cnpj, campo)` devolve um valor e a proveniência dele, aplicando
a precedência num ponto só. Empate resolve pela observação mais recente.

**3. View larga materializada.** Uma linha por CNPJ, uma coluna por campo, mais proveniência. É o
que o deck passa a ler. Gerada, nunca editada à mão.

**4. Ligar os slides 10–17.** O construtor do deck para de consumir `emission_field_audit` e passa a
consultar a view, filtrando pela mesma regra que já seleciona o ranking (tipo + competência + rank).
Dois efeitos obrigatórios:

- Some o `raise ValueError("auditoria dos slides 10–13 diverge dos rankings materializados")` de
  `scripts/build_fidc_revision_artifact_payload.py:860`. Ele existe porque há duas listas para
  sincronizar à mão; com a view não há mais. No lugar dele, um relatório de cobertura por campo.
- Sai do dado a coluna `bloco` com valor `"slides 10–13"` — que, além de acoplar dado a layout, já
  está errada: hoje são os slides 10 a 17.

## Limites do escopo — não ultrapasse

**Fora desta entrega:** `tabs/tab_industry_study.py` (16.262 linhas), os gráficos vigentes, qualquer
varredura documental nova, os demais slides, e introduzir dimensão de competência em datasets que
hoje não têm. Nenhum arquivo existente é apagado — os nove arquivos de curadoria continuam onde
estão e quem os lê hoje continua lendo.

A mudança é **aditiva**: tabela nova, função nova, view nova, e um único consumidor migrado.

Se em algum ponto o trabalho começar a exigir tocar no Streamlit ou nos gráficos para funcionar,
**pare e reporte** em vez de seguir. Isso é sinal de que a view está resolvendo diferente do que o
consumidor espera, e é informação, não obstáculo.

## Regras de correção

- **Cedente não é originador.** A Tabela I traz o cedente **legal**, frequentemente um veículo
  financeiro e não o originador econômico: Multiplica declara QI DTVM, Monee declara QI SCD. São
  campos distintos e não podem colapsar. Se as duas colunas ficarem iguais em massa, a junção está
  errada.
- **Sacado tem teto estrutural.** Nenhuma das 17 tabelas do Informe Mensal tem campo de sacado ou
  devedor identificado; só sai de leitura de regulamento. Registre isso como cobertura máxima
  esperada do campo. A meta de 34/120 vem toda de `profiles`, e é o que existe hoje.
- **Lacuna continua lacuna.** Sem fonte, `N/D`. Não estime, não interpole, não deduza do nome do
  fundo.
- **Fonte identifica documento.** A URL genérica do gerenciador do FundosNet aparece como fonte em
  71 linhas do `emission_field_audit` e em `profiles.fonte`. Ela não é evidência — é um "consulte
  aqui". O que vale é `documentos_primarios_ids` / `fonte_id`. Onde só houver a URL, trate como
  ausência de fonte identificada.

## Não quebrar o que está de pé

Rode a suíte antes de começar e guarde a saída como linha de base — hoje são 1.203 testes passando.
Nenhum teste existente pode passar a falhar.

Para as 120 linhas, gere um diff campo a campo entre o valor atual e o resolvido pela view, e só
troque a leitura do deck depois de explicar cada divergência. Divergência não explicada é bloqueio.

Suba o contrato de teste dos slides de "o cabeçalho existe" — que é tudo o que
`tests/test_industry_revision_artifacts.py` verifica hoje, e por isso oito páginas inteiramente
`N/D` passaram nos 1.203 testes — para piso de preenchimento por campo, usando os números da tabela
de metas. O teste tem que ficar vermelho se alguém republicar uma coluna vazia.

## Delegação

Você fica com o que exige julgamento: o vocabulário dos cinco campos, a decisão sobre estender ou
não o dimension catalog, o desenho da resolução, e a leitura dos diffs.

**Effort alto** — ETL de `profiles` e da Tabela I para o formato longo, com teste de contagem de
linhas e de CNPJs distintos; e o diff campo a campo das 120 linhas com as divergências classificadas
por causa.

**Effort médio** — a função de resolução sobre a tabela de precedência; a materialização da view; a
troca da leitura no construtor do deck; os testes de piso de cobertura.

**Effort baixo, Luna e Terra** — trocar o casamento por raiz de 8 dígitos por CNPJ de 14 dígitos no
enriquecimento manual e reportar as perdas; remover a coluna `bloco` e ajustar referências;
normalizar CNPJ para 14 dígitos com zero à esquerda em todos os ETLs; marcar a URL genérica do
FundosNet como ausência de fonte; reescrever os rodapés dos slides depois que os números finais
existirem, inclusive a frase que hoje afirma que as cinco colunas vêm da curadoria flagship —
afirmação falsa, já que essa curadoria cobre 6 dos 72 CNPJs; conferir formatação, acentuação,
truncamento de célula e mojibake; rodar a suíte e reportar.

## Entrega

Um relatório curto com: cobertura por campo antes e depois nas 120 linhas, contra a tabela de metas;
quantos fundos ganharam atributo só pela consolidação; as divergências que a precedência resolveu e
como; quantas linhas ficaram na quarentena de `candidate_extraction`; e o que continua `N/D`,
separado em "sem fonte", "campo inexistente na CVM" e "só há candidato bruto".

Esta é uma entrega de 1h a 1h30. Se o escopo começar a crescer, corte pelo fim — a view e a ligação
dos slides são o núcleo; refinamento de vocabulário e absorção dos demais arquivos de curadoria
ficam para a próxima.
