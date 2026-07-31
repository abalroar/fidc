"""Break FIDC issuance down by the curated ANBIMA taxonomy, year by year.

The panel already answers "how much was issued" per year and "what the industry
holds" per ANBIMA type.  It did not answer the two together — which sectors the
money went into — because nothing joined the closed-offer cohort to the fund
taxonomy.  This module is that join, and it deliberately reuses the display
rule of the *Escala e taxonomia* tab so the two readings of the same taxonomy
cannot drift apart:

* a fund the FIC gate flags leaves the four types.  A feeder raising money to
  buy quotas of a master that also raised would otherwise be counted twice, the
  same double count the exclusion exists to prevent — so its volume is reported
  on a reconciliation line rather than inside a sector;
* everything else resolves to the curated type, and whatever the curation could
  not name — no ANBIMA type, an ``FIC-FIDC`` label without the flag, an issuer
  the monthly base never saw — folds into ``Outros``, exactly as the tab folds
  ``N/D`` into ``Outros``.  How much of ``Outros`` arrived that way is measured
  and published instead of being left implicit.

2023 is the one year whose composition cannot be read off the CVM registry
alone: it captures R$ 26,5 bi of the R$ 43,7 bi ANBIMA closes, because 2023 was
the first year of Resolução CVM 160.  The unobserved share is distributed with
the composition of what *was* observed, which is an assumption, so it is
applied as an explicit scale factor and reported as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from services.industry_taxonomy_review import (
    apply_taxonomy_review_overlay,
    load_taxonomy_review_actions,
    normalize_cnpj,
)

COHORT_FILENAME = "industry_closed_offer_ticket_cohort.csv.gz"
FUND_BASE_RELATIVE = Path("generated_revision") / "base_fundo_cnpj.csv.gz"
VEHICLE_FILENAME = "vehicle_monthly.csv.gz"
LEDGER_FILENAME = "taxonomy_review_actions.csv"
ANBIMA_OFFERS_FILENAME = "industry_anbima_market_offers.csv"
OUTPUT_FILENAME = "industry_issuance_taxonomy_delta.csv"

#: As quatro categorias exibidas, na ordem da aba Escala e taxonomia.
DISPLAY_CATEGORIES: tuple[str, ...] = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    "Outros",
)

#: Categorias nomeadas; qualquer outra coisa cai em ``Outros``, como na aba.
NAMED_CATEGORIES = frozenset(DISPLAY_CATEGORIES[:-1])

FIC_RECONCILIATION_LABEL = "FIC-FIDC (fundos de cotas — fora dos quatro tipos)"

PERIODS: tuple[dict[str, Any], ...] = (
    {"key": "2023", "label": "2023", "year": 2023, "months": 12, "anbima_scaled": True},
    {"key": "2024", "label": "2024", "year": 2024, "months": 12, "anbima_scaled": False},
    {"key": "2025", "label": "2025", "year": 2025, "months": 12, "anbima_scaled": False},
    {
        "key": "jun25",
        "label": "jan–jun/25",
        "year": 2025,
        "months": 6,
        "anbima_scaled": False,
    },
    {
        "key": "jun26",
        "label": "jan–jun/26",
        "year": 2026,
        "months": 6,
        "anbima_scaled": False,
    },
)

#: Comparações publicadas.  jan–jun/26 é comparado a jan–jun/25 porque 2026
#: ainda não fechou: confrontá-lo com o ano cheio de 2025 mediria o calendário,
#: não o mercado.
DELTAS: tuple[tuple[str, str], ...] = (
    ("2023", "2024"),
    ("2024", "2025"),
    ("jun25", "jun26"),
)

_TRUE_VALUES = {"true", "1", "sim", "t", "yes"}


class IssuanceTaxonomyError(RuntimeError):
    """Raised when the decomposition cannot be built from the sources."""


@dataclass(frozen=True)
class CoverageAudit:
    """How much of each period rests on a positive classification.

    ``unresolved_*`` counts the issuers no base could name at all — they raised
    money and never filed a monthly report, so no curation could reach them.
    They land in ``Outros`` by the same rule as ``N/D`` and this is the measure
    of what that costs.
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    unresolved_cnpjs: tuple[str, ...] = ()

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _truthy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.casefold().isin(_TRUE_VALUES)


