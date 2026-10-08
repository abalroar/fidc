"""Period contracts for official offers, derived from the consolidated CVM cut."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from services.industry_comparative_period import ComparisonCut

INDUSTRY_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"

def resolve_offer_cut(comparison_cut: ComparisonCut | None = None, data_dir: str | Path = INDUSTRY_DIR) -> ComparisonCut:
    return comparison_cut or ComparisonCut.from_data_dir(data_dir)

def cut_from_offer_frame(frame: pd.DataFrame) -> ComparisonCut:
    partial = frame.loc[frame["period_label"].astype(str).str.contains("jan-", regex=False)]
    if partial.empty:
        raise ValueError("Coorte de ofertas sem período YTD explicitamente datado")
    dates = pd.to_datetime(partial["period_end"], errors="coerce")
    if dates.isna().any() or dates.nunique() != 1:
        raise ValueError("Coorte de ofertas contém datas YTD divergentes")
    cut = ComparisonCut.from_competence(dates.iloc[0].strftime("%Y-%m"))
    if dates.iloc[0].date() != cut.period_end or not partial["period_label"].eq(cut.period_id()).all():
        raise ValueError("Rótulo YTD diverge da data final do período de ofertas")
    return cut

def offer_periods(cut: ComparisonCut, *, history_years: int = 3, include_previous: bool = False) -> tuple[dict[str, object], ...]:
    rows=[]
    for order, year in enumerate(range(cut.year-history_years, cut.year), start=1):
        row={"period_order":order,"period_label":f"{year} FY","period_start":f"{year}-01-01","period_end":f"{year}-12-31","is_full_year":True}
        if include_previous:
            row.update(previous_period_label=f"{year-1} FY" if order>1 else "N/D — início da janela histórica",previous_period_start=f"{year-1}-01-01" if order>1 else "",previous_period_end=f"{year-1}-12-31" if order>1 else "")
        rows.append(row)
    row={"period_order":history_years+1,"period_label":cut.period_id(),"period_start":f"{cut.year}-01-01","period_end":cut.period_end.isoformat(),"is_full_year":False}
    if include_previous:
        row.update(previous_period_label=cut.period_id(cut.year-1),previous_period_start=f"{cut.year-1}-01-01",previous_period_end=cut.previous_period_end.isoformat())
    rows.append(row)
    return tuple(rows)

def ticket_periods(cut: ComparisonCut, *, history_years: int = 4) -> tuple[tuple[object, ...], ...]:
    periods=offer_periods(cut, history_years=history_years)
    return tuple((row["period_order"], f"{row['period_label']} parcial" if row["period_label"]=="2022 FY" else row["period_label"],row["period_start"],row["period_end"],row["is_full_year"]) for row in periods)
