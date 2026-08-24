# -*- coding: utf-8 -*-
"""Três quadros de comitê: perfil dos veículos, emissões e cronograma de amortização.

Convenção: n/d marca campo cuja fonte é o CVM Fundos.NET ou o informe mensal e que
não foi obtido nesta compilação. Essas células são destacadas para preenchimento manual.
"""
ND = "n/d"
VAZIO = ""

# ══════════════════════════════════════════ QUADRO 1A — perfil dos FIDCs
# Colunas: FIDC I a VIII. O VIII está em discussão e fica em branco.
FIDC_COLS = ["Atributo", "FIDC I", "FIDC II", "FIDC III", "FIDC IV",
             "FIDC V", "FIDC VI", "FIDC VII", "FIDC VIII"]
FIDC_LINHAS = [
    ("Data da 1ª emissão", "09/12/2020", "07/10/2021", "10/07/2023", "23/06/2022",
     "08/12/2022", "06/11/2024", "13/01/2026", VAZIO),
    ("PL mais recente (R$ mm)", "83,7", "94,1", "141,1", "17,5", "67,5", "211,1", "619,6", VAZIO),
    ("% Cota Sênior 1", "63,6%", "72,9%", "66,8%", "100,0%", "79,1%", "66,4%", "74,0%", VAZIO),
    ("% Cota Mezanino", "32,5%", "14,9%", "21,0%", "0,0%", "13,5%", "18,7%", "20,8%", VAZIO),
    ("% Cota Sub Júnior", "3,9%", "12,2%", "12,2%", "0,0%", "7,4%", "14,9%", "5,2%", VAZIO),
    ("Rentabilidade YTD · Sênior 1", ND, ND, ND, ND, ND, ND, ND, VAZIO),
    ("Rentabilidade YTD · Mezanino", ND, ND, ND, ND, ND, ND, ND, VAZIO),
    ("Rentabilidade YTD · Sub Júnior", ND, ND, ND, ND, ND, ND, ND, VAZIO),
    ("Over 90 / carteira (CVM)", "1,3%", "2,1%", "1,2%", "12,7%", "1,7%", "8,4%", "0,0%", VAZIO),
    ("Rating público", "brA+(sf) · Austin", "brA(sf) · Austin", "AAsf(bra) · Fitch",
     "brBBB+(sf) · Austin", "brA(sf) · Austin", "brAA(sf) · Austin",
     "AA+.br(sf) · Moody's", VAZIO),
    ("Administradora", "Daycoval", "Banco Genial", "Daycoval", "Banco Genial",
     "Daycoval", "Limine Trust", "Banco Genial", VAZIO),
    ("Gestor", "Angá", "Angá", "Régia Capital", "Genial", "Angá", "Régia Capital", "Angá", VAZIO),
]
FIDC_NOTA = ("PL, composição por cota e over 90 em 31/07/2026 (CVM — Informe Mensal FIDC). "
             "Rentabilidade YTD por classe não consta da compilação: é campo do informe mensal, "
             "a obter no CVM Fundos.NET. Rating do último relatório localizado no acervo.")

