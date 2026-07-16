# Relatório da revisão do Glossário de FIDCs

## Síntese executiva

Foi congelada a competência **202605**, indicada por `competencia_snapshot`, evitando o uso automático de `202606`, ainda preliminar/incompleto. A amostra contém exatamente **100 CNPJs de fundo únicos**, selecionados por PL com cobertura mínima de todos os 18 estratos ocupados. “Marcas e patentes” não tinha população elegível.

O PL da amostra é **R$ 399.488.372.325,77**, ou **41,6735%** dos R$ 958.614.843.834,84 de PL positivo reconciliado. Seis FIC-FIDCs somam R$ 13.940.997.626,48. Excluídos esses veículos em ambos os lados, a amostra representa **R$ 385.547.374.699,29**, ou **44,7192%** da indústria ex-FIC de R$ 862.151.993.954,82.

A revisão resultou em 18 páginas, 48 conceitos e 27 métricas. O conteúdo continua concept-first: os 100 fundos são corpus de evidência, não um catálogo. Nenhuma conclusão constitui rating, recomendação ou avaliação corrente de fundo.

## Seleção e cobertura por estrato

O campo técnico `subtipo_cvm_ime` implementa o algoritmo solicitado, mas os nomes editoriais são segmento oficial da Tabela II, abertura financeira da Tabela II e Sem segmentação IME. A cobertura bruta por estrato é:

| Estrato analítico | Indústria | Selecionados | Cobertura de PL |
|---|---:|---:|---:|
| Agronegócio | 59 | 2 | 16,26% |
| Ações judiciais | 205 | 2 | 8,31% |
| Cartão de crédito | 42 | 9 | 83,75% |
| Comercial | 513 | 18 | 48,95% |
| Factoring | 1 | 1 | 100,00% |
| Financeiro — consignado | 52 | 4 | 53,89% |
| Financeiro — crédito corporativo | 162 | 5 | 25,99% |
| Financeiro — crédito pessoal | 81 | 2 | 31,05% |
| Financeiro — imobiliário empresarial | 1 | 1 | 100,00% |
| Financeiro — imobiliário residencial | 1 | 1 | 100,00% |
| Financeiro — middle market | 4 | 2 | 97,94% |
| Financeiro — outros | 1.301 | 21 | 28,93% |
| Financeiro — veículos | 3 | 2 | 99,09% |
| Imobiliário | 32 | 2 | 34,02% |
| Industrial | 190 | 2 | 75,95% |
| Sem segmentação IME | 900 | 12 | 19,94% |
| Serviços | 304 | 9 | 50,93% |
| Setor público | 181 | 5 | 34,18% |

Em Sem segmentação IME, a cobertura ex-FIC é 28,48%. O estrato não é um subtipo oficial: ele indica total zero na Tabela II. Quatro fundos têm participação dominante inferior a 60% e foram marcados como híbridos/multissegmento.

Os 100 registros se dividem em 18 seleções `cobertura_1`, 15 `cobertura_2` e 67 `top_pl`. O ranking foi feito no nível de fundo após somar classes; todas as somas de classes componentes foram reconciliadas.

## Cobertura documental

O ledger documental tem 981 linhas canônicas, 748 IDs primários únicos e 233 pedidos prioritários sem documento. Foram extraídos página a página 731 documentos, correspondentes a 721 hashes únicos e 21.028 páginas deduplicadas.

| Estado ou tipo | Quantidade |
|---|---:|
| Fundos com algum documento primário lido | 100 |
| Regulamentos vigentes lidos | 95 |
| Regulamentos vigentes ausentes | 3 |
| Regulamentos vigentes inacessíveis | 2 |
| Documentos com OCR necessário | 15 |
| Relatórios de rating lidos | 52 |
| Demonstrações financeiras lidas | 91 |
| Relatórios mensais/trimestrais lidos | 98 |
| Prospectos/lâminas lidos | 3 |

Os regulamentos vigentes ausentes são Solis Capital Core FIC-FIDC, Expert III FIDC e PAN Auto FIDC. Os downloads inacessíveis são Fratto FIDC (Fundos.NET 1235423) e Monee FIC-FIDC (Fundos.NET 1051896). A cobertura de PL da amostra por regulamento vigente lido é 95,6155%. Todos os cinco fundos têm status explícito e outro documento primário lido.

O inventário anterior não era confiável: 1.501 PDFs declarados locais estavam ausentes, assim como 9.645 caminhos de outro inventário e 1.445 arquivos-fonte da base de conhecimento regulatória. Os 571 caches TXT existentes tinham `documento_id` igual ao CNPJ. Esses derivados serviram apenas de pista.

Quinze documentos permanecem em OCR necessário e dois ficaram inacessíveis. Nenhum deles sustenta afirmação categórica do glossário. A leitura substantiva de cláusulas usou 15 regulamentos, agrupados em 12 famílias independentes de template, cobrindo 48,44% do PL amostral.

## Resultado da matriz de evidências

A matriz contém 57 evidências atômicas e 62 candidatos a verbete. Para práticas contratuais, o denominador com documentação substantiva suficiente é 15, e não 100. As frequências abaixo excluem FIC-FIDCs e distinguem fundos de famílias independentes:

