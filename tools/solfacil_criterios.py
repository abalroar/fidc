# -*- coding: utf-8 -*-
"""Elegibilidade, concentração, prazos/WAM, waterfall, subordinada e PDD."""

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
    ("CRI-I", "Pré-fixada", ND, "0,10% do Patrimônio Separado (mais cap de 1% para os 10 maiores devedores)",
     "Taxa de Retorno pro forma >= Taxa Média Mínima de Retorno (21,5% a.a.)", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso", ND,
     "71 anos na emissão da CCB", "2", "Não éxigido", "185", "350000", "600000",
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND,
     "Emissora, com base nas informações prestadas pelos Cedentes", ND, ND,
     "Inadimplência do devedor; recebível em atraso; crédito não performado",
     "'o valor dos Direitos Creditórios Imobiliarios devidos por um Devedor individualmente não deverá representar mais de 0,10% do Patrimônio Separado da Emissão; e o grupo dos 10 maiores Devedores não poderá ser devedor de Direitos Creditórios Imobiliarios cujo valor supere 1% do Patrimônio Separado da Emissão'",
     "ANX-LAM-K1; ANX-PRO-K1", "Documentado"),

    ("CRI-II", "Pré-fixada", ND, "0,10% do Patrimônio Separado",
     "Taxa de Retorno pro forma >= Taxa Média Mínima de Retorno (21% a.a.)", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso", ND,
     "71 anos na emissão da CCB", "2", "Não éxigido", "185", "350000", ND,
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND,
     "Emissora, com base nas informações prestadas pelos Cedentes", ND, ND,
     "Inadimplência do devedor; recebível em atraso; crédito não performado",
     "'Taxa Média Mínima de Retorno: 21% (vinte e um por cento) a.a.'",
     "ANX-PRO-K2; ANX-TS2-K2; ANX-DECK", "Documentado"),

    ("CRI-III", "Pré-fixada", ND, "0,10% do Patrimônio Separado",
     "Taxa de Retorno pro forma >= Taxa Média Mínima de Retorno", "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso", ND,
     "71 anos na emissão da CCB", "2", "Não éxigido", "185", "350000", "700000",
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND,
     "Emissora, com base nas informações prestadas pelos Cedentes", ND, ND,
     "Inadimplência do devedor; recebível em atraso; crédito não performado",
     "'considerada pro forma a cessão pretendida, a Média Ponderada dos Prazos de Vencimento das CCBs integrantes do Patrimônio Separado da Emissão deverá ser de no máximo 2.000 (dois mil) dias'",
     "ANX-LAM-K3", "Documentado"),

    ("CRI-IV", "Pré-fixada", ND, "0,25% caindo para 0,17% do Patrimônio Separado (escalonado)",
     ND, "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso", ND,
     "71 anos na emissão da CCB", "2", ND, "185", "350000", ND,
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND,
     "Emissora", ND, ND, "Inadimplência do devedor; recebível em atraso; crédito não performado",
     "Redação literal indisponível: a lâmina da 4ª emissão não está no acervo; parâmetros vindos do deck",
     "ANX-DECK", "Documentado"),

    ("CRI-V", "Pré-fixada", "Reais (moeda brasileira), explícito",
     "0,15% do Patrimônio Separado até 470.600 quantidades integralizadas; 0,07% a partir de 750.000 quantidades",
     "Taxa de Retorno pro forma >= Taxa Média Mínima de Retorno, medida sobre o valor presente da cessão",
     "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso",
     "Exigido: principal e juros em parcelas mensais, sem parcela final superior as demais",
     "71 anos na emissão da CCB", "2", "Resolucao CMN 5.118", "185", "350000", "700000",
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND,
     "Emissora, com envio eletrônico de dados pela Gestora do Cedente Fundo e pela Solfácil, e com as informações da instituição custodiante do respectivo cedente",
     ND, ND,
     "Inadimplência do devedor; recebível em atraso; parcela balão final; PJ fora da CMN 5.118; crédito não performado",
     "'o Direito Creditorio Imobiliario seja um financiamento que preve o pagamento do principal e dos juros em parcelas mensais, sem a existência de parcela final em montante superior as demais parcelas'",
     "ANX-LAM-V174", "Documentado"),

    ("CRI-VI", "Pré-fixada", ND, "0,11% do Patrimônio Separado", ND, "2000", "3845", "126.3",
     "Vedado devedor inadimplente na Data de Oferta", "Vedado recebível em atraso", ND,
     "71 anos na emissão da CCB", "2", ND, "185", "350000", ND,
     ND, "CCB pré-fixada com destinação a Sistema Solar", ND, "Emissora", ND, ND,
     "Inadimplência do devedor; recebível em atraso; crédito não performado",
     "Redação literal indisponível: a lâmina da 177ª emissão não está no acervo; parâmetros vindos do deck",
     "ANX-DECK", "Documentado"),

    # ---------------- FIDCs ----------------
    ("FIDC-I", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, "2135", "3836", "126.1",
     "Não éxplicita na lista de critérios", ND, ND, ND, ND, ND, ND, "201000", "502000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND, "Redação menos protetiva que a dos CRI",
     ND, "ANX-DECK", "Documentado"),
    ("FIDC-II", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, "2400",
     "2.340 (pré) / 4.500 (pós)", "76,9 / 147,9", "Exigida", ND, ND, ND, ND, ND, "180", "300000", "500000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND, ND, ND, "ANX-DECK", "Documentado"),
    ("FIDC-III", "Fixa", ND, "0,10% (cap individual); 1% para os 10 maiores", ND, "2000", "3845", "126.3",
     "Exigida", ND, ND, ND, ND, ND, "185", "350000", "600000",
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND,
     "Critério próximo ao do CRI inicial", ND, "ANX-DECK", "Documentado"),
    ("FIDC-IV", "Fixa", ND, "20% (cap individual)", ND, ND, ND, ND, "Exigida", ND, ND, ND, ND, ND, ND, ND, ND,
     ND, "CCB PF e PJ", ND, "Gestora/Administrador", ND, ND,
     "Mais permissivo em concentração entre os sete fundos", ND, "ANX-DECK", "Documentado"),
    ("FIDC-V", "Fixa", ND, "2% (cap individual); 10% para os 10 maiores", ND, ND, "4760", "156.5",
     "Exigida", ND, ND, ND, ND, ND, "185 / 366", "500000", "700000",
     ND, "CCB + CPR-F", ND, "Gestora/Administrador", ND, ND,
     "Ativo e ticket mais amplos; único fundo que admite CPR-F", ND, "ANX-DECK", "Documentado"),
    ("FIDC-VI", "Fixa", "Reais", ND, ND, "2400", "3836", "126", "Exigida", ND, ND,
     "71 anos", "2", ND, "185", "350000", "700000",
     ND, "CCB PF e PJ", "101% do saldo contábil", "Gestora - elegibilidade", ND, ND,
     "Cap individual não divulgado no acervo público", ND, "ANX-DECK", "Documentado"),
    ("FIDC-VII", "Fixa", "Reais", ND, ND, "2400", "3836", "126", "Exigida", ND, ND,
     "71 anos", "2", ND, "185", "350000", "700000",
     ND, "CCB PF e PJ", "104% do saldo contábil", "Endossantes/originador - condição atestada", ND, ND,
     "Cap individual não divulgado; revolvência obrigatória de 12 meses", ND, "ANX-DECK", "Documentado"),
]

