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

No lugar dos seis entram seis: um por **categoria estrutural**, a mesma
taxonomia que dava nome aos slides originais. Cada slide traz o gráfico à
esquerda e, à direita, **uma tabela nativa do Office** com todos os veículos
daquele gráfico.

O gráfico nomeia só quem está abaixo do mínimo e os maiores por PL; a tabela é
quem garante que nenhum FIDC fique sem identificação. Ela é um objeto de tabela
de verdade — dá para ordenar, editar e colar no Excel.

| coluna | conteúdo |
| --- | --- |
| FIDC | nome curto do veículo |
| Mínimo (%) | mínimo estrutural quando existe; júnior nos demais |
| Atual (%) | subordinação da competência escolhida |
| Folga (p.p.) | **atual − mínimo**, uma casa decimal |

Ordenação: **PL do maior para o menor**, e a folga desempata pelo mais próximo
do limite. A cor da folga é sinalização de risco, e só isso — sem ícone, sem
forma, sem decoração:

| banda | folga |
| --- | --- |
| verde | ≥ 5,0 p.p. |
| amarelo | entre 2,0 e 5,0 p.p. |
| vermelho | < 2,0 p.p., inclusive negativa |

Os três maiores PLs do slide levam um cinza claríssimo na coluna do nome — o
destaque de materialidade fica longe da coluna da folga para não competir com
a sinalização de risco.

Passando de `MAX_ROWS_PER_SLIDE` linhas, a tabela continua num slide adicional
da mesma categoria, em vez de encolher a fonte.

O PNG do gráfico não desenha mais título nem subtítulo: o slide já os tem, e
repeti-los era ruído.

## Top 100 para revisão do universo Middle

`services/top100_middle_deck.py` fecha o deck com a lista dos cem maiores por
PL, em blocos de `ROWS_PER_SLIDE` linhas, cada bloco numa tabela nativa. A base
é `top100_fidcs_middle_review.csv`, e a mesma base gera
`outputs/top100_middle/Top100_FIDCs_Revisao_Middle.xlsx` — ali a aba é uma
**tabela do Excel** (ListObject), com filtro, ordenação e lista suspensa
Sim/Não na coluna `MIDDLE`.

Oito dos cem nunca reportaram patrimônio e fecham a lista, identificados como
tal em vez de receberem um número inventado.

## A taxonomia

O corte é o dos slides 18–23, e não o tipo ANBIMA: Financeiro, Adquirência,
Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS e Fomento Mercantil.
Ela nasce
em `services/industry_structural_risk.py` e só existia dentro do payload
publicado, um JSON de 29 MB; `scripts/build_carteira_taxonomia_estrutural.py`
extrai o mapa para `carteira_taxonomia_estrutural.csv`, com a origem de cada
linha. Um CNPJ fora do mapa fica em "Não classificado" — nenhuma categoria é
inferida.

### Revalidação contra o regulamento

A seção descreve **quem é o sacado e qual é o recebível encarteirado**, e quem
define os dois é o regulamento. `services/carteira_revalidacao.py` lê o
regulamento vigente de cada CNPJ, pontua os termos que descrevem lastro e
devedor, e devolve a categoria sustentada pelo documento com o trecho literal.

Duas travas evitam decisão por semelhança de nome:

| trava | efeito |
| --- | --- |
| `PONTUACAO_MINIMA` | abaixo dela o documento não distingue a operação |
| `MARGEM_MINIMA` | vantagem fina sobre a segunda colocada é empate, não escolha |

Sem evidência, a categoria vigente permanece e a linha fica marcada como não
revalidada. Onde o documento conclui e diverge, **o documento manda**.

Dois falsos positivos foram encontrados e travados por teste:

* o capítulo de **fatores de risco** repete todo o vocabulário do fundo em
  frases que não descrevem operação nenhuma — "podem afetar adversamente os
  produtores rurais" reclassificava um fundo de máquinas como agro. O corte do
  capítulo existia mas nunca disparava, porque olhava a primeira ocorrência do
  título, que está no sumário; passou a procurar a primeira dentro do corpo;
* **"consignado"** solto: todo regulamento diz que o voto é "consignado na
  ata". O termo só conta em contexto de crédito.

A marca de multicedente/multissacado sai do mesmo texto e acompanha o nome do
fundo na tabela: pulverizado entre muitos sacados não é o mesmo risco que
concentrado em um.

### Por que a marca não virou seção

A concentração é um **eixo diferente** do que define as seções. As seis são
definidas por lastro e devedor — cartão, folha, rural, banco, corporativo,
comercial —, e a marca cruza todas elas: dos 14 fundos marcados multissacado,
**13 estão fora de Fomento Mercantil** (7 em Agro / Revenda, 4 em Financeiro,
1 em Risco Corporativo, 1 em Consignado), e dos 5 de Fomento Mercantil apenas
1 é multissacado.

