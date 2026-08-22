# -*- coding: utf-8 -*-
"""Debênture Amazônia Solar e a pilha de funding: preço por tranche e evolução no tempo."""

ND = "n/d"

# ============================================================ Debênture (4o tipo de veículo)
# A escritura é de 18/02/2022. A emissora é a Amazônia Solar, securitizadora de créditos
# financeiros; a Solfácil figura como parte e origina as CCBs que lastreiam a operação.
DEBENTURE_VEICULO = (
    "DEB-I", "Debênture", "Debênture Amazônia Solar 1ª emissão",
    "1ª Emissão de Debêntures Simples, Não Conversíveis em Ações, em 2 Séries, da Espécie com Garantia Real",
    "1ª", "43.102.521/0001-62", "Amazônia Solar Companhia Securitizadora de Créditos Financeiros",
    "2022-02-18", ND, ND, "Ativa - em amortização",
    "n/a", "n/a", ND,
    "Vórtx DTVM Ltda. (CNPJ 22.610.500/0001-88)", ND, ND, "Sem rating público",
    ND, ND, "n/a", "60.0", "17.2", "2026-07-31",
    "ANX-ESC-DEB; ANX-RMA-DEB", "Documentado",
)

DEBENTURE_SERIES = [
    ("DEB-I", "Sênior", "1ª", "BRAMSCDBS000", "2022-02-18", "2033-02-18", "132",
     "57000", ND, "1000.00", "57.0", ND, "57.0", "95.0", "IPCA+",
     "n/a", "n/a", "IPCA + 7,22% a.a.", "n/a",
     ND, "438.97", "Sem rating público", ND, "Pública com esforços restritos (CVM 476)", "Não",
     "2026-07-31", "ANX-ESC-DEB; ANX-RMA-DEB", "Documentado"),
    ("DEB-I", "Subordinado Jr.", "2ª", "BRAMSCDBS018", "2022-02-18", "2035-08-18", "162",
     "3000", ND, "1000.00", "3.0", ND, "3.0", "5.0", "IPCA+",
     "n/a", "n/a", "IPCA + 7,22% a.a.", "n/a",
     ND, "1643.86", "Sem rating público", ND, "Privada", "Sim",
     "2026-07-31", "ANX-ESC-DEB; ANX-RMA-DEB", "Documentado"),
]

# Posição corrente da debênture no relatório mensal do agente fiduciário (31/07/2026)
DEBENTURE_POSICAO_COLS = ["veiculo_id", "serie", "codigo_negociacao", "data_base", "pu_R",
                          "quantidade_em_circulacao", "saldo_da_serie_R",
                          "total_distribuido_aos_investidores_R", "fonte_id"]
DEBENTURE_POSICAO = [
    ("DEB-I", "1ª", "AMSC11", "2026-07-31", "438.97", "15675", "6880830.36", "15039605.38", "ANX-RMA-DEB"),
    ("DEB-I", "2ª", "AMSC21", "2026-07-31", "1643.86", "825", "1356181.03", "0.00", "ANX-RMA-DEB"),
]

DEBENTURE_CARTEIRA_COLS = ["indicador", "valor", "unidade", "data_base", "fonte_id"]
DEBENTURE_CARTEIRA = [
    ("Valor de aquisição total acumulado", "17212382.98", "R$", "2026-07-31", "ANX-RMA-DEB"),
    ("Valor nominal total adquirido", "17212382.98", "R$", "2026-07-31", "ANX-RMA-DEB"),
    ("Quantidade de créditos adquiridos", "499", "contratos", "2026-07-31", "ANX-RMA-DEB"),
    ("Quantidade de devedores acumulada", "491", "devedores", "2026-07-31", "ANX-RMA-DEB"),
    ("Saldo de caixa e investimentos", "320680.07", "R$", "2026-07-31", "ANX-RMA-DEB"),
    ("Reserva de despesas", "198838.68", "R$", "2026-07-31", "ANX-RMA-DEB"),
    ("Saldo disponível para aquisição de direitos creditórios", "121841.39", "R$", "2026-07-31", "ANX-RMA-DEB"),
]

