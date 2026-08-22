# -*- coding: utf-8 -*-
"""Subscritores, matriz FIDC->CRI, cessoes e custo de captacao."""

ND = "n/d"

# ============================================================ 10_Subscritores (tabela longa, literal)
# Rotulos exatos do formulario CVM de dados finais de distribuicao.
SUBS_LONGA_COLS = ["veiculo_id", "serie", "camada", "tipo_de_investidor",
                   "numero_de_subscritores", "quantidade_subscrita", "data_base", "fonte_id"]

_TIPOS = [
    "Pessoas naturais", "Clubes de investimento", "Fundos de investimento",
    "Entidades de previdencia privada", "Companhias seguradoras", "Investidores estrangeiros",
    "Instituicoes intermediarias participantes do consorcio de distribuicao",
    "Instituicoes financeiras ligadas ao emissor e aos participantes do consorcio",
    "Demais instituicoes financeiras",
    "Demais pessoas juridicas ligadas ao emissor e aos participantes do consorcio",
    "Demais pessoas juridicas",
    "Socios, administradores, empregados, prepostos e demais pessoas ligadas ao emissor e aos participantes do consorcio",
]

# (serie, camada, [(n_subscritores, quantidade) por tipo na ordem de _TIPOS])
_CRI_I_SUBS = [
    ("1a", "Super Senior", [(989, 151827), (0, 0), (1, 1201), (0, 0), (0, 0), (0, 0), (0, 0),
                            (1, 200000), (0, 0), (0, 0), (1, 1895), (16, 5077)]),
    ("2a", "Senior", [(774, 82621), (0, 0), (1, 5717), (0, 0), (0, 0), (0, 0), (0, 0),
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
    ("CRI-I", "2138", "8", "1", "4", ND, "Anuncio de Encerramento (distribuicao na emissao)", "2024-02-23", "ANX-ENC-K1; ANX-DECK"),
    ("CRI-II", "2659", "86", "4", "9", ND, "Documentos de oferta (distribuicao na emissao)", "2024-06-25", "ANX-DECK"),
    ("CRI-III", "7855", "59", "1", "8", ND, "Documentos de oferta (distribuicao na emissao)", "2025-05-28", "ANX-DECK"),
    ("CRI-IV", "2567", "13", "3", "4", ND, "Documentos de oferta (distribuicao na emissao)", "2025-09-28", "ANX-DECK"),
    ("CRI-V", "2505", "13", "4", "10", ND, "Documentos de oferta (distribuicao na emissao)", "2026-05-20", "ANX-DECK"),
    ("CRI-VI", "Oferta aberta", "0", "0", "0", ND, "Oferta em curso; sem anuncio de encerramento", "2026-07-31", "ANX-DECK"),
]

NOTA_SUBSCRITORES = (
    "Distribuicao na emissao e posicao corrente sao coisas distintas: a primeira e publica pelos "
    "anuncios de encerramento, a segunda depende de B3, escriturador ou custodiante e permanece n/d "
    "nas seis operacoes. Numero de subscritores tambem nao e quantidade subscrita - a serie Super Senior "
    "de CRI-I teve 1.008 subscritores e mais da metade do volume ficou com um so."
)

# ============================================================ 11_Matriz_FIDC_CRI
MATRIZ_COLS = ["fidc", "cri", "estado", "criterio_que_bloqueia_ou_evidencia", "fonte_id", "status"]

_DOC = "Documentado"
_INF = "Inferido"

MATRIZ = []
_CEDEU = {
    ("FIDC-II", "CRI-I"): ("Nomeado no Prospecto Definitivo como representante de mais de 10% dos Direitos Creditorios Cedidos", "ANX-PRO-K1", _DOC),
    ("FIDC-IV", "CRI-I"): ("Nomeado no Prospecto Definitivo como representante de mais de 10% dos Direitos Creditorios Cedidos", "ANX-PRO-K1", _DOC),
    ("FIDC-II", "CRI-II"): ("Definicao de 'Cedentes' no Prospecto: o FIDC II e o FIDC IV em conjunto", "ANX-PRO-K2", _DOC),
    ("FIDC-IV", "CRI-II"): ("Definicao de 'Cedentes' no Prospecto: o FIDC II e o FIDC IV em conjunto", "ANX-PRO-K2", _DOC),
    ("FIDC-II", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-IV", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-III"): ("Deck registra cedentes FIDC II + IV + VI", "ANX-DECK", _DOC),
    ("FIDC-II", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessao direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-IV", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessao direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-IV"): ("Deck registra cedentes FIDC II + IV + VI e cessao direta da originadora", "ANX-DECK", _DOC),
    ("FIDC-VI", "CRI-V"): ("Deck registra cedente FIDC VI e cessao direta; a lamina confirma a existencia de um 'Cedente Fundo' com Gestora e custodiante proprios, sem nomea-lo", "ANX-DECK; ANX-LAM-V174", _DOC),
    ("FIDC-VI", "CRI-VI"): ("Deck registra cedentes FIDC VI + VII e cessao direta", "ANX-DECK", _DOC),
    ("FIDC-VII", "CRI-VI"): ("Deck registra cedentes FIDC VI + VII e cessao direta", "ANX-DECK", _DOC),
}
_NAO_ELEGIVEL = {
    "FIDC-V": ("Mandato admite CPR-F alem de CCB e prazo de ate 4.760 dias, acima do teto de 3.845 dias dos CRI; "
               "ticket PF de ate R$ 500 mil supera o limite de R$ 350 mil"),
}
for fidc in ["FIDC-I", "FIDC-II", "FIDC-III", "FIDC-IV", "FIDC-V", "FIDC-VI", "FIDC-VII"]:
    for cri in ["CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI"]:
        if (fidc, cri) in _CEDEU:
            just, fonte, st = _CEDEU[(fidc, cri)]
            MATRIZ.append((fidc, cri, "Cedeu", just, fonte, st))
        elif fidc in _NAO_ELEGIVEL:
            MATRIZ.append((fidc, cri, "Nao elegivel no mandato integral",
                           _NAO_ELEGIVEL[fidc] + " - parte da carteira pode ser elegivel, o mandato como um todo nao e",
                           "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174", _INF))
        else:
            MATRIZ.append((fidc, cri, "Pode ceder",
                           "Mandato origina CCB pre-fixada de financiamento solar, com prazo e ticket dentro dos tetos do CRI; "
                           "sem cessao documentada para esta operacao",
                           "ANX-DECK; ANX-LAM-K3; ANX-LAM-V174", _INF))

CESSOES_COLS = ["data", "fidc_cedente", "cri_cessionario", "volume_Rmi", "pct_do_pool_do_CRI",
                "preco_pct_saldo", "cessao_direta_do_originador", "fonte_id", "status"]
CESSOES = [
    ("2024-01-15", "FIDC-II e FIDC-IV", "CRI-I", ND, "Cada um representa mais de 10% dos Direitos Creditorios Cedidos",
     ND, "Nao", "ANX-PRO-K1", "Documentado"),
    ("2024-06-25", "FIDC-II e FIDC-IV", "CRI-II", ND, ND, ND, "Nao", "ANX-PRO-K2", "Documentado"),
    ("2025-05-28", "FIDC-II, FIDC-IV e FIDC-VI", "CRI-III", ND, ND, ND, "Nao", "ANX-DECK", "Documentado"),
    ("2025-09-28", "FIDC-II, FIDC-IV e FIDC-VI", "CRI-IV", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
    ("2026-05-20", "FIDC-VI", "CRI-V", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
    ("2026-07-21", "FIDC-VI e FIDC-VII", "CRI-VI", ND, ND, ND, "Sim - parcial", "ANX-DECK", "Documentado"),
]

NOTA_MATRIZ = (
    "So os Prospectos das duas primeiras emissoes nomeiam os FIDCs cedentes (II e IV). Das demais, o "
    "vinculo vem do deck; as laminas de CRI-III e CRI-V nao nomeiam nenhum fundo e remetem ao Termo de "
    "Securitizacao, que precisa ser obtido no Fundos.NET. Volume cedido, percentual do pool e preco por "
    "lote sao n/d em todas as seis operacoes."
)

# ============================================================ 12_Custo_Captacao
# Evolucao do spread por camada ao longo das seis operacoes (series comparaveis em DI+)
SPREAD_CAMADA_COLS = ["camada", "CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI", "unidade", "fonte_id"]
SPREAD_CAMADA = [
    ("Mezanino (DI + spread)", ND, "6,00", "5,75", "5,50", "5,50", "5,50", "% a.a. sobre 100% do DI",
     "ANX-CM-K2; ANX-LAM-K3; ANX-INI-K4; ANX-LAM-V174; ANX-DECK"),
    ("Subordinado (DI + spread)", ND, "10,00", "10,00", "10,00", "8,00", "8,00", "% a.a. sobre 100% do DI",
     "ANX-CM-K2; ANX-LAM-K3; ANX-INI-K4; ANX-LAM-V174; ANX-DECK"),
    ("Super Senior indexado ao DI", ND, ND, "105,50", ND, "104,00", ND, "% do DI", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Super Senior pre-fixado", "11,51", "13,1926", "15,50", "14,2216", "14,8064", ND, "% a.a. base 252",
     "ANX-LAM-K1; ANX-CM-K2; ANX-LAM-K3; ANX-DECK"),
    ("Senior pre-fixado", "12,74", "14,5663", "16,50", "15,3565", "15,7760", ND, "% a.a. base 252",
     "ANX-LAM-K1; ANX-CM-K2; ANX-LAM-K3; ANX-DECK"),
    ("Senior indexado ao DI", ND, ND, ND, ND, ND, "1,50 e 2,00", "% a.a. sobre 100% do DI", "ANX-DECK"),
    ("Subordinado Jr. (privada)", "9,86", "11,93", "13,6300", "13,2480", "14,0650", "100% do DI",
     "% a.a. base 252, salvo CRI-VI", "ANX-DECK"),
]

CUSTO_COLS = ["veiculo_id", "custo_medio_ponderado_das_series_publicas", "custo_da_subordinada",
              "custos_fixos_anualizados_bps", "custo_all_in_bps", "taxa_equivalente_CDI_hoje",
              "observacao", "data_base", "fonte_id", "status"]
CUSTO = [
    ("CRI-I", ND, ND, ND, ND, ND,
     "Nao apuravel sem curva DI da data-base: as quatro series publicas sao pre-fixadas e a conversao para spread sobre DI exige a curva B3 de 15/01/2024",
     "2024-01-15", "ANX-LAM-K1; ANX-ENC-K1", "n/d - falta curva DI"),
    ("CRI-II", ND, ND, ND, ND, ND,
     "Duas series pre e duas em DI+; a media ponderada exige a curva DI de 20/06/2024",
     "2024-06-25", "ANX-CM-K2", "n/d - falta curva DI"),
    ("CRI-III", ND, ND, ND, ND, ND,
     "Mistura pre, %DI e DI+; exige a curva DI de 28/05/2025", "2025-05-28", "ANX-LAM-K3", "n/d - falta curva DI"),
    ("CRI-IV", ND, ND, ND, ND, ND,
     "Quatro series pre e duas em DI+; exige a curva DI de 26/09/2025", "2025-09-28", "ANX-INI-K4", "n/d - falta curva DI"),
    ("CRI-V", ND, ND, ND, ND, ND,
     "Mistura pre, %DI e DI+; exige a curva DI de 20/05/2026", "2026-05-20", "ANX-LAM-V174", "n/d - falta curva DI"),
    ("CRI-VI", ND, ND, ND, ND, ND,
     "Todas as series em DI+ ou %DI; montantes por serie n/d", "2026-07-31", "ANX-DECK", "n/d - falta montante por serie"),
    ("FIDC-VI", ND, ND, ND, ND, "DI + 3,50% a.a. na senior", "Custo senior conhecido; custos fixos nao publicos",
     "2026-07-31", "ANX-DECK", "Parcial"),
    ("FIDC-VII", ND, ND, ND, ND, "DI + 2,00% a.a. na senior", "Custo senior conhecido; custos fixos nao publicos",
     "2026-07-31", "ANX-DECK", "Parcial"),
]

NOTA_CUSTO = (
    "O spread do Mezanino caiu de DI+6,00% em CRI-II para DI+5,75% em CRI-III e DI+5,50% de CRI-IV em "
    "diante; o do Subordinado caiu de DI+10,00% para DI+8,00% a partir de CRI-V. O custo all-in de cada "
    "estrutura nao e calculavel com dado publico: falta a curva DI de cada data-base para por pre, %DI e "
    "DI+ na mesma regua, e os custos fixos por veiculo nao sao divulgados. A comparacao all-in FIDC x CRI "
    "tambem nao capturaria preco de cessao, hedge nem capital retido."
)
