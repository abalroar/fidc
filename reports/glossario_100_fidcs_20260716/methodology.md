# Metodologia — revisão do Glossário a partir de 100 FIDCs

Data da revisão: **16/07/2026**

Competência congelada: **maio de 2026 (`202605`)**

## 1. Escopo e princípio de evidência

O estudo usa exatamente 100 `cnpj_fundo` como corpus de evidência para revisar um glossário orientado a conceitos. Ele não produz perfis, rating, recomendação de investimento ou avaliação corrente dos fundos. A revisão é exaustiva em relação ao corpus e às normas verificadas, não universalmente completa.

As afirmações foram separadas em cinco espécies:

1. **normativa**, sustentada por fonte oficial vigente ou, quando necessário, por norma legada identificada;
2. **prática contratual recorrente**, sustentada por ao menos dois fundos independentes e com denominador documental explícito;
3. **específica de família ou fundo**, rotulada como variação ou exemplo;
4. **convenção analítica**, com fórmula, unidade e limitação declaradas;
5. **inferência**, identificada como tal e não apresentada como cláusula.

Cache de texto, inventário legado ou JSON heurístico foi usado apenas para localizar candidatos. Afirmação contratual categórica exige PDF primário, versão e página. Ausência na extração não foi convertida em inexistência nem em zero.

## 2. Congelamento e reconciliação do universo

A competência veio de `competencia_snapshot` em `data/industry_study/metadata.json`. O mês `202606` não foi promovido automaticamente porque era preliminar/incompleto; a foto congelada permaneceu em `202605`.

A base principal foi `data/industry_study/vehicle_monthly.csv.gz`, reconciliada com o Informe Mensal e com a Tabela II da competência. `universe_latest.csv` foi tratado somente como fotografia auxiliar. O processo:

1. normalizou CNPJ para 14 dígitos, preservando zero à esquerda;
2. excluiu PL nulo, zero ou negativo;
3. agrupou no nível `cnpj_fundo` e somou o PL das classes reportantes;
4. preservou os CNPJs das classes componentes no ledger;
5. não contou séries ou subclasses da Tabela X.2 como fundos;
6. comparou o PL agregado das classes com o PL de cada fundo.

O snapshot contém 4.224 veículos: 4.037 registros com PL positivo, 150 com PL zero e 37 com PL negativo. O PL de todos os registros é R$ 958.535.660.089,73; os 37 negativos somam R$ -79.183.745,11. Após a exclusão, o universo elegível tem 4.032 fundos e R$ 958.614.843.834,84. O resíduo entre a soma dos veículos positivos e a soma dos fundos agregados é zero.

## 3. Segmentação e seleção dos 100

Para cada fundo, foi preservado o vetor dos 11 segmentos oficiais da Tabela II. A classificação operacional seguiu estas regras:

- maior valor entre os 11 blocos oficiais;
- se Financeiro vencer, maior abertura financeira entre F1 e F8;
- total da Tabela II igual a zero: **Sem segmentação IME**, estrato de qualidade de dados;
- participação dominante inferior a 60%: flag analítica **híbrido/multissegmento**.

O nome técnico `subtipo_cvm_ime` foi mantido no CSV solicitado para compatibilidade do artefato, mas não é tratado no conteúdo editorial como “subtipo CVM”. O book usa “segmento oficial da Tabela II do Informe Mensal”, “abertura financeira da Tabela II”, “taxonomia funcional documental” e “Sem segmentação IME”.

A seleção aplicou, nesta ordem:

1. dois maiores fundos de cada estrato ocupado, ou o único fundo quando havia apenas um;
2. até dois casos de Sem segmentação IME como cobertura mínima inicial;
3. preenchimento pelos maiores PLs globais ainda não selecionados;
4. desempate por PL decrescente e CNPJ crescente.

O resultado tem 100 fundos únicos: 18 por `cobertura_1`, 15 por `cobertura_2` e 67 por `top_pl`. Todos os 18 estratos ocupados estão representados; “Marcas e patentes” não tinha população elegível. Quatro fundos foram marcados como híbridos. Seis FIC-FIDCs permaneceram por materialidade, foram identificados em bloco próprio e excluídos da prevalência das práticas do crédito subjacente.

## 4. Cobertura de patrimônio

