# -*- coding: utf-8 -*-
"""Subscritores, matriz FIDC->CRI, cessões e custo de captação."""

ND = "n/d"

# ============================================================ 10_Subscritores (tabela longa, literal)
# Rotulos exatos do formulario CVM de dados finais de distribuicao.
SUBS_LONGA_COLS = ["veiculo_id", "serie", "camada", "tipo_de_investidor",
                   "numero_de_subscritores", "quantidade_subscrita", "data_base", "fonte_id"]

_TIPOS = [
    "Pessoas naturais", "Clubes de investimento", "Fundos de investimento",
    "Entidades de previdencia privada", "Companhias seguradoras", "Investidores estrangeiros",
    "Instituições intermediárias participantes do consórcio de distribuição",
    "Instituições financeiras ligadas ao emissor e aos participantes do consórcio",
    "Demais instituições financeiras",
    "Demais pessoas jurídicas ligadas ao emissor e aos participantes do consórcio",
    "Demais pessoas jurídicas",
    "Socios, administradores, empregados, prepostos e demais pessoas ligadas ao emissor e aos participantes do consórcio",
]

# (serie, camada, [(n_subscritores, quantidade) por tipo na ordem de _TIPOS])
_CRI_I_SUBS = [
    ("1a", "Super Sênior", [(989, 151827), (0, 0), (1, 1201), (0, 0), (0, 0), (0, 0), (0, 0),
                            (1, 200000), (0, 0), (0, 0), (1, 1895), (16, 5077)]),
    ("2a", "Sênior", [(774, 82621), (0, 0), (1, 5717), (0, 0), (0, 0), (0, 0), (0, 0),
                      (0, 0), (0, 0), (0, 0), (1, 70), (29, 1592)]),
    ("3a", "Mezanino", [(175, 48204), (0, 0), (3, 19500), (0, 0), (0, 0), (1, 12000), (0, 0),
                        (1, 20000), (0, 0), (0, 0), (1, 2473), (34, 5823)]),
    ("4a", "Subordinado", [(200, 7904), (0, 0), (3, 18500), (0, 0), (0, 0), (0, 0), (0, 0),
                           (0, 0), (0, 0), (0, 0), (1, 1350), (26, 2246)]),
]

SUBS_LONGA = []
for serie, camada, dados in _CRI_I_SUBS:
    for tipo, (n, q) in zip(_TIPOS, dados):
        SUBS_LONGA.append(("CRI-I", serie, camada, tipo, str(n), str(q), "2024-02-23", "ANX-ENC-K1"))

# Distribuicao inicial agregada por operacao (deck sl.21); posicao corrente e n/d em todas.
SUBS_AGREGADO_COLS = ["veiculo_id", "pessoas_fisicas", "fundos", "instituicoes_financeiras",
                      "outras_PJ", "titulares_atuais", "fonte_da_posicao", "data_base", "fonte_id"]
SUBS_AGREGADO = [
    ("CRI-I", "2138", "8", "1", "4", ND, "Anúncio de Encerramento (distribuição na emissão)", "2024-02-23", "ANX-ENC-K1; ANX-DECK"),
    ("CRI-II", "2659", "86", "4", "9", ND, "Documentos de oferta (distribuição na emissão)", "2024-06-25", "ANX-DECK"),
    ("CRI-III", "7855", "59", "1", "8", ND, "Documentos de oferta (distribuição na emissão)", "2025-05-28", "ANX-DECK"),
    ("CRI-IV", "2567", "13", "3", "4", ND, "Documentos de oferta (distribuição na emissão)", "2025-09-28", "ANX-DECK"),
    ("CRI-V", "2505", "13", "4", "10", ND, "Documentos de oferta (distribuição na emissão)", "2026-05-20", "ANX-DECK"),
    ("CRI-VI", "Oferta aberta", "0", "0", "0", ND, "Oferta em curso; sem anúncio de encerramento", "2026-07-31", "ANX-DECK"),
]

NOTA_SUBSCRITORES = (
    "Distribuição na emissão e posição corrente são coisas distintas: a primeira é pública pelos "
    "anúncios de encerramento, a segunda depende de B3, escriturador ou custodiante e permanece n/d "
    "nas seis operações. Número de subscritores também não é quantidade subscrita - a série Super Sênior "
    "de CRI-I teve 1.008 subscritores e mais da metade do volume ficou com um só."
)

# ============================================================ 11_Matriz_FIDC_CRI
MATRIZ_COLS = ["fidc", "cri", "estado", "criterio_que_bloqueia_ou_evidencia", "fonte_id", "status"]

