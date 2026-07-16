# Prompt Codex — Dashboard de Monitoramento de FIDCs (Quadros)

## Objetivo

Adicionar ao app Streamlit existente um **painel de monitoramento comparativo de FIDCs** que reproduz
a aba "Quadros" do workbook Excel de referência — alimentado dinamicamente pela API da CVM/FNET,
aproveitando **toda a infra já existente** no repositório.

Leia o código antes de escrever qualquer linha. Entenda os módulos existentes e decida você mesmo
o melhor plano de execução: quais arquivos criar, quais estender, como integrar. Não reescreva o que
já funciona.

---

## 1. Infraestrutura existente — entenda antes de codificar

### 1.1 Cliente HTTP / download de IMEs

`services/fundonet_client.py` → classe `FundosNetClient`
- `listar_documentos_ime(cnpj)` → lista documentos "Informe Mensal Estruturado" por CNPJ
- `download_documento(doc_id)` → baixa o XML do informe

`services/fundonet_service.py` → classe `InformeMensalService`
- `run(cnpj, data_inicial, data_final)` → orquestra download + parse de todos os IMEs do período;
  retorna `InformeMensalResult` com `wide_csv_path` (CSV em formato largo: linhas = `tag_path`,
  colunas = competências `MM/YYYY`)

`services/fundonet_parser.py` → `parse_informe_mensal_xml(xml_bytes, doc_id)`
- O parser extrai todos os campos escalares do XML e os emite como `tag_path` no formato
  `DOC_ARQ/LISTA_INFORM/<BLOCO>/<TAG>` (ex.: `DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ`)
- O DataFrame "wide" final tem `tag_path` como índice e uma coluna por competência (`MM/YYYY`)

### 1.2 Cache local

`services/ime_loader.py` → `load_or_extract_informe(cnpj, data_inicial, data_final)`
- Cache local em `.cache/fundonet-ime/<hash>/` — evita re-downloads
- Use esta função como ponto de entrada para obter dados de qualquer FIDC

### 1.3 Portfólios / carteiras

`services/portfolio_store.py` → `PortfolioStore` (backends local JSON e GitHub)
- Persistência em `portfolios.json` (repo raiz); suporte a GitHub via token
- `PortfolioRecord` contém `name`, `funds: list[PortfolioFund]`; `PortfolioFund` tem `cnpj` e `display_name`
- Use esta estrutura para gerenciar as carteiras de FIDCs do usuário — **não criar YAML paralelo**

### 1.4 Dashboard e métricas existentes

`services/fundonet_dashboard.py` → `build_dashboard_data(wide_df, ...)`
- Já implementa séries de PL, aging buckets, emissões/resgates
- Usa o helper `_numeric_series_nullable(wide_lookup, competencias, tag_path)` para buscar valores por `tag_path`
- Consulte este arquivo para entender o padrão de acesso ao `wide_df` antes de criar código novo

### 1.5 App Streamlit

`app.py` → app multi-tab com `st.tabs()`; importa cada aba de `tabs/`
- Adicione a nova aba em `tabs/tab_fidc_monitoring.py` e registre em `app.py`

### 1.6 Schema / mapeamento de campos

`services/fundonet_schema.py` + `services/fundonet_schema_576.json`
- Dicionário de `tag_path` → descrição; usado pelo parser para enriquecer nomes de campo

---

## 2. O que precisa ser criado

### 2.1 `services/variaveis_fnet.py` — lista canônica de variáveis

Crie este módulo com a lista abaixo. **Não modifique os IDs** — eles são os identificadores
canônicos da CVM e precisam casar com os `tag_path` que o parser já produz.

> **Nota sobre `tag_path`**: o parser emite caminhos completos como
> `DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ`. Os IDs abaixo usam a forma curta
> `BLOCO/TAG` (ex.: `PATRLIQ/VL_SOM_PATRLIQ`). Você precisará resolver a correspondência —
> consulte `fundonet_schema_576.json` e os padrões em `fundonet_dashboard.py` para entender
> como o código existente já faz essa busca via sufixo. Siga o mesmo padrão.

