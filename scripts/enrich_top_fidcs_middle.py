"""Completa o Originador dos Top FIDCs Middle com o cedente declarado à CVM.

A coluna saía como "Não identificado" em 16 de 16 porque a regra da curadoria
era não inferir originador sem suporte documental — e a leitura de regulamento
não tinha alcançado esses fundos.

O Informe Mensal resolve isso sem quebrar a regra: o cedente declarado na
Tabela I é o próprio fundo dizendo à CVM quem lhe cede os direitos creditórios.
É documento primário, não inferência.

Junto vem a triagem de porte de :mod:`services.middle_market_triage`, que diz
se aquele originador tem perfil de cliente Middle.

    python scripts/enrich_top_fidcs_middle.py --ime-dir <cache> --cnpj-dir <cache>
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_middle_market_triage import (  # noqa: E402
    _CAMPOS_TRIAGEM,
    declared_cedentes,
    registry,
)
from services.middle_market_triage import PROVAVEL, triar  # noqa: E402

DEFAULT_DATA_DIR = Path("data/industry_study")
RESOLVED_NAME = "top_fidcs_middle_resolved.csv"
NAO_IDENTIFICADO = "Não identificado"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--ime-dir", type=Path, required=True)
    parser.add_argument("--cnpj-dir", type=Path, required=True)
    return parser.parse_args()


def enrich(data_dir: Path, ime_dir: Path, cnpj_dir: Path) -> tuple[pd.DataFrame, dict]:
    resolved = pd.read_csv(Path(data_dir) / RESOLVED_NAME, dtype=str)
    resolved["cnpj14"] = (
        resolved["cnpj_fundo"].str.replace(r"\D", "", regex=True).str.zfill(14)
    )
    declarados = declared_cedentes(ime_dir, set(resolved["cnpj14"]))
    cadastro = registry(data_dir, cnpj_dir)

    linhas: list[dict[str, object]] = []
    for registro in declarados.to_dict("records"):
        ficha = cadastro.get(str(registro["cedente_doc"]), {})
        veredito = triar(
            str(registro["cedente_doc"]),
            **{k: v for k, v in ficha.items() if k in _CAMPOS_TRIAGEM},
        )
        linhas.append(
            {
                "cnpj_fundo": registro["cnpj_fundo"],
                "razao_social": veredito.razao_social,
                "classificacao": veredito.classificacao,
                "capital": veredito.capital_social,
                "pct": pd.to_numeric(registro.get("participacao_pct"), errors="coerce"),
            }
        )
    triagem = pd.DataFrame(linhas)
    # O originador é o cedente de maior participação; sem participação
    # declarada, o de maior capital social entre os declarados.
    dominante = (
        triagem.sort_values(["pct", "capital"], ascending=False)
        .drop_duplicates("cnpj_fundo")
        .set_index("cnpj_fundo")
    )

    antes = int(resolved["originador"].ne(NAO_IDENTIFICADO).sum())
    declarado = resolved["cnpj14"].map(dominante["razao_social"])
    resolved["originador"] = resolved["originador"].where(
        resolved["originador"].ne(NAO_IDENTIFICADO) & resolved["originador"].notna(),
        declarado.fillna(NAO_IDENTIFICADO),
    )
    resolved["originador_fonte"] = declarado.notna().map(
        {True: "CVM, Informe Mensal — cedente declarado na Tabela I", False: ""}
    )
    resolved["originador_porte"] = resolved["cnpj14"].map(dominante["classificacao"])
    resolved["originador_capital_social"] = resolved["cnpj14"].map(dominante["capital"])
    depois = int(resolved["originador"].ne(NAO_IDENTIFICADO).sum())

    resumo = {
        "originador": (antes, depois),
        "provavel_middle": int(resolved["originador_porte"].eq(PROVAVEL).sum()),
        "total": len(resolved),
    }
    return resolved.drop(columns=["cnpj14"]), resumo


def main() -> None:
    args = parse_args()
    resolved, resumo = enrich(args.data_dir, args.ime_dir, args.cnpj_dir)
    destino = Path(args.data_dir) / RESOLVED_NAME
    resolved.to_csv(destino, index=False)

    antes, depois = resumo["originador"]
    print(f"{destino}: {resumo['total']} fundos")
    print(f"  originador identificado  {antes} -> {depois}")
    print(f"  originador Provável Middle  {resumo['provavel_middle']}")


if __name__ == "__main__":
    main()