_DOC = "Documentado"
_INF = "Inferido"

MATRIZ = []
_CEDEU = {
    ("FIDC-II", "CRI-I"): ("Nomeado no Prospecto Definitivo como representante de mais de 10% dos Direitos Creditórios Cedidos", "ANX-PRO-K1", _DOC),
    ("FIDC-IV", "CRI-I"): ("Nomeado no Prospecto Definitivo como representante de mais de 10% dos Direitos Creditórios Cedidos", "ANX-PRO-K1", _DOC),
    ("FIDC-II", "CRI-II"): ("Definição de 'Cedentes' no Prospecto: o FIDC II e o FIDC IV em conjunto", "ANX-PRO-K2", _DOC),
    ("FIDC-IV", "CRI-II"): ("Definição de 'Cedentes' no Prospecto: o FIDC II e o FIDC IV em conjunto", "ANX-PRO-K2", _DOC),
    ("FIDC-II", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-IV", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-II", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessão direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-IV", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessão direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessão direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-V"): ("Deck registra cedente FIDC VI e cessão direta; a lâmina confirma a existência de um 'Cedente Fundo' com Gestora e custodiante próprios, sem nomea-lo", "ANX-DECK; ANX-LAM-V174", _DOC),
    ("FIDC-VI", "CRI-VI"): ("Deck registra cedentes FIDC VI + VII e cessão direta", "ANX-DECK", _DOC),
    ("FIDC-VII", "CRI-VI"): ("Deck registra cedentes FIDC VI + VII e cessão direta", "ANX-DECK", _DOC),
}
_NAO_ELEGIVEL = {
    "FIDC-V": ("Mandato admite CPR-F além de CCB e prazo de até 4.760 dias, acima do teto de 3.845 dias dos CRI; "
               "ticket PF de até R$ 500 mil supera o limite de R$ 350 mil"),
}
for fidc in ["FIDC-I", "FIDC-II", "FIDC-III", "FIDC-IV", "FIDC-V", "FIDC-VI", "FIDC-VII"]:
    for cri in ["CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI"]:
        if (fidc, cri) in _CEDEU:
            just, fonte, st = _CEDEU[(fidc, cri)]
            MATRIZ.append((fidc, cri, "Cedeu", just, fonte, st))
        elif fidc in _NAO_ELEGIVEL:
            MATRIZ.append((fidc, cri, "Não élegivel no mandato integral",
                           _NAO_ELEGIVEL[fidc] + " - parte da carteira pode ser elegível, o mandato como um todo não e",
                           "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174", _INF))
        else:
            MATRIZ.append((fidc, cri, "Pode ceder",
                           "Mandato origina CCB pré-fixada de financiamento solar, com prazo e ticket dentro dos tetos do CRI; "
                           "sem cessão documentada para esta operação",
                           "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174", _INF))

CESSOES_COLS = ["data", "fidc_cedente", "cri_cessionario", "volume_Rmi", "pct_do_pool_do_CRI",
                "preco_pct_saldo", "cessao_direta_do_originador", "fonte_id", "status"]
