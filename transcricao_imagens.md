# Transcrição consolidada das imagens

Observação: as imagens têm bastante sobreposição; removi duplicatas e organizei o texto em ordem lógica. A imagem `IMG_6324.jpg` está muito desfocada, então marquei os pontos que não pude confirmar como `[ilegível]`.

```markdown
# Projeto: Dashboard Streamlit de Monitoramento de FIDCs (CVM/FNET) com cache em GitHub

## 1. Contexto e objetivo

Estou fazendo o **reverse-engineering** de um workbook Excel de monitoramento de FIDCs.
O workbook tem:

- **Uma aba por FIDC** (ex.: "ANGA I BV FGTS", "CLOUDWALK AI", "SUPPLIER MERCADO", "PRAVALER", etc.). Cada aba é uma **matriz de variáveis x competências mensais**:
  - **Coluna A** contém o **identificador técnico da variável** no padrão da CVM/FNET (ex.: `APLIC_ATIVO/VL_SOM_APLIC_ATIVO`, `CRED_EXISTE/VL_CRED_EXISTE_VENC_ADIMPL`, `PATRLIQ/VL_SOM_PATRLIQ`, `COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_30`, ...).
  - **Coluna B** contém o **rótulo amigável** (ex.: "1 - Ativo (R$)", "a) Direitos Creditórios com Aquisição Substancial dos Riscos e Benefícios", "IV - Patrimônio Líquido", ...).
  - **Colunas C..AC** (ou mais) contêm **valores mensais**, com cabeçalho na **linha 10** no formato `jan/24`, `fev/24`, ..., `mar/26`, `abr/26`, ...
- Linhas 1-3 trazem metadados do fundo: `LINK` (URL do gerenciador FNET com `cnpjFundo=...`), `NOME`, `CNPJ`.
- **Uma aba "Lista fundos"**: tabela consolidada do PL mensal por fundo (uso secundário).
- **Uma aba "Quadros"**: é o **painel consolidado por fundo** (um quadro por fundo) com indicadores derivados — é exatamente o que precisamos reproduzir no Streamlit.
- **Uma aba "AUX"**: dicionário auxiliar com:
  - lista de "FIDCs que monitoramos" (nome longo, nome curto da aba, CNPJ, gestora, administradora, custodiante);
  - mapeamento "rótulo -> linha de origem" usada para montar os quadros.

A ideia é: **o usuário escolhe (em uma carteira salva previamente) os FIDCs que quer ver, e o Streamlit renderiza, para cada um deles, um quadro idêntico ao da aba "Quadros" do Excel** — porém alimentado dinamicamente pela API da CVM/FNET (mesma fonte que já abastece o Excel hoje), com **cache versionado em GitHub** (Parquet/JSON commitado) para evitar refazer requisições toda vez.

> **Premissa de infraestrutura existente (não recriar do zero, apenas reutilizar):**
> Já existe um módulo Python interno (`fnet_client`) que baixa o "Informe Mensal" (Doc CVM) por CNPJ + competência (mês/ano) e retorna um `dict` com **todos os campos** do informe usando exatamente os mesmos identificadores que aparecem na coluna A das abas (ex.: `APLIC_ATIVO/VL_SOM_APLIC_ATIVO`). Se ele não existir no repo, **crie um stub `fnet_client.py`** com a assinatura abaixo e um TODO claro, mas **não invente** o parsing real.

```python
# fnet_client.py
def fetch_informe_mensal(cnpj: str, competencia: str) -> dict[str, float | int | str | None]:
    """
    competencia: 'YYYY-MM' (ex.: '2026-04').
    Retorna {variavel_id: valor} para TODAS as variáveis listadas em VARIAVEIS_FNET (ver abaixo).
    Endpoint base: https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}
    """
