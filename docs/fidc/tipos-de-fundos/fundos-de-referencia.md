# Corpus de 100 FIDCs e casos documentais

Os dez **Fundos de Investimento em Direitos Creditórios (FIDCs)** exibidos nesta página são **exemplos narrativos**, não o corpus inteiro. A revisão separa seleção, processamento documental e leitura substantiva para não tratar extração automática como análise jurídica integral.

## Escala da revisão

| Camada | Escopo | Uso no glossário |
|---|---:|---|
| **Fundos selecionados** | 100 | cobertura patrimonial e dos estratos ocupados |
| **Fundos com algum primário processado** | 100 | cobertura documental mínima |
| **Regulamentos vigentes processados** | 95 | extração página a página e localização de cláusulas |
| **Documentos primários processados** | 731 | 721 impressões digitais criptográficas únicas e 21.028 páginas deduplicadas |
| **Leitura substantiva de regulamentos** | 15 fundos | 12 famílias independentes e 48,44% do patrimônio líquido (PL) amostral |
| **Exemplos narrativos abaixo** | 10 | ilustração rastreável, sem formar catálogo |

- **Processado:** documento primário recuperado e texto extraído por página.
- **Leitura substantiva:** cláusulas interpretadas e classificadas para a matriz de evidências.
- **Conferência visual:** página renderizada e comparada com a extração.

## Dez exemplos narrativos

| Fundo | Cadastro Nacional da Pessoa Jurídica (CNPJ) do fundo | Segmento oficial em 202605 | Documento-âncora | Uso editorial |
|---|---|---|---|---|
| FIDC do Sistema Petrobras | 09.195.235/0001-50 | Industrial | regulamento, Fundos.NET 792797 | arquitetura corporativa e política de classe |
| TAPSO FIDC RL | 26.287.464/0001-14 | Cartão de crédito | regulamento, Fundos.NET 1066031 | recebíveis e estrutura de pagamentos |
| Cloudwalk Bela FIDC | 62.393.679/0001-83 | Cartão de crédito | regulamento, Fundos.NET 1117954 | meios de pagamento como taxonomia documental |
| Itaú Crédito Privado FIDC RL | 53.286.499/0001-01 | Serviços | regulamento, Fundos.NET 579249 | limites e elegibilidade |
| Esperanza FIDC | 53.263.761/0001-00 | Financeiro: outros | regulamento, Fundos.NET 830304 | necessidade de explicar a abertura “outros” com documentos |
| BTG Pactual Consignados II FIDC | 52.242.420/0001-88 | Serviços | regulamento, Fundos.NET 938243 | diferença entre reporte e taxonomia funcional |
| Classe Consignado Privado do MT Global FIDC RL | 63.953.619/0001-30 | Comercial | anexo da classe 63.953.620/0001-65, Fundos.NET 1222863 | vínculo entre fundo, classe e documento componente |
| Aetos Energia FIDC | 52.610.624/0001-24 | Serviços | regulamento, Fundos.NET 794164 | concentração e fluxos de serviços |
| FIDC PagSeguro I | 28.169.275/0001-72 | Cartão de crédito | regulamento, Fundos.NET 1149521 | papéis no arranjo de pagamento |
| Cielo FIDC | 26.286.939/0001-58 | Cartão de crédito | regulamento, Fundos.NET 1017493 | necessidade de identificar o devedor do direito concreto |

Os temas da última coluna são rotas de leitura, não conclusões de risco. O nome do fundo não prova mecanismo, devedor, garantia ou desempenho atual.

**RL** nas denominações legais significa **responsabilidade limitada**. A sigla integra o nome cadastrado e não descreve a família do recebível.

## Como os 100 foram escolhidos

- **Competência:** 202605, indicada pelo `competencia_snapshot` oficial da base do estudo.
- **Nível do ranking:** CNPJ do fundo, com soma do patrimônio líquido das classes componentes.
- **Filtro:** exclusão de patrimônio nulo, zero ou negativo.
- **Cobertura mínima:** até dois maiores de cada estrato ocupado, incluindo o estrato de qualidade **Sem segmentação IME**.
- **Complemento:** maiores patrimônios globais ainda não selecionados, com desempate por CNPJ.
- **Fundos de cotas:** classes de investimento em cotas de FIDC, identificadas como **FIC-FIDC**, permaneceram por materialidade, mas foram excluídas das prevalências do crédito subjacente.

- **Unicidade:** 100 CNPJs únicos.
- **Estratos:** os 18 estratos ocupados estão representados; **Sem segmentação IME** é apenas o nome legado do estrato de qualidade de dados.
- **Cobertura bruta:** 41,67% do PL positivo.
- **Cobertura sem fundos de cotas:** 44,72% quando FIC-FIDCs são excluídos dos dois lados.
- **Estrato vazio:** Marcas e patentes não tinha população classificável na competência.

## Como a evidência entra no glossário

- **Norma:** pode sustentar um conceito normativo sem frequência contratual.
- **Prática recorrente:** exige pelo menos dois fundos economicamente independentes e documentação suficiente.
- **Cláusula isolada:** aparece apenas como variação ou exemplo específico.
- **Modelo documental repetido:** conta como uma família de evidência, não como várias práticas independentes.
- **Somente cache:** texto derivado sem o documento primário; serve como pista e não sustenta afirmação categórica.

## Onde consultar o rastro

Os artefatos versionados estão no [diretório público da revisão no GitHub](https://github.com/abalroar/fidc/tree/main/reports/glossario_100_fidcs_20260716) e incluem:

- **selection_100.csv:** os 100 fundos e a razão da seleção;
- **document_coverage.csv:** estado por fundo e prioridade documental;
- **evidence_long.csv:** evidências atômicas, documento, página e impressão digital criptográfica;
- **term_candidates.csv:** decisões editoriais por termo;
- **glossary_review_report.md:** cobertura, resultado e limitações;
- **manifest.json:** competência, reconciliações e impressões digitais pelo **Secure Hash Algorithm de 256 bits (SHA-256)**.

Veja também [Referências e rastreabilidade](../fontes/referencias.md).

Data de corte documental: **16/07/2026**.
