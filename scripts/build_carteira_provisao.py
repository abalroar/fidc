"""Extrai a PDD de cada FIDC do Informe Mensal e materializa a base da carteira.

O ``vehicle_monthly`` já traz carteira de direitos creditórios e inadimplência,
mas não a provisão.  No Informe Mensal da CVM ela mora na Tabela I, no campo
``VL_REDUCAO_RECUP`` — *redução ao valor recuperável* —, aberto em dois blocos:
os direitos creditórios **com** e **sem** coobrigação do cedente.  A PDD do
fundo é a soma dos dois.

Zeros declarados são preservados. Campos vazios ou não numéricos permanecem
indisponíveis. A precedência Classe/Fundo segue o mesmo critério da base de
carteira; registros repetidos do mesmo CNPJ não são somados.

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
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_provisao import PROVISAO_NAME  # noqa: E402
from services.carteira_subordinacao import DEFAULT_DATA_DIR, resolve_portfolio  # noqa: E402
from scripts.build_fidc_industry_study import RawStore, _stable_one_row_per_cnpj  # noqa: E402

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
    return extrair_tabela(tabela, competencia)


def extrair_tabela(tabela: pd.DataFrame, competencia: str) -> pd.DataFrame:
    tabela = _stable_one_row_per_cnpj(RawStore._normalize_keys(tabela.copy()))
    components = pd.concat([_numeric(tabela[coluna]) for coluna in PDD_COLUMNS], axis=1)
    pdd = components.sum(axis=1, min_count=len(PDD_COLUMNS))
    return pd.DataFrame(
        {"competencia": competencia, "cnpj": tabela["cnpj"], "pdd_brl": pdd}
    ).sort_values("cnpj").reset_index(drop=True)


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
    parser.add_argument("--skip-download", action="store_true", help="Usar somente os arquivos locais, inclusive snapshots congelados.")
    args = parser.parse_args()

    competencias = args.competencias
    if not competencias:
        # A opção de exibir inativos também precisa de PDD na mesma data.
        frame = resolve_portfolio(args.data_dir, somente_ativos=False).frame
        competencias = sorted(frame["competencia"].dropna().astype(str).unique())
    competencias = [c for c in competencias if len(c) == 7]

    partes = []
    store = RawStore(args.cache, allow_download=not args.skip_download)
    for competencia in competencias:
        source = store.read_table(competencia.replace("-", ""), "tab_I")
        if source is None:
            raise FileNotFoundError(f"Tabela I ausente para PDD em {competencia}")
        partes.append(extrair_tabela(source, competencia))
        print(f"{competencia}: {len(partes[-1])} fundos", flush=True)

    tabela = pd.concat(partes, ignore_index=True).sort_values(
        ["competencia", "cnpj"]
    )
    destino = args.data_dir / PROVISAO_NAME
    tabela.to_csv(destino, index=False, compression={"method": "gzip", "mtime": 0})
    print(f"{len(tabela)} linhas em {destino}")


if __name__ == "__main__":
    main()
