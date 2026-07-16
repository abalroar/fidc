# Guia de uso do Glossário de FIDCs

- **Para quem é:** analistas de crédito e profissionais comerciais que já conhecem crédito e demonstrações financeiras, mas precisam entender a estrutura dos **Fundos de Investimento em Direitos Creditórios (FIDCs)**.
- **O que conecta:** norma, contrato, operação e reporte regulatório. Essas quatro camadas se complementam, mas uma não prova a outra.
- **Como usar:** comece pelo conceito e siga as referências para a aplicação. A definição completa fica em uma página canônica para evitar versões contraditórias.
- **O que não faz:** o glossário não atribui classificação de risco, não recomenda investimento e não avalia a situação corrente de um fundo.

## Como ler

Uma sequência eficiente é:

1. [FIDC, classe, direito creditório e patrimônio segregado](glossario/o-que-e-fidc.md);
2. [participantes e responsabilidades](participantes/participantes.md);
3. [fundo, classe, subclasse, série, cota e cascata de pagamentos](estruturas/classes-cotas-waterfall.md);
4. [cessão, endosso, elegibilidade, regresso e lastro](glossario/cessao-e-resolucao.md);
5. [Tabela II do Informe Mensal](regulacao/informe-mensal-tabela-ii.md);
6. [métricas de desempenho](metricas/provisao-perdas-e-inadimplencia.md) e [métricas de estrutura](metricas/metricas-estruturais.md);
7. [eventos e governança](eventos/eventos-de-avaliacao-e-liquidacao.md).

## A hierarquia em uma abertura

- **Fundo**
  - É o veículo e o nível de governança. Pode ter uma ou mais classes.
  - **Classe A: patrimônio segregado A**
    - Aqui ficam a carteira, os passivos, as despesas e os cotistas vinculados à Classe A.
    - **Subclasse sênior**
      - Tem a prioridade definida no regulamento.
      - **Série 1**, quando admitida
        - **Cotas da Série 1:** unidades detidas pelos investidores.
    - **Subclasse mezanino**
      - Fica abaixo da sênior e acima da camada subordinada indicada.
    - **Subclasse subordinada**
      - Recebe resultados e absorve perdas na ordem contratual.
  - **Classe B: patrimônio segregado B**
    - Tem carteira, obrigações e regras próprias. Não responde automaticamente pela Classe A.

- **Emissão:** ato que cria um lote de cotas.
- **Oferta:** processo de distribuir essas cotas.
- **Tranche:** rótulo econômico que precisa ser mapeado para subclasse, série ou emissão.

## Quatro naturezas de afirmação

| Natureza | O que sustenta | Como ler neste glossário |
|---|---|---|
| **Normativa** | obrigação, faculdade ou definição prevista em norma | traz a norma, o dispositivo e a data de verificação |
| **Contratual** | regra de uma classe ou emissão | aponta o regulamento, anexo ou instrumento aplicável |
| **Prática recorrente** | cláusula encontrada em estruturas independentes | informa o denominador documentado e não transforma frequência em obrigação |
| **Convenção analítica** | cálculo construído para comparação | explicita fórmula, base, unidade e limitação |

- **Um limite de um fundo** não vira parâmetro universal.
- **Ausência na extração** não comprova inexistência de cláusula.
- **Texto intermediário em cache sem o documento primário** serve para localizar um candidato, não para sustentar afirmação categórica.

## O que o Informe Mensal mostra

- **Patrimônio líquido (PL)**, composição da carteira, vencidos por faixa, provisões ou reduções ao valor recuperável, aquisições, alienações, liquidações, cotas e movimentações reportadas.
- A [Tabela II](regulacao/informe-mensal-tabela-ii.md) distribui os direitos em **11 segmentos oficiais** e detalha o bloco Financeiro em **oito aberturas**.
- A série mensal ajuda a localizar mudança de composição, atraso, provisão, liquidez e capital. Ela é ponto de partida para perguntas, não resposta completa sobre o contrato.

## O que exige outro documento

- **Elegibilidade:** se cada crédito satisfaz os testes de entrada.
- **Capital e caixa:** a ordem de pagamentos, a absorção de perdas e os limites para amortizar cada camada.
- **Concentração:** limites por devedor, grupo econômico, cedente, originador, convênio ou prestador.
- **Garantias e lastro:** constituição, registro, prioridade, documentação e possibilidade de execução.
- **Eventos e governança:** gatilhos, prazo de correção, dispensa pontual e efeito de uma assembleia.
- **Operação:** qualidade da originação, cobrança, conciliação, conta de recebimento e continuidade do prestador.

## Vocabulário de classificação

- **Segmento oficial da Tabela II do Informe Mensal:** um dos 11 blocos oficiais.
- **Abertura financeira da Tabela II:** detalhamento F1 a F8 do bloco Financeiro.
- **Taxonomia funcional documental:** classificação inferida de documentos, como consignado, risco sacado, meios de pagamento, crédito estudantil ou crédito inadimplido.
- **Sem segmentação IME:** estrato de qualidade de dados usado quando a Tabela II não traz valores suficientes. A sigla IME aparece em artefatos legados para se referir ao Informe Mensal; não é um subtipo oficial.

## Escopo documental da revisão

- **100 fundos** foram selecionados na competência 202605 com cobertura de todos os estratos ocupados.
- **731 documentos primários** foram processados página a página, somando 721 impressões digitais criptográficas únicas e 21.028 páginas deduplicadas.
- **95 regulamentos vigentes** tiveram texto recuperado e extraído.
- **15 regulamentos de 12 famílias independentes** receberam leitura substantiva de cláusulas para as frequências contratuais, cobrindo 48,44% do PL da amostra.
- **10 casos narrativos** aparecem no glossário apenas como exemplos rastreáveis. Eles não representam o tamanho total do corpus.

Veja [Corpus de 100 FIDCs e casos documentais](tipos-de-fundos/fundos-de-referencia.md) e [Referências e rastreabilidade](fontes/referencias.md) para a escada completa de evidência.

Última verificação normativa: **16/07/2026**.
