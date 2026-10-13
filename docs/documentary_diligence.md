# Curadoria documental das carteiras

A aba **Dados de Carteira → Documentos** usa a cesta cadastrada, uma coluna por CNPJ e a mesma ordem entre os quadros. Regulamento, anexos, suplementos e versões anteriores sustentam os critérios; o IME fornece a observação mensal. Cada resposta conserva documento, data, versão e página ou cláusula. A falta de documento, acesso, texto, cláusula ou anexo referido tem estado próprio.

O catálogo inclui elegibilidade, recebíveis e partes, alocação e perímetro, proteção por camada, qualidade da carteira, avaliação/liquidação e cura, waterfall e prazo, garantias/cobrança, hedge/MTM, prestadores, emissões/custos e governança. As perguntas específicas do painel anterior permanecem no catálogo ou nas pendências. O material de referência de 16 slides orienta as dimensões de crédito; o fundamento de cada resposta vem dos documentos do CNPJ.

## Arquivos e responsabilidades

| Artefato | Conteúdo |
| --- | --- |
| `portfolios.json` | Cestas cadastradas e identidade dos fundos. |
| `data/documentary_diligence/corpus/<cnpj>.json` | Inventário, versões, buscas, estado de download e parsing, erros e limites da rodada. |
| `data/documentary_diligence/audit_corpus/<cnpj>.json` | Cópia sanitizada dos metadados para a aplicação publicada, com URLs e hashes, sem caminhos pessoais. |
| `data/documentary_diligence/funds/<cnpj>.json` | Critérios estruturados, fontes, história, prevalência, regras reproduzíveis e vínculos de investimento. |
| `data/documentary_diligence/history/<cnpj>.json` | Evidência histórica integral com passagens deduplicadas e referência por hash; a tela usa resumo e prévias limitadas. |
| `data/documentary_diligence/ime/` e `ime_index.json` | Snapshots mensais publicados, competência, origem, versão e campos recuperados. |
| `data/documentary_diligence/quarterly/` e `quarterly_index.json` | Informes trimestrais, formato efetivamente retornado, identidade, valores/respostas declarados e localizadores. |
| `data/documentary_diligence/source_routes/` | Rotas de administrador, gestor, rating, ofertas e verificação; consultas e limites efetivamente executados. |
| `data/documentary_diligence/verified_overrides/` | Leituras dirigidas com cláusulas e condições específicas. |
| `data/documentary_diligence/qa/` | Validação automatizada e amostra de trechos, com seu escopo. |
| `reports/documentary_diligence_YYYYMMDD/` | Cobertura antes/depois, pendências individuais, aquisição, confronto IME e diagnóstico. |

Os PDFs e textos completos ficam no acervo local. Sua cópia e publicação devem considerar tamanho e necessidade da tela. A aplicação precisa de critérios, fontes rastreáveis, metadados do corpus e snapshots IME compactos; ela não precisa carregar simultaneamente todos os PDFs, textos e históricos financeiros. Downloads públicos preservam URLs, hashes e referências e removem caminhos pessoais do computador.

`corpus/` conserva referências locais necessárias para retomada da aquisição. `audit_corpus/` fornece os mesmos estados documentais sanitizados à tela e ao relatório quando o corpus local não estiver publicado. O relatório de aceite pode ser reproduzido com os arquivos públicos: ele exige ID, URL, SHA256 e estado de processamento completo para reconstruir uma fonte antiga e aplica a mesma regra ao inventário local. O índice trimestral público `audit_quarterly_index.json` substitui o índice operacional quando este estiver ausente.

`acquisition_by_fund.csv` conserva contadores de documentos por tipo, disponibilidade, qualidade e buscas, com referência ao corpus integral de cada CNPJ. Os documentos e logs completos permanecem em `audit_corpus/`; sua repetição em uma única célula CSV ultrapassaria o limite de leitura do Excel e duplicaria o pacote. `remaining_cells.csv` referencia o mesmo registro de aquisição e mantém o motivo individual de cada pergunta.

O conjunto anterior em `data/deep_dives/` e os pareceres em `data/regulatory_profiles/documentary_comparisons/` são preservados. A nova aba prioriza o schema v2 para a cesta disponível. A exportação completa usa a mesma leitura v2 e conserva os motivos das ausências em tabelas editáveis e fontes nas notas.

## Aquisição e parsing

O processo é serial, com orçamento de bytes, prazo de rede, espaço mínimo em disco e possibilidade de retomada. Um documento por vez limita a memória. Inventário, download e leitura são etapas distintas. Uma lista com 100 documentos não significa que 100 PDFs foram obtidos ou lidos.

