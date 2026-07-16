# Informe Mensal: Tabela II, segmentos e qualidade de dados

## O que é

- **O que mostra:** a Tabela II do Informe Mensal distribui valores de direitos creditórios por atividade econômica ou natureza de crédito.
- **Para que serve:** permite comparar a composição reportada de fundos e classes em uma base padronizada.
- **O que não é:** não é a classificação da **Associação Brasileira das Entidades dos Mercados Financeiro e de Capitais (ANBIMA)** nem a descrição funcional extraída do regulamento.

## Os 11 segmentos oficiais

Os blocos oficiais são:

1. Industrial;
2. Comercial;
3. Serviços;
4. Agronegócio;
5. Financeiro;
6. Imobiliário;
7. Cartão de crédito;
8. Factoring;
9. Setor público;
10. Ações judiciais;
11. Marcas e patentes.

Esses nomes são chamados neste book de **segmento oficial da Tabela II do Informe Mensal**.

## As oito aberturas do bloco Financeiro

Quando Financeiro é o bloco relevante, a própria Tabela II oferece oito **aberturas financeiras da Tabela II**:

- **F1:** crédito consignado;
- **F2:** crédito pessoal;
- **F3:** crédito corporativo;
- **F4:** empresas de médio porte, ou *middle market*;
- **F5:** veículos;
- **F6:** imobiliário empresarial;
- **F7:** imobiliário residencial;
- **F8:** outros.

A abertura “outros” não é descrição econômica suficiente. Para entender se a carteira é, por exemplo, de **créditos inadimplidos, chamados de Non-Performing Loans (NPLs)**, crédito estudantil ou financiamento a empresas de tecnologia financeira, é necessário consultar os documentos e, se útil, atribuir uma **taxonomia funcional documental** separada.

## Convenção analítica usada no corpus de 100

Para o campo técnico `subtipo_cvm_ime` do registro da amostra:

1. soma-se o vetor dos 11 blocos no nível do fundo;
2. escolhe-se o maior bloco;
3. se o vencedor não for Financeiro, conserva-se seu nome oficial;
4. se for Financeiro, usa-se a maior abertura F1 a F8;
5. se o total for zero, usa-se **Sem segmentação IME**;
6. se o dominante representar menos de 60% do total informado, marca-se híbrido/multissegmento.

- **Natureza do campo:** é uma convenção de seleção, não “subtipo oficial da Comissão de Valores Mobiliários (CVM)”.
- **Nome legado:** **IME** aparece apenas no nome histórico do campo e do estrato; não é o nome oficial do informe.
- **Rastro:** vetor completo e participação dominante devem ser preservados.

## Fundo, classe e série no arquivo

- **Ranking do fundo:** use o **Cadastro Nacional da Pessoa Jurídica (CNPJ)** do fundo.
- **Várias classes reportantes:** some o **patrimônio líquido (PL)** das classes para o ranking, mas preserve os CNPJs componentes e seus anexos.
- **Subclasses e séries:** linhas da Tabela X.2 não são fundos adicionais.

O analista deve registrar o nível original do dado. Somar classes resolve o ranking do fundo, mas não apaga o patrimônio segregado nem autoriza combinar cláusulas de classes diferentes.

## Zero, ausência e “Sem segmentação IME”

- **Zero reportado:** há campo aplicável preenchido com zero.
- **Ausência:** o campo ou registro não está disponível; não deve virar zero por imputação silenciosa.
- **Sem segmentação IME:** não há valores suficientes na Tabela II para classificar. É estrato de qualidade de dados.

Um fundo pode ter patrimônio líquido positivo e Tabela II zerada. Isso pede investigação de escopo, fase operacional, classe reportante, retificação ou qualidade do envio; não prova carteira vazia.

## O que a Tabela II informa e o que não informa

Ela ajuda a medir composição por segmento e predominância. Não identifica necessariamente:

- devedor, cedente ou originador individual;
- garantia e prioridade;
- elegibilidade ou cadeia de transferência;
- concentração por grupo econômico;
- regime de coobrigação;
- cascata de pagamentos, gatilhos ou reserva;
- taxonomia funcional fina.

## Validações mínimas

1. usar a `competencia_snapshot` declarada no arquivo de metadados e rejeitar mês preliminar incompleto;
2. normalizar o CNPJ em 14 dígitos;
3. reconciliar classes e patrimônio líquido agregado;
4. preservar o vetor completo A a K e F1 a F8;
5. separar **classes de investimento em cotas de FIDC (FIC-FIDC)** para avaliar dupla contagem econômica;
6. documentar retificações, campos ausentes e dominância;
7. nunca chamar a taxonomia interna `setor_n1/setor_n2` de subtipo da CVM.

Fonte operacional: padrão de arquivo **Extensible Markup Language (XML)** mensal de Fundo de Investimento em Direitos Creditórios (FIDC) no CVMWeb e arquivos oficiais do Informe Mensal. Verificação: **16/07/2026**.
