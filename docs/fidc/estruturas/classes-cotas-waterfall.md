# Classes, subclasses, cotas e waterfall

## Classe e subclasse

Na arquitetura da Resolução CVM 175, o fundo pode ser organizado em classes e subclasses. A Parte Geral consolidada já traz, nas definições iniciais, a ideia de apêndices descritivos de subclasses e de assembleias especiais por classe ou subclasse.

Em FIDC real, isso muda a leitura do produto:

- pode haver classe única com diferentes séries de cotas;
- pode haver classes segregadas;
- pode haver subclasses com público-alvo, remuneração e risco próprios.

## Tipos de cotas na prática

Nos documentos do acervo, a nomenclatura recorrente é:

- cota sênior;
- cota subordinada mezanino;
- cota subordinada júnior ou simplesmente subordinada.

Sob RCVM 175, a terminologia formal de classes/subclasses convive, na prática de mercado, com a linguagem histórica de séries e cotas sênior/mezanino/subordinada. O dashboard precisa aceitar as duas camadas sem confundir o usuário.

## O que é waterfall

Waterfall, aqui, é a ordem econômica de alocação do caixa do fundo:

1. encargos e despesas;
2. pagamentos prioritários;
3. remuneração/amortização das cotas mais seniores;
4. absorção residual de perdas pelas cotas subordinadas.

O ponto não é decorar uma cascata genérica. O ponto é ler a ordem efetiva de cada fundo.

## Em termos práticos no acompanhamento

Três perguntas são mais úteis do que um desenho bonito da cascata:

1. quem absorve a primeira perda;
2. quando a subordinação deixa de ser suficiente;
3. quais travas impedem distribuição de caixa em cenário de deterioração.

## O que varia conforme o regulamento

- prioridade entre despesas, remuneração e amortização;
- classe-alvo de proteção;
- definição do cálculo de subordinação;
- gatilhos de turbo amortization ou bloqueio de distribuição;
- eventos que alteram a ordem normal do caixa.

## Exemplo real

O Seller mensal mostra, lado a lado, índices de subordinação, subordinação para amortização, cobertura e alocação mínima. Isso é mais útil para o acompanhamento recorrente do que uma descrição longa da cascata sem métricas verificáveis. Fonte: `estudo/2159283-43161-20260309175427.pdf`.

O iCred FGTS mensal mostra múltiplas cotas sênior e mezanino com benchmarks diferentes, o que reforça que a visualização do app deve conseguir distinguir:

- tranche;
- benchmark;
- prazo de resgate;
- rating;
- retorno realizado.

Fonte: `estudo/2159394-59901-20260310142833.pdf`.

## Base regulatória

- Resolução CVM 175, Parte Geral: estrutura por classe/subclasse e governança.
- Resolução CVM 175, Anexo Normativo II: especificidades do FIDC e exigências aplicáveis às cotas e subclasses em FIDC.

## Risco de interpretação simplista

Subordinação não é um número mágico. Ela só faz sentido se o analista também observar:

- qualidade da originação;
- velocidade de amortização;
- elegibilidade;
- dinâmica de recompras/resoluções;
- reservas e cobertura.

## Fontes desta página

- Norma oficial: Resolução CVM 175, Parte Geral.
- Norma oficial: Resolução CVM 175, Anexo Normativo II.
- Fonte local: `estudo/2159283-43161-20260309175427.pdf`.
- Fonte local: `estudo/2159394-59901-20260310142833.pdf`.
