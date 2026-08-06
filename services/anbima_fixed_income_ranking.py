"""Official ANBIMA fixed-income/hybrid ranking and its deal-by-deal annex.

ANBIMA publishes two workbooks per reference month for the *Ranking de Renda
Fixa e Híbridos*:

* the ranking itself (``Ranking de Renda Fixa e Híbridos - <mês> <ano>.xlsx``),
  with one block per ranking type and three accumulation windows; and
* the closing annex (``Anexo ao Ranking - Encerramento ...xlsx``), which lists
  **one row per (operation, coordinator)** together with the contractual share
  credited to that coordinator.

The annex is what makes the ranking auditable: the CVM open-data archive only
publishes ``Nome_Lider``/``CNPJ_Lider`` (the lead coordinator), so the full
syndicate — and the split among its members — is not derivable from CVM alone.
Summing the annex reproduces the published ranking exactly.

Both workbooks state monetary values in **R$ thousands**; this module converts
them to BRL so downstream code never has to remember the unit.
"""

from __future__ import annotations

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
import re
import unicodedata

import pandas as pd


PUBLICATION_API = (
    "https://data-strapi.prd.anbima.com.br/api/"
    "publicacao-ranking-de-renda-fixa-e-hibridos"
)
PUBLICATION_PAGE = (
    "https://data.anbima.com.br/publicacoes/ranking-de-renda-fixa-e-hibridos"
)
METHODOLOGY_URL = (
    "https://data-strapi.prd.anbima.com.br/uploads/"
    "Metodologia_RF_Hib_2026_2_b892ba3858.pdf"
)

#: Values in both workbooks are expressed in R$ thousands.
VALUE_UNIT_MULTIPLIER = 1_000.0

RANKING_SHEETS: dict[str, str] = {
    "Originação - Valor": "originacao_valor",
    "Nº de Operações": "originacao_numero_operacoes",
    "Distribuição": "distribuicao_valor",
}

ANNEX_SHEETS: dict[str, str] = {
    "RF&Híbridos - Originação": "originacao",
    "RF&Híbridos - Distribuição": "distribuicao",
}

ANNEX_COLUMNS: tuple[str, ...] = (
    "data_encerramento",
    "data_registro_cvm",
    "registro_cvm",
    "classe",
    "regime_colocacao",
    "emissor",
    "participante",
    "pu_emissao_brl",
    "quantidade",
    "valor_mil_brl",
    "percentual_participacao",
    "risco_securitizacao",
    "cnpj_emissor",
)

#: Asset classes as defined in Chapter II of the ANBIMA methodology (2026).
CLASS_LABELS: dict[str, str] = {
    "1.1.A": "Debêntures simples — curto prazo",
    "1.1.B": "Notas promissórias — curto prazo",
    "1.1.C": "Valor mobiliário de agência multilateral — curto prazo",
    "1.1.D": "Notas comerciais — curto prazo",
    "1.1.E": "CPR-F — curto prazo",
    "1.2.A": "Debêntures simples — longo prazo",
    "1.2.B": "Notas promissórias — longo prazo",
    "1.2.C": "Valor mobiliário de agência multilateral — longo prazo",
    "1.2.D": "Notas comerciais — longo prazo",
    "1.2.E": "CPR-F — longo prazo",
    "1.3.1": "FIDC — cotas seniores e subordinadas",
    "1.3.2": "CRI",
    "1.3.3": "CRA",
    "1.3.4": "CR",
    "2.1.A": "Debêntures conversíveis em ações",
    "2.1.B": "Debêntures permutáveis em ações",
    "2.2": "Fundo de Investimento Imobiliário",
    "2.3": "CEPAC",
    "2.4": "FIP-IE",
    "2.5": "FIAGRO",
}

FIDC_CLASS = "1.3.1"
FIXED_INCOME_BLOCK = "Tipo 1"
HYBRID_BLOCK = "Tipo 2"
RELATED_PARTY_BLOCK = "Tipo 3"

