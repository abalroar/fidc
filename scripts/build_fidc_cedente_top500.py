#!/usr/bin/env python3
"""Materialize the four-competence Top-500 cedent audit.

The build reads CVM Table I and Table IV snapshots, applies the fund-first
ranking and dominant-cedent rules from ``industry_cedente_top500``, and writes
versioned, auditable outputs for the workbook and Streamlit consumers.

Registry data can come from a compact Receita snapshot produced by
``extract_receita_cnpj_registry.py``.  The audited reference workbook remains
an explicit bootstrap/gabarito input while the official Receita bulk download
is unavailable; it is never treated as a live API.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_cedente_top500 import (  # noqa: E402
    DEFAULT_COMPETENCES,
    DEFAULT_CUTOFF_RANK,
    SCHEMA_VERSION,
    build_multi_competence_top500,
    normalize_document,
)


COMPETENCE_LABELS = {
    "202312": "dez/23",
    "202412": "dez/24",
    "202512": "dez/25",
    "202606": "jun/26",
}

CVM_SOURCE_URLS = {
    "202312": "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/HIST/inf_mensal_fidc_2023.zip",
    "202412": "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/HIST/inf_mensal_fidc_2024.zip",
    "202512": "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202512.zip",
    "202606": "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202606.zip",
}

REFERENCE_REGISTRY_SHEET = "Cedentes · por competência"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digits(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\D", "", text)


def _format_document(digits: str, kind: str) -> str:
    if kind == "CNPJ" and len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    if kind == "CPF" and len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return digits


def _stable_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def _write_csv(frame: pd.DataFrame, path: Path, *, compressed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _stable_csv_bytes(frame)
    if compressed:
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                zipped.write(payload)
    else:
        path.write_bytes(payload)


def _write_json(value: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_registry_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _read_reference_registry(path: Path) -> pd.DataFrame:
    """Read the audited registry slice without importing analytical totals."""

    frame = pd.read_excel(
        path,
        sheet_name=REFERENCE_REGISTRY_SHEET,
        header=3,
        dtype=str,
    ).fillna("")
    if frame.empty:
        raise ValueError(f"aba {REFERENCE_REGISTRY_SHEET!r} está vazia")
    required = {"CNPJ/CPF", "Razão social", "Segmento", "Critério do segmento"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"gabarito sem colunas {sorted(missing)}")
    fields = [
        "CNPJ/CPF",
        "Razão social",
        "Natureza do cedente",
        "Segmento",
        "Critério do segmento",
        "CNAE (cód.)",
        "CNAE principal",
        "Seção CNAE",
        "Porte Receita",
        "Capital social (R$)",
        "Simples",
        "MEI",
        "UF",
        "Município",
        "Situação cadastral",
        "Matriz/filial",
        "Fonte cadastral",
        "Data do cadastro",
    ]
    for field in fields:
        if field not in frame:
            frame[field] = ""
    frame = frame[fields].copy()
    frame["_doc_key"] = frame["CNPJ/CPF"].map(
        lambda value: normalize_document(value)["documento_key"]
    )
    frame["_filled"] = frame.replace("", pd.NA).notna().sum(axis=1)
    frame["_stable"] = frame.fillna("").astype(str).agg("\x1f".join, axis=1)
    return (
        frame.sort_values(
            ["_doc_key", "_filled", "_stable"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .drop_duplicates("_doc_key", keep="first")
        .drop(columns=["_doc_key", "_filled", "_stable"])
        .reset_index(drop=True)
    )


def _resolve_cvm_source(cvm_dir: Path, competence: str) -> Path:
    year = competence[:4]
    candidates = (
        cvm_dir / f"inf_mensal_fidc_{competence}.zip",
        cvm_dir / f"inf_mensal_fidc_{year}.zip",
        cvm_dir / f"{competence}.zip",
        cvm_dir / f"{year}.zip",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"fonte CVM de {competence} ausente; procurados: "
        + ", ".join(str(item) for item in candidates)
    )


def _human_links(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    links = frames["vinculos"].copy()
    top = frames["top500"].copy()
    if links.empty:
        return links
    top_fields = top[
        [
            "competencia",
            "cnpj_fundo",
            "administrador",
            "pl_industria_acumulado_pct",
        ]
    ].drop_duplicates(["competencia", "cnpj_fundo"])
    links = links.merge(
        top_fields,
        on=["competencia", "cnpj_fundo"],
        how="left",
        validate="many_to_one",
    )
    links["CNPJ do fundo"] = links["cnpj_fundo"].map(
        lambda value: _format_document(_digits(value).zfill(14), "CNPJ")
    )
    links["Cedente formatado"] = [
        _format_document(_digits(document), str(kind))
        for document, kind in zip(links["cedente_documento"], links["cedente_tipo"])
    ]
    links["Data"] = links["competencia"].map(COMPETENCE_LABELS)
    links["Simples"] = links.get("simples", "")
    links["MEI"] = links.get("mei", "")
    links["Documento fictício?"] = links["cedente_documento_ficticio_flag"].map(
        {True: "Sim", False: "Não"}
    )
    links["Zero à esquerda recuperado?"] = links["cedente_cnpj_zfill_flag"].map(
        {True: "Sim", False: "Não"}
    )
    links["Cedente dominante?"] = links["cedente_dominante_flag"].map(
        {True: "Sim", False: "Não"}
    )
    selected = pd.DataFrame(
        {
            "Competência": links["competencia"],
            "Data": links["Data"],
            "Rank PL": links["rank_pl"],
            "CNPJ do fundo": links["CNPJ do fundo"],
            "FIDC": links["fundo"],
            "PL do fundo (R$)": links["pl_fundo_reais"],
            "% PL acum.": links["pl_industria_acumulado_pct"],
            "Bloco": links["bloco"].map(
                {
                    "com_retencao": "com retenção de risco",
                    "sem_retencao": "sem retenção de risco",
                }
            ).fillna(links["bloco"]),
            "Ordem": links["ordem"],
            "CNPJ/CPF do cedente": links["cedente_documento"],
            "Cedente formatado": links["Cedente formatado"],
            "Tipo": links["cedente_tipo"],
            "% na carteira": links["percentual_cedente"],
            "Razão social do cedente": links.get("razao_social", ""),
            "CNAE (cód.)": links.get("cnae_codigo", ""),
            "CNAE principal": links.get("cnae_principal", ""),
            "Seção CNAE": links.get("secao_cnae", ""),
            "Natureza do cedente": links.get("natureza_cedente", ""),
            "Porte Receita": links.get("porte_receita", ""),
            "Capital social (R$)": links.get("capital_social_reais", ""),
            "Simples": links["Simples"],
            "MEI": links["MEI"],
            "Situação cadastral": links.get("situacao_cadastral", ""),
            "Matriz/filial": links.get("matriz_filial", ""),
            "UF": links.get("uf", ""),
            "Município": links.get("municipio", ""),
            "Segmento": links.get("segmento", ""),
            "Critério do segmento": links.get("criterio_segmento", ""),
            "Status do documento": links["cedente_documento_status"],
            "Documento fictício?": links["Documento fictício?"],
            "Zero à esquerda recuperado?": links["Zero à esquerda recuperado?"],
            "Cedente dominante?": links["Cedente dominante?"],
        }
    )
    return selected.sort_values(
        ["Competência", "Rank PL", "Bloco", "Ordem", "CNPJ/CPF do cedente"],
        kind="mergesort",
    ).reset_index(drop=True)


def _human_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return pd.DataFrame(
        {
            "Competência": frame["competencia"],
            "Data": frame["competencia"].map(COMPETENCE_LABELS),
            "Rank PL": frame["rank_pl"],
            "CNPJ do fundo": frame["cnpj_fundo"].map(
                lambda value: _format_document(_digits(value).zfill(14), "CNPJ")
            ),
            "FIDC": frame["fundo"],
            "PL do fundo (R$)": frame["pl_fundo_reais"],
            "% PL acum.": frame["pl_industria_acumulado_pct"],
            "Motivo": frame["motivo_sem_cedente"],
        }
    ).sort_values(["Competência", "Rank PL"], kind="mergesort").reset_index(drop=True)


def _registry_by_competence(links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return links.copy()
    rows: list[dict[str, object]] = []
    group_columns = ["Competência", "CNPJ/CPF do cedente"]
    for (competence, document), group in links.groupby(group_columns, sort=True, dropna=False):
        unique_funds = group.drop_duplicates("CNPJ do fundo")
        first = group.iloc[0]
        rows.append(
            {
                "Competência": competence,
                "Data": first["Data"],
                "CNPJ/CPF": document,
                "Formatado": first["Cedente formatado"],
                "Tipo": first["Tipo"],
                "Razão social": first["Razão social do cedente"],
                "Natureza do cedente": first["Natureza do cedente"],
                "Segmento": first["Segmento"],
                "Critério do segmento": first["Critério do segmento"],
                "CNAE (cód.)": first["CNAE (cód.)"],
                "CNAE principal": first["CNAE principal"],
                "Seção CNAE": first["Seção CNAE"],
                "Porte Receita": first["Porte Receita"],
                "Capital social (R$)": first["Capital social (R$)"],
                "Simples": first["Simples"],
                "MEI": first["MEI"],
                "Situação cadastral": first["Situação cadastral"],
                "Matriz/filial": first["Matriz/filial"],
                "UF": first["UF"],
                "Município": first["Município"],
                "Fundos": int(unique_funds["CNPJ do fundo"].nunique()),
                "PL alcançado (R$)": float(unique_funds["PL do fundo (R$)"].sum()),
                "Maior % em um fundo": pd.to_numeric(
                    group["% na carteira"], errors="coerce"
                ).max(),
            }
        )
    return pd.DataFrame(rows)


def _segment_evolution(links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return links.copy()
    rows: list[dict[str, object]] = []
    for (competence, segment), group in links.groupby(
        ["Competência", "Segmento"], sort=True, dropna=False
    ):
        reached = group.drop_duplicates("CNPJ do fundo")
        capital = pd.to_numeric(group["Capital social (R$)"], errors="coerce")
        rows.append(
            {
                "Competência": competence,
                "Data": group.iloc[0]["Data"],
                "Segmento": segment,
                "Cedentes únicos": int(group["CNPJ/CPF do cedente"].nunique()),
                "Vínculos": int(len(group)),
                "PL alcançado (R$)": float(reached["PL do fundo (R$)"].sum()),
                "% do PL do Top 500": pd.NA,
                "Capital social mediano (R$)": capital.median(),
            }
        )
    return pd.DataFrame(rows)


def _human_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return pd.DataFrame(
        {
            "Competência": frame["competencia"],
            "Data": frame["competencia"].map(COMPETENCE_LABELS),
            "Fundos na indústria": frame["fundos_industria"],
            "PL total da indústria (R$)": frame["pl_industria_reais"],
            "PL do Top 500 (R$)": frame["pl_top500_reais"],
            "% do PL total": frame["pl_top500_sobre_industria_pct"],
            "PL do 500º fundo (R$)": frame["pl_ultimo_fundo_top_reais"],
            "Fundos que identificam cedente": frame["fundos_com_cedente_real"],
            "% dos 500": frame["fundos_com_cedente_real_pct"],
            "PL desses fundos (R$)": frame["pl_fundos_com_cedente_real_reais"],
            "% do PL do Top 500": frame["pl_identificado_sobre_top500_pct"],
            "Fundos sem cedente": frame["fundos_sem_cedente_real"],
            "PL sem cedente (R$)": frame["pl_sem_cedente_real_reais"],
            "Vínculos fictícios": frame["vinculos_documento_ficticio"],
            "CNPJs com zero recuperado": frame["vinculos_cnpj_zfill"],
            "Cedentes reais distintos": frame["cedentes_reais_distintos"],
        }
    )


def _human_segment_pl(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return pd.DataFrame(
        {
            "Competência": frame["competencia"],
            "Data": frame["competencia"].map(COMPETENCE_LABELS),
            "Segmento": frame["segmento"],
            "PL dominante (R$)": frame["pl_dominante_reais"],
            "% do Top 500": frame["pl_sobre_top500_pct"],
            "% do PL identificado": frame["pl_sobre_identificado_pct"],
            "Fundos (dominante)": frame["fundos_dominante"],
            "Cedentes únicos": frame["cedentes_dominantes_distintos"],
            "PL Top 500 · denominador (R$)": frame["pl_top500_denominador_reais"],
            "PL identificado · denominador (R$)": frame[
                "pl_identificado_denominador_reais"
            ],
        }
    )


def _presence_history(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return registry.copy()
    rows: list[dict[str, object]] = []
    labels = [COMPETENCE_LABELS[item] for item in DEFAULT_COMPETENCES]
    for document, group in registry.groupby("CNPJ/CPF", sort=True, dropna=False):
        first = group.iloc[0]
        by_comp = group.set_index("Competência")["PL alcançado (R$)"].to_dict()
        present = [
            COMPETENCE_LABELS[item]
            for item in DEFAULT_COMPETENCES
            if item in set(group["Competência"].astype(str))
        ]
        rows.append(
            {
                "CNPJ/CPF": document,
                "Formatado": first["Formatado"],
                "Razão social": first["Razão social"],
                "Natureza do cedente": first["Natureza do cedente"],
                "Segmento": first["Segmento"],
                "CNAE principal": first["CNAE principal"],
                "UF": first["UF"],
                **{
                    f"PL {label} (R$)": by_comp.get(competence, pd.NA)
                    for competence, label in zip(DEFAULT_COMPETENCES, labels)
                },
                "Competências": len(present),
                "Presente em": " · ".join(present),
                "Situação": (
                    "Presente em jun/26"
                    if "jun/26" in present
                    else "Saiu do Top 500"
                ),
            }
        )
    return pd.DataFrame(rows)


def _cadastro_master(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return registry.copy()
    fields = [
        "CNPJ/CPF",
        "Formatado",
        "Tipo",
        "Razão social",
        "Natureza do cedente",
        "Segmento",
        "Critério do segmento",
        "CNAE (cód.)",
        "CNAE principal",
        "Seção CNAE",
        "Porte Receita",
        "Capital social (R$)",
        "Simples",
        "MEI",
        "Situação cadastral",
        "Matriz/filial",
        "UF",
        "Município",
    ]
    frame = registry[fields].copy()
    frame["_filled"] = frame.replace("", pd.NA).notna().sum(axis=1)
    frame["_stable"] = frame.fillna("").astype(str).agg("\x1f".join, axis=1)
    return (
        frame.sort_values(
            ["CNPJ/CPF", "_filled", "_stable"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .drop_duplicates("CNPJ/CPF", keep="first")
        .drop(columns=["_filled", "_stable"])
        .reset_index(drop=True)
    )


def _receita_targets(links: pd.DataFrame) -> pd.DataFrame:
    """Return the real CNPJ queue consumed by the offline Receita reader."""

    if links.empty:
        return pd.DataFrame(
            columns=["CNPJ", "CNPJ formatado", "Competências", "Primeira competência", "Última competência"]
        )
    eligible = links.loc[
        links["Tipo"].eq("CNPJ")
        & links["Documento fictício?"].eq("Não")
        & ~links["Status do documento"].eq("documento_irregular")
    ].copy()
    rows: list[dict[str, object]] = []
    for document, group in eligible.groupby("CNPJ/CPF do cedente", sort=True):
        competences = sorted(set(group["Competência"].astype(str)))
        rows.append(
            {
                "CNPJ": str(document).zfill(14),
                "CNPJ formatado": group.iloc[0]["Cedente formatado"],
                "Competências": " · ".join(competences),
                "Primeira competência": competences[0],
                "Última competência": competences[-1],
            }
        )
    return pd.DataFrame(rows)


def _add_segment_denominator(evolution: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    if evolution.empty:
        return evolution
    denominators = coverage.set_index("Competência")["PL do Top 500 (R$)"].to_dict()
    evolution["% do PL do Top 500"] = [
        float(row["PL alcançado (R$)"]) / float(denominators[row["Competência"]])
        if denominators.get(row["Competência"])
        else pd.NA
        for _, row in evolution.iterrows()
    ]
    return evolution


def _source_descriptor(path: Path, *, role: str, url: str = "") -> dict[str, object]:
    descriptor: dict[str, object] = {
        "name": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "role": role,
    }
    if url:
        descriptor["official_url"] = url
    return descriptor


def _output_descriptor(path: Path, *, rows: int | None = None) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "name": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }
    if rows is not None:
        descriptor["rows"] = rows
    return descriptor


def materialize(
    *,
    cvm_dir: Path,
    output_dir: Path,
    registry: pd.DataFrame,
    registry_source: Path,
) -> dict[str, object]:
    sources: dict[str, tuple[Path, Path]] = {}
    for competence in DEFAULT_COMPETENCES:
        path = _resolve_cvm_source(cvm_dir, competence)
        sources[competence] = (path, path)
    frames = build_multi_competence_top500(
        sources,
        cadastro=registry,
        registry_overrides=registry,
        cutoff_rank=DEFAULT_CUTOFF_RANK,
    )
    links = _human_links(frames)
    registry_by_comp = _registry_by_competence(links)
    coverage = _human_coverage(frames["cobertura"])
    gaps = _human_gaps(frames["fundos_sem_cedente"])
    segment_pl = _human_segment_pl(frames["pl_por_segmento"])
    evolution = _add_segment_denominator(_segment_evolution(links), coverage)
    presence = _presence_history(registry_by_comp)
    cadastro_master = _cadastro_master(registry_by_comp)
    receita_targets = _receita_targets(links)
    exclusions = frames["exclusoes"].copy()
    source_repairs = frames["reparos_fonte"].copy()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_specs = {
        "fidc_cedentes_top500_2023_2026.csv.gz": (links, True),
        "fidc_cedentes_por_competencia_2023_2026.csv.gz": (registry_by_comp, True),
        "fidc_cedentes_fundos_sem_cedente_2023_2026.csv.gz": (gaps, True),
        "fidc_cedentes_evolucao_segmento_2023_2026.csv": (evolution, False),
        "fidc_cedentes_presenca_tempo_2023_2026.csv.gz": (presence, True),
        "fidc_cedentes_cobertura_top500_2023_2026.csv": (coverage, False),
        "fidc_cedentes_pl_segmento_2023_2026.csv": (segment_pl, False),
        "fidc_cedentes_cadastro_master.csv.gz": (cadastro_master, True),
        "fidc_cedentes_receita_targets.csv": (receita_targets, False),
        "fidc_cedentes_exclusoes_2023_2026.csv.gz": (exclusions, True),
        "fidc_cedentes_reparos_fonte_2023_2026.csv": (source_repairs, False),
    }
    for filename, (frame, compressed) in output_specs.items():
        _write_csv(frame, output_dir / filename, compressed=compressed)

    for competence in DEFAULT_COMPETENCES:
        competence_dir = output_dir / competence
        competence_dir.mkdir(parents=True, exist_ok=True)
        filters = {
            "top500": frames["top500"]["competencia"].eq(competence),
            "vinculos": frames["vinculos"]["competencia"].eq(competence),
            "fundos_sem_cedente": frames["fundos_sem_cedente"]["competencia"].eq(competence),
            "exclusoes": frames["exclusoes"]["competencia"].eq(competence),
            "cobertura": frames["cobertura"]["competencia"].eq(competence),
            "pl_por_segmento": frames["pl_por_segmento"]["competencia"].eq(competence),
            "reparos_fonte": frames["reparos_fonte"]["competencia"].eq(competence),
        }
        for name, mask in filters.items():
            _write_csv(
                frames[name].loc[mask].reset_index(drop=True),
                competence_dir / f"fidc_cedentes_{name}_{competence}.csv.gz",
                compressed=True,
            )

    metrics = {
        str(row["Competência"]): {
            "fundos_industria": int(row["Fundos na indústria"]),
            "pl_industria_reais": float(row["PL total da indústria (R$)"]),
            "pl_top500_reais": float(row["PL do Top 500 (R$)"]),
            "pl_top500_sobre_industria_pct": float(row["% do PL total"]),
            "pl_ultimo_fundo_top_reais": float(row["PL do 500º fundo (R$)"]),
            "fundos_com_cedente_real": int(row["Fundos que identificam cedente"]),
            "fundos_sem_cedente_real": int(row["Fundos sem cedente"]),
            "pl_sem_cedente_real_reais": float(row["PL sem cedente (R$)"]),
        }
        for _, row in coverage.iterrows()
    }
    generated_at = datetime.now(timezone.utc).isoformat()
    registry_is_bootstrap = registry_source.suffix.lower() in {".xlsx", ".xls"}
    registry_role = (
        "gabarito auditado fornecido pelo usuário; bootstrap temporário, sem consulta BrasilAPI"
        if registry_is_bootstrap
        else "recorte cadastral local produzido pelo processamento em massa da Receita Federal"
    )
    per_competence_manifest_paths: list[Path] = []
    for competence in DEFAULT_COMPETENCES:
        competence_dir = output_dir / competence
        data_paths = sorted(
            path
            for path in competence_dir.glob(f"fidc_cedentes_*_{competence}.csv.gz")
            if path.is_file()
        )
        repair_path = competence_dir / f"fidc_cedentes_reparos_fonte_{competence}.csv.gz"
        if repair_path.exists() and repair_path not in data_paths:
            data_paths.append(repair_path)
        repair_rows = source_repairs.loc[source_repairs["competencia"].eq(competence)]
        source_path = sources[competence][0]
        competence_manifest = {
            "schema_version": SCHEMA_VERSION,
            "competence": competence,
            "generated_at": generated_at,
            "cutoff_rank": DEFAULT_CUTOFF_RANK,
            "metrics": metrics[competence],
            "source": _source_descriptor(
                source_path,
                role="Informe Mensal FIDC da CVM",
                url=CVM_SOURCE_URLS[competence],
            ),
            "source_repairs": repair_rows.to_dict(orient="records"),
            "outputs": {
                path.name: _output_descriptor(path)
                for path in sorted(data_paths)
            },
            "parent_manifest": "../fidc_cedentes_triagem_index.json",
        }
        manifest_path = competence_dir / f"fidc_cedentes_manifest_{competence}.json"
        _write_json(competence_manifest, manifest_path)
        per_competence_manifest_paths.append(manifest_path)

    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "competences": list(DEFAULT_COMPETENCES),
        "cutoff_rank": DEFAULT_CUTOFF_RANK,
        "sources": {
            "cvm": [
                _source_descriptor(
                    sources[competence][0],
                    role="Informe Mensal FIDC da CVM",
                    url=CVM_SOURCE_URLS[competence],
                )
                for competence in DEFAULT_COMPETENCES
            ],
            "registry": {
                **_source_descriptor(registry_source, role=registry_role),
                "rows": int(len(registry)),
                "mode": "bootstrap_reference_workbook" if registry_is_bootstrap else "receita_bulk_local",
            },
        },
        "metrics": metrics,
        "source_repairs_summary": {
            competence: int(
                source_repairs["competencia"].astype(str).eq(competence).sum()
            )
            for competence in DEFAULT_COMPETENCES
        },
        "rules": {
            "table_iv": "Fundo primeiro; Classe apenas na ausência de Fundo; sem soma",
            "table_i": "união Fundo/Classe, blocos com e sem retenção, slots 1 a 9",
            "fake_documents": "todos os dígitos iguais a 0 ou 9; excluídos da cobertura real",
            "leading_zero": "CNPJ de 12 ou 13 dígitos recebe zfill(14)",
            "pl_assignment": "PL integral atribuído ao cedente dominante; PR_CEDENTE não rateia PL",
            "potential_middle": "resíduo cadastral; faturamento de R$ 30-500 mi não confirmado",
            "not_classified": "cadastro não resolvido ou natureza sem evidência suficiente para classificação",
            "csv_repairs": "aspas órfãs reparadas apenas sob gate estrutural; demais casos falham fechados",
        },
        "limitations": [
            "A Tabela I identifica cedente e não identifica sacado.",
            "Porte Receita separa ME, EPP e Demais e não confirma faturamento.",
            "Capital social não substitui receita ou faturamento.",
            "O cadastro é um snapshot atual aplicado às quatro competências históricas.",
            "O enriquecimento cadastral não usa BrasilAPI.",
        ],
        "outputs": {
            filename: _output_descriptor(output_dir / filename, rows=int(len(frame)))
            for filename, (frame, _) in output_specs.items()
        },
        "competence_manifests": {
            path.parent.name: _output_descriptor(path)
            for path in per_competence_manifest_paths
        },
    }
    _write_json(manifest, output_dir / "fidc_cedentes_triagem_index.json")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cvm-dir",
        type=Path,
        required=True,
        help="Diretório com ZIPs CVM anuais/mensais das quatro competências",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "industry_study" / "cedente_triage",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry-csv", type=Path)
    source.add_argument("--reference-workbook", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_source = args.registry_csv or args.reference_workbook
    if not registry_source.exists():
        raise FileNotFoundError(registry_source)
    registry = (
        _read_registry_csv(args.registry_csv)
        if args.registry_csv
        else _read_reference_registry(args.reference_workbook)
    )
    manifest = materialize(
        cvm_dir=args.cvm_dir,
        output_dir=args.output_dir,
        registry=registry,
        registry_source=registry_source,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "competences": manifest["competences"],
                "metrics": manifest["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
