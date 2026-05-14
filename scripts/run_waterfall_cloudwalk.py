from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.waterfall_schedule import (
    DEFAULT_CLOUDWALK_EMISSIONS,
    DEFAULT_REFERENCE_DATE,
    DEFAULT_WATERFALL_OUTPUT_DIR,
    build_waterfall_schedule,
    export_waterfall,
    load_cloudwalk_emissions,
    load_cloudwalk_ime_assets,
    only_digits,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera waterfall de amortizações sênior dos FIDCs Cloudwalk.")
    parser.add_argument("--emissions-csv", type=Path, default=DEFAULT_CLOUDWALK_EMISSIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_WATERFALL_OUTPUT_DIR)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE.isoformat())
    parser.add_argument("--fetch-ime", action="store_true", help="Busca IME no Fundos.NET quando não houver cache local.")
    args = parser.parse_args()

    reference_date = date.fromisoformat(args.reference_date)
    schedules = load_cloudwalk_emissions(args.emissions_csv, reference_date=reference_date)
    included = [schedule for schedule in schedules if schedule.included]
    fund_names = {only_digits(schedule.cnpj): schedule.fund_name for schedule in schedules}
    ime_assets = load_cloudwalk_ime_assets(
        [schedule.cnpj for schedule in included],
        fund_names=fund_names,
        fetch_missing=args.fetch_ime,
        reference_date=reference_date,
    )
    caixa_recebiveis_ime = sum(item.caixa_recebiveis for item in ime_assets if item.included)
    rows = build_waterfall_schedule(schedules, caixa_recebiveis_ime, reference_date=reference_date)
    paths = export_waterfall(
        rows,
        schedules,
        args.output_dir,
        ime_assets=ime_assets,
        caixa_recebiveis_ime=caixa_recebiveis_ime,
    )

    excluded = [schedule for schedule in schedules if not schedule.included]
    ime_included = [item for item in ime_assets if item.included]
    ime_excluded = [item for item in ime_assets if not item.included]
    print(f"FIDCs/classes sênior incluídos: {len(included)}")
    print(f"Linhas excluídas do waterfall: {len(excluded)}")
    print(f"CNPJs com Caixa + Recebíveis via IME: {len(ime_included)}")
    print(f"Caixa + Recebíveis IME: R$ {caixa_recebiveis_ime:,.2f}")
    if ime_excluded:
        print("IME ausente/insuficiente:")
        for item in ime_excluded:
            print(f"- {item.cnpj}: {item.exclusion_reason}")
    if excluded:
        print("Principais motivos de exclusão:")
        for reason, count in Counter(schedule.exclusion_reason or "Sem motivo informado" for schedule in excluded).most_common():
            print(f"- {count}: {reason}")
    if not included:
        print(
            "Nenhum FIDC Cloudwalk entrou no consolidado. "
            "Os outputs foram gerados com relatório de inclusão/exclusão; faltam cronogramas sênior com percentuais parseáveis."
        )
    print("Arquivos gerados:")
    for label, path in paths.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
