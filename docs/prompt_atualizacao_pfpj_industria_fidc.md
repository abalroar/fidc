# Prompt mestre — atualização de saldo, taxonomia e emissões de FIDCs

Use este prompt para atualizar os slides de Saldo e Tipos de FIDCs, Emissões por setor, abertura de Outros e o ranking de prestadores. Trabalhe com fontes oficiais, leitura documental integral e bases auditáveis por CNPJ.

## Objetivo

Atualizar o PPTX e os arquivos de apoio com:

1. saldo ex-FIC por categoria;
2. abertura Multicarteira Pulverizado PF/PJ;
3. categorias Recuperação / NP, Precatórios / ações e Multicedente / multisacado;
4. novas emissões por setor, usando as mesmas listas de CNPJs;
5. ranking Top 5 de administração, gestão e custódia, com Itaú e Kanastra separados e incluídos como comparadores;
6. cenário sem FIDC TAPSO e FIDC do Sistema Petrobras.

Produza CSVs por CNPJ e por oferta antes de escrever qualquer número no PPTX. Um número ausente dos CSVs não pode aparecer no material.

## Fontes e precedência

Use, nesta ordem:

1. regulamento vigente na competência, lido integralmente;
2. documentos oficiais complementares do fundo ou da classe no FundosNet/B3/CVM;
3. cadastro e Informe Mensal da CVM;
4. Tipo e Foco ANBIMA;
5. ledger documental aprovado;
6. inferência, somente quando necessária, identificada como inferência e acompanhada de evidência.

O regulamento define o mandato permitido. A carteira efetiva da competência vem do Informe Mensal. Preserve divergências entre mandato e carteira; não transforme mandato em composição observada.

## Competência, universo e extinção

1. Confirme a competência mais recente com cobertura completa.
2. Para saldo, use uma linha por competência e CNPJ de fundo, PL numérico e não ausente.
3. Exclua FIC-FIDC do numerador e denominador.
4. Exclua do saldo corrente fundos extintos, encerrados ou sem veículo ativo na competência, após confirmar o status oficial. Ausência de reporte isolada não prova extinção.
5. Emissões são fluxo histórico. Uma emissão encerrada permanece no período mesmo que o fundo tenha sido extinto depois.
6. Não impute zero para dado ausente. Use N/D e registre a causa.
7. Mantenha cenário original e cenário sem:
   - FIDC do Sistema Petrobras — CNPJ 09.195.235/0001-50;
   - TAPSO FIDC — CNPJ 26.287.464/0001-14.
8. No cenário sem os dois fundos, retire seus PLs do numerador e do denominador em todas as competências. Recalcule emissões se qualquer um dos CNPJs aparecer na coorte; nunca presuma impacto zero.

## Classificação temporal

Construa um ledger efetivo por CNPJ com competência_inicio, competência_fim, fonte, data do documento e decisão.

- Se a classificação mudou, aplique a classificação válida em cada competência.
- Se só houver evidência atual e o histórico for necessário, escolha entre:
  1. investigar documentos históricos e formar intervalos efetivos; ou
  2. retroaplicar a classificação atual como cenário reconstruído.
- Identifique claramente a opção usada.
- Nunca sobrescreva silenciosamente a classificação histórica.
- Um fundo novo entra após leitura do regulamento e validação do CNPJ da classe/fundo.
- Se o fundo sair de Financeiro e estiver na lista PF/PJ, interrompa a atualização automática e investigue o conflito antes de decidir.

## Multicarteira Pulverizado PF/PJ

### Produtos que podem permanecer na abertura

Inclua fundos cujo regulamento vigente confirme crédito direto a PF ou PJ, inclusive:

- empréstimo pessoal;
- crédito estudantil;
- BNPL ou crédito parcelado ao consumidor;
- crédito direto a micro, pequenas ou médias empresas;
- crédito solar ou financiamento de equipamentos, quando a obrigação for direta do tomador PF/PJ e não se tratar de financiamento imobiliário;
- outros produtos diretos PF/PJ encontrados em fundos novos, desde que a natureza seja documentada.

CCB, isoladamente, não comprova o produto, o tipo de devedor nem a pulverização. Leia definições, política de investimento, critérios de elegibilidade, concentração, anexos e regras de originação.

### Produtos mantidos em Financeiro

Mantenha em Financeiro:

- consignado, INSS e FGTS;
- veículos;
- imobiliário;
- adquirência, agenda de recebíveis, cartão ou meios de pagamento como produto principal;
- banco emissor e outras carteiras financeiras sem evidência suficiente para a abertura;
- Sólido, ordem 11 do ledger de 01/09/2026;
- BizCapital Finpass PME, ordem 26 do mesmo ledger.

Garantia em recebíveis, débito em conta, cartão usado para autenticação ou equipamento instalado em imóvel não mudam automaticamente o produto. Examine a função jurídica e econômica no regulamento.

### Concentração observada

1. Reconcile Tabela I, Tabela II e Tabela VIII do Informe Mensal.
2. Calcule direitos creditórios brutos como direitos creditórios líquidos da Tabela I mais PDD, preservando ajustes documentados.
3. Use a maior posição positiva reportada na Tabela VIII como proxy Top1.
4. Critério vigente do ledger de 01/09/2026: Top1 / DC brutos menor ou igual a 1%.
5. Não exija 25 posições positivas. Registre quantas posições foram efetivamente reportadas.
6. Posições reportadas não equivalem ao número total de devedores. numero_total_devedores permanece N/D quando não houver campo oficial.
7. A soma das posições reportadas é somente a soma das linhas disponíveis, não a carteira inteira.
8. Registre limites contratuais, exceções e dispensas separadamente do observado mensal.

