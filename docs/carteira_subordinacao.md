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

### Quando o mês escolhido tem o quadro de cotas quebrado

Patrimônio positivo com `vl_cotas_total` zerado **não** é um fundo sem
subordinação: é a quebra do quadro de cotas naquele mês, e produziria 0% onde o
mês anterior traz o número real. A competência escolhida é a mais recente com
patrimônio **e** quadro de cotas fechado; a coluna `quadro_de_cotas_integro`
registra o caso raro em que nenhuma competência fecha.

Foi o que aconteceu com o **Blue II Segmento Crédito Corporativo**: em jun-26 o
quadro veio zerado, e mai-26 traz 100%. Já o **MCPO** reporta o quadro todo mês
e a cota subordinada zerada há nove meses seguidos — ali o 0% é o dado, não uma
falha, e `meses_sem_subordinada` é o que separa os dois casos.

### Unidades

O Informe Mensal reporta subordinação como **fração** (`0,2474`); a curadoria
documental, em **pontos percentuais** (`4,5`). A conversão acontece uma única
vez, em `resolve_portfolio`. Tudo que sai do módulo está em pontos percentuais.

### Contra o que se compara

Havendo mínimo estrutural, a comparação é contra ele (subordinada + mezanino);
não havendo, contra o mínimo júnior. A coluna `referencia_tipo` diz qual dos
dois foi usado em cada linha, e a nota de rodapé do gráfico repete o critério.

## O gráfico

Um par de pontos por fundo, ligados por uma haste. **O ponto verde marca sempre
o maior dos dois valores**: quando o verde está na subordinação atual, o fundo
supera o mínimo; quando está no mínimo, não alcança. O outro ponto mantém a cor
da sua série — cinza para a subordinação atual, vermelho para o mínimo.

O que carrega o alerta é a haste: quem está abaixo do mínimo ganha haste
**vermelha e grossa** e rótulo direto, também em vermelho. Nada mais no gráfico
muda de espessura, então o olho cai ali antes de ler qualquer texto.

### Duas saídas, uma fonte

| onde | função | por quê |
| --- | --- | --- |
| dashboard | `altair_dumbbell` | vetorial, responsivo, com tooltip por fundo — a saída nativa do app |
| PPTX | `dumbbell_figure` (matplotlib) | o slide precisa de imagem |

Ambas consomem `chart_frame`, então não há como as duas divergirem.

### Cor

Verde puro contra vermelho é o pior par possível para deuteranopia (ΔE 6,0).
O verde-azulado `#17A398` sobe a separação para **ΔE 14,9**, bem acima do piso,
e continua lendo como verde. A posição reforça: o ponto verde é sempre o de
cima. O cinza fica abaixo do piso de croma que o validador cobra de uma paleta
categórica — é deliberado, porque a série cinza é a referência neutra e não uma
categoria concorrente.

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

No lugar dos seis entram: um slide consolidado e um por **categoria
estrutural** — a mesma taxonomia que dava nome aos slides originais. São sete
gráficos para seis slots; o excedente **nasce no fim do deck e é movido** para
depois deles. Acrescentar é seguro: só remover abriria buraco na numeração.

Sobrando slot, ele recebe o consolidado restrito a quem está abaixo do mínimo.

## A taxonomia

O corte é o dos slides 18–23, e não o tipo ANBIMA: Financeiro, Adquirência,
Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS, Factoring. Ela nasce
em `services/industry_structural_risk.py` e só existia dentro do payload
publicado, um JSON de 29 MB; `scripts/build_carteira_taxonomia_estrutural.py`
extrai o mapa para `carteira_taxonomia_estrutural.csv`, com a origem de cada
linha. Um CNPJ fora do mapa fica em "Não classificado" — nenhuma categoria é
inferida.

## Cache

Salvar um fundo no painel muda o gráfico e muda o deck. Por isso o registro
entra na chave de cache das exportações (`_carteira_registry_signature`) e na
da posição (`_carteira_signature`): sem isso, o site continuaria servindo o
deck e o gráfico anteriores depois de uma gravação.
