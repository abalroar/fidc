# Curadoria documental — diagnóstico e aceite

Data: 2026-10-13T04:16:20-03:00. Escopo: 85 carteiras, 194 CNPJs cadastrados e 275 participações fundo/carteira. Os veículos vinculados documentalmente entram em camada própria.

No catálogo ampliado conservador, as respostas rastreáveis reconstruídas passam de 2319/11053 (21,0%) para 7803/11053 (70,6%). Nos 27 conceitos anteriores pareados, passam de 2319/5235 (44,3%) para 3923/5235 (74,9%). Aplicabilidade em apuração: 3217; não aplicabilidade documentada: 7. Pendências: 3250. Foram reintroduzidas 0 perguntas ausentes dos arquivos publicados para impedir ganho de cobertura pela remoção de linhas.

Reconstrução dos pareceres antigos pelo LEGACY_MAP, com valor substantivo, ID citado, URL primária, SHA256 e processamento completo registrados no inventário público ou local; páginas fora da extensão física conhecida são recusadas. A aplicabilidade antiga não era modelada. O denominador é o catálogo atual conservador, incluindo os critérios anteriores ausentes do arquivo publicado. O locator é reconstruído na coleção atual; isso não prova que o documento tivesse sido obtido em 07/10/2026. O número mede afirmações antigas rastreáveis reconstruídas, sem certificar revisão semântica ou disponibilidade em 07/10/2026.

## Causas e correções

| Falha relatada | Causa identificada | Tratamento e limite |
| --- | --- | --- |
| Fundos quase inteiros em N/D | Aquisição por CNPJ falhou com timeout/HTTP 520; havia inventário sem regulamento local. Extrações e pareceres não cobriam todo o acervo. | Inventário por documento, download e parsing com estados próprios; recuperação local e novas buscas. Documento inventariado não equivale a documento lido. |
| Afirmações genéricas e controles iguais | Critérios fixos, fallback textual e validação de campos preenchidos aceitavam textos de processo como fatos. | Catálogo de crédito, cláusula localizada e valor específico; proveniência separada e regras comuns só quando confirmadas. |
| Frases de lacuna substituíam conteúdo | O contrato aceitava qualquer descrição não vazia; o renderizador limpava remissões e faltas. | Estado, motivo e busca ficam nas pendências individuais; resposta e mecânica ficam na matriz. |
| N/D sem motivo | Ausência e aplicabilidade não eram campos independentes; a apresentação trocava lacunas por hífen e depois N/D. | Estados de aquisição, acesso, parsing, cláusula, documento referido e conflito; aplicabilidade em apuração permanece no denominador. |
| Fundos mudavam de agrupamento | Colunas com vetores visuais iguais eram agrupadas por seção, inclusive grupos inteiros sem informação. | Uma coluna por CNPJ na ordem da cesta, com largura fixa e identificação acessível. |
| Fontes afastadas das células | Fontes por célula existiam no CSV, mas a tela as concentrava em auditoria e o PPT nas notas. | ID, data e página/cláusula junto da resposta; links e excertos em detalhes; conteúdo integral nos arquivos. |
| Instruções de interface e competências divergentes | O enriquecimento escolhia o último cache de cada CNPJ e escrevia “selecionar competência”; Documentos não recebia o contexto financeiro. | Resolução da posição comum de toda a cesta; snapshot publicado e dados carregados com identidade e competência explícitas. |
| Limites sem confronto com IME | A aba mostrava descrições de monitorabilidade; faltavam fórmula, vigência, camada e observação ligada à célula. | Confronto com numerador/base/unidade; diferença de vigência, ausência de saldo individual, carência ou apuração diária impedem certificado. |
| FIC sem classe investida | O vínculo era citado em texto e a aquisição/exposição não era seguida até o veículo declarado. | Documentos e critérios do investido em camada própria, preservando CNPJ/subclasse e distinguindo vínculo permitido de posição efetiva. |

Na aquisição FIAGRO, o endpoint `pesquisarGerenciadorDocumentosDados` podia receber o filtro padrão `tipoFundo=2` de FIDC. O adaptador passa a consultar o CNPJ exato sem limitar o tipo e registra `scope=cnpj_all_fund_types`. O experimento para Ceres retornou 9 documentos com tipo 2 e 17 sem o filtro, incluindo IMEs de maio a agosto/2026 e CDA. Esse experimento e o inventário persistido são evidências distintas; o estado realmente gravado consta em `acquisition_by_fund.csv` e nos corpora.

