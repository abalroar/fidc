"""Curated correction of the FIC-FIDC perimeter.

The upstream industry builder initializes ``is_fic_fidc`` as a legacy nominal
signal derived locally from the registered corporate name.  No dedicated
official FIC flag was identified in the CVM layouts used by this pipeline.  A
fund selected by the perimeter leaves the four ANBIMA types and only feeds the
FIC net-asset balance.

Some vehicles registered as FIDC never buy a receivable and hold quotas of
other FIDCs.  This module writes the quantitative confirmations produced by
``scripts/build_fidc_fic_perimeter_review.py`` into the same perimeter column.

The correction only ever turns the indicator **on**.  A fund already selected
by the upstream local signal is never turned back into a direct FIDC by this
layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from services.industry_taxonomy_review import normalize_cnpj


OVERRIDES_FILENAME = "fic_perimeter_overrides.csv"

OVERRIDE_COLUMNS: tuple[str, ...] = (
    "cnpj_fundo",
    "denominacao",
    "is_fic_fidc",
    "evidencia",
    "fonte",
    "revisado_em_utc",
)


@dataclass(frozen=True)
class PerimeterCorrection:
    """What the correction changed, for the manifest and the audit trail.

    ``pl_moved_brl`` adds up every month-row touched, so it is a flow over the
    whole series, not a balance.  The figure that answers "how much net assets
    left the four ANBIMA types" is ``pl_moved_last_competence_brl`` — a stock,
    measured in the most recent competence the correction reached.
    """

    cnpj_count: int
    rows_changed: int
    pl_moved_brl: float
    competences: tuple[str, ...]
    pl_moved_last_competence_brl: float = 0.0
    last_competence: str = ""


def load_fic_perimeter_overrides(data_dir: Path) -> pd.DataFrame:
    """Read the curated corrections, or an empty frame when none exist."""

    path = Path(data_dir) / OVERRIDES_FILENAME
    if not path.exists():
        return pd.DataFrame(columns=list(OVERRIDE_COLUMNS))
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in OVERRIDE_COLUMNS:
        if column not in frame:
            frame[column] = ""
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame = frame[frame["cnpj_fundo"].str.len().eq(14)]
    frame = frame[
        frame["is_fic_fidc"].astype(str).str.strip().str.casefold().isin({"true", "1", "sim"})
    ]
    return frame.drop_duplicates("cnpj_fundo", keep="last").reset_index(drop=True)


def apply_fic_perimeter_overrides(
    frame: pd.DataFrame,
    overrides: pd.DataFrame,
    *,
    cnpj_column: str = "cnpj",
    flag_column: str = "is_fic_fidc",
    pl_column: str = "pl",
    competence_column: str = "competencia",
) -> tuple[pd.DataFrame, PerimeterCorrection]:
    """Turn the FIC perimeter indicator on for every curated CNPJ."""

    if frame is None or frame.empty or overrides.empty:
        return (
            frame if frame is not None else pd.DataFrame(),
            PerimeterCorrection(0, 0, 0.0, ()),
        )
    if cnpj_column not in frame.columns or flag_column not in frame.columns:
        return frame, PerimeterCorrection(0, 0, 0.0, ())

    corrected = frame.copy()
    keys = corrected[cnpj_column].map(normalize_cnpj)
    targets = set(overrides["cnpj_fundo"].map(normalize_cnpj))
    current = (
        corrected[flag_column]
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "sim"})
    )
    changing = keys.isin(targets) & ~current
    if not bool(changing.any()):
        return corrected, PerimeterCorrection(0, 0, 0.0, ())

    corrected.loc[changing, flag_column] = True
    moved = 0.0
    if pl_column in corrected.columns:
        moved = float(
            pd.to_numeric(corrected.loc[changing, pl_column], errors="coerce")
            .fillna(0.0)
            .sum()
        )
    competences: tuple[str, ...] = ()
    last_competence = ""
    moved_last = 0.0
    if competence_column in corrected.columns:
        competences = tuple(
            sorted(corrected.loc[changing, competence_column].astype(str).unique())
        )
        if competences:
            last_competence = competences[-1]
            if pl_column in corrected.columns:
                final = changing & corrected[competence_column].astype(str).eq(
                    last_competence
                )
                moved_last = float(
                    pd.to_numeric(corrected.loc[final, pl_column], errors="coerce")
                    .fillna(0.0)
                    .sum()
                )
    return corrected, PerimeterCorrection(
        cnpj_count=int(keys[changing].nunique()),
        rows_changed=int(changing.sum()),
        pl_moved_brl=moved,
        competences=competences,
        pl_moved_last_competence_brl=moved_last,
        last_competence=last_competence,
    )
