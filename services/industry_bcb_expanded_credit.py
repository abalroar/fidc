"""BCB expanded-credit stock reconciled with the CVM FIDC receivables book."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import requests


OUTPUT_FILENAME = "industry_bcb_expanded_credit.csv"
BCB_API = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
BCB_METADATA_URL = (
    "https://www.bcb.gov.br/content/publicacoes/Documents/reb/"
    "boxesreb2018/boxe3.pdf"
)
BCB_SERIES = {
    "expanded_credit_total": 28183,
    "loans": 28184,
    "loans_sfn": 28185,
    "loans_other_finance": 28186,
    "loans_government_funds": 28187,
    "debt_securities": 28188,
    "public_debt": 28189,
    "private_debt": 28190,
    "securitization": 28191,
    "external_debt": 28192,
}
OUTPUT_COLUMNS = (
    "period_order",
    "competencia",
    "period_label",
    "is_latest",
    "expanded_credit_total_brl",
    "private_expanded_credit_total_brl",
    "loans_brl",
    "public_debt_brl",
    "private_debt_brl",
    "fidc_receivables_brl",
    "other_securitization_brl",
    "external_debt_brl",
    "debt_securities_brl",
    "securitization_brl",
    "bcb_total_reconciliation_brl",
    "bcb_debt_reconciliation_brl",
    "bcb_loans_reconciliation_brl",
    "source_bcb",
    "source_cvm",
    "methodology",
)


class ExpandedCreditError(ValueError):
    """Raised when the BCB identities or the CVM bridge do not reconcile."""


def _download_series(
    code: int,
    *,
    start: str = "01/01/2015",
    end: str = "31/12/2026",
    timeout: int = 60,
) -> pd.DataFrame:
    response = requests.get(
        BCB_API.format(code=code),
        params={
            "formato": "json",
            "dataInicial": start,
            "dataFinal": end,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise ExpandedCreditError(f"BCB SGS {code} retornou série vazia.")
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["data"], format="%d/%m/%Y")
    frame["competencia"] = frame["date"].dt.to_period("M").astype(str)
    frame["value_brl"] = (
        pd.to_numeric(
            frame["valor"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        * 1_000_000
    )
    if frame["value_brl"].isna().any():
        raise ExpandedCreditError(f"BCB SGS {code} contém valor inválido.")
    return frame[["competencia", "value_brl"]]


def build_expanded_credit_history(
    industry_monthly: pd.DataFrame,
    *,
    series_frames: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Return December observations plus the latest common 2026 competence."""

    required = {"competencia", "carteira_dc"}
    missing = sorted(required.difference(industry_monthly.columns))
    if missing:
        raise ExpandedCreditError(
            "industry_monthly sem colunas: " + ", ".join(missing)
        )
    frames = series_frames or {
        name: _download_series(code) for name, code in BCB_SERIES.items()
    }
    wide: pd.DataFrame | None = None
    for name, code in BCB_SERIES.items():
        if name not in frames:
            raise ExpandedCreditError(f"Série BCB {code} ausente.")
        current = frames[name].rename(columns={"value_brl": name}).copy()
        wide = (
            current
            if wide is None
            else wide.merge(current, on="competencia", how="inner")
        )
    assert wide is not None
    cvm = industry_monthly[["competencia", "carteira_dc"]].copy()
    cvm["competencia"] = cvm["competencia"].astype(str)
    cvm["carteira_dc"] = pd.to_numeric(cvm["carteira_dc"], errors="coerce")
    joined = wide.merge(cvm, on="competencia", how="inner", validate="one_to_one")
    joined = joined[joined["competencia"].str[:4].astype(int).ge(2015)].copy()
    latest_2026 = joined.loc[
        joined["competencia"].str.startswith("2026-"), "competencia"
    ].max()
    if not latest_2026:
        raise ExpandedCreditError("Não há competência comum BCB/CVM em 2026.")
    selected = joined[
        joined["competencia"].str.endswith("-12")
        | joined["competencia"].eq(latest_2026)
    ].sort_values("competencia").reset_index(drop=True)
    selected["other_securitization"] = (
        selected["securitization"] - selected["carteira_dc"]
    )
    if selected["other_securitization"].lt(-1).any():
        rows = selected.loc[
            selected["other_securitization"].lt(-1),
            ["competencia", "securitization", "carteira_dc"],
        ]
        raise ExpandedCreditError(
            "Carteira FIDC supera securitização BCB: "
            + rows.to_dict("records").__repr__()
        )
    selected["other_securitization"] = selected[
        "other_securitization"
    ].clip(lower=0)
    selected["bcb_total_reconciliation"] = (
        selected["expanded_credit_total"]
        - selected["loans"]
        - selected["debt_securities"]
        - selected["external_debt"]
    )
    selected["bcb_debt_reconciliation"] = (
        selected["debt_securities"]
        - selected["public_debt"]
        - selected["private_debt"]
        - selected["securitization"]
    )
    selected["bcb_loans_reconciliation"] = (
        selected["loans"]
        - selected["loans_sfn"]
        - selected["loans_other_finance"]
        - selected["loans_government_funds"]
    )
    for column in (
        "bcb_total_reconciliation",
        "bcb_debt_reconciliation",
        "bcb_loans_reconciliation",
    ):
        tolerance = selected["expanded_credit_total"].abs() * 1e-8 + 1.0
        if selected[column].abs().gt(tolerance).any():
            raise ExpandedCreditError(f"Identidade BCB não fecha em {column}.")

    output = pd.DataFrame(
        {
            "period_order": range(1, len(selected) + 1),
            "competencia": selected["competencia"],
            "period_label": selected["competencia"].map(
                lambda value: (
                    f"{value[5:7]}/{value[:4][2:]}"
                    if value == latest_2026
                    else value[:4]
                )
            ),
            "is_latest": selected["competencia"].eq(latest_2026),
            "expanded_credit_total_brl": selected["expanded_credit_total"],
            "private_expanded_credit_total_brl": (
                selected["expanded_credit_total"] - selected["public_debt"]
            ),
            "loans_brl": selected["loans"],
            "public_debt_brl": selected["public_debt"],
            "private_debt_brl": selected["private_debt"],
            "fidc_receivables_brl": selected["carteira_dc"],
            "other_securitization_brl": selected["other_securitization"],
            "external_debt_brl": selected["external_debt"],
            "debt_securities_brl": selected["debt_securities"],
            "securitization_brl": selected["securitization"],
            "bcb_total_reconciliation_brl": selected[
                "bcb_total_reconciliation"
            ],
            "bcb_debt_reconciliation_brl": selected[
                "bcb_debt_reconciliation"
            ],
            "bcb_loans_reconciliation_brl": selected[
                "bcb_loans_reconciliation"
            ],
            "source_bcb": (
                "BCB SGS 28183-28192; "
                + BCB_METADATA_URL
            ),
            "source_cvm": (
                "CVM, Informe Mensal de FIDC, Tabela I, carteira de direitos "
                "creditórios na mesma competência"
            ),
            "methodology": (
                "BCB: Crédito Ampliado = empréstimos + títulos de dívida + "
                "dívida externa; títulos = públicos + privados + securitização. "
                "Carteira de Crédito Privada Ampliada exclui títulos públicos. "
                "FIDC usa carteira de direitos creditórios CVM; outras "
                "securitizações são o residual da SGS 28191. Debêntures e notas "
                "comerciais integram títulos privados."
            ),
        }
    )
    return validate_expanded_credit_history(output)


