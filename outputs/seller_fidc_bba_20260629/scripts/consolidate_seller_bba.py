#!/usr/bin/env python3
"""Consolidate Seller FIDC data for the Itaú BBA credit material.

The script filters the pre-existing Toma Conta/regulatory curation for the
specific Seller FIDC CNPJ and adds only the BBA fixed position inputs supplied
by the user. All derived amounts are mechanical calculations from documented
percent schedules or from the fixed BBA risk input.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


ROOT = Path("/Users/matheusjprates/fidc")
OUT = ROOT / "outputs/seller_fidc_bba_20260629/data"
CNPJ = "50.473.039/0001-02"
CNPJ_DIGITS = "50473039000102"
IME = ROOT / ".cache/fundonet-ime/c0ce8a5069fe47b6253df9ee86a9b53b58dc2ecca778de89072d8bbab0807695"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: Iterable[dict], fields: list[str]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def brl_to_float(value: str) -> float | None:
    if not value or "Não" in value:
        return None
    cleaned = (
        value.replace("R$", "")
        .replace("Até", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if not cleaned:
        return None
    return float(cleaned)


def qty_to_float(value: str) -> float | None:
    if not value or "Não" in value:
        return None
    cleaned = value.replace(".", "").replace(",", ".")
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if not cleaned:
        return None
    return float(cleaned)


def parse_date(value: str) -> str:
    if not value or "Não" in value:
        return ""
    match = re.search(r"\d{2}/\d{2}/\d{4}", value)
    return match.group(0) if match else value


def date_key(value: str) -> datetime:
    return datetime.strptime(value, "%d/%m/%Y")


def dec(value: float | str) -> Decimal:
    return Decimal(str(value))


def q2(value: Decimal | float) -> float:
    return float(dec(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def br_money(value: float | None) -> str:
    if value is None:
        return "não disponível na documentação"
    text = f"{value:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def apply_remaining_schedule(total_mm: float, schedule: list[tuple[str, float]]) -> list[dict[str, float | str]]:
    remaining = dec(total_mm)
    out: list[dict[str, float | str]] = []
    for index, (dt, pct) in enumerate(schedule):
        if index == len(schedule) - 1:
            amount = remaining
        else:
            amount = remaining * dec(pct) / dec(100)
        after = remaining - amount
        out.append(
            {
                "data": dt,
                "percentual_documental": pct,
                "amortizacao_mm": q2(amount),
                "saldo_apos_mm": q2(after),
            }
        )
        remaining = after
    return out


def series_short(name: str) -> str:
    replacements = {
        "Sênior 1ª série": "S1",
        "Sênior 2ª série": "S2",
        "Sênior 3ª série": "S3",
        "Sênior 4ª série": "S4",
        "Sênior 5ª série": "S5",
        "Subordinada Júnior (emissão 2023)": "Sub Jr 2023",
    }
    return replacements.get(name, name)


def source_category(row: dict[str, str]) -> str:
    if row.get("arquivo_local_existe") == "True":
        return "PDF local"
    if row.get("categoria") == "outro":
        return "Inventário sem PDF local"
    return "Curadoria"


def normalize_emissions() -> list[dict]:
    rows = [
        r
        for r in read_csv(ROOT / "reports/seller_cotas_emissoes_pagamentos.csv")
        if r.get("CNPJ") == CNPJ and r.get("Fundo") == "SELLER"
    ]
    out = []
    for r in rows:
        volume = brl_to_float(r["Volume"])
        qty = qty_to_float(r["Quantidade"])
        pu = brl_to_float(r["VNU"])
        out.append(
            {
                "fundo": r["Fundo"],
                "cnpj": r["CNPJ"],
                "classe_serie": r["Cota/Classe"],
                "serie_curta": series_short(r["Cota/Classe"]),
                "tipo": r["Tipo"],
                "data_deliberacao": r["Data deliberação"],
                "data_emissao_integralizacao": parse_date(r["Data emissão / 1ª integralização"]),
                "data_encerramento_oferta": r["Data encerramento/oferta"],
                "quantidade_cotas": qty,
                "volume_brl": volume,
                "volume_mm": None if volume is None else round(volume / 1_000_000, 2),
                "pu_emissao_brl": pu,
                "remuneracao": r["Remuneração"],
                "juros_remuneracao": r["Juros/remuneração"],
                "amortizacao_principal": r["Amortização principal"],
                "status_evidencia": r["Status/evidência"],
                "fonte": r["Fonte"],
                "tipo_dado": "Curadoria Toma Conta/regulatory_profiles",
            }
        )
    return out


def build_amortization_schedule(emissions: list[dict]) -> list[dict]:
    schedules = {
        "Sênior 1ª série": [
            ("15/12/2025", 25.00),
            ("15/01/2026", 33.33),
            ("15/02/2026", 50.00),
            ("15/03/2026", 100.00),
        ],
        "Sênior 2ª série": [
            ("15/04/2026", 50.00),
            ("15/05/2026", 100.00),
        ],
        "Sênior 5ª série": [
            ("15/12/2027", 16.67),
            ("15/01/2028", 20.00),
            ("15/02/2028", 25.00),
            ("15/03/2028", 33.33),
            ("15/04/2028", 50.00),
            ("15/05/2028", 100.00),
        ],
    }
    rows = []
    for e in emissions:
        serie = e["classe_serie"]
        volume_mm = e["volume_mm"]
        if serie in schedules and volume_mm is not None:
            for idx, item in enumerate(apply_remaining_schedule(volume_mm, schedules[serie]), start=1):
                rows.append(
                    {
                        "classe_serie": serie,
                        "serie_curta": e["serie_curta"],
                        "tipo": e["tipo"],
                        "data": item["data"],
                        "ordem_parcela": idx,
                        "amortizacao_programada": "Sim",
                        "definicao_parcela": "Percentual do saldo de principal remanescente",
                        "percentual_documental": item["percentual_documental"],
                        "amortizacao_principal_mm_calculada": item["amortizacao_mm"],
                        "saldo_apos_mm_calculado": item["saldo_apos_mm"],
                        "fonte": e["fonte"],
                        "observacao": "Valor em R$ calculado mecanicamente sobre o volume de emissão; documento traz percentual, não valor nominal fixo.",
                    }
                )
        else:
            rows.append(
                {
                    "classe_serie": serie,
                    "serie_curta": e["serie_curta"],
                    "tipo": e["tipo"],
                    "data": "não disponível na documentação",
                    "ordem_parcela": "",
                    "amortizacao_programada": "Não identificada" if "Sênior" in serie else "Condicionada/residual",
                    "definicao_parcela": "não disponível na documentação" if "Sênior" in serie else "Residual / evento extraordinário",
                    "percentual_documental": "",
                    "amortizacao_principal_mm_calculada": "",
                    "saldo_apos_mm_calculado": "",
                    "fonte": e["fonte"],
                    "observacao": e["status_evidencia"],
                }
            )
    return rows


def build_bba_reconciliation() -> list[dict]:
    return [
        {
            "data_encarteiramento": "23/11/2023",
            "montante_principal_mm": 150.5,
            "risco_accruado_mm": 150.5,
            "vencimento_insumo_bba": "15/09/2026",
            "emissao_reconciliada": "Sênior 3ª série",
            "emissao_total_mm": 200.0,
            "participacao_bba_sobre_emissao": 150.5 / 200.0,
            "natureza": "Participação em emissão tradicional de mercado; não customizada/exclusiva",
            "base_reconciliacao": "Casa data de deliberação/oferta de 23/11/2023 e volume da 3ª série; vencimento de 15/09/2026 vem do insumo BBA, pois o suplemento específico não está nos PDFs locais.",
            "fonte": "558803 pp.4-5; 559856 pp.1-2; insumo fixo Itaú BBA",
            "status": "Parcialmente confirmado",
            "diligencia": "Suplemento/calendário da 3ª série não disponível na documentação local para confirmar o vencimento quebrado.",
        },
        {
            "data_encarteiramento": "26/05/2025",
            "montante_principal_mm": 750.0,
            "risco_accruado_mm": 762.0,
            "vencimento_insumo_bba": "26/05/2028",
            "emissao_reconciliada": "Sênior 5ª série",
            "emissao_total_mm": 1500.0,
            "participacao_bba_sobre_emissao": 750.0 / 1500.0,
            "natureza": "Participação em emissão tradicional de mercado; não customizada/exclusiva",
            "base_reconciliacao": "Casa 3ª emissão/5ª série aprovada em 19/05/2025 e instrumento de emissão de 26/05/2025; oferta encerrada em 04/06/2025 com 2 instituições financeiras.",
            "fonte": "909546 p.9; 912093 pp.3-5; 912172 p.2; 932137 p.2; insumo fixo Itaú BBA",
            "status": "Confirmado com divergência de vencimento",
            "diligencia": "Insumo BBA indica 26/05/2028, mas o documento 912093 pp.3-5 traz amortização final em 15/05/2028.",
        },
    ]


def build_bba_waterfall() -> list[dict]:
    total = dec(150.5) + dec(762.0)
    rows = []
    remaining = total
    events: list[dict] = [
        {
            "data": "15/09/2026",
            "serie": "Sênior 3ª série",
            "tranche": "Itaú BBA 23/11/2023",
            "percentual_documental": "",
            "amortizacao_mm": dec(150.5),
            "base": "Risco accruado do insumo BBA; vencimento não confirmado nos PDFs locais",
            "fonte": "558803 pp.4-5; 559856 pp.1-2; insumo fixo Itaú BBA",
            "diligencia": "Suplemento da série não disponível localmente.",
        }
    ]
    s5_remaining = dec(762.0)
    s5_schedule = [
        ("15/12/2027", 16.67),
        ("15/01/2028", 20.00),
        ("15/02/2028", 25.00),
        ("15/03/2028", 33.33),
        ("15/04/2028", 50.00),
        ("15/05/2028", 100.00),
    ]
    for index, (dt, pct) in enumerate(s5_schedule):
        if index == len(s5_schedule) - 1:
            amount = s5_remaining
        else:
            amount = s5_remaining * dec(pct) / dec(100)
        s5_remaining -= amount
        events.append(
            {
                "data": dt,
                "serie": "Sênior 5ª série",
                "tranche": "Itaú BBA 26/05/2025",
                "percentual_documental": pct,
                "amortizacao_mm": amount,
                "base": "Risco accruado R$ 762,0 mm cascateado pelos percentuais documentais de amortização",
                "fonte": "912093 pp.3-5; insumo fixo Itaú BBA",
                "diligencia": "Data final documental 15/05/2028 diverge do vencimento BBA 26/05/2028.",
            }
        )
    for e in sorted(events, key=lambda r: date_key(r["data"])):
        before = remaining
        amount = e["amortizacao_mm"]
        remaining -= amount
        rows.append(
            {
                "data": e["data"],
                "tranche": e["tranche"],
                "classe_serie": e["serie"],
                "risco_accruado_inicial_mm": 150.5 if "23/11/2023" in e["tranche"] else 762.0,
                "percentual_documental": e["percentual_documental"],
                "amortizacao_vencimento_mm": q2(amount),
                "saldo_bba_antes_mm": q2(before),
                "saldo_bba_apos_mm": q2(remaining),
                "cor_serie": "#EC7000",
                "base": e["base"],
                "fonte": e["fonte"],
                "diligencia": e["diligencia"],
            }
        )
    return rows


def build_document_inventory() -> list[dict]:
    inv = [
        r
        for r in read_csv(ROOT / "reports/sellers_mercado_credito_document_inventory.csv")
        if r.get("cnpj_digits") == CNPJ_DIGITS
    ]
    for r in inv:
        r["fonte_cobertura"] = source_category(r)
    return inv


def build_ime_series_vnu() -> list[dict]:
    rows = read_csv(IME / "estruturas_lista.csv")
    grouped: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    meta: dict[tuple[str, str], dict[str, str]] = {}
    for r in rows:
        if r["sub_bloco"] != "DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR":
            continue
        key = (r["competencia"], r["list_index"])
        if r["tag"] in {"SERIE", "QT_COTAS", "VL_COTAS"}:
            grouped[key][r["tag"]] = r["valor_excel"] or r["valor_raw"]
        meta[key] = {
            "documento_id": r["documento_id"],
            "competencia": r["competencia"],
            "list_index": r["list_index"],
            "fonte": f"IME {r['documento_id']} competência {r['competencia']}",
        }
    out = []
    for key, vals in sorted(grouped.items(), key=lambda kv: (datetime.strptime(kv[0][0], "%m/%Y"), int(kv[0][1]))):
        comp, idx = key
        qt = float(vals.get("QT_COTAS", "0") or 0)
        vnu = float(vals.get("VL_COTAS", "0") or 0)
        out.append(
            {
                "competencia": comp,
                "data_competencia": datetime.strptime(comp, "%m/%Y").strftime("01/%m/%Y"),
                "serie_reportada": vals.get("SERIE", f"Série {idx}"),
                "indice_lista": int(idx),
                "quantidade_cotas": qt,
                "vnu_brl": vnu,
                "saldo_reportado_mm": round(qt * vnu / 1_000_000, 2),
                "documento_id": meta[key]["documento_id"],
                "fonte": meta[key]["fonte"],
                "observacao": "A partir de 03/2026 as séries remanescentes aparecem reindexadas no informe; usar com cautela para mapear série econômica.",
            }
        )
    return out


def vnu_lookup(vnu_rows: list[dict]) -> dict[tuple[str, int], dict]:
    return {(r["competencia"], int(r["indice_lista"])): r for r in vnu_rows}


def build_payment_validation(vnu_rows: list[dict]) -> list[dict]:
    lk = vnu_lookup(vnu_rows)

    def vnu(comp: str, idx: int) -> float | None:
        row = lk.get((comp, idx))
        return None if row is None else float(row["vnu_brl"])

    payment_fields = read_csv(IME / "informes_tidy.csv")
    amort_fields = [
        r
        for r in payment_fields
        if "CAPTA_RESGA_AMORTI" in r.get("tag_path", "")
        and (r.get("tag") in {"VL_TOTAL", "VL_COTA", "QT_COTAS", "VL_PAGO"})
    ]
    non_zero = [r for r in amort_fields if abs(float(r.get("valor_num") or 0)) > 0.000001]
    official_field_status = (
        "Campos CAPTA_RESGA_AMORTI com valores diferentes de zero encontrados."
        if non_zero
        else "Campos CAPTA_RESGA_AMORTI do IME vieram zerados para captação/resgate/amortização no período analisado."
    )

    rows: list[dict] = []
    rows.append(
        {
            "evento": "Pagamento semestral de juros/remuneração",
            "data_documental": "31/05/2025",
            "series_afetadas": "Sênior 1ª a 4ª séries",
            "evidencia_documental": "Juros semestrais a cada 6 meses a partir do 6º mês; S5 só inicia em 29/05/2025.",
            "evidencia_curadoria_ime": f"VNU cai de abr/2025 para mai/2025 nas séries 1-4; S5 aparece em mai/2025 como nova série com VNU R$ {br_money(vnu('05/2025', 5))}.",
            "valor_pagamento_brl": "não disponível na documentação",
            "status_validacao": "Consistente por evidência de VNU; valor exato de caixa não disponível",
            "divergencia": official_field_status,
            "fonte": "467929 pp.115-120; 912093 pp.3-5; IME 904794/925522",
        }
    )
    rows.append(
        {
            "evento": "Pagamento semestral de juros/remuneração",
            "data_documental": "30/11/2025",
            "series_afetadas": "Sênior 1ª a 5ª séries",
            "evidencia_documental": "Juros semestrais até a amortização final.",
            "evidencia_curadoria_ime": "VNU das séries seniores reinicia em nov/2025 após acumular até out/2025.",
            "valor_pagamento_brl": "não disponível na documentação",
            "status_validacao": "Consistente por evidência de VNU; valor exato de caixa não disponível",
            "divergencia": official_field_status,
            "fonte": "467929 pp.115-120; 912093 pp.3-5; IME 1014709/1062060",
        }
    )
    amort_events = [
        ("15/12/2025", "Sênior 1ª série", "25,00%", "11/2025", "12/2025", 1),
        ("15/01/2026", "Sênior 1ª série", "33,33%", "12/2025", "01/2026", 1),
        ("15/02/2026", "Sênior 1ª série", "50,00%", "01/2026", "02/2026", 1),
    ]
    for dt, serie, pct, prev, curr, idx in amort_events:
        before, after = vnu(prev, idx), vnu(curr, idx)
        delta = None if before is None or after is None else before - after
        rows.append(
            {
                "evento": "Amortização programada de principal",
                "data_documental": dt,
                "series_afetadas": serie,
                "evidencia_documental": f"Parcela de {pct} do saldo de principal remanescente.",
                "evidencia_curadoria_ime": (
                    "VNU antes/depois: "
                    f"{prev} R$ {br_money(before)}; {curr} R$ {br_money(after)}; queda R$ {br_money(delta)} por cota."
                    if delta is not None
                    else "VNU não disponível."
                ),
                "valor_pagamento_brl": "não disponível na documentação",
                "status_validacao": "Consistente por evidência de VNU; valor exato de caixa não disponível",
                "divergencia": official_field_status,
                "fonte": "467929 pp.115-117; IME competências 11/2025 a 02/2026",
            }
        )
    rows.append(
        {
            "evento": "Amortização final programada de principal",
            "data_documental": "15/03/2026",
            "series_afetadas": "Sênior 1ª série",
            "evidencia_documental": "Parcela final de 100,00% do saldo remanescente.",
            "evidencia_curadoria_ime": "Série 1 econômica deixa de ser identificável diretamente em 03/2026; informe passa a reindexar as séries remanescentes.",
            "valor_pagamento_brl": "não disponível na documentação",
            "status_validacao": "Consistência parcial; requer confirmação por relatório do administrador/boletim de pagamento",
            "divergencia": official_field_status,
            "fonte": "467929 pp.115-117; IME 1162826/1195849 competência 03/2026",
        }
    )
    rows.append(
        {
            "evento": "Amortizações Sênior 5ª série ainda futuras na base analisada",
            "data_documental": "15/12/2027 a 15/05/2028",
            "series_afetadas": "Sênior 5ª série",
            "evidencia_documental": "Cronograma documentado em 912093 pp.3-5.",
            "evidencia_curadoria_ime": "Sem ocorrência até a última competência local analisada (03/2026).",
            "valor_pagamento_brl": "não disponível na documentação",
            "status_validacao": "Não vencido no período analisado",
            "divergencia": "Vencimento BBA 26/05/2028 diverge da amortização final documental 15/05/2028.",
            "fonte": "912093 pp.3-5; IME até 03/2026; insumo fixo Itaú BBA",
        }
    )
    return rows


def comp_key(value: str) -> datetime:
    return datetime.strptime(value, "%m/%Y")


def latest_competencia(vnu_rows: list[dict]) -> str:
    return max((r["competencia"] for r in vnu_rows), key=comp_key)


def current_fund_position(vnu_rows: list[dict]) -> tuple[list[dict], Decimal]:
    latest = latest_competencia(vnu_rows)
    senior_map = {
        1: {
            "classe_serie_economica": "Sênior 2ª série",
            "serie_curta": "S2",
            "vencimento_base": "15/05/2026",
            "fonte_vencimento": "467929 pp.118-120",
            "status_documental": "Confirmado em documentação local",
            "observacao": "Informe 03/2026 reindexa as séries remanescentes; índice 1 corresponde economicamente à antiga S2 após amortização final da S1.",
        },
        2: {
            "classe_serie_economica": "Sênior 3ª série",
            "serie_curta": "S3",
            "vencimento_base": "15/09/2026",
            "fonte_vencimento": "Insumo fixo Itaú BBA; MercadoLibre Form 10-Q 1T26 reporta vencimento em setembro/2026; suplemento local não disponível",
            "status_documental": "Parcialmente confirmado; dia exato vem do insumo BBA",
            "observacao": "Série 3 consta nos documentos locais, mas o suplemento/calendário não está disponível.",
        },
        3: {
            "classe_serie_economica": "Sênior 4ª série",
            "serie_curta": "S4",
            "vencimento_base": "11/2026 (dia não disponível)",
            "fonte_vencimento": "MercadoLibre Form 10-Q 1T26 reporta vencimento em novembro/2026; suplemento local não disponível",
            "status_documental": "Mês corroborado externamente; dia exato não disponível na documentação local",
            "observacao": "Série 4 consta nos documentos locais, mas o suplemento/calendário não está disponível.",
        },
        4: {
            "classe_serie_economica": "Sênior 5ª série",
            "serie_curta": "S5",
            "vencimento_base": "15/05/2028",
            "fonte_vencimento": "912093 pp.3-5",
            "status_documental": "Confirmado em documentação local; diverge do insumo BBA 26/05/2028",
            "observacao": "Cronograma documental de 15/12/2027 a 15/05/2028.",
        },
    }
    positions: list[dict] = []
    for row in sorted((r for r in vnu_rows if r["competencia"] == latest), key=lambda r: int(r["indice_lista"])):
        idx = int(row["indice_lista"])
        meta = senior_map.get(idx)
        if not meta:
            continue
        qt = dec(row["quantidade_cotas"])
        vnu = dec(row["vnu_brl"])
        saldo = qt * vnu
        positions.append(
            {
                "competencia_base": latest,
                "classe_serie_economica": meta["classe_serie_economica"],
                "serie_curta": meta["serie_curta"],
                "classe_reportada_no_ime": row["serie_reportada"],
                "indice_lista_ime": idx,
                "quantidade_cotas": float(qt),
                "vnu_brl": float(vnu),
                "saldo_atual_brl": float(saldo),
                "saldo_atual_mm": q2(saldo / dec(1_000_000)),
                "vencimento_base": meta["vencimento_base"],
                "fonte_vencimento": meta["fonte_vencimento"],
                "status_documental": meta["status_documental"],
                "fonte_posicao": row["fonte"],
                "observacao": meta["observacao"],
            }
        )
    tidy = read_csv(IME / "informes_tidy.csv")
    pl = None
    sub_qt = None
    sub_vnu = None
    for r in tidy:
        if r.get("competencia") != latest:
            continue
        if r.get("tag_path") == "DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ":
            pl = dec(r["valor_num"])
        if r.get("tag_path") == "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/QT_COTAS":
            sub_qt = dec(r["valor_num"])
        if r.get("tag_path") == "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/VL_COTAS":
            sub_vnu = dec(r["valor_num"])
    if pl is None:
        raise RuntimeError("PL atual não encontrado no IME")
    senior_sum = sum((dec(p["saldo_atual_brl"]) for p in positions), Decimal("0"))
    residual_from_pl = pl - senior_sum
    sub_balance = sub_qt * sub_vnu if sub_qt is not None and sub_vnu is not None else residual_from_pl
    positions.append(
        {
            "competencia_base": latest,
            "classe_serie_economica": "Patrimônio líquido residual / Subordinada Júnior",
            "serie_curta": "PL residual",
            "classe_reportada_no_ime": "Subordinada 1",
            "indice_lista_ime": "",
            "quantidade_cotas": "" if sub_qt is None else float(sub_qt),
            "vnu_brl": "" if sub_vnu is None else float(sub_vnu),
            "saldo_atual_brl": float(residual_from_pl),
            "saldo_atual_mm": q2(residual_from_pl / dec(1_000_000)),
            "vencimento_base": "15/05/2028",
            "fonte_vencimento": "Premissa de waterfall: residual de PL pago no vencimento final; PL do IME 1162826 competência 03/2026",
            "status_documental": "Premissa de modelagem; sem projeção de accrual futuro",
            "fonte_posicao": "IME 1162826 competência 03/2026",
            "observacao": f"Saldo residual por PL menos seniores; saldo da subordinada por cota é R$ {br_money(float(sub_balance / dec(1_000_000)))} mm.",
        }
    )
    return positions, pl


def build_full_fund_waterfall(vnu_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    positions, pl = current_fund_position(vnu_rows)
    pos = {p["serie_curta"]: dec(p["saldo_atual_brl"]) / dec(1_000_000) for p in positions}

    event_defs: list[dict] = []

    s2_remaining = pos["S2"]
    for index, (dt, pct) in enumerate([("15/04/2026", 50.0), ("15/05/2026", 100.0)]):
        amount = s2_remaining if index == 1 else s2_remaining * dec(pct) / dec(100)
        s2_remaining -= amount
        event_defs.append(
            {
                "sort_key": "2026-04-15" if index == 0 else "2026-05-15",
                "data_evento": dt,
                "tipo_evento": "Amortização/vencimento de cota sênior",
                "classe_serie": "Sênior 2ª série",
                "serie_curta": "S2",
                "pagamento_senior_mm": amount,
                "pagamento_pl_residual_mm": Decimal("0"),
                "base_calculo": "Saldo atual no IME 03/2026 cascateado pelos percentuais documentais remanescentes.",
                "fonte": "467929 pp.118-120; IME 1162826 competência 03/2026",
                "status_documental": "Confirmado em documentação local",
            }
        )

    event_defs.append(
        {
            "sort_key": "2026-09-15",
            "data_evento": "15/09/2026",
            "tipo_evento": "Vencimento de cota sênior",
            "classe_serie": "Sênior 3ª série",
            "serie_curta": "S3",
            "pagamento_senior_mm": pos["S3"],
            "pagamento_pl_residual_mm": Decimal("0"),
            "base_calculo": "Saldo atual no IME 03/2026; vencimento exato conforme insumo BBA.",
            "fonte": "Insumo fixo Itaú BBA; MercadoLibre Form 10-Q 1T26 reporta Seller FIDC com vencimento setembro/2026; IME 1162826",
            "status_documental": "Parcialmente confirmado; suplemento local não disponível",
        }
    )
    event_defs.append(
        {
            "sort_key": "2026-11-30",
            "data_evento": "11/2026 (dia não disponível)",
            "tipo_evento": "Vencimento de cota sênior",
            "classe_serie": "Sênior 4ª série",
            "serie_curta": "S4",
            "pagamento_senior_mm": pos["S4"],
            "pagamento_pl_residual_mm": Decimal("0"),
            "base_calculo": "Saldo atual no IME 03/2026; mês de vencimento corroborado externamente.",
            "fonte": "MercadoLibre Form 10-Q 1T26 reporta Seller FIDC com vencimento novembro/2026; IME 1162826",
            "status_documental": "Mês corroborado externamente; dia exato não disponível na documentação local",
        }
    )

    s5_remaining = pos["S5"]
    for index, (dt, pct) in enumerate(
        [
            ("15/12/2027", 16.67),
            ("15/01/2028", 20.00),
            ("15/02/2028", 25.00),
            ("15/03/2028", 33.33),
            ("15/04/2028", 50.00),
            ("15/05/2028", 100.00),
        ]
    ):
        amount = s5_remaining if index == 5 else s5_remaining * dec(pct) / dec(100)
        s5_remaining -= amount
        event_defs.append(
            {
                "sort_key": datetime.strptime(dt, "%d/%m/%Y").strftime("%Y-%m-%d"),
                "data_evento": dt,
                "tipo_evento": "Amortização/vencimento de cota sênior",
                "classe_serie": "Sênior 5ª série",
                "serie_curta": "S5",
                "pagamento_senior_mm": amount,
                "pagamento_pl_residual_mm": Decimal("0"),
                "base_calculo": "Saldo atual no IME 03/2026 cascateado pelos percentuais documentais remanescentes.",
                "fonte": "912093 pp.3-5; IME 1162826 competência 03/2026",
                "status_documental": "Confirmado em documentação local; data final 15/05/2028 diverge do insumo BBA 26/05/2028",
            }
        )

    event_defs.append(
        {
            "sort_key": "2028-05-15.2",
            "data_evento": "15/05/2028",
            "tipo_evento": "Pagamento do PL residual",
            "classe_serie": "Patrimônio líquido residual / Subordinada Júnior",
            "serie_curta": "PL residual",
            "pagamento_senior_mm": Decimal("0"),
            "pagamento_pl_residual_mm": pos["PL residual"],
            "base_calculo": "PL atual do IME 03/2026 menos saldos atuais das séries seniores; sem projeção de accrual futuro.",
            "fonte": "IME 1162826 competência 03/2026; premissa solicitada pelo usuário",
            "status_documental": "Premissa de waterfall",
        }
    )

    remaining = pl / dec(1_000_000)
    out: list[dict] = []
    for order, event in enumerate(sorted(event_defs, key=lambda r: r["sort_key"]), start=1):
        senior = event["pagamento_senior_mm"]
        residual = event["pagamento_pl_residual_mm"]
        total_payment = senior + residual
        before = remaining
        remaining -= total_payment
        out.append(
            {
                "ordem": order,
                "data_evento": event["data_evento"],
                "tipo_evento": event["tipo_evento"],
                "classe_serie": event["classe_serie"],
                "serie_curta": event["serie_curta"],
                "pl_base_mm": q2(pl / dec(1_000_000)),
                "pagamento_senior_mm": q2(senior),
                "pagamento_pl_residual_mm": q2(residual),
                "pagamento_total_mm": q2(total_payment),
                "saldo_antes_mm": q2(before),
                "saldo_apos_mm": q2(remaining),
                "base_calculo": event["base_calculo"],
                "fonte": event["fonte"],
                "status_documental": event["status_documental"],
            }
        )
    return positions, out


def build_sources() -> list[dict]:
    return [
        {
            "id": "467929",
            "documento": "Regulamento 05/05/2023",
            "tipo": "regulamento",
            "arquivo_local": "data/raw/50473039000102/467929_regulamento_regulamento_467929_2023-05-05.pdf",
            "uso": "Suplementos e cronogramas Sênior 1ª e 2ª séries, pp.115-120.",
        },
        {
            "id": "468755",
            "documento": "AGE 22/05/2023",
            "tipo": "assembleia",
            "arquivo_local": "data/raw/50473039000102/468755_assembleia_assembleia_468755_2023-05-22.pdf",
            "uso": "Aprovação das primeiras séries.",
        },
        {
            "id": "471622",
            "documento": "Aviso ao Mercado 30/05/2023",
            "tipo": "emissao",
            "arquivo_local": "data/raw/50473039000102/471622_emissao_emissao_471622_2023-05-30.pdf",
            "uso": "Liquidação 31/05/2023 e cronograma da oferta.",
        },
        {
            "id": "558803",
            "documento": "AGE 23/11/2023",
            "tipo": "assembleia",
            "arquivo_local": "data/raw/50473039000102/558803_assembleia_assembleia_558803_2023-11-23.pdf",
            "uso": "Aprovação da 3ª/4ª séries e subordinada júnior.",
        },
        {
            "id": "559856",
            "documento": "Anúncio de Início 27/11/2023",
            "tipo": "emissao",
            "arquivo_local": "data/raw/50473039000102/559856_emissao_emissao_559856_2023-11-27.pdf",
            "uso": "Oferta tradicional de mercado de R$300 mm (3ª e 4ª séries).",
        },
        {
            "id": "909546",
            "documento": "AGO/E 19/05/2025",
            "tipo": "assembleia",
            "arquivo_local": "data/raw/50473039000102/909546_assembleia_assembleia_909546_2025-05-19.pdf",
            "uso": "Aprovação da emissão de 2025.",
        },
        {
            "id": "912093",
            "documento": "Instrumento Particular de Emissão de Cotas 26/05/2025",
            "tipo": "emissao",
            "arquivo_local": "data/raw/50473039000102/912093_assembleia_assembleia_912093_2025-05-26.pdf",
            "uso": "Sênior 5ª série: R$1,5 bi, DI+0,85%, cronograma até 15/05/2028.",
        },
        {
            "id": "912172",
            "documento": "Anúncio de Início 28/05/2025",
            "tipo": "emissao",
            "arquivo_local": "data/raw/50473039000102/912172_emissao_emissao_912172_2025-05-28.pdf",
            "uso": "Primeira integralização em 29/05/2025.",
        },
        {
            "id": "932137",
            "documento": "Anúncio de Encerramento 04/06/2025",
            "tipo": "emissao",
            "arquivo_local": "data/raw/50473039000102/932137_emissao_emissao_932137_2025-06-04.pdf",
            "uso": "Oferta integralmente subscrita por 2 instituições financeiras.",
        },
        {
            "id": "IME",
            "documento": "Informes Mensais Estruturados 02/2025-03/2026",
            "tipo": "relatorios_administrador",
            "arquivo_local": ".cache/fundonet-ime/c0ce8a5069fe47b6253df9ee86a9b53b58dc2ecca778de89072d8bbab0807695/",
            "uso": "VNU, quantidade de cotas e evidência de pagamentos/amortizações.",
        },
        {
            "id": "MELI-10Q-1T26",
            "documento": "MercadoLibre Form 10-Q, 1T26, nota de securitization transactions",
            "tipo": "fonte externa",
            "arquivo_local": "https://investor.mercadolibre.com/open-file?file=aHR0cHM6Ly9odHRwMi5tbHN0YXRpYy5jb20vc3RvcmFnZS9tbC1jbXMtYmFja2VuZC9jbXMtZG9jdW1lbnRzLXByb2Qvc2VjLzAwMDEwOTk1OTAvMDAwMTA5OTU5MC0yNi0wMDAwMTcvZm9ybTEwLVEtMDAwMTA5OTU5MC0yNi0wMDAwMTcucGRm",
            "uso": "Corroboração externa dos meses de vencimento das séries 3 e 4: setembro/2026 e novembro/2026.",
        },
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    document_inventory = build_document_inventory()
    coverage = [
        r
        for r in read_csv(ROOT / "reports/sellers_mercado_credito_document_coverage.csv")
        if r.get("cnpj") == CNPJ
    ]
    emissions = normalize_emissions()
    amort = build_amortization_schedule(emissions)
    bba_rec = build_bba_reconciliation()
    waterfall = build_bba_waterfall()
    vnu_rows = build_ime_series_vnu()
    fund_current_position, fund_waterfall = build_full_fund_waterfall(vnu_rows)
    payment_validation = build_payment_validation(vnu_rows)
    sources = build_sources()

    write_csv(
        OUT / "document_inventory.csv",
        document_inventory,
        [
            "grupo",
            "fundo",
            "nome_curto",
            "cnpj",
            "cnpj_digits",
            "data_referencia",
            "categoria",
            "tipo_documento",
            "especie",
            "documento_id",
            "source_file",
            "arquivo_local_existe",
            "page_count",
            "fonte_cobertura",
        ],
    )
    write_csv(
        OUT / "document_coverage.csv",
        coverage,
        [
            "grupo",
            "cnpj",
            "fundo",
            "documentos_inventariados",
            "pdfs_locais_analisaveis",
            "documentos_sem_pdf_local",
            "paginas_pdf_locais",
            "quebra_por_categoria",
        ],
    )
    write_csv(
        OUT / "emissions_clean.csv",
        emissions,
        [
            "fundo",
            "cnpj",
            "classe_serie",
            "serie_curta",
            "tipo",
            "data_deliberacao",
            "data_emissao_integralizacao",
            "data_encerramento_oferta",
            "quantidade_cotas",
            "volume_brl",
            "volume_mm",
            "pu_emissao_brl",
            "remuneracao",
            "juros_remuneracao",
            "amortizacao_principal",
            "status_evidencia",
            "fonte",
            "tipo_dado",
        ],
    )
    write_csv(
        OUT / "amortization_schedule.csv",
        amort,
        [
            "classe_serie",
            "serie_curta",
            "tipo",
            "data",
            "ordem_parcela",
            "amortizacao_programada",
            "definicao_parcela",
            "percentual_documental",
            "amortizacao_principal_mm_calculada",
            "saldo_apos_mm_calculado",
            "fonte",
            "observacao",
        ],
    )
    write_csv(
        OUT / "bba_reconciliation.csv",
        bba_rec,
        [
            "data_encarteiramento",
            "montante_principal_mm",
            "risco_accruado_mm",
            "vencimento_insumo_bba",
            "emissao_reconciliada",
            "emissao_total_mm",
            "participacao_bba_sobre_emissao",
            "natureza",
            "base_reconciliacao",
            "fonte",
            "status",
            "diligencia",
        ],
    )
    write_csv(
        OUT / "bba_waterfall.csv",
        waterfall,
        [
            "data",
            "tranche",
            "classe_serie",
            "risco_accruado_inicial_mm",
            "percentual_documental",
            "amortizacao_vencimento_mm",
            "saldo_bba_antes_mm",
            "saldo_bba_apos_mm",
            "cor_serie",
            "base",
            "fonte",
            "diligencia",
        ],
    )
    write_csv(
        OUT / "fund_current_position.csv",
        fund_current_position,
        [
            "competencia_base",
            "classe_serie_economica",
            "serie_curta",
            "classe_reportada_no_ime",
            "indice_lista_ime",
            "quantidade_cotas",
            "vnu_brl",
            "saldo_atual_brl",
            "saldo_atual_mm",
            "vencimento_base",
            "fonte_vencimento",
            "status_documental",
            "fonte_posicao",
            "observacao",
        ],
    )
    write_csv(
        OUT / "fund_full_waterfall.csv",
        fund_waterfall,
        [
            "ordem",
            "data_evento",
            "tipo_evento",
            "classe_serie",
            "serie_curta",
            "pl_base_mm",
            "pagamento_senior_mm",
            "pagamento_pl_residual_mm",
            "pagamento_total_mm",
            "saldo_antes_mm",
            "saldo_apos_mm",
            "base_calculo",
            "fonte",
            "status_documental",
        ],
    )
    write_csv(
        OUT / "ime_series_vnu.csv",
        vnu_rows,
        [
            "competencia",
            "data_competencia",
            "serie_reportada",
            "indice_lista",
            "quantidade_cotas",
            "vnu_brl",
            "saldo_reportado_mm",
            "documento_id",
            "fonte",
            "observacao",
        ],
    )
    write_csv(
        OUT / "payment_validation.csv",
        payment_validation,
        [
            "evento",
            "data_documental",
            "series_afetadas",
            "evidencia_documental",
            "evidencia_curadoria_ime",
            "valor_pagamento_brl",
            "status_validacao",
            "divergencia",
            "fonte",
        ],
    )
    write_csv(
        OUT / "sources.csv",
        sources,
        ["id", "documento", "tipo", "arquivo_local", "uso"],
    )
    with (OUT / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "fund_name": "SELLER FIDC SEGMENTO MEIOS DE PAGAMENTO DE RESPONSABILIDADE LIMITADA",
                "cnpj": CNPJ,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "document_inventory_rows": len(document_inventory),
                "coverage": coverage[0] if coverage else {},
                "emissions_rows": len(emissions),
                "amortization_rows": len(amort),
                "waterfall_rows": len(waterfall),
                "fund_full_waterfall_rows": len(fund_waterfall),
                "payment_validation_rows": len(payment_validation),
                "key_flags": [
                    "S3/S4 2023: suplemento/calendário não disponível nos PDFs locais; vencimento Itaú BBA de 15/09/2026 não foi confirmado no documento local.",
                    "S5 2025: insumo Itaú BBA indica vencimento 26/05/2028, mas 912093 pp.3-5 documenta amortização final em 15/05/2028.",
                    "Campos oficiais CAPTA_RESGA_AMORTI dos informes mensais vêm zerados; validação de pagamentos usa evidência de VNU e cronograma, com valor exato de caixa marcado como não disponível.",
                    "Waterfall do fundo inteiro usa PL e saldos por cota do IME 03/2026; residual de PL é pago no vencimento final por premissa de modelagem, sem projeção de accrual futuro.",
                ],
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
