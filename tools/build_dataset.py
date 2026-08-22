# -*- coding: utf-8 -*-
"""Gera a camada de dados auditavel em data/Solfácil/*.csv.

Todo número dos entregaveis nasce aqui. Nada e digitado direto no Excel ou no PPTX.
"""
import csv, os, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "solfacil_claude")
sys.path.insert(0, HERE)

import solfacil_fontes as F
import solfacil_veiculos as V
import solfacil_series as S
import solfacil_criterios as C
import solfacil_estrutura as E
import solfacil_mercado as M
import solfacil_sintese as Z
import solfacil_funding as FU

ND = "n/d"


def write(name, cols, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            assert len(r) == len(cols), f"{name}: linha com {len(r)} campos, esperado {len(cols)}"
            w.writerow(r)
    print(f"  {name:36s} {len(rows):4d} linhas x {len(cols):2d} colunas")
    return rows


def num(x):
    """Converte para float apenas se for número de verdade; n/d nunca vira zero."""
    if x in (ND, "", None) or not isinstance(x, str):
        return None
    t = x.replace(".", "").replace(",", ".") if x.count(",") == 1 and x.count(".") <= 1 else x
    try:
        return float(t)
    except ValueError:
        try:
            return float(x)
        except ValueError:
            return None


print("Gerando camada de dados em data/Solfácil/ ...")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- diretos
write("17_fontes.csv", F.FONTES_COLS, F.FONTES)
write("01_veiculos.csv", V.VEICULOS_COLS, V.VEICULOS)
write("02_series.csv", S.SERIES_COLS, S.SERIES)
write("03_elegibilidade.csv", C.ELEGIBILIDADE_COLS, C.ELEGIBILIDADE)
write("03b_elegibilidade_deltas.csv", C.ELEGIBILIDADE_DELTAS_COLS, C.ELEGIBILIDADE_DELTAS)
write("04_concentracao.csv", C.CONCENTRACAO_COLS, C.CONCENTRACAO)
write("06_waterfall.csv", E.WATERFALL_COLS, E.WATERFALL)
write("06b_waterfall_degraus.csv", E.WATERFALL_DEGRAUS_COLS, E.WATERFALL_DEGRAUS)
write("07_subordinada.csv", E.SUBORDINADA_COLS, E.SUBORDINADA)
write("08_pdd.csv", E.PDD_COLS, E.PDD)
write("09_eventos.csv", E.EVENTOS_COLS, E.EVENTOS)
write("09b_garantias.csv", E.GARANTIAS_COLS, E.GARANTIAS)
write("10_subscritores_longa.csv", M.SUBS_LONGA_COLS, M.SUBS_LONGA)
write("10b_subscritores_agregado.csv", M.SUBS_AGREGADO_COLS, M.SUBS_AGREGADO)
write("11_matriz_fidc_cri.csv", M.MATRIZ_COLS, M.MATRIZ)
write("11b_cessoes.csv", M.CESSOES_COLS, M.CESSOES)
write("12_custo_captacao.csv", M.CUSTO_COLS, M.CUSTO)
write("12b_spread_por_camada.csv", M.SPREAD_CAMADA_COLS, M.SPREAD_CAMADA)
write("14_antes_depois.csv", Z.ANTES_DEPOIS_COLS, Z.ANTES_DEPOIS)
write("15_fidc_vs_cri.csv", Z.VEREDITO_COLS, Z.VEREDITO)
write("16_conflitos.csv", Z.CONFLITOS_COLS, Z.CONFLITOS)
write("18_metodologia.csv", Z.METODOLOGIA_COLS, Z.METODOLOGIA)
write("19_glossario.csv", Z.GLOSSARIO_COLS, Z.GLOSSARIO)
write("20_lacunas.csv", Z.LACUNAS_COLS, Z.LACUNAS)

# ---------------------------------------------------------------- 05_Prazos_WAM (derivado)
# Confronta, na mesma escala de meses, o teto do ativo contra o prazo do passivo.
IDX = {c: i for i, c in enumerate(S.SERIES_COLS)}
ELEG_IDX = {c: i for i, c in enumerate(C.ELEGIBILIDADE_COLS)}
eleg_by_v = {r[0]: r for r in C.ELEGIBILIDADE}

prazos_cols = [
    "veiculo_id", "tipo", "série", "camada", "wam_contratual_max_dias", "wam_contratual_max_meses",
    "wam_observado_dias", "prazo_max_recebivel_dias", "prazo_max_recebivel_meses",
    "data_emissão", "vencimento_do_veiculo", "prazo_legal_da_serie_meses",
    "duration_dias", "duration_meses", "gap_duration_vs_prazo_legal_meses",
    "gap_prazo_max_recebivel_vs_duration_meses", "periodo_revolvencia_meses",
    "inicio_amortizacao", "fonte_id",
]
prazos = []
for r in S.SERIES:
    vid = r[IDX["veiculo_id"]]
    tipo = "CRI" if vid.startswith("CRI") else "FIDC"
    el = eleg_by_v.get(vid)
    wam_d = el[ELEG_IDX["wam_max_dias"]] if el else ND
    prz_d = el[ELEG_IDX["prazo_max_recebivel_dias"]] if el else ND
    prz_m = el[ELEG_IDX["prazo_max_recebivel_meses"]] if el else ND
    wam_m = ND
    w = num(wam_d)
    if w:
        wam_m = f"{w / 30.4375:.1f}"
    dur_d = r[IDX["duration_dias"]]
    dur_m = ND
    d = num(dur_d)
    if d:
        dur_m = f"{d / 30.4375:.1f}"
    legal = r[IDX["prazo_meses"]]
    gap_dur_legal = ND
    lg = num(legal)
    if d and lg:
        gap_dur_legal = f"{lg - d / 30.4375:.1f}"
    gap_ativo_dur = ND
    pm = num(prz_m)
    if d and pm:
        gap_ativo_dur = f"{pm - d / 30.4375:.1f}"
    revolv = "12" if vid == "FIDC-VII" else ("0 - pool fechado na cessão" if tipo == "CRI" else ND)
    prazos.append([
        vid, tipo, r[IDX["serie"]], r[IDX["camada"]], wam_d, wam_m, ND, prz_d, prz_m,
        r[IDX["data_emissao"]], r[IDX["data_vencimento"]], legal, dur_d, dur_m,
        gap_dur_legal, gap_ativo_dur, revolv, ND, r[IDX["fonte_id"]],
    ])
write("05_prazos_wam.csv", prazos_cols, prazos)

# ---------------------------------------------------------------- 10c_Concentracao de subscritores (derivado)
# Categoria nao e titular: so quando a categoria tem exatamente 1 subscritor o numero mede um titular unico.
SL = {c: i for i, c in enumerate(M.SUBS_LONGA_COLS)}
por_serie = {}
for r in M.SUBS_LONGA:
    key = (r[SL["veiculo_id"]], r[SL["serie"]], r[SL["camada"]])
    por_serie.setdefault(key, []).append((r[SL["tipo_de_investidor"]], int(r[SL["numero_de_subscritores"]]), int(r[SL["quantidade_subscrita"]])))

conc_cols = ["veiculo_id", "série", "camada", "qtd_total", "total_subscritores",
             "maior_categoria", "maior_categoria_qtd", "maior_categoria_pct",
             "maior_titular_unico_categoria", "maior_titular_unico_qtd", "maior_titular_unico_pct",
             "pct_varejo_PF", "ticket_medio_PF_R", "data_base", "fonte_id"]
conc = []
for (vid, serie, camada), itens in por_serie.items():
    total_q = sum(q for _, _, q in itens)
    total_s = sum(n for _, n, _ in itens)
    maior = max(itens, key=lambda x: x[2])
    unicos = [x for x in itens if x[1] == 1]
    mu = max(unicos, key=lambda x: x[2]) if unicos else None
    pf = next(x for x in itens if x[0] == "Pessoas naturais")
    conc.append([
        vid, serie, camada, str(total_q), str(total_s),
        maior[0], str(maior[2]), f"{100 * maior[2] / total_q:.1f}",
        mu[0] if mu else ND, str(mu[2]) if mu else ND,
        f"{100 * mu[2] / total_q:.1f}" if mu else ND,
        f"{100 * pf[2] / total_q:.1f}",
        f"{1000 * pf[2] / pf[1]:.0f}" if pf[1] else ND,
        "2024-02-23", "ANX-ENC-K1",
    ])
write("10c_concentracao_subscritores.csv", conc_cols, conc)

# ---------------------------------------------------------------- 13_Cronograma (Anexo I de CRI-II + realizado)
raw_path = os.path.join(OUT, "raw_anexo1_cri2_kanastra.csv")
crono_cols = ["veiculo_id", "série", "camada", "n_pagamento", "competência", "status",
              "paga_amortizacao", "pct_amortizacao_do_saldo", "saldo_final_pct_do_VNU",
              "paga_remuneracao", "atinge_98pct_amortizado", "fonte_id"]
crono = []
CAMADA_CRI2 = {"1ª": "Super Sênior", "2ª": "Sênior", "3ª": "Mezanino",
                "4ª": "Subordinado", "5ª": "Subordinado Jr."}
if os.path.exists(raw_path):
    with open(raw_path, encoding="utf-8") as fh:
        saldo = {}
        for row in csv.DictReader(fh):
            s = row["serie"]
            saldo.setdefault(s, 100.0)
            pct = row["pct_amortizacao_do_saldo"]
            p = num(pct)
            if p is not None and row["paga_amortizacao"] == "sim":
                saldo[s] = saldo[s] * (1 - p / 100.0)
                saldo_txt = f"{saldo[s]:.4f}"
                pct_txt = f"{p:.4f}"
            else:
                saldo_txt = f"{saldo[s]:.4f}" if p is not None or row["paga_amortizacao"] == "não" else ND
                pct_txt = pct if pct != "n/d" else ND
                if pct == "n/d":
                    saldo_txt = ND
            atinge = "sim" if (saldo_txt != ND and float(saldo_txt) <= 2.0) else ("não" if saldo_txt != ND else ND)
            crono.append([
                "CRI-II", s, CAMADA_CRI2[s], row["n_pagamento"], row["data"], "Projetado",
                row["paga_amortizacao"], pct_txt, saldo_txt, row["paga_remuneracao"], atinge, "ANX-TS2-K2",
            ])
write("13_cronograma_pagamentos.csv", crono_cols, crono)

# Realizado observado, agregado por camada (deck A3) - não há serie mensal publica
real_cols = ["veiculo_id", "camada", "primeira_ocorrencia", "ultima_ocorrencia", "meses_com_pagamento",
             "total_amortizado_Rmi", "maximo_mensal_Rmi", "status", "fonte_id"]
REALIZADO = [
    ("FIDC-I", "Subordinado Jr.", "2022-02-28", "2026-07-31", "41", "45.3", "2.1", "Realizado", "ANX-DECK"),
    ("FIDC-I", "Mezanino", "2024-01-31", "2026-07-31", "28", "85.1", "7.4", "Realizado", "ANX-DECK"),
    ("FIDC-II", "Subordinado Jr.", "2022-08-31", "2026-02-28", "20", "118.8", "13.8", "Realizado", "ANX-DECK"),
    ("FIDC-II", "Mezanino", "2023-12-31", "2026-04-30", "19", "42.0", "19.1", "Realizado", "ANX-DECK"),
    ("FIDC-III", "Subordinado Jr.", "2025-01-31", "2026-07-31", "18", "26.0", "3.2", "Realizado", "ANX-DECK"),
    ("FIDC-III", "Mezanino", "2024-04-30", "2026-07-31", "25", "75.4", "5.2", "Realizado", "ANX-DECK"),
    ("FIDC-IV", "Subordinado Jr.", "2022-07-31", "2025-11-30", "21", "159.4", "86.7", "Realizado", "ANX-DECK"),
    ("FIDC-IV", "Mezanino", "2023-12-31", "2025-08-31", "12", "279.5", "151.4", "Realizado", "ANX-DECK"),
    ("FIDC-V", "Subordinado Jr.", "2023-03-31", "2026-02-28", "6", "11.6", "3.4", "Realizado", "ANX-DECK"),
    ("FIDC-V", "Mezanino", "2023-12-31", "2026-07-31", "26", "22.8", "6.0", "Realizado", "ANX-DECK"),
    ("FIDC-VI", "Subordinado Jr.", "2025-12-31", "2026-06-30", "2", "35.2", "29.0", "Realizado", "ANX-DECK"),
    ("FIDC-VI", "Mezanino", "2025-03-31", "2026-06-30", "15", "148.1", "111.4", "Realizado", "ANX-DECK"),
    ("FIDC-VII", "Subordinado Jr.", "2026-07-31", "2026-07-31", "1", "7.7", "7.7", "Realizado", "ANX-DECK"),
    ("CRI-I", "Sênior", "2024-04-01", "2026-06-01", "27", "268.4", "16.8", "Realizado", "ANX-DECK"),
    ("CRI-I", "Mezanino", "2024-09-01", "2026-06-01", "22", "77.7", "6.5", "Realizado", "ANX-DECK"),
    ("CRI-I", "Subordinado", "2025-07-01", "2026-06-01", "12", "22.5", "7.4", "Realizado", "ANX-DECK"),
    ("CRI-II", "Sênior", "2024-09-01", "2026-05-01", "19", "258.7", "18.5", "Realizado", "ANX-DECK"),
    ("CRI-II", "Mezanino", "2025-01-01", "2026-05-01", "15", "31.7", "6.4", "Realizado", "ANX-DECK"),
    ("CRI-II", "Subordinado", "2025-09-01", "2026-05-01", "9", "7.8", "2.6", "Realizado", "ANX-DECK"),
    ("CRI-II", "Subordinado Jr.", "2025-10-01", "2026-05-01", "8", "6.8", "1.4", "Realizado", "ANX-DECK"),
    ("CRI-III", "Sênior", "2025-08-01", "2026-05-01", "10", "156.1", "21.4", "Realizado", "ANX-DECK"),
    ("CRI-III", "Mezanino", "2026-02-01", "2026-05-01", "4", "6.6", "1.7", "Realizado", "ANX-DECK"),
    ("CRI-III", "Subordinado", "2026-02-01", "2026-05-01", "4", "8.3", "3.2", "Realizado", "ANX-DECK"),
    ("CRI-IV", "Sênior", "2025-12-01", "2026-05-01", "6", "56.8", "6.7", "Realizado", "ANX-DECK"),
]
write("13b_amortizacao_realizada.csv", real_cols, REALIZADO)


# ---------------------------------------------------------------- 21_Funding por tranche (derivado)
# Uma linha por tranche de TODOS os instrumentos: cota de FIDC, série de CRI e série de debênture.
# Valor captado e preço lado a lado, com a família de indexador que torna a comparação honesta.
IX = {c: i for i, c in enumerate(S.SERIES_COLS)}
TIPO = {"FIDC": "FIDC (warehouse)", "CRI": "CRI (take-out)", "DEB": "Debênture"}
fund_cols = ["ordem_cronologica", "data_emissão", "instrumento", "veiculo_id", "camada", "série",
             "montante_captado_Rmi", "familia_indexador", "preco_taxa_contratada",
             "colocação", "retida_pelo_originador", "fonte_id", "status"]
fund = []
for r in S.SERIES:
    vid = r[IX["veiculo_id"]]
    inst = TIPO["FIDC" if vid.startswith("FIDC") else ("CRI" if vid.startswith("CRI") else "DEB")]
    montante = r[IX["montante_reportado_deck_Rmi"]]
    fund.append([r[IX["data_emissao"]] or ND, r[IX["data_emissao"]], inst, vid,
                 r[IX["camada"]], r[IX["serie"]], montante, r[IX["indexador"]],
                 r[IX["taxa_contratada"]], r[IX["colocacao"]], r[IX["retida_pelo_originador"]],
                 r[IX["fonte_id"]], r[IX["status"]]])
fund.sort(key=lambda x: (x[1] if x[1] != ND else "9999"))
for i, linha in enumerate(fund, 1):
    linha[0] = str(i)
write("21_funding_por_tranche.csv", fund_cols, fund)

# ---------------------------------------------------------------- 22_Custo senior no tempo
write("22_custo_senior_timeline.csv", FU.CUSTO_SENIOR_COLS, FU.CUSTO_SENIOR)

# ---------------------------------------------------------------- 23/24 Debenture
write("23_debenture_posicao.csv", FU.DEBENTURE_POSICAO_COLS, FU.DEBENTURE_POSICAO)
write("24_debenture_carteira.csv", FU.DEBENTURE_CARTEIRA_COLS, FU.DEBENTURE_CARTEIRA)

# ---------------------------------------------------------------- 25_Captacao por instrumento e ano
por_ano = {}
for linha in fund:
    d, inst, m = linha[1], linha[2], linha[6]
    if d == ND or m in (ND, ""):
        continue
    ano = d[:4]
    por_ano.setdefault((ano, inst), 0.0)
    por_ano[(ano, inst)] += float(m)
cap_cols = ["ano", "instrumento", "montante_captado_Rmi", "numero_de_tranches"]
cont = {}
for linha in fund:
    d, inst, m = linha[1], linha[2], linha[6]
    if d == ND or m in (ND, ""):
        continue
    cont[(d[:4], inst)] = cont.get((d[:4], inst), 0) + 1
cap = [[a, i, f"{v:.3f}", str(cont[(a, i)])] for (a, i), v in sorted(por_ano.items())]
write("25_captacao_por_ano.csv", cap_cols, cap)

# ---------------------------------------------------------------- 00_Painel
painel_cols = ["indicador", "valor", "unidade", "leitura", "data_base", "fonte_id"]
PAINEL = [
    ("Veículos no programa", "14", "veículos", "Sete FIDCs de warehouse, seis operações de CRI de take-out e uma debênture de 2022", "2026-08-21", "ANX-DECK; ANX-ESC-DEB"),
    ("Tranches precificadas", "70", "tranches", "34 classes de cotas de FIDC, 34 séries de CRI e 2 séries de debênture, cada uma com valor captado e preço", "2026-08-22", "ANX-TS-V177; ANX-ESC-DEB"),
    ("Spread sênior mais baixo do programa", "DI + 1,50%", "% a.a.", "Sênior A da 177ª emissão de CRI, em julho de 2026, contra DI + 2,00% do FIDC VII que a alimenta", "2026-07-21", "ANX-TS-V177"),
    ("Séries de CRI", "34", "séries", "5+5+6+7+6+5 nas seis operações, incluindo a série privada de cada uma", "2026-08-21", "ANX-DECK; ANX-LAM-K1; ANX-INI-K4"),
    ("Classes de cotas de FIDC", "34", "classes", "Coincidência numérica com as séries de CRI; são dimensões diferentes e não se somam", "2026-07-31", "ANX-DECK"),
    ("Volume nominal de CRI emitido", "3.670,6", "R$ mi", "Soma das seis operações, séries públicas e privadas, agora toda documentada por série", "2026-08-21", "ANX-DECK"),
    ("Séries privadas Subordinado Jr.", "107,0", "R$ mi", "De 2,49% a 3,00% de cada operação, subscritas pela Solfácil e/ou partes relacionadas", "2026-08-21", "ANX-DECK"),
    ("PL somado dos sete FIDCs", "1.234,6", "R$ mi", "Competência de julho de 2026", "2026-07-31", "ANX-DECK"),
    ("Carteira somada dos sete FIDCs", "986,7", "R$ mi", "Direitos creditórios; a diferença para o PL são outros ativos líquidos", "2026-07-31", "ANX-DECK"),
    ("Cap por devedor mais apertado", "0,07", "% do Patrimônio Separado", "CRI-V, a partir de 750.000 quantidades integralizadas", "2026-04-17", "ANX-LAM-V174"),
    ("WAM contratual máximo", "2.000", "dias", "Igual nas seis operações de CRI; 2.400 dias em três dos sete FIDCs", "2026-08-21", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Prazo máximo por recebível", "3.845", "dias", "126,4 meses, contados da emissão da CCB, nas seis operações", "2026-08-21", "ANX-LAM-K3; ANX-LAM-V174"),
    ("Principal subordinado já pago nos FIDCs", "1.076,2", "R$ mi", "Mezanino e júnior somados; ocorreu nos sete fundos", "2026-07-31", "ANX-DECK"),
    ("Operações com informe mensal de CRI", "5 de 6", "operações", "A VERT 177ª ainda não tem informe", "2026-08-21", "ANX-DECK"),
]
write("00_painel.csv", painel_cols, PAINEL)

# ---------------------------------------------------------------- checagens
print("\nChecagens de integridade:")
tot_series_cri = len([r for r in S.SERIES if r[0].startswith("CRI")])
print(f"  séries de CRI: {tot_series_cri} (esperado 34) -> {'OK' if tot_series_cri == 34 else 'FALHA'}")
soma_deck = sum(num(r[IDX['montante_reportado_deck_Rmi']]) or 0 for r in S.SERIES if r[0].startswith("CRI"))
print(f"  soma dos montantes reportados por série de CRI: R$ {soma_deck:,.1f} mi (deck: 3.670,7 mi, com CRI-VI n/d por série)")
fontes_ids = {r[0] for r in F.FONTES}
usados = set()
for rows, ci in [(S.SERIES, IDX['fonte_id']), (C.ELEGIBILIDADE, 25), (E.PDD, 19), (M.MATRIZ, 4)]:
    for r in rows:
        for f in str(r[ci]).split(";"):
            f = f.strip()
            if f and f not in ("n/a", ND):
                usados.add(f)
orfaos = sorted(usados - fontes_ids)
print(f"  fonte_id orfaos (usados e não inventariados): {orfaos if orfaos else 'nenhum'}")
print("\nCamada de dados concluida.")
