from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.cloudwalk_financial_cost import (  # noqa: E402
    DEFAULT_CLOUDWALK_EMISSIONS,
    DEFAULT_FINANCIAL_COST_CONFIG,
    DEFAULT_FINANCIAL_COST_OUTPUT_DIR,
    CostRunConfig,
    build_financial_cost_outputs,
    export_financial_cost_outputs,
    load_amortization_convention_overrides,
    load_cash_yield_factor,
    load_funding_lines,
    load_ime_financial_snapshots,
    load_spread_overrides,
)
from services.fidc_model.b3_cdi import B3CdiError, fetch_b3_cdi_monthly_rates  # noqa: E402
from services.fidc_model.b3_curves import fetch_latest_taxaswap_curve  # noqa: E402
from services.fidc_model.curves import INTERPOLATION_METHOD_FLAT_FORWARD_252, interpolate_curve  # noqa: E402
from services.waterfall_schedule import DEFAULT_REFERENCE_DATE, only_digits  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Estima custo financeiro anual Cloudwalk em três metodologias.")
    parser.add_argument("--emissions-csv", type=Path, default=DEFAULT_CLOUDWALK_EMISSIONS)
    parser.add_argument("--config-json", type=Path, default=DEFAULT_FINANCIAL_COST_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FINANCIAL_COST_OUTPUT_DIR)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--snapshot-date", default="")
    parser.add_argument("--cdi-aa", type=float, default=None, help="CDI/DI anual em decimal; ex. 0.13 para 13%%.")
    parser.add_argument("--curve-date", default=date.today().isoformat())
    parser.add_argument("--cache-root", default=".cache/fundonet-ime")
    parser.add_argument("--portable-cache-root", default="data/ime_cache/fundonet-ime")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date) if args.start_date else date(args.year, 1, 1)
    end_date = date.fromisoformat(args.end_date) if args.end_date else date(args.year, 12, 31)
    snapshot_date = date.fromisoformat(args.snapshot_date) if args.snapshot_date else _default_snapshot_date(start_date, end_date)
    cdi_aa, cdi_source = _resolve_cdi(args.cdi_aa, date.fromisoformat(args.curve_date))
    monthly_cdi_rates = ()
    if args.cdi_aa is None:
        try:
            monthly_cdi_rates = fetch_b3_cdi_monthly_rates(start_date, end_date)
        except B3CdiError as exc:
            print(
                f"Aviso: CDI mensal realizado indisponível; seguindo com a curva B3 ({exc}).",
                file=sys.stderr,
            )

    spread_overrides = load_spread_overrides(args.config_json)
    amortization_convention_overrides = load_amortization_convention_overrides(args.config_json)
    cash_yield_factor = load_cash_yield_factor(args.config_json)
    lines = load_funding_lines(
        args.emissions_csv,
        spread_overrides=spread_overrides,
        amortization_convention_overrides=amortization_convention_overrides,
    )
    fund_names = {only_digits(line.cnpj): line.fund_name for line in lines if line.fund_name}
    snapshots = load_ime_financial_snapshots(
        [line.cnpj for line in lines if line.included],
        fund_names=fund_names,
        cache_root=args.cache_root,
        portable_cache_root=args.portable_cache_root,
    )
    outputs = build_financial_cost_outputs(
        lines=lines,
        snapshots=snapshots,
        config=CostRunConfig(
            start_date=start_date,
            end_date=end_date,
            snapshot_date=snapshot_date,
            cdi_aa=cdi_aa,
            cdi_source=f"{cdi_source}; CDI mensal B3 composto" if monthly_cdi_rates else cdi_source,
            cash_yield_cdi_factor=cash_yield_factor,
            monthly_cdi_rates=monthly_cdi_rates,
        ),
    )
    paths = export_financial_cost_outputs(outputs, args.output_dir)

    print(f"CDI/DI proxy anual: {cdi_aa:.4%} ({cdi_source})")
    print(f"Linhas de funding carregadas: {len(lines)}")
    print(f"Linhas ativas sem spread CDI+: {len(outputs.missing_inputs_df.index)}")
    print("Arquivos gerados:")
    for label, path in paths.items():
        print(f"- {label}: {path}")


def _resolve_cdi(manual_cdi_aa: float | None, curve_date: date) -> tuple[float, str]:
    if manual_cdi_aa is not None:
        return manual_cdi_aa, "manual --cdi-aa"
    snapshot = fetch_latest_taxaswap_curve(start_date=curve_date, curve_code="PRE")
    cdi_aa = interpolate_curve(
        252.0,
        snapshot.curva_du,
        snapshot.curva_taxa_aa,
        method=INTERPOLATION_METHOD_FLAT_FORWARD_252,
    )
    source = f"B3 TaxaSwap PRE {snapshot.generated_at.isoformat()} DU252"
    return cdi_aa, source


def _default_snapshot_date(start_date: date, end_date: date) -> date:
    if start_date <= DEFAULT_REFERENCE_DATE <= end_date:
        return DEFAULT_REFERENCE_DATE
    if DEFAULT_REFERENCE_DATE > end_date:
        return end_date
    return start_date


if __name__ == "__main__":
    main()