O PL selecionado é R$ 399.488.372.325,77, equivalente a 41,6735% do universo de PL positivo. Os seis FIC-FIDCs selecionados somam R$ 13.940.997.626,48. A amostra ex-FIC soma R$ 385.547.374.699,29 sobre uma indústria ex-FIC de R$ 862.151.993.954,82, ou 44,7192%.

As coberturas por estrato estão em `selection_coverage_by_subtype.csv`. A flag FIC ampliada foi inferida da denominação e preserva também a flag legada; ela serve à reconciliação de dupla contagem potencial e não substitui confirmação documental da política de investimento.

## 5. Inventário, recuperação e leitura documental

O inventário antigo foi revalidado contra o filesystem. Em `document_inventory.csv.gz`, 1.501 PDFs declarados locais não existiam; sobreviveram 571 TXT e 1.449 JSON com hash rechecado. Nos 571 caches de texto, `documento_id` reproduzia o CNPJ, e não um ID documental confiável. Outros inventários continham 9.645 caminhos ausentes e 1.445 referências a arquivos-fonte não baixados. Por isso, `local_exists` legado não foi aceito como prova.

Para cada um dos 100 fundos, a coleta consultou a listagem oficial do Fundos.NET e procurou, por prioridade: regulamento vigente; parte geral e anexo; alterações materiais; instrumentos de emissão; prospecto ou lâmina; relatórios mensais/trimestrais; rating; fatos relevantes/assembleias; e demonstrações financeiras. Datas originais foram preservadas como string e normalizadas com `dayfirst=True`.

O ledger canônico contém 981 linhas: 748 IDs documentais primários únicos e 233 pedidos prioritários ausentes. Foram extraídos página a página 731 documentos (`pypdf`/`pdfplumber`), representando 721 hashes SHA-256 únicos e 21.028 páginas após deduplicação por hash. Quinze documentos ficaram em `OCR necessário`, dois em `inacessível` e nenhum deles sustenta afirmação categórica do glossário.

Todos os 100 fundos têm status documental explícito e ao menos um documento primário lido. Foram lidos 95 regulamentos vigentes; três não estavam listados e dois falharam no download. A cobertura de PL da amostra por regulamento vigente lido é 95,6155%. Também foram processados 52 relatórios de rating, 91 demonstrações financeiras, 98 relatórios mensais/trimestrais e três prospectos/lâminas.

“Lido” no ledger significa texto primário extraído e inspecionável página a página. A leitura jurídica substantiva de cláusulas concentrou-se em 15 regulamentos, equivalentes a 12 famílias independentes de template e 48,4402% do PL da amostra. Repetições idênticas ou quase idênticas foram agrupadas por hash e por família; não foram contadas como evidências econômicas independentes.

## 6. Extração, OCR e conferência visual

Cada registro documental contém CNPJ, nomes, ID Fundos.NET, tipo, datas, versão/status, URL oficial, caminho local, SHA-256, páginas, páginas sem texto, método de extração e estado de leitura. O OCR foi reservado a páginas sem camada textual; documentos integralmente dependentes de OCR e ainda não resolvidos permanecem explicitamente pendentes.

Cláusulas materiais foram comparadas com a página renderizada. A amostra de QA visual abrangeu os arts. 36 a 39 do Anexo Normativo II da RCVM 175 e páginas materiais dos regulamentos Cielo (p. 55 e 106), Aetos (p. 40 e 45), PagSeguro (p. 19), Monee (p. 58) e MT Global (p. 5).

## 7. Matriz de evidências e prevalência

`evidence_long.csv` contém 57 registros atômicos com termo, espécie de afirmação, fundo, segmento, documento, versão, página/seção, trecho curto, hash, confiança e decisão editorial. `term_candidates.csv` consolida 62 candidatos. O denominador nunca é automaticamente 100: cada prática usa apenas fundos com documentação substantiva suficiente.

No denominador de 15 regulamentos:

- critérios de elegibilidade: 15/15;
- linguagem explícita de concentração: 14/15;
- ordem de aplicação/alocação de recursos: 15/15;
- estrutura subordinada efetiva: 6/15;
- reserva nominada: 10/15;
- revolvência/reinvestimento autorizado: 11/15;
- ramp-up contratualmente definido: 1/15, mantido como idiossincrático;
- evento de avaliação separado: 14/15;
- evento de liquidação: 15/15;
- cessão/endosso estritamente sem regresso ou coobrigação: 5/15;
- dever positivo de verificação de lastro: 12/15;
- dispensa ou não incidência da verificação: 3/15;
- expressão literal “excesso de spread”: 0/15; o termo foi mantido somente como inferência analítica, não como prevalência contratual.