### Métrica exibida

O valor da categoria é o PL integral dos fundos selecionados, não a exposição efetiva em crédito PF/PJ. Publique em conjunto:

- quantidade de fundos;
- PL dos fundos;
- participação no PL ex-FIC;
- quantidade de posições reportadas;
- exposição efetiva PF/PJ = N/D, salvo apuração de carteira que feche;
- total de devedores = N/D, salvo campo oficial.

Na referência de jun/26, preserve as 26 decisões do ledger e inclua os 24 fundos aprovados. As ordens 11 e 26 ficam em Financeiro.

## Outras aberturas de Outros

Aplique primeiro o overlay documental aprovado ao Tipo/Foco ANBIMA. Depois use:

- Precatórios / ações: Tipo Outros + Foco Poder Público.
- Multicedente / multisacado: Tipo Outros + Foco Multicarteira Outros ou Multicedente/Multissacado.
- Recuperação / NP: Tipo Outros + Foco Recuperação.
- N/D: qualquer linha que não feche em uma categoria após o overlay.

O ledger pode conter decisões baseadas em regulamento que alterem Tipo/Foco. Preserve a classificação oficial em coluna separada e registre o documento, página, evidência, confiança e responsável pela decisão.

## Novas emissões por setor

1. Use ofertas públicas primárias de cotas de FIDC encerradas no período, deduplicadas pela regra oficial da base.
2. Some classes do mesmo FIDC conforme a chave de oferta documentada.
3. Faça o match pelo CNPJ emissor:
   - primeiro com CNPJ do fundo;
   - depois com CNPJ da classe;
   - sem match: N/D.
4. Use as mesmas categorias e o mesmo ledger efetivo do saldo.
5. Exclua FIC-FIDC dos setores e apresente seu volume na reconciliação.
6. Para 2023, se a coorte CVM estiver incompleta diante do total ANBIMA, aplique fator explícito ao mix observado e publique o fator.
7. Para fundos extintos:
   - mantenha a emissão no período;
   - procure a classificação vigente na data da emissão;
   - se ela não for recuperada, classifique como N/D;
   - não use o status atual para apagar o fluxo histórico.
8. Entregue um CSV por oferta com data, CNPJ, nome, valor observado, fator, valor apurado, categoria, tipo de match, FIC e fonte.
9. Entregue um CSV agregado por período/categoria; participações devem fechar 100% do volume ex-FIC.
10. Investigue emissores N/D materialmente relevantes antes de concluir. Documente buscas frustradas sem inferir categoria pelo nome.

## Prestadores

Em administração, gestão e custódia:

1. preserve o Top 5 verdadeiro;
2. acrescente Itaú e Kanastra como comparadores quando estiverem fora do Top 5;
3. Itaú inclui somente entidades documentadas do conglomerado para o papel analisado, como Intrag e Kinea quando aplicável;
4. Kanastra inclui Limine conforme a curadoria documentada;
5. não some papéis diferentes;
6. mostre origem e valor de cada entidade no CSV de linhagem.

## Controles obrigatórios

- CNPJ sempre com 14 dígitos em texto.
- Uma linha por competência/CNPJ no saldo.
- PL bruto, ex-FIC e cenário de exclusão reconciliados separadamente.
- Total das categorias igual ao denominador em cada período.
- Participações iguais a 100%, respeitada tolerância numérica.
- PF/PJ retirado exclusivamente de Financeiro.
- Sólido e BizCapital presentes em Financeiro e ausentes em PF/PJ.
- Emissões classificadas pela mesma lista efetiva de CNPJs.
- N/D preservado; nunca convertido em zero.
- Hash SHA-256 das entradas, CSVs, PPTXs e pacote final.
- Renderização de todos os slides e verificação de OOXML, charts, tabelas, notas e overflow.
- Download anônimo no site comparado ao hash do manifesto após o merge.

## Texto metodológico mínimo nos slides

Use asteriscos visíveis e adapte os números aos CSVs:

- * PF/PJ = PL de fundos com crédito direto PF/PJ confirmado em regulamento e Top1 mensal menor ou igual a 1% dos DC brutos; 24 CNPJs; Sólido e BizCapital mantidos em Financeiro. Exposição efetiva e total de devedores: N/D.
- * Outros: Poder Público para Precatórios/ações; Multicarteira Outros ou Multicedente/Multissacado para Multicedente/multissacado; Recuperação para Recuperação/NP, após overlay documental aprovado.
- * Emissões: ofertas CVM/SRE encerradas, match por CNPJ de fundo e depois classe, FIC fora, não localizado=N/D; 2023 escalado ao total ANBIMA.
- * Séries históricas: informe se o ledger foi aplicado por vigência ou retroaplicado como taxonomia congelada.

## Entregáveis

1. PPTX completo revisado;
2. PPTX apenas com as lâminas alteradas;
3. CSV das 26 decisões PF/PJ;
4. CSV dos 24 incluídos;
5. CSV do mapa de categorias por CNPJ;
6. CSV de emissões por oferta;
7. CSV de emissões por categoria;
8. CSV de exclusões TAPSO/Petrobras;
9. CSV de prestadores e linhagem;
10. relatório metodológico;
11. manifesto com hashes;
12. ZIP com todos os itens;
13. commit, push, merge e validação do arquivo baixado do site.
