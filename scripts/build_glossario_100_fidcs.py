"""Congela e audita a amostra de 100 FIDCs usada pelo Glossario.

O script nao altera os dados-fonte. Ele le a competencia_snapshot registrada em
``data/industry_study/metadata.json``, agrega classes no nivel de CNPJ do fundo,
reconstroi o vetor completo da Tabela II e aplica a selecao estratificada descrita
na metodologia do estudo do Glossario.

Uso:
    python scripts/build_glossario_100_fidcs.py
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "industry_study"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "glossario_100_fidcs_20260716"

SEGMENT_COLUMNS = {
    "TAB_II_A_VL_INDUST": "Industrial",
    "TAB_II_B_VL_IMOBIL": "Imobiliário",
    "TAB_II_C_VL_COMERC": "Comercial",
    "TAB_II_D_VL_SERV": "Serviços",
    "TAB_II_E_VL_AGRONEG": "Agronegócio",
    "TAB_II_F_VL_FINANC": "Financeiro",
    "TAB_II_G_VL_CREDITO": "Cartão de crédito",
    "TAB_II_H_VL_FACTOR": "Factoring",
    "TAB_II_I_VL_SETOR_PUBLICO": "Setor público",
    "TAB_II_J_VL_JUDICIAL": "Ações judiciais",
    "TAB_II_K_VL_MARCA": "Marcas e patentes",
}

FINANCIAL_OPENING_COLUMNS = {
    "TAB_II_F1_VL_CRED_PESSOA": "Financeiro — crédito pessoal",
    "TAB_II_F2_VL_CRED_PESSOA_CONSIG": "Financeiro — consignado",
    "TAB_II_F3_VL_CRED_CORP": "Financeiro — crédito corporativo",
    "TAB_II_F4_VL_MIDMARKET": "Financeiro — middle market",
    "TAB_II_F5_VL_VEICULO": "Financeiro — veículos",
    "TAB_II_F6_VL_IMOBIL_EMPRESA": "Financeiro — imobiliário empresarial",
    "TAB_II_F7_VL_IMOBIL_RESID": "Financeiro — imobiliário residencial",
    "TAB_II_F8_VL_OUTRO": "Financeiro — outros",
}


def _slug(value: str) -> str:
    replacements = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
    return re.sub(r"[^a-z0-9]+", "_", value.lower().translate(replacements)).strip("_")


OUTPUT_VECTOR_NAMES = {
    **{column: f"ime_{_slug(label)}" for column, label in SEGMENT_COLUMNS.items()},
    **{
        column: f"ime_abertura_{_slug(label.removeprefix('Financeiro — '))}"
        for column, label in FINANCIAL_OPENING_COLUMNS.items()
    },
}


def _normalize_cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return digits.zfill(14)[-14:]


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "sim", "s"}


def _fic_name_flag(name: object) -> bool:
    normalized = re.sub(r"\s+", " ", str(name or "").upper()).strip()
    return bool(
        re.search(
            r"\bFIC\b|INVESTIMENTO\s+EM\s+COTAS|FI\s+EM\s+COTAS|FUNDO\s+DE\s+COTAS",
            normalized,
        )
    )


def _raw_zip_path(snapshot: str, explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    candidates = (
        REPO_ROOT / ".cache" / "cvm-industry-study" / f"inf_mensal_fidc_{snapshot}.zip",
        REPO_ROOT / ".cache" / "cvm-industry-investors" / f"inf_mensal_fidc_{snapshot}.zip",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Arquivo oficial da competencia {snapshot} nao encontrado em: "
        + ", ".join(str(path) for path in candidates)
    )


def _read_table_ii(zip_path: Path, snapshot: str) -> pd.DataFrame:
    member = f"inf_mensal_fidc_tab_II_{snapshot}.csv"
    with zipfile.ZipFile(zip_path) as archive:
        if member not in archive.namelist():
            raise FileNotFoundError(f"{member} ausente em {zip_path}")
        payload = archive.read(member)
    table = pd.read_csv(
        io.BytesIO(payload),
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    cnpj_column = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in table else "CNPJ_FUNDO"
    table["cnpj_classe"] = table[cnpj_column].map(_normalize_cnpj)
    vector_columns = [*SEGMENT_COLUMNS, *FINANCIAL_OPENING_COLUMNS]
    for column in vector_columns:
        if column not in table:
            table[column] = 0.0
        table[column] = pd.to_numeric(table[column], errors="coerce").fillna(0.0).clip(lower=0.0)
    return table.groupby("cnpj_classe", as_index=False)[vector_columns].sum()


def _load_snapshot(data_dir: Path, snapshot: str, table_ii: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    competence = f"{snapshot[:4]}-{snapshot[4:]}"
    vehicles = pd.read_csv(
        data_dir / "vehicle_monthly.csv.gz",
        low_memory=False,
        dtype={"cnpj": str, "cnpj_fundo": str, "admin_cnpj": str, "gestor_cnpj": str},
    )
    month = vehicles.loc[vehicles["competencia"].astype(str).eq(competence)].copy()
    if month.empty:
        raise ValueError(f"Competencia {competence} ausente de vehicle_monthly.csv.gz")
    month["cnpj_classe"] = month["cnpj"].map(_normalize_cnpj)
    month["cnpj_fundo"] = month["cnpj_fundo"].fillna(month["cnpj"]).map(_normalize_cnpj)
    month["pl"] = pd.to_numeric(month["pl"], errors="coerce")

    audit = {
        "n_veiculos_snapshot": int(len(month)),
        "n_pl_nulo": int(month["pl"].isna().sum()),
        "n_pl_zero": int(month["pl"].eq(0).sum()),
        "n_pl_negativo": int(month["pl"].lt(0).sum()),
        "pl_negativo_excluido": float(month.loc[month["pl"].lt(0), "pl"].sum()),
        "pl_soma_todos_registros": float(month["pl"].sum()),
    }
    eligible = month.loc[month["pl"].notna() & month["pl"].gt(0)].copy()
    audit["n_veiculos_pl_positivo"] = int(len(eligible))
    audit["pl_elegivel"] = float(eligible["pl"].sum())

    joined = eligible.merge(table_ii, on="cnpj_classe", how="left")
    vector_columns = [*SEGMENT_COLUMNS, *FINANCIAL_OPENING_COLUMNS]
    joined[vector_columns] = joined[vector_columns].fillna(0.0)
    joined["fic_flag_ampliada_classe"] = joined.apply(
        lambda row: _as_bool(row.get("is_fic_fidc")) or _fic_name_flag(row.get("denominacao")),
        axis=1,
    )
    return joined, audit


def _join_unique(values: pd.Series) -> str:
    clean = sorted({str(value).strip() for value in values if str(value).strip() and str(value) != "nan"})
    return ";".join(clean)


def _aggregate_funds(joined: pd.DataFrame) -> pd.DataFrame:
    vector_columns = [*SEGMENT_COLUMNS, *FINANCIAL_OPENING_COLUMNS]
    name_rows = (
        joined.sort_values(["cnpj_fundo", "pl", "cnpj_classe"], ascending=[True, False, True])
        .drop_duplicates("cnpj_fundo")
        .set_index("cnpj_fundo")
    )
    aggregation: dict[str, object] = {
        "pl": "sum",
        "cnpj_classe": _join_unique,
        "is_fic_fidc": lambda values: any(_as_bool(value) for value in values),
        "fic_flag_ampliada_classe": "max",
        "admin_nome": _join_unique,
        "admin_cnpj": lambda values: _join_unique(values.map(_normalize_cnpj)),
        "gestor_nome": _join_unique,
        "gestor_cnpj": lambda values: _join_unique(values.map(_normalize_cnpj)),
    }
    aggregation.update({column: "sum" for column in vector_columns})
    funds = joined.groupby("cnpj_fundo", as_index=False).agg(aggregation)
    funds["nome"] = funds["cnpj_fundo"].map(name_rows["denominacao"])
    funds["n_classes_componentes"] = funds["cnpj_classe"].str.count(";") + 1
    funds["flag_fic_fidc_legado"] = funds["is_fic_fidc"].map(_as_bool)
    funds["flag_fic_fidc"] = funds["fic_flag_ampliada_classe"].map(_as_bool) | funds["nome"].map(_fic_name_flag)
    funds = funds.drop(columns=["is_fic_fidc", "fic_flag_ampliada_classe"])
    return funds


def _classify_segments(funds: pd.DataFrame) -> pd.DataFrame:
    top_columns = list(SEGMENT_COLUMNS)
    financial_columns = list(FINANCIAL_OPENING_COLUMNS)
    top_winner_column = funds[top_columns].idxmax(axis=1)
    top_winner_value = funds[top_columns].max(axis=1)
    table_ii_total = funds[top_columns].sum(axis=1)
    financial_winner_column = funds[financial_columns].idxmax(axis=1)
    financial_winner_value = funds[financial_columns].max(axis=1)

    funds["segmento_oficial_tabela_ii"] = top_winner_column.map(SEGMENT_COLUMNS)
    no_segmentation = table_ii_total.le(0)
    funds.loc[no_segmentation, "segmento_oficial_tabela_ii"] = "Sem segmentação IME"
    funds["abertura_financeira_tabela_ii"] = ""
    is_financial = funds["segmento_oficial_tabela_ii"].eq("Financeiro")
    funds.loc[is_financial, "abertura_financeira_tabela_ii"] = financial_winner_column.loc[
        is_financial
    ].map(FINANCIAL_OPENING_COLUMNS)
    funds["subtipo_cvm_ime"] = funds["segmento_oficial_tabela_ii"]
    funds.loc[is_financial, "subtipo_cvm_ime"] = funds.loc[
        is_financial, "abertura_financeira_tabela_ii"
    ]
    funds.loc[no_segmentation, "subtipo_cvm_ime"] = "Sem segmentação IME"

    dominant_value = top_winner_value.copy()
    dominant_value.loc[is_financial] = financial_winner_value.loc[is_financial]
    funds["valor_segmento_dominante"] = dominant_value
    funds["total_tabela_ii"] = table_ii_total
    funds["participacao_segmento_dominante"] = (dominant_value / table_ii_total).where(
        table_ii_total.gt(0)
    )
    funds["flag_hibrido_multissegmento"] = pd.Series(pd.NA, index=funds.index, dtype="boolean")
    funds.loc[~no_segmentation, "flag_hibrido_multissegmento"] = funds.loc[
        ~no_segmentation, "participacao_segmento_dominante"
    ].lt(0.60)
    return funds


def _document_status(selection: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    inventory_path = data_dir / "document_inventory.csv.gz"
    inventory = pd.read_csv(inventory_path, low_memory=False, dtype=str)
    inventory["cnpj_fundo"] = inventory["cnpj_fundo"].map(_normalize_cnpj)
    inventory["exists_now"] = inventory["local_path"].map(lambda value: (REPO_ROOT / str(value)).is_file())
    inventory["is_primary_pdf"] = inventory.apply(
        lambda row: row["exists_now"]
        and str(row.get("content_kind", "")).lower() == "pdf"
        and str(row.get("local_path", "")).lower().endswith(".pdf"),
        axis=1,
    )
    inv_stats = inventory.groupby("cnpj_fundo").agg(
        documentos_inventariados=("document_key", "size"),
        documentos_locais_inventario=("exists_now", "sum"),
        pdfs_primarios_locais_inventario=("is_primary_pdf", "sum"),
    )

    rows: list[dict[str, object]] = []
    for selected in selection.itertuples(index=False):
        cnpj = selected.cnpj_fundo
        component_cnpjs = {
            _normalize_cnpj(value)
            for value in str(selected.cnpjs_classes_componentes).split(";")
            if _normalize_cnpj(value)
        }
        document_cnpjs = {cnpj, *component_cnpjs}
        primary_pdfs: list[Path] = []
        for document_cnpj in sorted(document_cnpjs):
            official_dir = REPO_ROOT / "data" / "raw" / "industry_large_funds" / document_cnpj
            if official_dir.is_dir():
                primary_pdfs.extend(sorted(official_dir.glob("*.pdf")))
        unique_pdf_hashes: set[str] = set()
        for pdf_path in primary_pdfs:
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            unique_pdf_hashes.add(digest)
        stats = inv_stats.loc[cnpj].to_dict() if cnpj in inv_stats.index else {}
        listed = int(stats.get("documentos_inventariados", 0))
        local_derivatives = int(stats.get("documentos_locais_inventario", 0))
        primary_count = len(unique_pdf_hashes) + int(stats.get("pdfs_primarios_locais_inventario", 0))
        if primary_count:
            status = "primário local disponível"
        elif local_derivatives:
            status = "cache-only; primário ausente"
        elif listed:
            status = "inventariado; primário ausente"
        else:
            status = "sem documento inventariado"
        rows.append(
            {
                "cnpj_fundo": cnpj,
                "documentos_inventariados": listed,
                "derivados_locais": local_derivatives,
                "pdfs_primarios_locais": primary_count,
                "cobertura_documental_inicial": status,
            }
        )
    return pd.DataFrame(rows)


def _select_100(funds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = funds.sort_values(["pl", "cnpj_fundo"], ascending=[False, True]).reset_index(drop=True)
    ordered["ranking_global"] = range(1, len(ordered) + 1)
    ordered["ranking_segmento"] = ordered.groupby("subtipo_cvm_ime", sort=False).cumcount() + 1

    coverage = ordered.loc[ordered["ranking_segmento"].le(2)].copy()
    coverage["motivo_selecao"] = coverage["ranking_segmento"].map(
        {1: "cobertura_1", 2: "cobertura_2"}
    )
    remaining_slots = 100 - len(coverage)
    if remaining_slots < 0:
        raise AssertionError("A cobertura minima ocupa mais de 100 vagas")
    remaining = ordered.loc[~ordered["cnpj_fundo"].isin(coverage["cnpj_fundo"])].head(
        remaining_slots
    ).copy()
    remaining["motivo_selecao"] = "top_pl"
    selection = pd.concat([coverage, remaining], ignore_index=True)
    selection = selection.sort_values(["pl", "cnpj_fundo"], ascending=[False, True]).reset_index(drop=True)

    industry_pl = float(ordered["pl"].sum())
    segment_pl = ordered.groupby("subtipo_cvm_ime")["pl"].sum()
    selection["participacao_pl_segmento"] = selection.apply(
        lambda row: row["pl"] / segment_pl.loc[row["subtipo_cvm_ime"]], axis=1
    )
    selection["participacao_pl_industria"] = selection["pl"] / industry_pl
    selection["pl_classes_reconciliado"] = True

    vector_columns = [*SEGMENT_COLUMNS, *FINANCIAL_OPENING_COLUMNS]
    selection = selection.rename(columns=OUTPUT_VECTOR_NAMES)
    ordered = ordered.rename(columns=OUTPUT_VECTOR_NAMES)
    selection = selection.rename(columns={"cnpj_classe": "cnpjs_classes_componentes", "pl": "pl_agregado"})
    ordered = ordered.rename(columns={"cnpj_classe": "cnpjs_classes_componentes", "pl": "pl_agregado"})
    expected_vector_columns = [OUTPUT_VECTOR_NAMES[column] for column in vector_columns]
    front = [
        "competencia",
        "cnpj_fundo",
        "nome",
        "cnpjs_classes_componentes",
        "n_classes_componentes",
        "pl_agregado",
        "ranking_global",
        "segmento_oficial_tabela_ii",
        "abertura_financeira_tabela_ii",
        "subtipo_cvm_ime",
        "ranking_segmento",
        "participacao_segmento_dominante",
        "flag_hibrido_multissegmento",
        "flag_fic_fidc",
        "flag_fic_fidc_legado",
        "motivo_selecao",
        "participacao_pl_segmento",
        "participacao_pl_industria",
        "pl_classes_reconciliado",
        "admin_nome",
        "admin_cnpj",
        "gestor_nome",
        "gestor_cnpj",
        "valor_segmento_dominante",
        "total_tabela_ii",
        *expected_vector_columns,
    ]
    selection = selection[[column for column in front if column in selection.columns]]
    return selection, ordered


def _coverage_table(selection: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    selected_ids = set(selection["cnpj_fundo"])
    universe = universe.copy()
    universe["selecionado"] = universe["cnpj_fundo"].isin(selected_ids)
    rows: list[dict[str, object]] = []
    for subtype, group in universe.groupby("subtipo_cvm_ime", sort=True):
        selected = group.loc[group["selecionado"]]
        industry_pl = float(group["pl_agregado"].sum())
        selected_pl = float(selected["pl_agregado"].sum())
        industry_ex_fic = float(group.loc[~group["flag_fic_fidc"], "pl_agregado"].sum())
        selected_ex_fic = float(selected.loc[~selected["flag_fic_fidc"], "pl_agregado"].sum())
        rows.append(
            {
                "subtipo_cvm_ime": subtype,
                "fundos_industria": int(len(group)),
                "fundos_selecionados": int(len(selected)),
                "pl_industria": industry_pl,
                "pl_selecionado": selected_pl,
                "cobertura_pl_bruta": selected_pl / industry_pl if industry_pl else None,
                "fic_fidc_industria": int(group["flag_fic_fidc"].sum()),
                "fic_fidc_selecionados": int(selected["flag_fic_fidc"].sum()),
                "pl_industria_ex_fic": industry_ex_fic,
                "pl_selecionado_ex_fic": selected_ex_fic,
                "cobertura_pl_ex_fic": selected_ex_fic / industry_ex_fic if industry_ex_fic else None,
            }
        )
    return pd.DataFrame(rows)


def build(data_dir: Path, output_dir: Path, raw_zip: str | None = None) -> dict[str, object]:
    metadata = json.loads((data_dir / "metadata.json").read_text(encoding="utf-8"))
    snapshot = re.sub(r"\D", "", str(metadata["competencia_snapshot"]))[:6]
    if len(snapshot) != 6:
        raise ValueError(f"competencia_snapshot invalida: {metadata['competencia_snapshot']!r}")
    competence = f"{snapshot[:4]}-{snapshot[4:]}"
    zip_path = _raw_zip_path(snapshot, raw_zip)
    table_ii = _read_table_ii(zip_path, snapshot)
    joined, snapshot_audit = _load_snapshot(data_dir, snapshot, table_ii)
    funds = _classify_segments(_aggregate_funds(joined))
    funds["competencia"] = competence
    selection, universe = _select_100(funds)
    document_status = _document_status(selection, data_dir)
    selection = selection.merge(document_status, on="cnpj_fundo", how="left")
    coverage = _coverage_table(selection, universe)

    occupied = set(universe["subtipo_cvm_ime"])
    all_official_strata = (set(SEGMENT_COLUMNS.values()) - {"Financeiro"}) | set(
        FINANCIAL_OPENING_COLUMNS.values()
    )
    empty_official = sorted(all_official_strata - occupied)
    selected_occupied = set(selection["subtipo_cvm_ime"])
    validations = {
        "exactly_100_unique_funds": bool(
            len(selection) == 100 and selection["cnpj_fundo"].nunique() == 100
        ),
        "no_duplicate_funds": bool(not selection["cnpj_fundo"].duplicated().any()),
        "all_occupied_strata_represented": bool(occupied.issubset(selected_occupied)),
        "all_fund_class_sums_reconciled": bool(selection["pl_classes_reconciliado"].all()),
        "all_100_have_document_status": bool(
            selection["cobertura_documental_inicial"].notna().all()
        ),
    }
    if not all(validations.values()):
        raise AssertionError(validations)

    industry_pl = float(universe["pl_agregado"].sum())
    selected_pl = float(selection["pl_agregado"].sum())
    industry_ex_fic = float(universe.loc[~universe["flag_fic_fidc"], "pl_agregado"].sum())
    selected_ex_fic = float(selection.loc[~selection["flag_fic_fidc"], "pl_agregado"].sum())
    official_snapshot_pl = float(snapshot_audit["pl_soma_todos_registros"])
    reconciliation = official_snapshot_pl - (
        industry_pl + float(snapshot_audit["pl_negativo_excluido"])
    )

    manifest = {
        "schema_version": "glossario-100-fidcs/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "competencia_snapshot": snapshot,
        "competencia": competence,
        "source_metadata": str((data_dir / "metadata.json").relative_to(REPO_ROOT)),
        "source_vehicle_monthly": str((data_dir / "vehicle_monthly.csv.gz").relative_to(REPO_ROOT)),
        "source_table_ii_zip": str(zip_path.relative_to(REPO_ROOT)),
        "selection_algorithm": [
            "agregar PL positivo no nivel cnpj_fundo, somando classes componentes",
            "classificar pelo maior dos 11 segmentos oficiais da Tabela II",
            "quando Financeiro vencer, substituir pela maior abertura F1-F8",
            "classificar total zero como Sem segmentação IME",
            "selecionar ate dois maiores por estrato ocupado",
            "completar por PL global; desempate por CNPJ crescente",
        ],
        "dominant_share_rule": "maior abertura F1-F8 / soma dos 11 blocos quando Financeiro vence; caso contrario, maior bloco / soma dos 11 blocos",
        "fic_fidc_rule": "flag legada preservada e flag ampliada por nomenclatura; cobertura ex-FIC usa a flag ampliada",
        "snapshot_reconciliation": {
            **snapshot_audit,
            "n_fundos_elegiveis": int(len(universe)),
            "pl_fundos_elegiveis": industry_pl,
            "residuo_reconciliacao": reconciliation,
        },
        "sample": {
            "n_fundos": int(len(selection)),
            "pl_bruto": selected_pl,
            "cobertura_pl_bruta": selected_pl / industry_pl,
            "n_fic_fidc": int(selection["flag_fic_fidc"].sum()),
            "pl_ex_fic": selected_ex_fic,
            "cobertura_pl_ex_fic": selected_ex_fic / industry_ex_fic,
            "n_estratos_ocupados": int(len(occupied)),
        },
        "segmentos_oficiais_sem_populacao": empty_official,
        "validations": validations,
        "limitations": [
            "Sem segmentação IME é estrato de qualidade de dados, não subtipo oficial.",
            "A flag FIC-FIDC ampliada é inferida da denominação e não substitui validação documental.",
            "Valores negativos e zero são excluídos por regra; a reconciliação os evidencia separadamente.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    selection.to_csv(output_dir / "selection_100.csv", index=False)
    coverage.to_csv(output_dir / "selection_coverage_by_subtype.csv", index=False)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--raw-zip", default="")
    args = parser.parse_args()
    manifest = build(args.data_dir.resolve(), args.output_dir.resolve(), args.raw_zip or None)
    print(json.dumps(manifest["sample"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
