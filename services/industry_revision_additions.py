"""Pure analytical additions for the FIDC industry revision.

The functions in this module consume already-loaded dataframes.  They perform
no file reads, writes, network calls or presentation-layer transformations.
Each output has a stable, exported column contract so the pipeline can add the
tables later without moving analytical rules into the renderer.
"""

from __future__ import annotations

from collections.abc import Iterable
import math
import re
from typing import Final

import pandas as pd


DEFAULT_BANK_GROUPS: Final[tuple[str, ...]] = (
    "BB",
    "BTG",
    "Bradesco",
    "Itau",
    "Santander",
)

INDEPENDENT_PROVIDER_HISTORY_COLUMNS: Final[tuple[str, ...]] = (
    "competencia",
    "papel",
    "participante",
    "rank_independente",
    "rank_geral",
    "pl_brl",
    "share_pl_total",
    "fundos",
    "denominador_pl_brl",
    "fundos_universo",
    "fonte_prestador",
    "ownership_status",
    "ownership_source_url",
    "ownership_as_of_date",
    "ownership_notes",
    "latest_pl_brl",
    "latest_rank_independente",
    "selected_latest_top_n",
    "ordem_slide",
)

BANK_COHORT_HISTORY_COLUMNS: Final[tuple[str, ...]] = (
    "competencia",
    "bank_group",
    "is_total_5_banks",
    "pl_brl",
    "pl_brl_raw",
    "pl_recovered_official",
    "pl_display_suffix",
    "pl_source_references",
    "fundos_observados",
    "fundos_curados",
    "cobertura_fundos",
    "raizes_cnpj_listadas",
    "raizes_cnpj_observadas",
    "raizes_cnpj_nao_observadas",
    "cnpjs_nao_observados",
    "source_references",
    "publication_status",
)

BANK_COHORT_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "competencia",
    "bank_group",
    "cnpj_root8",
    "cnpj_fundo",
    "denominacao",
    "pl_brl",
    "pl_brl_raw",
    "pl_recovered_official",
    "pl_display_suffix",
    "pl_source_reference",
    "observado",
    "pl_reportado_zero",
    "source_reference",
)

ACQUIRING_RECLASSIFIED_MIX_COLUMNS: Final[tuple[str, ...]] = (
    "competencia",
    "categoria_cvm",
    "rank_reclassificado",
    "pl_original_brl",
    "share_original",
    "pl_reclassificado_brl",
    "share_reclassificado",
    "delta_pl_brl",
    "fundos_original",
    "fundos_reclassificados",
    "fundos_movidos_da_categoria",
    "pl_movido_da_categoria_brl",
    "cnpjs_movidos_da_categoria",
    "fundos_movidos_para_adquirencia",
    "pl_movido_para_adquirencia_brl",
    "cnpjs_movidos_para_adquirencia",
    "fundos_adquirencia_curados",
    "fundos_adquirencia_observados",
    "cobertura_cnpjs_curados",
    "cnpjs_curados_nao_observados",
    "denominador_pl_brl",
    "source_references",
)


def _require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    *,
    label: str,
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} deve ser um DataFrame")
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"{label} sem colunas obrigatórias: {sorted(missing)}")


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return "" if text.lower() in {"", "nan", "none", "nat"} else text


def _digits(value: object) -> str:
    raw = _clean(value)
    if re.fullmatch(r"\d+(?:\.0+)?", raw):
        raw = raw.split(".", 1)[0]
    return re.sub(r"\D", "", raw)


def _cnpj14(value: object) -> str:
    digits = _digits(value)
    return digits.zfill(14) if 0 < len(digits) <= 14 else ""


def _cnpj_root8(value: object) -> str:
    digits = _digits(value)
    if not digits:
        return ""
    if len(digits) <= 8:
        return digits.zfill(8)
    if len(digits) <= 14:
        return digits.zfill(14)[:8]
    return ""


def _join_unique(values: Iterable[object], separator: str = " | ") -> str:
    unique = sorted({_clean(value) for value in values if _clean(value)})
    return separator.join(unique)


def _parse_bool(value: object, *, label: str) -> bool:
    normalized = _clean(value).lower()
    if normalized in {"1", "true", "t", "sim", "s", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "nao", "não", "n", "no"}:
        return False
    raise ValueError(f"{label} contém booleano inválido: {value!r}")


def _boolean_series(values: pd.Series, *, label: str) -> pd.Series:
    return values.map(lambda value: _parse_bool(value, label=label)).astype(bool)


