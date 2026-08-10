"""Materializa as cotas da Carteira 101 por senioridade.

O ``vehicle_monthly`` preserva o total de cotas subordinadas usado no teste de
estresse, mas agrega júnior e mezanino. Esta base compacta volta à mesma Tabela
X.2 já armazenada no cache do estudo e separa as duas parcelas para o Excel de
validação. O comando não baixa arquivos por padrão.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unicodedata

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_fidc_industry_study import RawStore, prefer_class_rows, to_num
from services.carteira_subordinacao import _latest_monthly, resolve_portfolio


DEFAULT_DATA_DIR = Path("data/industry_study")
DEFAULT_RAW_DIR = Path(".cache/cvm-industry-study")
OUTPUT_NAME = "carteira_cotas_tranches.csv"


def _normalizar(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def _classificar(rotulo: object) -> str:
    normalizado = _normalizar(rotulo)
    if "MEZAN" in normalizado:
        return "mezanino"
    if "SENIOR" in normalizado:
        return "senior"
    if "SUBORD" in normalizado:
        return "subordinada"
    return "nao_classificada"


def build_frame(
    data_dir: Path,
    raw_dir: Path,
    *,
    allow_download: bool = False,
) -> pd.DataFrame:
    scope = pd.read_csv(data_dir / "industry_carteira_1_scope.csv", dtype=str)
    scope["cnpj_fundo"] = scope["cnpj_fundo"].str.replace(r"\D", "", regex=True).str.zfill(14)
    resolved = resolve_portfolio(data_dir, somente_ativos=False).frame
    extras = resolved[~resolved["cnpj"].isin(set(scope["cnpj_fundo"]))][
        ["cnpj", "fundo"]
    ].drop_duplicates("cnpj")
    extras = extras.assign(
        ordem=range(len(scope) + 1, len(scope) + len(extras) + 1),
        nome_foto=extras["fundo"],
        cnpj_fundo=extras["cnpj"],
        escopo="inclusão analítica",
    )
    scope = scope.assign(escopo="Carteira 101")
    targets = pd.concat(
        [scope[["ordem", "cnpj_fundo", "nome_foto", "escopo"]], extras[["ordem", "cnpj_fundo", "nome_foto", "escopo"]]],
        ignore_index=True,
    )
    latest = _latest_monthly(data_dir)
    latest = latest[latest["cnpj"].isin(targets["cnpj_fundo"])].copy()
    latest_index = latest.drop_duplicates("cnpj").set_index("cnpj")
    store = RawStore(raw_dir, allow_download=allow_download)

    parcelas: list[pd.DataFrame] = []
    for competencia, grupo in latest.groupby("competencia", dropna=True):
        yyyymm = str(competencia).replace("-", "")
        raw = store.read_table(yyyymm, "tab_X_2")
        if raw is None:
            raise FileNotFoundError(
                f"Tabela X.2 local ausente para {competencia}; "
                "use --allow-download somente após autorizar o download."
            )
        raw = prefer_class_rows(raw)
        raw = raw[raw["cnpj"].isin(set(grupo["cnpj"]))].copy()
        raw["competencia"] = str(competencia)
        raw["classe_tranche"] = raw["TAB_X_CLASSE_SERIE"].map(_classificar)
        raw["valor_brl"] = to_num(raw["TAB_X_QT_COTA"]) * to_num(raw["TAB_X_VL_COTA"])
        parcelas.append(
            raw[
                [
                    "competencia",
                    "cnpj",
                    "DENOM_SOCIAL",
                    "TAB_X_CLASSE_SERIE",
                    "classe_tranche",
                    "valor_brl",
                ]
            ]
        )

    detalhe = pd.concat(parcelas, ignore_index=True) if parcelas else pd.DataFrame()
    rows: list[dict[str, object]] = []
    for registro in targets.sort_values("ordem", key=lambda s: pd.to_numeric(s, errors="coerce")).itertuples():
        cnpj = registro.cnpj_fundo
        competencia = (
            str(latest_index.at[cnpj, "competencia"]) if cnpj in latest_index.index else ""
        )
        fundo = detalhe[(detalhe["cnpj"] == cnpj) & (detalhe["competencia"] == competencia)]
        current = latest_index.loc[cnpj] if cnpj in latest_index.index else None
        valores = (
            fundo.groupby("classe_tranche")["valor_brl"].sum().to_dict()
            if len(fundo)
            else {}
        )
        total = float(fundo["valor_brl"].sum()) if len(fundo) else None
        senior = valores.get("senior", 0.0) if len(fundo) else None
        mezanino = valores.get("mezanino", 0.0) if len(fundo) else None
        subordinada = valores.get("subordinada", 0.0) if len(fundo) else None
        tem_mezanino = bool((fundo["classe_tranche"] == "mezanino").any())
        nao_classificada = valores.get("nao_classificada", 0.0)
        total_mensal = float(current["vl_cotas_total"]) if current is not None else None
        sub_mensal = (
            float(current["vl_cotas_subordinadas"]) if current is not None else None
        )
        rows.append(
            {
                "ordem": int(registro.ordem),
                "cnpj": cnpj,
                "fundo": str(registro.nome_foto or ""),
                "escopo": str(registro.escopo),
                "competencia": competencia,
                "pl_total_cotas_brl": total,
                "pl_senior_brl": senior,
                "pl_mezanino_brl": mezanino,
                "pl_subordinada_brl": subordinada,
                "tem_mezanino": tem_mezanino,
                "valor_nao_classificado_brl": nao_classificada,
                "diferenca_total_vs_mensal_brl": (
                    total - total_mensal
                    if total is not None and total_mensal is not None
                    else None
                ),
                "diferenca_submaismez_vs_mensal_brl": (
                    (float(subordinada or 0.0) + float(mezanino or 0.0)) - sub_mensal
                    if sub_mensal is not None and len(fundo)
                    else None
                ),
                "fonte": (
                    f"CVM Informe Mensal {competencia} — Tabela X.2"
                    if len(fundo)
                    else "sem Tabela X.2 na competência mais recente"
                ),
            }
        )

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output or args.data_dir / OUTPUT_NAME
    frame = build_frame(
        args.data_dir,
        args.raw_dir,
        allow_download=args.allow_download,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"{output}: {len(frame)} FIDCs")


if __name__ == "__main__":
    main()
