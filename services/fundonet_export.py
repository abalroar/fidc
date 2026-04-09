from __future__ import annotations

from io import BytesIO
import re

import pandas as pd


WIDE_META_COLUMNS = [
    "bloco",
    "sub_bloco",
    "tag",
    "tag_path",
    "descricao",
]

_ILLEGAL_EXCEL_CHARS_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")


def build_wide_dataset(contas_df: pd.DataFrame, competencias_ordenadas: list[str]) -> pd.DataFrame:
    if contas_df.empty:
        return pd.DataFrame(columns=WIDE_META_COLUMNS)

    base = contas_df.copy()
    ordem_por_caminho = (
        base.groupby("tag_path", dropna=False)["ordem_xml"].min().rename("ordem_hierarquica").reset_index()
    )

    pivot = (
        base.pivot_table(
            index=WIDE_META_COLUMNS,
            columns="competencia",
            values="valor_excel",
            aggfunc="first",
            dropna=False,
        )
        .reset_index()
        .merge(ordem_por_caminho, on="tag_path", how="left")
        .sort_values(["ordem_hierarquica", "bloco", "sub_bloco", "tag_path"], kind="stable")
    )

    for competencia in competencias_ordenadas:
        if competencia not in pivot.columns:
            pivot[competencia] = pd.NA

    ordered_columns = WIDE_META_COLUMNS + competencias_ordenadas
    return pivot[ordered_columns]


def build_excel_bytes(
    wide_df: pd.DataFrame,
    listas_df: pd.DataFrame,
    docs_df: pd.DataFrame,
    audit_df: pd.DataFrame,
) -> bytes:
    def _sanitize_for_excel(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        safe_df = df.copy()
        object_columns = safe_df.select_dtypes(include=["object", "string"]).columns
        for column in object_columns:
            safe_df[column] = safe_df[column].map(
                lambda value: _ILLEGAL_EXCEL_CHARS_RE.sub("", value) if isinstance(value, str) else value
            )
        return safe_df

    safe_wide_df = _sanitize_for_excel(wide_df)
    safe_listas_df = _sanitize_for_excel(listas_df)
    safe_docs_df = _sanitize_for_excel(docs_df)
    safe_audit_df = _sanitize_for_excel(audit_df)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        safe_wide_df.to_excel(writer, sheet_name="informes_campos", index=False)
        safe_listas_df.to_excel(writer, sheet_name="estruturas_lista", index=False)
        safe_docs_df.to_excel(writer, sheet_name="documentos", index=False)
        safe_audit_df.to_excel(writer, sheet_name="auditoria", index=False)
    return output.getvalue()
