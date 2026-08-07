"""Triagem de prováveis clientes Middle Market entre os cedentes dos FIDCs.

Junta três coisas que já existem separadas e nunca tinham sido cruzadas:

1. os **cedentes declarados** por cada fundo no Informe Mensal da CVM
   (``TAB_I2A12``/``TAB_I2B12`` da Tabela I), varridos por várias competências
   porque um fundo declara num mês e omite no outro;
2. o **cadastro da Receita Federal** de cada cedente — capital social, CNAE,
   porte, situação e UF;
3. a regra de triagem de :mod:`services.middle_market_triage`.

O resultado é uma linha por par fundo–cedente, com a classificação e o motivo.
Um cedente sem cadastro resolvido fica ``Não avaliado``: ausência de dado não
vira "provavelmente não".

    python scripts/build_middle_market_triage.py --ime-dir <cache> --cnpj-dir <cache>
"""

from __future__ import annotations

import argparse
import glob
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.middle_market_triage import PROVAVEL, triar  # noqa: E402

DEFAULT_DATA_DIR = Path("data/industry_study")
REVIEW_NAME = "top100_fidcs_middle_review.csv"
MASTER_NAME = "cedente_triage/fidc_cedentes_cadastro_master.csv.gz"
OUTPUT_NAME = "top100_cedentes_middle_triagem.csv"

COLUMNS = (
    "cnpj_fundo",
    "fundo",
    "competencia",
    "cedente_doc",
    "cedente_formatado",
    "razao_social",
    "participacao_pct",
    "capital_social_reais",
    "cnae",
    "secao_cnae",
    "porte",
    "uf",
    "classificacao",
    "motivo",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--ime-dir",
        type=Path,
        required=True,
        help="Diretório com os ZIP do Informe Mensal (inf_mensal_fidc_AAAAMM.zip).",
    )
    parser.add_argument(
        "--cnpj-dir",
        type=Path,
        required=True,
        help="Diretório com <cnpj>.json do cadastro da Receita.",
    )
    return parser.parse_args()


#: Campos que ``triar`` aceita.  O cadastro carrega mais que isso — a seção
#: CNAE, por exemplo, que descreve o setor mas não entra no julgamento de porte.
_CAMPOS_TRIAGEM = (
    "razao_social",
    "cnae",
    "cnae_descricao",
    "capital_social",
    "porte",
    "situacao",
    "uf",
)


def _secao(cadastro: dict) -> str:
    """A seção CNAE — a taxonomia da Receita, mais legível que o CNAE cheio."""

    valor = cadastro.get("secao_cnae")
    if valor and valor == valor:
        return str(valor)
    # O cadastro consultado não traz a seção; o texto do CNAE fica no lugar.
    descricao = cadastro.get("cnae_descricao")
    return "" if not descricao or descricao != descricao else str(descricao)


def _formatar(doc: str) -> str:
    if len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return doc


def declared_cedentes(ime_dir: Path, alvo: set[str]) -> pd.DataFrame:
    """Cedentes declarados na Tabela I, varrendo todas as competências no cache.

    Um fundo declara o cedente num mês e omite no seguinte, então vale a
    declaração mais recente de cada par fundo–cedente, e não a de um mês só.
    """

    linhas: list[dict[str, object]] = []
    for caminho in sorted(glob.glob(str(Path(ime_dir) / "*.zip"))):
        competencia = re.sub(r"\D", "", Path(caminho).stem)[-6:]
        pacote = zipfile.ZipFile(caminho)
        nomes = [nome for nome in pacote.namelist() if "tab_I_" in nome]
        if not nomes:
            continue
        tabela = pd.read_csv(
            io.BytesIO(pacote.read(nomes[0])),
            sep=";",
            encoding="latin-1",
            dtype=str,
            low_memory=False,
        )
        tabela["cnpj_fundo"] = (
            tabela["CNPJ_FUNDO_CLASSE"].str.replace(r"\D", "", regex=True).str.zfill(14)
        )
        for registro in tabela[tabela["cnpj_fundo"].isin(alvo)].to_dict("records"):
            # Bloco A é direito creditório com risco; bloco B, sem risco.  Os
            # dois declaram cedente, e os dois interessam.
            for bloco in ("A", "B"):
                for indice in range(1, 10):
                    documento = registro.get(f"TAB_I2{bloco}12_CPF_CNPJ_CEDENTE_{indice}")
                    if not documento or str(documento).strip().lower() in {"", "nan"}:
                        continue
                    linhas.append(
                        {
                            "competencia": competencia,
                            "cnpj_fundo": registro["cnpj_fundo"],
                            "fundo": registro["DENOM_SOCIAL"],
                            "cedente_doc": re.sub(r"\D", "", str(documento)),
                            "participacao_pct": registro.get(
                                f"TAB_I2{bloco}12_PR_CEDENTE_{indice}"
                            ),
                        }
                    )

    frame = pd.DataFrame(linhas)
    if frame.empty:
        return frame
    frame = frame[frame["cedente_doc"].str.len().ge(11)]
    # Documentos só de zeros ou de noves são o preenchimento fictício que o
    # próprio informe admite quando o fundo não quer identificar o cedente.
    frame = frame[~frame["cedente_doc"].str.fullmatch(r"0+|9+")]
    return frame.sort_values("competencia").drop_duplicates(
        ["cnpj_fundo", "cedente_doc"], keep="last"
    )


