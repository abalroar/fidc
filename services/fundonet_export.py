from __future__ import annotations

from io import BytesIO

import pandas as pd


def build_wide_dataset(contas_df: pd.DataFrame, docs_df: pd.DataFrame) -> pd.DataFrame:
    if contas_df.empty:
        return pd.DataFrame(columns=["conta_codigo", "conta_descricao", "conta_caminho"])

    pivot = contas_df.pivot_table(
        index=["conta_codigo", "conta_descricao", "conta_caminho"],
        columns="coluna_informe",
        values="valor",
        aggfunc="first",
    ).reset_index()

    ordered_columns = [
        "conta_codigo",
        "conta_descricao",
        "conta_caminho",
    ] + docs_df["coluna_informe"].tolist()

    for col in docs_df["coluna_informe"].tolist():
        if col not in pivot.columns:
            pivot[col] = pd.NA

    return pivot[ordered_columns]


def build_excel_bytes(wide_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        wide_df.to_excel(writer, sheet_name="informes_empilhados", index=False)
    return output.getvalue()
