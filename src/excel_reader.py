from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class ExcelInputs:
    premissas: Dict[str, Any]
    outputs: List[str]
    fluxo_base: Optional[pd.DataFrame] = None
    bmf: Optional[pd.DataFrame] = None
    holidays: Optional[List[pd.Timestamp]] = None
    vencimentario: Optional[pd.DataFrame] = None


def _find_cell(df: pd.DataFrame, target: str) -> Optional[Tuple[int, int]]:
    target_lower = target.strip().lower()
    for row_idx in range(df.shape[0]):
        row = df.iloc[row_idx]
        for col_idx, value in enumerate(row):
            if isinstance(value, str) and value.strip().lower() == target_lower:
                return row_idx, col_idx
    return None


def _collect_premissas(df: pd.DataFrame, start_row: int, label_col: int) -> Dict[str, Any]:
    premissas: Dict[str, Any] = {}
    for row_idx in range(start_row + 1, df.shape[0]):
        label = df.iat[row_idx, label_col]
        value = df.iat[row_idx, label_col + 1] if label_col + 1 < df.shape[1] else None
        if pd.isna(label) or str(label).strip() == "":
            break
        premissas[str(label).strip()] = value
    return premissas


def _collect_outputs(df: pd.DataFrame, start_row: int, label_col: int) -> List[str]:
    outputs: List[str] = []
    for row_idx in range(start_row + 1, df.shape[0]):
        label = df.iat[row_idx, label_col]
        if pd.isna(label) or str(label).strip() == "":
            break
        outputs.append(str(label).strip())
    return outputs


def load_excel_inputs(path: str) -> ExcelInputs:
    xls = pd.ExcelFile(path)
    fluxo_base = pd.read_excel(xls, sheet_name="Fluxo Base", header=None)
    bmf = pd.read_excel(xls, sheet_name="BMF", header=0)
    holidays_df = pd.read_excel(xls, sheet_name="Holidays", header=None)
    vencimentario = pd.read_excel(xls, sheet_name="Vencimentário", header=None)

    premissas: Dict[str, Any] = {}
    outputs: List[str] = []
    premissa_cell = _find_cell(fluxo_base, "PREMISSAS")
    if premissa_cell:
        premissas = _collect_premissas(fluxo_base, premissa_cell[0], premissa_cell[1])

    outputs_cell = _find_cell(fluxo_base, "OUTPUTS")
    if outputs_cell:
        outputs = _collect_outputs(fluxo_base, outputs_cell[0], outputs_cell[1])

    holidays = _extract_holidays(holidays_df)

    return ExcelInputs(
        premissas=premissas,
        outputs=outputs,
        fluxo_base=fluxo_base,
        bmf=bmf,
        holidays=holidays,
        vencimentario=vencimentario,
    )


def _extract_holidays(df: pd.DataFrame) -> List[pd.Timestamp]:
    holidays: List[pd.Timestamp] = []
    for col in df.columns:
        series = pd.to_datetime(df[col], errors="coerce")
        series = series.dropna()
        holidays.extend(series.tolist())
    unique_holidays = sorted({pd.Timestamp(h).normalize() for h in holidays})
    return unique_holidays


def infer_curve(bmf: pd.DataFrame) -> Optional[pd.DataFrame]:
    if bmf is None or bmf.empty:
        return None

    date_col = None
    rate_col = None
    for col in bmf.columns:
        if date_col is None and "date" in str(col).lower():
            date_col = col
        if rate_col is None and ("rate" in str(col).lower() or "taxa" in str(col).lower()):
            rate_col = col

    if date_col is None:
        date_col = bmf.columns[0]
    if rate_col is None and len(bmf.columns) > 1:
        rate_col = bmf.columns[1]

    if rate_col is None:
        return None

    curve = bmf[[date_col, rate_col]].copy()
    curve.columns = ["date", "rate"]
    curve["date"] = pd.to_datetime(curve["date"], errors="coerce")
    curve = curve.dropna(subset=["date", "rate"])
    return curve
