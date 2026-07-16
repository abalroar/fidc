# Referências e rastreabilidade

## Fontes normativas e de reporte

- página oficial e textos consolidados da RCVM 175, Parte Geral e Anexo Normativo II;
- RCVM 160, para ofertas públicas;
- RCVM 30, para categorias de investidores e suitability;
- ICVM 489 e orientações SIN/SNC, para demonstrações e perdas contábeis de FIDC;
- padrão XML mensal FIDC/CVMWeb e dados abertos da CVM;
- Ofício-Circular CVM/SSE 8/2023, para registro, custódia e lastro.

Os URLs oficiais e a data de verificação ficam em `sources.json`. A consolidação consultada da RCVM 175 incorporava alterações até a RCVM 240/2026 em 16/07/2026.

## Documentos de fundos

O índice versionado contém apenas documentos primários efetivamente recuperados ou fontes oficiais com status explícito. Cada registro informa CNPJ, ID Fundos.NET, data original, versão, URL, caminho local quando versionável, SHA-256, páginas, método e páginas do book relacionadas.

PDFs baixados para a análise ficam em `data/raw/glossario_100_fidcs_20260716/`, diretório ignorado pelo Git; sua existência e hash são auditados no ledger `document_coverage.csv`. O book não declara esses arquivos como dependências locais permanentes.

## Correção do acervo legado

Os antigos caminhos `estudo/*.pdf` foram retirados dos índices: os 13 arquivos declarados não existiam no filesystem. Também foram eliminados IDs divergentes entre `sources.json` e `document_index.json`. Caches antigos continuam úteis como pistas, mas são rotulados `cache-only` porque o PDF-fonte não está disponível.

## Evidência contratual

Uma linha de `evidence_long.csv` preserva termo, fundo, segmento, PL, documento, versão, página, trecho curto e hash. Para entrar como prática recorrente, a cláusula precisa aparecer em pelo menos duas famílias econômicas independentes com documento suficiente. Repetição do mesmo template não aumenta artificialmente a independência.

## Evidência normativa

Definições legais citam norma e artigo. Quando o PDF tem paginação editorial diferente da página do arquivo, o registro guarda seção/artigo e página física. Alterações futuras exigem nova data de verificação.

## Estados documentais

| Status | Significado |
|---|---|
| lido | primário recuperado e extraído página a página |
| OCR necessário | primário recuperado, mas uma ou mais páginas precisam OCR/conferência |
| cache-only | texto derivado sem primário recuperável; apenas pista |
| ausente | documento não encontrado na listagem consultada |
| não aplicável | tipo não é pertinente à estrutura |
| inacessível | listagem ou download falhou |

Ausência não é zero nem prova de inexistência de cláusula.

## Artefatos da revisão

O diretório `reports/glossario_100_fidcs_20260716/` contém seleção, cobertura patrimonial, cobertura documental, evidências, candidatos, matriz de lacunas, log de mudanças, metodologia, relatório e manifesto. O manifesto fixa competência, parâmetros, hashes e reconciliações.

Última verificação: **16/07/2026**.