_BLOCK_PATTERN = re.compile(r"^Tipo\s+(\d+(?:\.\d+)*)\s*[:.]?\s*(.*)$")
_RANK_PATTERN = re.compile(r"^(\d+)")


class AnbimaRankingError(ValueError):
    """Raised when a workbook does not match the expected ANBIMA layout."""


def workbook_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: object) -> str:
    # Empty spreadsheet cells surface as ``None``, ``nan`` or ``NaT`` depending
    # on the inferred column dtype; all three mean "no value".
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return ""
    return " ".join(str(value).split())


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.upper()


def _numeric(value: object) -> float:
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def _rank(value: object) -> float:
    match = _RANK_PATTERN.match(_text(value))
    return float(match.group(1)) if match else float("nan")


_PARTICIPANT_COLUMN = ANNEX_COLUMNS.index("participante")


def _is_annex_data_row(row: tuple[object, ...]) -> bool:
    if len(row) <= _PARTICIPANT_COLUMN:
        return False
    closing = _text(row[0])
    if not closing or pd.isna(pd.to_datetime(closing, errors="coerce", dayfirst=True)):
        return False
    return bool(_text(row[_PARTICIPANT_COLUMN]))


def _load_rows(path: str | Path, sheet: str) -> list[tuple[object, ...]]:
    frame = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
    return [tuple(row) for row in frame.itertuples(index=False, name=None)]


def _iter_blocks(
    rows: list[tuple[object, ...]],
) -> Iterator[tuple[str, str, int, int]]:
    """Yield ``(block_code, block_label, first_row, last_row)`` per section."""

    starts: list[tuple[int, str, str]] = []
    for index, row in enumerate(rows):
        match = _BLOCK_PATTERN.match(_text(row[0] if row else ""))
        if match:
            starts.append((index, match.group(1), _text(match.group(2))))
    for position, (index, code, label) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(rows)
        yield code, label, index, end


def parse_ranking_workbook(path: str | Path) -> pd.DataFrame:
    """Return the published ranking as one row per participant and window."""

    path = Path(path)
    available = set(pd.ExcelFile(path).sheet_names)
    missing = sorted(set(RANKING_SHEETS).difference(available))
    if missing:
        raise AnbimaRankingError(
            "Planilha de ranking ANBIMA sem abas: " + ", ".join(missing)
        )

    records: list[dict[str, object]] = []
    for sheet, measure in RANKING_SHEETS.items():
        rows = _load_rows(path, sheet)
        is_value = measure != "originacao_numero_operacoes"
        # Value sheets repeat (rank, value, share) per window; the operation
        # count sheet drops the share column.
        windows = (
            (
                ("acumulado_ano", 1, 2, 3),
                ("ultimos_3_meses", 4, 5, 6),
                ("ultimos_12_meses", 7, 8, 9),
            )
            if is_value
            else (
                ("acumulado_ano", 1, 2, None),
                ("ultimos_3_meses", 3, 4, None),
                ("ultimos_12_meses", 5, 6, None),
            )
        )
        for code, label, start, end in _iter_blocks(rows):
            for row in rows[start + 3 : end]:
                participant = _text(row[0] if row else "")
                if not participant or _normalize(participant) == "TOTAL":
                    continue
                for window, rank_col, value_col, share_col in windows:
                    value = _numeric(row[value_col] if len(row) > value_col else None)
                    rank = _rank(row[rank_col] if len(row) > rank_col else None)
                    if pd.isna(value) and pd.isna(rank):
                        continue
                    share = (
                        _numeric(row[share_col])
                        if share_col is not None and len(row) > share_col
                        else float("nan")
                    )
                    records.append(
                        {
                            "measure": measure,
                            "ranking_code": code,
                            "ranking_label": label,
                            "window": window,
                            "participant": participant,
                            "rank": rank,
                            "value": (
                                float(value) * VALUE_UNIT_MULTIPLIER
                                if is_value and pd.notna(value)
                                else value
                            ),
                            "share": share,
                        }
                    )

    frame = pd.DataFrame(records)
    if frame.empty:
        raise AnbimaRankingError("Nenhum bloco de ranking reconhecido na planilha.")
    frame = frame.rename(columns={"value": "value_brl_or_count"})
    return frame.sort_values(
        ["measure", "ranking_code", "window", "rank", "participant"],
        na_position="last",
    ).reset_index(drop=True)


