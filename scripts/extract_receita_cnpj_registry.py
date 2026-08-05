"""Extrai um cadastro seletivo do snapshot local do CNPJ da Receita.

Exemplo:
    python scripts/extract_receita_cnpj_registry.py \
      --source-dir /dados/receita/2026-01 \
      --targets-file cedentes.csv \
      --cnpj-column cedente_cnpj \
      --snapshot-date 2026-01-17 \
      --output-csv cadastro_receita.csv.gz \
      --manifest-json cadastro_receita_manifest.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.receita_cnpj_bulk import (  # noqa: E402
    extract_receita_cnpj_registry,
    write_receita_cnpj_registry,
)


def _load_targets(path: Path, cnpj_column: str | None) -> list[object]:
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith((".csv", ".csv.gz")):
        frame = pd.read_csv(path, dtype=str)
    elif suffixes.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(path, dtype=str)
    elif suffixes.endswith(".jsonl"):
        frame = pd.read_json(path, lines=True, dtype=False)
    elif suffixes.endswith(".json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list) and all(not isinstance(item, dict) for item in payload):
            return payload
        if isinstance(payload, dict):
            for key in ("cnpjs", "targets", "documentos"):
                values = payload.get(key)
                if isinstance(values, list):
                    return values
        frame = pd.DataFrame(payload)
    else:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]

    if frame.empty:
        return []
    if cnpj_column:
        if cnpj_column not in frame.columns:
            raise ValueError(
                f"Coluna {cnpj_column!r} ausente; disponiveis={list(frame.columns)!r}"
            )
        column = cnpj_column
    elif len(frame.columns) == 1:
        column = str(frame.columns[0])
    else:
        candidates = [
            str(column)
            for column in frame.columns
            if "cnpj" in str(column).casefold() or "document" in str(column).casefold()
        ]
        if len(candidates) != 1:
            raise ValueError(
                "Use --cnpj-column quando o arquivo tiver mais de uma coluna de documento"
            )
        column = candidates[0]
    return frame[column].dropna().tolist()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filtra os ZIPs locais dos Dados Abertos do CNPJ e produz um "
            "cadastro auditavel sem chamadas de rede."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help=(
            "Pasta com Empresas0-9.zip, Estabelecimentos0-9.zip, "
            "Simples.zip, Cnaes.zip e Municipios.zip"
        ),
    )
    parser.add_argument(
        "--targets-file",
        type=Path,
        required=True,
        help="CSV, XLSX, JSON, JSONL ou TXT com os CNPJs-alvo",
    )
    parser.add_argument(
        "--cnpj-column",
        default=None,
        help="Nome da coluna de CNPJ; inferido quando inequívoco",
    )
    parser.add_argument(
        "--snapshot-date",
        required=True,
        help="Data do snapshot oficial no formato YYYY-MM-DD",
    )
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument(
        "--chunksize",
        type=int,
        default=250_000,
        help="Linhas lidas por bloco de cada CSV interno (padrão: 250000)",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Permite menos de dez partes em Empresas/Estabelecimentos (uso de teste)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    targets = _load_targets(args.targets_file, args.cnpj_column)
    result = extract_receita_cnpj_registry(
        args.source_dir,
        targets,
        snapshot_date=args.snapshot_date,
        chunksize=args.chunksize,
        strict_parts=not args.allow_partial,
    )
    write_receita_cnpj_registry(
        result,
        output_csv=args.output_csv,
        manifest_json=args.manifest_json,
    )
    print(
        "[ok] "
        f"{result.manifest['cadastros_encontrados']}/"
        f"{result.manifest['target_cnpjs']} CNPJs encontrados"
    )
    print(f"[ok] cadastro: {args.output_csv}")
    print(f"[ok] manifesto: {args.manifest_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
