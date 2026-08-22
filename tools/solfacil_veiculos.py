# -*- coding: utf-8 -*-
"""Veículos (7 FIDCs + 6 operações de CRI) e as 34 séries/classes."""

ND = "n/d"

VEICULOS_COLS = [
    "veiculo_id", "tipo", "nome_comercial", "nome_oficial", "numero_emissao",
    "cnpj_ou_emissora", "securitizadora", "data_inicio_ou_emissao",
    "data_bookbuilding", "data_encerramento_oferta", "situacao",
    "administrador", "gestor", "custodiante", "agente_fiduciario", "escriturador",
    "auditor", "agencia_rating", "coordenador_lider", "demais_coordenadores",
    "participantes_especiais", "pl_ou_saldo_Rmi", "carteira_Rmi",
    "data_base", "fonte_id", "status",
]

# ---------------------------------------------------------------- FIDCs
# PL/carteira/administrador/gestor: CVM Informe Mensal FIDC e cadastro, via ANX-DECK (sl.7 e 8), data-base 31/07/2026.
# Nome oficial e CNPJ do II e do IV confirmados em documento primario (ANX-PRO-K1 sec. 11.1.2).
from solfacil_funding import DEBENTURE_VEICULO

VEICULOS = [
    ("FIDC-I", "FIDC", "Solfácil FIDC I", ND, "n/a", "36.771.685/0001-17", "n/a",
     "2020-12-21", "n/a", "n/a", "Em funcionamento", "Daycoval", "Anga", ND, ND, ND, ND,
     "Austin Rating", "n/a", "n/a", "n/a", "83.7", "77.6", "2026-07-31", "ANX-DECK", "Documentado"),

    ("FIDC-II", "FIDC", "Solfácil FIDC II", "GREEN SOLFÁCIL II FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
     "n/a", "42.462.306/0001-00", "n/a", "2021-10-15", "n/a", "n/a", "Em funcionamento",
     "Banco Genial S.A. (CNPJ 45.246.410/0001-55)", "Anga", ND, ND, ND, ND, "Austin Rating",
     "n/a", "n/a", "n/a", "94.1", "102.5", "2026-07-31", "ANX-DECK; ANX-PRO-K1", "Documentado"),

    ("FIDC-III", "FIDC", "Solfácil FIDC III", ND, "n/a", "49.920.525/0001-34", "n/a",
     "2023-07-11", "n/a", "n/a", "Em funcionamento", "Daycoval", "Regia", ND, ND, ND, ND,
     "Fitch Ratings; Austin Rating", "n/a", "n/a", "n/a", "141.1", "131.5", "2026-07-31", "ANX-DECK", "Documentado"),

    ("FIDC-IV", "FIDC", "Solfácil FIDC IV", "GREEN SOLFÁCIL IV FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
     "n/a", "44.909.456/0001-44", "n/a", "2022-06-23", "n/a", "n/a", "Em funcionamento",
     "Banco Genial S.A. (CNPJ 45.246.410/0001-55)", "Genial", ND, ND, ND, ND, "Austin Rating",
     "n/a", "n/a", "n/a", "17.5", "14.6", "2026-07-31", "ANX-DECK; ANX-PRO-K1", "Documentado"),

    ("FIDC-V", "FIDC", "Solfácil FIDC V", ND, "n/a", "47.240.785/0001-33", "n/a",
     "2023-03", "n/a", "n/a", "Em funcionamento", "Daycoval", "Anga", ND, ND, ND, ND,
     "Austin Rating", "n/a", "n/a", "n/a", "67.5", "66.7", "2026-07-31", "ANX-DECK", "Documentado"),

    ("FIDC-VI", "FIDC", "Solfácil FIDC VI",
     "IS GREEN SOLFÁCIL VI FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA", "n/a", "57.028.406/0001-08", "n/a",
     "2024-11-06", "n/a", "n/a", "Em funcionamento", "Limine", "Regia", ND, ND, ND, ND,
     "Austin Rating", "n/a", "n/a", "n/a", "211.1", "147.7", "2026-07-31", "ANX-DECK; ANX-TS-V177", "Documentado"),

    ("FIDC-VII", "FIDC", "Solfácil FIDC VII",
     "SOLFÁCIL CRÉDITO PESSOAL VII FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA", "n/a", "63.505.455/0001-89", "n/a",
     "2026-02-06", "n/a", "n/a", "Em funcionamento (CVM 175, subclasses)", "Banco Genial", "Anga", ND, ND, ND, ND,
     "Moody's America Latina", "n/a", "n/a", "n/a", "619.6", "446.1", "2026-07-31", "ANX-DECK; ANX-TS-V177", "Documentado"),

    # ---------------------------------------------------------------- CRIs
    ("CRI-I", "CRI", "CRI Solfácil I", "1ª Emissão, em 5 séries (1 privada + 4 públicas), da Kanastra Securitizadora S.A.",
     "1a", "48.238.484/0001-38", "Kanastra Securitizadora S.A.", "2024-01-15", ND, "2024-02-23",
     "Ativa / adimplente", "n/a", "n/a", ND,
     "Vortx DTVM Ltda. (CNPJ 22.610.500/0001-88)", "Oliveira Trust DTVM S.A. (CNPJ 36.113.876/0004-34)", ND,
     "Fitch Ratings", "Banco Itaú BBA S.A. (CNPJ 17.298.092/0001-30)", "n/a",
     "BTG Pactual; XP Investimentos; Orama; Banco Andbank (Brasil)",
     "603.0", ND, "2026-08-21", "ANX-ENC-K1; ANX-LAM-K1; ANX-PRO-K1; ANX-DECK", "Documentado"),

    ("CRI-II", "CRI", "CRI Solfácil II", "2ª Emissão, em 5 séries (1 privada + 4 públicas), da Kanastra Securitizadora S.A.",
     "2a", "48.238.484/0001-38", "Kanastra Securitizadora S.A.", "2024-06-25", "2024-06-20", ND,
     "Ativa / adimplente", "n/a", "n/a", ND,
     "Oliveira Trust DTVM S.A. (CNPJ 36.113.876/0001-91)", ND, ND,
     "Fitch Ratings; Moody's America Latina",
     "Itaú BBA Assessoria Financeira S.A. (CNPJ 04.845.753/0001-59), sucessor legal do Banco Itaú BBA S.A. (CNPJ 17.298.092/0001-30)",
     "XP Investimentos", "n/a", "750.0", ND, "2026-08-21", "ANX-CM-K2; ANX-PRO-K2; ANX-TS2-K2; ANX-DECK", "Documentado"),

    ("CRI-III", "CRI", "CRI Solfácil III", "3ª Emissão, em até 6 séries (1 privada + 5 públicas), da Kanastra Securitizadora S.A.",
     "3a", "48.238.484/0001-38", "Kanastra Securitizadora S.A.", "2025-05-28", ND, ND,
     "Ativa / adimplente", "n/a", "n/a", ND, ND, ND, ND,
     "Moody's America Latina", ND, ND, "n/a", "750.0", ND, "2026-08-21", "ANX-LAM-K3; ANX-DECK", "Documentado"),

    ("CRI-IV", "CRI", "CRI Solfácil IV", "4ª Emissão, em 7 séries (1 privada + 6 públicas), da Kanastra Securitizadora S.A.",
     "4a", "48.238.484/0001-38", "Kanastra Securitizadora S.A.", "2025-09-28", "2025-09-26", ND,
     "Ativa / adimplente", "n/a", "n/a", ND,
     "Oliveira Trust DTVM S.A. (CNPJ 36.113.876/0001-91)", ND, ND, "Moody's America Latina",
     "Itaú BBA Assessoria Financeira S.A. (CNPJ 04.845.753/0001-59)",
     "Banco Bradesco BBI S.A. (CNPJ 06.271.464/0073-93); XP Investimentos (CNPJ 02.332.886/0011-78)",
     "n/a", "450.0", ND, "2026-08-21", "ANX-INI-K4; ANX-DECK", "Documentado"),

    ("CRI-V", "CRI", "CRI Solfácil V", "174ª Emissão, em 6 séries (1 privada + 5 públicas), da VERT Companhia Securitizadora",
     "174a", "25.005.683/0001-09", "VERT Companhia Securitizadora", "2026-05-29", ND, ND,
     "Ativa / adimplente", "n/a", "n/a", ND,
     "Oliveira Trust DTVM S.A. (CNPJ 36.113.876/0001-91)", ND, ND, "Moody's America Latina",
     ND, "XP Investimentos; Banco Bradesco BBI S.A.", "n/a", "470.6", ND, "2026-08-21",
     "ANX-LAM-V174; ANX-DECK", "Documentado"),

    ("CRI-VI", "CRI", "CRI Solfácil VI", "177ª Emissão da VERT Companhia Securitizadora",
     "177a", "25.005.683/0001-09", "VERT Companhia Securitizadora", "2026-07-31", ND, ND,
     "Ativa - sem informe mensal até a data-base", "n/a", "n/a", ND,
     "Oliveira Trust DTVM S.A. (CNPJ 36.113.876/0001-91)", ND, ND,
     "Sem classificação de risco mínima da Emissão", ND, ND, "n/a", "647.059", ND, "2026-07-31",
     "ANX-TS-V177; ANX-DECK", "Documentado"),
]

# Notas de leitura por veiculo, usadas nas abas e no deck.
VEICULOS.append(DEBENTURE_VEICULO)

NOTA_VEICULOS = (
    "Sete FIDCs funcionam como warehouse, seis operações de CRI como take-out e uma debênture "
    "da Amazônia Solar, de 2022, completa o perímetro de funding. "
    "PL e carteira dos FIDCs são de 31/07/2026; o volume dos CRI e nominal de emissão, "
    "somando série privada e séries públicas."
)