def parse_ranking_totals(path: str | Path) -> pd.DataFrame:
    """Return the published ``Total`` row of each ranking block.

    The per-participant operation counts do not add up to the number of
    operations — a syndicated deal credits one unit to every coordinator — so
    the published total is the only correct source for "how many operations
    happened in this segment".
    """

    path = Path(path)
    available = set(pd.ExcelFile(path).sheet_names)
    records: list[dict[str, object]] = []
    for sheet, measure in RANKING_SHEETS.items():
        if sheet not in available:
            continue
        is_value = measure != "originacao_numero_operacoes"
        windows = (
            (("acumulado_ano", 2), ("ultimos_3_meses", 5), ("ultimos_12_meses", 8))
            if is_value
            else (
                ("acumulado_ano", 2),
                ("ultimos_3_meses", 4),
                ("ultimos_12_meses", 6),
            )
        )
        rows = _load_rows(path, sheet)
        for code, label, start, end in _iter_blocks(rows):
            for row in rows[start + 3 : end]:
                if _normalize(row[0] if row else "") != "TOTAL":
                    continue
                for window, column in windows:
                    value = _numeric(row[column] if len(row) > column else None)
                    if pd.isna(value):
                        continue
                    records.append(
                        {
                            "measure": measure,
                            "ranking_code": code,
                            "ranking_label": label,
                            "window": window,
                            "total": (
                                float(value) * VALUE_UNIT_MULTIPLIER
                                if is_value
                                else float(value)
                            ),
                        }
                    )
                break
    return pd.DataFrame(records)


def parse_annex_workbook(path: str | Path) -> pd.DataFrame:
    """Return the closing annex as one row per operation and coordinator."""

    path = Path(path)
    available = set(pd.ExcelFile(path).sheet_names)
    missing = sorted(set(ANNEX_SHEETS).difference(available))
    if missing:
        raise AnbimaRankingError(
            "Anexo ANBIMA sem abas: " + ", ".join(missing)
        )

    frames: list[pd.DataFrame] = []
    for sheet, role in ANNEX_SHEETS.items():
        rows = _load_rows(path, sheet)
        for code, label, start, end in _iter_blocks(rows):
            # The last block is followed by an "*Classes de Ativos" legend whose
            # lines also sit in column A; a data row is only a row that carries
            # both a closing date and a coordinator.
            payload = [
                row[: len(ANNEX_COLUMNS)]
                for row in rows[start + 3 : end]
                if _is_annex_data_row(row)
            ]
            if not payload:
                continue
            block = pd.DataFrame(payload, columns=list(ANNEX_COLUMNS))
            block["role"] = role
            block["block_code"] = code
            block["block_label"] = label
            frames.append(block)

    if not frames:
        raise AnbimaRankingError("Nenhuma operação reconhecida no anexo ANBIMA.")

    annex = pd.concat(frames, ignore_index=True)
    for column in ("registro_cvm", "classe", "regime_colocacao", "emissor",
                   "participante", "risco_securitizacao"):
        annex[column] = annex[column].map(_text)
    annex["cnpj_emissor"] = (
        annex["cnpj_emissor"].map(lambda v: re.sub(r"\D", "", _text(v)).zfill(14))
    )
    for column in ("data_encerramento", "data_registro_cvm"):
        annex[column] = pd.to_datetime(
            annex[column], errors="coerce", dayfirst=True, format="mixed"
        )
    for column in ("pu_emissao_brl", "quantidade", "valor_mil_brl",
                   "percentual_participacao"):
        annex[column] = pd.to_numeric(annex[column], errors="coerce")

    annex["valor_brl"] = annex["valor_mil_brl"] * VALUE_UNIT_MULTIPLIER
    annex["classe_label"] = annex["classe"].map(CLASS_LABELS).fillna("")
    annex["block_name"] = "Tipo " + annex["block_code"]
    # ANBIMA credits one unit per *operation*, and a single operation may carry
    # several CVM registrations (one per series/class of the same issuance).
    # Issuer + closing date is the grain that reproduces the published counts.
    annex["operation_key"] = (
        annex["cnpj_emissor"]
        + ":"
        + annex["data_encerramento"].dt.strftime("%Y-%m-%d").fillna("")
    )
    annex = annex.drop(columns=["valor_mil_brl"])
    return annex.sort_values(
        ["role", "block_code", "data_encerramento", "registro_cvm", "participante"]
    ).reset_index(drop=True)