def validate_expanded_credit_history(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(OUTPUT_COLUMNS).difference(frame.columns))
    if missing:
        raise ExpandedCreditError("Saída sem colunas: " + ", ".join(missing))
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    numeric = [
        column
        for column in OUTPUT_COLUMNS
        if column.endswith("_brl") or column == "period_order"
    ]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result[numeric].isna().any().any():
        raise ExpandedCreditError("Saída contém número ausente.")
    if result["competencia"].duplicated().any():
        raise ExpandedCreditError("Competência duplicada.")
    if result["is_latest"].astype(bool).sum() != 1:
        raise ExpandedCreditError("Saída deve conter uma única observação atual.")
    components = (
        result["loans_brl"]
        + result["public_debt_brl"]
        + result["private_debt_brl"]
        + result["fidc_receivables_brl"]
        + result["other_securitization_brl"]
        + result["external_debt_brl"]
    )
    if not (
        (components - result["expanded_credit_total_brl"]).abs()
        <= result["expanded_credit_total_brl"].abs() * 1e-8 + 1
    ).all():
        raise ExpandedCreditError("Pilha não fecha no Crédito Ampliado.")
    private_components = (
        result["loans_brl"]
        + result["private_debt_brl"]
        + result["fidc_receivables_brl"]
        + result["other_securitization_brl"]
        + result["external_debt_brl"]
    )
    if not (
        (private_components - result["private_expanded_credit_total_brl"]).abs()
        <= result["private_expanded_credit_total_brl"].abs() * 1e-8 + 1
    ).all():
        raise ExpandedCreditError(
            "Pilha não fecha na Carteira de Crédito Privada Ampliada."
        )
    return result.sort_values("period_order").reset_index(drop=True)


def write_expanded_credit_history(
    frame: pd.DataFrame,
    output_dir: str | Path,
) -> Path:
    output = validate_expanded_credit_history(frame)
    path = Path(output_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


def load_materialized_expanded_credit_history(
    data_dir: str | Path,
) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(
            f"Carteira de Crédito Privada Ampliada ausente: {path}"
        )
    return validate_expanded_credit_history(pd.read_csv(path))


__all__ = [
    "BCB_SERIES",
    "ExpandedCreditError",
    "OUTPUT_FILENAME",
    "build_expanded_credit_history",
    "load_materialized_expanded_credit_history",
    "validate_expanded_credit_history",
    "write_expanded_credit_history",
]