def _numeric_series(values: pd.Series, *, label: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    bad = numeric.isna() & values.map(_clean).ne("")
    if bad.any():
        examples = values.loc[bad].map(_clean).drop_duplicates().head(3).tolist()
        raise ValueError(f"{label} contém valores não numéricos: {examples}")
    return numeric


def _single_numeric(values: pd.Series, *, label: str) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    first = float(numeric.iloc[0])
    tolerance = max(1.0, abs(first)) * 1e-10
    if any(abs(float(value) - first) > tolerance for value in numeric.iloc[1:]):
        raise ValueError(f"{label} inconsistente no mesmo papel/competência")
    return first


def _rank_rows(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    rank_column: str,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, group in frame.groupby(group_columns, sort=True, dropna=False):
        ordered = group.sort_values(
            ["pl_brl", "participante"],
            ascending=[False, True],
            kind="mergesort",
        ).copy()
        ordered[rank_column] = range(1, len(ordered) + 1)
        parts.append(ordered)
    if not parts:
        return frame.assign(**{rank_column: pd.Series(dtype="int64")})
    return pd.concat(parts, ignore_index=True)


def _ownership_rules(ownership_curation: pd.DataFrame) -> list[dict[str, object]]:
    required = {
        "participant_pattern",
        "normalized_group",
        "bank_affiliated",
        "independent_reviewed",
        "ownership_status",
        "source_url",
        "as_of_date",
        "notes",
    }
    _require_columns(ownership_curation, required, label="ownership_curation")
    if ownership_curation.empty:
        raise ValueError("ownership_curation está vazia")

    rules: list[dict[str, object]] = []
    group_flags: dict[str, tuple[bool, bool]] = {}
    for index, row in ownership_curation.reset_index(drop=True).iterrows():
        pattern = _clean(row["participant_pattern"])
        group = _clean(row["normalized_group"])
        if not pattern or not group:
            raise ValueError(f"ownership_curation linha {index} sem padrão ou grupo")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"ownership_curation linha {index} contém regex inválida: {exc}"
            ) from exc
        bank_affiliated = _parse_bool(
            row["bank_affiliated"], label="ownership_curation.bank_affiliated"
        )
        independent_reviewed = _parse_bool(
            row["independent_reviewed"],
            label="ownership_curation.independent_reviewed",
        )
        if bank_affiliated and independent_reviewed:
            raise ValueError(
                f"grupo {group!r} não pode ser bancário e independente revisado"
            )
        flags = (bank_affiliated, independent_reviewed)
        if group in group_flags and group_flags[group] != flags:
            raise ValueError(f"flags societários conflitantes para o grupo {group!r}")
        group_flags[group] = flags
        rules.append(
            {
                "compiled": compiled,
                "normalized_group": group,
                "bank_affiliated": bank_affiliated,
                "independent_reviewed": independent_reviewed,
                "ownership_status": _clean(row["ownership_status"]),
                "source_url": _clean(row["source_url"]),
                "as_of_date": _clean(row["as_of_date"]),
                "notes": _clean(row["notes"]),
            }
        )
    return rules


def _match_ownership(
    participant: object,
    rules: list[dict[str, object]],
) -> dict[str, object]:
    name = _clean(participant) or "Não informado"
    matches = [rule for rule in rules if rule["compiled"].search(name)]
    if not matches:
        return {
            "participante": name,
            "bank_affiliated": False,
            "independent_reviewed": False,
            "ownership_status": "unreviewed",
            "ownership_source_url": "",
            "ownership_as_of_date": "",
            "ownership_notes": "",
        }
    groups = {str(rule["normalized_group"]) for rule in matches}
    flags = {
        (bool(rule["bank_affiliated"]), bool(rule["independent_reviewed"]))
        for rule in matches
    }
    if len(groups) != 1 or len(flags) != 1:
        raise ValueError(f"regras societárias conflitantes para {name!r}")
    bank_affiliated, independent_reviewed = next(iter(flags))
    return {
        "participante": next(iter(groups)),
        "bank_affiliated": bank_affiliated,
        "independent_reviewed": independent_reviewed,
        "ownership_status": _join_unique(
            rule["ownership_status"] for rule in matches
        ),
        "ownership_source_url": _join_unique(rule["source_url"] for rule in matches),
        "ownership_as_of_date": max(
            (_clean(rule["as_of_date"]) for rule in matches), default=""
        ),
        "ownership_notes": _join_unique(rule["notes"] for rule in matches),
    }


def build_independent_provider_historical_ranking(
    provider_history: pd.DataFrame,
    ownership_curation: pd.DataFrame,
    *,
    latest_period: str | None = None,
    top_n: int = 6,
) -> pd.DataFrame:
    """Consolidate provider groups and rank reviewed independents.

    ``rank_geral`` is recalculated after every reviewed bank and independent
    alias is consolidated.  ``rank_independente`` is then calculated only among
    groups explicitly marked as reviewed independents.  Unmatched participants
    remain in the general ranking and never enter the independent ranking.
    """

    required = {
        "competencia",
        "papel",
        "participante",
        "pl_brl",
        "denominador_pl_brl",
    }
    _require_columns(provider_history, required, label="provider_history")
    if top_n <= 0:
        raise ValueError("top_n deve ser positivo")
    if provider_history.empty:
        return pd.DataFrame(columns=INDEPENDENT_PROVIDER_HISTORY_COLUMNS)

    history = provider_history.copy()
    history["competencia"] = history["competencia"].map(_clean).str[:7]
    history["papel"] = history["papel"].map(_clean)
    history["participante"] = history["participante"].map(_clean)
    history["pl_brl"] = _numeric_series(
        history["pl_brl"], label="provider_history.pl_brl"
    )
    history["denominador_pl_brl"] = _numeric_series(
        history["denominador_pl_brl"],
        label="provider_history.denominador_pl_brl",
    )
    if history[["competencia", "papel", "participante"]].eq("").any().any():
        raise ValueError("provider_history contém chave vazia")

    history["fundos"] = (
        _numeric_series(history["fundos"], label="provider_history.fundos")
        if "fundos" in history
        else 0
    )
    history["fundos_universo"] = (
        _numeric_series(
            history["fundos_universo"], label="provider_history.fundos_universo"
        )
        if "fundos_universo" in history
        else float("nan")
    )
    history["fonte_prestador"] = (
        history["fonte_prestador"].map(_clean)
        if "fonte_prestador" in history
        else ""
    )

    rules = _ownership_rules(ownership_curation)
    matches = {
        participant: _match_ownership(participant, rules)
        for participant in history["participante"].unique()
    }
    for column in (
        "participante",
        "bank_affiliated",
        "independent_reviewed",
        "ownership_status",
        "ownership_source_url",
        "ownership_as_of_date",
        "ownership_notes",
    ):
        target = "participante_normalizado" if column == "participante" else column
        history[target] = history["participante"].map(
            lambda value, field=column: matches[value][field]
        )

    rows: list[dict[str, object]] = []
    for (period, role, group), scoped in history.groupby(
        ["competencia", "papel", "participante_normalizado"],
        sort=True,
        dropna=False,
    ):
        denominator = _single_numeric(
            scoped["denominador_pl_brl"],
            label=f"denominador {period}/{role}",
        )
        funds_universe = _single_numeric(
            scoped["fundos_universo"],
            label=f"fundos_universo {period}/{role}",
        )
        bank_flags = set(scoped["bank_affiliated"].astype(bool))
        independent_flags = set(scoped["independent_reviewed"].astype(bool))
        if len(bank_flags) != 1 or len(independent_flags) != 1:
            raise ValueError(f"flags conflitantes após consolidação de {group!r}")
        rows.append(
            {
                "competencia": period,
                "papel": role,
                "participante": group,
                "pl_brl": float(scoped["pl_brl"].sum(min_count=1)),
                "fundos": int(scoped["fundos"].fillna(0).sum()),
                "denominador_pl_brl": denominator,
                "fundos_universo": (
                    int(funds_universe) if not math.isnan(funds_universe) else pd.NA
                ),
                "fonte_prestador": _join_unique(scoped["fonte_prestador"]),
                "bank_affiliated": next(iter(bank_flags)),
                "independent_reviewed": next(iter(independent_flags)),
                "ownership_status": _join_unique(scoped["ownership_status"]),
                "ownership_source_url": _join_unique(
                    scoped["ownership_source_url"]
                ),
                "ownership_as_of_date": max(
                    scoped["ownership_as_of_date"].map(_clean), default=""
                ),
                "ownership_notes": _join_unique(scoped["ownership_notes"]),
            }
        )

    consolidated = pd.DataFrame(rows)
    consolidated = _rank_rows(
        consolidated,
        group_columns=["competencia", "papel"],
        rank_column="rank_geral",
    )
    independent = consolidated[
        consolidated["independent_reviewed"]
        & ~consolidated["bank_affiliated"]
    ].copy()
    independent = _rank_rows(
        independent,
        group_columns=["competencia", "papel"],
        rank_column="rank_independente",
    )
    independent["share_pl_total"] = independent["pl_brl"].div(
        independent["denominador_pl_brl"].where(
            independent["denominador_pl_brl"] != 0
        )
    )

    latest = _clean(latest_period)[:7] if latest_period else max(
        independent["competencia"], default=""
    )
    if latest and latest not in set(independent["competencia"]):
        raise ValueError(f"latest_period ausente no ranking independente: {latest}")
    latest_rows = independent[independent["competencia"].eq(latest)].copy()
    latest_lookup = latest_rows.set_index(["papel", "participante"])
    selected = set(
        latest_rows[latest_rows["rank_independente"].le(top_n)][
            ["papel", "participante"]
        ].itertuples(index=False, name=None)
    )

    def latest_value(row: pd.Series, column: str) -> object:
        key = (row["papel"], row["participante"])
        return latest_lookup.at[key, column] if key in latest_lookup.index else pd.NA

    independent["latest_pl_brl"] = independent.apply(
        lambda row: latest_value(row, "pl_brl"), axis=1
    )
    independent["latest_rank_independente"] = independent.apply(
        lambda row: latest_value(row, "rank_independente"), axis=1
    )
    independent["selected_latest_top_n"] = [
        (role, participant) in selected
        for role, participant in zip(
            independent["papel"], independent["participante"]
        )
    ]
    independent["ordem_slide"] = independent["latest_rank_independente"].where(
        independent["selected_latest_top_n"], pd.NA
    )
    independent["rank_independente"] = independent["rank_independente"].astype(
        "Int64"
    )
    independent["rank_geral"] = independent["rank_geral"].astype("Int64")
    independent["latest_rank_independente"] = independent[
        "latest_rank_independente"
    ].astype("Int64")
    independent["ordem_slide"] = independent["ordem_slide"].astype("Int64")
    independent = independent.sort_values(
        ["papel", "latest_rank_independente", "participante", "competencia"],
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    return independent.loc[:, INDEPENDENT_PROVIDER_HISTORY_COLUMNS]


def _prepare_bank_fidc_curation(
    bank_fidc_curation: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize the fixed cohort and its optional official PL recoveries."""

    _require_columns(
        bank_fidc_curation,
        {"bank_group", "cnpj_root8", "source_reference"},
        label="bank_fidc_curation",
    )
    if bank_fidc_curation.empty:
        raise ValueError("bank_fidc_curation está vazia")

    curation = bank_fidc_curation.copy()
    optional_defaults: dict[str, object] = {
        "pl_override_competencia": "",
        "pl_override_brl": float("nan"),
        "pl_override_status": "",
        "pl_override_display_suffix": "",
        "pl_override_source_reference": "",
    }
    for column, default in optional_defaults.items():
        if column not in curation:
            curation[column] = default

    curation["bank_group"] = curation["bank_group"].map(_clean)
    curation["cnpj_root8"] = curation["cnpj_root8"].map(_cnpj_root8)
    curation["source_reference"] = curation["source_reference"].map(_clean)
    curation["pl_override_competencia"] = curation[
        "pl_override_competencia"
    ].map(_clean).str[:7]
    curation["pl_override_brl"] = _numeric_series(
        curation["pl_override_brl"], label="bank_fidc_curation.pl_override_brl"
    )
    for column in (
        "pl_override_status",
        "pl_override_display_suffix",
        "pl_override_source_reference",
    ):
        curation[column] = curation[column].map(_clean)

    if curation[["bank_group", "cnpj_root8"]].eq("").any().any():
        raise ValueError("bank_fidc_curation contém grupo ou raiz de CNPJ inválida")

    has_period = curation["pl_override_competencia"].ne("")
    has_value = curation["pl_override_brl"].notna()
    if (has_period ^ has_value).any():
        raise ValueError(
            "bank_fidc_curation exige competência e valor em conjunto para override de PL"
        )
    override_rows = curation[has_period & has_value]
    if not override_rows.empty:
        if override_rows["pl_override_brl"].le(0).any():
            raise ValueError("override oficial de PL deve ser positivo")
        if not override_rows["pl_override_status"].eq("official_recovered").all():
            raise ValueError(
                "override de PL da coorte deve ter status official_recovered"
            )
        if not override_rows["pl_override_display_suffix"].eq("*").all():
            raise ValueError("override oficial de PL deve usar asterisco")
        if override_rows["pl_override_source_reference"].eq("").any():
            raise ValueError("override oficial de PL exige fonte")
        duplicate_overrides = override_rows.duplicated(
            ["cnpj_root8", "pl_override_competencia"], keep=False
        )
        if duplicate_overrides.any():
            raise ValueError("override de PL duplicado por raiz de CNPJ/competência")

    return curation


def _apply_official_bank_pl_recoveries(
    funds: pd.DataFrame,
    curation: pd.DataFrame,
) -> pd.DataFrame:
    """Replace a malformed reported value with a sourced official value once."""

    recovered = funds.copy()
    recovered["pl_brl_raw"] = recovered["pl"]
    recovered["pl_recovered_official"] = False
    recovered["pl_display_suffix"] = ""
    recovered["pl_source_reference"] = ""

    overrides = curation[
        curation["pl_override_competencia"].ne("")
        & curation["pl_override_brl"].notna()
    ]
    for item in overrides.itertuples(index=False):
        mask = recovered["competencia"].eq(item.pl_override_competencia) & recovered[
            "cnpj_root8"
        ].eq(item.cnpj_root8)
        matches = int(mask.sum())
        if matches != 1:
            raise ValueError(
                "override oficial de PL exige exatamente um registro bruto: "
                f"{item.cnpj_root8}/{item.pl_override_competencia}, encontrados={matches}"
            )
        raw_value = float(recovered.loc[mask, "pl"].iloc[0])
        override_value = float(item.pl_override_brl)
        if raw_value > 0 and not math.isclose(
            raw_value, override_value, rel_tol=1e-10, abs_tol=1_000.0
        ):
            raise ValueError(
                "override oficial de PL conflita com valor bruto positivo: "
                f"{item.cnpj_root8}/{item.pl_override_competencia}"
            )
        recovered.loc[mask, "pl"] = override_value
        recovered.loc[mask, "pl_recovered_official"] = True
        recovered.loc[mask, "pl_display_suffix"] = item.pl_override_display_suffix
        recovered.loc[mask, "pl_source_reference"] = (
            item.pl_override_source_reference
        )
    return recovered


def build_fixed_bank_fidc_cohort_history(
    fund_base: pd.DataFrame,
    bank_fidc_curation: pd.DataFrame,
    *,
    periods: Iterable[str] | None = None,
    expected_bank_groups: Iterable[str] | None = DEFAULT_BANK_GROUPS,
) -> pd.DataFrame:
    """Aggregate a fixed, root-CNPJ cohort for five bank groups by month."""

    _require_columns(
        fund_base,
        {"competencia", "cnpj_fundo", "pl"},
        label="fund_base",
    )
    curation = _prepare_bank_fidc_curation(bank_fidc_curation)
    conflicts = curation.groupby("cnpj_root8")["bank_group"].nunique()
    if conflicts.gt(1).any():
        roots = conflicts[conflicts.gt(1)].index.tolist()
        raise ValueError(f"raiz de CNPJ atribuída a mais de um banco: {roots}")
    curation = curation.drop_duplicates(["bank_group", "cnpj_root8"])

    groups = (
        tuple(sorted({_clean(value) for value in expected_bank_groups}))
        if expected_bank_groups is not None
        else tuple(sorted(curation["bank_group"].unique()))
    )
    observed_groups = set(curation["bank_group"])
    if expected_bank_groups is not None and observed_groups != set(groups):
        raise ValueError(
            "bank_fidc_curation diverge dos cinco grupos esperados: "
            f"esperados={sorted(groups)}, observados={sorted(observed_groups)}"
        )

    funds = fund_base.copy()
    funds["competencia"] = funds["competencia"].map(_clean).str[:7]
    funds["cnpj_fundo"] = funds["cnpj_fundo"].map(_cnpj14)
    funds["cnpj_root8"] = funds["cnpj_fundo"].str[:8]
    funds["pl"] = _numeric_series(funds["pl"], label="fund_base.pl")
    if funds[["competencia", "cnpj_fundo"]].eq("").any().any():
        raise ValueError("fund_base contém competência ou CNPJ inválido")
    duplicated = funds.duplicated(["competencia", "cnpj_fundo"], keep=False)
    if duplicated.any():
        examples = (
            funds.loc[duplicated, ["competencia", "cnpj_fundo"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"fund_base duplicada por competência/CNPJ: {examples}")
    funds = _apply_official_bank_pl_recoveries(funds, curation)

    available_periods = sorted(funds["competencia"].unique())
    selected_periods = (
        [_clean(value)[:7] for value in periods]
        if periods is not None
        else available_periods
    )
    missing_periods = sorted(set(selected_periods).difference(available_periods))
    if missing_periods:
        raise ValueError(f"competências ausentes no fund_base: {missing_periods}")

    root_to_group = curation.set_index("cnpj_root8")["bank_group"].to_dict()
    cohort = funds[funds["cnpj_root8"].isin(root_to_group)].copy()
    cohort["bank_group"] = cohort["cnpj_root8"].map(root_to_group)
    rows: list[dict[str, object]] = []
    for period in selected_periods:
        period_rows: list[dict[str, object]] = []
        period_cohort = cohort[cohort["competencia"].eq(period)]
        for group in groups:
            curated = curation[curation["bank_group"].eq(group)]
            curated_roots = set(curated["cnpj_root8"])
            observed = period_cohort[period_cohort["bank_group"].eq(group)]
            observed_roots = set(observed["cnpj_root8"])
            missing_roots = sorted(curated_roots.difference(observed_roots))
            recovered_official = bool(
                observed["pl_recovered_official"].any()
            ) if not observed.empty else False
            recovery_sources = _join_unique(observed["pl_source_reference"])
            row = {
                "competencia": period,
                "bank_group": group,
                "is_total_5_banks": False,
                "pl_brl": float(observed["pl"].sum(min_count=1))
                if not observed.empty
                else float("nan"),
                "pl_brl_raw": float(observed["pl_brl_raw"].sum(min_count=1))
                if not observed.empty
                else float("nan"),
                "pl_recovered_official": recovered_official,
                "pl_display_suffix": "*" if recovered_official else "",
                "pl_source_references": recovery_sources,
                "fundos_observados": len(observed_roots),
                "fundos_curados": len(curated_roots),
                "cobertura_fundos": len(observed_roots) / len(curated_roots),
                "raizes_cnpj_listadas": ";".join(sorted(curated_roots)),
                "raizes_cnpj_observadas": ";".join(sorted(observed_roots)),
                "raizes_cnpj_nao_observadas": ";".join(missing_roots),
                "cnpjs_nao_observados": ";".join(missing_roots),
                "source_references": _join_unique(
                    [*curated["source_reference"], recovery_sources]
                ),
                "publication_status": (
                    "complete_fixed_cohort"
                    if not missing_roots
                    else "partial_fixed_cohort"
                ),
            }
            rows.append(row)
            period_rows.append(row)

        total_curated = sum(int(row["fundos_curados"]) for row in period_rows)
        total_observed = sum(int(row["fundos_observados"]) for row in period_rows)
        all_missing = sorted(
            root
            for row in period_rows
            for root in str(row["cnpjs_nao_observados"]).split(";")
            if root
        )
        all_listed = sorted(
            root
            for row in period_rows
            for root in str(row["raizes_cnpj_listadas"]).split(";")
            if root
        )
        all_observed = sorted(
            root
            for row in period_rows
            for root in str(row["raizes_cnpj_observadas"]).split(";")
            if root
        )
        rows.append(
            {
                "competencia": period,
                "bank_group": "Total 5 bancos",
                "is_total_5_banks": True,
                "pl_brl": float(
                    sum(
                        float(row["pl_brl"])
                        for row in period_rows
                        if not pd.isna(row["pl_brl"])
                    )
                ),
                "pl_brl_raw": float(
                    sum(
                        float(row["pl_brl_raw"])
                        for row in period_rows
                        if not pd.isna(row["pl_brl_raw"])
                    )
                ),
                "pl_recovered_official": any(
                    bool(row["pl_recovered_official"]) for row in period_rows
                ),
                "pl_display_suffix": (
                    "*"
                    if any(
                        bool(row["pl_recovered_official"])
                        for row in period_rows
                    )
                    else ""
                ),
                "pl_source_references": _join_unique(
                    row["pl_source_references"] for row in period_rows
                ),
                "fundos_observados": total_observed,
                "fundos_curados": total_curated,
                "cobertura_fundos": total_observed / total_curated,
                "raizes_cnpj_listadas": ";".join(all_listed),
                "raizes_cnpj_observadas": ";".join(all_observed),
                "raizes_cnpj_nao_observadas": ";".join(all_missing),
                "cnpjs_nao_observados": ";".join(all_missing),
                "source_references": _join_unique(
                    row["source_references"] for row in period_rows
                ),
                "publication_status": (
                    "complete_fixed_cohort"
                    if total_observed == total_curated
                    else "partial_fixed_cohort"
                ),
            }
        )
    output = pd.DataFrame(rows)
    return output.loc[:, BANK_COHORT_HISTORY_COLUMNS]


def build_fixed_bank_fidc_cohort_detail(
    fund_base: pd.DataFrame,
    bank_fidc_curation: pd.DataFrame,
    *,
    periods: Iterable[str],
) -> pd.DataFrame:
    """Return the fund-level audit trail behind the fixed five-bank cohort."""

    _require_columns(
        fund_base,
        {"competencia", "cnpj_fundo", "denominacao", "pl"},
        label="fund_base",
    )
    curation = _prepare_bank_fidc_curation(bank_fidc_curation)
    curation = curation.drop_duplicates(["bank_group", "cnpj_root8"])

    funds = fund_base.copy()
    funds["competencia"] = funds["competencia"].map(_clean).str[:7]
    funds["cnpj_fundo"] = funds["cnpj_fundo"].map(_cnpj14)
    funds["cnpj_root8"] = funds["cnpj_fundo"].str[:8]
    funds["pl"] = _numeric_series(funds["pl"], label="fund_base.pl")
    funds["denominacao"] = funds["denominacao"].map(_clean)
    duplicated = funds.duplicated(["competencia", "cnpj_fundo"], keep=False)
    if duplicated.any():
        raise ValueError("fund_base duplicada por competência/CNPJ")
    funds = _apply_official_bank_pl_recoveries(funds, curation)
    funds["pl_brl"] = funds["pl"]

    rows: list[dict[str, object]] = []
    for period_value in periods:
        period = _clean(period_value)[:7]
        scoped = funds[funds["competencia"].eq(period)].copy()
        if scoped.empty:
            raise ValueError(f"competência ausente no fund_base: {period}")
        by_root = scoped.sort_values(
            ["pl_brl", "cnpj_fundo"], ascending=[False, True]
        ).drop_duplicates("cnpj_root8")
        by_root = by_root.set_index("cnpj_root8")
        for item in curation.itertuples(index=False):
            observed = item.cnpj_root8 in by_root.index
            fund = by_root.loc[item.cnpj_root8] if observed else None
            pl_value = float(fund["pl_brl"]) if observed else float("nan")
            pl_raw = float(fund["pl_brl_raw"]) if observed else float("nan")
            recovered_official = bool(
                observed and fund["pl_recovered_official"]
            )
            recovery_source = (
                str(fund["pl_source_reference"]) if recovered_official else ""
            )
            rows.append(
                {
                    "competencia": period,
                    "bank_group": item.bank_group,
                    "cnpj_root8": item.cnpj_root8,
                    "cnpj_fundo": str(fund["cnpj_fundo"]) if observed else "",
                    "denominacao": str(fund["denominacao"]) if observed else "não observado",
                    "pl_brl": pl_value,
                    "pl_brl_raw": pl_raw,
                    "pl_recovered_official": recovered_official,
                    "pl_display_suffix": "*" if recovered_official else "",
                    "pl_source_reference": recovery_source,
                    "observado": bool(observed),
                    "pl_reportado_zero": bool(observed and pl_raw == 0),
                    "source_reference": _join_unique(
                        [item.source_reference, recovery_source]
                    ),
                }
            )
    output = pd.DataFrame(rows).sort_values(
        ["competencia", "bank_group", "pl_brl", "cnpj_root8"],
        ascending=[True, True, False, True],
        na_position="last",
    )
    return output.loc[:, BANK_COHORT_DETAIL_COLUMNS].reset_index(drop=True)


def build_acquiring_reclassified_cvm_mix(
    fund_base: pd.DataFrame,
    acquiring_curation: pd.DataFrame,
    *,
    periods: Iterable[str] | None = None,
    category_column: str = "segmento_principal",
    acquiring_label: str = "Adquirência",
    exclude_fic_fidc: bool = True,
    expected_curated_funds: int | None = 16,
) -> pd.DataFrame:
    """Move curated acquiring FIDCs from their CVM bucket to one open bucket.

    The denominator is PL, matching a fund-taxonomy view.  The original CVM
    category is preserved in the output and only the 16 curated fund CNPJs are
    moved.  This function does not alter the reported values of Tabela II.
    """

    _require_columns(
        fund_base,
        {"competencia", "cnpj_fundo", "pl", category_column},
        label="fund_base",
    )
    _require_columns(
        acquiring_curation,
        {"cnpj14_digits", "label", "source_reference"},
        label="acquiring_curation",
    )
    curation = acquiring_curation.copy()
    curation["cnpj14_digits"] = curation["cnpj14_digits"].map(_cnpj14)
    curation["label"] = curation["label"].map(_clean)
    curation["source_reference"] = curation["source_reference"].map(_clean)
    if curation["cnpj14_digits"].eq("").any():
        raise ValueError("acquiring_curation contém CNPJ inválido")
    if curation["cnpj14_digits"].duplicated().any():
        duplicates = curation.loc[
            curation["cnpj14_digits"].duplicated(False), "cnpj14_digits"
        ].unique()
        raise ValueError(f"acquiring_curation contém CNPJs duplicados: {duplicates}")
    if expected_curated_funds is not None and len(curation) != expected_curated_funds:
        raise ValueError(
            "quantidade de FIDCs de adquirência diverge da curadoria esperada: "
            f"esperado={expected_curated_funds}, observado={len(curation)}"
        )

    funds = fund_base.copy()
    funds["competencia"] = funds["competencia"].map(_clean).str[:7]
    funds["cnpj_fundo"] = funds["cnpj_fundo"].map(_cnpj14)
    funds["pl"] = _numeric_series(funds["pl"], label="fund_base.pl")
    funds["categoria_original"] = funds[category_column].map(_clean).replace(
        "", "N/D"
    )
    if funds[["competencia", "cnpj_fundo"]].eq("").any().any():
        raise ValueError("fund_base contém competência ou CNPJ inválido")
    duplicated = funds.duplicated(["competencia", "cnpj_fundo"], keep=False)
    if duplicated.any():
        examples = (
            funds.loc[duplicated, ["competencia", "cnpj_fundo"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"fund_base duplicada por competência/CNPJ: {examples}")
    if exclude_fic_fidc and "is_fic_fidc" in funds:
        fic = _boolean_series(funds["is_fic_fidc"].fillna(False), label="is_fic_fidc")
        funds = funds.loc[~fic].copy()

    available_periods = sorted(funds["competencia"].unique())
    selected_periods = (
        [_clean(value)[:7] for value in periods]
        if periods is not None
        else available_periods
    )
    missing_periods = sorted(set(selected_periods).difference(available_periods))
    if missing_periods:
        raise ValueError(f"competências ausentes no fund_base: {missing_periods}")

    acquiring_cnpjs = set(curation["cnpj14_digits"])
    source_references = _join_unique(curation["source_reference"])
    rows: list[dict[str, object]] = []
    for period in selected_periods:
        scoped = funds[funds["competencia"].eq(period)].copy()
        denominator = float(scoped["pl"].sum(min_count=1))
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError(f"denominador de PL não positivo em {period}")
        scoped["is_acquiring"] = scoped["cnpj_fundo"].isin(acquiring_cnpjs)
        scoped["categoria_reclassificada"] = scoped["categoria_original"].where(
            ~scoped["is_acquiring"], acquiring_label
        )
        observed_cnpjs = set(scoped.loc[scoped["is_acquiring"], "cnpj_fundo"])
        missing_cnpjs = sorted(acquiring_cnpjs.difference(observed_cnpjs))
        moved = scoped[
            scoped["is_acquiring"]
            & scoped["categoria_original"].ne(acquiring_label)
        ].copy()

        original = (
            scoped.groupby("categoria_original", as_index=False)
            .agg(pl_original_brl=("pl", "sum"), fundos_original=("cnpj_fundo", "nunique"))
            .set_index("categoria_original")
        )
        reclassified = (
            scoped.groupby("categoria_reclassificada", as_index=False)
            .agg(
                pl_reclassificado_brl=("pl", "sum"),
                fundos_reclassificados=("cnpj_fundo", "nunique"),
            )
            .set_index("categoria_reclassificada")
        )
        moved_by_source = (
            moved.groupby("categoria_original", as_index=False)
            .agg(
                fundos_movidos_da_categoria=("cnpj_fundo", "nunique"),
                pl_movido_da_categoria_brl=("pl", "sum"),
                cnpjs_movidos_da_categoria=(
                    "cnpj_fundo",
                    lambda values: ";".join(sorted(set(values))),
                ),
            )
            .set_index("categoria_original")
        )
        moved_count = int(moved["cnpj_fundo"].nunique())
        moved_pl = float(moved["pl"].sum())
        moved_cnpjs = ";".join(sorted(set(moved["cnpj_fundo"])))
        categories = sorted(set(original.index).union(reclassified.index))
        period_rows: list[dict[str, object]] = []
        for category in categories:
            original_pl = (
                float(original.at[category, "pl_original_brl"])
                if category in original.index
                else 0.0
            )
            reclassified_pl = (
                float(reclassified.at[category, "pl_reclassificado_brl"])
                if category in reclassified.index
                else 0.0
            )
            moved_source = (
                moved_by_source.loc[category]
                if category in moved_by_source.index
                else None
            )
            period_rows.append(
                {
                    "competencia": period,
                    "categoria_cvm": category,
                    "pl_original_brl": original_pl,
                    "share_original": original_pl / denominator,
                    "pl_reclassificado_brl": reclassified_pl,
                    "share_reclassificado": reclassified_pl / denominator,
                    "delta_pl_brl": reclassified_pl - original_pl,
                    "fundos_original": int(original.at[category, "fundos_original"])
                    if category in original.index
                    else 0,
                    "fundos_reclassificados": int(
                        reclassified.at[category, "fundos_reclassificados"]
                    )
                    if category in reclassified.index
                    else 0,
                    "fundos_movidos_da_categoria": int(
                        moved_source["fundos_movidos_da_categoria"]
                    )
                    if moved_source is not None
                    else 0,
                    "pl_movido_da_categoria_brl": float(
                        moved_source["pl_movido_da_categoria_brl"]
                    )
                    if moved_source is not None
                    else 0.0,
                    "cnpjs_movidos_da_categoria": str(
                        moved_source["cnpjs_movidos_da_categoria"]
                    )
                    if moved_source is not None
                    else "",
                    "fundos_movidos_para_adquirencia": moved_count
                    if category == acquiring_label
                    else 0,
                    "pl_movido_para_adquirencia_brl": moved_pl
                    if category == acquiring_label
                    else 0.0,
                    "cnpjs_movidos_para_adquirencia": moved_cnpjs
                    if category == acquiring_label
                    else "",
                    "fundos_adquirencia_curados": len(acquiring_cnpjs),
                    "fundos_adquirencia_observados": len(observed_cnpjs),
                    "cobertura_cnpjs_curados": len(observed_cnpjs)
                    / len(acquiring_cnpjs),
                    "cnpjs_curados_nao_observados": ";".join(missing_cnpjs),
                    "denominador_pl_brl": denominator,
                    "source_references": source_references,
                }
            )
        ranked = pd.DataFrame(period_rows).sort_values(
            ["pl_reclassificado_brl", "categoria_cvm"],
            ascending=[False, True],
            kind="mergesort",
        )
        ranked["rank_reclassificado"] = range(1, len(ranked) + 1)
        if not math.isclose(
            float(ranked["pl_original_brl"].sum()),
            denominator,
            rel_tol=1e-10,
            abs_tol=0.01,
        ):
            raise ValueError(f"mix original não reconcilia em {period}")
        if not math.isclose(
            float(ranked["pl_reclassificado_brl"].sum()),
            denominator,
            rel_tol=1e-10,
            abs_tol=0.01,
        ):
            raise ValueError(f"mix reclassificado não reconcilia em {period}")
        rows.extend(ranked.to_dict("records"))

    output = pd.DataFrame(rows)
    output["rank_reclassificado"] = output["rank_reclassificado"].astype("Int64")
    return output.loc[:, ACQUIRING_RECLASSIFIED_MIX_COLUMNS]


__all__ = [
    "ACQUIRING_RECLASSIFIED_MIX_COLUMNS",
    "BANK_COHORT_HISTORY_COLUMNS",
    "BANK_COHORT_DETAIL_COLUMNS",
    "DEFAULT_BANK_GROUPS",
    "INDEPENDENT_PROVIDER_HISTORY_COLUMNS",
    "build_acquiring_reclassified_cvm_mix",
    "build_fixed_bank_fidc_cohort_history",
    "build_fixed_bank_fidc_cohort_detail",
    "build_independent_provider_historical_ranking",
]
