# -*- coding: utf-8 -*-
"""Elegibilidade, concentracao, prazos/WAM, waterfall, subordinada e PDD."""

ND = "n/d"

# ============================================================ 03_Elegibilidade
ELEGIBILIDADE_COLS = [
    "veiculo_id", "taxa_da_CCB", "moeda_do_pagamento", "cap_individual_pct_patrimonio_separado",
    "taxa_retorno_minima_pro_forma", "wam_max_dias", "prazo_max_recebivel_dias",
    "prazo_max_recebivel_meses", "adimplencia_na_cessao", "atraso_na_cessao",
    "amortizacao_mensal_sem_balao", "idade_maxima_devedor_PF", "constituicao_minima_PJ_anos",
    "enquadramento_PJ", "carencia_max_dias", "valor_presente_max_PF_R", "valor_presente_max_PJ_R",
    "seasoning_minimo_meses", "tipos_de_ativo", "preco_max_aquisicao_pct_saldo",
    "quem_atesta_elegibilidade", "restricao_geografica", "restricao_score",
    "vedacoes_expressas", "redacao_literal", "fonte_id", "status",
]

ELEGIBILIDADE = [
    # ---------------- CRIs (redacao literal das laminas) ----------------
    ("CRI-I", "Pre-fixada", ND, "0,10% do Patrimonio Separado (mais cap de 1% para os 10 maiores devedores)",
     "Taxa de Retorno pro forma >= Taxa Media Minima de Retorno (21,5% a.a.)", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso", ND,
     "71 anos na emissao da CCB", "2", "Nao exigido", "185", "350000", "600000",
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND,
     "Emissora, com base nas informacoes prestadas pelos Cedentes", ND, ND,
     "Inadimplencia do devedor; recebivel em atraso; credito nao performado",
     "'o valor dos Direitos Creditorios Imobiliarios devidos por um Devedor individualmente nao devera representar mais de 0,10% do Patrimonio Separado da Emissao; e o grupo dos 10 maiores Devedores nao podera ser devedor de Direitos Creditorios Imobiliarios cujo valor supere 1% do Patrimonio Separado da Emissao'",
     "ANX-LAM-K1; ANX-PRO-K1", "Documentado"),

    ("CRI-II", "Pre-fixada", ND, "0,10% do Patrimonio Separado",
     "Taxa de Retorno pro forma >= Taxa Media Minima de Retorno (21% a.a.)", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso", ND,
     "71 anos na emissao da CCB", "2", "Nao exigido", "185", "350000", ND,
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND,
     "Emissora, com base nas informacoes prestadas pelos Cedentes", ND, ND,
     "Inadimplencia do devedor; recebivel em atraso; credito nao performado",
     "'Taxa Media Minima de Retorno: 21% (vinte e um por cento) a.a.'",
     "ANX-PRO-K2; ANX-TS2-K2; ANX-DECK", "Documentado"),

    ("CRI-III", "Pre-fixada", ND, "0,10% do Patrimonio Separado",
     "Taxa de Retorno pro forma >= Taxa Media Minima de Retorno", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso", ND,
     "71 anos na emissao da CCB", "2", "Nao exigido", "185", "350000", "700000",
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND,
     "Emissora, com base nas informacoes prestadas pelos Cedentes", ND, ND,
     "Inadimplencia do devedor; recebivel em atraso; credito nao performado",
     "'considerada pro forma a cessao pretendida, a Media Ponderada dos Prazos de Vencimento das CCBs integrantes do Patrimonio Separado da Emissao devera ser de no maximo 2.000 (dois mil) dias'",
     "ANX-LAM-K3", "Documentado"),

    ("CRI-IV", "Pre-fixada", ND, "0,25% caindo para 0,17% do Patrimonio Separado (escalonado)",
     ND, "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso", ND,
     "71 anos na emissao da CCB", "2", ND, "185", "350000", ND,
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND,
     "Emissora", ND, ND, "Inadimplencia do devedor; recebivel em atraso; credito nao performado",
     "Redacao literal indisponivel: a lamina da 4a emissao nao esta no acervo; parametros vindos do deck",
     "ANX-DECK", "Documentado"),

    ("CRI-V", "Pre-fixada", "Reais (moeda brasileira), explicito",
     "0,15% do Patrimonio Separado ate 470.600 quantidades integralizadas; 0,07% a partir de 750.000 quantidades",
     "Taxa de Retorno pro forma >= Taxa Media Minima de Retorno, medida sobre o valor presente da cessao",
     "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso",
     "Exigido: principal e juros em parcelas mensais, sem parcela final superior as demais",
     "71 anos na emissao da CCB", "2", "Resolucao CMN 5.118", "185", "350000", "700000",
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND,
     "Emissora, com envio eletronico de dados pela Gestora do Cedente Fundo e pela Solfacil, e com as informacoes da instituicao custodiante do respectivo cedente",
     ND, ND,
     "Inadimplencia do devedor; recebivel em atraso; parcela balao final; PJ fora da CMN 5.118; credito nao performado",
     "'o Direito Creditorio Imobiliario seja um financiamento que preve o pagamento do principal e dos juros em parcelas mensais, sem a existencia de parcela final em montante superior as demais parcelas'",
     "ANX-LAM-V174", "Documentado"),

    ("CRI-VI", "Pre-fixada", ND, "0,11% do Patrimonio Separado", ND, "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebivel em atraso", ND,
     "71 anos na emissao da CCB", "2", ND, "185", "350000", ND,
     ND, "CCB pre-fixada com destinacao a Sistema Solar", ND, "Emissora", ND, ND,
     "Inadimplencia do devedor; recebivel em atraso; credito nao performado",
     "Redacao literal indisponivel: a lamina da 177a emissao nao esta no acervo; parametros vindos do deck",
     "ANX-DECK", "Documentado"),

    # ---------------- FIDCs ----------------
    ("FIDC-I", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, "2135", "3836", "126.1",
     "Nao explicita na lista de criterios", ND, ND, ND, ND, ND, ND, "201000", "502000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND, "Redacao menos protetiva que a dos CRI",
     ND, "ANX-DECK", "Documentado"),
    ("FIDC-II", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, "2400",
     "2340 (pre) / 4500 (pos)", "76,9 / 147,9", "Exigida", ND, ND, ND, ND, ND, "180", "300000", "500000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND, ND, ND, "ANX-DECK", "Documentado"),
    ("FIDC-III", "Fixa", ND, "0,10% (cap individual); 1% para os 10 maiores", ND, "2000", "3845", "126.3",
     "Exigida", ND, ND, ND, ND, ND, "185", "350000", "600000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND,
     "Criterio proximo ao do CRI inicial", ND, "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Fixa", ND, "20% (cap individual)", ND, ND, ND, ND, "Exigida", ND, ND, ND, ND, ND, ND, ND, ND,
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND,
     "Mais permissivo em concentracao entre os sete fundos", ND, "ANX-DECK", "Documentado"),
    ("FIDC-V", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, ND, "4760", "156.5",
     "Exigida", ND, ND, ND, ND, ND, "185 / 366", "500000", "700000",
     ND, "CCB + CPR-F", ND, "Gestora/Administrador", ND, ND,
     "Ativo e ticket mais amplos; unico fundo que admite CPR-F", ND, "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Fixa", "Reais", ND, ND, "2400", "3836", "126", "Exigida", ND, ND,
     "71 anos", "2", ND, "185", "350000", "700000",
     ND, "CCB PF e PJ", "101% do saldo contabil", "Gestora - elegibilidade", ND, ND,
     "Cap individual nao divulgado no acervo publico", ND, "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Fixa", "Reais", ND, ND, "2400", "3836", "126", "Exigida", ND, ND,
     "71 anos", "2", ND, "185", "350000", "700000",
     ND, "CCB PF e PJ", "104% do saldo contabil", "Endossantes/originador - condicao atestada", ND, ND,
     "Cap individual nao divulgado; revolvencia obrigatoria de 12 meses", ND, "ANX-DECK", "Documentado"),
]

# Linhas derivadas de leitura, para a mesma aba
ELEGIBILIDADE_DELTAS = [
    ("Delta CRI-I -> CRI-III", "Cap por devedor mantido em 0,10%, mas o cap de 1% para os 10 maiores devedores desaparece; o ticket maximo PJ sobe de R$ 600 mil para R$ 700 mil.",
     "Afrouxa: some um limite de concentracao de grupo e o ticket PJ cresce 16,7%.", "ANX-LAM-K1; ANX-LAM-K3"),
    ("Delta CRI-III -> CRI-V", "Cap por devedor passa de 0,10% fixo para 0,15% escalonado, caindo a 0,07% quando a integralizacao atinge 750.000 quantidades; entram a vedacao a parcela balao, a exigencia de moeda em Reais e o enquadramento do PJ na Resolucao CMN 5.118; o WAM passa a ser medido sobre o valor presente da cessao.",
     "Endurece na maturidade: no inicio da emissao o limite e mais folgado (0,15%), mas o pool maduro fica 30% mais granular que o de CRI-III (0,07% contra 0,10%).",
     "ANX-LAM-K3; ANX-LAM-V174"),
    ("Delta FIDC -> CRI (geral)", "O cap individual cai de 2%-20% nos FIDCs para 0,07%-0,25% nos CRIs; o WAM contratual cai de 2.400 para 2.000 dias; o prazo maximo por recebivel cai de ate 4.760 dias (FIDC V) para 3.845 dias.",
     "O CRI compra um recorte mais granular e mais curto do que o mandato do warehouse permite originar.",
     "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174"),
    ("Delta FIDC-VI -> FIDC-VII", "O preco maximo de aquisicao sobe de 101% para 104% do saldo contabil; entra revolvencia obrigatoria de 12 meses e trava de 3 meses da junior apos Evento de Venda.",
     "Troca: o fundo aceita pagar mais agio na entrada e compensa com disciplina de reinvestimento e retencao pos-venda.",
     "ANX-DECK"),
]
ELEGIBILIDADE_DELTAS_COLS = ["comparacao", "o_que_muda", "leitura_de_credito", "fonte_id"]

# ============================================================ 04_Concentracao
CONCENTRACAO_COLS = [
    "veiculo_id", "cap_individual_pct_patrimonio_separado", "cap_individual_escalonado",
    "cap_top10_pct", "cap_por_devedor_ANBIMA_pct", "cap_por_integrador", "cap_por_UF",
    "cap_PJ_pct", "cap_por_safra", "concentracao_observada_individual",
    "concentracao_observada_top10", "folga_vs_limite_pp", "classificacao_ANBIMA",
    "data_base", "fonte_id",
]

CONCENTRACAO = [
    ("CRI-I", "0,10", "Nao - limite fixo", "1,0", "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2024-01-15", "ANX-LAM-K1; ANX-CM-K2"),
    ("CRI-II", "0,10", "Nao - limite fixo", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2024-06-25", "ANX-CM-K2; ANX-DECK"),
    ("CRI-III", "0,10", "Nao - limite fixo", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2025-04-22", "ANX-LAM-K3"),
    ("CRI-IV", "0,25", "Sim - 0,25% caindo para 0,17% do Patrimonio Separado", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2025-09-29", "ANX-DECK"),
    ("CRI-V", "0,15", "Sim - 0,15% ate 470.600 quantidades integralizadas; 0,07% a partir de 750.000 quantidades",
     ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2026-04-17", "ANX-LAM-V174"),
    ("CRI-VI", "0,11", ND, ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentracao: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2026-07-31", "ANX-DECK"),
    ("FIDC-I", "2,0", "Nao", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a - classificacao ANBIMA de CRI nao se aplica a FIDC",
     "2026-07-31", "ANX-DECK"),
    ("FIDC-II", "2,0", "Nao", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-III", "0,10", "Nao", "1,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-IV", "20,0", "Nao", ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-V", "2,0", "Nao", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-VI", ND, ND, ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-VII", ND, ND, ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
]

NOTA_CONCENTRACAO = (
    "O cap da ANBIMA (maximo de 20% dos creditos por um unico devedor) e o cap contratual "
    "(0,07% a 0,25% do Patrimonio Separado) medem coisas diferentes e estao a duas ordens de grandeza "
    "de distancia: quem morde e o contratual. A concentracao observada nao e publicada em nenhuma das "
    "seis operacoes, entao a folga contra o limite permanece n/d."
)