```

Crie um módulo `variaveis_fnet.py` com a lista canônica abaixo (extraída da coluna A das abas do workbook). **Não modifique os IDs** — eles batem 1:1 com o que a CVM/FNET retorna.

```python
# variaveis_fnet.py

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

    # d-i) Outros itens do Ativo
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
    ("NEGOC_DICRED_MES_VENC_ADIMPL/QT_DICRED_AQUIS", "VII.a.3.1) DC a vencer adimplentes - Qtd", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_VENC_ADIMPL/VL_DICRED_AQUIS", "VII.a.3.2) DC a vencer adimplentes - Valor", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_VENC_INAD/QT_DICRED_AQUIS", "VII.a.4.1) DC a vencer com inadimplentes - Qtd", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_VENC_INAD/VL_DICRED_AQUIS", "VII.a.4.2) DC a vencer com inadimplentes - Valor", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_INAD/QT_DICRED_AQUIS", "VII.a.5.1) DC Inadimplentes - Qtd", "NEGOCIOS_MES"),
    ("NEGOC_DICRED_MES_INAD/VL_DICRED_AQUIS", "VII.a.5.2) DC Inadimplentes - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/QT_DICRED_ALIEN", "VII.b) Alienações - Quantidade Total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/VL_DICRED_ALIEN", "VII.b) Alienações - Valor total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN/VL_DICRED_ALIEN_CONTAB", "VII.b) Alienações - Valor Contábil Total", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_CEDENT/QT_DICRED_ALIEN", "VII.b.1.1) Alienações ao Cedente - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_CEDENT/VL_DICRED_ALIEN", "VII.b.1.2) Alienações ao Cedente - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_CEDENT/VL_DICRED_ALIEN_CONTAB", "VII.b.1.3) Alienações ao Cedente - Valor Contábil", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_PREST/QT_DICRED_ALIEN", "VII.b.2.1) Alienações a Prestadores - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_PREST/VL_DICRED_ALIEN", "VII.b.2.2) Alienações a Prestadores - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_PREST/VL_DICRED_ALIEN_CONTAB", "VII.b.2.3) Alienações a Prestadores - Valor Contábil", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_TERCR/QT_DICRED_ALIEN", "VII.b.3.1) Alienações a Terceiros - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_TERCR/VL_DICRED_ALIEN", "VII.b.3.2) Alienações a Terceiros - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_TERCR/VL_DICRED_ALIEN_CONTAB", "VII.b.3.3) Alienações a Terceiros - Valor Contábil", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_SUBST/QT_DICRED_ALIEN", "VII.c.1) Substituições - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_SUBST/VL_DICRED_ALIEN", "VII.c.2) Substituições - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_SUBST/VL_DICRED_ALIEN_CONTAB", "VII.c.3) Substituições - Valor Contábil", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/QT_DICRED_ALIEN", "VII.d.1) Recompras - Qtd", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN", "VII.d.2) Recompras - Valor", "NEGOCIOS_MES"),
    ("DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN_CONTAB", "VII.d.3) Recompras - Valor Contábil", "NEGOCIOS_MES"),

    # ===== Cotas (séries/classes) =====
    ("DESC_SERIE_CLASSE_SENIOR/QT_COTAS", "Série Sênior - Qtd Cotas (descrição)", "COTAS"),
    ("DESC_SERIE_CLASSE_SENIOR/VL_COTAS", "Série Sênior - Valor Cotas (descrição)", "COTAS"),
    ("DESC_SERIE_CLASSE_SUBORD/QT_COTAS", "Série Subordinada - Qtd Cotas (descrição)", "COTAS"),
    ("DESC_SERIE_CLASSE_SUBORD/VL_COTAS", "Série Subordinada - Valor Cotas (descrição)", "COTAS"),
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

> **Observação importante**: a aba modelo possui também blocos extras para **CLASSE SR 1 / SUB 1 / MZ 1** (Qtd, VL_COTA, RENTABILIDADE) preenchidos manualmente quando o fundo tem **classe Mezanino**. Quando a API não retorna os campos de mezanino, **o app deve aceitar input manual** desses três campos (3 colunas x N meses) por fundo, persistindo em arquivo `manual_overrides/{cnpj}.json` no repo.

## 3. Indicadores DERIVADOS (cálculos do painel "Quadros")

Estes campos **NÃO vêm da API**, são fórmulas. Implemente em `metrics.py`:

| Indicador (label do quadro) | Fórmula (em termos dos IDs CVM) |
| --- | --- |
| PL (R$ MM) | `PATRLIQ/VL_SOM_PATRLIQ / 1e6` |
| Dir Cred | `CRED_EXISTE/VL_SOM_DICRED_AQUIS + DICRED/VL_DICRED` |
| Dir Cred / PL | `Dir Cred / PATRLIQ/VL_SOM_PATRLIQ` |
| Vencidos até 90 d | `COMPMT_DICRED_AQUIS/VL_INAD_VENC_30 + _31_60 + _61_90` (+ idem `SEM_AQUIS` quando aplicável) |
| Vencidos Acima 90 d | soma de `_91_120` até `_1080` em ambos blocos `COMPMT` |
| Vencidos Total | Vencidos até 90 d + Vencidos Acima 90 d |
| Vencidos / Crédito (3 variantes) | cada Vencidos dividido por `Dir Cred` |
| PDD (R$ MM) | `(CRED_EXISTE/VL_PROVIS_REDUC_RECUP + DICRED/VL_DICRED_PROVIS_REDUC_RECUP) / 1e6` |
| PDD / Crédito, / Venc 90+, / Venc Total | divisões diretas (com tratamento de divisão por zero -> `None`) |
| Recompras (R$ MM) | `DICRED_MES_ALIEN_RECOMP/VL_DICRED_ALIEN / 1e6` |
| Recompras / Crédito, / PL | divisões diretas |
| Cotas SR / PL - % | `CLASSE_SENIOR/VL_TOTAL / PATRLIQ/VL_SOM_PATRLIQ` (ou input manual mezanino) |
| Cotas MZ / PL - % | só quando mezanino existe (override manual ou inferência) |
| Cotas Sub / PL - % | `CLASSE_SUBORD/VL_TOTAL / PATRLIQ/VL_SOM_PATRLIQ` |
| Rentabilidade SR - % a.m. | `RENT_CLASSE_SENIOR/PR_APURADA` (já em %) |
| Rentabilidade Sub - % a.m. | `RENT_CLASSE_SUBORD/PR_APURADA` |
| Bloco "Vencidos por bucket" | replicar células `B26:B43` da aba "Quadros": faixas 1-30, 31-60, 61-90, 91-120, 121-150, 151-180, 181-360, acima 361 — em valor (R$ MM) e cumulativo / Crédito |

## 4. Carteira de FIDCs do usuário (input)

Crie `carteiras/{usuario}.yaml` no repo com a estrutura:

```yaml
nome: "Carteira Default"
fundos:
  - apelido: "ANGA I BV FGTS"
    nome_oficial: "FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS ANGÁ FGTS I - RESPONSABILIDADE LIMITADA"
    cnpj: "51957370000152"
    tem_mezanino: false
  - apelido: "ANGA II"
    nome_oficial: "[ilegível]"
    cnpj: "[ilegível]"
    tem_mezanino: false
  - apelido: "ANGA III"
    nome_oficial: "[ilegível]"
    cnpj: "[ilegível]"
    tem_mezanino: false
```

A lista inicial deve ser pré-populada com os fundos do workbook. Quando restante, o Streamlit deve permitir ao usuário marcar/desmarcar fundos e salvar a carteira `default` no GitHub repo. [Trecho parcialmente ilegível na imagem.]

## 5. Cache versionado em GitHub

Estrutura de cache no repo:

```text
cache/
  raw/{cnpj}/{competencia}.json
  parsed/{cnpj}.parquet
  metadata/[ilegível].json
```

**Política de cache**:

1. Ao requisitar `(cnpj, competencia)`:
   - se existe `cache/raw/{cnpj}/{competencia}.json` **e** `competencia` < mês corrente -> usa cache.
   - se `competencia` == mês corrente -> revalida (TTL 24h via mtime).
2. Após sucesso, atualiza `cache/parsed/{cnpj}.parquet` (DataFrame long).
3. Commit automático opcional (`git add cache/ && git commit -m "cache: refresh {cnpj} {competencia}" && git push`) atrás de flag `GIT_AUTOCOMMIT=true`.

**GitHub Action** (`.github/workflows/refresh.yml`): roda **mensalmente no dia 5 às 09:00 BRT**, executa `python -m refresh --carteira carteiras/default.yaml`, commita atualizações em `cache/` e abre PR automático se houver diff. Use `peter-evans/create-pull-request`.

## 6. Streamlit (`app.py`) - UX requerida

Layout:

1. **Sidebar**:
   - Selectbox de carteira (lê `carteiras/*.yaml`).
   - Multiselect de fundos da carteira (default = todos).
   - Date range (competência inicial e final, default últimos 24 meses).
   - Selectbox da **variável a destacar** (default `PATRLIQ/VL_SOM_PATRLIQ`, com label amigável). Esta seleção controla um **gráfico comparativo** entre todos os fundos selecionados.
   - Botão "Atualizar dados" (chama `fnet_client` ignorando cache).
   - Botão "Salvar carteira".

