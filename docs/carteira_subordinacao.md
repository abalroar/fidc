# Carteira de subordinação

Compara, fundo a fundo, a subordinação que o FIDC **tem** contra a que o
regulamento **exige**. Vive em três lugares que compartilham o mesmo dado: um
registro em CSV, a aba **Carteira** em Dados da Indústria e seis slides do deck
executivo.

## O registro é o único lugar onde o mínimo entra

`data/industry_study/carteira_subordinacao_registry.csv`

| coluna | o que guarda |
| --- | --- |
| `cnpj` | 14 dígitos, sem máscara |
| `apelido` | nome de trabalho, usado quando o Informe não traz denominação |
| `subordinacao_minima_pct` | mínimo júnior isolado, em pontos percentuais |
| `subordinacao_estrutural_pct` | mínimo Sub+Mez, em pontos percentuais |
| `inclui_mezanino` | verdadeiro quando há mínimo estrutural |
| `origem` | `carteira_101` (semeado) ou `manual` (incluído no painel) |
| `fonte` | regulamento, página e data da cláusula |
| `observacao`, `responsavel`, `atualizado_em_utc` | trilha da decisão |

A Carteira 101 chega ali por semeadura, a partir da curadoria documental em
`industry_carteira_1_document_curation.csv`. A inclusão manual de um CNPJ no
painel grava **no mesmo arquivo, com as mesmas colunas** — não existe caminho
privilegiado para os 101. Semear de novo preserva o que foi editado à mão, a
menos que `seed_registry(overwrite=True)` seja chamado de propósito.

O mínimo é digitado, e não lido do Informe, porque ele não está no Informe: vem
do regulamento do fundo. O registro é a forma de trazer essa leitura para
dentro do sistema com a fonte anexada.

## A competência é escolhida fundo a fundo

`resolve_portfolio` toma, para cada CNPJ, **a competência mais recente em que
aquele fundo reportou patrimônio** — não a competência mais recente da base.
Quando julho chega para parte da carteira e junho é o que existe para o resto,
cada fundo entra com o seu próprio dado mais novo, e a coluna `competencia`
registra qual foi usada.

Um fundo é considerado **ativo** quando reportou em alguma das últimas
`ACTIVE_TOLERANCE_MONTHS` competências da base. A tolerância existe porque o
Informe de um mês chega escalonado: exigir a competência mais recente derrubaria
do gráfico fundos vivos que apenas ainda não entregaram.

### Unidades

O Informe Mensal reporta subordinação como **fração** (`0,2474`); a curadoria
documental, em **pontos percentuais** (`4,5`). A conversão acontece uma única
vez, em `resolve_portfolio`. Tudo que sai do módulo está em pontos percentuais.

### Contra o que se compara

Havendo mínimo estrutural, a comparação é contra ele (subordinada + mezanino);
não havendo, contra o mínimo júnior. A coluna `referencia_tipo` diz qual dos
dois foi usado em cada linha, e a nota de rodapé do gráfico repete o critério.

## O gráfico

Um par de pontos por fundo, ligados por uma haste: cinza é a subordinação
atual, vermelho é o mínimo exigido. Onde o vermelho aparece **acima** do cinza,
o fundo está abaixo do que o próprio regulamento exige — a leitura é imediata,
sem consultar legenda ou tabela. Os fundos em descumprimento recebem rótulo
direto; os demais rótulos vão para os maiores por PL, para dar escala ao eixo.

Desenhado com matplotlib sobre o dataframe do pandas. O cinza fica abaixo do
piso de croma que o validador de paletas cobra de uma paleta categórica: é
deliberado, porque a série cinza é a referência neutra e não uma categoria
concorrente. A separação entre as duas séries é de ΔE 15,4 no pior caso de
visão de cores, bem acima do piso, e o pareamento posicional reforça a leitura.

## Os slides 18–23

O deck padrão é um binário publicado, validado contra manifesto. Os seis slides
de risco estrutural são **reescritos no lugar** no caminho de exportação, sobre
a apresentação já carregada em memória — o bundle em disco permanece intacto e
continua validando.

Reescrever em vez de remover e recriar não é preferência de estilo: o
`next_partname` do python-pptx devolve nomes de parte **já ocupados** quando a
numeração deixa de ser contígua, e remover um slide do meio do deck é
exatamente o que abre esse buraco. O pacote sairia com dois
`ppt/slides/slideN.xml`. `tests/test_carteira_subordinacao.py` guarda essa
propriedade explicitamente.

No lugar dos seis entram: um slide consolidado e um por tipo ANBIMA com pelo
menos `MIN_FUNDS_PER_TYPE` fundos comparáveis. Sobrando slot, ele recebe o
consolidado restrito a quem está abaixo do mínimo.

## Cache

Salvar um fundo no painel muda o gráfico e muda o deck. Por isso o registro
entra na chave de cache das exportações (`_carteira_registry_signature`) e na
da posição (`_carteira_signature`): sem isso, o site continuaria servindo o
deck e o gráfico anteriores depois de uma gravação.
