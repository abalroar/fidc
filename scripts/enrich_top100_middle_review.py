"""Completa a base do Top 100 com o cedente declarado e a triagem de Middle.

O que estava vazio na base — cedente, CNAE, UF, tipo e foco ANBIMA — estava
vazio porque a curadoria manual só tinha alcançado 29 dos 100 fundos.  Este
script preenche o resto a partir de fontes primárias, e **nunca sobrescreve** o
que a curadoria já decidiu: o preenchimento entra só onde a célula está vazia.

Fontes, nesta ordem de precedência:

* cedente, CNAE, UF — Informe Mensal da CVM, via
  ``top100_cedentes_middle_triagem.csv``, tomando o cedente de maior
  participação declarada;
* tipo e foco ANBIMA — cadastro oficial de classes;
* coluna Middle — a triagem de :mod:`services.middle_market_triage`.

    python scripts/enrich_top100_middle_review.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.middle_market_triage import PROVAVEL  # noqa: E402

DEFAULT_DATA_DIR = Path("data/industry_study")
REVIEW_NAME = "top100_fidcs_middle_review.csv"
TRIAGE_NAME = "top100_cedentes_middle_triagem.csv"
CLASSIFICATION_NAME = "industry_anbima_classification.csv.gz"

#: Valor com que a coluna de revisão chega pré-preenchida.  O analista confirma
#: ou corrige; o campo continua sendo dele.
SUGESTAO_MIDDLE = "Provável"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser.parse_args()


def _dominante(triagem: pd.DataFrame) -> pd.DataFrame:
    """O cedente que responde pela maior parte da carteira de cada fundo.

    Empate na participação — comum quando o fundo não a declara — desempata
    pelo maior capital social, que é o cedente de maior porte entre os
    declarados.
    """

    frame = triagem.copy()
    frame["pct"] = pd.to_numeric(frame["participacao_pct"], errors="coerce").fillna(0.0)
    frame["cap"] = pd.to_numeric(frame["capital_social_reais"], errors="coerce")
    return (
        frame.sort_values(["pct", "cap"], ascending=False)
        .drop_duplicates("cnpj_fundo")
        .set_index("cnpj_fundo")
    )


def enrich(data_dir: Path) -> tuple[pd.DataFrame, dict[str, tuple[int, int]]]:
    review = pd.read_csv(Path(data_dir) / REVIEW_NAME, dtype=str)
    triagem = pd.read_csv(Path(data_dir) / TRIAGE_NAME, dtype=str)
    review["cnpj14"] = review["cnpj"].str.zfill(14)

    dominante = _dominante(triagem)
    provaveis = _dominante(triagem[triagem["classificacao"].eq(PROVAVEL)])

    cobertura: dict[str, tuple[int, int]] = {}
    for coluna, origem in (
        ("Razão social cedente", "razao_social"),
        ("CNPJ cedente", "cedente_doc"),
        ("CNAE cedente", "cnae"),
        ("UF", "uf"),
        ("Porte", "porte"),
    ):
        antes = int(review[coluna].notna().sum())
        review[coluna] = review[coluna].fillna(review["cnpj14"].map(dominante[origem]))
        cobertura[coluna] = (antes, int(review[coluna].notna().sum()))

    # A seção CNAE do cedente descreve o setor quando a curadoria ainda não
    # chegou nele — é a mesma informação, na taxonomia da Receita.
    antes = int(review["Setor cedente"].notna().sum())
    review["Setor cedente"] = review["Setor cedente"].fillna(
        review["cnpj14"].map(dominante["secao_cnae"]).replace("", pd.NA)
    )
    cobertura["Setor cedente"] = (antes, int(review["Setor cedente"].notna().sum()))

    registro = pd.read_csv(Path(data_dir) / CLASSIFICATION_NAME, dtype=str)
    por_fundo = registro.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")
    por_classe = registro.drop_duplicates("cnpj_classe").set_index("cnpj_classe")
    for coluna, origem in (("Tipo ANBIMA", "tipo_anbima"), ("Foco ANBIMA", "foco_anbima")):
        antes = int(review[coluna].notna().sum())
        review[coluna] = review[coluna].fillna(
            review["cnpj14"].map(por_fundo[origem])
        ).fillna(review["cnpj14"].map(por_classe[origem]))
        cobertura[coluna] = (antes, int(review[coluna].notna().sum()))

    # A coluna de revisão chega sugerida onde a triagem encontrou um cedente de
    # porte Middle, com a razão social ao lado para o analista conferir.
    antes = int(review["MIDDLE (preencher)"].notna().sum())
    # ``Series.map`` aplica a função também ao ausente; a sugestão precisa vir
    # de uma máscara, senão os cem fundos saem sugeridos como Middle.
    tem_provavel = review["cnpj14"].isin(provaveis.index)
    review["MIDDLE (preencher)"] = review["MIDDLE (preencher)"].fillna(
        pd.Series(SUGESTAO_MIDDLE, index=review.index).where(tem_provavel)
    )
    review["Cedente Provável Middle"] = review["cnpj14"].map(provaveis["razao_social"])
    review["Capital social do cedente (R$)"] = review["cnpj14"].map(
        provaveis["capital_social_reais"]
    )
    cobertura["MIDDLE (preencher)"] = (antes, int(review["MIDDLE (preencher)"].notna().sum()))

    return review.drop(columns=["cnpj14"]), cobertura


def main() -> None:
    args = parse_args()
    review, cobertura = enrich(args.data_dir)
    destino = Path(args.data_dir) / REVIEW_NAME
    review.to_csv(destino, index=False)

    print(f"{destino}: {len(review)} fundos")
    print(f"{'coluna':32s} antes -> depois")
    for coluna, (antes, depois) in cobertura.items():
        marca = "  +" if depois > antes else "   "
        print(f"{marca} {coluna:30s} {antes:3d} -> {depois:3d}")


if __name__ == "__main__":
    main()