CESSOES = [
    ("2024-01-15", "FIDC-II e FIDC-IV", "CRI-I", ND, "Cada um representa mais de 10% dos Direitos Creditórios Cedidos",
     ND, "Não", "ANX-PRO-K1", "Documentado"),
    ("2024-06-25", "FIDC-II e FIDC-IV", "CRI-II", ND, ND, ND, "Não", "ANX-PRO-K2", "Documentado"),
    ("2025-05-28", "FIDC-II, FIDC-IV e FIDC-VI", "CRI-III", ND, ND, ND, "Não", "ANX-DECK", "Documentado"),
    ("2025-09-28", "FIDC-II, FIDC-IV e FIDC-VI", "CRI-IV", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
    ("2026-05-20", "FIDC-VI", "CRI-V", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
    ("2026-07-21", "FIDC-VI e FIDC-VII", "CRI-VI", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
]

NOTA_MATRIZ = (
    "Só os Prospectos das duas primeiras emissões nomeiam os FIDCs cedentes (II e IV). Das demais, o "
    "vínculo vem do deck; as lâminas de CRI-III e CRI-V não nomeiam nenhum fundo e remetem ao Termo de "
    "Securitização, que precisa ser obtido no Fundos.NET. Volume cedido, percentual do pool e preço por "
    "lote são n/d em todas as seis operações."
)

# ============================================================ 12_Custo_Captacao
# Evolucao do spread por camada ao longo das seis operacoes (series comparaveis em DI+)
SPREAD_CAMADA_COLS = ["camada", "CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI", "unidade", "fonte_id"]
SPREAD_CAMADA = [
    ("Mezanino (DI + spread)", ND, "6,00", "5,75", "5,50", "5,50", "5,50", "% a.a. sobre 100% do DI",
     "ANX-CM-K2; ANX-LAM-K3; ANX-INI-K4; ANX-LAM-V174; ANX-DECK"),
    ("Subordinado (DI + spread)", ND, "10,00", "10,00", "10,00", "8,00", "8,00", "% a.a. sobre 100% do DI",
     "ANX-CM-K2; ANX-LAM-K3; ANX-INI-K4; ANX-LAM-V174; ANX-DECK"),
    ("Super Sênior indexado ao DI", ND, ND, "105,50", ND, "104,00", ND, "% do DI", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Super Sênior pré-fixado", "11,51", "13,1926", "15,50", "14,2216", "14,8064", ND, "% a.a. base 252",
     "ANX-LAM-K1; ANX-CM-K2; ANX-LAM-K3; ANX-DECK"),
    ("Sênior pré-fixado", "12,74", "14,5663", "16,50", "15,3565", "15,7760", ND, "% a.a. base 252",
     "ANX-LAM-K1; ANX-CM-K2; ANX-LAM-K3; ANX-DECK"),
    ("Sênior indexado ao DI", ND, ND, ND, ND, ND, "1,50 e 2,00", "% a.a. sobre 100% do DI", "ANX-DECK"),
    ("Subordinado Jr. (privada)", "9,86", "11,93", "13,6300", "13,2480", "14,0650", "100% do DI",
     "% a.a. base 252, salvo CRI-VI", "ANX-DECK"),
]

CUSTO_COLS = ["veiculo_id", "custo_medio_ponderado_das_series_publicas", "custo_da_subordinada",
              "custos_fixos_anualizados_bps", "custo_all_in_bps", "taxa_equivalente_CDI_hoje",
              "observacao", "data_base", "fonte_id", "status"]
CUSTO = [
    ("CRI-I", ND, ND, ND, ND, ND,
     "Não apurável sem curva DI da data-base: as quatro séries públicas são pré-fixadas e a conversão para spread sobre DI exige a curva B3 de 15/01/2024",
     "2024-01-15", "ANX-LAM-K1; ANX-ENC-K1", "n/d - falta curva DI"),
    ("CRI-II", ND, ND, ND, ND, ND,
     "Duas séries pre e duas em DI+; a média ponderada exige a curva DI de 20/06/2024",
     "2024-06-25", "ANX-CM-K2", "n/d - falta curva DI"),
    ("CRI-III", ND, ND, ND, ND, ND,
     "Mistura pre, %DI e DI+; exige a curva DI de 28/05/2025", "2025-05-28", "ANX-LAM-K3", "n/d - falta curva DI"),
    ("CRI-IV", ND, ND, ND, ND, ND,
     "Quatro séries pre e duas em DI+; exige a curva DI de 26/09/2025", "2025-09-28", "ANX-INI-K4", "n/d - falta curva DI"),
    ("CRI-V", ND, ND, ND, ND, ND,
     "Mistura pre, %DI e DI+; exige a curva DI de 20/05/2026", "2026-05-20", "ANX-LAM-V174", "n/d - falta curva DI"),
    ("CRI-VI", ND, ND, ND, ND, ND,
     "Todas as séries em DI+ ou %DI; montantes por série n/d", "2026-07-31", "ANX-DECK", "n/d - falta montante por série"),
    ("FIDC-VI", ND, ND, ND, ND, "DI + 3,50% a.a. na sênior", "Custo sênior conhecido; custos fixos não públicos",
     "2026-07-31", "ANX-DECK", "Parcial"),
    ("FIDC-VII", ND, ND, ND, ND, "DI + 2,00% a.a. na sênior", "Custo sênior conhecido; custos fixos não públicos",
     "2026-07-31", "ANX-DECK", "Parcial"),
]

NOTA_CUSTO = (
    "O spread do Mezanino caiu de DI+6,00% em CRI-II para DI+5,75% em CRI-III e DI+5,50% de CRI-IV em "
    "diante; o do Subordinado caiu de DI+10,00% para DI+8,00% a partir de CRI-V. O custo all-in de cada "
    "estrutura não é calculável com dado público: falta a curva DI de cada data-base para pôr pré, %DI e "
    "DI+ na mesma régua, e os custos fixos por veículo não são divulgados. A comparação all-in FIDC x CRI "
    "também não capturaria preço de cessão, hedge nem capital retido."
)
