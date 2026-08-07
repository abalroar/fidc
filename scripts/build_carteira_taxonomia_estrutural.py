"""Materializa a taxonomia estrutural da Carteira 101 num CSV enxuto.

A classificação que dava nome aos slides 18–23 — Financeiro, Adquirência,
Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS, Factoring — nasce em
``services.industry_structural_risk`` e hoje só existe dentro do payload
publicado, um JSON de 29 MB.  Ler aquele arquivo a cada renderização para
recuperar um mapa de 101 linhas é desproporcional.

Este script extrai o mapa e o grava ao lado das outras tabelas curadas, com a
origem de cada linha: se a categoria veio da taxonomia calculada ou de um
override manual, e o motivo registrado.

    python scripts/build_carteira_taxonomia_estrutural.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATA_DIR = Path("data/industry_study")
PAYLOAD = Path("generated_revision/artifact_payload.json")
OUTPUT_NAME = "carteira_taxonomia_estrutural.csv"
BLOCK = "carteira_1_structural_assets"

#: O rótulo herdado do payload publicado não descreve estes veículos: nenhum é
#: factoring no sentido regulatório, e os próprios regulamentos se classificam
#: como fomento mercantil.  A tradução acontece aqui, e não no serviço de risco
#: estrutural, que está amarrado ao contrato do bundle.
RENOMEIA = {"Factoring": "Fomento Mercantil"}

COLUMNS = (
    "cnpj",
    "fundo",
    "categoria_estrutural",
    "categoria_detalhe",
    "override_flag",
    "fonte",
    "motivo",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser.parse_args()


def build_frame(data_dir: Path) -> pd.DataFrame:
    payload = json.loads((Path(data_dir) / PAYLOAD).read_text(encoding="utf-8"))
    assets = pd.DataFrame(payload[BLOCK])
    frame = pd.DataFrame(
        {
            "cnpj": assets["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14),
            "fundo": assets["ativo"].astype(str),
            "categoria_estrutural": assets["mvp_slide_categoria"]
            .astype(str)
            .replace(RENOMEIA),
            # ``categoria`` é o corte fino (Consignado INSS e Consignado FGTS
            # entram separados ali e juntos na categoria do slide).
            "categoria_detalhe": assets["categoria"].astype(str),
            "override_flag": assets["mvp_slide_categoria_override_flag"].astype(bool),
            "fonte": assets["mvp_slide_categoria_fonte"].astype(str),
            "motivo": assets["mvp_slide_categoria_motivo"].astype(str),
        }
    )
    return frame.sort_values(["categoria_estrutural", "fundo"]).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    frame = build_frame(args.data_dir)
    output = Path(args.data_dir) / OUTPUT_NAME
    frame.to_csv(output, index=False)
    print(f"{output}: {len(frame)} fundos")
    print(frame["categoria_estrutural"].value_counts().to_string())


if __name__ == "__main__":
    main()