```python
# services/variaveis_fnet.py

VARIAVEIS_FNET: list[tuple[str, str, str]] = [
    # (id_cvm, rótulo amigável, seção)

    # ===== I - Ativo =====
    ("APLIC_ATIVO/VL_SOM_APLIC_ATIVO", "1 - Ativo (R$)", "ATIVO"),
    ("APLIC_ATIVO/VL_DISPONIB", "1 - Disponibilidades", "ATIVO"),
    ("APLIC_ATIVO/VL_CARTEIRA", "2 - Carteira", "ATIVO"),

    # a) Direitos Creditórios COM aquisição substancial dos riscos
    ("CRED_EXISTE/VL_SOM_DICRED_AQUIS", "a) Direitos Creditórios com Aquisição Substancial dos Riscos e Benefícios", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_EXISTE_VENC_ADIMPL", "a.1) Créditos Existentes a Vencer e Adimplentes", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_EXISTE_VENC_INAD", "a.2) Créditos Existentes a Vencer com Parcelas Inadimplentes", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_TOTAL_VENC_INAD", "a.2.1) Valor Total das Parcelas Inadimplentes", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_EXISTE_INAD", "a.3) Créditos Existentes Inadimplentes", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_REFER_DICRED_PERFO", "a.4) Créditos Referentes a Direitos Creditórios a Performar", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_VENC_PEND", "a.5) Créditos vencidos e pendentes na cessão", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_ORIGEM_EMP_PROC_RECUP", "a.6) Créditos de Empresas em Recuperação Judicial/Extrajudicial", "ATIVO"),
    ("CRED_EXISTE/VL_DECOR_RECEIT_PUBLIC", "a.7) Créditos de receitas públicas (União/Estados/DF/Municípios)", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_ACAO_JUDIC", "a.8) Créditos de ações judiciais em curso", "ATIVO"),
    ("CRED_EXISTE/VL_CRED_CONST_JUR_FATRISC", "a.9) Créditos com fator preponderante de risco jurídico", "ATIVO"),
    ("CRED_EXISTE/VL_OUTROS_CRED", "a.10) Outros créditos (não enquadráveis ICVM 356, art. 2º, I)", "ATIVO"),
    ("CRED_EXISTE/VL_PROVIS_REDUC_RECUP", "a.11) Provisão para Redução no Valor de Recuperação (-)", "ATIVO"),

    # b) Direitos Creditórios SEM aquisição substancial dos riscos
    ("DICRED/VL_DICRED", "b) Direitos Creditórios sem Aquisição Substancial dos Riscos e Benefícios", "ATIVO"),
    ("DICRED/VL_DICRED_CEDENT", "b.1) Créditos Existentes a Vencer e Adimplentes", "ATIVO"),
    ("DICRED/VL_DICRED_EXISTE_VENC_INAD", "b.2) Créditos Existentes a Vencer com Parcelas Inadimplentes", "ATIVO"),
    ("DICRED/VL_DICRED_TOTAL_VENC_INAD", "b.2.1) Valor total das parcelas Inadimplentes", "ATIVO"),
    ("DICRED/VL_DICRED_EXISTE_INAD", "b.3) Créditos Existentes Inadimplentes", "ATIVO"),
    ("DICRED/VL_DICRED_REFER_DICRED_PERFO", "b.4) Créditos a Performar", "ATIVO"),
    ("DICRED/VL_DICRED_VENC_PEND", "b.5) Créditos vencidos e pendentes na cessão", "ATIVO"),
    ("DICRED/VL_DICRED_ORIGEM_EMP_PROC_RECUP", "b.6) Créditos de Empresas em Recuperação Judicial/Extrajudicial", "ATIVO"),
    ("DICRED/VL_DICRED_RECEIT_PUBLIC", "b.7) Créditos de receitas públicas", "ATIVO"),
    ("DICRED/VL_DICRED_ACAO_JUDIC", "b.8) Créditos de ações judiciais", "ATIVO"),
    ("DICRED/VL_DICRED_CONST_JUR_FATRISC", "b.9) Créditos com fator preponderante de risco jurídico", "ATIVO"),
    ("DICRED/VL_DICRED_OUTROS_CRED", "b.10) Outros créditos (não enquadráveis ICVM 356)", "ATIVO"),
    ("DICRED/VL_DICRED_PROVIS_REDUC_RECUP", "b.11) Provisão para Redução no Valor de Recuperação (-)", "ATIVO"),

    # c) Valores Mobiliários
    ("VALORES_MOB/VL_SOM_VALORES_MOB", "c) Valores Mobiliários", "ATIVO"),
    ("VALORES_MOB/VL_DEBT", "c.1) Debêntures", "ATIVO"),
    ("VALORES_MOB/VL_CRI", "c.2) CRI", "ATIVO"),
    ("VALORES_MOB/VL_NP_COMERC", "c.3) Notas Promissórias Comerciais", "ATIVO"),
    ("VALORES_MOB/VL_LETRA_FINANC", "c.4) Letras Financeiras", "ATIVO"),
    ("VALORES_MOB/VL_COTA_FDO_ICVM409", "c.5) Cotas de Fundos da ICVM 409", "ATIVO"),
    ("VALORES_MOB/VL_OUTRO_DICRED", "c.6) Outros", "ATIVO"),

    # d-j) Outros itens do Ativo
    ("APLIC_ATIVO/VL_TITPUB_FED", "d) Títulos Públicos Federais", "ATIVO"),
    ("APLIC_ATIVO/VL_CDB", "e) Certificados de Depósitos Bancários", "ATIVO"),
    ("APLIC_ATIVO/VL_APLIC_OPER_COMPSS", "f) Aplicações em Operações Compromissadas", "ATIVO"),
    ("APLIC_ATIVO/VL_ATIV_FINANC_RF", "g) Outros Ativos Financeiros de Renda Fixa", "ATIVO"),
    ("APLIC_ATIVO/VL_COTA_FIDC", "h) Cotas de FIDC", "ATIVO"),
    ("APLIC_ATIVO/VL_COTA_FIDC_NAO_PADRAO", "i) Cotas de FIDC Não Padronizados", "ATIVO"),
    ("APLIC_ATIVO/VL_CONTR_COMPRA_VENDA_PRESTC_FUTURA", "j) Warrants e Contratos de Compra/Venda Futura", "ATIVO"),
    ("APLIC_ATIVO/VL_PVS_DBT_CRI_NTA_PMS", "(-) Provisões sobre Debêntures, CRI, NP e Letras Financeiras", "ATIVO"),
    ("APLIC_ATIVO/VL_PVS_CTA_FND_INV", "(-) Provisões sobre Cotas de FIDC", "ATIVO"),
    ("APLIC_ATIVO/VL_PVS_OTR_ATV", "(-) Provisões sobre outros ativos", "ATIVO"),

    # 3 - Derivativos
    ("MERC_DERIVATIVO/VL_SOM_MERC_DERIVATIVO", "3 - Posições Mantidas em Mercados de Derivativos", "ATIVO"),
    ("MERC_DERIVATIVO/VL_MERC_TERMO_POS_COMPRD", "a) Mercado a Termo - Posições Compradas", "ATIVO"),
    ("MERC_DERIVATIVO/VL_MERC_OP_POS_TITUL", "b) Mercado de Opções - Posições Titulares", "ATIVO"),
    ("MERC_DERIVATIVO/VL_MERC_FUT_AJUST_POSIT", "c) Mercado Futuro - Ajustes Positivos", "ATIVO"),
    ("MERC_DERIVATIVO/VL_DIFER_SWAP_RECEB", "d) Diferencial de Swap a Receber", "ATIVO"),
    ("MERC_DERIVATIVO/VL_COBERT_PREST", "e) Coberturas Prestadas", "ATIVO"),
    ("MERC_DERIVATIVO/VL_DEPOS_MARGEM", "f) Depósitos de Margem", "ATIVO"),

    # 4 - Outros Ativos
    ("OUTROS_ATIVOS/VL_SOM_OUTROS_ATIVOS", "4 - Outros Ativos", "ATIVO"),
    ("OUTROS_ATIVOS/VL_OUTRO_VL_RECEB_CURPRZ", "a) Curto Prazo (<= 12 meses)", "ATIVO"),
    ("OUTROS_ATIVOS/VL_OUTRO_VL_RECEB_LPRAZO", "b) Longo Prazo (> 12 meses)", "ATIVO"),

    # ===== II - Carteira por Segmento =====
    ("CART_SEGMT/VL_SOM_CART_SEGMT", "II - Carteira por Segmento", "SEGMENTO"),
    ("CART_SEGMT/VL_IND", "a) Industrial", "SEGMENTO"),
    ("CART_SEGMT/VL_MERC_IMOBIL", "b) Mercado Imobiliário (não financeiro)", "SEGMENTO"),
    ("SEGMT_COMERC/VL_SOM_SEGMT_COMERC", "c) Comercial", "SEGMENTO"),
    ("SEGMT_COMERC/VL_COMERC", "c.1) Comercial", "SEGMENTO"),
    ("SEGMT_COMERC/VL_COMERC_VARJ", "c.2) Comercial - Varejo", "SEGMENTO"),
    ("SEGMT_COMERC/VL_ARREND_MERCNT", "c.3) Arrendamento Mercantil", "SEGMENTO"),
    ("SEGMT_SERV/VL_SOM_SEGMT_SERV", "d) Serviços", "SEGMENTO"),
    ("SEGMT_SERV/VL_SERV", "d.1) Serviços", "SEGMENTO"),
    ("SEGMT_SERV/VL_SERV_PUBLIC", "d.2) Serviços Públicos", "SEGMENTO"),
    ("SEGMT_SERV/VL_SERV_EDUC", "d.3) Serviços Educacionais", "SEGMENTO"),
    ("SEGMT_SERV/VL_SERV_ENTRETEN", "d.4) Entretenimento", "SEGMENTO"),
    ("CART_SEGMT/VL_AGRONEG", "e) Agronegócio", "SEGMENTO"),
    ("SEGMT_FINANC/VL_SOM_SEGMT_FINANC", "f) Financeiro", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_CRED_PESSOA", "f.1) Crédito Pessoal", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_CRED_PESSOA_CONSIG", "f.2) Crédito Pessoal Consignado", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_CRED_CORPOR", "f.3) Crédito Corporativo", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_MMARKET", "f.4) Middle Market", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_VEICL", "f.5) Veículos", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_IMOBIL_EMPSRL", "f.6) Carteira Imobiliária - Empresarial", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_IMOBIL_RESID", "f.7) Carteira Imobiliária - Residencial", "SEGMENTO"),
    ("SEGMT_FINANC/VL_FINANC_OUTRO", "f.8) Outros (Financeiro)", "SEGMENTO"),
    ("CART_SEGMT/VL_CART_CRED", "g) Cartão de Crédito", "SEGMENTO"),
    ("SEGMT_FACT/VL_SOM_SEGMT_FACT", "h) Factoring", "SEGMENTO"),
    ("SEGMT_FACT/VL_FACT_PESSOA", "h.1) Factoring - Pessoal", "SEGMENTO"),
    ("SEGMT_FACT/VL_FACT_CORPOR", "h.2) Factoring - Corporativo", "SEGMENTO"),
    ("SEGMT_SETOR_PUBLIC/VL_SOM_SEGMT_SETOR_PUBLIC", "i) Setor Público (ICVM 444)", "SEGMENTO"),
    ("SEGMT_SETOR_PUBLIC/VL_SETOR_PUBLIC_PRECAT", "i.1) Precatórios", "SEGMENTO"),
    ("SEGMT_SETOR_PUBLIC/VL_SETOR_PUBLIC_CRED_TRIBUT", "i.2) Créditos Tributários", "SEGMENTO"),
    ("SEGMT_SETOR_PUBLIC/VL_SETOR_PUBLIC_ROYA", "i.3) Royalties", "SEGMENTO"),
    ("SEGMT_SETOR_PUBLIC/VL_SETOR_PUBLIC_OUTRO", "i.4) Outros (Setor Público)", "SEGMENTO"),
    ("CART_SEGMT/VL_ACAO_JUDIC", "j) Ações Judiciais (ICVM 444)", "SEGMENTO"),
    ("CART_SEGMT/VL_PROPRD_MARCA_PATENT", "k) Propriedade Intelectual e Marcas & Patentes", "SEGMENTO"),

    # ===== III - Passivo =====
    ("PASSIV/VL_SOM_PASSIV", "III - Passivo", "PASSIVO"),
    ("PASSIV_VALORES/VL_SOM_PASSIV_VALORES", "a) Valores a pagar", "PASSIVO"),
    ("PASSIV_VALORES/VL_PGTO_CURPRZ", "a.1) Curto Prazo", "PASSIVO"),
    ("PASSIV_VALORES/VL_PGTO_LPRAZO", "a.2) Longo Prazo", "PASSIVO"),
    ("PASSIV_POSICOES/VL_SOM_PASSIV_POSICOES", "b) Posições Mantidas em Mercado de Derivativos", "PASSIVO"),
    ("PASSIV_POSICOES/VL_POS_MANT_VEND", "b.1) Mercado a termo (Posições vendidas)", "PASSIVO"),
    ("PASSIV_POSICOES/VL_POS_MANT_LANC", "b.2) Mercado de Opções (Posições Lançadas)", "PASSIVO"),
    ("PASSIV_POSICOES/VL_POS_MANT_AJT_FUT", "b.3) Mercado Futuro (Ajustes Negativos)", "PASSIVO"),
    ("PASSIV_POSICOES/VL_POS_MANT_SWAP_PAGAR", "b.4) Diferencial de Swap a Pagar", "PASSIVO"),

    # ===== IV - Patrimônio Líquido =====
    ("PATRLIQ/VL_SOM_PATRLIQ", "IV - Patrimônio Líquido", "PL"),
    ("PATRLIQ/VL_PATRIM_LIQ", "a) Valor do Patrimônio Líquido", "PL"),
    ("PATRLIQ/VL_PATRIM_LIQ_MEDIO", "b) Valor do PL Médio (últimos 3 meses)", "PL"),

    # ===== V - Comportamento da Carteira (COM aquisição) =====
    ("COMPMT_DICRED_AQUIS/VL_SOM_PRAZO_VENC", "V.a) Por Prazo de Vencimento (R$)", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_30", "V.a.1) Até 30 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_31_60", "V.a.2) De 31 a 60 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_61_90", "V.a.3) De 61 a 90 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_91_120", "V.a.4) De 91 a 120 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_121_150", "V.a.5) De 121 a 150 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_151_180", "V.a.6) De 151 a 180 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_181_360", "V.a.7) De 181 a 360 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_361_720", "V.a.8) De 361 a 720 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_721_1080", "V.a.9) De 721 a 1080 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_1080", "V.a.10) Acima de 1080 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_SOM_INAD_VENC", "V.b) Inadimplentes (Parcelas Inadimplentes, R$)", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_30", "V.b.1) Vencidos 1 a 30 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_31_60", "V.b.2) Vencidos 31 a 60 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_61_90", "V.b.3) Vencidos 61 a 90 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_91_120", "V.b.4) Vencidos 91 a 120 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_121_150", "V.b.5) Vencidos 121 a 150 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_151_180", "V.b.6) Vencidos 151 a 180 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_181_360", "V.b.7) Vencidos 181 a 360 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_361_720", "V.b.8) Vencidos 361 a 720 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_721_1080", "V.b.9) Vencidos 721 a 1080 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_INAD_VENC_1080", "V.b.10) Vencidos acima de 1080 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_SOM_PAGO_ANTCP", "V.c) Pagos Antecipadamente (R$)", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_30", "V.c.1) Pagos Antecipadamente 1 a 30 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_31_60", "V.c.2) 31 a 60 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_61_90", "V.c.3) 61 a 90 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_91_120", "V.c.4) 91 a 120 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_121_150", "V.c.5) 121 a 150 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_151_180", "V.c.6) 151 a 180 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_181_360", "V.c.7) 181 a 360 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_361_720", "V.c.8) 361 a 720 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_721_1080", "V.c.9) 721 a 1080 dias", "COMPORTAMENTO_AQUIS"),
    ("COMPMT_DICRED_AQUIS/VL_PAGO_ANTCP_1080", "V.c.10) acima de 1080 dias", "COMPORTAMENTO_AQUIS"),

    # ===== VI - Comportamento da Carteira (SEM aquisição) =====
    ("COMPMT_DICRED_SEM_AQUIS/VL_SOM_PRAZO_VENC", "VI.a) Por Prazo de Vencimento (R$)", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_30", "VI.a.1) Até 30 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_31_60", "VI.a.2) De 31 a 60 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_61_90", "VI.a.3) De 61 a 90 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_91_120", "VI.a.4) De 91 a 120 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_121_150", "VI.a.5) De 121 a 150 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_151_180", "VI.a.6) De 151 a 180 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_181_360", "VI.a.7) De 181 a 360 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_361_720", "VI.a.8) De 361 a 720 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_721_1080", "VI.a.9) De 721 a 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_1080", "VI.a.10) Acima de 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_SOM_INAD_VENC", "VI.b) Inadimplentes (R$)", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_30", "VI.b.1) 1 a 30 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_31_60", "VI.b.2) 31 a 60 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_61_90", "VI.b.3) 61 a 90 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_91_120", "VI.b.4) 91 a 120 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_121_150", "VI.b.5) 121 a 150 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_151_180", "VI.b.6) 151 a 180 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_181_360", "VI.b.7) 181 a 360 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_361_720", "VI.b.8) 361 a 720 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_721_1080", "VI.b.9) 721 a 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_1080", "VI.b.10) acima de 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_SOM_PAGO_ANTCP", "VI.c) Pagos Antecipadamente (R$)", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_30", "VI.c.1) 1 a 30 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_31_60", "VI.c.2) 31 a 60 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_61_90", "VI.c.3) 61 a 90 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_91_120", "VI.c.4) 91 a 120 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_121_150", "VI.c.5) 121 a 150 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_151_180", "VI.c.6) 151 a 180 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_181_360", "VI.c.7) 181 a 360 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_361_720", "VI.c.8) 361 a 720 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_721_1080", "VI.c.9) 721 a 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),
    ("COMPMT_DICRED_SEM_AQUIS/VL_PAGO_ANTCP_1080", "VI.c.10) acima de 1080 dias", "COMPORTAMENTO_SEM_AQUIS"),

    # ===== VII - Negócios com Direitos Creditórios no mês =====
    ("AQUISICOES/QT_DICRED_AQUIS", "VII.a) Aquisições - Quantidade Total", "NEGOCIOS_MES"),
    ("AQUISICOES/VL_DICRED_AQUIS", "VII.a) Aquisições - Valor total", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_AQUIS/QT_DICRED_AQUIS", "VII.a.1.1) DC com Aquisição - Quantidade", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_AQUIS/VL_DICRED_AQUIS", "VII.a.1.2) DC com Aquisição - Valor", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_SEM_AQUIS/QT_DICRED_AQUIS", "VII.a.2.1) DC sem Aquisição - Quantidade", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_SEM_AQUIS/VL_DICRED_AQUIS", "VII.a.2.2) DC sem Aquisição - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/QT_DICRED_ALIEN", "VII.b) Alienações - Quantidade Total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/VL_DICRED_ALIEN", "VII.b) Alienações - Valor total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/VL_DICRED_ALIEN_CONTAB", "VII.b) Alienações - Valor Contábil Total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/QT_DICRED_ALIEN", "VII.d.1) Recompras - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN", "VII.d.2) Recompras - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN_CONTAB", "VII.d.3) Recompras - Valor Contábil", "NEGOCIOS_MES"),

    # ===== Cotas (séries/classes) =====
    ("RENT_CLASSE_SENIOR/PR_APURADA", "Rentabilidade Sênior apurada (% a.m.)", "COTAS"),
    ("RENT_CLASSE_SUBORD/PR_APURADA", "Rentabilidade Subordinada apurada (% a.m.)", "COTAS"),
    ("CLASSE_SENIOR/QT_COTAS", "Classe Sênior - Qtd Cotas", "COTAS"),
    ("CLASSE_SENIOR/VL_COTAS", "Classe Sênior - Valor Cotas", "COTAS"),
    ("CLASSE_SUBORD/QT_COTAS", "Classe Subordinada - Qtd Cotas", "COTAS"),
    ("CLASSE_SUBORD/VL_COTAS", "Classe Subordinada - Valor Cotas", "COTAS"),
    ("CLASSE_SENIOR/VL_COTA", "Classe Sênior - Valor por Cota", "COTAS"),
    ("CLASSE_SENIOR/VL_TOTAL", "Classe Sênior - Valor Total", "COTAS"),
    ("CLASSE_SUBORD/VL_COTA", "Classe Subordinada - Valor por Cota", "COTAS"),
    ("CLASSE_SUBORD/VL_TOTAL", "Classe Subordinada - Valor Total", "COTAS"),
]
```

