# Conclusões documentais — Top 20 por Tipo ANBIMA

## Escopo

A revisão cobre 320 posições: os 20 maiores FIDCs de cada Tipo ANBIMA exibido em dezembro de 2023, dezembro de 2024, dezembro de 2025 e junho de 2026. As posições reconciliam 143 CNPJs legais únicos. Uma conclusão documental por CNPJ é reutilizada nas competências em que o mesmo veículo reaparece.

## Separação das camadas

- `industry_top20_taxonomy_document_review.csv`: extração automática inicial, com documento, páginas e candidatos textuais.
- `industry_top20_taxonomy_document_conclusions.csv`: conclusão documental proposta por CNPJ.
- `taxonomy_review_actions.csv`: decisão manual do usuário, identificada por competência e CNPJ.
- Base CVM/ANBIMA: campos declarados preservados, sem sobrescrita pela conclusão ou pela decisão manual.

A conclusão preenche a sugestão exibida no formulário. Ela produz efeito analítico somente depois de uma ação `aprovado` registrada pelo botão **Aprovar e aplicar**.

## Critério de conclusão

Cada regulamento disponível é lido página a página. A seleção da evidência prioriza:

1. definição dos Direitos Creditórios;
2. política de investimento;
3. critérios de elegibilidade e condições de cessão;
4. descrição do lastro e dos documentos comprobatórios;
5. identificação explícita de cedente ou originador.

Termos presentes apenas em fatores de risco, cobrança de ativos vencidos ou listas genéricas de instrumentos não determinam a classificação. Mandatos que enumeram quatro ou mais famílias de ativos permanecem na categoria oficial multicarteira, salvo evidência mais específica. Adquirência exige vínculo do direito creditório com transação e arranjo de pagamento, agenda de recebíveis, credenciadora ou subcredenciadora. NPL exige aquisição de carteira vencida ou inadimplida. Poder Público exige precatório, receita ou dívida pública, ou ação judicial contra ente público.

## Estados da conclusão

- `manter_classificacao_oficial`: o regulamento sustenta a classificação preservada ou não apresenta evidência específica em sentido diferente.
- `propor_reclassificacao_documental`: a definição ou política de investimento sustenta outra combinação de Tipo e Foco.
- `propor_correcao_perimetro_documental`: o cadastro local identifica um FIF fora do universo esperado; a exclusão requer confirmação cadastral manual.
- `manter_provisoriamente_por_limitacao_documental`: não há regulamento legível; a fotografia oficial é mantida com confiança baixa e limitação explícita.

Os três estados permanecem pendentes de aprovação manual. O nível de confiança reflete a especificidade da cláusula e a presença de famílias concorrentes, sem substituir a validação da composição efetiva da carteira.

## Rastreabilidade

Cada linha concluída registra CNPJ, nome, documento, data, URL FundosNet, caminho local quando disponível, página/cláusula, trecho decisivo, cedente/originador explicitamente localizado, Tipo/Foco propostos, Tabela II analítica, taxonomia funcional, confiança, método de leitura e limitação.

O manifesto registra contagem, competências, cobertura de documentos, distribuição de status e confiança, além dos hashes SHA-256 da extração documental e da base de ranking usada.

## Validação requerida

- 320 posições e 143 CNPJs únicos reconciliados;
- 143 conclusões, sem Tipo ou Foco proposto vazio;
- 113 classificações oficiais mantidas, 25 reclassificações documentais propostas, 3 correções de perímetro propostas e 2 conclusões provisórias;
- 136 regulamentos legíveis; BR Eletro concluído por revisão visual de fonte primária digitalizada e F ACB complementado por decisão oficial da CVM;
- Expert III e PAN Auto mantidos provisoriamente, com a insuficiência documental explícita;
- nenhuma conclusão com status `ambigua`;
- ledger manual sem mutação durante a geração;
- campos oficiais sem mutação;
- precedência da curadoria documental já existente sobre a conclusão assistida;
- execução dos testes de classificação, fila histórica, payload e publicação do bundle;
- inspeção visual das páginas decisivas para amostras de adquirência, bancos emissores, consignado, veículos, agro, energia, NPL, Poder Público e FIC-FIDC.

## Limitações

A conclusão descreve o mandato permitido pelo regulamento. A materialidade efetiva de cada família depende da carteira observada na competência. PDF sem camada de texto, regulamento ausente, Anexo Descritivo não localizado e cedente/originador não nomeado permanecem registrados como limitações; esses fatos não são inferidos pelo nome do fundo.
