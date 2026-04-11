# Provisionamento, perdas e inadimplência

## O problema de linguagem

Em FIDC, é comum o mercado usar “inadimplência”, “provisão”, “perda” e “PDD” quase como se fossem a mesma coisa. Para análise séria, isso é inadequado.

## Três camadas diferentes

### 1. Atraso / inadimplência

É a dimensão comportamental do crédito:

- venceu e não pagou;
- atrasou quantos dias;
- está em qual bucket de aging.

### 2. Provisão

É a dimensão contábil ou de política de perdas:

- qual parte do valor está provisionada;
- em qual regra ou política isso se apoia;
- se a provisão é linear, por bucket, por evento, por amostragem ou por regra específica do fundo.

### 3. Perda esperada ou perda realizada

É a dimensão econômica:

- o que o fundo espera perder com a carteira;
- o que de fato já foi absorvido;
- quanto foi coberto por subordinação, spread, reserva, recompra ou resolução.

## O que os documentos do acervo sugerem

- GERU trata provisões e perdas junto da lógica de monitoramento da carteira e da governança de parâmetros estruturais. Fonte: `estudo/1337461-15981-20200901100422.pdf`.
- Facta INSS CB organiza a carteira em torno de cessão, elegibilidade, cobrança e eventos, o que impede leitura simplista de atraso puro como perda econômica final. Fonte: `estudo/1599001-38501-20221212113215.pdf`.
- Seller mensal privilegia métricas estruturais como cobertura e subordinação, mostrando que inadimplência isolada não esgota a análise do risco do fundo. Fonte: `estudo/2159283-43161-20260309175427.pdf`.

## O que o dashboard não deve fazer

- transformar campo ausente em zero;
- assumir que bucket do IME equivale à política de provisão do fundo;
- mostrar provisão como métrica universal se a fonte não a reporta;
- misturar provisão contábil com perda econômica realizada.

## Regra prática para o produto

Cada número ligado a perdas deveria carregar um rótulo explícito:

- `atraso reportado`;
- `provisão reportada`;
- `perda esperada calculada`;
- `perda realizada`;
- `não informado`;
- `não aplicável`.

## Risco de interpretação simplista

Dois fundos com o mesmo atraso podem ter riscos muito diferentes se:

- um tiver forte mecanismo de recompra/resolução;
- outro depender apenas de subordinação;
- um tiver política agressiva de provisão;
- outro tiver atraso alto, mas spread e liquidez ainda confortáveis.

## Fontes desta página

- Fonte local: `estudo/1337461-15981-20200901100422.pdf`.
- Fonte local: `estudo/1599001-38501-20221212113215.pdf`.
- Fonte local: `estudo/2159283-43161-20260309175427.pdf`.