> **Atenção sobre a busca por `tag_path`**: o parser produz caminhos completos como
> `DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ`. A forma curta `PATRLIQ/VL_PATRIM_LIQ` é
> um sufixo. O código em `fundonet_dashboard.py` já usa busca por sufixo via
> `_numeric_series_nullable`. Você pode e deve usar a mesma estratégia — ou criar uma função
> `resolve_tag_path(short_id, wide_df) -> str | None` em `variaveis_fnet.py` que encontra
> a coluna correta no `wide_df`. Escolha a abordagem mais limpa dado o código existente.

---

### 2.2 `services/monitoring_metrics.py` — indicadores derivados

Implemente as funções de cálculo dos indicadores do painel. Recebem um `wide_df` (índice =
`tag_path` completo, colunas = competências) e uma lista de competências; retornam um
`pd.DataFrame` com linhas = indicadores e colunas = competências.

| Indicador (label do painel) | Fórmula |
|---|---|
| PL (R$ MM) | `PATRLIQ/VL_SOM_PATRLIQ ÷ 1e6` |
| Dir Cred (R$ MM) | `CRED_EXISTE/VL_SOM_DICRED_AQUIS + DICRED/VL_DICRED` |
| Dir Cred / PL | `Dir Cred ÷ PATRLIQ/VL_SOM_PATRLIQ` |
| Vencidos ≤ 90 d (R$ MM) | soma de `VL_INAD_VENC_30 + _31_60 + _61_90` nos blocos `COMPMT_DICRED_AQUIS` e `COMPMT_DICRED_SEM_AQUIS` |
| Vencidos > 90 d (R$ MM) | soma de `_91_120` até `_1080` nos mesmos blocos |
| Vencidos Total (R$ MM) | Vencidos ≤ 90 d + Vencidos > 90 d |
| Vencidos ≤ 90 d / Crédito | Vencidos ≤ 90 d ÷ Dir Cred |
| Vencidos > 90 d / Crédito | Vencidos > 90 d ÷ Dir Cred |
| Vencidos Total / Crédito | Vencidos Total ÷ Dir Cred |
| PDD (R$ MM) | `(CRED_EXISTE/VL_PROVIS_REDUC_RECUP + DICRED/VL_DICRED_PROVIS_REDUC_RECUP) ÷ 1e6` |
| PDD / Crédito | PDD ÷ Dir Cred |
| PDD / Venc > 90 d | PDD ÷ Vencidos > 90 d |
| PDD / Venc Total | PDD ÷ Vencidos Total |
| Recompras (R$ MM) | `DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN ÷ 1e6` |
| Recompras / Crédito | Recompras ÷ Dir Cred |
| Recompras / PL | Recompras ÷ PL |
| Cotas SR / PL % | `CLASSE_SENIOR/VL_TOTAL ÷ PATRLIQ/VL_SOM_PATRLIQ` |
| Cotas MZ / PL % | campo mezanino (override manual) ÷ PL — omitir se não houver override |
| Cotas Sub / PL % | `CLASSE_SUBORD/VL_TOTAL ÷ PATRLIQ/VL_SOM_PATRLIQ` |
| Rentabilidade SR % a.m. | `RENT_CLASSE_SENIOR/PR_APURADA` (já em %) |
| Rentabilidade Sub % a.m. | `RENT_CLASSE_SUBORD/PR_APURADA` |
| Vencidos por bucket (bloco Aging) | faixas 1-30, 31-60, 61-90, 91-120, 121-150, 151-180, 181-360, acima 361 — em R$ MM e cumulativo / Crédito |

