# O que é FIDC e o que são direitos creditórios

## O que é

Na prática econômica, um FIDC é um fundo que concentra recursos para adquirir direitos creditórios e outros ativos permitidos, organizando risco, subordinação, remuneração e governança em torno dessa carteira.

Na revisão oficial usada nesta base, a norma estrutural relevante é a [Resolução CVM 175](../regulacao/hierarquia-regulatoria.md), especialmente o Anexo Normativo II para FIDC. Já os regulamentos dos fundos do acervo mostram como essa moldura normativa é concretizada em carteiras reais.

## O que são direitos creditórios

Direito creditório não é sinônimo de “qualquer recebível” em sentido solto. O ponto central é haver um crédito identificável, cedível ao fundo e enquadrado na política de investimento, nas condições de cessão e nos critérios de elegibilidade.

Nos documentos do acervo, isso aparece de formas diferentes:

- no Seller, os direitos creditórios se ligam a transações de pagamento e a operações com sub-rogação no ecossistema Mercado Pago/Mercado Crédito;
- no Facta INSS CB e no Agibank, os direitos se conectam a empréstimos consignados representados por CCBs;
- no BV Veículos, os créditos decorrem de financiamentos de veículos automotores representados por CCBs;
- no Cielo, a lógica passa pelo arranjo de pagamentos e pela posição da Cielo como devedor nas estruturas monitoradas.

## Em termos práticos no acompanhamento

Quando um analista acompanha um FIDC, o primeiro filtro deveria ser:

1. qual é a natureza jurídica e operacional do crédito;
2. quem origina;
3. quem deve;
4. se existe ou não coobrigação/regresso;
5. como o crédito entra, performa e sai da carteira.

Sem isso, métricas como inadimplência, subordinação e amortização perdem contexto.

## O que costuma variar conforme o regulamento

- definição exata do que conta como direito creditório elegível;
- documentos exigidos para cessão;
- critérios de elegibilidade;
- hipóteses de recompra, resolução ou substituição;
- coexistência com caixa, títulos públicos e outros ativos permitidos;
- limites de concentração, prazo, coobrigação e revolvência.

## O que não é seguro assumir

- que todo FIDC financeiro tem a mesma lógica de risco;
- que todo crédito cedido é sem coobrigação;
- que todo atraso no IME mede a mesma coisa que atraso econômico do fundo;
- que os buckets do XML substituem a leitura do regulamento.

## Sinal importante para o app

O dashboard não deveria apresentar apenas “direitos creditórios” como um bloco genérico. Ele precisa identificar a família de crédito e mostrar, logo no topo:

- tipo de recebível;
- cedente/originador;
- devedor;
- coobrigação;
- documento-fonte da elegibilidade.

## Fontes desta página

- Norma oficial: Resolução CVM 175, Anexo Normativo II.
- Fonte local: [Seller FIDC - regulamento](../fontes/referencias.md).
- Fonte local: [Facta INSS CB - regulamento](../fontes/referencias.md).
