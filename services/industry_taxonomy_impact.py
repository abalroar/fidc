"""Reconcile the June/2026 audited taxonomy against published FIDC views.

The audit workbook and the current revision bundle do not share the same
perimeter.  This module therefore emits separate, explicitly denominated
views instead of forcing one bridge:

* gross effect of the 37 audited decisions on the workbook's June/2026 mix;
* incremental effect of replacing the ``origin/main`` ledger with the current
  ledger while holding the current fund universe fixed;
* period-by-period movement in the materialized issuance taxonomy;
* denominator movement in the market-share subtypes, calculated twice from
  the same current fund base and differing only by ledger.

Official ANBIMA fields remain the starting point in both incremental photos.
Missing classifications follow the existing four-Type display rule and land
in ``Outros``.  No balance is inferred and no perimeter difference is plugged.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
from io import StringIO
from typing import Any

import pandas as pd

from services.industry_anbima import ANBIMA_TYPES
from services.industry_taxonomy_review import (
    TAXONOMY_REVIEW_COLUMNS,
    apply_taxonomy_review_overlay,
    build_curated_type_mix,
    normalize_cnpj,
)
from services.industry_revision_analysis import build_market_share_by_subtype


REFERENCE_COMPETENCE = "2026-06"
SOURCE_MIX_SHEET = "Mix ANBIMA"
TYPE_MIGRATION_LABEL = "Migra de Tipo"
FOCUS_ONLY_LABEL = "Só Foco"
DISPLAY_TYPES = tuple(ANBIMA_TYPES)
SOURCE_TYPES = (*DISPLAY_TYPES, "N/D")

SUMMARY_FILENAME = "industry_taxonomy_impact_summary_202606.csv"
FLOWS_FILENAME = "industry_taxonomy_impact_flows_202606.csv"
ISSUANCE_FILENAME = "industry_taxonomy_issuance_impact_202606.csv"
MARKET_SHARE_FILENAME = (
    "industry_taxonomy_market_share_denominator_impact_202606.csv"
)


class TaxonomyImpactError(RuntimeError):
    """Raised when two views cannot be compared without hiding a mismatch."""


@dataclass(frozen=True)
class TaxonomyImpactReport:
    summary: pd.DataFrame
    flows: pd.DataFrame
    issuance: pd.DataFrame
    market_share_denominators: pd.DataFrame


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_text(repo_dir: Path, ref: str, relative_path: Path | str) -> str:
    """Read a tracked baseline without checking it out or mutating the tree."""

    result = subprocess.run(
        ["git", "show", f"{ref}:{Path(relative_path).as_posix()}"],
        cwd=Path(repo_dir),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or "git show failed"
        raise TaxonomyImpactError(
            f"não foi possível ler {relative_path} em {ref}: {detail}"
        )
    return result.stdout


def git_ref_commit(repo_dir: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=Path(repo_dir),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise TaxonomyImpactError(
            f"não foi possível resolver o ref {ref}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def taxonomy_actions_from_csv_text(text: str) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    for column in TAXONOMY_REVIEW_COLUMNS:
        if column not in frame:
            frame[column] = ""
    frame = frame.loc[:, list(TAXONOMY_REVIEW_COLUMNS)].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    return frame


def load_source_mix(workbook_path: Path) -> pd.DataFrame:
    """Read the exact June/2026 stock mix carried by the audited workbook."""

    frame = pd.read_excel(workbook_path, sheet_name=SOURCE_MIX_SHEET, header=0)
    required = {"competencia", "anbima_tipo", "pl_brl", "funds"}
    missing = required.difference(frame.columns)
    if missing:
        raise TaxonomyImpactError(
            f"aba {SOURCE_MIX_SHEET} sem colunas: {', '.join(sorted(missing))}"
        )
    scoped = frame[frame["competencia"].astype(str).eq(REFERENCE_COMPETENCE)].copy()
    scoped["anbima_tipo"] = scoped["anbima_tipo"].fillna("N/D").astype(str).str.strip()
    scoped["pl_brl"] = pd.to_numeric(scoped["pl_brl"], errors="coerce")
    scoped["funds"] = pd.to_numeric(scoped["funds"], errors="coerce")
    scoped = scoped[scoped["anbima_tipo"].isin(SOURCE_TYPES)].copy()
    if scoped["anbima_tipo"].duplicated().any() or set(scoped["anbima_tipo"]) != set(
        SOURCE_TYPES
    ):
        raise TaxonomyImpactError(
            "Mix ANBIMA de 2026-06 não contém exatamente os quatro Tipos e N/D"
        )
    if scoped[["pl_brl", "funds"]].isna().any().any():
        raise TaxonomyImpactError("Mix ANBIMA de 2026-06 contém PL ou contagem ausente")
    order = {name: index for index, name in enumerate(SOURCE_TYPES)}
    scoped["_order"] = scoped["anbima_tipo"].map(order)
    return scoped.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def _validate_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    required = {
        "cnpj_fundo",
        "denominacao_referencia",
        "pl_brl",
        "tipo_atual",
        "foco_atual",
        "tipo_proposto",
        "foco_proposto",
        "efeito",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise TaxonomyImpactError(
            "decisões auditadas sem colunas: " + ", ".join(sorted(missing))
        )
    frame = decisions.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["pl_brl"] = pd.to_numeric(frame["pl_brl"], errors="coerce")
    if frame["cnpj_fundo"].duplicated().any() or frame["pl_brl"].isna().any():
        raise TaxonomyImpactError("decisões auditadas têm CNPJ repetido ou PL ausente")
    counts = frame["efeito"].value_counts().to_dict()
    if counts != {TYPE_MIGRATION_LABEL: 19, FOCUS_ONLY_LABEL: 18}:
        raise TaxonomyImpactError(
            "decisões auditadas deveriam reconciliar 19 migrações de Tipo e "
            f"18 mudanças só de Foco; receberam {counts}"
        )
    return frame


def build_gross_source_impact(
    decisions: pd.DataFrame,
    source_mix: pd.DataFrame,
    *,
    source_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the closed 19 Type moves to the workbook's own stock perimeter."""

    decisions = _validate_decisions(decisions)
    migrations = decisions[decisions["efeito"].eq(TYPE_MIGRATION_LABEL)].copy()
    denominator = float(source_mix["pl_brl"].sum())
    if denominator <= 0:
        raise TaxonomyImpactError("perímetro bruto da fonte sem PL positivo")

    summary_rows: list[dict[str, Any]] = []
    for effect in (TYPE_MIGRATION_LABEL, FOCUS_ONLY_LABEL):
        scoped = decisions[decisions["efeito"].eq(effect)]
        summary_rows.append(
            {
                "view": "source_decision_summary",
                "competence": REFERENCE_COMPETENCE,
                "universe": "37 decisões documentais no Top 200 da fonte auditada",
                "dimension": "classe_decisao",
                "category": effect,
                "decision_count": int(len(scoped)),
                "impacted_pl_brl": float(scoped["pl_brl"].sum()),
                "before_brl": pd.NA,
                "after_brl": pd.NA,
                "delta_brl": pd.NA,
                "denominator_brl": denominator,
                "before_share": pd.NA,
                "after_share": pd.NA,
                "delta_pp": pd.NA,
                "source": source_label,
                "note": (
                    "PL impactado soma os casos da classe; mudanças só de Foco "
                    "não alteram o gráfico por Tipo."
                ),
            }
        )

    net = {name: 0.0 for name in SOURCE_TYPES}
    out_pl = {name: 0.0 for name in SOURCE_TYPES}
    in_pl = {name: 0.0 for name in SOURCE_TYPES}
    out_count = {name: 0 for name in SOURCE_TYPES}
    in_count = {name: 0 for name in SOURCE_TYPES}
    for row in migrations.itertuples(index=False):
        if row.tipo_atual not in net or row.tipo_proposto not in net:
            raise TaxonomyImpactError(
                f"migração fora do Mix ANBIMA: {row.tipo_atual} → {row.tipo_proposto}"
            )
        value = float(row.pl_brl)
        net[row.tipo_atual] -= value
        net[row.tipo_proposto] += value
        out_pl[row.tipo_atual] += value
        in_pl[row.tipo_proposto] += value
        out_count[row.tipo_atual] += 1
        in_count[row.tipo_proposto] += 1

    before_by_type = source_mix.set_index("anbima_tipo")["pl_brl"]
    for category in SOURCE_TYPES:
        before = float(before_by_type.loc[category])
        after = before + net[category]
        summary_rows.append(
            {
                "view": "source_gross_stock_type",
                "competence": REFERENCE_COMPETENCE,
                "universe": "PL ex-FIC da aba Mix ANBIMA do workbook auditado",
                "dimension": "tipo_anbima_exibido",
                "category": category,
                "decision_count": out_count[category] + in_count[category],
                "impacted_pl_brl": out_pl[category] + in_pl[category],
                "before_brl": before,
                "after_brl": after,
                "delta_brl": net[category],
                "denominator_brl": denominator,
                "before_share": before / denominator,
                "after_share": after / denominator,
                "delta_pp": net[category] / denominator * 100.0,
                "source": source_label,
                "note": (
                    f"saídas: {out_count[category]} fundos / R$ {out_pl[category]:.2f}; "
                    f"entradas: {in_count[category]} fundos / R$ {in_pl[category]:.2f}. "
                    "Perímetro da fonte preservado; N/D permanece no denominador."
                ),
            }
        )

    flow_rows: list[dict[str, Any]] = []
    grouped = decisions.groupby(
        [
            "efeito",
            "tipo_atual",
            "foco_atual",
            "tipo_proposto",
            "foco_proposto",
        ],
        dropna=False,
        sort=True,
    )
    for keys, rows in grouped:
        effect, from_type, from_focus, to_type, to_focus = keys
        flow_rows.append(
            {
                "view": "source_gross_decision_flow",
                "competence": REFERENCE_COMPETENCE,
                "effect": effect,
                "from_type": from_type,
                "from_focus": from_focus,
                "to_type": to_type,
                "to_focus": to_focus,
                "decision_count": int(len(rows)),
                "pl_brl": float(rows["pl_brl"].sum()),
                "cnpjs": " | ".join(sorted(rows["cnpj_fundo"].astype(str))),
                "source": source_label,
                "note": "Fluxo documental bruto; cada CNPJ aparece uma vez.",
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(flow_rows)


def _current_photo(fund_base: pd.DataFrame) -> pd.DataFrame:
    required = {
        "competencia",
        "cnpj_fundo",
        "pl",
        "is_fic_fidc",
        "anbima_tipo_oficial",
        "anbima_foco_oficial",
    }
    missing = required.difference(fund_base.columns)
    if missing:
        raise TaxonomyImpactError(
            "base corrente sem colunas: " + ", ".join(sorted(missing))
        )
    photo = fund_base[
        fund_base["competencia"].astype(str).eq(REFERENCE_COMPETENCE)
    ].copy()
    photo["cnpj_fundo"] = photo["cnpj_fundo"].map(normalize_cnpj)
    photo["pl"] = pd.to_numeric(photo["pl"], errors="coerce")
    if photo["cnpj_fundo"].duplicated().any():
        raise TaxonomyImpactError("base corrente tem mais de uma linha por fundo em 2026-06")
    return photo


def _effective_photo(
    current_photo: pd.DataFrame, actions: pd.DataFrame
) -> pd.DataFrame:
    effective = apply_taxonomy_review_overlay(current_photo, actions)
    effective["anbima_tipo"] = effective["anbima_tipo_curado"]
    effective["anbima_foco"] = effective["anbima_foco_curado"]
    return effective


def build_incremental_current_impact(
    fund_base: pd.DataFrame,
    baseline_actions: pd.DataFrame,
    current_actions: pd.DataFrame,
    *,
    baseline_label: str,
    current_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Hold the June fund photo fixed and change only the analytical ledger."""

    photo = _current_photo(fund_base)
    before_effective = _effective_photo(photo, baseline_actions)
    after_effective = _effective_photo(photo, current_actions)
    before_mix = build_curated_type_mix(
        photo, baseline_actions, latest=REFERENCE_COMPETENCE
    )
    after_mix = build_curated_type_mix(photo, current_actions, latest=REFERENCE_COMPETENCE)
    before_mix = before_mix.set_index("anbima_tipo").reindex(DISPLAY_TYPES)
    after_mix = after_mix.set_index("anbima_tipo").reindex(DISPLAY_TYPES)
    before_total = float(before_mix["pl"].sum())
    after_total = float(after_mix["pl"].sum())
    if abs(before_total - after_total) > 0.01:
        raise TaxonomyImpactError(
            "troca de ledger alterou o denominador do universo corrente"
        )

    summary_rows: list[dict[str, Any]] = []
    for category in DISPLAY_TYPES:
        before = float(before_mix.at[category, "pl"])
        after = float(after_mix.at[category, "pl"])
        delta = after - before
        summary_rows.append(
            {
                "view": "current_bundle_incremental_stock_type",
                "competence": REFERENCE_COMPETENCE,
                "universe": "mesma base corrente de fundos, ex-FIC; varia somente o ledger",
                "dimension": "tipo_anbima_exibido",
                "category": category,
                "decision_count": pd.NA,
                "impacted_pl_brl": pd.NA,
                "before_brl": before,
                "after_brl": after,
                "delta_brl": delta,
                "denominator_brl": before_total,
                "before_share": before / before_total if before_total else pd.NA,
                "after_share": after / before_total if before_total else pd.NA,
                "delta_pp": delta / before_total * 100.0 if before_total else pd.NA,
                "source": f"antes={baseline_label}; depois={current_label}",
                "note": (
                    "Campos oficiais e PL de 2026-06 são idênticos nas duas fotos; "
                    "N/D segue a regra de exibição em Outros."
                ),
            }
        )

    keys = [
        "cnpj_fundo",
        "denominacao",
        "pl",
        "anbima_tipo_curado",
        "anbima_foco_curado",
    ]
    before_rows = before_effective[keys].rename(
        columns={
            "anbima_tipo_curado": "from_type",
            "anbima_foco_curado": "from_focus",
        }
    )
    after_rows = after_effective[
        ["cnpj_fundo", "anbima_tipo_curado", "anbima_foco_curado"]
    ].rename(
        columns={
            "anbima_tipo_curado": "to_type",
            "anbima_foco_curado": "to_focus",
        }
    )
    changes = before_rows.merge(
        after_rows, on="cnpj_fundo", how="inner", validate="one_to_one"
    )
    changes = changes[
        changes["from_type"].ne(changes["to_type"])
        | changes["from_focus"].ne(changes["to_focus"])
    ].copy()
    changes["effect"] = changes["from_type"].ne(changes["to_type"]).map(
        {True: TYPE_MIGRATION_LABEL, False: FOCUS_ONLY_LABEL}
    )
    flow_rows: list[dict[str, Any]] = []
    if not changes.empty:
        grouped = changes.groupby(
            ["effect", "from_type", "from_focus", "to_type", "to_focus"],
            dropna=False,
            sort=True,
        )
        for keys_group, rows in grouped:
            effect, from_type, from_focus, to_type, to_focus = keys_group
            flow_rows.append(
                {
                    "view": "current_bundle_incremental_flow",
                    "competence": REFERENCE_COMPETENCE,
                    "effect": effect,
                    "from_type": from_type,
                    "from_focus": from_focus,
                    "to_type": to_type,
                    "to_focus": to_focus,
                    "decision_count": int(len(rows)),
                    "pl_brl": float(rows["pl"].sum()),
                    "cnpjs": " | ".join(sorted(rows["cnpj_fundo"].astype(str))),
                    "source": f"antes={baseline_label}; depois={current_label}",
                    "note": (
                        "Efeito incremental no PL observado em 2026-06; decisões "
                        "já presentes no baseline não reaparecem."
                    ),
                }
            )

    before_market, _ = build_market_share_by_subtype(before_effective)
    after_market, _ = build_market_share_by_subtype(after_effective)
    market_impact = build_market_share_denominator_impact(
        before_market,
        after_market,
        baseline_label=baseline_label,
        current_label=current_label,
    )
    return pd.DataFrame(summary_rows), pd.DataFrame(flow_rows), market_impact


def _market_denominators(frame: pd.DataFrame, side: str) -> pd.DataFrame:
    columns = [
        "papel",
        "tipo_anbima",
        "foco_anbima",
        "denominador_pl_subtipo_brl",
        "denominador_publicacao_pl_positivo_brl",
        "fundos_subtipo",
    ]
    missing = set(columns).difference(frame.columns)
    if missing:
        raise TaxonomyImpactError(
            "market share sem colunas: " + ", ".join(sorted(missing))
        )
    reduced = frame.loc[:, columns].drop_duplicates()
    role_counts = reduced.groupby(["tipo_anbima", "foco_anbima"])["papel"].nunique()
    if not role_counts.eq(3).all():
        raise TaxonomyImpactError(
            f"denominadores de market share ({side}) não cobrem os três papéis"
        )
    value_columns = [
        "denominador_pl_subtipo_brl",
        "denominador_publicacao_pl_positivo_brl",
        "fundos_subtipo",
    ]
    uniqueness = reduced.groupby(["tipo_anbima", "foco_anbima"])[
        value_columns
    ].nunique(dropna=False)
    if not uniqueness.le(1).all().all():
        raise TaxonomyImpactError(
            f"denominadores de market share ({side}) divergem entre papéis"
        )
    return (
        reduced.sort_values(["tipo_anbima", "foco_anbima", "papel"])
        .drop_duplicates(["tipo_anbima", "foco_anbima"])
        .drop(columns="papel")
    )


def build_market_share_denominator_impact(
    before_market: pd.DataFrame,
    after_market: pd.DataFrame,
    *,
    baseline_label: str,
    current_label: str,
) -> pd.DataFrame:
    before = _market_denominators(before_market, "antes").add_prefix("before_")
    after = _market_denominators(after_market, "depois").add_prefix("after_")
    merged = before.merge(
        after,
        left_on=["before_tipo_anbima", "before_foco_anbima"],
        right_on=["after_tipo_anbima", "after_foco_anbima"],
        how="outer",
        validate="one_to_one",
    )
    merged["tipo_anbima"] = merged["before_tipo_anbima"].fillna(
        merged["after_tipo_anbima"]
    )
    merged["foco_anbima"] = merged["before_foco_anbima"].fillna(
        merged["after_foco_anbima"]
    )
    for column in (
        "before_denominador_pl_subtipo_brl",
        "after_denominador_pl_subtipo_brl",
        "before_denominador_publicacao_pl_positivo_brl",
        "after_denominador_publicacao_pl_positivo_brl",
        "before_fundos_subtipo",
        "after_fundos_subtipo",
    ):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    total_before = float(merged["before_denominador_pl_subtipo_brl"].sum())
    total_after = float(merged["after_denominador_pl_subtipo_brl"].sum())
    if abs(total_before - total_after) > 0.01:
        raise TaxonomyImpactError(
            "taxonomia alterou o denominador total do escopo de market share"
        )
    merged["delta_denominator_brl"] = (
        merged["after_denominador_pl_subtipo_brl"]
        - merged["before_denominador_pl_subtipo_brl"]
    )
    merged["before_share_scope"] = (
        merged["before_denominador_pl_subtipo_brl"] / total_before
        if total_before
        else pd.NA
    )
    merged["after_share_scope"] = (
        merged["after_denominador_pl_subtipo_brl"] / total_after
        if total_after
        else pd.NA
    )
    merged["delta_pp"] = (
        (merged["after_share_scope"] - merged["before_share_scope"]) * 100.0
    )
    output = pd.DataFrame(
        {
            "competence": REFERENCE_COMPETENCE,
            "tipo_anbima": merged["tipo_anbima"],
            "foco_anbima": merged["foco_anbima"],
            "before_denominator_brl": merged["before_denominador_pl_subtipo_brl"],
            "after_denominator_brl": merged["after_denominador_pl_subtipo_brl"],
            "delta_denominator_brl": merged["delta_denominator_brl"],
            "before_positive_denominator_brl": merged[
                "before_denominador_publicacao_pl_positivo_brl"
            ],
            "after_positive_denominator_brl": merged[
                "after_denominador_publicacao_pl_positivo_brl"
            ],
            "before_funds": merged["before_fundos_subtipo"].astype(int),
            "after_funds": merged["after_fundos_subtipo"].astype(int),
            "scope_total_before_brl": total_before,
            "scope_total_after_brl": total_after,
            "before_share_scope": merged["before_share_scope"],
            "after_share_scope": merged["after_share_scope"],
            "delta_pp": merged["delta_pp"],
            "roles_reconciled": 3,
            "source": f"antes={baseline_label}; depois={current_label}",
            "note": (
                "Denominador idêntico em administração, gestão e custódia; "
                "PL negativo permanece no denominador bruto e sai do denominador "
                "positivo de publicação."
            ),
        }
    )
    return output.sort_values(
        ["tipo_anbima", "foco_anbima"], kind="stable"
    ).reset_index(drop=True)


def build_issuance_impact(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    baseline_label: str,
    current_label: str,
) -> pd.DataFrame:
    required = {"period_key", "period_label", "categoria", "volume_brl", "share"}
    for name, frame in (("baseline", baseline), ("current", current)):
        missing = required.difference(frame.columns)
        if missing:
            raise TaxonomyImpactError(
                f"emissões {name} sem colunas: " + ", ".join(sorted(missing))
            )
    before = baseline.loc[:, list(required)].rename(
        columns={
            "period_label": "before_period_label",
            "volume_brl": "before_volume_brl",
            "share": "before_share",
        }
    )
    after = current.loc[:, list(required)].rename(
        columns={
            "period_label": "after_period_label",
            "volume_brl": "after_volume_brl",
            "share": "after_share",
        }
    )
    merged = before.merge(
        after,
        on=["period_key", "categoria"],
        how="outer",
        validate="one_to_one",
    )
    if merged[
        ["before_period_label", "after_period_label", "before_volume_brl", "after_volume_brl"]
    ].isna().any().any():
        raise TaxonomyImpactError("emissões baseline e current não têm o mesmo contrato")
    if not merged["before_period_label"].eq(merged["after_period_label"]).all():
        raise TaxonomyImpactError("rótulos de período das emissões divergiram")
    merged["before_volume_brl"] = pd.to_numeric(
        merged["before_volume_brl"], errors="raise"
    )
    merged["after_volume_brl"] = pd.to_numeric(
        merged["after_volume_brl"], errors="raise"
    )
    totals = merged.groupby("period_key").agg(
        period_total_before_brl=("before_volume_brl", "sum"),
        period_total_after_brl=("after_volume_brl", "sum"),
    )
    if not (
        totals["period_total_before_brl"] - totals["period_total_after_brl"]
    ).abs().le(0.01).all():
        raise TaxonomyImpactError("reclassificação alterou o total emitido por período")
    merged = merged.join(totals, on="period_key")
    merged["delta_brl"] = merged["after_volume_brl"] - merged["before_volume_brl"]
    merged["before_share"] = pd.to_numeric(merged["before_share"], errors="raise")
    merged["after_share"] = pd.to_numeric(merged["after_share"], errors="raise")
    merged["delta_pp"] = (merged["after_share"] - merged["before_share"]) * 100.0
    period_order = {key: index for index, key in enumerate(baseline["period_key"].drop_duplicates())}
    type_order = {name: index for index, name in enumerate(DISPLAY_TYPES)}
    merged["_period_order"] = merged["period_key"].map(period_order)
    merged["_type_order"] = merged["categoria"].map(type_order)
    output = pd.DataFrame(
        {
            "period_key": merged["period_key"],
            "period_label": merged["before_period_label"],
            "categoria": merged["categoria"],
            "before_volume_brl": merged["before_volume_brl"],
            "after_volume_brl": merged["after_volume_brl"],
            "delta_brl": merged["delta_brl"],
            "before_share": merged["before_share"],
            "after_share": merged["after_share"],
            "delta_pp": merged["delta_pp"],
            "period_total_before_brl": merged["period_total_before_brl"],
            "period_total_after_brl": merged["period_total_after_brl"],
            "source_before": baseline_label,
            "source_after": current_label,
            "note": (
                "Comparação de artefatos materializados; total do período "
                "preservado. Em 2023, ambos os lados mantêm o mesmo fator ANBIMA."
            ),
            "_period_order": merged["_period_order"],
            "_type_order": merged["_type_order"],
        }
    )
    return output.sort_values(["_period_order", "_type_order"]).drop(
        columns=["_period_order", "_type_order"]
    ).reset_index(drop=True)


def build_taxonomy_impact_report(
    *,
    decisions: pd.DataFrame,
    source_mix: pd.DataFrame,
    fund_base: pd.DataFrame,
    baseline_actions: pd.DataFrame,
    current_actions: pd.DataFrame,
    baseline_issuance: pd.DataFrame,
    current_issuance: pd.DataFrame,
    source_label: str,
    baseline_label: str,
    current_label: str,
) -> TaxonomyImpactReport:
    gross_summary, gross_flows = build_gross_source_impact(
        decisions, source_mix, source_label=source_label
    )
    incremental_summary, incremental_flows, market = build_incremental_current_impact(
        fund_base,
        baseline_actions,
        current_actions,
        baseline_label=baseline_label,
        current_label=current_label,
    )
    issuance = build_issuance_impact(
        baseline_issuance,
        current_issuance,
        baseline_label=baseline_label,
        current_label=current_label,
    )
    return TaxonomyImpactReport(
        summary=pd.concat([gross_summary, incremental_summary], ignore_index=True),
        flows=pd.concat([gross_flows, incremental_flows], ignore_index=True),
        issuance=issuance,
        market_share_denominators=market,
    )


def materialize_taxonomy_impact(
    report: TaxonomyImpactReport, data_dir: Path
) -> dict[str, Path]:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "summary": data_dir / SUMMARY_FILENAME,
        "flows": data_dir / FLOWS_FILENAME,
        "issuance": data_dir / ISSUANCE_FILENAME,
        "market_share": data_dir / MARKET_SHARE_FILENAME,
    }
    frames = {
        "summary": report.summary,
        "flows": report.flows,
        "issuance": report.issuance,
        "market_share": report.market_share_denominators,
    }
    for key, frame in frames.items():
        frame.to_csv(
            outputs[key],
            index=False,
            lineterminator="\n",
            float_format="%.12f",
        )
    return outputs


__all__ = [
    "DISPLAY_TYPES",
    "FLOWS_FILENAME",
    "ISSUANCE_FILENAME",
    "MARKET_SHARE_FILENAME",
    "REFERENCE_COMPETENCE",
    "SOURCE_MIX_SHEET",
    "SUMMARY_FILENAME",
    "TaxonomyImpactError",
    "TaxonomyImpactReport",
    "build_gross_source_impact",
    "build_incremental_current_impact",
    "build_issuance_impact",
    "build_market_share_denominator_impact",
    "build_taxonomy_impact_report",
    "file_sha256",
    "git_blob_text",
    "git_ref_commit",
    "load_source_mix",
    "materialize_taxonomy_impact",
    "taxonomy_actions_from_csv_text",
]