Regras obrigatórias:
- Divisão por zero → retorna `None` / `pd.NA` (não `NaN`, não lança exceção)
- **Não compute** campos que a API já entrega; calcule apenas os indicadores derivados acima
- **Não invente** IDs CVM além dos listados em `VARIAVEIS_FNET`

**Golden test** (valores do mês `10/2025` do FIDC "ANGA I BV FGTS"):

| Indicador | Valor esperado |
|---|---|
| PL | R$ 672.084.551,63 |
| Dir Cred / PL | 0,9901 |
| PDD (R$ MM) | 53.548,38 / 1e6 |
| Recompras | 0 |
| Cotas SR / PL | 89,69 % |
| Cotas Sub / PL | 5,31 % |
| Rent SR | 1,01 % a.m. |
| Rent Sub | 1,34 % a.m. |

Escreva testes em `tests/test_monitoring_metrics.py` cobrindo no mínimo: PL, Dir Cred/PL,
PDD/Crédito, Vencidos buckets, Cotas SR/PL. Use fixture de dados sintéticos — não dependa
de rede ou de arquivo real.

---

### 2.3 Mezanino — overrides manuais

Quando um FIDC tem classe Mezanino, a API pode não retornar os campos. Persista os overrides
em `manual_overrides/{cnpj}.json` (crie o diretório se não existir). Estrutura sugerida:

```json
{
  "cnpj": "...",
  "competencias": {
    "10/2025": { "vl_total_mz": 12345678.90, "rent_mz": 1.02 }
  }
}
```

Exponha no `monitoring_metrics.py` uma função para ler e mesclar esses overrides com o
`wide_df` antes de calcular os indicadores. Persista edições feitas pelo usuário no
Streamlit via `st.data_editor`.

---

### 2.4 `tabs/tab_fidc_monitoring.py` — nova aba Streamlit

#### Fluxo de dados

1. Usuário seleciona carteira (lê `portfolios.json` via `PortfolioStore`) e período
2. Para cada FIDC da carteira: chama `load_or_extract_informe` (`ime_loader.py`) → obtém
   `wide_df`
3. Calcula indicadores via `monitoring_metrics.py`
4. Renderiza o painel

#### Layout da aba (4 sub-abas internas)

**Sub-aba 1 — Comparativo**
- Selectbox: variável a comparar (padrão: `PATRLIQ/VL_SOM_PATRLIQ`) — label amigável da
  `VARIAVEIS_FNET`
- Gráfico de linhas (Plotly ou Altair — use o mesmo que já está no projeto) com a série da
  variável selecionada para cada FIDC
- Tabela transposta: linhas = fundos, colunas = competências

