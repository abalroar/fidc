"""Revalida, contra o regulamento, a seção de cada FIDC da carteira.

Lê o regulamento vigente de cada CNPJ, procura os termos que descrevem o
**lastro e o devedor**, e grava a categoria que o documento sustenta ao lado da
categoria vigente — com a pontuação, os termos achados e o trecho literal.

Onde o documento não distingue a operação, a saída é ``sem evidência`` e a
categoria vigente permanece: o script marca o que não pôde revalidar em vez de
decidir por semelhança de nome.

Os regulamentos não moram no repositório (são dezenas de megabytes de PDF
extraído); ``--docs-dir`` aponta para o cache baixado da FundosNET, e o que
fica versionado é este CSV, com a evidência de cada linha.

    python scripts/build_carteira_revalidacao.py --docs-dir <cache>
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_revalidacao import SEM_EVIDENCIA, classify  # noqa: E402

DEFAULT_DATA_DIR = Path("data/industry_study")
OUTPUT_NAME = "carteira_revalidacao_secoes.csv"
SCOPE_NAME = "industry_carteira_1_scope.csv"
TAXONOMY_NAME = "carteira_taxonomia_estrutural.csv"

COLUMNS = (
    "cnpj",
    "fundo",
    "categoria_vigente",
    "categoria_documental",
    "status",
    "pontuacao",
    "margem",
    "multi_flag",
    "termos",
    "documento_id",
    "documento_data",
    "evidencia",
)

STATUS_CONFIRMA = "confirma"
STATUS_DIVERGE = "diverge"
STATUS_SEM_EVIDENCIA = "sem evidência"
STATUS_SEM_DOCUMENTO = "sem documento"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        required=True,
        help="Diretório com <cnpj>.json.gz do cache da FundosNET.",
    )
    return parser.parse_args()


def _melhor_regulamento(registro: dict) -> dict | None:
    """O regulamento mais completo do fundo — o texto mais longo entregue."""

    candidatos = [
        documento
        for documento in registro.get("documentos", [])
        if documento.get("categoria") == "Regulamento" and documento.get("pages")
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda doc: sum(len(page) for page in doc["pages"]))


def build_frame(data_dir: Path, docs_dir: Path) -> pd.DataFrame:
    scope = pd.read_csv(Path(data_dir) / SCOPE_NAME, dtype=str)
    taxonomia = pd.read_csv(Path(data_dir) / TAXONOMY_NAME, dtype=str).set_index("cnpj")

    linhas: list[dict[str, object]] = []
    for registro in scope.itertuples():
        cnpj = str(registro.cnpj_fundo).zfill(14)
        vigente = taxonomia["categoria_estrutural"].get(cnpj, "N/D")
        nome = taxonomia["fundo"].get(cnpj) or str(registro.nome_foto or "")
        caminho = Path(docs_dir) / f"{cnpj}.json.gz"
        base = {
            "cnpj": cnpj,
            "fundo": nome,
            "categoria_vigente": vigente,
            "categoria_documental": "",
            "status": STATUS_SEM_DOCUMENTO,
            "pontuacao": "",
            "margem": "",
            "multi_flag": "",
            "termos": "",
            "documento_id": "",
            "documento_data": "",
            "evidencia": "",
        }
        if not caminho.exists():
            linhas.append(base)
            continue
        conteudo = json.loads(gzip.decompress(caminho.read_bytes()))
        documento = _melhor_regulamento(conteudo)
        if documento is None:
            linhas.append(base)
            continue

        veredito = classify(cnpj, "\n".join(documento["pages"]))
        if not veredito.conclusivo:
            status = STATUS_SEM_EVIDENCIA
        elif veredito.categoria == vigente:
            status = STATUS_CONFIRMA
        else:
            status = STATUS_DIVERGE
        base.update(
            {
                "categoria_documental": (
                    "" if veredito.categoria == SEM_EVIDENCIA else veredito.categoria
                ),
                "status": status,
                "pontuacao": veredito.pontuacao,
                "margem": veredito.margem,
                "multi_flag": veredito.multi,
                "termos": " | ".join(veredito.termos),
                "documento_id": documento.get("id", ""),
                "documento_data": documento.get("data_referencia", ""),
                "evidencia": veredito.evidencia[:600],
            }
        )
        linhas.append(base)

    return pd.DataFrame(linhas, columns=list(COLUMNS))


def main() -> None:
    args = parse_args()
    frame = build_frame(args.data_dir, args.docs_dir)
    destino = Path(args.data_dir) / OUTPUT_NAME
    frame.to_csv(destino, index=False)

    print(f"{destino}: {len(frame)} fundos")
    print(frame["status"].value_counts().to_string())
    divergem = frame[frame["status"].eq(STATUS_DIVERGE)]
    if len(divergem):
        print("\nDivergências:")
        for linha in divergem.itertuples():
            print(
                f"  {linha.cnpj} {linha.fundo[:44]:44s} "
                f"{linha.categoria_vigente} -> {linha.categoria_documental} "
                f"(pontos {linha.pontuacao}, margem {linha.margem})"
            )
    marcados = frame[frame["multi_flag"].astype(str).str.len().gt(0)]
    print(f"\nMulticedente/multissacado: {len(marcados)}")


if __name__ == "__main__":
    main()
