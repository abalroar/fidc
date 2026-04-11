# Book FIDC: escopo, método e trilha de leitura

Este acervo foi criado para ser a camada canônica de conhecimento FIDC do repositório. O desenho é deliberado:

- o texto humano vive em Markdown;
- a navegação do app lê esse mesmo Markdown;
- o índice e as fontes ficam em `docs/fidc/_data/`;
- a base pode ser reaproveitada por Obsidian, busca local e futuro RAG.

## Regra editorial

Este book só deve afirmar algo quando a afirmação estiver ancorada em:

1. norma oficial da CVM;
2. orientação oficial da CVM;
3. documento oficial do fundo presente em `estudo/`.

Isso significa que esta base diferencia de forma explícita:

- exigência regulatória;
- prática de mercado;
- cláusula específica de regulamento;
- observação analítica extraída de fundo real.

## O que esta base cobre

- fundamentos do FIDC e dos direitos creditórios;
- papéis dos participantes da estrutura;
- classes, cotas, subordinação e waterfall;
- métricas estruturais recorrentes;
- eventos de avaliação e liquidação antecipada;
- famílias de recebíveis financeiros;
- comparação entre FIDCs com cedentes IFs ou carteiras originadas por IFs.

## O que esta base não deve fazer

- tratar uma cláusula de um fundo como regra universal;
- tratar padrão XML do IME como se fosse a norma estrutural do FIDC;
- preencher lacuna documental com suposição;
- esconder ambiguidade de dado ou de norma.

## Trilha mínima de leitura

1. [Hierarquia regulatória](regulacao/hierarquia-regulatoria.md)
2. [O que é FIDC e o que são direitos creditórios](glossario/o-que-e-fidc.md)
3. [Participantes da estrutura](participantes/participantes.md)
4. [Classes, subclasses, cotas e waterfall](estruturas/classes-cotas-waterfall.md)
5. [Métricas estruturais e guardrails](metricas/metricas-estruturais.md)
6. [Recebíveis financeiros](recebiveis/recebiveis-financeiros.md)
7. [Análise comparativa de FIDCs com originação financeira](tipos-de-fundos/fidcs-com-originacao-if.md)

## Como isso conversa com o dashboard

O dashboard atual do projeto extrai e organiza o IME da CVM. Isso é útil, mas insuficiente para cobrir toda a camada estrutural de um FIDC. O book existe justamente para:

- explicar o que o XML entrega e o que ele não entrega;
- mostrar quais métricas dependem de regulamento ou relatório mensal;
- orientar a expansão da UI para além do IME básico.

Exemplo prático:

- `alocação em direitos creditórios`, `subordinação` e `inadimplência` podem aparecer no IME;
- `índice de cobertura`, `relação mínima`, `excesso de spread`, `reserva de liquidez` e `first payment default` costumam depender de regulamento e relatório de monitoramento;
- `rating`, `público-alvo`, `rito da oferta` e `classe/subclasse` exigem leitura combinada de norma, suplemento e material de distribuição.

## Fontes-base desta fase

- Resolução CVM 175 e Anexo Normativo II de FIDC.
- Resolução CVM 160.
- Resolução CVM 30.
- Padrão XML Mensal FIDC da CVMWeb.
- Regulamentos e relatórios mensais de fundos reais do acervo, com destaque para Seller, Facta INSS CB, GERU, Supplier, Agibank I, iCred FGTS, Cielo e BV Veículos.

## Observação de método

Na revisão feita aqui, o eixo normativo central foi:

- `RCVM 175 + Anexo II` para estrutura e funcionamento do FIDC;
- `RCVM 160` para oferta pública;
- `RCVM 30` para categorias de investidor;
- padrão XML/CVMWeb como camada de reporte.

Ou seja: a antiga referência associada ao XML mensal não é a espinha regulatória principal do veículo.

## Fontes desta página

- Fonte oficial: Resolução CVM 175, página oficial e anexos consolidados.
- Fonte oficial: padrão XML mensal FIDC da CVMWeb.
- Fonte local: [Seller FIDC - relatório mensal fevereiro/2026](fontes/referencias.md).