**Sub-aba 2 — Quadros por fundo**

Para cada FIDC da carteira, renderizar um bloco com:
- Header: `{display_name}` · CNPJ formatado · link FNET
  (`https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}`)
- **Tabela de Indicadores** (linhas = indicadores da seção 2.2, colunas = competências)
- **Tabela Aging** (linhas = buckets de inadimplência, colunas = competências)
- Sparkline de PL e de Dir Cred/PL ao lado do header

**Sub-aba 3 — Dados brutos**
- Todos os IDs de `VARIAVEIS_FNET` × competências, com filtro de seção
  (ATIVO / SEGMENTO / PASSIVO / PL / COMPORTAMENTO / NEGOCIOS_MES / COTAS)

**Sub-aba 4 — Overrides de Mezanino**
- `st.data_editor` para fundos com mezanino (filtra da carteira)
- Salva em `manual_overrides/{cnpj}.json`

#### Formatação

- Valores monetários: R$ MM com 1 decimal, separador milhares `.`, decimal `,` (locale pt-BR)
- Percentuais: 2 decimais
- `None` / `NaN` → exibir `-`
- Cabeçalho das colunas: `mmm/aa` (ex.: `out/25`)

---

## 3. Restrições

- **Não reescreva** `FundosNetClient`, `InformeMensalService`, `ime_loader`, `portfolio_store`
  — apenas importe e use
