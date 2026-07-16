# Registro de alterações do Glossário

Data de corte: **16/07/2026**

Competência do corpus: **202605**

## Resultado estrutural

O book passou de 14 para 18 páginas indexadas, com 49 conceitos, 28 métricas, 10 fundos de referência, 36 fontes e 21 documentos primários pontualmente indexados. Três páginas temáticas foram criadas:

- `regulacao/informe-mensal-tabela-ii.md`;
- `estruturas/reforcos-revolvencia-e-liquidez.md`;
- `recebiveis/instrumentos-garantias-e-concentracao.md`.

`fontes/referencias.md` passou a integrar o índice. As páginas antigas foram reescritas sem criar perfis dos 100 fundos.

## Criados ou substancialmente ampliados

- arquitetura RCVM 175: fundo, classe, patrimônio segregado, subclasse, série, cota e tranche como termo de mercado;
- 11 segmentos oficiais da Tabela II, oito aberturas financeiras e Sem segmentação IME;
- taxonomia funcional documental e sua separação da classificação oficial;
- registradora, escriturador, distribuidor, consultoria especializada, agente de cobrança e prestadores contratados;
- cessão, endosso, regresso, coobrigação, existência, formalização, lastro e vícios do crédito;
- CCB, duplicata, CPR, recebíveis de cartão, consignado, crédito pessoal, crédito corporativo, veículos, imobiliário, precatório, ação judicial, NPL, risco sacado, energia, mensalidades e crédito estudantil;
- critérios de elegibilidade, condições de cessão, concentração e diluição;
- waterfall de caixa, apropriação de resultado e absorção de perdas como planos distintos;
- reservas de liquidez, despesas e recomposição; garantia; sobrecolateralização; excesso de spread apenas analítico;
- revolvência, reinvestimento, ramp-up, amortização, pré-pagamento, duration/WAL e descasamento;
- eventos de avaliação, eventos de liquidação, cura, waiver, consentimento, quórum e governança;
- oferta, emissão, benchmark, remuneração-alvo e ausência de garantia de retorno;
- aging nas dez faixas disponíveis, Over, FPD, roll rate, cura, safra, provisão, perda esperada, perda realizada, baixa e recuperação.

## Corrigidos

- **Fundo/classe/subclasse:** o patrimônio segregado foi atribuído à classe; subclasse e série deixaram de ser tratadas como fundos ou patrimônios autônomos.
- **Custodiante e lastro:** retirou-se a afirmação de que o custodiante é verificador universal. A responsabilidade do gestor, a contratação sob supervisão, a amostragem e as hipóteses de custódia/verificação foram separadas conforme os arts. 36 a 39 do Anexo Normativo II.
- **Rating:** passou de requisito implícito a documento/serviço condicionado à estrutura, à oferta e ao regulamento; objeto e escopo devem ser declarados.
- **Subordinação:** proxy do Informe Mensal e índice contratual por classe/subclasse foram separados. Waterfall não passou a provar existência de subordinação.
- **Consignado:** INSS ou ente conveniado foi descrito como fonte pagadora/operador do desconto, não automaticamente como devedor do crédito.
- **Veículos:** bem financiado deixou de ser chamado de garantia implícita; alienação fiduciária ou outra garantia exige instrumento.
- **Cielo e meios de pagamento:** a linguagem de não regresso por solvência foi separada da responsabilidade por existência, formalização e condições de elegibilidade.
- **Provisão e perda esperada:** o registro combinado foi dividido; provisão/impairment, perda esperada, perda realizada, write-off e recuperação agora têm verbetes e métricas distintos.
- **Aging:** foram preservadas as dez faixas do reporte, sem fundir 121–150 com 151–180 nem truncar acima de 360 dias.
- **FPD:** deixou de citar um regulamento sem definição correspondente e foi rotulado como convenção operacional do Glossário, com coorte, janela e critério de default obrigatórios.
- **Oferta:** rito, emissão, instrumento, público e remuneração deixaram de ser generalizados a partir de um único caso.
- **Evento:** ocorrência, período de cura, deliberação, waiver e liquidação foram separados em estados auditáveis.

## Segunda rodada editorial e funcional