def summarize_participants(
    annex: pd.DataFrame,
    *,
    role: str = "originacao",
    block_code: str = "1",
    classes: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Aggregate annex rows into a ranking-shaped participant summary."""

    selected = annex[annex["role"].eq(role) & annex["block_code"].eq(block_code)]
    if classes is not None:
        selected = selected[selected["classe"].isin(classes)]
    if selected.empty:
        return pd.DataFrame(
            columns=[
                "participant",
                "volume_brl",
                "share",
                "operations",
                "rank",
            ]
        )

    grouped = selected.groupby("participante", sort=False)
    summary = pd.DataFrame(
        {
            "volume_brl": grouped["valor_brl"].sum(),
            "operations": grouped["operation_key"].nunique(),
            "registrations": grouped["registro_cvm"].nunique(),
        }
    ).reset_index(names="participant")
    total = float(summary["volume_brl"].sum())
    summary["share"] = summary["volume_brl"] / total if total else float("nan")
    summary = summary.sort_values(
        ["volume_brl", "participant"], ascending=[False, True]
    ).reset_index(drop=True)
    summary["rank"] = summary["volume_brl"].rank(ascending=False, method="min")
    summary["universe_volume_brl"] = total
    summary["universe_operations"] = int(selected["operation_key"].nunique())
    return summary


def syndication_profile(
    annex: pd.DataFrame,
    *,
    role: str = "originacao",
    block_code: str = "1",
    classes: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Distribution of operations by number of coordinators in the syndicate."""

    selected = annex[annex["role"].eq(role) & annex["block_code"].eq(block_code)]
    if classes is not None:
        selected = selected[selected["classe"].isin(classes)]
    if selected.empty:
        return pd.DataFrame(columns=["coordinators", "operations", "volume_brl"])

    per_operation = selected.groupby("operation_key").agg(
        coordinators=("participante", "nunique"),
        volume_brl=("valor_brl", "sum"),
    )
    profile = per_operation.groupby("coordinators").agg(
        operations=("volume_brl", "size"),
        volume_brl=("volume_brl", "sum"),
    ).reset_index()
    total_operations = int(profile["operations"].sum())
    profile["share_of_operations"] = profile["operations"] / total_operations
    return profile.sort_values("coordinators").reset_index(drop=True)


__all__ = [
    "ANNEX_COLUMNS",
    "ANNEX_SHEETS",
    "AnbimaRankingError",
    "CLASS_LABELS",
    "FIDC_CLASS",
    "FIXED_INCOME_BLOCK",
    "HYBRID_BLOCK",
    "METHODOLOGY_URL",
    "PUBLICATION_API",
    "PUBLICATION_PAGE",
    "RANKING_SHEETS",
    "RELATED_PARTY_BLOCK",
    "VALUE_UNIT_MULTIPLIER",
    "parse_annex_workbook",
    "parse_ranking_totals",
    "parse_ranking_workbook",
    "summarize_participants",
    "syndication_profile",
    "workbook_sha256",
]