Fundos.NET/B3 deve ser consultado pelo CNPJ exato, com atenção ao tipo de fundo/classe. O filtro geral `tipoFundo=2` pode excluir documentos de FIAGRO. O adaptador documental usa o endpoint `pesquisarGerenciadorDocumentosDados` sem limitar o tipo, registrando o escopo da consulta. Ao retomar uma rodada, a listagem antiga precisa ser invalidada quando seu escopo for diferente. CNPJ com consulta vazia, portal acessível ou arquivo candidato por nome continua sem prova de ausência, identidade ou conteúdo.

Os corpora registram o que foi consultado, os arquivos presentes, o parsing completo ou parcial e os erros. Requisição bloqueada, timeout, orçamento esgotado e PDF sem texto não podem ser tratados como cláusula inexistente. Fontes externas possuem cobertura própria: o registro inicial sondou 20 URLs únicas para 430 rotas. Esses resultados direcionados não constituem inventário externo exaustivo nem obtenção de todos os relatórios de rating/lastro.

`unreadable_text` identifica PDFs com todas as páginas físicas processadas e mapa de caracteres corrompido. A tela informa “Texto ilegível por codificação do PDF”; o documento não entra no contador de textos completos. Uma leitura visual dirigida pode sustentar uma resposta específica com `verification=visual_directed`, localizador e registro próprios, sem certificar a legibilidade do restante do documento.

A recuperação por OCR local conserva `parse_method=apple_vision_ocr`, confiança e páginas excluídas. As fontes exibem “Texto por OCR local; fonte PDF original”, com link e página do PDF. A aceitação automática exige confiança média de pelo menos 0,96 e mínima de 0,85 por página; páginas abaixo desses limites não sustentam extração automática. OCR é transcrição automática, com escopo próprio e sem certificação de leitura humana.

Os informes trimestrais têm etapas serializadas de versão atual e histórico e orçamento próprio. O servidor pode entregar PDF ou XML; `source.type` conserva `quarterly_pdf` ou `quarterly_xml`. Identidade, competência e localizador são verificados antes de usar uma resposta declarada. Dados trimestrais são evidência de verificação e ocorrência declarada, com sua data e seu perímetro; a cláusula continua sustentada pelo documento normativo. O relatório conserva estados e formatos por CNPJ e os hashes dos arquivos trimestrais.

## Respostas e cobertura

Uma resposta conta quando está confirmada e aplicável, tem valor substantivo e aponta para documento identificado, data válida e página ou cláusula. Um registro de busca, corpus, falha de acesso ou fonte sem localização não conta como resposta.

**Cobertura conservadora = respostas confirmadas com fonte válida ÷ (critérios aplicáveis + aplicabilidade em apuração).** A não aplicabilidade só sai do denominador com fundamento documental. O relatório reintroduz perguntas do catálogo ou do quadro anterior ausentes do arquivo publicado, marcando-as como pendência. Nenhum ganho deve resultar de apagar uma linha sem resposta.

O relatório apresenta duas comparações:

1. **Pareada:** os 27 conceitos do painel anterior, com o mesmo denominador antes/depois e N/A documentado explicitamente.
2. **Ampliada:** catálogo atual, perguntas anteriores preservadas e critérios específicos. O antes inclui somente afirmações antigas mapeadas e rastreáveis.

A aplicabilidade antiga não existia no schema. A reconstrução usa `LEGACY_MAP`, valor substantivo, ID citado e localizador, cruzados com URL, SHA256 e processamento completo no inventário atual. O locator é reconstruído na coleção atual; isso não prova que o documento tivesse sido obtido em 07/10/2026. Essa reconstrução mede a rastreabilidade das afirmações anteriores; ela não certifica sua validade semântica ou a extensão da leitura daquela data. O baseline mecânico original permanece separado em `baseline.json` e no resumo do relatório.

`primary_passage`, `previous_review_with_primary_locator` e `verified_override` são contados separadamente. Os termos identificam extração de trecho, reaproveitamento de parecer e leitura dirigida registrada. Nenhuma categoria implica certificação de revisão humana integral. O validador de relevância cobre seu conjunto de arquivos; a amostra material e a inspeção visual têm escopos próprios.

## Competência e confronto IME

O confronto usa a posição comum dos CNPJs elegíveis da cesta completa. Um subconjunto carregado ou a última competência isolada de cada fundo não deve substituir essa posição. Registro/cancelamento e exclusões conservam a fonte e a ressalva temporal.

`registry_statuses.json` publica o snapshot cadastral dos CNPJs exatos da cesta, com URL oficial, hash do ZIP e data de observação. Esse arquivo permite reproduzir as exclusões por cancelamento e a posição comum mesmo sem o cache local de cadastro CVM. O relatório inclui seu hash; a situação é a observada nessa rodada, com as datas cadastrais explicitadas.

