from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.waterfall_schedule import (
    DEFAULT_CLOUDWALK_EMISSIONS,
    DEFAULT_WATERFALL_OUTPUT_DIR,
    build_waterfall_schedule,
    export_waterfall,
    load_cloudwalk_emissions,
    load_waterfall_inputs,
)


DEFAULT_INPUTS = Path("config/waterfall_cloudwalk_inputs.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera waterfall de amortizações sênior dos FIDCs Cloudwalk.")
    parser.add_argument("--emissions-csv", type=Path, default=DEFAULT_CLOUDWALK_EMISSIONS)
    parser.add_argument("--inputs-json", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_WATERFALL_OUTPUT_DIR)
    args = parser.parse_args()

    inputs = load_waterfall_inputs(args.inputs_json)
    schedules = load_cloudwalk_emissions(args.emissions_csv, reference_date=inputs["reference_date"])
    rows = build_waterfall_schedule(
        schedules,
        inputs["caixa_inicial"],
        inputs["recebiveis"],
        reference_date=inputs["reference_date"],
    )
    paths = export_waterfall(rows, schedules, args.output_dir)

    included = [schedule for schedule in schedules if schedule.included]
    excluded = [schedule for schedule in schedules if not schedule.included]
    print(f"FIDCs/classes sênior incluídos: {len(included)}")
    print(f"Linhas excluídas do waterfall: {len(excluded)}")
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