def _load_taxonomy_photo(data_dir: Path) -> pd.DataFrame:
    """One row per fund: the latest snapshot under the analytical overlay."""

    base = pd.read_csv(
        data_dir / FUND_BASE_RELATIVE,
        usecols=[
            "competencia",
            "cnpj_fundo",
            "cnpj_classe",
            "anbima_tipo",
            "anbima_foco",
            "is_fic_fidc",
        ],
        low_memory=False,
    )
    for column in ("cnpj_fundo", "cnpj_classe"):
        base[column] = base[column].astype(str).map(normalize_cnpj)
    photo = base.sort_values("competencia").drop_duplicates("cnpj_fundo", keep="last")
    actions = load_taxonomy_review_actions(data_dir / LEDGER_FILENAME)
    return apply_taxonomy_review_overlay(photo.copy(), actions)


def _resolve_issuers(cohort: pd.DataFrame, photo: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """Attach the curated type to every offer, saying how each match was made.

    An offer is registered by whoever issues, and under Resolução CVM 175 that
    can be the class rather than the fund, so matching on the fund CNPJ alone
    loses issuers that the base does carry.  The chain tries the fund, then the
    class, and finally the reporting vehicle — the last only to learn whether
    the FIC gate flags it, which is enough to keep it out of the four types.
    """

    by_fund = photo.set_index("cnpj_fundo")
    by_class = (
        photo[photo["cnpj_classe"].str.len().eq(14)]
        .drop_duplicates("cnpj_classe", keep="last")
        .set_index("cnpj_classe")
    )
    columns = ["anbima_tipo_curado", "anbima_foco_curado", "is_fic_fidc"]

    resolved = cohort.merge(
        by_fund[columns], left_on="cnpj_n", right_index=True, how="left"
    )
    resolved["match"] = resolved["anbima_tipo_curado"].notna().map(
        {True: "cnpj_fundo", False: ""}
    )
    missing = resolved["match"].eq("")
    if missing.any():
        fallback = resolved.loc[missing, "cnpj_n"].map(
            lambda cnpj: by_class[columns].loc[cnpj].to_dict()
            if cnpj in by_class.index
            else None
        )
        for index, values in fallback.items():
            if not values:
                continue
            for column in columns:
                resolved.at[index, column] = values[column]
            resolved.at[index, "match"] = "cnpj_classe"

    still_missing = resolved["match"].eq("")
    if still_missing.any():
        vehicle = pd.read_csv(
            data_dir / VEHICLE_FILENAME, usecols=["cnpj", "is_fic_fidc"], low_memory=False
        )
        vehicle["cnpj_n"] = vehicle["cnpj"].astype(str).map(normalize_cnpj)
        flags = (
            vehicle.assign(flag=_truthy(vehicle["is_fic_fidc"]))
            .groupby("cnpj_n")["flag"]
            .max()
        )
        for index in resolved.index[still_missing]:
            cnpj = resolved.at[index, "cnpj_n"]
            if cnpj in flags.index:
                resolved.at[index, "is_fic_fidc"] = bool(flags.loc[cnpj])
                resolved.at[index, "match"] = "vehicle_monthly"
    return resolved


def _display_category(row: pd.Series) -> str:
    """Apply the tab's rule: named type, or ``Outros`` for everything else."""

    curated = str(row.get("anbima_tipo_curado") or "").strip()
    return curated if curated in NAMED_CATEGORIES else "Outros"


def _period_slice(offers: pd.DataFrame, period: dict[str, Any]) -> pd.DataFrame:
    scoped = offers[offers["ano"].eq(period["year"])]
    if period["months"] < 12:
        scoped = scoped[scoped["mes"].le(period["months"])]
    return scoped


def build_issuance_taxonomy(data_dir: Path) -> tuple[pd.DataFrame, CoverageAudit]:
    """Return the long-form decomposition and the audit of what it rests on."""

    data_dir = Path(data_dir)
    cohort = pd.read_csv(data_dir / COHORT_FILENAME, low_memory=False)
    cohort["cnpj_n"] = cohort["cnpj_emissor"].astype(str).map(normalize_cnpj)
    cohort["registered_volume_brl"] = pd.to_numeric(
        cohort["registered_volume_brl"], errors="coerce"
    ).fillna(0.0)
    closing = pd.to_datetime(cohort["data_encerramento"], errors="coerce")
    cohort["ano"] = closing.dt.year
    cohort["mes"] = closing.dt.month
    if closing.isna().any():
        raise IssuanceTaxonomyError(
            "coorte de ofertas com data de encerramento ausente; o recorte por "
            "período não pode ser construído"
        )

    photo = _load_taxonomy_photo(data_dir)
    offers = _resolve_issuers(cohort, photo, data_dir)
    offers["is_fic"] = _truthy(offers["is_fic_fidc"].fillna(False))
    offers["categoria"] = offers.apply(_display_category, axis=1)

    anbima = pd.read_csv(data_dir / ANBIMA_OFFERS_FILENAME)
    anbima_2023 = anbima[
        anbima["instrument_label"].eq("FIDCs") & anbima["period_label"].eq("2023 FY")
    ]
    if len(anbima_2023) != 1:
        raise IssuanceTaxonomyError(
            "snapshot ANBIMA sem a observação de FIDCs em 2023 FY; o nível do "
            "ano não pode ser corrigido"
        )
    anbima_2023_brl = float(anbima_2023["closed_volume_brl"].iloc[0])

    records: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    unresolved: set[str] = set()

    for period in PERIODS:
        scoped = _period_slice(offers, period)
        observed = float(scoped["registered_volume_brl"].sum())
        if observed <= 0:
            raise IssuanceTaxonomyError(
                f"período {period['label']} sem volume observado na coorte"
            )
        scale = 1.0
        if period["anbima_scaled"]:
            # O não observado recebe a composição do observado. É hipótese, e
            # por isso vira um fator explícito em vez de sumir na conta.
            scale = anbima_2023_brl / observed

        eligible = scoped[~scoped["is_fic"]]
        fic_volume = float(scoped.loc[scoped["is_fic"], "registered_volume_brl"].sum())
        by_category = (
            eligible.groupby("categoria")["registered_volume_brl"]
            .sum()
            .reindex(DISPLAY_CATEGORIES, fill_value=0.0)
            * scale
        )
        total = float(by_category.sum())
        for categoria, volume in by_category.items():
            records.append(
                {
                    "period_key": period["key"],
                    "period_label": period["label"],
                    "categoria": categoria,
                    "volume_brl": float(volume),
                    "share": float(volume) / total if total else 0.0,
                }
            )

        # ``Outros`` é classificação legítima da ANBIMA, não ausência dela: o
        # fallback são apenas os fundos que a curadoria não conseguiu nomear em
        # nenhuma das quatro categorias e que a regra da aba manda para Outros.
        fallback = eligible[
            ~eligible["anbima_tipo_curado"].fillna("").isin(DISPLAY_CATEGORIES)
        ]
        unresolved.update(
            eligible.loc[eligible["match"].eq(""), "cnpj_n"].astype(str)
        )
        audit_rows.append(
            {
                "period_key": period["key"],
                "period_label": period["label"],
                "observed_brl": observed,
                "scale_factor": scale,
                "total_brl": total,
                "fic_excluded_brl": fic_volume * scale,
                "fic_excluded_offers": int(scoped["is_fic"].sum()),
                "outros_from_fallback_brl": float(
                    fallback["registered_volume_brl"].sum() * scale
                ),
                "outros_from_fallback_share": (
                    float(fallback["registered_volume_brl"].sum() * scale) / total
                    if total
                    else 0.0
                ),
                "unresolved_issuer_brl": float(
                    eligible.loc[eligible["match"].eq(""), "registered_volume_brl"].sum()
                    * scale
                ),
                "unresolved_issuers": int(
                    eligible.loc[eligible["match"].eq(""), "cnpj_n"].nunique()
                ),
                "classified_share": (
                    1.0
                    - (
                        float(fallback["registered_volume_brl"].sum() * scale) / total
                        if total
                        else 0.0
                    )
                ),
            }
        )

    frame = pd.DataFrame(records)
    return frame, CoverageAudit(rows=audit_rows, unresolved_cnpjs=tuple(sorted(unresolved)))


def build_wide_table(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Pivot into the delivery shape: value and share per period, plus deltas."""

    table = pd.DataFrame({"Categoria": list(DISPLAY_CATEGORIES)})
    values = long_frame.pivot(
        index="categoria", columns="period_key", values="volume_brl"
    ).reindex(DISPLAY_CATEGORIES)
    shares = long_frame.pivot(
        index="categoria", columns="period_key", values="share"
    ).reindex(DISPLAY_CATEGORIES)
    labels = {period["key"]: period["label"] for period in PERIODS}

    # O delta é emitido depois do período que o fecha, não do que o abre: a
    # coluna tem de ser lida logo após os dois valores que ela compara.
    delta_after = {end: (start, end) for start, end in DELTAS}
    for period in PERIODS:
        key, label = period["key"], period["label"]
        table[f"{label} (R$ bi)"] = (values[key] / 1e9).to_numpy()
        table[f"{label} (%)"] = shares[key].to_numpy()
        if key in delta_after:
            start, end = delta_after[key]
            table[
                f"Delta {labels[start]}→{labels[end]} (R$ bi)"
            ] = ((values[end] - values[start]) / 1e9).to_numpy()
    return table


def validate_issuance_taxonomy(frame: pd.DataFrame) -> pd.DataFrame:
    """Fail on a decomposition that cannot be read as complete."""

    expected = {period["key"] for period in PERIODS}
    if set(frame["period_key"]) != expected:
        raise IssuanceTaxonomyError("decomposição com períodos inesperados")
    if len(frame) != len(expected) * len(DISPLAY_CATEGORIES):
        raise IssuanceTaxonomyError(
            f"decomposição deveria conter {len(expected) * len(DISPLAY_CATEGORIES)} "
            f"linhas; contém {len(frame)}"
        )
    for key, group in frame.groupby("period_key"):
        total = float(group["share"].sum())
        if abs(total - 1.0) > 1e-6:
            raise IssuanceTaxonomyError(
                f"participações de {key} somam {total:.6f} em vez de 1"
            )
        if (group["volume_brl"] < 0).any():
            raise IssuanceTaxonomyError(f"volume negativo em {key}")
    return frame


def write_issuance_taxonomy(frame: pd.DataFrame, data_dir: Path) -> Path:
    path = Path(data_dir) / OUTPUT_FILENAME
    validate_issuance_taxonomy(frame).to_csv(path, index=False)
    return path


def load_issuance_taxonomy(data_dir: Path) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"decomposição de emissões ausente: {path}")
    return validate_issuance_taxonomy(pd.read_csv(path))


__all__ = [
    "DELTAS",
    "DISPLAY_CATEGORIES",
    "FIC_RECONCILIATION_LABEL",
    "OUTPUT_FILENAME",
    "PERIODS",
    "CoverageAudit",
    "IssuanceTaxonomyError",
    "build_issuance_taxonomy",
    "build_wide_table",
    "load_issuance_taxonomy",
    "validate_issuance_taxonomy",
    "write_issuance_taxonomy",
]