NOTA_DEBENTURE = (
    "A debênture é o veículo mais antigo e o menor do programa, e não estava no perímetro original "
    "de sete FIDCs e seis CRIs. A emissora é a Amazônia Solar, securitizadora de créditos financeiros; "
    "a Solfácil figura como parte da escritura e origina as CCBs. A 2ª série é subordinada à 1ª e foi "
    "subscrita exclusivamente pela Solfácil - a mesma mecânica de retenção que aparece nos seis CRIs. "
    "Em 31/07/2026 restavam R$ 8,2 mi de saldo somando as duas séries, contra R$ 60,0 mi de valor de emissão."
)

# ============================================================ Famílias de indexador
# Comparação honesta: só dentro da mesma família. A conversão entre famílias exige a curva DI
# de cada data-base, que não está disponível - por isso não há coluna de spread equivalente.
FAMILIAS = {
    "IPCA+": "IPCA + spread",
    "DI+": "DI + spread",
    "%DI": "Percentual do DI",
    "Pré": "Pré-fixado",
    "Residual": "Residual, sem benchmark",
}

# Custo sênior por veículo, na data de emissão - a espinha da evolução do funding
CUSTO_SENIOR_COLS = ["ordem", "data", "veiculo_id", "instrumento", "camada", "montante_Rmi",
                     "familia_indexador", "taxa_contratada", "spread_numerico", "fonte_id"]
CUSTO_SENIOR = [
    ("1", "2020-12-09", "FIDC-I", "FIDC", "Sênior", "367.0", "IPCA+", "IPCA + 6,75% a.a.", "6.75", "ANX-DECK"),
    ("2", "2021-10-07", "FIDC-II", "FIDC", "Sênior", "500.0", "IPCA+", "IPCA + 11,00% a.a. (m1-12)", "11.00", "ANX-DECK"),
    ("3", "2022-02-18", "DEB-I", "Debênture", "Sênior", "57.0", "IPCA+", "IPCA + 7,22% a.a.", "7.22", "ANX-ESC-DEB"),
    ("4", "2022-12-08", "FIDC-V", "FIDC", "Sênior", "113.3", "IPCA+", "IPCA + 10,00% a.a.", "10.00", "ANX-DECK"),
    ("5", "2023-07-10", "FIDC-III", "FIDC", "Sênior", "312.5", "DI+", "CDI + 3,50% a.a.", "3.50", "ANX-DECK"),
    ("6", "2024-01-15", "CRI-I", "CRI", "Super Sênior", "360.0", "Pré", "11,51% a.a.", "11.51", "ANX-LAM-K1; ANX-DECK"),
    ("7", "2024-06-25", "CRI-II", "CRI", "Super Sênior", "487.5", "Pré", "13,1926% a.a.", "13.1926", "ANX-CM-K2"),
    ("8", "2024-11-06", "FIDC-VI", "FIDC", "Sênior", "700.0", "DI+", "DI + 3,50% a.a.", "3.50", "ANX-DECK"),
    ("9", "2025-05-28", "CRI-III", "CRI", "Super Sênior A", "367.5", "Pré", "15,50% a.a.", "15.50", "ANX-PRO-K3"),
    ("10", "2025-09-28", "CRI-IV", "CRI", "Super Sênior A", "195.0", "Pré", "14,2216% a.a.", "14.2216", "ANX-INI-K4; ANX-DECK"),
    ("11", "2026-01-13", "FIDC-VII", "FIDC", "Sênior", "600.0", "DI+", "DI + 2,00% a.a.", "2.00", "ANX-DECK"),
    ("12", "2026-05-20", "CRI-V", "CRI", "Super Sênior A", "103.9", "Pré", "14,8064% a.a.", "14.8064", "ANX-PRO-V174"),
    ("13", "2026-07-21", "CRI-VI", "CRI", "Sênior A", "100.0", "DI+", "DI + 1,50% a.a.", "1.50", "ANX-TS-V177"),
]

NOTA_CUSTO_SENIOR = (
    "A camada sênior de cada veículo, na data de emissão. Só os pontos da mesma família de indexador "
    "se comparam diretamente. Dentro da família DI+, que é onde está a série mais longa e mais recente, "
    "o spread sênior caiu de CDI+3,50% no FIDC III em 2023 para DI+1,50% na 177ª emissão de CRI em 2026 - "
    "200 pontos-base em três anos. O ponto mais relevante para a estrutura: em julho de 2026 o take-out "
    "em CRI (DI+1,50%) capta 50 pontos-base abaixo do warehouse que o alimenta (FIDC VII, DI+2,00%)."
)