# ══════════════════════════════════════════ QUADRO 1B — perfil dos CRIs
CRI_COLS = ["Atributo", "CRI I", "CRI II", "CRI III", "CRI IV", "CRI V", "CRI VI"]
CRI_LINHAS = [
    ("Securitizadora", "Kanastra", "Kanastra", "Kanastra", "Kanastra", "VERT", "VERT"),
    ("Nº da emissão", "1ª", "2ª", "3ª", "4ª", "174ª", "177ª"),
    ("Data de emissão", "15/01/2024", "25/06/2024", "28/05/2025", "28/09/2025", "20/05/2026", "21/07/2026"),
    ("Volume emitido (R$ mm)", "603,0", "750,0", "750,0", "450,0", "470,6", "647,1"),
    ("Nº de séries", "5", "5", "6", "7", "6", "5"),
    ("% 1ª série", "59,7%", "65,0%", "49,0%", "43,3%", "22,1%", "15,5%"),
    ("% 2ª série", "14,9%", "18,0%", "16,0%", "21,7%", "47,9%", "69,5%"),
    ("% 3ª série", "17,9%", "10,0%", "18,0%", "12,0%", "15,0%", "8,0%"),
    ("% 4ª série", "5,0%", "4,0%", "10,0%", "6,0%", "8,0%", "4,0%"),
    ("% 5ª série", "2,5%", "3,0%", "4,0%", "10,0%", "4,0%", "3,0%"),
    ("% 6ª série", "n.a.", "n.a.", "3,0%", "4,0%", "3,0%", "n.a."),
    ("% 7ª série", "n.a.", "n.a.", "n.a.", "3,0%", "n.a.", "n.a."),
    ("Rentabilidade YTD · 1ª série", ND, ND, ND, ND, ND, ND),
    ("Rentabilidade YTD · série mezanino", ND, ND, ND, ND, ND, ND),
    ("Rentabilidade YTD · série subordinada", ND, ND, ND, ND, ND, ND),
    ("Over 90 / carteira (CVM)", ND, ND, ND, ND, ND, ND),
    ("Rating público · série mais sênior", "AA+ · Fitch", "AA+ · Fitch; AAA · Moody's",
     "AAA · Moody's", "AAA preliminar · Moody's", "AAA · Moody's", "Sem rating mínimo"),
    ("Agente fiduciário", "Vórtx", "Oliveira Trust", ND, "Oliveira Trust", "Oliveira Trust", "Oliveira Trust"),
    ("Escriturador", "Oliveira Trust", ND, ND, ND, ND, ND),
]
CRI_NOTA = ("Volume e composição por série conforme prospectos definitivos, comunicados de bookbuilding "
            "e termos de securitização. Rentabilidade YTD por série e over 90 por operação são campos do "
            "Informe Mensal CRI, a obter no CVM Fundos.NET. A 177ª não possui informe até a data-base.")

# ══════════════════════════════════════════ QUADRO 2A — emissões dos FIDCs
EMI_FIDC_COLS = ["FIDC", "1ª emissão", "Última emissão", "Volume emitido (R$ mm)",
                 "Abertura por data de emissão", "Remuneração-alvo por emissão", "Subordinação mínima"]