2. **Main**:
   - **Aba 1 — Comparativo**: gráfico de linhas (Plotly) com a variável selecionada para todos os fundos selecionados + tabela transposta (linhas = fundos, colunas = meses).
   - **Aba 2 — Quadros por fundo**: para cada fundo, renderizar **um quadro idêntico ao da aba "Quadros"** do Excel: header com nome + CNPJ + link FNET; tabela "Indicadores" (linhas da Seção 3) x competências; tabela "Vencidos buckets"; sparkline de PL e de Dir Cred/PL.
   - **Aba 3 — Dados brutos**: tabela com **todos** os IDs de `VARIAVEIS_FNET` x competências, com filtro de seção (ATIVO/SEGMENTO/PASSIVO/PL/COMPORTAMENTO/NEGÓCIOS/COTAS).
   - **Aba 4 — Overrides manuais**: editor (`st.data_editor`) para preencher classes Mezanino dos fundos com `tem_mezanino: true`.

Formatação:

- Valores monetários em R$ MM com separador `.` para milhares e `,` para decimais (locale pt-BR), 1 casa decimal.
- Percentuais com 2 casas.
- Células `None` / `NaN` -> exibir `-` (igual ao Excel).
- Headers das colunas no formato `mmm/aa` (ex.: `out/25`).

## 7. Stack técnica

- Python 3.11+
- `streamlit`, `pandas`, `pyarrow`, `plotly`, `pyyaml`, `requests`, `httpx`, `tenacity` (retry), `python-dateutil`.
- `pre-commit` com `ruff` + `black`.
- Testes unitários com `pytest` para `metrics.py` (use os valores do mês `out/25` da aba `ANGA I BV FGTS` como golden test: PL=672.084.551,63; Dir Cred=665.439.516,49; Dir Cred/PL=0,9901; PDD=53.548,38; Recompras=0; Cotas SR/PL=89,69%; Cotas Sub/PL=5,31%; Rent SR=1,01% a.m.; Rent Sub=1,34% a.m.).

## 8. Entregáveis

1. Código completo do app.
2. `README.md` com: como rodar local (`streamlit run app.py`), como configurar token GitHub para autocommit, como adicionar novo FIDC, e tabela explicando cada IND. derivado.
3. `requirements.txt` e `pyproject.toml`.
4. `tests/test_metrics.py` cobrindo no mínimo PL, Dir Cred/PL, PDD/Crédito, Vencidos buckets, Cotas SR/PL.
5. `tests/test_fnet_client.py` mockando a CVM (use `respx` ou `responses`).
6. `.github/workflows/refresh.yml` (cron mensal).
7. `.github/workflows/ci.yml` (lint + tests em PR).
8. Carteira-exemplo `carteiras/default.yaml` pré-populada com TODOS os fundos da minha lista atual:

`ANGA I BV FGTS, ANGA II FGTS, ANGA III BMG FGTS, ANGA MAIS FGTS, CLOUDWALK A I, CLOUDWALK AKIRA I CARTOES, CLOUDWALK AKIRA II CARTOES, CLOUDWALK KA I CARTOES, CLOUDWALK KA II CARTOES, SUPPLIER MERCADO, SUPPLIER EXCLUSIVO, SUPPLIER III, MERCADO LIVRE SELLERS, IBM LASTRO BRADESCO, IBM LASTRO BB, PAG SELLERS, PAG II, SUMUP ITAU, SUMUP SMART, QUATA FGTS, PRAVALER, CREDSYSTEM, IFOOD PAG I, IFOOD PAG III, VTK, ENDURANCE, FUTURO CONSIGNADO PUB II, FUTURO CONSIGNADO PUB IV, BV VEICULOS, MERCADO LIVRE OLIMPIA`

Para cada fundo, deixe `cnpj: "TODO"` quando você não tiver — extraia o CNPJ da célula B3 de cada aba (URL `cnpjFundo=...` em B1).

## 9. Restrições

- **Não recompute** valores que a API já entrega — apenas armazene; cálculos só nas métricas derivadas.
- **Não invente** IDs CVM diferentes de `VARIAVEIS_FNET`.
- **Tudo data-driven**: nada de hard-code de fundos no código (use os YAML/JSON do repo).
- Mensagens de UI em **pt-BR**.
- Logs estruturados (`json`) em `logs/`.

Pronto, agora gere o projeto inteiro.
```
