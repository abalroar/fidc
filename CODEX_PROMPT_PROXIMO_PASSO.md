# Slides 10–17: legibilidade da tabela e o que a base já sustenta e não está sendo mostrado

## Ponto de partida

A entrega anterior (PR #151) funcionou. Cobertura nas 120 linhas: cedente 14 → 66, sacado 2 → 44,
subordinação 7 → 19, remuneração-alvo 7 → 32. O guard segurou o caso mais difícil — VTK
(`62.588.266/0001-54`) tem 5,12%, 5,41% e 7,10% de taxa de endosso nos documentos e a coluna ficou
`N/D`, correto. O log de 24 rejeições com decisão tipada (`SUPERSEDED`, `OCR_TRUNCATED`,
`CLASS_DRIFT`, `AFTER_CUTOFF`, `INACTIVE_CLASS`) é artefato de auditoria de verdade. E a mudança em
`services/carteira_101_document_audit.py` ficou aditiva — parametrizou o prefixo de arquivo sem
tocar em `choose_field` nem em `_EXPLICIT_STATUS`, então a Carteira 101 não corre risco.

Esta rodada não é sobre cobertura. É sobre a tabela ficar legível e sobre usar o que já foi
extraído. Nada aqui exige varredura documental nova.

## Parte 1 — Defeitos de leitura na tabela

**1.1 Originador e Cedente dizem a mesma coisa em metade das linhas.**
Das 30 linhas com as duas colunas preenchidas, **15 trazem a mesma entidade**: TAPSO
(Stone* / Stone/Pagar.me), CloudWalk (CLOUDWALK / CLOUDWALK), VTK (FACTA / FACTA), Havan
(Havan* / HAVAN S.A). São duas colunas de nove consumindo largura para repetir um fato.

Ao mesmo tempo, **Originador é a única coluna que não andou**: 30 → 34 em 120. Ela é a que menos
informa e a que mais duplica.

Decida entre duas saídas e justifique a escolha:

- **Fundir** numa coluna só ("Cedente / originador"), mostrando a entidade uma vez, com a distinção
  legal preservada na aba de auditoria; ou
- **Manter separadas mas suprimir a repetição**: quando as duas resolverem para a mesma entidade,
  a célula de Originador fica vazia com marcação de "mesmo que o cedente", em vez de repetir.

A largura liberada vai para Sacado e Remuneração-alvo, que são as colunas que hoje mais truncam.

**1.2 Dezenove células de Sacado são fragmentos de frase cortados no meio.**
Exemplos reais do deck publicado:

```
MULTIPLICA        "1 sacado 2 sacado 3"
NAGOYA            "os devedores dos"
IOX I             "pessoas físicas e/ou"
AGRO FLEX         "as Cooperativas, os"
CLOUDWALK PI      "(i) o Itaú Unibanco"
CLOUDWALK BELA    "Emissores e"
```

`"1 sacado 2 sacado 3"` é artefato de extração, não conteúdo. As demais são prosa cortada no
caractere, começando por artigo ou por marcador de enumeração `(i)`.

Numa tabela executiva, fragmento assim é pior que `N/D`: parece defeito de software e derruba a
confiança nas células que estão certas. Resolva com resumo semântico, não com corte por caractere —
uma frase curta que caiba, do tipo "Estabelecimentos credenciados", "Pessoas físicas — consignado",
"Cooperativas e produtores", com o texto integral na aba de auditoria. Onde não houver resumo
possível dentro da largura, `N/D` com o motivo registrado.

**1.3 O sufixo `+N*` aparece em 22 células e não é decifrável.**
`CDI+1,50% +3*`, `103% do CDI +2*`. Presumo que `+3` seja "mais três séries", mas o leitor não tem
como saber. Ou explicite na legenda o que o número significa, ou troque por algo autoexplicativo
(`CDI+1,50% · 4 séries`), ou remova do slide e deixe só na auditoria.

**1.4 O asterisco carrega três significados diferentes no mesmo rodapé.**
Hoje: *"* = complemento manual, múltiplas cotas/séries ou mínimo estrutural/total"*. Em `Stone*` o
leitor não consegue saber qual dos três é. Use símbolos distintos, ou deixe o `*` só para
complemento manual — que é o único que muda a confiabilidade do dado — e resolva os outros dois na
própria célula.

## Parte 2 — O que a base sustenta e o slide não mostra

`data/industry_study/emission_target_remuneration_accepted.csv` tem **105 observações aceitas**, com
`classe_serie`, `source_id`, `page`, `document_date` e `event_date`. O slide reduz isso a 32 células
com um número só por fundo. A informação mais interessante está sendo descartada na exibição.

**2.1 Prêmio de subordinação.** Há **20 pares fundo-corte com Sênior e Mezanino documentados no
mesmo fundo**. O diferencial mediano é de **100 bps**, com faixa de 50 a 300:

```
SIFRA PLUS      jun/26   Sr 2,50%   Mz 3,60%   (+110 bps)
SIFRA STAR      jun/26   Sr 3,00%   Mz 3,90%   ( +90 bps)
MULTIPLICA      jun/26   Sr 3,10%   Mz 4,10%   (+100 bps)
IOX II          dez/25   Sr 4,50%   Mz 6,75%   (+225 bps)
```

Isso é comparação dentro do mesmo veículo, mesma carteira, mesma data — metodologicamente limpa, ao
contrário de comparar spread entre fundos diferentes. É a leitura mais defensável que esse dado
permite e não aparece em lugar nenhum.

Avalie onde cabe: uma coluna a mais na tabela (Sênior e Mezanino lado a lado nos 20 fundos que
têm ambos), ou um gráfico/quadro próprio. Decida você — o critério é caber sem espremer o que já
está lá.

**2.2 Movimento no semestre.** As oito páginas já mostram dez/25 e jun/26 lado a lado, mas nada
compara os dois. SIFRA PLUS teve sênior de CDI+3,00% para CDI+2,50%, **−50 bps no semestre**, com
AGE documentada. É o tipo de fato que justifica a existência das duas páginas.

**2.3 Uma armadilha estatística, e ela é séria.** O spread sênior médio sai de 1,96% em dez/25 para
3,21% em jun/26 — mas isso é **composição da amostra, não movimento de mercado**: são 15
observações no primeiro corte e 33 no segundo, porque a varredura documentou mais fundos. Dos 22
pares fundo-classe presentes nos dois cortes, **apenas 1 mudou de taxa**.

Se alguém plotar a média por período, o deck publica "spread subiu 125 bps no semestre", que é
falso. Trate isso explicitamente: qualquer comparação temporal tem que ser em amostra casada, e o
denominador precisa estar visível. Se decidir mostrar a evolução, mostre sobre os 22 pares, não
sobre o total.

## Regras que continuam valendo

- Lacuna sem fonte é `N/D`. Não estime, não interpole, não deduza do nome do fundo.
- Fonte identifica documento e página, não a URL genérica do gerenciador do FundosNet.
- Cedente legal (Tabela I) e originador econômico são conceitos distintos — se a fusão da coluna
  for a saída escolhida, a distinção tem que sobreviver na aba de auditoria.
- Spread só é comparável a igual subordinação, prazo e lastro. Se a tabela passar a permitir
  comparação entre fundos, o rodapé precisa dizer isso.

## Não quebrar o que está de pé

Rode a suíte antes e guarde a linha de base. Nenhum teste existente pode passar a falhar, e o
contrato de cobertura por campo que você calibrou não pode regredir: cedente 66, sacado 44,
subordinação 19, remuneração 32 são piso, não meta.

Esta rodada mexe em apresentação e em agregação — não deve alterar nenhum valor já resolvido. Se
algum número de célula mudar, isso é bug, não melhoria: pare e reporte.

Não encoste no Streamlit nem nos demais slides. Não instale ImageMagick nem monte contact sheet das
37 páginas — valide as oito que você mexeu.

## Delegação

Você fica com: a decisão entre fundir ou suprimir Originador/Cedente, o desenho do resumo semântico
de Sacado, e onde o prêmio de subordinação entra sem espremer a tabela.

**Effort alto** — o resumo semântico de Sacado a partir do texto integral, com teste caso a caso
contra os 19 fragmentos atuais; e o cálculo do prêmio de subordinação em amostra casada, com o
tratamento de composição da seção 2.3.

**Effort médio** — a supressão ou fusão da coluna redundante e a redistribuição de largura; a
renderização do novo bloco de subordinação; os testes de piso de cobertura atualizados.

**Effort baixo, Luna e Terra** — corrigir `"BRF S .A."`, que tem espaço espúrio; trocar ou explicar
o sufixo `+N*`; separar os três significados do asterisco na legenda e no rodapé; conferir
truncamento, acentuação e mojibake nas oito páginas; rodar a suíte e reportar.

## Entrega

Antes e depois de cada coluna em número de células; quantas linhas deixaram de repetir entidade
entre Originador e Cedente; quantos dos 19 fragmentos de Sacado viraram resumo legível e quantos
viraram `N/D`; e o quadro do prêmio de subordinação com o denominador explícito.

Se o escopo crescer, corte pelo fim: a legibilidade da tabela é o núcleo, o prêmio de subordinação
é o bônus.