# Linhas derivadas de leitura, para a mesma aba
ELEGIBILIDADE_DELTAS = [
    ("Delta CRI-I -> CRI-III", "Cap por devedor mantido em 0,10%, mas o cap de 1% para os 10 maiores devedores desaparece; o ticket máximo PJ sobe de R$ 600 mil para R$ 700 mil.",
     "Afrouxa: some um limite de concentração de grupo e o ticket PJ cresce 16,7%.", "ANX-LAM-K1; ANX-LAM-K3"),
    ("Delta CRI-III -> CRI-V", "Cap por devedor passa de 0,10% fixo para 0,15% escalonado, caindo a 0,07% quando a integralização atinge 750.000 quantidades; entram a vedação a parcela balão, a exigência de moeda em Reais e o enquadramento do PJ na Resolucao CMN 5.118; o WAM passa a ser medido sobre o valor presente da cessão.",
     "Endurece na maturidade: no início da emissão o limite é mais folgado (0,15%), mas o pool maduro fica 30% mais granular que o de CRI-III (0,07% contra 0,10%).",
     "ANX-LAM-K3; ANX-LAM-V174"),
    ("Delta FIDC -> CRI (geral)", "O cap individual cai de 2%-20% nos FIDCs para 0,07%-0,25% nos CRIs; o WAM contratual cai de 2.400 para 2.000 dias; o prazo máximo por recebível cai de até 4.760 dias (FIDC V) para 3.845 dias.",
     "O CRI compra um recorte mais granular e mais curto do que o mandato do warehouse permite originar.",
     "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174"),
    ("Delta FIDC-VI -> FIDC-VII", "O preço máximo de aquisição sobe de 101% para 104% do saldo contábil; entra revolvência obrigatória de 12 meses e trava de 3 meses da júnior após Evento de Venda.",
     "Troca: o fundo aceita pagar mais ágio na entrada e compensa com disciplina de reinvestimento e retenção pos-venda.",
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
    ("CRI-I", "0,10", "Não - limite fixo", "1,0", "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2024-01-15", "ANX-LAM-K1; ANX-CM-K2"),
    ("CRI-II", "0,10", "Não - limite fixo", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2024-06-25", "ANX-CM-K2; ANX-DECK"),
    ("CRI-III", "0,10", "Não - limite fixo", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2025-04-22", "ANX-LAM-K3"),
    ("CRI-IV", "0,25", "Sim - 0,25% caindo para 0,17% do Patrimônio Separado", ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2025-09-29", "ANX-DECK"),
    ("CRI-V", "0,15", "Sim - 0,15% até 470.600 quantidades integralizadas; 0,07% a partir de 750.000 quantidades",
     ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2026-04-17", "ANX-LAM-V174"),
    ("CRI-VI", "0,11", ND, ND, "20", ND, ND, ND, ND, ND, ND, ND,
     "Concentração: Pulverizados; Categoria: Hibrido; Segmento: I - Outros; Tipo de contrato com lastro: C (CCB)",
     "2026-07-31", "ANX-DECK"),
    ("FIDC-I", "2,0", "Não", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a - classificação ANBIMA de CRI não se aplica a FIDC",
     "2026-07-31", "ANX-DECK"),
    ("FIDC-II", "2,0", "Não", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-III", "0,10", "Não", "1,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-IV", "20,0", "Não", ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-V", "2,0", "Não", "10,0", "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-VI", ND, ND, ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
    ("FIDC-VII", ND, ND, ND, "n/a", ND, ND, ND, ND, ND, ND, ND, "n/a", "2026-07-31", "ANX-DECK"),
]

NOTA_CONCENTRACAO = (
    "O cap da ANBIMA (máximo de 20% dos créditos por um único devedor) é o cap contratual "
    "(0,07% a 0,25% do Patrimônio Separado) medem coisas diferentes e estão a duas ordens de grandeza "
    "de distância: quem morde é o contratual. A concentração observada não é publicada em nenhuma das "
    "seis operações, então a folga contra o limite permanece n/d."
)