As frequências ponderadas usam o PL agregado dos fundos no denominador e excluem FIC-FIDCs da prática de crédito subjacente. O número de famílias econômicas, administradores, gestores e segmentos acompanha cada candidato para reduzir falso consenso causado por templates.

## 8. Revisão editorial e integridade

### Convenções analíticas de desempenho

As métricas abaixo são definições operacionais do Glossário, não campos normativos nem thresholds universais:

- `FPD = exposição da coorte em default na primeira obrigação / exposição elegível da coorte`;
- `roll rate i→j = exposição que migra do estado i para o estado j / exposição elegível no estado i na origem`;
- `taxa de cura = exposição que retorna ao estado adimplente / exposição inadimplente elegível na origem`;
- `taxa de recuperação = caixa recuperado líquido ou bruto, conforme declarado / base de exposição baixada ou inadimplida definida`;
- `WAL = Σ(principal_t × tempo_t) / Σ(principal_t)`;
- `gap de prazo = duration ou WAL dos ativos - duration ou WAL dos passivos`, usando a mesma base temporal;
- `Over N = saldo com atraso superior a N dias / base declarada`.

FPD exige coorte, primeira obrigação, janela e critério de default explícitos. A varredura não localizou definição literal de FPD nos 95 regulamentos vigentes legíveis nem nos 52 relatórios de rating do corpus; por isso o termo foi reclassificado como convenção operacional e deixou de citar o regulamento BTG Consignados II como se fosse sua fonte. Roll rate, cura e recuperação também exigem política operacional; as orientações contábeis oficiais sustentam os estados de atraso, perda e baixa, não uma fórmula universal dessas taxas.

A auditoria pré-revisão abrangeu as 14 páginas então indexadas, conceitos, métricas, fundos de referência, fontes, documentos, o serviço do book e o mini-glossário. A matriz contém definição anterior, aliases, fontes, cobertura, redundância, contradição, afirmação a revalidar e ação proposta.

A edição preservou o formato concept-first. Definições canônicas passaram a concentrar arquitetura fundo/classe/subclasse, participantes, transferência e lastro, Tabela II, estrutura de capital, reforços, revolvência, desempenho, liquidez, eventos, oferta e famílias de recebíveis. O mini-glossário é agora derivado da mesma base estruturada de conceitos e métricas.

As validações cobrem IDs únicos, referências cruzadas, caminhos e hashes locais, correspondência dos dez fundos narrativos com `reference_funds.json`, carregamento das 18 páginas, busca por aliases e termos essenciais, 100 CNPJs únicos, reconciliação de PL, cobertura de estratos e status documental dos 100 fundos.

## 9. Reprodutibilidade

Ordem dos scripts:

```bash
source .venv/bin/activate
python scripts/build_glossario_100_fidcs.py
python scripts/build_glossario_document_corpus.py
python scripts/build_glossario_evidence.py
python scripts/finalize_glossario_100_manifest.py
python -m unittest tests.test_fidc_book
git diff --check
```

Os hashes dos artefatos finais estão em `manifest.json`. A recuperação remota depende da disponibilidade do Fundos.NET; os PDFs brutos e renderizações de trabalho permanecem fora do diretório versionado, enquanto o ledger conserva URL, ID, hash e estado.

## 10. Limitações

- Cinco regulamentos vigentes não foram lidos: três ausentes na listagem e dois inacessíveis no download.
- Quinze documentos requerem OCR adicional; não foram usados como suporte categórico.
- O corpus documental é amplo, mas a leitura jurídica substantiva de prevalência tem denominador de 15 regulamentos e 12 famílias, declarado em cada prática.
- A Tabela II classifica valores reportados e não substitui a leitura da política de investimento; Sem segmentação IME expressa falta de valores suficientes.
- A identificação ampliada de FIC-FIDC por denominação pode conter imperfeições.
- Norma e documento foram verificados em 16/07/2026; versões posteriores exigem nova revisão.
