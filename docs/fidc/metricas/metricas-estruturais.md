# Métricas estruturais, inadimplência e guardrails

## Regra de leitura

Nem toda métrica importante de FIDC é:

- regulatória;
- universal;
- disponível no IME.

Para não induzir leitura errada, o book separa as métricas em três grupos.

## 1. Métricas quase universais de acompanhamento

Essas aparecem com frequência alta e fazem sentido em boa parte dos fundos:

- patrimônio líquido;
- tamanho por classe/cota;
- alocação em direitos creditórios;
- inadimplência/atraso;
- provisão/perdas;
- subordinação;
- concentração;
- emissões, amortizações e resgates.

## 2. Métricas estruturais recorrentes, mas dependentes do regulamento

Essas já aparecem em vários fundos reais do acervo, mas não são universais:

- alocação mínima;
- índice de cobertura;
- relação mínima;
- índice mínimo de subordinação;
- subordinação para amortização;
- excesso de spread;
- reserva de caixa;
- reserva de liquidez;
- reserva de despesas e encargos;
- first payment default;
- índices de refinanciamento;
- métricas de resolução, recompra, erros ou pagamentos incorretos.

## 3. Métricas fortemente idiossincráticas

Aqui o risco de generalização é alto. Exemplos do acervo:

- `DCV`, `DCV 30`, `DCV 120`, `DCV 180` no Supplier;
- índices de resolução e pagamentos incorretos em Volkswagen Tera;
- combinação específica entre cobertura, subordinação e alocação no Seller;
- relação mínima e FPD em GERU.

## Como ler as principais métricas

### Subordinação

É um colchão estrutural, não uma garantia. Sozinha, ela não resolve má originação, concentração ruim ou quebra operacional.

### Cobertura

Normalmente tenta mostrar se o fundo mantém margem estrutural suficiente para suportar determinada tranche. A fórmula precisa ser a do documento do fundo, não uma aproximação genérica do app.

### Alocação mínima

Importa especialmente em fundos com mistura entre direitos creditórios e outros ativos. Se o fundo estiver subalocado em crédito, o perfil econômico da carteira muda.

### Inadimplência

Pode significar coisas diferentes a depender do documento:

- atraso contratual bruto;
- crédito vencido e não pago;
- bucket regulatório do IME;
- inadimplência com ou sem provisão;
- atraso relevante apenas após janela mínima.

### Provisão / perda esperada

Não existe uma leitura única. Em FIDC, a política pode depender:

- do regulamento;
- da política contábil;
- do estágio da carteira;
- da existência de recompras, resolução ou reforço estrutural.

## O que os fundos reais do acervo mostram

- Seller mensal: alocação mínima, cobertura sênior, subordinação e subordinação para amortização aparecem como núcleo do monitoramento. Fonte: `estudo/2159283-43161-20260309175427.pdf`.
- GERU: relação mínima, alocação mínima, índice de cobertura e FPD aparecem como guardrails centrais. Fonte: `estudo/1337461-15981-20200901100422.pdf`.
- Supplier: excesso de spread, reservas, DCV e refinanciamento mostram uma camada de monitoramento muito mais rica do que o IME padrão. Fonte: `estudo/1385961-759-20210301165301.pdf`.
- Volkswagen Tera: recompra, resolução, erros e pagamentos incorretos lembram que o risco operacional e contratual pode ser decisivo. Fonte: `estudo/2076171-63381-20250204121014.pdf`.

## O que isso implica para o dashboard

O dashboard deveria classificar toda métrica mostrada como uma das categorias abaixo:

- `reportada no IME`;
- `derivada do IME`;
- `reportada em relatório mensal`;
- `exigida por regulamento`;
- `métrica específica do fundo`.

Essa rotulagem é necessária para não passar falsa sensação de comparabilidade.

## Risco de interpretação simplista

Esta base não encontrou `arrasto` como termo recorrente e estruturante nos documentos amostrados do acervo. Se esse tema entrar no book, ele deve entrar apenas quando houver cláusula documentada em fundo específico.

## Fontes desta página

- Fonte oficial: Ofício-Circular CVM/SSE 8/2023.
- Fonte local: `estudo/2159283-43161-20260309175427.pdf`.
- Fonte local: `estudo/1385961-759-20210301165301.pdf`.
- Fonte local: `estudo/1337461-15981-20200901100422.pdf`.
- Fonte local: `estudo/1599001-38501-20221212113215.pdf`.
- Fonte local: `estudo/2076171-63381-20250204121014.pdf`.
