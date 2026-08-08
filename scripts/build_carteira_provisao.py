"""Extrai a PDD de cada FIDC do Informe Mensal e materializa a base da carteira.

O ``vehicle_monthly`` já traz carteira de direitos creditórios e inadimplência,
mas não a provisão.  No Informe Mensal da CVM ela mora na Tabela I, no campo
``VL_REDUCAO_RECUP`` — *redução ao valor recuperável* —, aberto em dois blocos:
os direitos creditórios **com** e **sem** coobrigação do cedente.  A PDD do
fundo é a soma dos dois.

Um detalhe do arquivo importa para a leitura: a CVM **nunca deixa o campo em
branco** na Tabela I.  Um fundo que não provisiona reporta ``0``, e isso é uma
declaração, não uma ausência.  Quem some da base é o fundo que não entregou o
informe daquela competência — e é só esse que a aplicação mostra como
``sem informe``.

As competências baixadas são as que a carteira resolvida de fato usa: cada
fundo entra com o seu mês mais recente, então a carteira mistura meses e a base
precisa cobrir todos eles.

    python scripts/build_carteira_provisao.py
    python scripts/build_carteira_provisao.py --competencias 2026-06 2026-07
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import time
import zipfile

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_provisao import PROVISAO_NAME  # noqa: E402
from services.carteira_subordinacao import DEFAULT_DATA_DIR, resolve_portfolio  # noqa: E402

BASE_URL = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/"
USER_AGENT = "fidc-dashboard/1.0 (dados.cvm.gov.br open data)"

#: A PDD do Informe: redução ao valor recuperável, com e sem coobrigação.
PDD_COLUMNS = ("TAB_I2A11_VL_REDUCAO_RECUP", "TAB_I2B11_VL_REDUCAO_RECUP")


def _numeric(series: pd.Series) -> pd.Series:
    """Os valores da CVM, em número.

    A Tabela I sai com ponto decimal e sem separador de milhar
    (``96556579.53``), mas outros arquivos do mesmo pacote saem no formato
    brasileiro.  Tratar o ponto como milhar sempre multiplicaria a Tabela I por
    cem; a decisão é por linha, pela presença da vírgula.
    """

    texto = series.astype(str).str.strip()
    tem_virgula = texto.str.contains(",", regex=False)
    brasileiro = texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto.where(~tem_virgula, brasileiro), errors="coerce")


def baixar(competencia: str, cache: Path) -> bytes:
    """O zip da competência, do cache local ou da CVM."""

    snapshot = competencia.replace("-", "")
    destino = cache / f"inf_mensal_fidc_{snapshot}.zip"
    if destino.is_file():
        return destino.read_bytes()
    cache.mkdir(parents=True, exist_ok=True)
    ultimo: Exception | None = None
    for tentativa in range(4):
        try:
            resposta = requests.get(
                f"{BASE_URL}inf_mensal_fidc_{snapshot}.zip",
                headers={"User-Agent": USER_AGENT},
                timeout=300,
            )
            resposta.raise_for_status()
            destino.write_bytes(resposta.content)
            return resposta.content
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
            time.sleep(2**tentativa)
    raise RuntimeError(f"Não foi possível baixar {competencia}: {ultimo}")


def extrair(payload: bytes, competencia: str) -> pd.DataFrame:
    snapshot = competencia.replace("-", "")
    membro = f"inf_mensal_fidc_tab_I_{snapshot}.csv"
    with zipfile.ZipFile(io.BytesIO(payload)) as arquivo:
        if membro not in arquivo.namelist():
            raise FileNotFoundError(f"{membro} ausente no zip de {competencia}")
        bruto = arquivo.read(membro)
    tabela = pd.read_csv(
        io.BytesIO(bruto),
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    coluna_cnpj = (
        "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in tabela else "CNPJ_FUNDO"
    )
    tabela["cnpj"] = (
        tabela[coluna_cnpj].str.replace(r"\D", "", regex=True).str.zfill(14)
    )
    pdd = sum(_numeric(tabela[coluna]).fillna(0.0) for coluna in PDD_COLUMNS)
    saida = pd.DataFrame(
        {"competencia": competencia, "cnpj": tabela["cnpj"], "pdd_brl": pdd}
    )
    # Uma classe por linha; o fundo é a soma das suas classes.
    return saida.groupby(["competencia", "cnpj"], as_index=False)["pdd_brl"].sum()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--competencias",
        nargs="*",
        help="AAAA-MM a baixar; o padrão são as competências que a carteira usa.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=ROOT / ".cache" / "cvm-industry-study",
        help="Onde os zips da CVM ficam, para não rebaixar a cada execução.",
    )
    args = parser.parse_args()

    competencias = args.competencias
    if not competencias:
        # Só a carteira ativa: um fundo que parou de reportar em 2024 puxaria
        # zips de competências que a aplicação nunca mostra.
        frame = resolve_portfolio(args.data_dir).frame
        competencias = sorted(frame["competencia"].dropna().astype(str).unique())
    competencias = [c for c in competencias if len(c) == 7]

    partes = []
    for competencia in competencias:
        partes.append(extrair(baixar(competencia, args.cache), competencia))
        print(f"{competencia}: {len(partes[-1])} fundos", flush=True)

    tabela = pd.concat(partes, ignore_index=True).sort_values(
        ["competencia", "cnpj"]
    )
    destino = args.data_dir / PROVISAO_NAME
    tabela.to_csv(destino, index=False, compression="gzip")
    print(f"{len(tabela)} linhas em {destino}")


if __name__ == "__main__":
    main()
