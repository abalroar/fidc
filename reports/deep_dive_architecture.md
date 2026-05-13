# Deep Dive - arquitetura e prompt operacional

## Objetivo

A aba `Deep Dive` consome pacotes offline já curados e versionados no repositório. Ela não baixa dados, não consulta CVM e não executa LLM no Streamlit. O fluxo esperado é:

1. extração/curadoria offline via terminal;
2. geração de tabelas auditáveis em CSV;
3. empacotamento em `data/deep_dives/<deep_dive_id>/`;
4. commit/push do pacote;
5. renderização no app e exportação PPTX editável.

## Referência visual

O padrão é research institucional: fundo branco, tabela como elemento central, cabeçalho escuro, tipografia Calibri/sem serifa, uso restrito de laranja para destaque e rodapé técnico discreto. A estética vem de alinhamento, densidade controlada e rastreabilidade, não de ornamento.

## Estrutura de pacote

Cada pacote deve conter:

- `manifest.json`: metadados, fundos, tabelas, fonte, confidencialidade e warnings.
- `tables/*.csv`: matrizes ou tabelas fonte com dados já formatados para apresentação.
- `evidence/*.csv`: evidências documentais ou inventários de suporte.
- `notes/*.md`: relatório narrativo ou memória de curadoria.

O app lista todos os pacotes encontrados em `data/deep_dives/*/manifest.json`.

## Componentes implementados

- `services/deep_dive_models.py`: dataclasses do manifesto e tabelas.
- `services/deep_dive_store.py`: descoberta, leitura e filtro por carteira.
- `services/deep_dive_ppt_export.py`: exportação PPTX editável com tabelas reais.
- `tabs/tab_deep_dive.py`: UI Streamlit minimalista para seleção, visualização e exportação.
- `scripts/build_deep_dive_package.py`: empacotador do estudo Sellers vs Mercado Crédito.

## Prompt padrão para nova curadoria offline

Use este prompt no terminal/instância de análise antes de gerar novo pacote:

```text
Você é auditor sênior de FIDC e engenheiro Python no repositório local /fidc.

Objetivo: gerar um Deep Dive institucional, auditável e exportável para a carteira/fundos abaixo:
[listar carteira, CNPJs e nomes]

Leia todos os documentos locais disponíveis para esses fundos: regulamentos, consolidados, suplementos, atas, fatos relevantes, relatórios de rating, informes, demonstrações financeiras, XML/IME e auxiliares. Não assuma nada sem evidência documental. Para cada conclusão, preserve documento-fonte, página/seção/cláusula quando disponível, data do documento e lacunas.

Produza tabelas CSV com:
1. matriz comparativa principal: primeira coluna `Nome`, demais colunas = FIDCs/veículos;
2. emissões e cronogramas: classe/série, emissão, integralização, vencimento, remuneração, amortização, rating, fonte;
3. triggers/thresholds: critério, comparação, limite, vigência, monitorável via IME, fonte;
4. timeline de eventos relevantes;
5. matriz de lacunas e conflitos documentais.

Use apenas evidências locais e dados IME já existentes no repo/cache. Não invente dados. Se algo não for monitorável via IME, marque explicitamente.

Ao final, gere/atualize um pacote em `data/deep_dives/<deep_dive_id>/` com `manifest.json`, `tables/`, `evidence/` e `notes/`, compatível com `services.deep_dive_store`. Em seguida rode validação de carregamento e gere um PPTX de QA com `services.deep_dive_ppt_export.build_deep_dive_pptx_bytes`.
```

## Critérios de validação

- o pacote aparece na aba `Deep Dive`;
- a tabela mantém cabeçalho e colunas alinhados;
- campos ausentes aparecem como `—`;
- o PPTX abre sem erro e usa tabelas editáveis;
- nenhuma rotina do app busca dados externos para renderizar o Deep Dive.