EMI_FIDC = [
    ("FIDC I", "09/12/2020", "20/06/2022", "533,6",
     "dez/20: Sr 375,0 + Mezz 50,0 + Sub Jr (n/d emitido) · nov/21: Sub Jr 50,0 · dez/21: Sub Jr (n/d) · jun/22: Mezz B 58,6",
     "Sr: IPCA + 6,75% · Mezz: IPCA + 8,00% · Mezz B: IPCA positivo (% n/d) · Sub Jr: residual",
     "Piso de subordinação total: 25% do PL"),
    ("FIDC II", "24/09/2021", "25/04/2022", "721,0",
     "set/21: Sub Jr 25,0 · out/21: Sr 500,0 + Mezz A 100,0 · abr/22: Sr 2ª série 80,0 + Mezz B 16,0",
     "Sr: IPCA + 11,00% (m1-12), 8,00% (m13-49), 7,00% (m50+) · Mezz A: IPCA + 13,00%/12,50%/11,50% · Sub Jr: residual",
     "Piso de subordinação total: 20% do PL"),
    ("FIDC III", "10/07/2023", "30/09/2023", "500,0",
     "jul/23: Sr 375,0 + Mezz A 75,0 + Mezz B 30,0 · set/23: Sub Jr privada 20,0",
     "Sr: CDI + 3,50% · Mezz A: CDI + 5,75% · Mezz B: CDI + 7,75% (6,75% se Mezz B ≥ 12%) · Sub Jr: n.a.",
     "Piso de subordinação total: 25% do PL"),
    ("FIDC IV", "23/06/2022", "05/12/2023", "877,0",
     "jun/22: Sr A 375,0 + Mezz A-1 75,0 + Sub Jr 50,0 · jan/23: Sr B 250,0 + Mezz A-2 10,0 + Mezz B-1 50,0 + Mezz B-2 7,0 · dez/23: Sr C 260,0",
     "Sr A/B/C: n/d · Mezz A-1: DI + 6,65% · Mezz A-2 e B-2: DI + 7,30% até 23/06/2025, depois 8,30% · Mezz B-1: DI + 6,20% até 23/06/2025, depois 7,20%",
     "Sem piso de subordinação contratual"),
    ("FIDC V", "08/12/2022", "08/12/2022", "356,3",
     "dez/22: Sr 300,0 + Mezz 56,3 · Sub Jr privada: data e volume n/d",
     "Sr: IPCA + 10,00% com piso de 10,00% · Mezz: IPCA + 13,00% com piso de 13,00% · Sub Jr: residual",
     "Piso de subordinação total: 20% do PL"),
    ("FIDC VI", "06/11/2024", "06/11/2024", "896,0",
     "nov/24: Sr 700,0 + Mezz A 140,0 + Mezz B 56,0 · Sub Jr privada: data e volume n/d",
     "Sr: DI + 3,50% · Mezz A e B: n/d · Sub Jr: residual",
     "Piso de subordinação total: 25% do PL · testes de amortização da júnior: 136,0% / 113,3% / 106,3%"),
    ("FIDC VII", "13/01/2026", "13/01/2026", "768,0",
     "jan/26: Sr 600,0 + Mezz A 120,0 + Mezz B 48,0 · Sub Jr privada: data e volume n/d",
     "Sr: DI + 2,00% · Mezz A e B: n/d · Sub Jr: residual",
     "Piso de subordinação total: 25% do PL · mesmos testes do FIDC VI, com trava de 3 meses pós-venda"),
    ("FIDC VIII", VAZIO, VAZIO, VAZIO, VAZIO, VAZIO, VAZIO),
]

# ══════════════════════════════════════════ QUADRO 2B — emissões dos CRIs
EMI_CRI_COLS = ["Operação", "Emissão", "Volume emitido (R$ mm)",
                "Abertura por série", "Remuneração-alvo por série", "Subordinação mínima / cobertura"]