Cada comparação conserva numerador, denominador, unidade, camada, vigência, carência e frequência. O valor observado pode ser apresentado quando disponível; a certificação de enquadramento é suspensa se faltar vigência efetiva, data de início, saldo individual de série/subclasse ou correspondência exata com o IME. Snapshot mensal não demonstra cura, reincidência ou conformidade diária. Disponibilidades não equivalem automaticamente a reserva contratual, e posição agregada de derivativos não demonstra finalidade, elegibilidade ou reserva de MTM.

Os sete critérios de alocação, subordinação, cobertura, reservas, PDD e concentração têm confronto explícito mesmo quando a fórmula contratual exige esclarecimento. Nesses casos, a célula mostra a razão de incomparabilidade e, quando calculável, uma **referência agregada** com fórmula e fonte próprias. `context_value` conserva essa referência; `observed_value` permanece vazio se a medida exigida pelo regulamento não puder ser reproduzida. A referência agregada não conta como enquadramento.

O FIC mantém sua própria coluna e detalha o veículo vinculado com CNPJ/subclasse e fontes. Política que permite comprar cotas, vínculo documental e posição efetivamente investida são estados distintos. Peso, exposição efetiva e lastro final permanecem sem estimativa quando não declarados.

## Executar e retomar

O wrapper serial global organiza aquisição, parsing, snapshots mensais, construção de critérios, validação e relatório. Seu lock evita duas rodadas concorrentes; a retomada conserva os limites de cada estágio. Ele deve ser executado no checkout de trabalho e terminar antes da geração do relatório final. O estágio IME publica snapshots mensais compactos; abrir Documentos não deve iniciar uma carga de 24 meses de dados financeiros.

```bash
.venv/bin/python scripts/refresh_all_documentary_diligence.py \
  --resume --network-timeout 8 --attempts 2 \
  --max-download-gb 6 --max-quarterly-download-gb .25 --disk-floor-gb 10
```

O lock é `data/documentary_diligence/.global-refresh.lock` e o checkpoint é `run_status.json`. Uma etapa e um processo filho rodam por vez; o estágio IME cobre três meses. `--skip-network` usa o acervo disponível. `--only-stage build --only-stage report` declara execução parcial. O lock do wrapper não protege invocações individuais antigas: não mantenha esses comandos em paralelo à rodada global.

Os comandos individuais permanecem disponíveis para diagnóstico e manutenção:

```bash
.venv/bin/python scripts/refresh_documentary_corpus.py --help
.venv/bin/python scripts/build_documentary_diligence.py --help
.venv/bin/python scripts/report_documentary_diligence.py
```

Relatório de uma data e destino explícitos:

```bash
.venv/bin/python scripts/report_documentary_diligence.py \
  --root /caminho/do/repositorio \
  --as-of 2026-10-13 \
  --output-dir reports/documentary_diligence_20261013
```

`--skip-ime` produz um relatório documental provisório, sem a tabela de confronto preenchida. O relatório final deve rodar com IME após encerrar aquisição, snapshots e construção. Os arquivos são escritos atomicamente; `summary.json` é o marcador final da rodada. Fingerprints dos insumos e alterações detectadas durante a geração permitem conferir consistência. Uma rodada com insumos mudando precisa ser executada novamente.

## Validação e publicação

Conferir cobertura e pendências de todos os CNPJs, identidade da cesta, número de colunas, fonte de cada valor e estados de ausência. Exercitar uma cesta extensa, um fundo individual e um FIC. Na interface, cabeçalhos e critérios ficam fixos, sem agrupar fundos por respostas idênticas. Valores em reais usam HTML e permanecem literais, sem interpretação como fórmula LaTeX.

O cabeçalho usa o apelido cadastrado para caber na tabela e oferece a identificação completa com nome e CNPJ. O nome integral e a camada própria ou investida permanecem nas fontes e nos downloads.

CSV/JSON incluem estados, fontes, regras, competência e camada própria/investida. A exportação de JSON é um ZIP com arquivos por CNPJ, metadados da cesta, corpora e históricos completos. Ela lê e serializa um fundo por vez, evitando montar o histórico da cesta inteira em memória. CSV, ZIP e PPTX são preparados somente no clique de download. O inventário da tela é consultado para o fundo escolhido, sem carregar todos os corpora.

O PPTX usa tabelas editáveis, estados tipificados e excertos atuais completos nas notas; o histórico integral permanece no ZIP. Texto de resposta deve ser curto e material, com a condição integral na fonte. A tela conserva quantidade, datas e referências do histórico, com as passagens completas no arquivo separado. A chave de cada download inclui os arquivos dos fundos, históricos, corpora e o código de exportação.

Para publicação, incluir metadados, critérios e snapshots necessários, conferir URLs/hashes e manter o acervo bruto fora do pacote quando desnecessário. Reiniciar o runtime após atualização de módulos. Conferir no fluxo público a cesta escolhida, a competência, as fontes e os downloads realmente servidos. Implementação local, commit/merge e funcionamento público são evidências separadas.
