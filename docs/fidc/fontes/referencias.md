# Referências e rastreabilidade

## Fontes normativas e de reporte

- **Resolução da Comissão de Valores Mobiliários (RCVM) 175:** Parte Geral, Anexo Normativo II e página oficial de consolidação.
- **Resolução CVM 160:** distribuição pública de cotas e outros valores mobiliários.
- **Resolução CVM 30:** adequação ao perfil do cliente e categorias de investidores.
- **Instrução CVM 489 e orientações oficiais:** demonstrações, mensuração e perdas contábeis de Fundo de Investimento em Direitos Creditórios (FIDC).
- **Informe Mensal:** padrão de arquivo Extensible Markup Language (XML) e dados abertos da Comissão de Valores Mobiliários (CVM).
- **Ofício-Circular da Superintendência de Supervisão de Securitização (SSE) da CVM 8/2023:** registro, custódia e verificação de lastro.

A página oficial da RCVM 175 indicava consolidação até a RCVM 240/2026 na verificação de 16/07/2026. Uma análise histórica deve preservar também a redação vigente na data do fato.

## Documentos dos fundos

- **Índice versionado:** registra **Cadastro Nacional da Pessoa Jurídica (CNPJ)**, identificador do Fundos.NET, tipo, data, versão, endereço oficial, estado, páginas, método e páginas do glossário relacionadas.
- **Arquivos brutos de trabalho:** ficam fora do Git quando seu volume não é adequado ao repositório. O registro versionado conserva endereço, impressão digital criptográfica e estado.
- **Secure Hash Algorithm de 256 bits (SHA-256):** função criptográfica usada para identificar o conteúdo do arquivo e detectar mudança ou duplicação.
- **Caminho local:** é evidência de processamento no ambiente de auditoria, não um link público para o leitor da página.

## Correção do acervo legado

- Treze caminhos antigos sob `estudo/` foram removidos porque os arquivos não existiam.
- Identificadores divergentes entre `sources.json` e `document_index.json` foram reconciliados.
- Inventários antigos que marcavam `local_exists` foram rechecados no sistema de arquivos.
- Textos intermediários em cache continuam úteis para localizar candidatos, mas não substituem o documento primário.

## Escada de leitura documental

| Estado | Significado |
|---|---|
| **processado** | primário recuperado e texto extraído página a página |
| **leitura substantiva** | cláusulas materiais interpretadas e registradas |
| **conferido visualmente** | página renderizada e comparada com a extração |
| **Optical Character Recognition (OCR), ou reconhecimento óptico de caracteres, necessário** | página depende desse processo de leitura de imagem |
| **somente cache, ou cache-only** | derivado sem arquivo primário em Portable Document Format (PDF) recuperável; apenas pista |
| **ausente** | documento aplicável não localizado na listagem |
| **inacessível** | falha de listagem ou transferência do arquivo |
| **não aplicável** | tipo não corresponde ao caso |

Ausência não é zero nem prova de inexistência de cláusula.

## Evidência contratual

- Uma linha de `evidence_long.csv` preserva termo, fundo, segmento, patrimônio, documento, versão, página, trecho curto e hash.
- Prática recorrente exige pelo menos dois fundos independentes com documentação suficiente.
- Modelo documental repetido conta como uma família, não como várias confirmações independentes.
- Limite numérico de um fundo não vira definição universal.

## Evidência normativa

- Definições legais citam norma e dispositivo.
- Quando a página editorial e a página física do arquivo divergem, o registro preserva dispositivo e página física.
- Nova consolidação normativa exige nova data de verificação.

## Artefatos versionados

O [diretório público da revisão no GitHub](https://github.com/abalroar/fidc/tree/main/reports/glossario_100_fidcs_20260716) contém seleção, cobertura patrimonial, inventário documental, evidências, candidatos, matriz de lacunas, metodologia, relatório, log de mudanças e manifesto.

O manifesto fixa competência, parâmetros, reconciliações e impressões digitais SHA-256. A revisão é exaustiva em relação ao corpus e às normas verificadas, não universalmente completa.

Última verificação: **16/07/2026**.