EMI_CRI = [
    ("CRI I · Kanastra 1ª", "15/01/2024", "603,0",
     "1ª Super Sr 360,0 · 2ª Sr 90,0 · 3ª Mezz 108,0 · 4ª Sub 30,0 · 5ª Sub Jr privada 15,0",
     "1ª pré 11,51% · 2ª pré 12,74% · 3ª pré 16,48% · 4ª pré 20,95% · 5ª pré 9,86%",
     "n/d — Termo de Securitização não localizado. Deck reporta targets por camada 54/15/18/5/8"),
    ("CRI II · Kanastra 2ª", "25/06/2024", "750,0",
     "1ª Super Sr 487,5 · 2ª Sr 135,0 · 3ª Mezz 75,0 · 4ª Sub 30,0 · 5ª Sub Jr privada 22,5",
     "1ª pré 13,1926% · 2ª pré 14,5663% · 3ª 100% DI + 6,00% · 4ª 100% DI + 10,00% · 5ª pré 11,93%",
     "Razões de Cobertura: Super Sr 159% · Sr 123% · Mezz 110% · Sub 105% · Atraso de estoque máx. 15%"),
    ("CRI III · Kanastra 3ª", "28/05/2025", "750,0",
     "1ª Super Sr A 367,5 · 2ª Super Sr B 120,0 · 3ª Sr 135,0 · 4ª Mezz 75,0 · 5ª Sub 30,0 · 6ª Sub Jr privada 22,5",
     "1ª pré 15,50% · 2ª 105,50% do DI · 3ª pré 16,50% · 4ª 100% DI + 5,75% · 5ª 100% DI + 10,00% · 6ª pré 13,63%",
     "n/d — Termo de Securitização não localizado"),
    ("CRI IV · Kanastra 4ª", "28/09/2025", "450,0",
     "1ª Super Sr A 195,0 · 2ª Super Sr B 97,5 · 3ª Sr A 54,0 · 4ª Sr B 27,0 · 5ª Mezz 45,0 · 6ª Sub 18,0 · 7ª Sub Jr privada 13,5",
     "1ª e 2ª pré 14,2216% · 3ª e 4ª pré 15,3565% · 5ª 100% DI + 5,50% · 6ª 100% DI + 10,00% · 7ª pré 13,2480%",
     "n/d — Termo de Securitização não localizado"),
    ("CRI V · VERT 174ª", "20/05/2026", "470,6",
     "1ª Super Sr A 103,9 · 2ª Super Sr B 225,6 · 3ª Sr 70,6 · 4ª Mezz 37,6 · 5ª Sub 18,8 · 6ª Sub Jr privada 14,1",
     "1ª pré 14,8064% · 2ª 104,00% do DI · 3ª pré 15,7760% · 4ª 100% DI + 5,50% · 5ª 100% DI + 8,00% · 6ª pré 14,0650%",
     "n/d — Termo de Securitização não localizado"),
    ("CRI VI · VERT 177ª", "21/07/2026", "647,1",
     "1ª Sr A 100,0 · 2ª Sr B 450,0 · 3ª Mezz I 51,8 · 4ª Mezz II 25,9 · 5ª Sub Jr privada 19,4",
     "1ª 100% DI + 1,50% · 2ª 100% DI + 2,00% · 3ª 100% DI + 5,50% · 4ª 100% DI + 8,00% · 5ª 100% do DI",
     "Razões de Cobertura: Sr 120,48% · Mezz I 109,89% · Mezz II 105,26% · Atraso de estoque máx. 15%"),
]

NOTA_SUBORDINACAO = (
    "O índice aparece em duas formas distintas no programa e não são equivalentes. Nos FIDCs é um PISO "
    "DE SUBORDINAÇÃO TOTAL, medido como percentual do PL e somando mezanino e subordinada júnior — "
    "20% ou 25% conforme o fundo, e ausente no FIDC IV. Nos CRIs não existe piso percentual: a proteção "
    "é uma RAZÃO DE COBERTURA por camada, que divide o valor presente dos direitos creditórios líquido "
    "de PDD mais o ativo financeiro pelo saldo devedor daquela camada e de todas acima. São 159%/123%/"
    "110%/105% em CRI-II e 120,48%/109,89%/105,26% em CRI-VI. Um piso de 25% do PL e uma cobertura de "
    "120% do saldo medem coisas diferentes e não devem ser comparados diretamente."
)


# ══════════════════════════════════════════ QUADRO 3 — cronograma e runoff
import csv as _csv
import os as _os
from datetime import date as _date

_DATA = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      "data", "solfacil_claude")
_ROTULO = {"CRI-I": "CRI I · KAN 1ª", "CRI-II": "CRI II · KAN 2ª", "CRI-III": "CRI III · KAN 3ª",
           "CRI-IV": "CRI IV · KAN 4ª", "CRI-V": "CRI V · VERT 174ª", "CRI-VI": "CRI VI · VERT 177ª",
           "DEB-I": "Debênture"}
_INICIO = (2026, 2)          # 2T26


