#!/usr/bin/env python3
"""Quantitative closing report for the ``Outros`` documentary curation.

Reports, for the four reference competences, how much of the FIDC market the
analytical ledger already covers, how much net asset value left the ``Outros``
bucket and which decisions still deserve a human look.  Nothing is written to
the ledger here; the script only reads and reconciles.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_outros_reclassification import NAMED_DISPLAY_TYPES  # noqa: E402
from services.industry_taxonomy_review import (  # noqa: E402
    apply_taxonomy_review_overlay,
    load_taxonomy_review_actions,
    normalize_cnpj,
)


DEFAULT_PERIODS = ("2023-12", "2024-12", "2025-12", "2026-06")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--periods", default=",".join(DEFAULT_PERIODS))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _display_type(value: str) -> str:
    return value if value in NAMED_DISPLAY_TYPES else "Outros"


def load_base(data_dir: Path, periods: tuple[str, ...]) -> pd.DataFrame:
    base = pd.read_csv(
        data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz",
        dtype=str,
        keep_default_na=False,
    )
    base["cnpj_fundo"] = base["cnpj_fundo"].map(normalize_cnpj)
    base["pl"] = pd.to_numeric(base["pl"], errors="coerce").fillna(0.0)
    base = base[base["competencia"].isin(periods)]
    return base[
        ~base["is_fic_fidc"].str.strip().str.casefold().isin({"true", "1"})
    ].copy()


def build_report(data_dir: Path, periods: tuple[str, ...]) -> dict[str, object]:
    base = load_base(data_dir, periods)
    actions = load_taxonomy_review_actions(data_dir / "taxonomy_review_actions.csv")
    overlay = apply_taxonomy_review_overlay(base, actions)
    overlay["tipo_oficial_exibido"] = overlay["anbima_tipo_oficial"].map(_display_type)
    overlay["tipo_curado_exibido"] = overlay["anbima_tipo_curado"].map(_display_type)

    per_period: list[dict[str, object]] = []
    for period in periods:
        frame = overlay[overlay["competencia"].eq(period)]
        total = float(frame["pl"].sum())
        official_outros = float(
            frame.loc[frame["tipo_oficial_exibido"].eq("Outros"), "pl"].sum()
        )
        curated_outros = float(
            frame.loc[frame["tipo_curado_exibido"].eq("Outros"), "pl"].sum()
        )
        covered = float(frame.loc[frame["taxonomy_review_applied"], "pl"].sum())
        per_period.append(
            {
                "competencia": period,
                "fundos": int(len(frame)),
                "pl_total": total,
                "outros_oficial": official_outros,
                "outros_curado": curated_outros,
                "reducao_outros": official_outros - curated_outros,
                "pl_com_decisao_aplicada": covered,
                "cobertura_pl_pct": 100.0 * covered / total if total else 0.0,
                "outros_pct_oficial": 100.0 * official_outros / total if total else 0.0,
                "outros_pct_curado": 100.0 * curated_outros / total if total else 0.0,
            }
        )

    ledger_counts = actions["status"].value_counts().to_dict()
    conclusions_path = data_dir / "industry_outros_reclassification_conclusions.csv"
    conclusion_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    if conclusions_path.exists():
        conclusions = pd.read_csv(conclusions_path, dtype=str, keep_default_na=False)
        conclusion_counts = conclusions["decision_status"].value_counts().to_dict()
        confidence_counts = (
            conclusions.loc[
                conclusions["decision_status"].eq("aprovado"), "confianca_documental"
            ]
            .value_counts()
            .to_dict()
        )

    queue_path = data_dir / "industry_outros_reclassification_queue.csv"
    queue_size = 0
    queue_remaining = 0
    if queue_path.exists():
        queue = pd.read_csv(queue_path, dtype=str, keep_default_na=False)
        queue["cnpj_fundo"] = queue["cnpj_fundo"].map(normalize_cnpj)
        decided = set(actions["cnpj_fundo"].map(normalize_cnpj))
        queue_size = int(len(queue))
        queue_remaining = int((~queue["cnpj_fundo"].isin(decided)).sum())

    return {
        "periods": list(periods),
        "por_competencia": per_period,
        "ledger_status": {str(k): int(v) for k, v in ledger_counts.items()},
        "conclusoes_outros": {str(k): int(v) for k, v in conclusion_counts.items()},
        "confianca_aprovados": {str(k): int(v) for k, v in confidence_counts.items()},
        "fila_outros_total": queue_size,
        "fila_outros_remanescente": queue_remaining,
    }


def _fund_family_key(name: str) -> str:
    """Group sibling vehicles of the same programme (``JC 4870`` and ``JC 4870 IV``)."""

    words = [word for word in str(name).upper().split() if word]
    stop = {
        "FUNDO",
        "FUNDOS",
        "DE",
        "DO",
        "DA",
        "DOS",
        "DAS",
        "EM",
        "E",
        "INVESTIMENTO",
        "INVESTIMENTOS",
        "DIREITOS",
        "CREDITORIOS",
        "CREDITÓRIOS",
        "FIDC",
        "FIDC-NP",
        "NP",
        "NAO",
        "NÃO",
        "PADRONIZADOS",
        "PADRONIZADO",
        "RESPONSABILIDADE",
        "LIMITADA",
        "ILIMITADA",
        "COTAS",
        "MULTIMERCADO",
        "CLASSE",
        "UNICA",
        "ÚNICA",
    }
    meaningful = [word for word in words if word not in stop]
    return " ".join(meaningful[:2])


def build_consistency_review(
    data_dir: Path, base: pd.DataFrame
) -> pd.DataFrame:
    """Flag decisions that a human should look at before the next bundle."""

    path = data_dir / "industry_outros_reclassification_conclusions.csv"
    if not path.exists():
        return pd.DataFrame()
    conclusions = pd.read_csv(path, dtype=str, keep_default_na=False)
    conclusions["cnpj_fundo"] = conclusions["cnpj_fundo"].map(normalize_cnpj)
    conclusions["pl_max"] = pd.to_numeric(conclusions["pl_max"], errors="coerce").fillna(
        0.0
    )
    managers = (
        base.sort_values("competencia")
        .drop_duplicates("cnpj_fundo", keep="last")
        .set_index("cnpj_fundo")["gestor_nome"]
    )
    conclusions["gestor_nome"] = conclusions["cnpj_fundo"].map(managers).fillna("")
    conclusions["familia"] = conclusions["nome_fidc"].map(_fund_family_key)

    approved = conclusions[conclusions["decision_status"].eq("aprovado")].copy()
    rows: list[dict[str, object]] = []

    grouped = approved[approved["familia"].str.len().ge(4)].groupby("familia")
    for familia, frame in grouped:
        if len(frame) < 2:
            continue
        types = set(frame["tipo_anbima_sugerido"])
        if len(types) > 1:
            rows.append(
                {
                    "motivo": "familia_de_fundos_com_tipos_divergentes",
                    "chave": familia,
                    "cnpjs": "; ".join(frame["cnpj_fundo"]),
                    "detalhe": " vs ".join(sorted(types)),
                    "pl_envolvido": float(frame["pl_max"].sum()),
                }
            )

    manager_groups = approved[approved["gestor_nome"].str.len().ge(4)].groupby(
        ["gestor_nome", "foco_anbima_oficial"]
    )
    for (gestor, foco_oficial), frame in manager_groups:
        if len(frame) < 3 or not foco_oficial:
            continue
        focus = frame["foco_anbima_sugerido"].value_counts()
        if len(focus) < 2:
            continue
        minority = focus[focus.eq(focus.min())]
        if focus.max() >= 3 * focus.min() and focus.min() == 1:
            outliers = frame[frame["foco_anbima_sugerido"].isin(minority.index)]
            rows.append(
                {
                    "motivo": "foco_minoritario_no_mesmo_gestor_e_foco_oficial",
                    "chave": f"{gestor} | {foco_oficial}",
                    "cnpjs": "; ".join(outliers["cnpj_fundo"]),
                    "detalhe": (
                        f"{focus.idxmax()} em {focus.max()} fundos contra "
                        + ", ".join(f"{name} em {count}" for name, count in minority.items())
                    ),
                    "pl_envolvido": float(outliers["pl_max"].sum()),
                }
            )

    moved = approved[
        approved["tipo_anbima_oficial"].isin(NAMED_DISPLAY_TYPES)
        & approved["tipo_anbima_sugerido"].ne(approved["tipo_anbima_oficial"])
        & approved["confianca_documental"].eq("media")
    ]
    for row in moved.sort_values("pl_max", ascending=False).head(25).to_dict(
        orient="records"
    ):
        rows.append(
            {
                "motivo": "mudanca_de_tipo_oficial_com_confianca_media",
                "chave": row["nome_fidc"],
                "cnpjs": row["cnpj_fundo"],
                "detalhe": (
                    f"{row['tipo_anbima_oficial']} -> {row['tipo_anbima_sugerido']} "
                    f"({row['family_scores']})"
                ),
                "pl_envolvido": float(row["pl_max"]),
            }
        )

    review = pd.DataFrame(rows)
    if review.empty:
        return review
    return review.sort_values("pl_envolvido", ascending=False).reset_index(drop=True)


def format_report(report: dict[str, object]) -> str:
    lines = ["| Competência | Fundos | PL total | Outros oficial | Outros curado | Redução | Cobertura PL |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in report["por_competencia"]:  # type: ignore[index]
        lines.append(
            "| {competencia} | {fundos} | R$ {pl_total:,.1f} bi | "
            "R$ {outros_oficial:,.1f} bi ({outros_pct_oficial:.1f}%) | "
            "R$ {outros_curado:,.1f} bi ({outros_pct_curado:.1f}%) | "
            "R$ {reducao_outros:,.1f} bi | {cobertura_pl_pct:.1f}% |".format(
                competencia=row["competencia"],
                fundos=row["fundos"],
                pl_total=row["pl_total"] / 1e9,
                outros_oficial=row["outros_oficial"] / 1e9,
                outros_pct_oficial=row["outros_pct_oficial"],
                outros_curado=row["outros_curado"] / 1e9,
                outros_pct_curado=row["outros_pct_curado"],
                reducao_outros=row["reducao_outros"] / 1e9,
                cobertura_pl_pct=row["cobertura_pl_pct"],
            )
        )
    lines.append("")
    lines.append(f"Ledger: {report['ledger_status']}")
    lines.append(f"Conclusões da expansão Outros: {report['conclusoes_outros']}")
    lines.append(f"Confiança das aprovações: {report['confianca_aprovados']}")
    lines.append(
        f"Fila Outros: {report['fila_outros_remanescente']} CNPJs sem decisão "
        f"de {report['fila_outros_total']}"
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    periods = tuple(part.strip() for part in args.periods.split(",") if part.strip())
    report = build_report(args.data_dir, periods)
    review = build_consistency_review(args.data_dir, load_base(args.data_dir, periods))
    if not review.empty:
        review_path = args.data_dir / "industry_outros_consistency_review.csv"
        review.to_csv(review_path, index=False)
        report["revisao_humana_sugerida"] = int(len(review))
    print(format_report(report))
    if not review.empty:
        print()
        print(f"Casos para revisão humana: {len(review)}")
        print(review.head(15).to_string(index=False))
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
