# Informe Mensal: Tabela II, segmentos e qualidade de dados

## O que é

A Tabela II do Informe Mensal distribui valores de direitos creditórios por atividade econômica ou natureza de crédito. Ela é um reporte padronizado e pode ser usada para estratificar o universo, desde que não seja confundida com classificação ANBIMA ou com descrição funcional extraída de regulamento.

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

- F1 — crédito consignado;
- F2 — crédito pessoal;
- F3 — crédito corporativo;
- F4 — middle market;
- F5 — veículos;
- F6 — imobiliário empresarial;
- F7 — imobiliário residencial;
- F8 — outros.

A abertura “outros” não é descrição econômica suficiente. Para entender se a carteira é, por exemplo, NPL, crédito estudantil ou financiamento a fintechs, é necessário consultar os documentos e, se útil, atribuir uma **taxonomia funcional documental** separada.

## Convenção analítica usada no corpus de 100

Para o campo técnico `subtipo_cvm_ime` do ledger:

1. soma-se o vetor dos 11 blocos no nível do fundo;
2. escolhe-se o maior bloco;
3. se o vencedor não for Financeiro, conserva-se seu nome oficial;
4. se for Financeiro, usa-se a maior abertura F1–F8;
5. se o total for zero, usa-se **Sem segmentação IME**;
6. se o dominante representar menos de 60% do total informado, marca-se híbrido/multissegmento.

Esse campo é uma convenção de seleção, não “subtipo oficial CVM”. O vetor completo e a participação dominante devem ser preservados.

## Fundo, classe e série no arquivo

O ranking econômico deve ocorrer por `cnpj_fundo`. Quando várias classes reportantes pertencem ao mesmo fundo, o PL é somado, conservando-se os CNPJs componentes para ligar anexos e documentos. Linhas de subclasses ou séries — inclusive na Tabela X.2 — não são fundos adicionais.

O analista deve registrar o nível original do dado. Somar classes resolve o ranking do fundo, mas não apaga o patrimônio segregado nem autoriza combinar cláusulas de classes diferentes.

## Zero, ausência e “Sem segmentação IME”

- **Zero reportado:** há campo aplicável preenchido com zero.
- **Ausência:** o campo ou registro não está disponível; não deve virar zero por imputação silenciosa.
- **Sem segmentação IME:** não há valores suficientes na Tabela II para classificar. É estrato de qualidade de dados.

Um fundo pode ter PL positivo e Tabela II zerada. Isso pede investigação de escopo, fase operacional, classe reportante, retificação ou qualidade do envio; não prova carteira vazia.

## O que a Tabela II informa — e o que não informa

Ela ajuda a medir composição por segmento e predominância. Não identifica necessariamente:

- devedor, cedente ou originador individual;
- garantia e prioridade;
- elegibilidade ou cadeia de transferência;
- concentração por grupo econômico;
- regime de coobrigação;
- waterfall, gatilhos ou reserva;
- taxonomia funcional fina.

## Validações mínimas

1. usar a `competencia_snapshot` declarada no metadata e rejeitar mês preliminar incompleto;
2. normalizar CNPJ em 14 dígitos;
3. reconciliar classes e PL agregado;
4. preservar o vetor completo A–K e F1–F8;
5. separar FIC-FIDC para avaliar dupla contagem econômica;
6. documentar retificações, campos ausentes e dominância;
7. nunca chamar a taxonomia interna `setor_n1/setor_n2` de subtipo CVM.

Fonte operacional: padrão XML mensal FIDC/CVMWeb e arquivos oficiais do Informe Mensal. Verificação: **16/07/2026**.