- **Não duplique** lógica já presente em `fundonet_dashboard.py`; se necessário, extraia para
  função compartilhada
- **Tudo data-driven**: nenhum CNPJ ou nome de fundo hard-coded no código Python — use
  `portfolios.json`
- UI em **pt-BR**
- Siga o estilo de código existente: `from __future__ import annotations`, type hints, sem
  dependências externas além das já em `requirements.txt` (adicione apenas se estritamente
  necessário e justifique no commit)
- Não crie `README.md` nem `pyproject.toml` — já existem ou estão fora do escopo desta tarefa

---

## 4. Entregáveis mínimos

1. `services/variaveis_fnet.py`
2. `services/monitoring_metrics.py`
3. `tabs/tab_fidc_monitoring.py`
4. `manual_overrides/.gitkeep` (cria o diretório)
5. `tests/test_monitoring_metrics.py`
6. Registro da nova aba em `app.py`

---

## 5. Referência visual — o que existe hoje e como melhorar

As três imagens a seguir descrevem a saída atual (Excel/PPT) que deve ser reproduzida e superada no Streamlit. Leia cada painel com atenção — o objetivo é **mais bonito, mais simples, mais visual e mais intuitivo** que a versão Excel, não uma cópia pixel a pixel.

---

### Painel A — "Quadros por fundo" (aba Excel "Quadros")

**O que é:** uma aba do Excel com um bloco por FIDC monitorado. Cada bloco tem:

#### Seção 1 — Tabela de indicadores (linhas × competências)

Matriz com indicadores nas linhas e meses nas colunas (jan/24 → mês atual). Linhas:

```
[cabeçalho escuro]  R$ MM    jan/24  fev/24  ...  out/25  nov/25  ...
PL (R$ MM)                   263,1   333,7       570,4   413,3
Dir Cred / PL (%)             90,5%   0,0%        ...
Dir Cred (R$ MM)             238,1   245,6
Vencidos até 90 d (R$ MM)     1,7     1,8
Vencidos Acima 90 d (R$ MM)   1,3     1,3
Vencidos Total (R$ MM)        3,0     3,4
Vencidos até 90d / Crédito    0,7%    0,8%
Vencidos Acima 90d / Crédito  0,5%    0,5%
Vencidos Total / Crédito      1,3%    1,3%
PDD (R$ MM)                  10,7    11,7
PDD / Crédito (%)             4,5%    4,8%
PDD / Vencidos Total (%)    352,3%  359,2%
PDD / Vencidos > 90d (%)    ...
Cotas SR / PL (%)             70%     70%
Cotas MZ / PL (%)              8%      8%   ← só quando fundo tem mezanino
Cotas Sub / PL (%)            20%     15%
Rentabilidade SR % a.m.       1,1%    1,0%
Rentabilidade Sub % a.m.      1,3%    1,2%
```

#### Seção 2 — Aging buckets (duas sub-tabelas)

**Sub-tabela "Vencidos R$ MM"** (valores absolutos por faixa de atraso):

```
[cabeçalho escuro]  Vencidos    jan/24  fev/24  ...
Vencidos 1 - 30d               0,90    1,04
Vencidos 31 - 60d              0,47    0,38
Vencidos 61 - 90d              0,37    0,38
Vencidos 91 - 120d             0,32    0,38
Vencidos 121 - 150d            0,25    0,27
Vencidos 151 - 180d            0,19    0,21
Vencidos 181 - 360d            0,54    0,52
Vencidos acima 361d            0,00    0,00
```

**Sub-tabela "Vencidos / Crédito por bucket"** (cada bucket como % da carteira de crédito):

```
[cabeçalho vermelho]  Vencidos / Crédito   jan/24  fev/24  ...
1 - 30d                                     1,3%    1,3%
31 - 60d                                    0,9%    0,9%
61 - 90d                                    0,7%    0,7%
91 - 120d                                   0,5%    0,5%
121 - 150d                                  0,4%    0,4%
151 - 180d                                  0,3%    0,3%
181 - 360d                                  0,2%    0,2%
acima 361d                                  0,0%    0,0%
```

**Problema desta versão:** é uma tabela estática, sem contexto visual, sem destaque de
tendências, sem hierarquia clara entre indicadores de mesma família.

---

### Painel B — "Consolidado" (aba Excel "Lista fundos")

**O que é:** uma única tabela com todos os FIDCs nas linhas e competências nas colunas,
mostrando apenas o PL (R$) de cada fundo por mês. Exemplo:

```
              Consolidado
PL (R$ MM)    mai/25        jun/25        jul/25      ... mar/26
ANGA I BV FGTS     551.614.005   538.535.237   526.362.725
ANGA II FGTS       353.296.587   344.527.607   336.437.556
ANGA III BMG FGTS 1.227.449.316 1.200.135.105 1.173.368.045
ANGA MAIS FGTS      98.052.105    96.062.829    93.918.695
CLOUDWALK A I        2.694.740...
CLOUDWALK AKIRA I    516.673.482   516.663.178
...
PRAVALER           389.517.398   383.315.471
CREDSYSTEM       1.128.540.601 1.162.969.144
...
```

**Problema:** tabela pura, sem sparklines, sem heatmap, sem ordenação por variação.

---

### Painel C — "Visão gráfica por fundo" (PPT de comitê)