Transformar a marca em seção mapearia mal nas duas direções. O Pneucash II é o
caso didático: três cedentes o tornam multicedente na forma, mas concentrado no
risco — ele entraria na seção pelo motivo errado.

### O rótulo "Factoring"

Nenhum destes veículos é factoring no sentido regulatório: são FIDCs de
recebíveis comerciais. **Fomento Mercantil** é o termo da ANBIMA e o que os
próprios regulamentos usam — o do Pneucash II diz, com todas as letras, que
"para fins do Código ANBIMA, o Fundo é classificado como Fomento Mercantil".

A tradução acontece ao materializar `carteira_taxonomia_estrutural.csv`, e não
em `services/industry_structural_risk.py`: aquele serviço está amarrado ao
contrato do bundle publicado, que continua dizendo "Factoring".

## Cache

Salvar um fundo no painel muda o gráfico e muda o deck. Por isso o registro
entra na chave de cache das exportações (`_carteira_registry_signature`) e na
da posição (`_carteira_signature`): sem isso, o site continuaria servindo o
deck e o gráfico anteriores depois de uma gravação.


## Triagem de prováveis clientes Middle Market

Quem, entre os cedentes que os FIDCs declaram, tem porte de cliente Middle.

O cedente vem do **Informe Mensal da CVM** (`TAB_I2A12`/`TAB_I2B12` da Tabela
I) — é o próprio fundo dizendo à CVM quem lhe cede os direitos creditórios,
documento primário e não inferência. A varredura cobre sete competências,
porque um fundo declara num mês e omite no seguinte.

O julgamento sai do **cadastro da Receita Federal**: capital social, CNAE,
situação e UF. Três exclusões vêm antes de qualquer faixa, porque descrevem
quem não é cliente por definição — o cedente que é o próprio veículo, o banco
múltiplo ou comercial, e a pessoa física.

| classificação | critério |
| --- | --- |
| Provável Middle | capital social entre R$ 1 mm e R$ 500 mm, cadastro ativo |
| Improvável Middle | fora da faixa, fundo, banco, pessoa física ou cadastro baixado |
| Não avaliado | sem cadastro resolvido ou sem capital publicado |

A faixa de capital é proxy declarada: separa o microempreendedor da
corporação, mas não substitui o faturamento, que a Receita não publica.

**Não avaliado nunca vira improvável.** Ausência de dado é ausência de dado.


## Onde baixar

**Dados da Indústria → Dados e exportações**, em dois grupos. Nove botões numa
linha só espremem o rótulo até ficar ilegível, então o pacote executivo fica em
cima e as bases analíticas embaixo.

| botão | conteúdo |
| --- | --- |
| Revisão Middle | Top 100 por PL com o cedente declarado e a coluna MIDDLE pré-sugerida |
| Triagem de cedentes | um par fundo–cedente por linha, com capital social, CNAE e o motivo |
| Revalidação das seções | a leitura dos regulamentos, com o trecho literal de cada veredito |
| Subordinação da carteira | atual contra o mínimo, com o gráfico de bolhas nativo |

Cada botão serve **bytes construídos na hora**, não um arquivo antigo em disco:
é o que garante que o download saiu da mesma base que a página está exibindo.
Os CSV são lidos e revalidados antes de sair, de modo que um arquivo truncado
apareça como botão desabilitado com o motivo, em vez de chegar ilegível na mão
de quem baixou.


## Override do analista sobre o mínimo

`data/industry_study/carteira_subordinacao_overrides.csv`

A camada é **separada do registro**, de propósito. O registro guarda o que a
curadoria documental extraiu dos regulamentos; sobrescrevê-lo apagaria o dado
bruto e ninguém saberia mais o que o documento dizia. O override fica por cima,
e `resolve_portfolio` preserva os dois:

| coluna resultante | conteúdo |
| --- | --- |
| `referencia_extraida_pct` | o que a leitura automática produziu |
| `referencia_pct` | o que está valendo |
| `minimo_fonte` | qual dos dois, e de onde veio |
| `minimo_divergiu` | os dois existem e discordam |
| `minimo_override_motivo` | por que o analista decidiu assim |

O override incide sobre a **referência** — o mínimo contra o qual a folga é
medida —, e não sobre o mínimo júnior isolado: a tabela revisada dá um mínimo
por estrutura.

O arquivo também **acrescenta** fundos. Uma estrutura que a curadoria não
alcançou entra por ali, com o mínimo do analista e a categoria, e passa a
integrar o universo comparável. Um fundo introduzido assim tem
`referencia_extraida_pct` vazio: ele nunca teve leitura automática, e registrar
o override como se fosse extração seria inventar uma auditoria que não existe.

A categoria do override vem por último, depois da revalidação documental. É a
única camada que enxerga o que o documento não diz — e, quando classifica
contra a evidência, o motivo registrado explica por quê.