def registry(data_dir: Path, cnpj_dir: Path) -> dict[str, dict[str, object]]:
    """O cadastro de cada documento: o curado no repositório e o consultado."""

    cadastro: dict[str, dict[str, object]] = {}
    master = pd.read_csv(Path(data_dir) / MASTER_NAME, dtype=str)
    master["doc"] = master["CNPJ/CPF"].str.replace(r"\D", "", regex=True)
    for registro in master.drop_duplicates("doc").to_dict("records"):
        cadastro[registro["doc"]] = {
            "razao_social": registro.get("Razão social"),
            "cnae": registro.get("CNAE (cód.)"),
            "cnae_descricao": registro.get("CNAE principal"),
            "secao_cnae": registro.get("Seção CNAE"),
            "capital_social": registro.get("Capital social (R$)"),
            "porte": registro.get("Porte Receita"),
            "situacao": registro.get("Situação cadastral"),
            "uf": registro.get("UF"),
        }
    # O cadastro consultado é mais novo que o curado, e prevalece.
    for caminho in Path(cnpj_dir).glob("*.json"):
        dado = json.loads(caminho.read_text(encoding="utf-8"))
        cadastro[caminho.stem] = {
            "razao_social": dado.get("razao_social"),
            "cnae": dado.get("cnae_fiscal"),
            "cnae_descricao": dado.get("cnae_fiscal_descricao"),
            "capital_social": dado.get("capital_social"),
            "porte": dado.get("porte"),
            "situacao": dado.get("descricao_situacao_cadastral"),
            "uf": dado.get("uf"),
        }
    return cadastro


def build_frame(data_dir: Path, ime_dir: Path, cnpj_dir: Path) -> pd.DataFrame:
    review = pd.read_csv(Path(data_dir) / REVIEW_NAME, dtype=str)
    alvo = set(review["cnpj"].str.zfill(14))
    declarados = declared_cedentes(ime_dir, alvo)
    cadastro = registry(data_dir, cnpj_dir)

    linhas: list[dict[str, object]] = []
    for registro in declarados.to_dict("records"):
        documento = str(registro["cedente_doc"])
        ficha = cadastro.get(documento, {})
        veredito = triar(
            documento, **{k: v for k, v in ficha.items() if k in _CAMPOS_TRIAGEM}
        )
        linhas.append(
            {
                "cnpj_fundo": registro["cnpj_fundo"],
                "fundo": registro["fundo"],
                "competencia": registro["competencia"],
                "cedente_doc": documento,
                "cedente_formatado": _formatar(documento),
                "razao_social": veredito.razao_social,
                "participacao_pct": registro.get("participacao_pct"),
                "capital_social_reais": veredito.capital_social,
                "cnae": veredito.cnae,
                "secao_cnae": _secao(ficha),
                "porte": veredito.porte,
                "uf": veredito.uf,
                "classificacao": veredito.classificacao,
                "motivo": veredito.motivo,
            }
        )
    frame = pd.DataFrame(linhas, columns=list(COLUMNS))
    return frame.sort_values(
        ["classificacao", "capital_social_reais"], ascending=[True, False]
    ).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    frame = build_frame(args.data_dir, args.ime_dir, args.cnpj_dir)
    destino = Path(args.data_dir) / OUTPUT_NAME
    frame.to_csv(destino, index=False)

    print(f"{destino}: {len(frame)} pares fundo–cedente")
    print(frame["classificacao"].value_counts().to_string())
    provaveis = frame[frame["classificacao"].eq(PROVAVEL)]
    print(
        f"\nProvável Middle: {provaveis['razao_social'].nunique()} empresas em "
        f"{provaveis['cnpj_fundo'].nunique()} fundos"
    )


if __name__ == "__main__":
    main()
