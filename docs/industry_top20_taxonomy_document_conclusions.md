# Conclusões documentais — Top 20 por Tipo ANBIMA

## Escopo

A revisão cobre 320 posições: os 20 maiores FIDCs de cada Tipo ANBIMA exibido em dezembro de 2023, dezembro de 2024, dezembro de 2025 e junho de 2026. As posições reconciliam 143 CNPJs legais únicos. Uma conclusão documental por CNPJ é reutilizada nas competências em que o mesmo veículo reaparece.

## Separação das camadas

- `industry_top20_taxonomy_document_review.csv`: extração automática inicial, com documento, páginas e candidatos textuais.
- `industry_top20_taxonomy_document_conclusions.csv`: conclusão documental proposta por CNPJ.
- `taxonomy_user_comment_overrides.csv`: decisão manual explícita do usuário por CNPJ, com o comentário preservado como evidência e precedência sobre a proposta documental.
- `taxonomy_review_actions.csv`: decisão consolidada, identificada pelo CNPJ legal.
- Base CVM/ANBIMA: campos declarados preservados, sem sobrescrita pela conclusão ou pela decisão manual.

A decisão `aprovado` produz efeito analítico em todas as ocorrências passadas e futuras do CNPJ. Competência, documento e data permanecem como proveniência e não restringem a vigência.

## Critério de conclusão

Cada regulamento disponível é lido página a página. A seleção da evidência prioriza:

1. definição dos Direitos Creditórios;
2. política de investimento;
3. critérios de elegibilidade e condições de cessão;
4. descrição do lastro e dos documentos comprobatórios;
5. identificação explícita de cedente ou originador.

Termos presentes apenas em fatores de risco, cobrança de ativos vencidos ou listas genéricas de instrumentos não determinam a classificação. Mandatos que enumeram quatro ou mais famílias de ativos permanecem na categoria oficial multicarteira, salvo evidência mais específica. Adquirência exige vínculo do direito creditório com transação e arranjo de pagamento, agenda de recebíveis, credenciadora ou subcredenciadora. NPL exige aquisição de carteira vencida ou inadimplida. Poder Público exige precatório, receita ou dívida pública, ou ação judicial contra ente público.

Para estruturas de pagamentos, a conclusão verifica no regulamento e nas demonstrações financeiras: cedente, devedor ou suporte econômico do risco e família do lastro. A classificação segue o risco predominante entre adquirente/credenciadora, banco emissor, crédito PF, arranjo fechado e carteira mista. Ausência de demonstrações ou de abertura por família mantém o CNPJ na fila quando impede medir a predominância.

Uma decisão manual explícita pode fechar a classificação analítica quando o usuário identifica o lastro, o cedente/originador ou a estratégia econômica. O comentário, a justificativa e a limitação documental ficam registrados separadamente. A maximização de tipos diferentes de `Outros` respeita o encaixe econômico: carteiras de precatórios, direitos judiciais, NPL e special situations permanecem em `Outros` quando os demais tipos ANBIMA não comportam o risco descrito.

## Fila operacional

- Uma linha por CNPJ, ordenada pelo maior PL observado nas quatro competências.
- CNPJs com decisão aprovada deixam a fila.
- **Aprovar e próximo** consolida a decisão e avança; **Salvar e permanecer** preserva o trabalho sem aplicar; **Pular** avança sem gravação.
- A interface mostra nome, CNPJ, maior PL, evidência, cedente/originador e os seis campos de classificação. Auditoria, histórico, competências e informações administrativas permanecem no banco.

## Estados da conclusão

- `manter_classificacao_oficial`: o regulamento sustenta a classificação preservada ou não apresenta evidência específica em sentido diferente.
- `propor_reclassificacao_documental`: a definição ou política de investimento sustenta outra combinação de Tipo e Foco.
- `propor_correcao_perimetro_documental`: o cadastro local identifica um FIF fora do universo esperado; a exclusão requer confirmação cadastral manual.
- `manter_provisoriamente_por_limitacao_documental`: não há regulamento legível; a fotografia oficial é mantida com confiança baixa e limitação explícita.
- `requer_validacao_manual`: falta documento obrigatório ou a carteira é mista sem predominância mensurável.

O nível de confiança reflete a especificidade da cláusula e a presença de famílias concorrentes. Ele permanece no banco e não é exibido na fila principal.

## Rastreabilidade

Cada linha concluída registra CNPJ, nome, documento, data, URL FundosNet, caminho local quando disponível, página/cláusula, trecho decisivo, cedente/originador explicitamente localizado, Tipo/Foco propostos, Tabela II analítica, taxonomia funcional, confiança, método de leitura e limitação.

O manifesto registra contagem, competências, cobertura de documentos, distribuição de status e confiança, além dos hashes SHA-256 da extração documental e da base de ranking usada.

## Validação requerida

- 320 posições e 143 CNPJs únicos reconciliados;
- 143 conclusões, sem Tipo ou Foco proposto vazio;
- 111 classificações oficiais mantidas, 25 reclassificações documentais aprovadas, 2 validações manuais, 3 correções de perímetro propostas e 2 conclusões provisórias;
- 136 regulamentos legíveis; BR Eletro concluído por revisão visual de fonte primária digitalizada e F ACB complementado por decisão oficial da CVM;
- Expert III e PAN Auto têm conclusão documental provisória; a decisão manual do usuário fecha Expert III como Financeiro / Multicarteira Financeiro;
- nenhuma conclusão com status `ambigua`;
- 15 decisões manuais da imagem `IMG_8592.jpg`, das quais 11 resultam em tipos diferentes de `Outros` e 4 preservam `Outros` com foco econômico refinado;
- ledger com 137 CNPJs aprovados e trilha de auditoria reproduzível;
- fila operacional reduzida a Cielo Emissores II, HOTFUND e PAN Auto;
- campos oficiais sem mutação;
- precedência da curadoria documental já existente sobre a conclusão assistida;
- 868 testes e 2 subtestes aprovados, cobrindo classificação, fila histórica, payload e publicação do bundle;
- inspeção visual das páginas decisivas para amostras de adquirência, bancos emissores, consignado, veículos, agro, energia, NPL, Poder Público e FIC-FIDC.

## Efeito das decisões manuais sobre Outros

| Competência | Outros após as decisões | Redução adicional desta rodada | Redução total ante o oficial |
|---|---:|---:|---:|
| dez/23 | R$ 158,089 bi | R$ 7,882 bi | R$ 13,784 bi |
| dez/24 | R$ 235,721 bi | R$ 16,896 bi | R$ 25,840 bi |
| dez/25 | R$ 329,511 bi | R$ 25,747 bi | R$ 41,709 bi |
| jun/26 | R$ 299,695 bi | R$ 30,948 bi | R$ 56,010 bi |

## Limitações

A conclusão descreve o mandato permitido pelo regulamento. A materialidade efetiva de cada família depende da carteira observada na competência. PDF sem camada de texto, regulamento ausente, Anexo Descritivo não localizado e cedente/originador não nomeado permanecem registrados como limitações; esses fatos não são inferidos pelo nome do fundo.