- **Navegação publicada:** links relativos entre arquivos Markdown passaram a ser convertidos em rotas internas por `page_id`, preservando os arquivos-fonte navegáveis no GitHub.
- **Hierarquia:** fundo, classe, subclasse, série e cota passaram a ser exibidos como abertura encadeada, com a subordinação posicionada no início da análise.
- **Mapa normativo:** RCVM 175, RCVM 160 e RCVM 30 foram reescritas pela pergunta prática respondida e pelo fluxo de uma oferta pública.
- **Famílias de recebíveis:** cada família recebeu riscos, indicadores prioritários, fórmula analítica, fonte necessária e motivo da priorização.
- **Siglas:** WAL, FPD, LTV, PD, LGD, EAD, CCB, CPR, SCD, SEP, NPL e termos estrangeiros materiais passaram a ser expandidos na primeira ocorrência.
- **DCV:** foi removido como alias de diluição. A varredura de 95 regulamentos vigentes e 52 ratings, equivalentes a 141 hashes únicos, não localizou DCV, FPD, roll rate ou fórmula recorrente de diluição, cura e recuperação.
- **Atribuições documentais:** cobertura passou a citar Multiplike 1223029, p. 55, e Seller 909547, p. 46; diluição e excesso de spread passaram a ser rotulados como convenções analíticas onde não houve definição literal recorrente.
- **Pré-pagamento e refinanciamento:** o alias ambíguo “CPR de pré-pagamento” foi removido para não confundir com Cédula de Produto Rural; VTK 1002580, p. 114 e p. 118, foi mantido apenas como exemplo contratual específico.
- **LTV:** foi criado verbete estruturado com RED Performance 1127150, p. 67, e RED Real 1090771, p. 51, contados como uma única família de template.
- **Transparência documental:** `lido` deixou de ser apresentado ao leitor como leitura jurídica integral; o conteúdo agora distingue processado, leitura substantiva e conferência visual.

## Fundidos e centralizados

- definições repetidas de direito creditório, elegibilidade, lastro, subordinação, aging e evento foram centralizadas em conceitos canônicos;
- o mini-glossário do monitoramento passou a ser gerado de `concepts.json` e `metrics.json`;
- busca do book passou a usar corpo Markdown, títulos, aliases, grafias sem acento e terminologia legada;
- fontes documentais e IDs de documento passaram a compartilhar o mesmo `source_id` quando representam o mesmo PDF.

## Depreciados ou substituídos

- conceito agregado “classes de cotas” foi substituído por classe, subclasse, série, cota e tranche legada;
- registro único “provisão e perda esperada” foi substituído por conceitos contábeis separados;
- “reserva de liquidez” genérica foi desdobrada por finalidade, alvo, saque e recomposição;
- catálogo narrativo de fundos foi reduzido a dez casos metodológicos reconciliados com JSON;
- caminhos `estudo/*.pdf` e IDs sem arquivo foram removidos dos índices;
- definições completas duplicadas foram substituídas por referências cruzadas.

## Descartados como regra de mercado

- rating obrigatório ou quase universal;
- custódia e verificação de lastro sempre concentradas no custodiante;
- cessão sempre sem regresso/coobrigação;
- existência de subordinação inferida apenas pela waterfall;
- “excesso de spread” como expressão contratual recorrente: houve zero ocorrência literal nos 15 regulamentos substantivos;
- threshold numérico de um fundo convertido em definição universal;
- ausência de cláusula ou campo convertida em zero;
- garantia de veículo presumida sem instrumento;
- avaliação de cobertura de provisão acima/abaixo de 100% como conclusão automática de conservadorismo ou insuficiência.

## Reconciliações de dados e índices

- os dez fundos narrativos agora correspondem exatamente aos dez registros de `reference_funds.json`, todos com CNPJ e documento primário;
- os 13 caminhos documentais inexistentes foram substituídos por 16 PDFs primários locais revalidados por SHA-256; cinco documentos adicionais foram indexados por URL oficial e hash, sem dependência local versionada;
- 36 IDs de fonte são únicos e todas as referências de páginas, conceitos, métricas e documentos resolvem;
- provisão e perda esperada deixaram de compartilhar um único registro estruturado;
- aliases novos e essenciais são pesquisáveis;
- o book carrega todas as 18 páginas;
- o mini-glossário e o book compartilham a fonte canônica.

## Artefatos de suporte

As decisões atômicas estão em `evidence_long.csv`; os candidatos e frequências, em `term_candidates.csv`; a matriz antes/depois, em `glossary_gap_matrix.csv`; e a seleção/documentação, nos demais CSVs deste diretório. `manifest.json` registra contagens, limitações e hashes.
