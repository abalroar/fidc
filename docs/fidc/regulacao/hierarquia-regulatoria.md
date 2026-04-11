# Hierarquia regulatória: 175, 160, 30 e o padrão XML

## Visão curta

Na revisão oficial feita para este repositório, a arquitetura normativa principal do projeto ficou assim:

1. `Resolução CVM 175` e `Anexo Normativo II`: estrutura, funcionamento e divulgação do FIDC.
2. `Resolução CVM 160`: oferta pública e rito de distribuição.
3. `Resolução CVM 30`: categorias de investidores e suitability.
4. `Padrão XML Mensal FIDC` na CVMWeb: camada operacional de reporte.

## O que a Resolução CVM 175 cobre

A página oficial da norma já descreve a Resolução CVM 175 como a regra sobre constituição, funcionamento e divulgação de informações dos fundos de investimento. A mesma página aponta expressamente o `Anexo Normativo II` como o anexo dos fundos de investimento em direitos creditórios.

Na prática do book, isso significa:

- se a pergunta é “o que é o FIDC, como ele se organiza e quais peças estruturais importam?”, o ponto de partida é a 175;
- se a pergunta é “qual anexo eu leio para FIDC?”, a resposta é o Anexo II.

## O que a Resolução CVM 160 cobre

A 160 entra quando a pergunta muda para:

- como a oferta pública é estruturada;
- qual o rito de registro;
- quais documentos de distribuição fazem parte da operação.

No acervo local, anúncios de início, encerramento e comunicados ao mercado de ofertas sob rito automático aparecem em diversos fundos, como Seller, Supplier, Fortbrasil e iCred 2.

## O que a Resolução CVM 30 cobre

A 30 é a referência certa para categorias de investidor e suitability.

Na versão consolidada consultada:

- o `art. 11` define investidores profissionais;
- o `art. 12` define investidores qualificados.

Isso é particularmente importante para não confundir:

- fundo para investidor profissional;
- fundo para investidor qualificado;
- oferta pública destinada a um ou outro público.

## Onde entra o padrão XML mensal

O padrão XML mensal é essencial para o app, porque o dashboard atual parte do IME. Mas ele é uma camada de reporte, não o eixo principal da estrutura do fundo.

Na prática:

- o XML ajuda a entender campos, buckets e blocos reportados;
- o XML não substitui o regulamento;
- o XML não resolve sozinho elegibilidade, eventos, reserves, spread, FPD ou covenants específicos.

## O que isso corrige na memória regulatória do projeto

Na revisão oficial feita aqui, o eixo central não foi `576 + outra norma + 505`. O que apareceu com clareza foi:

- `175/Anexo II` para o FIDC em si;
- `160` para oferta;
- `30` para investidor;
- padrão XML como infraestrutura de reporte.

Se a equipe quiser escrever páginas normativas mais profundas, a próxima etapa deve citar artigo por artigo conforme o tema, mas a hierarquia base já está suficientemente clara para orientar a arquitetura do book.

## Consequência prática para a knowledge base

Cada página do book deve informar explicitamente se a afirmação vem de:

- norma geral da CVM;
- norma de oferta;
- regra de categoria de investidor;
- orientação oficial da CVM;
- documento específico do fundo.

## Fontes desta página

- Página oficial da Resolução CVM 175: https://conteudo.cvm.gov.br/legislacao/resolucoes/resol175.html
- Resolução CVM 175, Parte Geral consolidada.
- Resolução CVM 175, Anexo Normativo II consolidado.
- Resolução CVM 160 consolidada.
- Resolução CVM 30 consolidada.
- Padrão XML Mensal FIDC da CVMWeb.