**O que é:** slide com 4 gráficos para um único FIDC, mostrando evolução temporal dos
principais indicadores. Cada gráfico é um combo **barra + linha com eixo Y duplo**:

1. **"Evolução PL e Nível Subordinação"**
   - Barras vermelhas: PL (R$ MM), eixo esquerdo (0–500)
   - Linha preta: Cotas Sub / PL %, eixo direito (0%–25%)
   - X: últimos ~9 meses (mai/25–jan/26)

2. **"Evolução Dir Cred e Vencidos"**
   - Barras vermelhas: Dir Cred (R$ MM), eixo esquerdo (0–400)
   - Linha cinza: Vencidos até 90d / Crédito, eixo direito (0%–1%)
   - Linha preta: Vencidos Acima 90d / Crédito, eixo direito
   - X: mesma janela temporal

3. **"Provisão e Cobertura"**
   - Barras vermelhas: PDD (R$ MM), eixo esquerdo (0–25)
   - Linha: PDD / Vencidos Total (%), eixo direito (300%–400%)
   - X: mesma janela

4. **"Rentabilidade das Cotas"**
   - Duas linhas: Rentabilidade SR % a.m. e Rentabilidade Sub % a.m.
   - Janela mais longa (jan/24 em diante), captura toda a série histórica
   - Eixo Y esquerdo: 0%–2%, direito: escala maior para volatilidade Sub

**Problema:** visualmente aceitável mas limitado — sem interatividade, sem drill-down,
sem hover com valores, cores genéricas (vermelho + preto), sem separação clara entre
"visão atual" e série histórica.

---

### Como o Streamlit deve melhorar sobre esses painéis

A nova aba deve ter **duas visões** que o usuário alterna:

#### Visão 1 — "Carteira" (equivalente ao Painel B, mas melhor)

- **Heatmap + tabela** de uma métrica selecionável (padrão: PL) para todos os FIDCs
  da carteira. Células coloridas por intensidade (azul claro → azul escuro) indicam
  magnitude do valor. O fundo usa a escala de 0 → máximo da carteira.
- **Variação MoM** (coluna extra ao lado de cada mês, em %, com cor verde/vermelho).
- **Sparklines inline** na última coluna (mini-gráfico por linha de fundo).
- Selectbox para trocar a métrica visualizada: PL, Dir Cred, Vencidos/Crédito, etc.
- Ordenação por clique de coluna.

#### Visão 2 — "Por fundo" (equivalente ao Painel A + C, melhor)

Para cada FIDC selecionado, renderizar um **card expansível** (`st.expander`) contendo:

**Topo do card:**
```
[Nome do FIDC]                      CNPJ: XX.XXX.XXX/0001-XX   [🔗 FNET]
Competência mais recente: out/25    PL atual: R$ 570,4 MM
```

**Bloco de KPIs rápidos** (4–6 métricas do mês mais recente em pills/cards):

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PL           │ │ Dir Cred/PL  │ │ Venc>90d/Cred│ │ PDD/Cred     │
│ R$ 570,4 MM  │ │ 99,0 %       │ │ 0,5 %        │ │ 4,8 %        │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
┌──────────────┐ ┌──────────────┐
│ Cotas SR/PL  │ │ Rent SR a.m. │
│ 89,7 %       │ │ 1,01 %       │
└──────────────┘ └──────────────┘
```

**4 gráficos em 2×2** (replicar Painel C com melhorias):
- Cada gráfico: barra + linha com eixo duplo, hover com tooltip mostrando valores exatos,
  paleta consistente com o app existente (vermelho `#ff5a00` para barras, linhas em `#111`
  e `#6e6e6e`)
- Os 4 gráficos do Painel C, mas com período selecionável via slider/radio na sidebar

**Tabela de indicadores colapsável** (equivalente à Seção 1 do Painel A):
- Expandida por padrão para os últimos 12 meses
- Linhas agrupadas por família: [PL] [Crédito] [Inadimplência] [PDD] [Cotas] [Rentabilidade]
- Cabeçalho de grupo em cinza claro; linhas alternadas branco/quase-branco
- Células `None`/`NaN` → `-`; percentuais com 2 decimais; R$ MM com 1 decimal

**Tabela de aging colapsável** (equivalente à Seção 2 do Painel A):
- Acima: valores absolutos R$ MM por bucket, colunas = meses
- Abaixo (ou aba interna): % de crédito por bucket
- **Melhoria sobre o Excel**: adicionar um stacked bar chart do aging do mês mais recente
  (barras horizontais, uma por bucket, comprimento = % do crédito) — visualiza
  instantaneamente se a inadimplência está concentrada em dívidas recentes ou antigas

---

### Princípios de design a seguir

1. **Hierarquia clara**: KPI pills no topo (leitura em 5 segundos), gráficos no meio
   (tendências), tabelas detalhadas colapsadas embaixo (drill-down).
2. **Uma cor primária**: use `#ff5a00` (laranja/vermelho do app) para barras e destaques.
   Linhas secundárias em `#111111` e `#6e6e6e`. Fundo sempre branco.
3. **Sem poluição visual**: não mostrar todos os indicadores ao mesmo tempo. Agrupe com
   `st.expander`. Não use bordas pesadas em tabelas — separe por espaçamento e cor de fundo.
4. **Números formatados pt-BR**: `1.234,5 MM` e `12,34%` — nunca formato inglês.
5. **Responsivo ao período**: qualquer mudança no seletor de período (sidebar) recomputa
   tudo sem recarregar a página.