def _tri(d):
    return (d.year, (d.month - 1) // 3 + 1)


def _rot_tri(t):
    return f"{t[1]}T{str(t[0])[2:]}"


def _seq_tri(t0, t1):
    out, t = [], t0
    while t <= t1:
        out.append(t)
        t = (t[0] + 1, 1) if t[1] == 4 else (t[0], t[1] + 1)
    return out


def _carrega_series():
    with open(_os.path.join(_DATA, "02_series.csv"), encoding="utf-8") as fh:
        return [x for x in _csv.DictReader(fh)
                if not x["veiculo_id"].startswith("FIDC")
                and x["montante_reportado_deck_Rmi"] not in ("n/d", "")
                and x["data_vencimento"] not in ("n/d", "")]


def _pmt_cri2_serie1():
    """Único cronograma contratual de principal do acervo: CRI-II, 1ª série."""
    caminho = _os.path.join(_DATA, "raw_anexo1_cri2_kanastra.csv")
    if not _os.path.exists(caminho):
        return {}
    saldo, por_tri = 487.5, {}
    with open(caminho, encoding="utf-8") as fh:
        for row in _csv.DictReader(fh):
            if row["serie"] != "1ª" or row["paga_amortizacao"] != "sim":
                continue
            p = row["pct_amortizacao_do_saldo"]
            if p in ("n/d", ""):
                continue
            d = row["data"]
            if d == "Data de Vencimento":
                dt = _date(2029, 6, 7)
            else:
                dd, mm, aa = d.split("/")
                dt = _date(int(aa), int(mm), int(dd))
            valor = saldo * float(p) / 100.0
            saldo -= valor
            por_tri[_tri(dt)] = por_tri.get(_tri(dt), 0.0) + valor
    return por_tri


def monta_cronograma():
    series = _carrega_series()
    venc = {}
    for x in series:
        a, m, _ = x["data_vencimento"].split("-")
        t = _tri(_date(int(a), int(m), 1))
        vid = x["veiculo_id"]
        venc.setdefault(t, {}).setdefault(vid, 0.0)
        venc[t][vid] += float(x["montante_reportado_deck_Rmi"])
    tris = _seq_tri(_INICIO, max(venc))
    pmt2 = _pmt_cri2_serie1()
    total = sum(float(x["montante_reportado_deck_Rmi"]) for x in series)
    ja_venceu = sum(v for t, d in venc.items() if t < _INICIO for v in d.values())
    saldo = total - ja_venceu
    linhas, runoff = [], []
    for t in tris:
        d = venc.get(t, {})
        venc_tri = sum(d.values())
        saldo_ini = saldo
        saldo -= venc_tri
        linhas.append([_rot_tri(t),
                       f"{saldo_ini:,.1f}".replace(",", "."),
                       f"{venc_tri:,.1f}".replace(",", ".") if venc_tri else "—",
                       f"{pmt2.get(t, 0.0):,.1f}".replace(",", ".") if pmt2.get(t) else ND,
                       f"{saldo:,.1f}".replace(",", "."),
                       ", ".join(_ROTULO.get(k, k) for k in sorted(d)) or "—"])
        runoff.append((_rot_tri(t), saldo_ini, venc_tri, pmt2.get(t, 0.0),
                       {k: v for k, v in d.items()}))
    return linhas, runoff, total, ja_venceu


CRONO_COLS = ["Trimestre", "Saldo inicial (R$ mm)", "Vencimento legal no tri (R$ mm)",
              "PMT contratual documentada (R$ mm)", "Saldo final (R$ mm)", "Instrumentos que vencem"]
CRONOGRAMA, RUNOFF, TOTAL_CRI, JA_VENCIDO = monta_cronograma()

NOTA_CRONOGRAMA = (
    "A coluna de vencimento legal é documentada para as 34 séries de CRI e as 2 séries de debênture. "
    "A coluna de PMT contratual só existe para a 1ª série de CRI-II, único cronograma de principal do "
    "acervo — o Anexo I das demais séries traz apenas calendário de datas, porque elas amortizam até um "
    "Saldo Devedor Target, não até um percentual fixo. Os FIDCs não entram: suas cotas não têm data de "
    "vencimento publicada. O saldo remanescente é limite superior de exposição, não expectativa de "
    "recebimento: assume que nenhuma série amortiza antes do vencimento legal."
)