| Prática observada | Fundos | Equal-weight | Ponderada por PL | Famílias independentes |
|---|---:|---:|---:|---:|
| Critérios de elegibilidade explícitos | 15/15 | 100,00% | 100,00% | 12 |
| Linguagem explícita de concentração | 14/15 | 93,33% | 68,56% | 11 |
| Ordem de aplicação/alocação de recursos | 15/15 | 100,00% | 100,00% | 12 |
| Estrutura subordinada efetiva | 6/15 | 40,00% | 40,81% | 6 |
| Reserva nominada | 10/15 | 66,67% | 54,03% | 9 |
| Revolvência/reinvestimento autorizado | 11/15 | 73,33% | 56,95% | 9 |
| Ramp-up contratualmente definido | 1/15 | 6,67% | 5,16% | 1 |
| Evento de avaliação separado | 14/15 | 93,33% | 97,02% | 11 |
| Evento de liquidação | 15/15 | 100,00% | 100,00% | 12 |
| Sem regresso/coobrigação em linguagem estrita | 5/15 | 33,33% | 34,42% | 5 |
| Dever positivo de verificação de lastro | 12/15 | 80,00% | 61,18% | 10 |
| Dispensa/não incidência de verificação | 3/15 | 20,00% | 38,82% | 2 |

Ramp-up permaneceu rotulado como idiossincrático. A expressão literal “excesso de spread” apareceu em 0/15 regulamentos: o glossário preserva o conceito apenas como inferência analítica de spread residual, não como prática contratual demonstrada.

## Principais ampliações

1. **Regime e arquitetura:** fundo, classe, patrimônio segregado, subclasse, série, cota e tranche legada foram distinguidos segundo a RCVM 175.
2. **Tabela II:** os 11 segmentos, as oito aberturas financeiras, o vetor completo, a dominância, a flag híbrida e Sem segmentação IME receberam página canônica.
3. **Participantes e lastro:** responsabilidades de administrador, gestor, custodiante e terceiros passaram a refletir a norma e as cláusulas; amostragem, contratação e supervisão foram separadas.
4. **Transferência e instrumentos:** cessão, endosso, regresso, coobrigação, existência, formalização, elegibilidade, concentração, CCB, duplicata, CPR e garantias foram ampliados.
5. **Capital e liquidez:** waterfall, apropriação de resultado, absorção de perda, reservas, sobrecolateralização, revolvência, ramp-up, amortização, pré-pagamento, WAL e descasamento agora têm definições distintas.
6. **Desempenho:** aging usa as dez faixas disponíveis; provisão, perda esperada, perda realizada, baixa e recuperação foram separados; Over, FPD, roll rate, cura e safra receberam fórmula e denominador. FPD foi rotulado como convenção operacional porque não houve definição literal nos 95 regulamentos e 52 ratings varridos.
7. **Eventos e oferta:** evento, cura, waiver, quórum, liquidação, emissão, benchmark e remuneração-alvo foram reestruturados.
8. **Famílias de recebíveis:** consignado, cartão, veículos, crédito corporativo/pessoal, imobiliário, NPL, risco sacado, ações judiciais, precatórios, agronegócio, serviços e recebíveis industriais passaram a registrar variações de risco e fonte necessária.

## Inconsistências corrigidas

- dez fundos narrativos versus oito no JSON: agora são dez em ambos;
- IDs parcialmente divergentes entre `sources.json` e `document_index.json`: resolvidos e validados como únicos;
- 13 caminhos `estudo/*.pdf` inexistentes: removidos e substituídos por documentos primários revalidados;
- provisão e perda esperada agregadas: separadas em conceitos e métricas próprios;
- conceitos citados sem verbete: convertidos em registros estruturados ou referência cruzada;
- mini-glossário divergente: passou a ser gerado da base canônica;
- aging incompleto: ampliado às dez faixas do Informe Mensal;
- custódia, rating, subordinação, Cielo, consignado e lastro: reescritos após conferência normativa e contratual;
- busca limitada a títulos: ampliada ao Markdown, aliases, grafias sem acento e termos legados;
- classificação interna `setor_n1/setor_n2`: explicitamente separada da classificação oficial da Tabela II.

## Divergências e limitações remanescentes

- Regulamentos de uma mesma família podem divergir em thresholds, reservas, concentração e eventos; o relatório conta templates, mas cada aplicação exige a versão do fundo.
- PagSeguro apresenta condições que exigem leitura conjunta de política, critérios e lastro; Aetos contém redação material que não deve ser normalizada sem o original. Esses casos ficaram vinculados a página e hash.
- O corpus de 100 tem documento explícito para todos, mas cinco não têm regulamento vigente lido e 15 documentos aguardam OCR.
- Segmentos de população pequena têm cobertura alta por construção; Ações judiciais, Agronegócio e alguns estratos financeiros têm cobertura de PL mais baixa e evidência contratual menos densa.
- Sem segmentação IME é uma limitação de reporte, não ausência econômica de carteira.
- FIC-FIDC pode gerar dupla contagem econômica; por isso as coberturas bruta e ex-FIC são apresentadas separadamente.
- A revisão normativa tem data de verificação de 16/07/2026 e deve ser atualizada quando a CVM consolidar nova alteração.

## Estado concreto da entrega

Os dez artefatos de auditoria estão no diretório deste relatório. O ledger tem 100 fundos únicos, todos os estratos ocupados estão representados, o PL está reconciliado, os 100 fundos têm estado documental explícito, novas definições materiais têm fonte, os índices não contêm referências quebradas e o mini-glossário deriva do book. Os hashes dos seis CSVs e três relatórios Markdown, além das limitações, estão registrados em `manifest.json`.
