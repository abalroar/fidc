# Arquitetura proposta — Informe Mensal Estruturado (FIDC)

## 1) Diagnóstico do repositório atual

### Componentes já existentes (e úteis)
- `services/fundonet_client.py`: já implementa bootstrap de sessão, resolução de fundo, paginação da grade (`pesquisarGerenciadorDocumentosDados`) e download por `downloadDocumento?id=...`.
- `services/fundonet_service.py`: orquestra fluxo ponta-a-ponta (validação -> listar -> filtrar informe -> download -> parse -> dataset wide -> excel), com trilha de auditoria.
- `services/fundonet_parser.py`: faz flatten do XML para formato tabular (`conta_codigo`, `conta_descricao`, `conta_caminho`, `valor`).
- `services/fundonet_export.py`: pivota para formato largo e gera Excel.
- `app.py`: já expõe aba Streamlit para execução e download do resultado consolidado.
- `fundonet_fidc_pipeline.py`: CLI funcional, mas com lógica parcialmente duplicada em relação ao módulo `services/`.

### Gargalos observados
1. Duplicação de lógica entre `fundonet_fidc_pipeline.py` e `services/*` (risco de divergência).
2. Ausência de camada explícita de "fonte oficial CVM (dados abertos)" para fallback/primária.
3. Fluxo de export ainda focado em um único layout (wide), sem padrão de contrato de dados para múltiplos consumidores.
4. Não há um catálogo de metadados de execução (ex.: fonte usada, período efetivo, versão do parser) além da trilha básica.

---

## 2) Conclusão da investigação técnica (Fundos.NET)

Com base no comportamento capturado:
- O endpoint `/fnet/rb_...` é telemetria (Dynatrace/RUM), **não** API de negócio.
- O download individual está em `GET /fnet/publico/downloadDocumento?id=<id>`.
- O `id` do documento vem da listagem da grade (`pesquisarGerenciadorDocumentosDados`).
- O fluxo efetivo para automação é:

`resolver fundo -> listar documentos -> filtrar IME -> baixar XML -> parsear -> consolidar -> exportar`.

Isso já está aderente ao desenho da implementação em `services/`.

---

## 3) Arquitetura-alvo recomendada (robusta e funcional)

## 3.1 Princípio de fontes

Adotar arquitetura **híbrida com prioridade em dados oficiais**:

- **Fonte primária:** Dados Abertos CVM (ZIPs mensais de FIDC Informe Mensal), quando cobrir o escopo.
- **Fonte secundária:** Fundos.NET (download por documento) para lacunas, conferência e reprocessamento pontual.

Benefício: menor fragilidade operacional e menor exposição a bloqueios de sessão/captcha.

## 3.2 Camadas

1. **Ingestion Layer**
   - `OpenDataCVMClient` (novo): baixa/atualiza pacotes mensais oficiais.
   - `FundosNetClient` (existente): mantém extração por documento id.

2. **Domain Layer**
   - `InformeMensalService` como orquestrador central.
   - Estratégia de seleção de fonte: `source="open_data" | "fundonet" | "auto"`.

3. **Parsing Layer**
   - Parser XML único e versionado (manter `flatten_xml_contas` como base).
   - Contrato canônico de saída (tidy):
     - `cnpj_fundo`, `documento_id`, `data_referencia`, `conta_codigo`, `conta_descricao`, `conta_caminho`, `valor`, `fonte`.

4. **Consolidação Layer**
   - Dataset `tidy` (base analítica).
   - Dataset `wide` (consumo humano/Excel).

5. **Delivery Layer**
   - Streamlit: visualização + filtros + export.
   - Exportadores:
     - XLSX (usuário final)
     - CSV tidy (integração)
     - JSON de auditoria (observabilidade)

## 3.3 Contrato mínimo de execução

Cada execução deve gerar também `run_metadata.json` com:
- `run_id`, `timestamp_utc`, `cnpj_fundo`, `data_inicial`, `data_final`
- `source_selected`, `documents_found`, `documents_processed`, `documents_failed`
- `parser_version`, `app_version`

---

## 4) Próximos passos (ordem recomendada)

### Passo 1 — Consolidar código existente
- Tornar `fundonet_fidc_pipeline.py` um wrapper do `InformeMensalService`.
- Remover duplicação de cliente/parser/export no script legado.

### Passo 2 — Formalizar contratos de dados
- Padronizar saída `tidy` como contrato principal.
- Fazer export wide derivado sempre do tidy.

### Passo 3 — Adicionar camada Open Data CVM
- Implementar `OpenDataCVMClient` com ingestão mensal incremental.
- Estratégia `auto`: tenta Open Data primeiro; cai para Fundos.NET quando necessário.

### Passo 4 — Observabilidade operacional
- Persistir trilha de auditoria + metadata de execução.
- Expor no Streamlit contadores de sucesso/falha por documento.

### Passo 5 — Hardening
- Testes de contrato para parser XML com amostras reais.
- Retry/backoff por tipo de falha HTTP.
- Cache local por `documento_id` para evitar download repetido.

---

## 5) Blueprint técnico (MVP de produção)

1. Entrada: `cnpj_fundo`, `data_inicial`, `data_final`, `source=auto`.
2. Resolução de origem:
   - se Open Data cobre período -> ingestão por lote;
   - senão -> fluxo Fundos.NET por listagem+download.
3. Parse unificado para `tidy`.
4. Consolidação para `wide`.
5. Export:
   - `informes_tidy.csv`
   - `informes_wide.xlsx`
   - `audit_log.json`
   - `run_metadata.json`

---

## 6) Decisões práticas para o seu caso imediato

Para o fundo `33.254.370/0001-04`:
1. Validar cobertura no dataset oficial de FIDC Informe Mensal no período-alvo.
2. Se cobrir, usar Open Data como padrão da rotina automatizada.
3. Manter Fundos.NET como via complementar para:
   - conferência de documento específico;
   - reprocessamento de IDs pontuais;
   - troubleshooting quando houver divergência.

Isso preserva robustez de produção sem perder capacidade de auditoria por documento.
