# Revisão da indústria de FIDCs · 11/11/2026

A referência consolidada permanece setembro de 2026. A consulta à CVM de
11/11/2026 encontrou outubro com 1.148 veículos e R$ 158,48 bilhões de PL:
25,82% da quantidade e 16,00% do PL de setembro. Outubro permanece preliminar,
fora das fotografias, rankings e comparações consolidadas.

| Métrica de setembro | Valor | Perímetro |
|---|---:|---|
| Veículos reportantes | 4.447 | Tabela IV, após deduplicação e filtros de PL |
| Fundos | 4.439 | Ponte entre classes e CNPJ do fundo |
| PL bruto | R$ 990,75 bi | Soma do PL reportado |
| Componente FIC-FIDC | R$ 146,70 bi | Portão analítico de FICs, com ledger preservado |
| PL ex-FIC | R$ 844,05 bi | PL bruto menos o componente FIC-FIDC |
| Carteira DC reportada | R$ 703,52 bi | Tabela I, mesmo universo de PL |
| Contas de cotistas | 512.572 | Tabela X.1; contas podem se repetir entre classes/séries |

As entregas e retificações posteriores à publicação anterior acrescentaram
17 veículos e R$ 1,43 bilhão de PL em setembro. O processamento cobre 166 meses,
de janeiro de 2013 a outubro de 2026, e 244.200 registros mensais por CNPJ.
Os comparativos de ofertas usam janeiro a setembro contra o mesmo intervalo
do ano anterior. CVM e BCB alcançam setembro; o ranking ANBIMA também avançou
de agosto para setembro. As 40 fontes em arquivo foram congeladas e verificadas
por SHA-256.

Foi corrigido o gerador dos agregados históricos: Tabelas I e II e as demais
tabelas de estoque/contas agora usam os CNPJs com PL aceito na Tabela IV.
Anteriormente, os totais mensais podiam incluir carteira e inadimplência de
registros ausentes desse universo, inclusive registros cujo PL foi excluído
como pico isolado. Os valores brutos permanecem nos arquivos CVM; as exclusões
ficam contadas na auditoria. Movimentos X.4 sem Tabela IV continuam preservados
como `Sem Tab IV` na base granular.

A conferência independente reconciliou os 15 agregados monetários/de contas
com o painel granular, em todos os meses disponíveis, e as 11 categorias
principais da Tabela II. A chave competência/CNPJ não apresenta duplicidades.
As quantidades de veículos reconciliam após separar os registros exclusivos
de fluxo. As métricas analíticas de inadimplência usam carteira positiva,
flags de presença e cap por veículo conforme o manifesto; o saldo bruto inclui
um registro de carteira negativa, preservado na base.

O status consolidado está sujeito a entregas tardias. Há 61 CNPJs reportantes
de agosto ausentes na Tabela IV de setembro, com R$ 13,69 bilhões de PL em
agosto. O conjunto inclui registros cancelados, em liquidação e com situações
cadastrais distintas. O PL de setembro desses registros permanece indisponível;
ausência de informe não foi convertida em zero nem interpretada como liquidação.

O ranking ANBIMA e seu anexo de setembro apresentam divergências, mantidas na
base e identificadas no manifesto e nos downloads:

- Distribuição de FIDCs, Itaú BBA: o ranking excede o anexo em R$ 1 milhão.
- Distribuição de securitização, Votorantim: o anexo excede o ranking em
  R$ 617,471 milhões. Na própria aba `Distribuição` do ranking, o subtotal em
  `C124` é inferior ao recorte FIDC em `C171`. Os valores publicados não foram
  ajustados para forçar a reconciliação.
- Originação de empresas ligadas: os volumes reconciliam; a maior diferença
  de participação entre publicações é 1,0191 ponto percentual.

O arquivo de participações reconstruídas identifica o anexo como fonte. O
ranking oficial permanece em arquivo separado. Essas divergências pertencem
ao ranking de coordenadores; os gráficos de volume do deck usam as séries
CVM e o boletim ANBIMA com os respectivos perímetros.

A classificação oficial Tipo/Foco ANBIMA utilizada continua sendo a fotografia
de 29/12/2025. Decisões documentais e reclassificações analíticas preservam
suas próprias datas e evidências. O download atual dessa base passou por um
formulário cadastral; uma fotografia oficial mais recente não foi incorporada.
Ratings e evidências documentais mantêm suas datas de revisão e lacunas N/D.

A validação final passou em 920 testes, com um teste opcional ignorado. As oito
subabas abriram no teste completo da aplicação e os cinco downloads principais
reproduziram os bytes do manifesto. O PPTX foi aberto no PowerPoint e seus 15
slides foram renderizados e revisados, com 33 gráficos nativos e duas tabelas
editáveis. A planilha abriu no Excel, e as verificações de fórmulas, caches,
zeros e estrutura OOXML passaram. O pacote validado é
`202609_e1c4ffe713e48e48`; seus hashes completos estão no
[manifesto de exportação](../data/industry_study/generated_revision/industry_export_bundle.json).

Evidências da revisão: [reconciliação e hashes das fontes](../reports/industry_review_20261111/data_audit.json),
[CNPJs de agosto ausentes em setembro](../reports/industry_review_20261111/reportantes_agosto_ausentes_setembro.csv)
e [diferenças mensais contra a publicação anterior](../reports/industry_review_20261111/diferencas_mensais_vs_publicacao_anterior.csv).
As [ofertas acrescentadas no mesmo corte de setembro](../reports/industry_review_20261111/ofertas_acrescentadas_mesmo_corte_setembro.csv)
e a [reconciliação dos arquivos de ofertas](../reports/industry_review_20261111/offer_source_reconciliation.json)
separam entregas posteriores de mudanças na janela de comparação.

Fontes principais: [Informe Mensal CVM](https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal),
[ranking ANBIMA de setembro](https://data-strapi.prd.anbima.com.br/uploads/Ranking_de_Renda_Fixa_e_Hibridos_Setembro_2026_8_34fb719a7f.xlsx)
e [anexo ANBIMA de setembro](https://data-strapi.prd.anbima.com.br/uploads/Anexo_ao_Ranking_Encerramento_de_Renda_Fixa_e_Hibridos_Setembro_2026_8_e035007fec.xlsx).