## Entrega verificável

- `coverage_funds.csv`: antes/depois por CNPJ, denominadores, aplicabilidade e proveniência.
- `coverage_portfolios.csv`: as 85 cestas completas, incluindo repetição de CNPJ entre carteiras.
- `remaining_cells.csv`: uma linha por pergunta pendente, com estado, motivo, fonte criterial e referência ao registro de aquisição do CNPJ.
- `acquisition_by_fund.csv`: inventário, disponibilidade, parsing, buscas e rotas pendentes.
- `ime_comparisons.csv`: competência comum, observação, limite, fórmula, fonte e ressalva de comparação; referências agregadas ficam em campos próprios quando a base contratual não é reproduzível.
- `quarterly_declarations.csv`: respostas declaradas no informe trimestral e conflitos com a norma, preservando período, fonte e ressalva; sem aumentar a cobertura normativa.
- `summary.json`: método, fingerprints dos insumos e limites das afirmações.

Confronto IME: 1589 linhas de critério/CNPJ/carteira, sendo 1564 da camada própria e 25 de veículos vinculados. Há 69 valores observados para medidas contratuais e 512 referências agregadas, mantidos em campos distintos; essas contagens podem coexistir numa linha e não representam CNPJs únicos. Resultado conclusivo de enquadramento: 0 linhas. Dado IME indisponível para a medida ou posição comum: 830 linhas, com motivo individual no CSV. Vigência efetiva, início/carência, base individual e frequência de apuração impedem as conclusões pendentes; referência agregada não certifica cumprimento.

Aquisição no escopo ativo: 18841 registros inventariados, 7685 documentos locais/obtidos e 7540 textos com parsing completo. Os números de registros e arquivos podem diferir por versão, tipo e reaproveitamento de acervo. Buscas externas direcionadas não constituem levantamento exaustivo de todas as fontes.

Qualidade de leitura: 0 documentos com texto ilegível por codificação e 5 recuperados por OCR local, com método, confiança e páginas excluídas no inventário. Páginas físicas completas não certificam texto legível. OCR conserva a referência ao PDF original e não representa leitura humana.

Rotas externas: `{"generated_at": "2026-10-13T05:32:28Z", "cnpjs": 194, "funds_with_routes": 175, "funds_without_complete_regulatory_document": 0, "routes": 984, "unique_urls_probed": 192, "probe_states": {"blocked": 198, "portal_reachable": 521, "error": 54, "not_found": 161, "http_error": 24, "reachable_candidate_document": 26}, "web_searches": [], "no_document_downloads": true}`. O registro inicial usa 20 URLs únicas sondadas por HEAD para 430 rotas identificadas; retornos compartilhados por URL são contados por rota no resumo. Links de PDF podem ser candidatos por nome com CNPJ ainda não verificado. Acessibilidade de portal ou resultado vazio não comprova existência, identidade ou ausência de documento.

Proveniência das respostas: `{"primary_passage": 7631, "verified_override": 208}`. `primary_passage` identifica extração de trecho; `previous_review_with_primary_locator` identifica parecer anterior reaproveitado; `verified_override` identifica leitura dirigida registrada nesta execução. Nenhuma categoria certifica revisão humana integral.

O QA automatizado cobre os arquivos declarados no relatório do validador; a amostra material e a inspeção visual têm escopo próprio, indicado em `summary.json`. A matriz foi exercitada para BTG, cesta de 101 fundos e fundo individual, com fontes, valores monetários literais e downloads locais. Implementação, publicação e validação pública devem ser comprovadas separadamente.

A revisão distribuída inicial permanece preservada. O recheck dirigido dos achados iniciais e adicionais conserva estado, valor, fontes e hash antes/depois em `distributed_credit_review_revision.json`, com seu escopo explícito no resumo. Retirar confirmação inadequada reduz a cobertura e mantém a pergunta pendente; isso não obtém a cláusula faltante. A ausência de achado remanescente nesse conjunto não certifica todos os critérios ou documentos do universo.

Os critérios preservam número, base, janela, cura/reincidência, waterfall, liberação da júnior, PDD, hedge/MTM, cessão, garantias e cobrança quando documentados. As dimensões do material de referência de 16 slides orientaram as perguntas; esse material não substitui regulamento ou evidência por CNPJ.

Relatório gerado somente por leitura. Insumos alterados durante a geração: 0. Se houver alteração, execute novamente após terminar aquisição, snapshots e construção dos critérios.
