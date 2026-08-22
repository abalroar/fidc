#!/usr/bin/env python3
"""Build the auditable Solfacil CSV layer from official CVM files and documents.

The script intentionally preserves missing values as the literal ``n/d`` and
adds a source/status/method trail to every analytical row.  Office artifacts
consume only the CSV files emitted here.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd


ACCESS_DATE = "2026-08-22"
FIDC_BASE = "2026-07-31"
ND = "n/d"


def norm_cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 15 and digits.endswith("0") and str(value).endswith(".0"):
        digits = digits[:-1]
    return digits.zfill(14) if digits else ""


def num(value: object):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def nz(value: object, default=0.0) -> float:
    parsed = num(value)
    return default if parsed is None else parsed


def nd(value: object):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ND
    if isinstance(value, str) and not value.strip():
        return ND
    return value


def iso(value: object):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ND
    parsed = pd.to_datetime(value, errors="coerce")
    return ND if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def months_between(start: str, end: str):
    if start == ND or end == ND:
        return ND
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    return round((b - a).days / 30.4375, 1)


def pct(numerator: object, denominator: object):
    n, d = num(numerator), num(denominator)
    if n is None or d in (None, 0):
        return ND
    return n / d


def source_join(*ids: str) -> str:
    ordered=[]
    for value in ids:
        if value and value not in ordered:
            ordered.append(value)
    return " | ".join(ordered)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", encoding="latin1", low_memory=False)


def read_zip_member(zip_path: Path, contains: str) -> pd.DataFrame | None:
    if not zip_path.exists():
        return None
    pattern = re.compile(re.escape(contains) + r"(?:\d{2})?\.csv$", re.IGNORECASE)
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(n for n in zf.namelist() if pattern.search(n))
        if not names:
            return None
        frames = [pd.read_csv(io.BytesIO(zf.read(name)), sep=";", encoding="latin1", low_memory=False) for name in names]
    return pd.concat(frames, ignore_index=True)


def write_csv(outdir: Path, stem: str, rows: list[dict], columns: list[str] | None = None) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{stem}.csv"
    if not rows:
        if not columns:
            raise ValueError(f"No rows or columns for {stem}")
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")
        return
    frame = pd.DataFrame(rows)
    if columns:
        for col in columns:
            if col not in frame:
                frame[col] = ND
        frame = frame[columns]
    frame = frame.where(pd.notna(frame), ND)
    frame.to_csv(path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)


FIDCS = {
    "FIDC_I": {
        "cnpj": "36771685000117", "nome": "Solfácil FIDC I", "inicio": "2020-12-21",
        "admin": "Banco Daycoval S.A.", "gestor": "Angá Administração de Recursos Ltda.",
        "custodiante": "Banco Daycoval S.A.", "auditor": "EY",
        "reg_src": "DOC_FIDC_I_REG_202411", "rating": "Austin Rating", "rating_nota": "A+ (deck; vínculo por classe n/d)",
    },
    "FIDC_II": {
        "cnpj": "42462306000100", "nome": "Solfácil FIDC II", "inicio": "2021-10-08",
        "admin": "Banco Genial S.A.", "gestor": "Angá Administração de Recursos Ltda.",
        "custodiante": "Banco Genial S.A.", "auditor": "KPMG",
        "reg_src": "DOC_FIDC_II_REG_202412", "rating": "Austin Rating", "rating_nota": "BBB (deck; vínculo por classe n/d)",
    },
    "FIDC_III": {
        "cnpj": "49920525000134", "nome": "Solfácil FIDC III", "inicio": "2023-07-04",
        "admin": "Banco Daycoval S.A.", "gestor": "Régia Capital Ltda.",
        "custodiante": "Banco Daycoval S.A.", "auditor": "PwC",
        "reg_src": "DOC_FIDC_III_REG_202512", "rating": "Fitch", "rating_nota": "AAA (deck; vínculo por classe n/d)",
    },
    "FIDC_IV": {
        "cnpj": "44909456000144", "nome": "Solfácil FIDC IV", "inicio": "2022-07-15",
        "admin": "Banco Genial S.A.", "gestor": "Genial Gestão Ltda.",
        "custodiante": "Banco Genial S.A.", "auditor": "KPMG",
        "reg_src": "DOC_FIDC_IV_REG_202510", "rating": "Moody's", "rating_nota": "AAA (deck; vínculo por classe n/d)",
    },
    "FIDC_V": {
        "cnpj": "47240785000133", "nome": "Solfácil FIDC V", "inicio": "2023-02-06",
        "admin": "Banco Daycoval S.A.", "gestor": "Angá Administração de Recursos Ltda.",
        "custodiante": "Banco Daycoval S.A.", "auditor": "RSM",
        "reg_src": "DOC_FIDC_V_REG_202411", "rating": "Austin Rating", "rating_nota": "A (deck; vínculo por classe n/d)",
    },
    "FIDC_VI": {
        "cnpj": "57028406000108", "nome": "Solfácil FIDC VI", "inicio": "2024-11-06",
        "admin": "Limine Trust DTVM Ltda.", "gestor": "Régia Capital Ltda.",
        "custodiante": "Limine Trust DTVM Ltda.", "auditor": "Next Auditores",
        "reg_src": "DOC_FIDC_VI_REG_202605", "rating": ND, "rating_nota": ND,
    },
    "FIDC_VII": {
        "cnpj": "63505455000189", "nome": "Solfácil FIDC VII", "inicio": "2026-01-13",
        "admin": "Genial Investimentos CVM S.A.", "gestor": "Angá Administração de Recursos Ltda.",
        "custodiante": "Banco Genial S.A.", "auditor": "Deloitte",
        "reg_src": "DOC_FIDC_VII_REG_202605", "rating": "Moody's", "rating_nota": "AA+ (1ª série sênior)",
    },
}


CRIS = {
    "CRI_K1": {"nome": "CRI Solfácil — Kanastra 1ª emissão", "securitizadora": "Kanastra Securitizadora S.A.", "emissao": "2024-01-15", "publico": 588_000_000, "total": 603_000_000, "code": "BRKNSTCRI000", "latest": "2026-06-01", "offer_req": 4201, "source": "ANX_CRI1_PROSP_20240216"},
    "CRI_K2": {"nome": "CRI Solfácil — Kanastra 2ª emissão", "securitizadora": "Kanastra Securitizadora S.A.", "emissao": "2024-06-25", "publico": 727_500_000, "total": 750_000_000, "code": "BRKNSTCRI059", "latest": "2026-05-01", "offer_req": 15843, "source": "ANX_CRI2_RATING_202406"},
    "CRI_K3": {"nome": "CRI Solfácil — Kanastra 3ª emissão", "securitizadora": "Kanastra Securitizadora S.A.", "emissao": "2025-05-28", "publico": 727_500_000, "total": 750_000_000, "code": "BRKNSTCRI0A4", "latest": "2026-05-01", "offer_req": 20290, "source": "ANX_CRI3_LAM_PREL_20250422"},
    "CRI_K4": {"nome": "CRI Solfácil — Kanastra 4ª emissão", "securitizadora": "Kanastra Securitizadora S.A.", "emissao": "2025-09-28", "publico": 436_500_000, "total": 450_000_000, "code": "BRKNSTCRI0G1", "latest": "2026-05-01", "offer_req": 22096, "source": "ANX_CRI4_INICIO_20250929"},
    "CRI_V174": {"nome": "CRI Solfácil — VERT 174ª emissão", "securitizadora": "VERT Companhia Securitizadora", "emissao": "2026-05-20", "publico": 456_481_000, "total": 470_603_821.89, "code": "BRVERTCRIDZ7", "latest": "2026-06-01", "offer_req": 25971, "source": "ANX_CRIV_LAM_PREL_20260417"},
    "CRI_V177": {"nome": "CRI Solfácil — VERT 177ª emissão", "securitizadora": "VERT Companhia Securitizadora", "emissao": "2026-07-21", "publico": 627_647_000, "total": 647_059_000, "code": "BRVERTCRIEC4", "latest": ND, "offer_req": 27183, "source": "CVM_FUNDOSNET_VERT177_20260720"},
}


CRI_SERIES = {
    "CRI_K1": [
        (1,"Super Sênior",360_000_000,"BRKNSTCRI000","2031-01-15","Pré","11,51% a.a.","Fitch","AA+sf(bra)","pública"),
        (2,"Sênior",90_000_000,"BRKNSTCRI018","2032-01-15","Pré","12,74% a.a.","Fitch","AAsf(bra)","pública"),
        (3,"Mezanino",108_000_000,"BRKNSTCRI026","2034-01-15","Pré","16,48% a.a. (número; extenso 17,48%)",ND,ND,"pública"),
        (4,"Subordinada",30_000_000,"BRKNSTCRI034","2034-01-15","Pré","20,95% a.a.",ND,ND,"pública"),
        (5,"Júnior/Subordinada",15_000_000,"BRKNSTCRI042","2036-01-15","Pré + residual","9,86% a.a. + prêmio residual",ND,ND,"privada"),
    ],
    "CRI_K2": [
        (1,"Super Sênior",487_500_000,"BRKNSTCRI059","2029-06-07","Pré","13,1926% a.a.","Fitch / Moody's","AA+ / AAA","pública"),
        (2,"Sênior",135_000_000,"BRKNSTCRI067","2032-06-07","Pré","14,5663% a.a.","Fitch / Moody's","A / AA-","pública"),
        (3,"Mezanino",75_000_000,"BRKNSTCRI075","2034-06-07","DI+","DI + 6,00% a.a.",ND,ND,"pública"),
        (4,"Subordinada",30_000_000,"BRKNSTCRI083","2034-06-07","DI+","DI + 10,00% a.a.",ND,ND,"pública"),
        (5,"Júnior/Subordinada",22_500_000,"BRKNSTCRI091",ND,"Residual",ND,ND,ND,"privada"),
    ],
    "CRI_K3": [
        (1,"Super Sênior A",367_500_000,"BRKNSTCRI0A4","2030-05-08","Pré",ND,"Moody's","AAA","pública"),
        (2,"Super Sênior B",120_000_000,"BRKNSTCRI0B2","2030-05-08","DI%",ND,"Moody's","AAA","pública"),
        (3,"Sênior",135_000_000,"BRKNSTCRI0C0","2033-05-06","Pré",ND,"Moody's","AA-","pública"),
        (4,"Mezanino",75_000_000,"BRKNSTCRI0D8","2035-05-08","DI+",ND,ND,ND,"pública"),
        (5,"Subordinada",30_000_000,"BRKNSTCRI0E6","2035-05-08","DI+",ND,ND,ND,"pública"),
        (6,"Júnior/Subordinada",22_500_000,"BRKNSTCRI0F3","2037-05-08","Residual",ND,ND,ND,"privada"),
    ],
    "CRI_K4": [
        (1,"Super Sênior A",195_000_000,"BRKNSTCRI0G1","2030-09-20","Pré","14,2216% a.a.","Moody's","AAA","pública"),
        (2,"Super Sênior B",97_500_000,"BRKNSTCRI0K3","2030-09-20","Pré","14,2216% a.a.","Moody's","AAA","pública"),
        (3,"Sênior A",54_000_000,"BRKNSTCRI0H9","2033-09-22","Pré","15,3565% a.a.","Moody's","AA-","pública"),
        (4,"Sênior B",27_000_000,"BRKNSTCRI0M9","2033-09-22","Pré","15,3565% a.a.","Moody's","AA-","pública"),
        (5,"Mezanino",45_000_000,"BRKNSTCRI0I7","2035-09-24","DI+","DI + 5,50% a.a.",ND,ND,"pública"),
        (6,"Subordinada",18_000_000,"BRKNSTCRI0J5","2035-09-24","DI+","DI + 10,00% a.a.",ND,ND,"pública"),
        (7,"Júnior/Subordinada",13_500_000,"BRKNSTCRI0N7","2037-09-22","Pré + residual","13,2480% a.a. + residual",ND,ND,"privada"),
    ],
    "CRI_V174": [
        (1,"Super Sênior A",103_870_000,"BRVERTCRIDZ7","2031-05-20","Pré","14,81% a.a.","Moody's","AAA","pública"),
        (2,"Super Sênior B",225_550_000,"BRVERTCRIE08","2031-05-20","DI%","104,00% do DI", "Moody's","AAA","pública"),
        (3,"Sênior",70_590_000,"BRVERTCRIE16","2034-05-22","Pré","15,78% a.a.","Moody's","AA-","pública"),
        (4,"Mezanino",37_647_000,"BRVERTCRIE24","2036-05-20","DI+","DI + 5,50% a.a.",ND,ND,"pública"),
        (5,"Subordinada",18_828_821.89,"BRVERTCRIE32","2036-05-20","DI+","DI + 8,00% a.a.",ND,ND,"pública"),
        (6,"Júnior/Subordinada",14_118_000,"BRVERTCRIE40","2038-05-20","Pré + residual","14,07% a.a. + residual",ND,ND,"privada"),
    ],
    "CRI_V177": [
        (1,"Sênior A",100_000_000,"BRVERTCRIEC4","2031-05-20","DI+","DI + 1,50% a.a.",ND,ND,"pública"),
        (2,"Sênior B",450_000_000,"BRVERTCRIED2","2031-07-21","DI+","DI + 2,00% a.a.",ND,ND,"pública"),
        (3,"Mezanino I",51_765_000,"BRVERTCRIEE0","2036-07-21","DI+","DI + 5,50% a.a.",ND,ND,"pública"),
        (4,"Mezanino II",25_882_000,"BRVERTCRIEF7","2036-07-21","DI+","DI + 8,00% a.a.",ND,ND,"pública"),
        (5,"Júnior/Subordinada",19_412_000,ND,"2038-07-20","DI% + residual","100% do DI + prêmio final residual",ND,ND,"privada"),
    ],
}


ELIG = {
    "FIDC_I": dict(adimplencia_na_cessao="Direito creditório performado; condições documentais e operacionais", seasoning_minimo_meses=ND, idade_maxima_devedor=70, prazo_max_recebivel_dias=3836, wam_max_dias=2135, ticket_max_PF_R=201000, ticket_max_PJ_R=502000, tipos_de_ativo="CCB de financiamento solar", carencia_max_dias=ND, preco_max_aquisicao_pct_saldo=1.004, quem="Gestor; custodiante verifica documentação", geo=ND, score=ND, ved="créditos não elegíveis; limites de concentração e integrador", literal="WAM não superior a 2.135 dias; preço de aquisição não superior a 100,4%", status="Documentado"),
    "FIDC_II": dict(adimplencia_na_cessao="Devedor e direito sem atraso", seasoning_minimo_meses=ND, idade_maxima_devedor=70, prazo_max_recebivel_dias=4500, wam_max_dias=2400, ticket_max_PF_R=300000, ticket_max_PJ_R=500000, tipos_de_ativo="CCB pré ou pós-fixada", carencia_max_dias=180, preco_max_aquisicao_pct_saldo=1.005, quem="Gestor", geo=ND, score=ND, ved="direitos/devedores inadimplentes", literal="WAM máximo de 2.400 dias; preço de aquisição limitado a 100,5%", status="Documentado"),
    "FIDC_III": dict(adimplencia_na_cessao="Devedor e direito adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=600000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="Gestor", geo=ND, score=ND, ved="crédito não performado e seleção adversa", literal="WAM máximo de 2.000 dias; valor nominal máximo de R$350 mil/R$600 mil", status="Documentado"),
    "FIDC_IV": dict(adimplencia_na_cessao="Devedor adimplente", seasoning_minimo_meses=ND, idade_maxima_devedor=70, prazo_max_recebivel_dias=ND, wam_max_dias=ND, ticket_max_PF_R=ND, ticket_max_PJ_R=ND, tipos_de_ativo="CCB de financiamento solar", carencia_max_dias=5, preco_max_aquisicao_pct_saldo=ND, quem="Administrador/gestor", geo=ND, score=ND, ved="direitos fora dos critérios do regulamento", literal="devedor adimplente; verificação de carência em até 5 dias úteis", status="Documentado"),
    "FIDC_V": dict(adimplencia_na_cessao="Devedor e direito adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=70, prazo_max_recebivel_dias=4760, wam_max_dias=2400, ticket_max_PF_R=500000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB PF/PJ; CPR-F até 15% do PL", carencia_max_dias=366, preco_max_aquisicao_pct_saldo=1.005, quem="Gestor", geo=ND, score=ND, ved="pré-fixados acima de 15%; integrador acima dos limites", literal="WAM máximo de 2.400 dias; preço de aquisição limitado a 100,5%", status="Documentado"),
    "FIDC_VI": dict(adimplencia_na_cessao="Devedor e direito sem atraso", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3836, wam_max_dias=2400, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=1.01, quem="Gestor", geo=ND, score=ND, ved="balloon; seleção adversa; direitos vencidos", literal="WAM máximo de 2.400 dias; preço de aquisição limitado a 101%", status="Documentado"),
    "FIDC_VII": dict(adimplencia_na_cessao="Devedor e direito sem atraso", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3836, wam_max_dias=2400, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=1.04, quem="Gestor", geo=ND, score=ND, ved="balloon; seleção adversa; direitos vencidos", literal="preço de aquisição limitado a 104% do saldo contábil", status="Documentado"),
    "CRI_K1": dict(adimplencia_na_cessao="Direito não vencido e devedor adimplente", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=600000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="Solfácil atesta; securitizadora verifica", geo=ND, score=ND, ved="crédito não performado", literal="WAM pro forma até 2.000 dias; devedor individual 0,10%; top 10 1,00%", status="Documentado"),
    "CRI_K2": dict(adimplencia_na_cessao="Direito não vencido e devedor adimplente", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=600000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="Solfácil/FIDCs; securitizadora verifica", geo=ND, score=ND, ved="crédito não performado", literal="WAM pro forma até 2.000 dias; novados limitados a 5%", status="Documentado"),
    "CRI_K3": dict(adimplencia_na_cessao="Direito e devedor adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="Securitizadora com dados dos cedentes", geo=ND, score=ND, ved="crédito não performado", literal="WAM pro forma até 2.000 dias; valor presente PF R$350 mil/PJ R$700 mil", status="Documentado"),
    "CRI_K4": dict(adimplencia_na_cessao="Direito e devedor adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB pré-fixada", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="Securitizadora/cedente", geo=ND, score=ND, ved="crédito não performado", literal="critérios alinhados ao termo; redação completa no documento público", status="Documentado"),
    "CRI_V174": dict(adimplencia_na_cessao="Direito e devedor adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB pré-fixada, em reais, sem balloon", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="VERT com dados do gestor/cedente e custodiante", geo=ND, score=ND, ved="crédito não performado; balloon", literal="WAM máximo 2.000 dias; concentração individual 0,15%/0,07%", status="Documentado"),
    "CRI_V177": dict(adimplencia_na_cessao="Direito e devedor adimplentes", seasoning_minimo_meses=ND, idade_maxima_devedor=71, prazo_max_recebivel_dias=3845, wam_max_dias=2000, ticket_max_PF_R=350000, ticket_max_PJ_R=700000, tipos_de_ativo="CCB de financiamento solar", carencia_max_dias=185, preco_max_aquisicao_pct_saldo=ND, quem="VERT/cedente", geo=ND, score=ND, ved="crédito não performado", literal="Termo de securitização VERT 177ª, 2026-07-20", status="Documentado"),
}


def latest_fidc_tables(source_root: Path) -> dict[str, pd.DataFrame]:
    folder = source_root / "fidc_202607"
    tables = {}
    for key in ("I", "IV", "V", "VIII", "X_1", "X_2", "X_1_1"):
        frame = read_csv(folder / f"inf_mensal_fidc_tab_{key}_202607.csv")
        frame["_cnpj"] = frame["CNPJ_FUNDO_CLASSE"].map(norm_cnpj)
        tables[key] = frame[frame["_cnpj"].isin({v["cnpj"] for v in FIDCS.values()})].copy()
    return tables


def latest_cri_tables(source_root: Path) -> dict[str, pd.DataFrame]:
    folder = source_root / "cri_2026"
    tables = {}
    for key in ("geral", "classe", "carteira", "ativo_passivo", "creditos"):
        tables[key] = read_csv(folder / f"inf_mensal_cri_{key}_2026.csv")
    return tables


def latest_by_code(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    subset = frame[frame["Codigo_Identificacao_Certificado"].astype(str).eq(code)].copy()
    if subset.empty:
        return subset
    subset["_date"] = pd.to_datetime(subset["Data_Referencia"], errors="coerce")
    return subset[subset["_date"].eq(subset["_date"].max())].copy()


def reconcile_certificate_balances(group: pd.DataFrame, control_total: float | None) -> tuple[dict, str]:
    """Reconcile the inconsistent Valor_Certificados unit at operation/date level.

    The regulatory layout defines a unit value, while filers sometimes put the
    aggregate series balance in the same field.  Direct and quantity-weighted
    alternatives are tested against Valor_Atualizado_Emissao.  When neither
    reconciles, every series balance for the operation/date remains n/d.
    """
    raw = {idx: num(row.get("Valor_Certificados")) for idx, row in group.iterrows()}
    qty = {idx: num(row.get("Quantidade_Certificados")) for idx, row in group.iterrows()}
    if not raw or any(value is None for value in raw.values()):
        return ({idx: None for idx in group.index}, "n/d")
    direct_total = sum(raw.values())
    weighted = {idx: raw[idx] * qty[idx] if qty[idx] is not None else None for idx in group.index}
    weighted_total = sum(value for value in weighted.values() if value is not None) if all(value is not None for value in weighted.values()) else None

    def reconciles(candidate: float | None) -> bool:
        return bool(control_total and candidate is not None and abs(candidate - control_total) <= max(10_000.0, abs(control_total) * 0.005))

    if reconciles(direct_total):
        return raw, "saldo agregado reconciliado"
    if reconciles(weighted_total):
        return weighted, "valor unitário × quantidade reconciliado"

    # Some early filings have a zero/missing aggregate control. Large values
    # that are individually material versus integralized capital are clearly
    # aggregate balances and can be retained without multiplication.
    if not control_total:
        clearly_aggregate = True
        for idx, row in group.iterrows():
            integralized = num(row.get("Total_Integralizado"))
            if integralized and raw[idx] < integralized * 0.01:
                clearly_aggregate = False
        if clearly_aggregate:
            return raw, "saldo agregado; controle total indisponível"
    return ({idx: None for idx in group.index}, "n/d por conflito de unidade")


def build_series(fidc: dict[str, pd.DataFrame], cri: dict[str, pd.DataFrame]) -> list[dict]:
    rows: list[dict] = []
    x2 = fidc["X_2"]
    for vehicle_id, meta in FIDCS.items():
        subset = x2[x2["_cnpj"].eq(meta["cnpj"])].copy()
        total_nav = (subset["TAB_X_QT_COTA"].fillna(0) * subset["TAB_X_VL_COTA"].fillna(0)).sum()
        for _, item in subset.iterrows():
            raw = str(item["TAB_X_CLASSE_SERIE"])
            normalized = raw.lower()
            if "mezanino 2" in normalized:
                layer = "Mezanino B"
            elif "mezanino" in normalized:
                layer = "Mezanino A"
            elif "subordinada 1" in normalized:
                layer = "Júnior/Subordinada"
            else:
                layer = "Sênior"
            nav = nz(item["TAB_X_QT_COTA"]) * nz(item["TAB_X_VL_COTA"])
            rows.append({
                "veiculo_id": vehicle_id, "camada": layer, "serie": raw.replace("Subclasse ", ""),
                "isin": ND, "data_emissao": ND, "data_vencimento": ND, "prazo_meses": ND,
                "montante_emitido_R$": ND, "montante_subscrito_R$": ND, "saldo_atual_R$": nav,
                "pct_da_emissao": pct(nav, total_nav), "indexador": ND, "taxa_contratada": ND,
                "taxa_preliminar_ou_teto": ND, "pu_atual": nd(item["TAB_X_VL_COTA"]),
                "rating_agencia": ND, "rating_nota": ND,
                "colocacao": ND, "retida_pelo_originador": ND, "data_base": FIDC_BASE,
                "conflito": "não", "fonte_id": "CVM_FIDC_202607_X2", "status": "Documentado",
                "nota_metodo": "Saldo da cota = quantidade de cotas × valor da cota no Informe Mensal. O rating do deck é veicular e não foi imputado à classe.",
            })

    latest_class = cri["classe"]
    for vehicle_id, meta in CRIS.items():
        latest = latest_by_code(latest_class, meta["code"])
        current_ap = latest_by_code(cri["ativo_passivo"], meta["code"])
        control_total = num(current_ap.iloc[0].get("Valor_Atualizado_Emissao")) if not current_ap.empty else None
        reconciled, balance_mode = reconcile_certificate_balances(latest, control_total) if not latest.empty else ({}, "n/d")
        balance_by_series = {}
        if not latest.empty:
            for idx, item in latest.iterrows():
                series_number = num(item.get("Numero_Serie"))
                if series_number is not None:
                    balance_by_series[int(series_number)] = reconciled.get(idx)
        for (series_no, layer, amount, isin, maturity, indexer, rate, agency, note, placement) in CRI_SERIES[vehicle_id]:
            if vehicle_id == "CRI_K3":
                prelim = {1:"maior entre DI futuro + 1,00% e 15,50%",2:"105,50% do DI",3:"maior entre DI futuro + 2,00% e 16,50%",4:"DI + 5,75%",5:"DI + 10,00%",6:ND}[series_no]
            elif vehicle_id == "CRI_V174":
                prelim = {1:"maior entre DI futuro + 0,65% e 14,00%",2:"104,00% do DI",3:"maior entre DI futuro + 1,50% e 14,95%",4:"DI + 5,50%",5:"DI + 8,00%",6:ND}[series_no]
            else:
                prelim = ND
            current = balance_by_series.get(series_no)
            conflict = "sim" if (vehicle_id == "CRI_K1" and series_no == 3) or vehicle_id in {"CRI_K2", "CRI_K3", "CRI_K4", "CRI_V174"} else "não"
            rows.append({
                "veiculo_id": vehicle_id, "camada": layer, "serie": f"Série {series_no}", "isin": isin,
                "data_emissao": meta["emissao"], "data_vencimento": maturity,
                "prazo_meses": months_between(meta["emissao"], maturity), "montante_emitido_R$": amount,
                "montante_subscrito_R$": amount, "saldo_atual_R$": nd(current),
                "pct_da_emissao": pct(amount if amount != ND else None, meta["total"]), "indexador": indexer,
                "taxa_contratada": rate, "taxa_preliminar_ou_teto": prelim, "pu_atual": ND,
                "rating_agencia": agency, "rating_nota": note, "colocacao": placement,
                "retida_pelo_originador": "sim" if placement == "privada" else ND,
                "data_base": meta["latest"], "conflito": conflict,
                "fonte_id": source_join(meta["source"], "CVM_FUNDOSNET_TERMOS_CRI_20260822", "CVM_CRI_2026_CLASSE" if vehicle_id != "CRI_V177" else "CVM_FUNDOSNET_VERT177_20260720"),
                "status": "Documentado" if amount != ND else "n/d",
                "nota_metodo": f"Montante e termos documentais; saldo da última competência: {balance_mode}. Reconciliação usa Valor_Atualizado_Emissao; conflito de unidade permanece n/d.",
            })
    return rows


def build_vehicles(fidc: dict[str, pd.DataFrame], cri: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    tab_i, tab_iv = fidc["I"], fidc["IV"]
    for vehicle_id, meta in FIDCS.items():
        irow = tab_i[tab_i["_cnpj"].eq(meta["cnpj"])].iloc[0]
        ivrow = tab_iv[tab_iv["_cnpj"].eq(meta["cnpj"])].iloc[0]
        rows.append({
            "veiculo_id": vehicle_id, "tipo": "FIDC", "nome": meta["nome"], "cnpj_ou_emissora": meta["cnpj"],
            "securitizadora": ND, "data_inicio_ou_emissao": meta["inicio"], "situacao": "Em funcionamento normal",
            "administrador": meta["admin"], "gestor": meta["gestor"], "custodiante": meta["custodiante"],
            "agente_fiduciario": ND, "auditor": meta["auditor"], "agencia_rating": meta["rating"],
            "pl_ou_saldo_R$mi": nz(ivrow["TAB_IV_A_VL_PL"]) / 1e6, "carteira_R$mi": nz(irow["TAB_I2_VL_CARTEIRA"]) / 1e6,
            "data_base": FIDC_BASE, "fonte_id": "CVM_CADASTRO_20260821 | CVM_FIDC_202607_I_IV | ANX_XP_20260428", "status": "Documentado",
            "nota_metodo": "PL e carteira na última competência pública; prestadores no cadastro CVM; agência de rating declarada no deck e não vinculada a cada classe.",
        })
    ap = cri["ativo_passivo"]
    geral = cri["geral"]
    for vehicle_id, meta in CRIS.items():
        current_ap = latest_by_code(ap, meta["code"])
        current_general = latest_by_code(geral, meta["code"])
        ap_row = current_ap.iloc[0] if not current_ap.empty else None
        general_row = current_general.iloc[0] if not current_general.empty else None
        rows.append({
            "veiculo_id": vehicle_id, "tipo": "CRI", "nome": meta["nome"], "cnpj_ou_emissora": meta["securitizadora"],
            "securitizadora": meta["securitizadora"], "data_inicio_ou_emissao": meta["emissao"],
            "situacao": "Oferta registrada; encerramento não publicado" if vehicle_id == "CRI_V177" else "Em acompanhamento / oferta encerrada",
            "administrador": ND, "gestor": ND,
            "custodiante": nd(general_row.get("Custodiante")) if general_row is not None else "VERT DTVM" if vehicle_id.startswith("CRI_V") else ND,
            "agente_fiduciario": nd(general_row.get("Agente_Fiduciario")) if general_row is not None else "Oliveira Trust DTVM S.A." if vehicle_id.startswith("CRI_V") else ND,
            "auditor": ND, "agencia_rating": nd(general_row.get("Agencia_Classificadora")) if general_row is not None else ND,
            "pl_ou_saldo_R$mi": nz(ap_row.get("Valor_Atualizado_Emissao")) / 1e6 if ap_row is not None else ND,
            "carteira_R$mi": nz(ap_row.get("Creditos")) / 1e6 if ap_row is not None else ND,
            "data_base": meta["latest"], "fonte_id": source_join(meta["source"], "CVM_CRI_2026_GERAL_ATIVO"),
            "status": "Documentado" if ap_row is not None else "n/d",
            "nota_metodo": "Saldo e créditos da última competência pública; VERT 177 ainda sem Informe Mensal na data de acesso.",
        })
    return rows


def build_eligibility() -> list[dict]:
    rows = []
    for vehicle_id, data in ELIG.items():
        src = FIDCS[vehicle_id]["reg_src"] if vehicle_id in FIDCS else CRIS[vehicle_id]["source"]
        days = data["prazo_max_recebivel_dias"]
        rows.append({
            "veiculo_id": vehicle_id, "adimplencia_na_cessao": data["adimplencia_na_cessao"],
            "seasoning_minimo_meses": data["seasoning_minimo_meses"], "idade_maxima_devedor": data["idade_maxima_devedor"],
            "prazo_max_recebivel_dias": days, "prazo_max_recebivel_meses": round(days / 30.4375, 1) if isinstance(days, (int,float)) else ND,
            "wam_max_dias": data["wam_max_dias"], "ticket_max_PF_R$": data["ticket_max_PF_R"], "ticket_max_PJ_R$": data["ticket_max_PJ_R"],
            "tipos_de_ativo": data["tipos_de_ativo"], "carencia_max_dias": data["carencia_max_dias"],
            "preco_max_aquisicao_pct_saldo": data["preco_max_aquisicao_pct_saldo"], "preco_efetivo_aquisicao_pct_saldo": ND,
            "quem_atesta_elegibilidade": data["quem"], "restricao_geografica": data["geo"], "restricao_score": data["score"],
            "vedacoes_expressas": data["ved"], "redacao_literal": data["literal"], "fonte_id": src,
            "status": data["status"], "nota_metodo": "Limite contratual; preço efetivo permanece n/d quando o documento não publica o denominador.",
        })
    for fidc_id, cri_id in (("FIDC_II","CRI_K1"),("FIDC_IV","CRI_K1"),("FIDC_II","CRI_K2"),("FIDC_IV","CRI_K2")):
        f, c = ELIG[fidc_id], ELIG[cri_id]
        diffs=[]
        for field, label in (("wam_max_dias","WAM"),("prazo_max_recebivel_dias","prazo"),("ticket_max_PF_R","ticket PF"),("ticket_max_PJ_R","ticket PJ")):
            fv, cv=f[field],c[field]
            if isinstance(fv,(int,float)) and isinstance(cv,(int,float)) and cv<fv:
                diffs.append(f"{label}: CRI aperta {fv-cv:g}")
        rows.append({
            "veiculo_id": f"Δ {fidc_id}→{cri_id}", "adimplencia_na_cessao": "CRI exige adimplência na cessão",
            "seasoning_minimo_meses": ND, "idade_maxima_devedor": ND, "prazo_max_recebivel_dias": ND,
            "prazo_max_recebivel_meses": ND, "wam_max_dias": ND, "ticket_max_PF_R$": ND, "ticket_max_PJ_R$": ND,
            "tipos_de_ativo": "CCB solar", "carencia_max_dias": ND, "preco_max_aquisicao_pct_saldo": ND,
            "preco_efetivo_aquisicao_pct_saldo": ND, "quem_atesta_elegibilidade": "Comparação por código",
            "restricao_geografica": ND, "restricao_score": ND, "vedacoes_expressas": "; ".join(diffs) if diffs else "nenhum aperto quantificável com os campos publicados",
            "redacao_literal": "Linha derivada; consulte as duas linhas de origem", "fonte_id": source_join(FIDCS[fidc_id]["reg_src"], CRIS[cri_id]["source"]),
            "status": "Inferido", "nota_metodo": "Diferença simples entre tetos; n/d não é tratado como zero.",
        })
    return rows


WATERFALLS = {
    "FIDC_I": ("pró-rata condicionado; sequencial na liquidação", "despesas e reservas", "sênior até alvo", "mezanino A até alvo", "mezanino B e júnior proporcionalmente", "desde mês 73: sênior e A pró-rata; depois B e júnior", "eventos de avaliação/liquidação", "sênior", "sênior", "mezanino A/B", "júnior", "sim", "6 meses", ND, ND),
    "FIDC_II": ("target até mês 59; sequencial desde mês 60", "despesas", "sênior até target", "mezanino até target", "júnior", "desde mês 60: sênior integral → mezanino → júnior", "evento de venda ou liquidação", "sênior", "sênior", "mezanino", "júnior", "sim", "3 meses", ND, ND),
    "FIDC_III": ("pró-rata até mês 47; sequencial desde mês 48/desalavancagem", "despesas e reservas", "sênior", "mezanino A", "derivativos e mezanino B", "júnior", "atraso desenquadrado por 10 DU; mês 48", "sênior", "sênior", "A antes de B", "júnior", "sim", ND, ND, "derivativos"),
    "FIDC_IV": ("ordem operacional; pró-rata formal n/d", "despesas", "benchmark sênior", "benchmark mezanino", "reservas", "amortização extraordinária júnior e compras", "eventos de liquidação", "sênior", "sênior", "mezanino", "júnior", ND, ND, ND, ND),
    "FIDC_V": ("pró-rata condicionado até mês 72; liquidação sequencial", "despesas e reservas", "sênior até alvo", "mezanino até alvo", "reserva de amortização", "júnior e cura; desde mês 73 sênior/mezanino pró-rata", "eventos de avaliação/liquidação", "sênior", "sênior", "mezanino", "júnior", "sim", ND, ND, ND),
    "FIDC_VI": ("pró-rata; sequencial após desalavancagem", "despesas/reserva/derivativos", "sênior", "mezanino A", "mezanino B e reserva MTM", "saque júnior; aquisição", "coberturas/atraso-90; aceleração definitiva", "sênior", "sênior", "A antes de B", "júnior após públicas", "sim", "3 meses", ND, "menor entre MTM negativo e 1% do nocional"),
    "FIDC_VII": ("revolvência 12m; pró-rata por targets; sequencial após evento", "despesas/reservas/derivativos", "sênior", "mezanino A", "mezanino B", "júnior", "evento encerra revolvência; aceleração definitiva", "sênior", "sênior", "A antes de B", "júnior", "sim", "3 meses", ND, "menor entre MTM negativo e 1% do PL"),
    "CRI_K1": ("pró-rata até mês 47; sequencial desde mês 48/evento", "despesas", "recomposição da reserva", "juros por camada", "amortização por repasses 54/15/18/5/8", "prêmio residual S5 após S1–S4", "atraso estoque >15% em 2 verificações ou downgrade 2 níveis", "juros por camada", "S1", "S2/S3/S4", "S5; prêmio residual travado", "sim", "R$0,905 mi inicial", ND, ND),
    "CRI_K2": ("pró-rata até mês 47; sequencial desde mês 48/evento", "despesas", "reserva", "juros por camada", "amortização por repasses", "júnior/residual conforme termo", "atraso >15% em 3 verificações; downgrade; cobertura", "juros por camada", "S1", "S2/S3/S4", "S5", "sim", ND, ND, ND),
    "CRI_K3": ("regime detalhado n/d na lâmina", "despesas", "reserva", "remuneração", "amortização conforme disponibilidade", ND, "termo definitivo necessário", "n/d", "S1/S2", "S3/S4/S5", "S6", ND, ND, ND, ND),
    "CRI_K4": ("pró-rata/sequencial conforme termo; detalhe n/d no anúncio", "despesas", "reserva", "remuneração", "amortização", ND, "termo definitivo necessário", "n/d", "S1/S2", "S3–S6", "S7", ND, ND, ND, ND),
    "CRI_V174": ("regime detalhado n/d na lâmina", "despesas", "reserva", "remuneração", "amortização conforme disponibilidade", ND, "termo definitivo necessário", "n/d", "S1/S2", "S3–S5", "S6", ND, ND, ND, ND),
    "CRI_V177": ("n/d", ND, ND, ND, ND, ND, "termo integral necessário", ND, ND, ND, ND, ND, ND, ND, ND),
}


def build_waterfall() -> tuple[list[dict], list[dict]]:
    rows, visual = [], []
    for vehicle_id, w in WATERFALLS.items():
        src = FIDCS[vehicle_id]["reg_src"] if vehicle_id in FIDCS else CRIS[vehicle_id]["source"]
        rows.append({
            "veiculo_id": vehicle_id, "regime": w[0], "ordem_1": w[1], "ordem_2": w[2], "ordem_3": w[3],
            "ordem_4": w[4], "ordem_5": w[5], "gatilho_de_mudanca_para_sequencial": w[6],
            "quem_recebe_juros_antes_de_principal": w[7], "super_senior_prioridade": w[8],
            "senior_prioridade": w[8], "mezanino_prioridade": w[9], "junior_prioridade": w[10],
            "cash_sweep": w[11], "reserva_de_despesas": w[12], "reserva_de_juros": w[13], "reserva_MTM": w[14],
            "fonte_id": src, "status": "Documentado" if w[0] != ND else "n/d",
            "nota_metodo": "Ordem resumida; o texto contratual integral prevalece.",
        })
    for regime, steps, trigger in (
        ("Pró-rata condicionado", ["Despesas e reservas", "Juros das camadas", "Principal conforme targets", "Júnior apenas se testes passam", "Reinvestimento quando permitido"], "Mantido enquanto índices e coberturas permanecem enquadrados"),
        ("Sequencial pós-evento", ["Despesas e reservas", "Juros da camada prioritária", "Principal sênior integral", "Mezanino A e B", "Júnior por último"], "Ativado por evento, passagem do tempo ou aceleração"),
    ):
        for order, step in enumerate(steps, 1):
            visual.append({"regime": regime, "ordem": order, "degrau": step, "condicao": trigger, "fonte_id": "METH_WATERFALL_COMPARATIVO", "status": "Inferido", "nota_metodo": "Síntese comparativa dos contratos; diferenças por veículo permanecem em 06_Waterfall."})
    return rows, visual


SUBORD = {
    "FIDC_I": ("sim","titular B/júnior","administrador após testes",ND,"subordinação pro forma 26,5%; B+júnior 16,5%; cobertura públicas 110%; eventos/reservas/concentração ok","25% total; 15% B+júnior",ND,"durante o regime previsto","vedado se evento ou teste desenquadrado"),
    "FIDC_II": ("sim","titular júnior","administrador após testes",ND,"razões mínimas; índices de atraso; retorno 3m e mês positivo; sem evento","20% total; 4,5% júnior",ND,ND,"vedado em evento/liquidação"),
    "FIDC_III": ("sim","titular júnior","administrador após testes",ND,"subordinação ≥25%; B+júnior ≥10%; júnior ≥12% para saque; coberturas","25% total; 10% B+júnior; 4% júnior","targets 67/15/6/12","até evento/mês 48","vedado em sequencial"),
    "FIDC_IV": ("sim","titular júnior",ND,ND,"cláusulas internas incompletas",ND,ND,ND,"n/d"),
    "FIDC_V": ("sim","titular júnior","administrador após testes",ND,"subordinação pro forma 22%; júnior 9%; cobertura pública 105%; retorno positivo","20% total; 7% júnior",ND,ND,"vedado em evento"),
    "FIDC_VI": ("sim","75% da cota júnior","administrador", "75% do júnior", "pró-rata; coberturas 136%/113,3%/106,3%; MTM; sem evento","5% A; 2,5% B; 2% júnior","coberturas e atraso-90","até desinvestimento","vedado no sequencial/evento"),
    "FIDC_VII": ("sim","75% da cota júnior","administrador", "75% do júnior", "pró-rata; coberturas; MTM; sem evento","5% A; 2,5% B; 2% júnior","targets 73/15/6/6","após carência; respeita revolvência","vedado no sequencial/evento"),
    "CRI_K1": ("sim — por waterfall","automático pelo contrato","securitizadora",ND,"regime pró-rata; prêmio residual somente após S1–S4","targets 54/15/18/5/8",ND,"até mês 47 se sem evento","prêmio residual travado"),
    "CRI_K2": ("sim — por waterfall","automático pelo contrato","securitizadora",ND,"regime pró-rata e coberturas","índices 159%/123%/110%/105%",ND,"até mês 47 se sem evento","vedado no sequencial conforme termo"),
}


def build_subordinated(series_rows: list[dict], fidc: dict[str, pd.DataFrame]) -> list[dict]:
    rows=[]
    vehicles=list(FIDCS)+list(CRIS)
    tab_i=fidc["I"]
    for vehicle_id in vehicles:
        data=SUBORD.get(vehicle_id,(ND,ND,ND,ND,ND,ND,ND,ND,ND))
        src=FIDCS[vehicle_id]["reg_src"] if vehicle_id in FIDCS else CRIS[vehicle_id]["source"]
        current=[r for r in series_rows if r["veiculo_id"]==vehicle_id and isinstance(r["saldo_atual_R$"],(int,float))]
        support_rows=[r for r in current if r["camada"] in {"Mezanino A","Mezanino B","Mezanino","Júnior/Subordinada","Subordinada"}]
        support=sum(r["saldo_atual_R$"] for r in support_rows)
        if vehicle_id in FIDCS:
            portfolio=nz(tab_i[tab_i["_cnpj"].eq(FIDCS[vehicle_id]["cnpj"])].iloc[0]["TAB_I2_VL_CARTEIRA"])
            attach=pct(support,portfolio) if support_rows else ND
            row_source=source_join(src,"CVM_FIDC_202607_I_IV","CVM_FIDC_202607_X2")
        else:
            attach=ND
            row_source=src
        rows.append({
            "veiculo_id":vehicle_id,"saque_permitido":data[0],"quem_solicita":data[1],"quem_autoriza":data[2],"quorum":data[3],
            "testes_exigidos":data[4],"pisos_de_subordinacao_pct":data[5],"indices_de_cobertura":data[6],"trava_temporal":data[7],
            "vedacoes_pos_evento":data[8],"principal_subordinado_ja_pago_R$mi":ND,"primeira_ocorrencia":ND,"ultima_ocorrencia":ND,
            "attachment_atual_pct_carteira":attach,"subordinacao_antes_do_saque_pct":ND,"subordinacao_depois_pct":ND,"variacao_pp":ND,
            "impacto_na_senior":"n/d — nenhum saque observado com valor e data publicados",
            "fonte_id":row_source,"status":"Inferido" if isinstance(attach,float) else ("Documentado" if data[0]!=ND else "n/d"),
            "nota_metodo":"Attachment atual = (NAV mezanino + NAV júnior) / carteira bruta na mesma competência. Antes/depois de saque permanece n/d sem ocorrência pública com valor e data.",
        })
    return rows


PDD_GRID = {
    "FIDC_I": [ND]*8,
    "FIDC_II": [0.0,0.02,0.06,0.20,1.0,1.0,1.0,1.0],
    "FIDC_III": [ND]*8,
    "FIDC_IV": [0.005,0.01,0.03,0.10,0.30,0.50,0.70,1.0],
    "FIDC_V": [0.005,0.01,0.03,0.10,0.30,0.50,0.70,1.0],
    "FIDC_VI": [0.0,0.015,0.05,0.10,0.37,0.58,0.78,1.0],
    "FIDC_VII": [0.0,0.015,0.05,0.10,0.37,0.58,0.78,1.0],
    "CRI_K1": [0.0,0.01,0.03,0.10,0.30,0.50,0.70,1.0],
    "CRI_K2": [0.0,0.01,0.03,0.10,0.30,0.50,0.70,1.0],
    "CRI_K3": [ND]*8, "CRI_K4": [ND]*8, "CRI_V174": [ND]*8, "CRI_V177": [ND]*8,
}


def build_pdd(fidc: dict[str,pd.DataFrame], cri: dict[str,pd.DataFrame]) -> list[dict]:
    rows=[]
    i, v=fidc["I"],fidc["V"]
    for vehicle_id, meta in FIDCS.items():
        ir=i[i["_cnpj"].eq(meta["cnpj"])].iloc[0]; vr=v[v["_cnpj"].eq(meta["cnpj"])].iloc[0]
        portfolio=nz(ir["TAB_I2_VL_CARTEIRA"])
        allowance=nz(ir.get("TAB_I2A11_VL_REDUCAO_RECUP"))+nz(ir.get("TAB_I2B11_VL_REDUCAO_RECUP"))
        over90=sum(nz(vr.get(f"TAB_V_B{idx}_VL_INAD_{suffix}")) for idx,suffix in [(4,"120"),(5,"150"),(6,"180"),(7,"360"),(8,"720"),(9,"1080"),(10,"MAIOR_1080")])
        grid=PDD_GRID[vehicle_id]
        ratio=pct(allowance,over90)
        rows.append({
            "veiculo_id":vehicle_id,"ate_15d":grid[0],"16_30d":grid[1],"31_60d":grid[2],"61_90d":grid[3],"91_120d":grid[4],"121_150d":grid[5],"151_180d":grid[6],"acima_180d":grid[7],
            "base_de_incidencia":"saldo integral da CCB" if vehicle_id in {"FIDC_II","FIDC_IV","FIDC_V","FIDC_VI","FIDC_VII"} else ND,
            "efeito_vagao":"sim" if vehicle_id in {"FIDC_II","FIDC_IV","FIDC_V","FIDC_VI","FIDC_VII"} else ND,
            "tratamento_do_dia_181":"100%; baixa após 365d ou impossibilidade" if vehicle_id!="FIDC_I" and vehicle_id!="FIDC_III" else ND,
            "pdd_adicional_discricionaria":ND,"pdd_observada_pct_carteira":pct(allowance,portfolio),"saldo_90d_pct_carteira":pct(over90,portfolio),"razao_pdd_sobre_90d":ratio,
            "data_base":FIDC_BASE,"fonte_id":source_join(meta["reg_src"],"CVM_FIDC_202607_I_V"),"status":"Documentado",
            "nota_metodo":"Informe Mensal agrega até 30 dias; a divisão 0–15/16–30 vem apenas do regulamento. Razão acima de 100% é indício analítico, mas efeito_vagao fica n/d sem regra contratual localizada.",
        })
    ap, car=cri["ativo_passivo"],cri["carteira"]
    for vehicle_id,meta in CRIS.items():
        ar=latest_by_code(ap,meta["code"]); cr=latest_by_code(car,meta["code"])
        allowance=credits=over90=None
        if not ar.empty:
            allowance=num(ar.iloc[0].get("Reducao_Valor_Recuperacao")); credits=num(ar.iloc[0].get("Creditos"))
        if not cr.empty:
            r=cr.iloc[0]
            over90=sum(nz(r.get(c)) for c in ["Creditos_Vinculados_Inadimplentes_91a120Dias","Creditos_Vinculados_Inadimplentes_121a150Dias","Creditos_Vinculados_Inadimplentes_151a180Dias","Creditos_Vinculados_Inadimplentes_Acima180Dias"])
        grid=PDD_GRID[vehicle_id]; ratio=pct(allowance,over90)
        rows.append({
            "veiculo_id":vehicle_id,"ate_15d":grid[0],"16_30d":grid[1],"31_60d":grid[2],"61_90d":grid[3],"91_120d":grid[4],"121_150d":grid[5],"151_180d":grid[6],"acima_180d":grid[7],
            "base_de_incidencia":"saldo integral da CCB","efeito_vagao":"sim","tratamento_do_dia_181":"100%" if vehicle_id in {"CRI_K1","CRI_K2"} else ND,
            "pdd_adicional_discricionaria":ND,"pdd_observada_pct_carteira":pct(allowance,credits),"saldo_90d_pct_carteira":pct(over90,credits),"razao_pdd_sobre_90d":ratio,
            "data_base":meta["latest"],"fonte_id":source_join(meta["source"],"CVM_CRI_2026_ATIVO_CARTEIRA"),"status":"Documentado" if credits is not None else "n/d",
            "nota_metodo":"PDD = redução ao valor de recuperação / créditos; >90d soma as faixas publicadas do Informe Mensal.",
        })
    return rows


CONC_LIMITS = {
    "FIDC_I":(0.02,0.10,0.10,ND,ND), "FIDC_II":(0.02,0.10,ND,ND,ND), "FIDC_III":(0.001,0.01,ND,ND,ND),
    "FIDC_IV":(0.20,ND,ND,ND,ND), "FIDC_V":(0.02,0.10,0.10,ND,ND), "FIDC_VI":(0.20,ND,ND,ND,ND), "FIDC_VII":(0.20,ND,ND,ND,ND),
    "CRI_K1":(0.001,0.01,ND,ND,ND), "CRI_K2":(0.001,ND,ND,ND,ND), "CRI_K3":(0.001,ND,ND,ND,ND), "CRI_K4":(0.001,ND,ND,ND,ND),
    "CRI_V174":("0,15% até 470,6 mil unidades; 0,07% no patamar 750 mil",ND,ND,ND,ND), "CRI_V177":(ND,ND,ND,ND,ND),
}


def build_concentration(fidc: dict[str,pd.DataFrame], cri: dict[str,pd.DataFrame]) -> list[dict]:
    rows=[]; top=fidc["VIII"]; tab_i=fidc["I"]
    for vehicle_id,meta in FIDCS.items():
        vals=top[top["_cnpj"].eq(meta["cnpj"])].sort_values("SEQUENCIAL")["VALOR"].fillna(0).tolist()
        portfolio=nz(tab_i[tab_i["_cnpj"].eq(meta["cnpj"])].iloc[0]["TAB_I2_VL_CARTEIRA"])
        observed1=pct(max(vals) if vals else None,portfolio); observed10=pct(sum(vals[:10]),portfolio)
        lim=CONC_LIMITS[vehicle_id]
        slack=(lim[0]-observed1) if isinstance(lim[0],float) and isinstance(observed1,float) else ND
        rows.append({"veiculo_id":vehicle_id,"cap_individual_pct":lim[0],"cap_top10_pct":lim[1],"cap_por_devedor_ANBIMA_pct":ND,"cap_por_integrador":lim[2],"cap_por_UF":lim[3],"cap_PJ_pct":lim[4],"cap_por_safra":ND,"concentracao_observada_individual":observed1,"concentracao_observada_top10":observed10,"folga_vs_limite_pp":slack,"data_base":FIDC_BASE,"fonte_id":source_join(meta["reg_src"],"CVM_FIDC_202607_VIII"),"status":"Documentado","nota_metodo":"Observado = valores da Tabela VIII / carteira; a CVM publica os maiores valores sem identificação do devedor."})
    credits=cri["creditos"]
    for vehicle_id,meta in CRIS.items():
        latest=latest_by_code(credits,meta["code"]); lim=CONC_LIMITS[vehicle_id]
        obs1=obs10=ND
        if not latest.empty:
            row=latest.iloc[0]; obs1=nd(row.get("Maior_Devedor")); obs10=nd(row.get("Dez_Maiores_Devedores"))
            # Filings normally express these fields as percentages; retain raw documented ratio.
            if isinstance(obs1,(int,float)) and obs1>1: obs1=obs1/100
            if isinstance(obs10,(int,float)) and obs10>1: obs10=obs10/100
        slack=(lim[0]-obs1) if isinstance(lim[0],float) and isinstance(obs1,float) else ND
        rows.append({"veiculo_id":vehicle_id,"cap_individual_pct":lim[0],"cap_top10_pct":lim[1],"cap_por_devedor_ANBIMA_pct":0.20,"cap_por_integrador":lim[2],"cap_por_UF":lim[3],"cap_PJ_pct":lim[4],"cap_por_safra":ND,"concentracao_observada_individual":obs1,"concentracao_observada_top10":obs10,"folga_vs_limite_pp":slack,"data_base":meta["latest"],"fonte_id":source_join(meta["source"],"CVM_CRI_2026_CREDITOS"),"status":"Documentado" if not latest.empty else "n/d","nota_metodo":"Cap ANBIMA de 20% é classificação de mercado e não substitui o limite contratual."})
    return rows


FIDC_TERM = {
    "FIDC_I":(2135,ND,126,ND,12,"2024-11-01"), "FIDC_II":(2400,ND,150,ND,ND,ND), "FIDC_III":(2000,ND,150,ND,6,ND),
    "FIDC_IV":(ND,ND,ND,ND,ND,ND), "FIDC_V":(2400,ND,156,ND,ND,ND), "FIDC_VI":(2400,ND,126,ND,ND,ND), "FIDC_VII":(2400,ND,126,ND,12,"mês 61 ou PL R$100 mi"),
}


def build_terms(series_rows:list[dict]) -> list[dict]:
    rows=[]
    for vehicle_id,meta in FIDCS.items():
        t=FIDC_TERM[vehicle_id]
        rows.append({"veiculo_id":vehicle_id,"wam_contratual_max_dias":t[0],"wam_observado_dias":t[1],"prazo_medio_recebivel_meses":ND,"prazo_max_recebivel_meses":t[2],"vencimento_do_veiculo":ND,"prazo_do_veiculo_meses":ND,"duration_serie_mais_longa":ND,"gap_ativo_passivo_meses":ND,"periodo_revolvencia_meses":t[4],"inicio_amortizacao":t[5],"fonte_id":meta["reg_src"],"status":"Documentado","nota_metodo":"Regulamentos/suplementos não publicam vencimentos efetivos em vários FIDCs; teto de WAM não é WAM observado."})
    for vehicle_id,meta in CRIS.items():
        series=[r for r in series_rows if r["veiculo_id"]==vehicle_id]
        max_maturity=max((r["data_vencimento"] for r in series if r["data_vencimento"]!=ND),default=ND)
        max_month=max((r["prazo_meses"] for r in series if isinstance(r["prazo_meses"],(int,float))),default=ND)
        asset_month=round(ELIG[vehicle_id]["wam_max_dias"]/30.4375,1) if isinstance(ELIG[vehicle_id]["wam_max_dias"],(int,float)) else ND
        gap=(max_month-asset_month) if isinstance(max_month,(int,float)) and isinstance(asset_month,(int,float)) else ND
        rows.append({"veiculo_id":vehicle_id,"wam_contratual_max_dias":ELIG[vehicle_id]["wam_max_dias"],"wam_observado_dias":ND,"prazo_medio_recebivel_meses":ND,"prazo_max_recebivel_meses":round(ELIG[vehicle_id]["prazo_max_recebivel_dias"]/30.4375,1),"vencimento_do_veiculo":max_maturity,"prazo_do_veiculo_meses":max_month,"duration_serie_mais_longa":ND,"gap_ativo_passivo_meses":gap,"periodo_revolvencia_meses":ND,"inicio_amortizacao":"conforme disponibilidade e waterfall","fonte_id":meta["source"],"status":"Documentado","nota_metodo":"Gap usa o prazo legal da série mais longa menos o teto de WAM; prazo médio observado permanece n/d."})
    return rows


def build_events() -> list[dict]:
    rows=[]
    templates={
      "FIDC_I":[("Avaliação","atraso de estoque ou parcelas acima de 15%","15%","pode levar à liquidação/sequencial",ND,ND), ("Avaliação","rating sênior cai 2 níveis","2 níveis","avaliação",ND,ND)],
      "FIDC_II":[("Avaliação","atraso estoque >10% ou roll-90 >0,9%","10% / 0,9%","avaliação",ND,ND)],
      "FIDC_III":[("Desalavancagem","atraso estoque >12% ou parcelas >8,5%","12% / 8,5%","sequencial","n/d","10 DU")],
      "FIDC_IV":[("Avaliação","shortfall benchmark sênior","2 DU","avaliação",ND,"2 DU")],
      "FIDC_V":[("Avaliação","atraso estoque >15% ou arrecadação >10%","15% / 10%","avaliação",ND,ND)],
      "FIDC_VI":[("Desalavancagem","atraso-90 >15%","15%","sequencial","75% júnior para matérias previstas",ND),("Avaliação","rolagem-90 >1,6%","1,6%","avaliação",ND,ND),("Amortização Antecipada","solicitação após 18 meses","18 meses","amortização das públicas","75% júnior",ND)],
      "FIDC_VII":[("Desalavancagem","atraso-90 >15%","15%","encerra revolvência e ativa sequencial",ND,ND),("Resgate Compulsório","desinvestimento no mês 61 ou PL R$100 mi","61 meses / R$100 mi","desinvestimento",ND,ND),("Amortização Antecipada","solicitação após 24 meses","24 meses","amortização com prêmio 0,20% a.a.","75% júnior",ND)],
      "CRI_K1":[("Desalavancagem","índice de atraso estoque >15% por 2 verificações","15%; 2 verificações","waterfall sequencial",ND,"3 verificações conformes para retorno"),("Desalavancagem","downgrade S1/S2 em 2 níveis","2 níveis","waterfall sequencial",ND,"3 verificações conformes")],
      "CRI_K2":[("Desalavancagem","atraso >15% por 3 verificações","15%; 3 verificações","waterfall sequencial",ND,"6 meses; depois sequencial permanente salvo assembleia"),("Desalavancagem","cobertura 159%/123%/110%/105% desenquadrada","159%/123%/110%/105%","waterfall sequencial",ND,"2 consecutivas ou 4 em 12")],
      "CRI_K3":[("Resgate Compulsório","hipóteses referenciadas na lâmina",ND,"resgate",ND,ND)],
      "CRI_K4":[("Avaliação","termo definitivo necessário para a lista completa",ND,ND,ND,ND)],
      "CRI_V174":[("Resgate Compulsório","98% do VNU amortizado e caixa suficiente","98%","quitação integral",ND,ND)],
      "CRI_V177":[("Avaliação","termo integral necessário para a lista comparável",ND,ND,ND,ND)],
    }
    for vehicle_id,items in templates.items():
        src=FIDCS[vehicle_id]["reg_src"] if vehicle_id in FIDCS else CRIS[vehicle_id]["source"]
        for typ,desc,param,cons,quorum,cure in items:
            rows.append({"veiculo_id":vehicle_id,"tipo":typ,"descricao_do_gatilho":desc,"parametro_numerico":param,"consequencia_automatica":cons,"quorum_de_dispensa":quorum,"prazo_de_cura":cure,"ja_ocorreu":"n/d","data_da_ocorrencia":ND,"fonte_id":src,"status":"Documentado" if param!=ND else "n/d","nota_metodo":"Ocorrência histórica não é inferida a partir da cláusula contratual."})
    return rows


def build_subscribers(source_root:Path, fidc:dict[str,pd.DataFrame]) -> list[dict]:
    offers=read_csv(source_root/"ofertas"/"oferta_resolucao_160.csv")
    rows=[]
    for vehicle_id,meta in CRIS.items():
        hit=offers[pd.to_numeric(offers["Numero_Requerimento"],errors="coerce").eq(meta["offer_req"])]
        if hit.empty:
            data=None
        else:
            data=hit.iloc[0]
        closed=data is not None and str(data.get("Status_Requerimento","")).lower().find("encerrada")>=0
        def value(col):
            return int(nz(data.get(col))) if data is not None and closed else ND
        pf=value("Num_Invest_Pessoa_Natural")
        funds=value("Num_Invest_Fundos_Investimento")
        ifs=sum(value(c) if isinstance(value(c),int) else 0 for c in ["Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib","Num_Invest_Instit_Financ_Emissora_Partic_Consorcio","Num_Invest_Demais_Instit_Financ"]) if closed else ND
        pjs=sum(value(c) if isinstance(value(c),int) else 0 for c in ["Num_Invest_Companhia_Seguradora","Num_Invest_Investidor_Estrangeiro","Num_Invest_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio","Num_Invest_Demais_Pessoa_Juridica","Num_Invest_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio"]) if closed else ND
        total=sum(x for x in (pf,funds,ifs,pjs) if isinstance(x,int)) if closed else ND
        retail_qty=nz(data.get("Qtde_VM_Pessoa_Natural")) if data is not None and closed else None
        registered=nz(data.get("Qtde_Total_Registrada")) if data is not None and closed else None
        rows.append({"veiculo_id":vehicle_id,"serie":"Oferta pública agregada","qtd_cotistas_PF":pf,"qtd_fundos":funds,"qtd_IFs":ifs,"qtd_outras_PJ":pjs,"qtd_total":total,"ticket_medio_R$":meta["publico"]/total if isinstance(total,int) and total else ND,"pct_distribuido_varejo":pct(retail_qty,registered),"coordenadores":nd(data.get("Nome_Lider")) if data is not None else ND,"titulares_atuais":ND,"concentracao_maior_titular":ND,"fonte_da_posicao":"distribuição na emissão; posição corrente não pública","data_base":iso(data.get("Data_Encerramento")) if data is not None and closed else iso(data.get("Data_Registro")) if data is not None else ND,"fonte_id":"CVM_OFERTAS_RCVM160_20260822","status":"Documentado" if closed else "n/d","nota_metodo":"Contagem de investidores na oferta encerrada. Zeros da oferta VERT 177 não são tratados como posição corrente nem como ausência de investidores."})
    x1=fidc["X_1"]
    for vehicle_id,meta in FIDCS.items():
        for _,r in x1[x1["_cnpj"].eq(meta["cnpj"])].iterrows():
            rows.append({"veiculo_id":vehicle_id,"serie":r["TAB_X_CLASSE_SERIE"],"qtd_cotistas_PF":ND,"qtd_fundos":ND,"qtd_IFs":ND,"qtd_outras_PJ":ND,"qtd_total":int(nz(r["TAB_X_NR_COTST"])),"ticket_medio_R$":ND,"pct_distribuido_varejo":ND,"coordenadores":ND,"titulares_atuais":ND,"concentracao_maior_titular":ND,"fonte_da_posicao":"Informe Mensal: número total da classe; tipo de investidor por classe n/d","data_base":FIDC_BASE,"fonte_id":"CVM_FIDC_202607_X1","status":"Documentado","nota_metodo":"A distribuição por tipo não é imputada a partir do total da classe."})
    return rows


def public_registered_volume(source_root:Path):
    offers=read_csv(source_root/"ofertas"/"oferta_resolucao_160.csv")
    requests={meta["offer_req"] for meta in CRIS.values()}
    selected=offers[pd.to_numeric(offers["Numero_Requerimento"],errors="coerce").isin(requests)]
    if selected["Numero_Requerimento"].nunique()!=len(requests):
        return ND
    values=pd.to_numeric(selected["Valor_Total_Registrado"],errors="coerce")
    return ND if values.isna().any() else values.sum()/1e6


def build_cessions() -> tuple[list[dict],list[dict]]:
    cessions=[
      {"data":"2023-12-29","fidc_cedente":"FIDC_II","cri_cessionario":"CRI_K1","volume_R$mi":150.00133875,"pct_do_pool_do_CRI":150.00133875/600.00410190,"preco_pct_saldo":ND,"cessao_direta_do_originador":"não","fonte_id":"ANX_CRI1_PROSP_20240216","status":"Documentado","nota_metodo":"Preço total impresso; percentual sobre o pool usa a soma documentada das duas cessões."},
      {"data":"2023-12-29","fidc_cedente":"FIDC_IV","cri_cessionario":"CRI_K1","volume_R$mi":450.00276315,"pct_do_pool_do_CRI":450.00276315/600.00410190,"preco_pct_saldo":ND,"cessao_direta_do_originador":"não","fonte_id":"ANX_CRI1_PROSP_20240216","status":"Documentado","nota_metodo":"Preço total impresso; percentual sobre o pool usa a soma documentada das duas cessões."},
      {"data":"2024-05-24","fidc_cedente":"FIDC_II","cri_cessionario":"CRI_K2","volume_R$mi":ND,"pct_do_pool_do_CRI":ND,"preco_pct_saldo":ND,"cessao_direta_do_originador":"não","fonte_id":"ANX_CRI2_RATING_202406","status":"Documentado","nota_metodo":"Cedente e data documentados; volume e preço percentual não localizados."},
      {"data":"2024-05-24","fidc_cedente":"FIDC_IV","cri_cessionario":"CRI_K2","volume_R$mi":ND,"pct_do_pool_do_CRI":ND,"preco_pct_saldo":ND,"cessao_direta_do_originador":"não","fonte_id":"ANX_CRI2_RATING_202406","status":"Documentado","nota_metodo":"Cedente e data documentados; volume e preço percentual não localizados."},
    ]
    matrix=[]
    for fidc_id in FIDCS:
        row={"fidc":fidc_id}
        for cri_id in CRIS:
            docs=[x for x in cessions if x["fidc_cedente"]==fidc_id and x["cri_cessionario"]==cri_id]
            if docs:
                d=docs[0]; vol=f"R$ {d['volume_R$mi']:.3f} mi" if isinstance(d["volume_R$mi"],float) else "volume n/d"
                row[cri_id]=f"Cedeu — {d['data']}; {vol}"
            elif fidc_id=="FIDC_IV":
                row[cri_id]="Pode ceder: n/d — regulamento não publica WAM/ticket suficientes"
            else:
                f,c=ELIG[fidc_id],ELIG[cri_id]
                blockers=[]
                if isinstance(f["ticket_max_PF_R"],(int,float)) and isinstance(c["ticket_max_PF_R"],(int,float)) and f["ticket_max_PF_R"]>c["ticket_max_PF_R"]: blockers.append("selecionar PF abaixo do teto do CRI")
                if isinstance(f["wam_max_dias"],(int,float)) and isinstance(c["wam_max_dias"],(int,float)) and f["wam_max_dias"]>c["wam_max_dias"]: blockers.append("pool com WAM ≤ teto do CRI")
                row[cri_id]="Pode ceder — " + ("; ".join(blockers) if blockers else "mandato contém CCB que pode passar nos critérios")
        row.update({"fonte_id":"METH_MATRIZ_ELEGIBILIDADE","status":"Inferido","nota_metodo":"Cedeu exige documento; Pode ceder cruza mandato, tipo, prazo, WAM e ticket. Não comprova que uma fita concreta passa."})
        matrix.append(row)
    return matrix,cessions


def build_costs(series_rows:list[dict]) -> list[dict]:
    rows=[]
    for r in series_rows:
        rows.append({"veiculo_id":r["veiculo_id"],"serie":r["serie"],"saldo_atual_R$":r["saldo_atual_R$"],"indexador":r["indexador"],"taxa_contratada":r["taxa_contratada"],"taxa_equivalente_CDI_hoje":ND,"taxa_equivalente_pre_hoje":ND,"spread_sobre_DI_bps":ND,"custo_ponderado_da_camada":ND,"custo_medio_ponderado_das_cotas_publicas":ND,"custo_da_subordinada":ND,"custos_fixos_anualizados_bps":ND,"custo_distribuicao_uma_vez_bps":ND,"custo_all_in_bps":ND,"data_base":ACCESS_DATE,"fonte_id":r["fonte_id"],"status":"n/d","nota_metodo":"Equivalências dependem da curva DI futura e inflação implícita da data-base; a curva datada não foi obtida. Taxa contratada permanece documentada."})
    known={
      "FIDC_I":"admin 0,074% + gestão 0,20% + custódia 0,031%; mínimos aplicáveis",
      "FIDC_II":"admin por fórmula/escala; gestão 0,12%; custódia 0,02%; cobrança 1% da carteira líquida de PDD",
      "FIDC_III":"admin 0,04%; gestão 0,20%; custódia 0,02%; cobrança 1% da carteira líquida; mínimos",
      "FIDC_IV":"admin R$15 mil/mês; gestão deduzida; custódia 0,02%; adicional inicial",
      "FIDC_V":"admin 0,09% + gestão 0,30% + custódia 0,03%; mínimos",
      "FIDC_VI":"admin 0,10% + gestão 0,20% + custódia 0,02%; distribuição até 0,60%",
      "FIDC_VII":"admin 0,10% + gestão 0,20% + custódia 0,02%; distribuição até 0,60%",
      "CRI_K1":"distribuição ampla R$13,8567 mi / 2,3566% da oferta pública; rating anual R$100 mil",
    }
    for vehicle_id in list(FIDCS)+list(CRIS):
        src=FIDCS[vehicle_id]["reg_src"] if vehicle_id in FIDCS else CRIS[vehicle_id]["source"]
        rows.append({"veiculo_id":vehicle_id,"serie":"Resumo do veículo","saldo_atual_R$":ND,"indexador":"misto","taxa_contratada":ND,"taxa_equivalente_CDI_hoje":ND,"taxa_equivalente_pre_hoje":ND,"spread_sobre_DI_bps":ND,"custo_ponderado_da_camada":ND,"custo_medio_ponderado_das_cotas_publicas":ND,"custo_da_subordinada":ND,"custos_fixos_anualizados_bps":ND,"custo_distribuicao_uma_vez_bps":235.66 if vehicle_id=="CRI_K1" else ND,"custo_all_in_bps":ND,"data_base":ACCESS_DATE,"fonte_id":src,"status":"n/d","nota_metodo":known.get(vehicle_id,"Custos públicos insuficientes para anualizar todos os componentes. O all-in permanece n/d; preço de cessão, hedge e capital retido também não estão capturados.")})
    return rows


def build_payment_schedule(source_root:Path, series_rows:list[dict]) -> list[dict]:
    frames=[]; ap_frames=[]
    for year in (2024,2025,2026):
        frame=read_zip_member(source_root/f"inf_mensal_cri_{year}.zip",f"inf_mensal_cri_classe_{year}")
        if frame is not None:
            frame["_year"]=year; frames.append(frame)
        ap_frame=read_zip_member(source_root/f"inf_mensal_cri_{year}.zip",f"inf_mensal_cri_ativo_passivo_{year}")
        if ap_frame is not None:
            ap_frame["_year"]=year; ap_frames.append(ap_frame)
    allc=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    allap=pd.concat(ap_frames,ignore_index=True) if ap_frames else pd.DataFrame()
    rows=[]
    canonical={(r["veiculo_id"],str(r["isin"])):r for r in series_rows if r["veiculo_id"].startswith("CRI_")}
    for vehicle_id,meta in CRIS.items():
        subset=allc[allc["Codigo_Identificacao_Certificado"].astype(str).eq(meta["code"])].copy() if not allc.empty else pd.DataFrame()
        if not subset.empty:
            subset["_date"]=pd.to_datetime(subset["Data_Referencia"],errors="coerce")
            subset=subset.sort_values(["Codigo_ISIN","Numero_Serie","_date"])
            ap_subset=allap[allap["Codigo_Identificacao_Certificado"].astype(str).eq(meta["code"])].copy() if not allap.empty else pd.DataFrame()
            if not ap_subset.empty:
                ap_subset["_date"]=pd.to_datetime(ap_subset["Data_Referencia"],errors="coerce")
                if "Versao" in ap_subset.columns:
                    ap_subset=ap_subset.sort_values(["_date","Versao"]).drop_duplicates("_date",keep="last")
            balance_by_index={}; mode_by_date={}
            for report_date,date_group in subset.groupby("_date"):
                control_rows=ap_subset[ap_subset["_date"].eq(report_date)] if not ap_subset.empty else pd.DataFrame()
                control=num(control_rows.iloc[-1].get("Valor_Atualizado_Emissao")) if not control_rows.empty else None
                reconciled,mode=reconcile_certificate_balances(date_group,control)
                balance_by_index.update(reconciled); mode_by_date[report_date]=mode
            resolved=[]
            for _,r in subset.iterrows():
                isin=str(r.get("Codigo_ISIN") or "")
                series_no=int(nz(r.get("Numero_Serie"))) if nz(r.get("Numero_Serie")) else None
                match=canonical.get((vehicle_id,isin))
                if match is None and series_no:
                    candidate=[s for s in series_rows if s["veiculo_id"]==vehicle_id and s["serie"]==f"Série {series_no}"]
                    match=candidate[0] if candidate else None
                if match is None:
                    continue
                resolved.append((match,r))
            resolved.sort(key=lambda item:(item[0]["serie"],item[1]["_date"]))
            previous={}
            for match,r in resolved:
                key=(vehicle_id,match["serie"])
                closing=balance_by_index.get(r.name)
                first_observation=key not in previous
                initial=previous[key] if not first_observation else None
                balance_mode=mode_by_date.get(r["_date"],"n/d")
                initial_note=" Saldo inicial da primeira competência permanece n/d; Total_Integralizado não foi usado como saldo corrente." if first_observation else ""
                rows.append({"veiculo_id":vehicle_id,"serie":match["serie"],"camada":match["camada"],"competencia":iso(r["Data_Referencia"]),"saldo_inicial":nd(initial),"juros_programados":ND,"amortizacao_programada":ND,"saldo_final":nd(closing),"juros_pagos_realizado":nd(r.get("Rendimentos")),"amortizacao_paga_realizada":nd(r.get("Amortizacoes")),"status":"Realizado","fonte_id":f"CVM_CRI_{int(r['_year'])}_CLASSE","status_dado":"Documentado","nota_metodo":f"Saldo final: {balance_mode}, controlado por Valor_Atualizado_Emissao. Unidade sem reconciliação permanece n/d; pagamentos realizados ficam documentados.{initial_note}"})
                previous[key]=closing
        # One explicit gap row per series makes the absence of contractual curves auditable.
        for s in [x for x in series_rows if x["veiculo_id"]==vehicle_id]:
            rows.append({"veiculo_id":vehicle_id,"serie":s["serie"],"camada":s["camada"],"competencia":s["data_vencimento"],"saldo_inicial":ND,"juros_programados":ND,"amortizacao_programada":ND,"saldo_final":ND,"juros_pagos_realizado":ND,"amortizacao_paga_realizada":ND,"status":"Projetado","fonte_id":meta["source"],"status_dado":"n/d","nota_metodo":"Curva contratual mensal completa não localizada; a data de vencimento não foi transformada em projeção bullet."})
    return rows


def combined_fidc_history(source_root:Path, table:str) -> pd.DataFrame:
    records=[]
    target={FIDCS["FIDC_II"]["cnpj"],FIDCS["FIDC_IV"]["cnpj"]}
    for year in (2023,2024):
        path=source_root/f"inf_mensal_fidc_{year}.zip"
        pattern=re.compile(re.escape(f"inf_mensal_fidc_tab_{table}_{year}")+r"\d{2}\.csv$",re.IGNORECASE)
        with zipfile.ZipFile(path) as zf:
            for name in sorted(n for n in zf.namelist() if pattern.search(n)):
                text=zf.read(name).decode("latin1","ignore")
                lines=text.splitlines()
                if not lines: continue
                header=next(csv.reader([lines[0]],delimiter=";"))
                for line in lines[1:]:
                    if not any(cnpj in norm_cnpj(line.split(";",2)[1] if ";" in line else "") for cnpj in target):
                        continue
                    values=next(csv.reader([line],delimiter=";"))
                    if len(values)!=len(header):
                        continue
                    row=dict(zip(header,values)); row["_year"]=year; row["_cnpj"]=norm_cnpj(row.get("CNPJ_FUNDO_CLASSE") or row.get("CNPJ_FUNDO")); records.append(row)
    return pd.DataFrame(records)


def build_before_after(source_root:Path) -> list[dict]:
    ti=combined_fidc_history(source_root,"I"); tiv=combined_fidc_history(source_root,"IV"); tv=combined_fidc_history(source_root,"V"); tx=combined_fidc_history(source_root,"X_2")
    rows=[]
    events=[("2023-12-31","CRI_K1",["FIDC_II","FIDC_IV"]),("2024-05-31","CRI_K2",["FIDC_II","FIDC_IV"])]
    for event_date,cri_id,fidc_ids in events:
        ev=pd.Timestamp(event_date)
        for fidc_id in fidc_ids:
            cnpj=FIDCS[fidc_id]["cnpj"]
            subset=tiv[tiv["_cnpj"].eq(cnpj)].copy(); subset["_date"]=pd.to_datetime(subset["DT_COMPTC"],errors="coerce")
            for _,plr in subset.iterrows():
                d=plr["_date"]; mob=(d.year-ev.year)*12+d.month-ev.month
                if mob < -3 or mob > 3: continue
                ir=ti[(ti["_cnpj"].eq(cnpj)) & (pd.to_datetime(ti["DT_COMPTC"],errors="coerce").eq(d))]
                vr=tv[(tv["_cnpj"].eq(cnpj)) & (pd.to_datetime(tv["DT_COMPTC"],errors="coerce").eq(d))]
                if ir.empty: continue
                ir=ir.iloc[0]; portfolio=nz(ir.get("TAB_I2_VL_CARTEIRA")); allowance=nz(ir.get("TAB_I2A11_VL_REDUCAO_RECUP"))+nz(ir.get("TAB_I2B11_VL_REDUCAO_RECUP"))
                over90=ND
                if not vr.empty:
                    vr=vr.iloc[0]; over90=sum(nz(vr.get(f"TAB_V_B{idx}_VL_INAD_{suffix}")) for idx,suffix in [(4,"120"),(5,"150"),(6,"180"),(7,"360"),(8,"720"),(9,"1080"),(10,"MAIOR_1080")])
                xrows=tx[(tx["_cnpj"].eq(cnpj)) & (pd.to_datetime(tx["DT_COMPTC"],errors="coerce").eq(d))]
                sub_nav=0.0; support_rows=0
                for _,xr in xrows.iterrows():
                    if "senior" not in str(xr.get("TAB_X_CLASSE_SERIE","")).lower() and "sênior" not in str(xr.get("TAB_X_CLASSE_SERIE","")).lower():
                        support_rows+=1; sub_nav+=nz(xr.get("TAB_X_QT_COTA"))*nz(xr.get("TAB_X_VL_COTA"))
                pl=nz(plr.get("TAB_IV_A_VL_PL"))
                rows.append({"fidc":fidc_id,"cri_evento":cri_id,"competencia":iso(d),"mob":mob,"pl_R$mi":pl/1e6,"carteira_R$mi":portfolio/1e6,"pdd_pct_carteira":pct(allowance,portfolio),"saldo_90d_pct_carteira":pct(over90,portfolio) if isinstance(over90,(int,float)) else ND,"wam_observado":ND,"ticket_medio":ND,"subordinacao_pct":pct(sub_nav,pl) if support_rows else ND,"evento":"cessão em t=0" if mob==0 else "janela t−3 a t+3","leitura":"Os agregados mostram a trajetória do denominador, PDD e atraso. Sem tape por CCB, não se separa seleção do pool de mudança de denominador.","fonte_id":f"CVM_FIDC_{int(plr['_year'])}_I_IV_V_X2 | {CRIS[cri_id]['source']}","status":"Documentado","nota_metodo":"Meses relativos ao fechamento da competência da cessão; ausência de classe subordinada identificável, aging, WAM ou ticket permanece n/d."})
    return rows


def build_comparison() -> list[dict]:
    items=[
      ("Velocidade de originação","Veículo warehouse compra continuamente enquanto há revolvência e capital.","Oferta exige documentação, registro, bookbuilding quando aplicável e liquidação.","FIDC","mandato e períodos de revolvência dos regulamentos","tempo de execução comparável por operação"),
      ("Prazo do passivo","Depende do suplemento; vários vencimentos efetivos estão n/d nos documentos públicos.","Séries chegam a 2038 e alongam o funding do pool cedido.","CRI","02_Series e 05_Prazos_WAM","vencimentos efetivos dos FIDCs"),
      ("Risco de rollover","Surge no fim da revolvência e no vencimento das cotas; datas n/d limitam quantificação.","Take-out trava prazo por série e reduz rollover do pool transferido.","CRI","05_Prazos_WAM","cronogramas completos dos FIDCs"),
      ("Custo","Taxas e custos recorrentes são parcialmente públicos.","Taxas contratadas são públicas; equivalência DI/all-in está n/d sem curva datada e custos completos.","neutro","12_Custo_Captacao","curva B3/inflação implícita, hedge, preço de cessão e custos recorrentes"),
      ("Base de investidores","Cotas públicas concentram investidores qualificados/profissionais conforme a oferta.","Ofertas encerradas alcançaram milhares de pessoas físicas em várias emissões.","CRI","10_Subscritores","posição corrente por titular"),
      ("Granularidade exigida do pool","Limites variam de 0,10% a 20%; alguns FIDCs têm caps de top 10/integrador.","CRIs normalmente apertam WAM e concentração individual do pool cedido.","CRI","03_Elegibilidade e 04_Concentracao","tape atual por CCB"),
      ("Retenção de risco","Júnior costuma ficar com a originadora/relacionadas e pode ter saque condicionado.","Série privada subordinada fica com Solfácil/relacionadas nas estruturas documentadas.","neutro","02_Series e 07_Subordinada","titularidade corrente e capital econômico retido"),
      ("Flexibilidade de revolvência","Permite compras e gestão do denominador durante o período contratual.","Pool fica vinculado; amortização e substituições seguem o termo.","FIDC","06_Waterfall","uso efetivo de substituições por operação"),
      ("Custo fixo por veículo","Administração, gestão, custódia e cobrança recorrem durante a vida do fundo.","Distribuição, securitização, agente, rating e escrituração incidem por emissão.","neutro","12_Custo_Captacao","todas as faturas e PL médio"),
      ("Transparência pós-emissão","Informe Mensal publica PL, carteira, aging e cotas por classe.","Informe Mensal publica saldo, créditos, pagamentos e classes; posição de investidores permanece n/d.","FIDC","08_PDD, 10_Subscritores e 13_Cronograma","tape por CCB e posição corrente"),
    ]
    return [{"dimensao":a,"como_funciona_no_FIDC":b,"como_funciona_no_CRI":c,"vantagem_real":d,"evidencia":e,"o_que_falta_para_confirmar":f,"fonte_id":"METH_COMPARACAO_FIDC_CRI","status":"Inferido","nota_metodo":"Veredito limitado às fontes públicas listadas; n/d não é convertido em vantagem."} for a,b,c,d,e,f in items]


def build_conflicts(series_rows:list[dict], public_registered_R_mi) -> list[dict]:
    raw=[
      ("CRI_K1","volume da emissão","R$600 mi","ANX_XP_20260428","R$588 mi público / R$603 mi total","ANX_CRI1_PROSP_20240216","R$588 mi público; R$603 mi total","O deck arredonda e mistura perímetros; o prospecto separa oferta pública e série privada."),
      ("CRI_K1","taxa Série 3","16,48% (número)","ANX_CRI1_PROSP_20240216 p.14","17,48% (por extenso)","ANX_CRI1_PROSP_20240216 p.211","16,48% com conflito=sim","O valor numérico foi preservado; confirmação operacional continua pendente."),
      ("CRI_K1","gatilho de atraso","3 meses","ANX_XP_20260428 p.17","2 verificações; 3 conformes para cura","ANX_CRI1_PROSP_20240216 p.228","2 verificações","O termo definitivo define o gatilho e distingue a cura."),
      ("CRI_K1","custo de distribuição","R$13,8567 mi","ANX_CRI1_PROSP_20240216 p.85","R$1,5732 mi","ANX_CRI1_PROSP_20240216 p.312","R$13,8567 mi como custo amplo; subtotal separado","A tabela ampla contém distribuição e prestadores; o anexo é subtotal restrito."),
      ("CRI_K2","volume","R$727,5 mi","ANX_CRI2_BOOK_20240620","R$750,0 mi","ANX_XP_20260428 p.16","R$727,5 mi público; R$750,0 mi total","A diferença é a série privada de R$22,5 mi."),
      ("CRI_K2","identificadores no Informe Mensal","ISINs/maturidades copiados da 1ª emissão","CVM_CRI_2026_CLASSE","ISINs e vencimentos da 2ª emissão","ANX_CRI2_RATING_202406","documentos da oferta; saldo por número da série","O filing corrente contém campos incompatíveis com a emissão."),
      ("CRI_K3","volume","R$600 mi","ANX_XP_20260428 p.11","R$750 mi total / R$727,5 mi público","CVM_OFERTAS_RCVM160_20260822 | CVM_CRI_2026_CLASSE","R$727,5 mi público; R$750 mi total","Oferta encerrada e Informe Mensal têm competência e perímetro definidos."),
      ("CRI_K3","taxa contratada","taxas preliminares/tetos","ANX_CRI3_LAM_PREL_20250422","campo Taxa_Juros inválido no filing","CVM_CRI_2026_CLASSE","taxa contratada n/d; preliminar em coluna própria","Teto de bookbuilding não é taxa final."),
      ("CRI_K4","número de séries e volume","7 séries / R$450 mi","ANX_XP_20260428","6 séries públicas / R$436,5 mi","ANX_CRI4_INICIO_20250929","7 totais: 6 públicas + 1 privada; R$450 mi total","Os dois números descrevem perímetros distintos."),
      ("CRI_K4","data de emissão","2025-09-28","CVM_CRI_2026_CLASSE","2025-09-29 (registro/anúncio)","ANX_CRI4_INICIO_20250929","2025-09-28 emissão; 2025-09-29 registro/anúncio","As datas se referem a eventos jurídicos diferentes."),
      ("CRI_V174","data","2026-05-29","USER_REQUEST_20260822","2026-05-20 emissão; encerramento 2026-05-28","CVM_CRI_2026_GERAL | CVM_OFERTAS_RCVM160_20260822","2026-05-20","O Informe Mensal identifica a data jurídica da emissão."),
      ("CRI_V177","data","2026-07-31","USER_REQUEST_20260822","2026-07-21 emissão; termo/anúncio 2026-07-20","CVM_FUNDOSNET_VERT177_20260720","2026-07-21","O termo fixa a emissão; 31/07 não é a data jurídica documentada."),
      ("Universo","quantidade de séries","34 séries totais","USER_REQUEST_20260822","31 identificadores no resultado agregado inicial da busca B3","UNIVERSO_SEARCH_20260822","34 séries: 28 públicas + 6 privadas, confirmadas nos seis termos","Os termos por emissão prevalecem; a visão agregada de busca omitiu três séries e não define o universo contratual."),
      ("FIDC_II","targets de capital","80% / 16% / 6%","DOC_FIDC_II_REG_202412","soma 102%","METH_RECONCILIACAO","preservar redação; não normalizar","Inconsistência aritmética do regulamento permanece explícita."),
      ("CRI_K1","limite PF/PJ","valor nominal no resumo","ANX_CRI1_PROSP_20240216","valor presente no termo consolidado","ANX_CRI1_PROSP_20240216","valor presente","O termo consolidado é a redação contratual específica."),
      ("CRI_K1","volume na página da securitizadora","R$600 mi","KANASTRA_API_20260822","R$588 mi público / R$603 mi total","ANX_CRI1_PROSP_20240216","R$588 mi público; R$603 mi total","A página comercial arredonda o volume; o prospecto separa oferta pública e série privada."),
      ("CRI_K3","número da emissão na página da securitizadora","1ª emissão","KANASTRA_API_20260822","3ª emissão","CVM_FUNDOSNET_TERMOS_CRI_20260822","3ª emissão","O termo oficial define a numeração jurídica da emissão."),
      ("CRI_V177","data no portal da securitizadora","2026-07-08","VERT_DATA_20260822","2026-07-21","CVM_FUNDOSNET_VERT177_20260720","2026-07-21","O termo oficial fixa a data jurídica; o portal exibe uma data operacional distinta."),
      ("CRIs","unidade de Valor_Certificados no Informe Mensal","saldo agregado em R$ em parte das competências","CVM_CRI_2024_CLASSE","valor unitário próximo de R$1 mil em outras competências","CVM_CRI_2026_CLASSE","usar apenas saldo claramente agregado; caso ambíguo = n/d","A unidade muda no próprio campo e a quantidade corrente não reconcilia o valor unitário; nenhuma multiplicação ou roll-forward foi estimado."),
    ]
    public_series=sum(r["montante_emitido_R$"] for r in series_rows if r["veiculo_id"].startswith("CRI_") and r["colocacao"]=="pública" and isinstance(r["montante_emitido_R$"],(int,float)))/1e6
    raw.append(("Universo","volume público agregado",f"R$ {public_registered_R_mi:.6f} mi" if isinstance(public_registered_R_mi,(int,float)) else ND,"CVM_OFERTAS_RCVM160_20260822",f"R$ {public_series:.6f} mi","CVM_FUNDOSNET_TERMOS_CRI_20260822",f"R$ {public_registered_R_mi:.6f} mi no agregado; valores por série preservados" if isinstance(public_registered_R_mi,(int,float)) else "agregado n/d; valores por série preservados","O agregado adota o volume registrado na CVM; os valores nominais individuais permanecem como publicados nos termos. A diferença de pequena monta continua explícita."))
    source_bases={
      "ANX_XP_20260428":"2026-04-28","ANX_CRI1_PROSP_20240216":"2024-02-16","ANX_CRI2_BOOK_20240620":"2024-06-20",
      "ANX_CRI2_RATING_202406":"2024-06-01 a 2024-06-30","ANX_CRI3_LAM_PREL_20250422":"2025-04-22","ANX_CRI4_INICIO_20250929":"2025-09-29",
      "CVM_CRI_2024_CLASSE":"2024-01-01 a 2024-12-31","CVM_CRI_2026_CLASSE":"2026-06-01","CVM_CRI_2026_GERAL":"2026-06-01",
      "CVM_OFERTAS_RCVM160_20260822":"2026-08-20","CVM_FUNDOSNET_VERT177_20260720":"2026-07-20",
      "CVM_FUNDOSNET_TERMOS_CRI_20260822":"2026-08-22","DOC_FIDC_II_REG_202412":"2024-12-01 a 2024-12-31",
      "KANASTRA_API_20260822":"2026-08-22","VERT_DATA_20260822":"2026-08-22","USER_REQUEST_20260822":"2026-08-22",
      "UNIVERSO_SEARCH_20260822":"2026-08-22","METH_RECONCILIACAO":"2026-08-22",
    }
    def conflict_base(source_label:str) -> str:
        values=[]
        for token in source_label.split("|"):
            source_id=re.sub(r" p\.\d+$","",token.strip())
            value=source_bases.get(source_id,ND)
            if value not in values:
                values.append(value)
        return " | ".join(values)
    return [{"conflito_id":f"CONF_{i:02d}","veiculo_id":v,"campo":field,"valor_fonte_A":a,"fonte_A":sa,"data_base_A":conflict_base(sa),"valor_fonte_B":b,"fonte_B":sb,"data_base_B":conflict_base(sb),"valor_adotado":adopt,"decisao_justificativa":why,"conflito":"sim","fonte_id":source_join(re.sub(r" p\.\d+$","",sa),re.sub(r" p\.\d+$","",sb)),"status":"Documentado","nota_metodo":"Conflito tratado explicitamente; nenhuma fonte foi sobrescrita silenciosamente."} for i,(v,field,a,sa,b,sb,adopt,why) in enumerate(raw,1)]


def build_sources(source_root:Path, attachments:Path) -> list[dict]:
    rows=[]
    def add(source_id,doc,url,base,page,status="obtido",sha=ND,note=""):
        rows.append({"fonte_id":source_id,"documento":doc,"url_ou_caminho":url,"data_acesso":ACCESS_DATE,"data_base":base,"trecho_ou_pagina":page,"status_obtencao":status,"sha256":sha,"observacao":note,"status":"Documentado" if status=="obtido" else "n/d","nota_metodo":"Inventário fechado antes do build; fontes não obtidas permanecem registradas."})
    add("CVM_CADASTRO_20260821","Cadastro de Fundos/Classes CVM","https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip","2026-08-21","linhas dos 7 CNPJs")
    for suffix,page in [("I_IV","Tabelas I e IV"),("X2","Tabela X_2"),("X1","Tabela X_1"),("I_V","Tabelas I e V"),("VIII","Tabela VIII"),("I_V_X2","Tabelas I, V e X_2")]:
        add(f"CVM_FIDC_202607_{suffix}","Informe Mensal FIDC 2026-07","https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202607.zip",FIDC_BASE,page)
    for year in (2023,2024): add(f"CVM_FIDC_{year}_I_IV_V_X2",f"Informe Mensal FIDC {year}",f"https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_{year}.zip",f"{year}-01-01 a {year}-12-31","Tabelas I, IV, V e X_2")
    cri_coverage={2024:"2024-01-01 a 2024-12-31",2025:"2025-01-01 a 2025-12-31",2026:"2026-01-01 a 2026-06-01"}
    for year in (2024,2025,2026): add(f"CVM_CRI_{year}_CLASSE",f"Informe Mensal CRI {year}",f"https://dados.cvm.gov.br/dados/SEC/DOC/INF_MENSAL/DADOS/inf_mensal_cri_{year}.zip",cri_coverage[year],"classe/série")
    for suffix,page in [("GERAL_ATIVO","geral e ativo/passivo"),("ATIVO_CARTEIRA","ativo/passivo e carteira"),("CREDITOS","créditos")]: add(f"CVM_CRI_2026_{suffix}","Informe Mensal CRI 2026","https://dados.cvm.gov.br/dados/SEC/DOC/INF_MENSAL/DADOS/inf_mensal_cri_2026.zip","2026-06-01",page)
    add("CVM_OFERTAS_RCVM160_20260822","Ofertas Públicas — RCVM 160","https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip","2026-08-22","requerimentos 4201, 15843, 20290, 22096, 25971, 27183")
    regs=[("I","2024-11","2024-11-01 a 2024-11-30","d70daa3"),("II","2024-12","2024-12-01 a 2024-12-31","025001"),("III","2025-12","2025-12-01 a 2025-12-31","31378"),("IV","2025-10","2025-10-01 a 2025-10-31","38355"),("V","2024-11","2024-11-01 a 2024-11-30","4373"),("VI","2026-05","2026-05-01 a 2026-05-31","0d88"),("VII","2026-05","2026-05-01 a 2026-05-31","312d")]
    for roman,base,coverage,sha in regs: add(f"DOC_FIDC_{roman}_REG_{base.replace('-','')}",f"Regulamento Solfácil FIDC {roman}",str(source_root/f"fidc{['I','II','III','IV','V','VI','VII'].index(roman)+1}_reg_{base.replace('-','')}.pdf"),coverage,"páginas citadas em cada linha",sha=sha,note="Documento obtido via Fundos.NET; mês documental expresso como intervalo; hash abreviado no inventário.")
    add("ANX_XP_20260428","Analise-de-Credito-Solfacil-4.pdf",str(attachments/"Analise-de-Credito-Solfacil-4.pdf"),"2026-04-28","21 páginas",sha="121122ccca06d567c667382383628a640ce336ca6936bb75f26b92142c320f36")
    add("ANX_CRI1_PROSP_20240216","CRI Solfácil — Prospecto Definitivo — 1ª emissão",str(attachments/"CRI Solfácil - Prospecto Definitivo - 1emissao.pdf"),"2024-02-16","1.026 páginas",sha="dff12b90c7dadf7bc390a78c078bf23edfe271b914c19f5d6130263eec53130d")
    add("ANX_CRI2_BOOK_20240620","Comunicado ao Mercado — 2ª emissão",str(attachments/"Comunicado ao Mercado (1).pdf"),"2024-06-20","3 páginas",sha="6b50a8e593debb9a110f9fed9a5b64c685e7d651c6535f4e7ea3b0d1d2e2e675")
    add("ANX_CRI2_RATING_202406","Prospecto Definitivo Rating — 2ª emissão",str(attachments/"Prospecto Definitivo Rating.pdf"),"2024-06-01 a 2024-06-30","1.205 páginas",sha="c631",note="Mês documental expresso como intervalo; hash abreviado; documento local integral.")
    add("ANX_CRI3_LAM_PREL_20250422","CRI Solfácil III — Lâmina preliminar",str(attachments/"CRI Solfácil III - Lâmina da Oferta 22-04-2025_V007.pdf"),"2025-04-22","11 páginas",sha="42633730859c5763e3817e18588c7fa99bb95b4ebdf1391ff8db876e4ea3c5f8")
    add("ANX_CRI4_INICIO_20250929","Anúncio de Início — 4ª emissão Kanastra",str(attachments/"INICIO_SOLFACIL_29-09-2025_V005.pdf"),"2025-09-29","3 páginas",sha="1e04df",note="As duas cópias anexadas são idênticas; hash abreviado.")
    add("ANX_CRIV_LAM_PREL_20260417","CRI Solfácil V — Lâmina preliminar VERT 174ª",str(attachments/"CRI_Solfacil_V_Lamina_17.04.2026_v004.pdf"),"2026-04-17","11 páginas",sha="2b8bc77858879b7d7c4c138fb0d7846de7d30623118f80822a140a7f5963af07")
    add("CVM_FUNDOSNET_VERT177_20260720","Termo e Anúncio de Início VERT 177ª","https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=1260549 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=1260554","2026-07-20","5 séries; montantes, taxas e vencimentos")
    add("CVM_FUNDOSNET_TERMOS_CRI_20260822","Termos oficiais das seis operações","https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=605873 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=677969 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=917001 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=1001402 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=1166447 | https://fnet.bmfbovespa.com.br/fnet/publico/visualizarProtocoloDocumentoCVM?idDocumento=1260549",ACCESS_DATE,"contagem 5+5+6+7+6+5 = 34; 28 públicas + 6 privadas")
    add("KANASTRA_API_20260822","API pública de securitizações Kanastra","https://kanastra.com.br/api/website/securitizations?page=1&size=100",ACCESS_DATE,"15 emissões; quatro resultados Solfácil",note="A API não lista CRI Solfácil posterior à 4ª emissão Kanastra na data de acesso.")
    add("VERT_DATA_20260822","Portal público de emissões VERT","https://data.vert-capital.app/?q=Solfacil&company=securitizadora&skip_redirect=true",ACCESS_DATE,"VERT 174ª e 177ª; uma debênture de 2022",note="O portal não lista CRI Solfácil posterior à 177ª; a data exibida da 177ª diverge do termo oficial.")
    add("USER_REQUEST_20260822","Universo inicial informado no pedido","conversa local do trabalho",ACCESS_DATE,"datas e contagens indicadas como ponto de partida",note="Ponto de partida reconciliado com fontes públicas; não tratado como prova documental isolada.")
    add("UNIVERSO_SEARCH_20260822","Busca de universo CVM/B3/Fundos.NET/Kanastra/VERT","https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCertificadosCVM | https://dados.cvm.gov.br/dataset/oferta-distrib | https://kanastra.com.br/api/website/securitizations?page=1&size=100 | https://data.vert-capital.app/?q=Solfacil&company=securitizadora&skip_redirect=true",ACCESS_DATE,"SOLFACIL/SOLFÁCIL/SOL FACIL; Kanastra/VERT; entregas 2026-08-21 e 2026-08-22",note="Encontrados 7 FIDCs e 6 operações de CRI. Kanastra e VERT não listam emissão posterior; o CSV de ofertas tinha corte em 20/08/2026.")
    add("B3_CURVA_DI_20260822","B3 — Taxas Referenciais","https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-de-derivativos/indicadores/indicadores-financeiros/",ACCESS_DATE,"tentativa de curva datada","não localizado",note="Página dinâmica acessada; curva DI futura completa da data-base não extraída.")
    add("ANBIMA_CURVA_20260822","ANBIMA Data — curvas/estoque","https://data.anbima.com.br/",ACCESS_DATE,"tentativa de inflação implícita/estoque","não localizado",note="Série datada necessária para equivalência; sem estimativa manual.")
    for source_id,doc in [("METH_WATERFALL_COMPARATIVO","Síntese comparativa de waterfalls"),("METH_MATRIZ_ELEGIBILIDADE","Cruzamento de elegibilidade"),("METH_COMPARACAO_FIDC_CRI","Matriz de comparação FIDC×CRI"),("METH_RECONCILIACAO","Reconciliação por código")]: add(source_id,doc,"gerado por tools/prepare_solfacil_data.py",ACCESS_DATE,"método reproduzível")
    return rows


def build_methodology() -> list[dict]:
    items=[
      ("WAM observado","Σ(saldo_i × dias até vencimento_i) / Σ saldo_i","dias","Exige tape por recebível; teto contratual fica em coluna separada.","METH_RECONCILIACAO"),
      ("Prazo máximo em meses","prazo_max_recebivel_dias / 30,4375","meses","Conversão de comparação; contrato continua regido em dias quando assim redigido.","METH_RECONCILIACAO"),
      ("Subordinação / attachment","(NAV mezanino + NAV júnior) / carteira bruta","% da carteira","NAV por classe vem do Informe Mensal; carteira bruta deve manter o mesmo perímetro.","CVM_FIDC_202607_X2"),
      ("Attachment após saque","(NAV mezanino pós + NAV júnior pós) / carteira bruta pós","% da carteira","Fica n/d sem valor/data do saque observado.","METH_RECONCILIACAO"),
      ("Folga ao piso","[Sub_NAV − piso × PL] / [1 − piso]","R$","Só calculável quando Sub_NAV, PL e piso têm a mesma competência.","METH_RECONCILIACAO"),
      ("PDD observada","redução ao valor de recuperação / carteira ou créditos","% da carteira","Denominador aparece no nome da coluna; não combina FIDC e CRI sem coluna de data-base.","CVM_FIDC_202607_I_V | CVM_CRI_2026_ATIVO_CARTEIRA"),
      ("Saldo acima de 90 dias","Σ faixas 91–120, 121–150, 151–180 e posteriores / carteira","% da carteira","A faixa CVM até 30 dias não permite separar 0–15 e 16–30.","CVM_FIDC_202607_I_V | CVM_CRI_2026_ATIVO_CARTEIRA"),
      ("Efeito vagão","sinalizar quando PDD / saldo >90d > 100%","sim/não/indício","Razão acima de 100% é indício; confirmação contratual vem do regulamento/termo.","METH_RECONCILIACAO"),
      ("Concentração observada","maior valor da Tabela VIII / carteira; top10 = soma dos 10 maiores / carteira","% da carteira","Tabela VIII não identifica os devedores; zeros publicados são preservados.","CVM_FIDC_202607_VIII"),
      ("Gap ativo–passivo","prazo legal da série mais longa − teto de WAM","meses","É um comparador conservador e não uma duration financeira.","METH_RECONCILIACAO"),
      ("Equivalência para DI","resolver taxa equivalente com curva DI futura B3 e inflação implícita NTN-B na data-base","bps sobre DI","Sem as curvas datadas, resultado permanece n/d; não há estimativa de cabeça.","B3_CURVA_DI_20260822 | ANBIMA_CURVA_20260822"),
      ("Custo all-in","custo ponderado das cotas/séries públicas + custos fixos anualizados / PL médio","bps a.a.","Preço de cessão, hedge e capital retido ficam fora salvo divulgação específica.","METH_RECONCILIACAO"),
      ("Saldo mensal realizado","Valor_Certificados quando claramente agregado em R$; saldo inicial = saldo final anterior documentado","R$","Na primeira competência, saldo inicial permanece n/d; Total_Integralizado não substitui saldo corrente. Valor unitário/ambíguo permanece n/d.","CVM_CRI_2026_CLASSE"),
      ("Antes/depois","competências t−3…t+3 relativas ao mês da cessão","índice/moeda/%","Sem tape por CCB, mudança de denominador e seleção do pool não são separáveis.","CVM_FIDC_2023_I_IV_V_X2 | CVM_FIDC_2024_I_IV_V_X2"),
    ]
    return [{"metrica":a,"formula":b,"unidade":c,"qualificador":d,"fonte_id":e,"status":"Documentado","nota_metodo":"Fórmula implementada em tools/prepare_solfacil_data.py quando os insumos existem."} for a,b,c,d,e in items]


def build_glossary() -> list[dict]:
    items=[
      ("Waterfall","Ordem contratual de uso do caixa para despesas, juros e principal de cada camada."),
      ("Pró-rata","Pagamento distribuído entre camadas conforme percentuais ou metas, condicionado aos testes."),
      ("Sequencial","Pagamento que quita primeiro a camada prioritária e só depois avança para a seguinte."),
      ("Attachment point","Parcela da carteira que absorve perda antes de a camada sênior começar a perder."),
      ("Efeito vagão","Regra que leva o atraso de uma parcela para a classificação do saldo integral do contrato."),
      ("Seasoning","Tempo mínimo de histórico do crédito antes de poder entrar na carteira."),
      ("Take-out","Transferência de créditos do veículo de estoque para uma emissão de prazo mais longo."),
      ("Warehouse","Veículo que acumula créditos antes da cessão ou securitização."),
      ("Cash sweep","Uso acelerado do caixa para reduzir principal quando um teste é descumprido."),
      ("MTM","Valor de mercado de uma posição, especialmente derivativos usados para proteção."),
      ("Cota subordinada","Cota que absorve perdas antes das cotas mais prioritárias."),
      ("Super sênior","Camada com primeira prioridade de pagamento e maior proteção estrutural."),
      ("Mezanino","Camada intermediária entre sênior e júnior na ordem de perdas e pagamentos."),
      ("PDD","Redução contábil que reconhece perda esperada ou risco de não recuperação dos créditos."),
      ("WAM","Prazo médio da carteira ponderado pelo saldo de cada recebível."),
      ("Revolvência","Período em que cobranças podem financiar novas aquisições em vez de amortizar cotas."),
      ("Desalavancagem","Mudança que acelera pagamento das camadas prioritárias após um gatilho."),
      ("Cessão","Transferência jurídica e econômica de créditos entre cedente e comprador."),
      ("Lastro","Conjunto de créditos que gera o caixa destinado ao pagamento da emissão."),
      ("Preço de aquisição","Valor pago pelos créditos; um limite percentual não revela o preço efetivo praticado."),
    ]
    return [{"termo":a,"definicao":b,"fonte_id":"METH_COMPARACAO_FIDC_CRI","status":"Documentado","nota_metodo":"Definição em português direto usada no workbook e no deck."} for a,b in items]


def build_panel(vehicles:list[dict], series:list[dict], conflicts:list[dict], cessions:list[dict], public_registered_R_mi) -> list[dict]:
    fidc_pl=sum(r["pl_ou_saldo_R$mi"] for r in vehicles if r["tipo"]=="FIDC" and isinstance(r["pl_ou_saldo_R$mi"],(int,float)))
    cri_total=sum(r["montante_emitido_R$"] for r in series if r["veiculo_id"].startswith("CRI_") and isinstance(r["montante_emitido_R$"],(int,float)))/1e6
    metrics=[
      ("indicador","FIDCs confirmados",7,"veículos",FIDC_BASE,"UNIVERSO_SEARCH_20260822","Sete fundos/classes I–VII; busca por VIII+ sem ocorrência."),
      ("indicador","Operações de CRI",6,"operações",ACCESS_DATE,"UNIVERSO_SEARCH_20260822","Kanastra 1ª–4ª e VERT 174ª/177ª."),
      ("indicador","Séries de CRI",sum(1 for r in series if r["veiculo_id"].startswith("CRI_")),"séries totais",ACCESS_DATE,"CVM_FUNDOSNET_VERT177_20260720 | CVM_CRI_2026_CLASSE","Inclui séries privadas."),
      ("indicador","Classes/subclasses FIDC",sum(1 for r in series if r["veiculo_id"].startswith("FIDC_")),"classes",FIDC_BASE,"CVM_FIDC_202607_X2","Posição da última competência."),
      ("indicador","Volume nominal total",cri_total,"R$ mi",ACCESS_DATE,"CVM_FUNDOSNET_TERMOS_CRI_20260822","Soma nominal das 34 séries; o agregado público CVM permanece em linha separada."),
      ("indicador","Volume público registrado",public_registered_R_mi,"R$ mi",ACCESS_DATE,"CVM_OFERTAS_RCVM160_20260822","Soma do Valor_Total_Registrado das seis ofertas."),
      ("indicador","PL dos FIDCs",fidc_pl,"R$ mi",FIDC_BASE,"CVM_FIDC_202607_I_IV","Soma simples dos sete veículos na mesma competência."),
      ("indicador","CRIs com Informe Mensal",5,"operações",ACCESS_DATE,"CVM_CRI_2026_GERAL_ATIVO","VERT 177 ainda sem competência publicada."),
      ("indicador","Cessões documentadas",len(cessions),"linhas",ACCESS_DATE,"ANX_CRI1_PROSP_20240216 | ANX_CRI2_RATING_202406","FIDC II/IV para CRI 1/2."),
      ("indicador","Conflitos reconciliados",len(conflicts),"campos",ACCESS_DATE,"METH_RECONCILIACAO","Cada decisão permanece na aba Conflitos."),
      ("mapa","Originação Solfácil",1,"etapa",ACCESS_DATE,"METH_COMPARACAO_FIDC_CRI","CCBs de financiamento solar entram no programa."),
      ("mapa","Warehouse FIDC",2,"etapa",ACCESS_DATE,"METH_COMPARACAO_FIDC_CRI","FIDCs acumulam e financiam créditos durante a revolvência permitida."),
      ("mapa","Take-out CRI",3,"etapa",ACCESS_DATE,"METH_COMPARACAO_FIDC_CRI","Cessão transfere um pool elegível para o patrimônio separado."),
      ("mapa","Investidores",4,"etapa",ACCESS_DATE,"CVM_OFERTAS_RCVM160_20260822","Séries públicas e privadas distribuem risco por camada."),
      ("pergunta","P1 — descasamento de prazo","05_Prazos_WAM","aba",ACCESS_DATE,"METH_COMPARACAO_FIDC_CRI","Prazo médio observado do recebível e prazo legal dos FIDCs estão n/d; os CRIs têm 119,4–144,0 meses. Suplementos dos FIDCs são necessários para quantificar rollover."),
      ("pergunta","P2 — seleção do pool","03_Elegibilidade + 11_Matriz_FIDC_CRI","abas",ACCESS_DATE,"METH_MATRIZ_ELEGIBILIDADE","Os CRIs exigem adimplência, WAM de 2.000 dias, prazo e tickets máximos. Seasoning, MoB e safra performada permanecem n/d."),
      ("pergunta","P3 — antes e depois","14_Antes_Depois","aba",ACCESS_DATE,"CVM_FIDC_2023_I_IV_V_X2 | CVM_FIDC_2024_I_IV_V_X2","PDD e atraso mudam ao redor das cessões; sem tape por CCB, o dado agregado não separa seleção do pool e mudança do denominador."),
      ("pergunta","P4 — saque da subordinada","07_Subordinada","aba",ACCESS_DATE,"METH_RECONCILIACAO","Os sete FIDCs permitem saque condicionado. CRIs I e II pagam a subordinada pelo waterfall. Valores e datas de saques observados permanecem n/d."),
      ("pergunta","P5 — pró-rata e sequencial","06_Waterfall + 07_Subordinada","abas",ACCESS_DATE,"METH_WATERFALL_COMPARATIVO","O pró-rata vigora enquanto testes e prazos permitem; evento ou passagem do tempo ativa sequência. A júnior sai apenas quando os testes contratuais passam."),
      ("pergunta","P6 — curva de amortização","13_Cronograma_Pagamentos","aba",ACCESS_DATE,"CVM_CRI_2024_CLASSE | CVM_CRI_2025_CLASSE | CVM_CRI_2026_CLASSE","O realizado vem do Informe Mensal com lacunas de unidade preservadas. Curvas projetadas por série estão n/d porque os cronogramas mensais não foram localizados."),
      ("pergunta","P7 — custo de captação","12_Custo_Captacao","aba",ACCESS_DATE,"B3_CURVA_DI_20260822 | ANBIMA_CURVA_20260822","Taxas contratadas estão documentadas; custo all-in comparável permanece n/d sem curvas datadas, custos completos, hedge e preço de cessão."),
      ("pergunta","P8 — matriz de cessão","11_Matriz_FIDC_CRI + 11b_Cessoes","abas",ACCESS_DATE,"METH_MATRIZ_ELEGIBILIDADE","FIDCs II e IV cederam para CRIs I e II. Os demais estados Pode ceder são inferências de mandato e critérios, sem prova de uma fita concreta."),
    ]
    return [{"tipo":t,"indicador_ou_etapa":i,"valor":v,"unidade":u,"data_base":d,"fonte_id":s,"status":"Documentado" if t=="indicador" else "Inferido","leitura":l,"nota_metodo":"Todos os números desta aba aparecem detalhados nos CSVs analíticos."} for t,i,v,u,d,s,l in metrics]


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,default=Path("/tmp/solfacil_sources_20260822"))
    parser.add_argument("--attachments",type=Path,default=Path("/Users/matheusjprates/Desktop"))
    parser.add_argument("--output",type=Path,default=Path("data/solfacil"))
    args=parser.parse_args()

    fidc=latest_fidc_tables(args.source_root); cri=latest_cri_tables(args.source_root)
    series=build_series(fidc,cri); vehicles=build_vehicles(fidc,cri); eligibility=build_eligibility()
    waterfall,waterfall_visual=build_waterfall(); subordinated=build_subordinated(series,fidc); pdd=build_pdd(fidc,cri)
    concentration=build_concentration(fidc,cri); terms=build_terms(series); events=build_events(); subscribers=build_subscribers(args.source_root,fidc)
    matrix,cessions=build_cessions(); costs=build_costs(series); schedule=build_payment_schedule(args.source_root,series); before_after=build_before_after(args.source_root)
    public_registered=public_registered_volume(args.source_root)
    comparison=build_comparison(); conflicts=build_conflicts(series,public_registered); sources=build_sources(args.source_root,args.attachments); methodology=build_methodology(); glossary=build_glossary(); panel=build_panel(vehicles,series,conflicts,cessions,public_registered)

    # Add aliases used by some composite rows to keep every source token mapped.
    source_ids={r["fonte_id"] for r in sources}
    for alias,base in [("CVM_CRI_2026_CLASSE","CVM_CRI_2026_CLASSE"),("CVM_CRI_2026_GERAL","CVM_CRI_2026_GERAL_ATIVO"),("CVM_FIDC_202607_I_IV","CVM_FIDC_202607_I_IV")]:
        if alias not in source_ids and base in source_ids:
            original=next(r for r in sources if r["fonte_id"]==base).copy(); original["fonte_id"]=alias; sources.append(original)

    outputs={
      "00_painel":panel,"01_veiculos":vehicles,"02_series":series,"03_elegibilidade":eligibility,
      "04_concentracao":concentration,"05_prazos_wam":terms,"06_waterfall":waterfall,"06b_waterfall_visual":waterfall_visual,
      "07_subordinada":subordinated,"08_pdd":pdd,"09_eventos":events,"10_subscritores":subscribers,
      "11_matriz_fidc_cri":matrix,"11b_cessoes":cessions,"12_custo_captacao":costs,"13_cronograma_pagamentos":schedule,
      "14_antes_depois":before_after,"15_fidc_vs_cri":comparison,"16_conflitos":conflicts,"17_fontes":sources,
      "18_metodologia":methodology,"19_glossario":glossary,
    }
    for stem,rows in outputs.items(): write_csv(args.output,stem,rows)
    print(f"Wrote {len(outputs)} CSV files to {args.output}")
    print(f"Rows: vehicles={len(vehicles)}, series={len(series)}, schedule={len(schedule)}, before_after={len(before_after)}, conflicts={len(conflicts)}")
    if len(series)!=59:
        raise SystemExit(f"Integrity error: expected 59 series/class rows (25 FIDC + 34 CRI), got {len(series)}")


if __name__ == "__main__":
    main()
