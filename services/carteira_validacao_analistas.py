"""Base auditável para a validação dos analistas da Carteira 101."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from services.carteira_estresse import estressar
from services.carteira_provisao import attach_provisao
from services.carteira_subordinacao import resolve_portfolio
from services.carteira_triagem import DECIDIR, triar


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
SCOPE_NAME = "industry_carteira_1_scope.csv"
TRANCHES_NAME = "carteira_cotas_tranches.csv"
DOCUMENTAL_NAME = "carteira_subordinacao_validacao.csv"


def _cnpj(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"\D", "", regex=True).str.zfill(14)


def build_validation_frame(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Uma linha por CNPJ da Carteira 101, na ordem do arquivo de escopo."""

    data_dir = Path(data_dir)
    scope = pd.read_csv(data_dir / SCOPE_NAME, dtype=str)
    scope["cnpj"] = _cnpj(scope["cnpj_fundo"])
    scope["ordem"] = pd.to_numeric(scope["ordem"], errors="raise").astype(int)

    tranches = pd.read_csv(data_dir / TRANCHES_NAME, dtype={"cnpj": str})
    tranches["cnpj"] = _cnpj(tranches["cnpj"])
    for column in (
        "pl_total_cotas_brl",
        "pl_senior_brl",
        "pl_mezanino_brl",
        "pl_subordinada_brl",
    ):
        tranches[column] = pd.to_numeric(tranches[column], errors="coerce")
    tranches["tem_mezanino"] = tranches["tem_mezanino"].astype(str).str.lower().eq("true")

    documental = pd.read_csv(data_dir / DOCUMENTAL_NAME, dtype={"cnpj": str}).fillna("")
    documental["cnpj"] = _cnpj(documental["cnpj"])
    documental["valor_documental_pct"] = pd.to_numeric(
        documental["valor_documental_pct"], errors="coerce"
    )
    documental = documental.drop_duplicates("cnpj", keep="last")

    position = resolve_portfolio(data_dir, somente_ativos=False).frame
    stress = triar(estressar(attach_provisao(position, data_dir)))
    stress = stress.drop_duplicates("cnpj", keep="last")
    stress_columns = [
        "cnpj",
        "fundo",
        "competencia",
        "cobertura_pct",
        "dc_inadimplentes",
        "pdd_brl",
        "referencia_pct",
        "minimo_fonte",
        "deficit_brl",
        "sub_pos_pct",
        "folga_pos_pp",
        "aporte_brl",
        "triagem_status",
    ]

    frame = (
        scope[
            ["ordem", "cnpj", "nome_foto", "status_identidade", "observacao_identidade"]
        ]
        .merge(tranches, on=["ordem", "cnpj"], how="left", suffixes=("", "_x2"))
        .merge(stress[stress_columns], on="cnpj", how="left", suffixes=("", "_stress"))
        .merge(
            documental[
                [
                    "cnpj",
                    "veredito",
                    "valor_documental_pct",
                    "pagina",
                    "trecho",
                    "documento",
                    "fonte_no_registro",
                ]
            ],
            on="cnpj",
            how="left",
        )
    )
    frame["fidc"] = frame["fundo_stress"].where(
        frame["fundo_stress"].fillna("").astype(str).str.strip().ne(""),
        frame["nome_foto"],
    )
    frame["competencia"] = frame["competencia_stress"].where(
        frame["competencia_stress"].fillna("").astype(str).str.strip().ne(""),
        frame["competencia"],
    )
    frame["resultado_documental"] = frame["veredito"].fillna("").replace(
        "", "sem documento na apuração anterior"
    )
    frame["incluido_slide"] = frame["triagem_status"].eq(DECIDIR)
    frame["subordinada_sobre_pl"] = (
        frame["pl_subordinada_brl"] / frame["pl_total_cotas_brl"].where(
            frame["pl_total_cotas_brl"].gt(0)
        )
    )
    frame["submaismez_sobre_pl"] = np.where(
        frame["tem_mezanino"],
        (frame["pl_subordinada_brl"].fillna(0) + frame["pl_mezanino_brl"].fillna(0))
        / frame["pl_total_cotas_brl"].where(frame["pl_total_cotas_brl"].gt(0)),
        np.nan,
    )
    frame["aporte_sobre_pl"] = frame["aporte_brl"] / frame["pl_total_cotas_brl"].where(
        frame["pl_total_cotas_brl"].gt(0)
    )
    return frame.sort_values("ordem").reset_index(drop=True)


def slide_frame(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Os nove desenquadramentos usados na lâmina de resultado."""

    data_dir = Path(data_dir)
    position = resolve_portfolio(data_dir, somente_ativos=False).frame
    stress = triar(estressar(attach_provisao(position, data_dir)))
    stress = stress[stress["triagem_status"].eq(DECIDIR)].copy()
    tranches = pd.read_csv(data_dir / TRANCHES_NAME, dtype={"cnpj": str})
    tranches["cnpj"] = _cnpj(tranches["cnpj"])
    for column in (
        "pl_total_cotas_brl",
        "pl_senior_brl",
        "pl_mezanino_brl",
        "pl_subordinada_brl",
    ):
        tranches[column] = pd.to_numeric(tranches[column], errors="coerce")
    tranches["tem_mezanino"] = tranches["tem_mezanino"].astype(str).str.lower().eq("true")
    frame = stress.merge(
        tranches[
            [
                "cnpj",
                "pl_total_cotas_brl",
                "pl_senior_brl",
                "pl_mezanino_brl",
                "pl_subordinada_brl",
                "tem_mezanino",
            ]
        ],
        on="cnpj",
        how="left",
    )
    frame["subordinada_sobre_pl"] = frame["pl_subordinada_brl"] / frame[
        "pl_total_cotas_brl"
    ].where(frame["pl_total_cotas_brl"].gt(0))
    frame["submaismez_sobre_pl"] = np.where(
        frame["tem_mezanino"],
        (frame["pl_subordinada_brl"].fillna(0) + frame["pl_mezanino_brl"].fillna(0))
        / frame["pl_total_cotas_brl"].where(frame["pl_total_cotas_brl"].gt(0)),
        np.nan,
    )
    frame["aporte_sobre_pl"] = frame["aporte_brl"] / frame["pl_total_cotas_brl"].where(
        frame["pl_total_cotas_brl"].gt(0)
    )
    return frame.sort_values("folga_pos_pp").reset_index(drop=True)


def target_validation_frame(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Os nove casos da validação, com a contraprova documental anexada."""

    data_dir = Path(data_dir)
    frame = slide_frame(data_dir)
    documental = pd.read_csv(data_dir / DOCUMENTAL_NAME, dtype={"cnpj": str}).fillna("")
    documental["cnpj"] = _cnpj(documental["cnpj"])
    documental["valor_documental_pct"] = pd.to_numeric(
        documental["valor_documental_pct"], errors="coerce"
    )
    documental = documental.drop_duplicates("cnpj", keep="last")
    frame = frame.merge(
        documental[
            [
                "cnpj",
                "veredito",
                "valor_documental_pct",
                "pagina",
                "trecho",
                "documento",
                "fonte_no_registro",
            ]
        ],
        on="cnpj",
        how="left",
    )
    frame["fidc"] = frame["fundo"]
    frame["resultado_documental"] = frame["veredito"].fillna("").replace(
        "", "sem documento na apuração anterior"
    )
    frame["incluido_slide"] = True
    return frame


__all__ = [
    "DOCUMENTAL_NAME",
    "SCOPE_NAME",
    "TRANCHES_NAME",
    "build_validation_frame",
    "slide_frame",
    "target_validation_frame",
]
