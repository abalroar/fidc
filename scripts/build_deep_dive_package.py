from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.deep_dive_store import write_deep_dive_index
from services.fundonet_dashboard import build_dashboard_data
from services.monitoring_metrics import build_monitoring_tables, read_wide_csv
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from services.variaveis_fnet import competencia_columns


DEFAULT_PACKAGE_ID = "sellers_vs_mercado_credito"
REPORTS = ROOT / "reports"
OUT_ROOT = ROOT / "data" / "deep_dives"
IME_CACHE_ROOT = ROOT / ".cache" / "fundonet-ime"
PORTFOLIOS_PATH = ROOT / "portfolios.json"

logging.getLogger("pypdf").setLevel(logging.ERROR)

GLOBAL_DOCUMENT_INVENTORY = REPORTS / "regulatory_document_inventory.csv"
GLOBAL_CURATION_STATUS = REPORTS / "all_fidcs_regulatory_curation_status.csv"
GLOBAL_CRITERIA_MATRIX = REPORTS / "regulatory_criteria_matrix.csv"
GLOBAL_CURATED_CRITERIA = ROOT / "data" / "regulatory_profiles" / "all_fidcs_criteria_monitoraveis_ime.csv"
GLOBAL_CURATED_EMISSIONS = ROOT / "data" / "regulatory_profiles" / "all_fidcs_cotas_emissoes_pagamentos.csv"


def main() -> None:
    args = parse_args()
    if args.all_portfolios:
        build_all_portfolio_packages(args)
        return
    if args.portfolio_id:
        portfolio = get_portfolio_by_id(args.portfolio_id)
        if portfolio is None:
            raise SystemExit(f"Carteira não encontrada: {args.portfolio_id}")
        build_portfolio_package(args, portfolio)
        return
    build_sellers_mercado_credito_package(args)


def build_sellers_mercado_credito_package(args: argparse.Namespace) -> None:
    package_dir = args.output_root / args.deep_dive_id
    (package_dir / "tables").mkdir(parents=True, exist_ok=True)
    (package_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (package_dir / "notes").mkdir(parents=True, exist_ok=True)

    coverage = read_csv(REPORTS / "sellers_mercado_credito_document_coverage.csv")
    performance = read_csv(REPORTS / "sellers_mercado_credito_performance_metrics.csv")
    threshold_versions = read_csv(REPORTS / "sellers_mercado_credito_threshold_versions.csv")
    emissions = read_csv(REPORTS / "sellers_mercado_credito_emissions.csv")

    performance = enrich_performance_from_local_ime_cache(performance, coverage)
    emission_rows = build_emission_rows(emissions, coverage)
    comparison = build_comparison_main(coverage, performance, threshold_versions, emissions)
    comparison.to_csv(package_dir / "tables" / "comparison_main.csv", index=False)
    build_emission_schedule_table(emission_rows).to_csv(package_dir / "tables" / "emissions.csv", index=False)
    build_latest_thresholds_table(threshold_versions, coverage).to_csv(package_dir / "tables" / "thresholds.csv", index=False)
    performance.to_csv(package_dir / "evidence" / "performance_metrics_enriched.csv", index=False)
    for name in [
        "sellers_mercado_credito_document_by_document_digest.csv",
        "sellers_mercado_credito_pdf_evidence.csv",
        "sellers_mercado_credito_deep_dive.md",
    ]:
        source = REPORTS / name
        if not source.exists():
            continue
        target = package_dir / ("notes" if source.suffix == ".md" else "evidence") / source.name
        target.write_bytes(source.read_bytes())

    manifest = build_manifest(args, coverage, comparison)
    (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_deep_dive_index(args.output_root)
    print(f"Pacote criado em {package_dir.relative_to(ROOT)}")


def build_all_portfolio_packages(args: argparse.Namespace) -> None:
    portfolios = load_saved_portfolios()
    if not portfolios:
        raise SystemExit("Nenhuma carteira salva encontrada em portfolios.json.")
    for portfolio in portfolios:
        build_portfolio_package(args, portfolio)
    write_deep_dive_index(args.output_root)
    print(f"{len(portfolios)} pacote(s) de carteira criados em {args.output_root.relative_to(ROOT)}")


def build_portfolio_package(args: argparse.Namespace, portfolio: PortfolioRecord) -> None:
    package_id = args.deep_dive_id if args.deep_dive_id != DEFAULT_PACKAGE_ID and not args.all_portfolios else portfolio_deep_dive_id(portfolio)
    package_dir = args.output_root / package_id
    (package_dir / "tables").mkdir(parents=True, exist_ok=True)
    (package_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (package_dir / "notes").mkdir(parents=True, exist_ok=True)

    coverage = build_portfolio_coverage(portfolio)
    performance = enrich_performance_from_local_ime_cache(pd.DataFrame(), coverage)
    threshold_versions = build_threshold_versions_for_coverage(coverage)
    emissions = build_emissions_for_coverage(coverage)
    emission_rows = build_emission_rows(emissions, coverage)
    comparison = build_comparison_main(coverage, performance, threshold_versions, emissions)

    comparison.to_csv(package_dir / "tables" / "comparison_main.csv", index=False)
    build_emission_schedule_table(emission_rows).to_csv(package_dir / "tables" / "emissions.csv", index=False)
    build_latest_thresholds_table(threshold_versions, coverage).to_csv(package_dir / "tables" / "thresholds.csv", index=False)
    performance.to_csv(package_dir / "evidence" / "performance_metrics_enriched.csv", index=False)
    coverage.to_csv(package_dir / "evidence" / "document_coverage.csv", index=False)

    manifest = build_manifest(
        argparse.Namespace(
            deep_dive_id=package_id,
            title=f"Deep Dive {portfolio.name}",
            subtitle="Estrutura, emissões, gatilhos monitoráveis e métricas IME",
            portfolio_id=portfolio.id,
            portfolio_signature=portfolio_basket_signature(portfolio.funds),
        ),
        coverage,
        comparison,
    )
    (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Pacote criado em {package_dir.relative_to(ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Empacota artefatos offline em um Deep Dive consumível pelo app.")
    parser.add_argument("--deep-dive-id", default=DEFAULT_PACKAGE_ID)
    parser.add_argument("--title", default="Comparativo Sellers vs Mercado Crédito")
    parser.add_argument("--subtitle", default="Estrutura, documentação, gatilhos e performance monitorável")
    parser.add_argument("--portfolio-id", default="")
    parser.add_argument("--portfolio-signature", default="")
    parser.add_argument("--output-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--all-portfolios", action="store_true", help="Gera um pacote Deep Dive para cada carteira salva.")
    return parser.parse_args()


def load_saved_portfolios(path: Path = PORTFOLIOS_PATH) -> list[PortfolioRecord]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [PortfolioRecord.from_dict(item) for item in payload.get("portfolios") or []]


def get_portfolio_by_id(portfolio_id: str) -> PortfolioRecord | None:
    return next((portfolio for portfolio in load_saved_portfolios() if portfolio.id == portfolio_id), None)


def portfolio_deep_dive_id(portfolio: PortfolioRecord) -> str:
    return f"carteira_{safe_token(portfolio.name)}_{portfolio.id[:8]}"


def build_portfolio_coverage(portfolio: PortfolioRecord) -> pd.DataFrame:
    inventory = read_csv(GLOBAL_DOCUMENT_INVENTORY)
    curation = read_csv(GLOBAL_CURATION_STATUS)
    sellers_coverage = read_csv(REPORTS / "sellers_mercado_credito_document_coverage.csv")
    page_cache: dict[str, int] = {}
    rows = []
    for fund in portfolio.funds:
        cnpj = normalize_cnpj(fund.cnpj)
        docs = inventory[inventory["CNPJ"].map(normalize_cnpj).eq(cnpj)].copy() if not inventory.empty else pd.DataFrame()
        curation_row = first_matching_cnpj_row(curation, cnpj)
        sellers_row = first_matching_cnpj_row(sellers_coverage, cnpj)
        fund_name = (
            display(curation_row.get("Fundo") if curation_row is not None else "")
            if curation_row is not None
            else "—"
        )
        if fund_name == "—":
            fund_name = (
                display(sellers_row.get("fundo") if sellers_row is not None else "")
                if sellers_row is not None
                else "—"
            )
        if fund_name == "—" and not docs.empty:
            fund_name = display(docs.iloc[0].get("Fundo"))
        if fund_name == "—":
            fund_name = fund.display_name

        if sellers_row is not None and display(sellers_row.get("paginas_pdf_locais")) != "—":
            local_pages = sellers_row.get("paginas_pdf_locais")
        else:
            local_pages = str(sum_pdf_pages(docs.get("Arquivo", pd.Series(dtype=str)).tolist(), page_cache=page_cache))

        local_pdfs = local_pdf_count(docs.get("Arquivo", pd.Series(dtype=str)).tolist())
        rows.append(
            {
                "grupo": portfolio.name,
                "cnpj": format_cnpj(cnpj),
                "fundo": fund_name,
                "documentos_inventariados": str(len(docs)) if sellers_row is None else display(sellers_row.get("documentos_inventariados")),
                "pdfs_locais_analisaveis": str(local_pdfs) if sellers_row is None else display(sellers_row.get("pdfs_locais_analisaveis")),
                "documentos_sem_pdf_local": str(max(len(docs) - local_pdfs, 0)) if sellers_row is None else display(sellers_row.get("documentos_sem_pdf_local")),
                "paginas_pdf_locais": local_pages,
                "quebra_por_categoria": category_breakdown(docs) if sellers_row is None else display(sellers_row.get("quebra_por_categoria")),
            }
        )
    return pd.DataFrame(rows)


def first_matching_cnpj_row(frame: pd.DataFrame, cnpj: str) -> pd.Series | None:
    if frame.empty:
        return None
    cnpj_col = "CNPJ" if "CNPJ" in frame.columns else "cnpj" if "cnpj" in frame.columns else ""
    if not cnpj_col:
        return None
    subset = frame[frame[cnpj_col].map(normalize_cnpj).eq(cnpj)]
    if subset.empty:
        return None
    return subset.iloc[0]


def local_pdf_count(paths: list[object]) -> int:
    return sum(1 for value in paths if pdf_path(value).exists())


def sum_pdf_pages(paths: list[object], *, page_cache: dict[str, int]) -> int:
    total = 0
    for value in paths:
        path = pdf_path(value)
        if not path.exists():
            continue
        key = str(path)
        if key not in page_cache:
            page_cache[key] = count_pdf_pages(path)
        total += page_cache[key]
    return total


def pdf_path(value: object) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path("__missing__")
    path = Path(text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def count_pdf_pages(path: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001
        return 0


def category_breakdown(docs: pd.DataFrame) -> str:
    if docs.empty:
        return "—"
    column = "Tipo" if "Tipo" in docs.columns else docs.columns[0]
    counts = docs[column].fillna("").replace("", "outro").value_counts()
    return "; ".join(f"{key}: {value}" for key, value in counts.items())


def build_threshold_versions_for_coverage(coverage: pd.DataFrame) -> pd.DataFrame:
    frames = [
        normalize_curated_criteria(read_csv(GLOBAL_CURATED_CRITERIA)),
        normalize_criteria_matrix(read_csv(GLOBAL_CRITERIA_MATRIX)),
    ]
    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True, sort=False)
    if combined.empty or coverage.empty:
        return pd.DataFrame()
    cnpjs = {normalize_cnpj(value) for value in coverage["cnpj"].tolist()}
    combined = combined[combined["cnpj"].map(normalize_cnpj).isin(cnpjs)].copy()
    if combined.empty:
        return combined
    combined["_priority"] = combined["source_kind"].map({"curated": 2, "matrix": 1}).fillna(0)
    combined["_dedupe"] = combined.apply(
        lambda row: "|".join(
            [
                normalize_cnpj(row.get("cnpj")),
                str(row.get("chave") or ""),
                str(row.get("comparacao") or ""),
                str(row.get("limite") or ""),
                str(row.get("source_file") or ""),
            ]
        ),
        axis=1,
    )
    return (
        combined.sort_values("_priority")
        .drop_duplicates("_dedupe", keep="last")
        .drop(columns=["_priority", "_dedupe"], errors="ignore")
    )


def normalize_curated_criteria(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    output = []
    for _, row in frame.iterrows():
        comparison, limit = split_limit_rule(row.get("Limite/regra"))
        source = row.get("Fonte") or ""
        output.append(
            {
                "fundo": row.get("Fundo") or "",
                "cnpj": row.get("CNPJ") or "",
                "criterio": row.get("Critério") or "",
                "chave": row.get("Chave") or "",
                "evento": row.get("Critério") or "",
                "comparacao": comparison,
                "limite": limit,
                "monitorabilidade_ime": row.get("Monitorabilidade IME") or "",
                "metrica_ime": row.get("Métrica IME / proxy") or "",
                "fonte_pagina": source,
                "source_file": source,
                "data_documento": extract_date_from_text(source),
                "categoria_documento": classify_source(source),
                "tipo_documento": classify_source(source),
                "source_kind": "curated",
            }
        )
    return pd.DataFrame(output)


def normalize_criteria_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    output = []
    for _, row in frame.iterrows():
        source = row.get("Fonte") or ""
        output.append(
            {
                "fundo": row.get("Fundo") or "",
                "cnpj": row.get("CNPJ") or "",
                "criterio": row.get("Critério") or "",
                "chave": row.get("Chave") or "",
                "evento": row.get("Evento") or row.get("Critério") or "",
                "comparacao": row.get("Comparação") or "",
                "limite": row.get("Limite") or "",
                "monitorabilidade_ime": row.get("Monitoramento") or "",
                "metrica_ime": row.get("Métrica IME sugerida") or "",
                "fonte_pagina": source,
                "source_file": source,
                "data_documento": extract_date_from_text(source),
                "categoria_documento": classify_source(source),
                "tipo_documento": classify_source(source),
                "source_kind": "matrix",
            }
        )
    return pd.DataFrame(output)


def split_limit_rule(value: object) -> tuple[str, str]:
    text = display(value)
    if text == "—":
        return "", ""
    match = re.match(r"\s*(>=|<=|>|<|=)\s*(.+)", text)
    if match:
        return match.group(1), match.group(2).strip()
    return "", text


def classify_source(value: object) -> str:
    text = str(value or "").lower()
    for token in ("regulamento", "assembleia", "emissao", "evento"):
        if token in text:
            return token
    return "outro"


def build_emissions_for_coverage(coverage: pd.DataFrame) -> pd.DataFrame:
    frames = [read_csv(GLOBAL_CURATED_EMISSIONS), read_csv(REPORTS / "sellers_mercado_credito_emissions.csv")]
    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True, sort=False)
    if combined.empty or coverage.empty:
        return pd.DataFrame()
    cnpjs = {normalize_cnpj(value) for value in coverage["cnpj"].tolist()}
    combined = combined[combined["CNPJ"].map(normalize_cnpj).isin(cnpjs)].copy()
    if combined.empty:
        return combined
    combined["_dedupe"] = combined.apply(
        lambda row: "|".join(
            [
                normalize_cnpj(row.get("CNPJ")),
                str(row.get("Cota/Classe") or row.get("Classe/Série") or ""),
                str(row.get("Data emissão / 1ª integralização") or row.get("Data") or ""),
                str(row.get("Volume") or ""),
                str(row.get("Fonte") or ""),
            ]
        ),
        axis=1,
    )
    return combined.drop_duplicates("_dedupe", keep="last").drop(columns=["_dedupe"], errors="ignore")


def build_manifest(args: argparse.Namespace, coverage: pd.DataFrame, comparison: pd.DataFrame) -> dict[str, object]:
    funds = []
    if not coverage.empty:
        for _, row in coverage.iterrows():
            funds.append(
                {
                    "cnpj": str(row.get("cnpj") or ""),
                    "name": str(row.get("fundo") or ""),
                    "short_name": short_name(row.get("fundo") or row.get("cnpj") or ""),
                }
            )
    return {
        "schema_version": 1,
        "deep_dive_id": args.deep_dive_id,
        "title": args.title,
        "subtitle": args.subtitle,
        "portfolio_id": args.portfolio_id,
        "portfolio_signature": args.portfolio_signature,
        "generated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "source": "Extração offline local · CVM/Fundos.NET · IME cache",
        "confidentiality": "Uso interno",
        "funds": funds,
        "tables": [
            {
                "id": "comparison_main",
                "title": "Comparativo principal",
                "subtitle": "Matriz FIDC x métrica, emissões e gatilhos monitoráveis",
                "kind": "comparison_matrix",
                "source_file": "tables/comparison_main.csv",
                "first_column": "Nome",
            },
            {
                "id": "emissions",
                "title": "Cronograma de emissões",
                "kind": "source_table",
                "source_file": "tables/emissions.csv",
                "first_column": "Fundo",
            },
            {
                "id": "thresholds",
                "title": "Regulamento mais recente",
                "kind": "source_table",
                "source_file": "tables/thresholds.csv",
                "first_column": "fundo",
            },
        ],
        "audit": {
            "warnings": [
                "Pacote gerado exclusivamente a partir de arquivos locais já extraídos no repositório.",
                "Métricas IME foram enriquecidas a partir do cache local quando disponível; fundos sem IME vigente mantêm lacuna explícita.",
                f"Tabela principal com {len(comparison)} linhas; contagem documental foi substituída por páginas locais analisadas.",
            ]
        },
    }


def build_comparison_main(
    coverage: pd.DataFrame,
    performance: pd.DataFrame,
    threshold_versions: pd.DataFrame,
    emissions: pd.DataFrame,
) -> pd.DataFrame:
    fund_keys = ordered_funds(coverage)
    aliases = cnpj_aliases(coverage)
    emission_rows = build_emission_rows(emissions, coverage)
    emission_summary = emission_summary_by_fund(emission_rows)
    rows: list[dict[str, str]] = []

    def add_row(label: str, values: dict[str, object]) -> None:
        row = {"Nome": label}
        for key in fund_keys:
            row[key] = display(values.get(key))
        rows.append(row)

    add_row("Grupo", {short_name(row.get("fundo")): row.get("grupo") for _, row in coverage.iterrows()})
    add_row("CNPJ", {short_name(row.get("fundo")): row.get("cnpj") for _, row in coverage.iterrows()})
    add_row("Páginas locais analisadas", {short_name(row.get("fundo")): row.get("paginas_pdf_locais") for _, row in coverage.iterrows()})

    add_row("Última competência IME", latest_competence_by_fund(performance, aliases))
    for indicator, label in [
        ("PL (R$ MM)", "PL (R$ mm)"),
        ("Dir Cred / PL", "Direitos creditórios / PL"),
        ("Vencidos Over 30 d / Crédito", "Vencidos Over 30d / crédito"),
        ("Vencidos Over 60 d / Crédito", "Vencidos Over 60d / crédito"),
        ("Vencidos Over 90 d / Crédito", "Vencidos Over 90d / crédito"),
        ("Vencidos Over 180 d / Crédito", "Vencidos Over 180d / crédito"),
        ("Vencidos Over 360 d / Crédito", "Vencidos Over 360d / crédito"),
        ("PDD / Crédito", "PDD / crédito"),
        ("PDD / Venc Total", "PDD / vencidos"),
        ("Cotas SR / PL %", "Cotas sênior / PL"),
        ("Cotas MZ / PL %", "Cotas mezanino / PL"),
        ("Cotas Sub / PL %", "Cotas subordinadas / PL"),
    ]:
        add_row(label, latest_metric_by_fund(performance, indicator, aliases))

    for metric_key, label in [
        ("series_count", "Séries/classes emitidas identificadas"),
        ("volume_mm", "Volume emitido identificado (R$ mm)"),
        ("first_date", "Primeira emissão identificada"),
        ("last_date", "Última emissão identificada"),
    ]:
        add_row(label, {fund: values.get(metric_key) for fund, values in emission_summary.items()})
    for metric_key, label in [
        ("emission_terms", "Emissões detectadas (data, classe, preço e volume)"),
        ("remuneration_terms", "Remuneração-alvo por emissão detectada"),
        ("amortization_terms", "Amortização/vencimento por emissão detectada"),
    ]:
        add_row(label, {fund: values.get(metric_key) for fund, values in emission_summary.items()})

    add_row("Regulamento-base dos thresholds", latest_regulation_source_by_fund(threshold_versions, aliases))
    for key, label in [
        ("credit_rights_allocation_min", "Alocação mínima em DCs"),
        ("subordination_ratio_min", "Subordinação mínima"),
        ("default_rate_evaluation_event", "Evento de avaliação por atraso"),
        ("default_rate_early_maturity", "Liquidação/vencimento por atraso"),
        ("pdd_coverage_min", "Cobertura mínima PDD"),
        ("minimum_cash_ratio", "Reserva/caixa mínimo"),
        ("permitted_hedges", "Hedges permitidos"),
    ]:
        add_row(label, latest_threshold_by_fund(threshold_versions, key, aliases))

    return pd.DataFrame(rows)


def enrich_performance_from_local_ime_cache(performance: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """Completa métricas monitoráveis a partir de caches IME locais já existentes."""

    if coverage.empty or not IME_CACHE_ROOT.exists():
        return performance
    rows: list[dict[str, object]] = []
    for _, fund in coverage.iterrows():
        cache = best_ime_cache_for_cnpj(fund.get("cnpj"))
        if not cache:
            continue
        rows.extend(performance_rows_from_ime_cache(cache, fund))
    if not rows:
        return performance

    local = pd.DataFrame(rows)
    base = performance.copy()
    if not base.empty and "indicador" in base.columns:
        enriched_cnpjs = {normalize_cnpj(value) for value in local["cnpj"].dropna().tolist()}
        base = base[
            ~(
                base["cnpj"].map(normalize_cnpj).isin(enriched_cnpjs)
                & base["indicador"].astype(str).eq("Lacuna IME")
            )
        ].copy()
    combined = pd.concat([base, local], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    combined["_cnpj_norm"] = combined["cnpj"].map(normalize_cnpj)
    combined["_source_rank"] = combined["observacao"].astype(str).str.contains("cache IME local", case=False, na=False).map({True: 2, False: 1})
    combined = (
        combined.sort_values(["_source_rank"])
        .drop_duplicates(subset=["_cnpj_norm", "competencia", "indicador"], keep="last")
        .drop(columns=["_cnpj_norm", "_source_rank"])
    )
    return combined


def best_ime_cache_for_cnpj(cnpj: object) -> dict[str, Any] | None:
    cnpj_digits = normalize_cnpj(cnpj)
    candidates: list[dict[str, Any]] = []
    for manifest_path in IME_CACHE_ROOT.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if normalize_cnpj(manifest.get("cnpj_fundo")) != cnpj_digits:
            continue
        competencias = [str(item) for item in manifest.get("competencias") or []]
        if not competencias:
            continue
        manifest["_path"] = manifest_path
        manifest["_latest_comp"] = max(competencias, key=comp_sort)
        manifest["_comp_count"] = len(competencias)
        candidates.append(manifest)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (comp_sort(item.get("_latest_comp")), int(item.get("_comp_count") or 0)))[-1]


def performance_rows_from_ime_cache(manifest: dict[str, Any], fund: pd.Series) -> list[dict[str, object]]:
    manifest_path = Path(manifest["_path"])
    cache_dir = manifest_path.parent
    files = manifest.get("files") or {}
    wide_path = cache_dir / str(files.get("wide_csv_path", ""))
    listas_path = cache_dir / str(files.get("listas_csv_path", ""))
    docs_path = cache_dir / str(files.get("docs_csv_path", ""))
    if not wide_path.exists():
        return []

    wide_df = read_wide_csv(wide_path)
    competencias = list(manifest.get("competencias") or competencia_columns(wide_df))
    if not competencias:
        return []

    dashboard_data = None
    dashboard_note = "Campos escalares IME"
    if listas_path.exists() and docs_path.exists():
        try:
            dashboard_data = build_dashboard_data(
                wide_csv_path=wide_path,
                listas_csv_path=listas_path,
                docs_csv_path=docs_path,
            )
            dashboard_note = "Visão Executiva canônica"
        except Exception as exc:  # noqa: BLE001
            dashboard_note = f"Campos escalares IME; dashboard_data indisponível ({type(exc).__name__})"
    tables = build_monitoring_tables(
        wide_df,
        competencias,
        cnpj=str(fund.get("cnpj") or ""),
        overrides={},
        dashboard_data=dashboard_data,
    )

    rows: list[dict[str, object]] = []
    for _, indicator_row in tables.indicators_df.iterrows():
        indicator = str(indicator_row.get("indicador") or "")
        unit = str(indicator_row.get("unidade") or "")
        for competencia in competencias:
            value = indicator_row.get(competencia)
            if display(value) == "—":
                continue
            rows.append(
                {
                    "grupo": fund.get("grupo") or "",
                    "fundo": fund.get("fundo") or "",
                    "nome_curto": short_name(fund.get("fundo") or ""),
                    "cnpj": fund.get("cnpj") or "",
                    "competencia": competencia,
                    "indicador": indicator,
                    "valor": value,
                    "unidade": unit,
                    "observacao": f"{dashboard_note}; cache IME local {cache_dir.name}",
                    "cache_folder": str(cache_dir.relative_to(ROOT)),
                }
            )
    return rows


def build_emission_rows(emissions: pd.DataFrame, coverage: pd.DataFrame) -> list[dict[str, object]]:
    if emissions.empty:
        return []
    emissions = preferred_emission_rows(emissions)
    aliases = cnpj_aliases(coverage)
    rows: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for _, row in emissions.iterrows():
        cnpj_norm = normalize_cnpj(row.get("CNPJ"))
        fund = aliases.get(cnpj_norm, short_name(row.get("Fundo") or row.get("cnpj") or cnpj_norm))
        classe = clean_emission_text(first_value(row, ["Cota/Classe", "Classe/Série", "series_or_class"]))
        tipo = clean_emission_type(first_value(row, ["Tipo"]), classe)
        source = clean_emission_text(first_value(row, ["Fonte"]))
        date = normalize_date_label(first_value(row, ["Data emissão / 1ª integralização", "Data", "Data deliberação"]))
        if not date:
            date = extract_date_from_text(source)
        quantity = clean_emission_text(first_value(row, ["Quantidade"]))
        unit_price = clean_emission_text(first_value(row, ["VNU"]))
        volume_value = parse_money_value(first_value(row, ["Volume"]))
        if volume_value is None:
            quantity_value = parse_money_value(quantity)
            unit_value = parse_money_value(unit_price)
            if quantity_value is not None and unit_value is not None:
                volume_value = quantity_value * unit_value
        volume_mm = None if volume_value is None else volume_value / 1_000_000.0
        if volume_mm is not None and volume_mm < 1.0:
            volume_mm = None
        remuneration = normalize_remuneration(first_value(row, ["Remuneração", "Juros/remuneração"]))
        amortization = normalize_amortization(first_value(row, ["Amortização principal", "Amortização/Vencimento"]))

        if is_noise_emission_row(classe, remuneration, amortization, volume_mm):
            continue
        key = (
            cnpj_norm,
            simplify_text(classe),
            tipo,
            date,
            round(float(volume_mm or 0.0), 3),
            simplify_text(remuneration),
            simplify_text(amortization),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "fund": fund,
                "cnpj": format_cnpj(cnpj_norm),
                "cnpj_norm": cnpj_norm,
                "date": date or "—",
                "sort_key": date_sort(date),
                "class": classe or "Classe/série não identificada",
                "type": tipo or "—",
                "quantity": quantity or "—",
                "unit_price": unit_price or "—",
                "volume_mm": volume_mm,
                "remuneration": remuneration or "—",
                "amortization": amortization or "—",
                "source": source or "—",
            }
        )
    return sorted(rows, key=lambda item: (item["fund"], item["sort_key"], item["class"]))


def build_emission_schedule_table(rows: list[dict[str, object]]) -> pd.DataFrame:
    output = []
    for row in rows:
        output.append(
            {
                "Fundo": row["fund"],
                "CNPJ": row["cnpj"],
                "Data": row["date"],
                "Classe/Série": row["class"],
                "Tipo": row["type"],
                "Qtd cotas": row["quantity"],
                "Preço/VNU": row["unit_price"],
                "Volume identificado (R$ mm)": format_optional_number(row.get("volume_mm"), decimals=1),
                "Remuneração-alvo": row["remuneration"],
                "Amortização/vencimento": row["amortization"],
                "Fonte": row["source"],
            }
        )
    return pd.DataFrame(output)


def emission_summary_by_fund(rows: list[dict[str, object]]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for fund, fund_rows in group_rows(rows, key="fund").items():
        dated = sorted(fund_rows, key=lambda item: item.get("sort_key") or "")
        classes = {
            simplify_text(row.get("class"))
            for row in fund_rows
            if display(row.get("class")) != "—" and simplify_text(row.get("class")) != simplify_text("Classe/série não identificada")
        }
        volume_sum = sum(float(row.get("volume_mm") or 0.0) for row in fund_rows if row.get("volume_mm") is not None)
        senior_rows = [
            row
            for row in dated
            if "sênior" in str(row.get("type") or "").lower() and display(row.get("remuneration")) != "—"
        ]
        any_remunerated = [row for row in dated if display(row.get("remuneration")) != "—"]
        amortized = [row for row in dated if display(row.get("amortization")) != "—"]
        output[fund] = {
            "series_count": str(len(classes) or len(fund_rows)),
            "volume_mm": format_optional_number(volume_sum if volume_sum else None, decimals=0),
            "first_date": next((str(row.get("date")) for row in dated if display(row.get("date")) != "—"), "—"),
            "last_date": next((str(row.get("date")) for row in reversed(dated) if display(row.get("date")) != "—"), "—"),
            "latest_senior_remuneration": summarize_with_date((senior_rows or any_remunerated)[-1] if (senior_rows or any_remunerated) else None, "remuneration"),
            "latest_amortization": summarize_with_date(amortized[-1] if amortized else None, "amortization"),
            "emission_terms": summarize_emission_terms(dated),
            "remuneration_terms": summarize_emission_field(dated, "remuneration"),
            "amortization_terms": summarize_emission_field(dated, "amortization"),
        }
    return output


def summarize_emission_terms(rows: list[dict[str, object]]) -> str:
    values = []
    for row in rows:
        label = emission_label(row)
        quantity = display(row.get("quantity"))
        unit_price = display(row.get("unit_price"))
        volume = format_optional_number(row.get("volume_mm"), decimals=0)
        parts = []
        if quantity != "—":
            parts.append(f"Qtd {quantity}")
        if unit_price != "—":
            parts.append(f"Preço {unit_price}")
        if volume != "—":
            parts.append(f"R$ {volume} mm")
        values.append(f"{label}: {'; '.join(parts) if parts else 'termos econômicos não identificados'}")
    return join_summary_items(values)


def summarize_emission_field(rows: list[dict[str, object]], field: str) -> str:
    values = []
    for row in rows:
        value = display(row.get(field))
        if value == "—":
            continue
        values.append(f"{emission_label(row)}: {value}")
    return join_summary_items(values)


def emission_label(row: dict[str, object]) -> str:
    date = display(row.get("date"))
    klass = display(row.get("class"))
    kind = display(row.get("type"))
    parts = [part for part in [date, klass, kind] if part != "—"]
    return " · ".join(parts) or "Emissão sem data/classe identificada"


def join_summary_items(values: list[str]) -> str:
    unique = []
    seen: set[str] = set()
    for value in values:
        cleaned = display(value)
        if cleaned == "—" or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    return " | ".join(unique) if unique else "—"


def build_latest_thresholds_table(threshold_versions: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    if threshold_versions.empty:
        return pd.DataFrame()
    aliases = cnpj_aliases(coverage)
    rows = latest_threshold_rows(threshold_versions)
    output = []
    for _, row in rows.iterrows():
        cnpj_norm = normalize_cnpj(row.get("cnpj"))
        output.append(
            {
                "fundo": aliases.get(cnpj_norm, short_name(row.get("fundo") or "")),
                "CNPJ": format_cnpj(cnpj_norm),
                "Data regulamento": row.get("data_documento") or "—",
                "Critério": row.get("criterio") or row.get("chave") or "—",
                "Evento": row.get("evento") or "—",
                "Comparação": row.get("comparacao") or "—",
                "Limite": row.get("limite") or "—",
                "Monitorável IME": row.get("monitorabilidade_ime") or "—",
                "Métrica IME": row.get("metrica_ime") or "—",
                "Fonte": row.get("fonte_pagina") or Path(str(row.get("source_file") or "")).name or "—",
            }
        )
    return pd.DataFrame(output)


def ordered_funds(coverage: pd.DataFrame) -> list[str]:
    if coverage.empty:
        return []
    return [short_name(value) for value in coverage["fundo"].tolist()]


def cnpj_aliases(coverage: pd.DataFrame) -> dict[str, str]:
    if coverage.empty:
        return {}
    return {normalize_cnpj(row.get("cnpj")): short_name(row.get("fundo")) for _, row in coverage.iterrows()}


def latest_metric_by_fund(performance: pd.DataFrame, indicator: str, aliases: dict[str, str]) -> dict[str, str]:
    if performance.empty:
        return {}
    subset = performance[performance["indicador"].astype(str) == indicator].copy()
    if subset.empty:
        return {}
    subset["sort_key"] = subset["competencia"].map(comp_sort)
    output = {}
    for cnpj, group in subset.sort_values("sort_key").groupby(subset["cnpj"].map(normalize_cnpj), dropna=False):
        row = group.iloc[-1]
        output[aliases.get(str(cnpj), str(row.get("nome_curto") or row.get("cnpj")))] = format_metric(row.get("valor"), row.get("unidade"))
    return output


def latest_competence_by_fund(performance: pd.DataFrame, aliases: dict[str, str]) -> dict[str, str]:
    if performance.empty or "competencia" not in performance.columns:
        return {}
    subset = performance[performance["indicador"].astype(str).ne("Lacuna IME")].copy()
    if subset.empty:
        return {}
    subset["sort_key"] = subset["competencia"].map(comp_sort)
    output = {}
    for cnpj, group in subset.sort_values("sort_key").groupby(subset["cnpj"].map(normalize_cnpj), dropna=False):
        row = group.iloc[-1]
        output[aliases.get(str(cnpj), str(row.get("nome_curto") or row.get("cnpj")))] = display(row.get("competencia"))
    return output


def latest_threshold_by_fund(threshold_versions: pd.DataFrame, key: str, aliases: dict[str, str]) -> dict[str, str]:
    if threshold_versions.empty:
        return {}
    subset = latest_threshold_rows(threshold_versions)
    subset = subset[subset["chave"].astype(str) == key].copy()
    if subset.empty:
        return {}
    output = {}
    for cnpj, group in subset.groupby(subset["cnpj"].map(normalize_cnpj), dropna=False):
        values = []
        for _, row in group.iterrows():
            value = " ".join(str(item) for item in [row.get("comparacao"), row.get("limite")] if str(item or "").strip())
            if value and value not in values:
                values.append(value)
        output[aliases.get(str(cnpj), str(group.iloc[0].get("nome_curto") or group.iloc[0].get("cnpj")))] = "; ".join(values[:4]) + (f"; +{len(values) - 4}" if len(values) > 4 else "") or "—"
    return output


def latest_threshold_rows(threshold_versions: pd.DataFrame) -> pd.DataFrame:
    if threshold_versions.empty:
        return threshold_versions.copy()
    subset = threshold_versions.copy()
    regulation_mask = (
        subset.get("categoria_documento", pd.Series("", index=subset.index)).astype(str).str.contains("regulamento", case=False, na=False)
        | subset.get("tipo_documento", pd.Series("", index=subset.index)).astype(str).str.contains("regulamento", case=False, na=False)
        | subset.get("source_file", pd.Series("", index=subset.index)).astype(str).str.contains("regulamento", case=False, na=False)
    )
    subset = subset[regulation_mask].copy()
    if subset.empty:
        return subset
    subset["_cnpj_norm"] = subset["cnpj"].map(normalize_cnpj)
    subset["_sort_key"] = subset["data_documento"].map(date_sort)
    latest_rows = []
    for (cnpj, key), group in subset.sort_values("_sort_key").groupby(["_cnpj_norm", "chave"], dropna=False):
        latest_key = group["_sort_key"].max()
        latest_group = group[group["_sort_key"] == latest_key].copy()
        latest_group["_dedupe"] = latest_group.apply(
            lambda row: "|".join(
                [
                    str(row.get("criterio") or ""),
                    str(row.get("evento") or ""),
                    str(row.get("comparacao") or ""),
                    str(row.get("limite") or ""),
                    str(row.get("fonte_pagina") or row.get("source_file") or ""),
                ]
            ),
            axis=1,
        )
        latest_rows.append(latest_group.drop_duplicates("_dedupe"))
    if not latest_rows:
        return subset.iloc[0:0].drop(columns=["_cnpj_norm", "_sort_key"], errors="ignore")
    return pd.concat(latest_rows, ignore_index=True).drop(columns=["_cnpj_norm", "_sort_key", "_dedupe"], errors="ignore")


def latest_regulation_source_by_fund(threshold_versions: pd.DataFrame, aliases: dict[str, str]) -> dict[str, str]:
    rows = latest_threshold_rows(threshold_versions)
    if rows.empty:
        return {}
    output: dict[str, int] = {}
    rows["_sort_key"] = rows["data_documento"].map(date_sort)
    for cnpj, group in rows.sort_values("_sort_key").groupby(rows["cnpj"].map(normalize_cnpj), dropna=False):
        row = group.iloc[-1]
        source = Path(str(row.get("source_file") or "")).name or str(row.get("fonte_pagina") or "")
        output[aliases.get(str(cnpj), str(row.get("nome_curto") or row.get("cnpj")))] = f"{display(row.get('data_documento'))} · {source}"
    return output


def short_from_cnpj_or_frame(cnpj: str, frame: pd.DataFrame) -> str:
    for col in ("nome_curto", "Fundo", "fundo"):
        if col in frame.columns:
            value = str(frame.iloc[0].get(col) or "").strip()
            if value:
                return short_name(value)
    return cnpj


def format_metric(value: object, unit: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return display(value)
    unit_text = str(unit or "")
    if "R$ bruto" in unit_text:
        return f"R$ {br_number(numeric / 1_000_000, 0)} mm"
    if "R$ MM" in unit_text:
        return f"R$ {br_number(numeric, 0)} mm"
    if unit_text in {"ratio", "%"} or "/" in unit_text:
        if unit_text == "ratio":
            numeric *= 100
        return f"{br_number(numeric, 1)}%"
    return br_number(numeric, 1)


def display(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return "—"
    return text


def format_optional_number(value: object, *, decimals: int) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(numeric):
        return "—"
    return br_number(numeric, decimals)


def br_number(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def slim_table(frame: pd.DataFrame, max_rows: int = 120) -> pd.DataFrame:
    if frame.empty:
        return frame
    keep = [col for col in frame.columns if col not in {"source_excerpt", "trecho"}]
    return frame[keep].head(max_rows).copy()


def first_value(row: pd.Series, columns: list[str]) -> object:
    for column in columns:
        if column not in row.index:
            continue
        value = row.get(column)
        if display(value) != "—":
            return value
    return ""


def preferred_emission_rows(emissions: pd.DataFrame) -> pd.DataFrame:
    if emissions.empty or "CNPJ" not in emissions.columns:
        return emissions
    selected = []
    for _, group in emissions.groupby(emissions["CNPJ"].map(normalize_cnpj), dropna=False):
        source = group.get("arquivo_origem_tabela", pd.Series("", index=group.index)).astype(str)
        profile_rows = group[source.str.contains("data/regulatory_profiles", case=False, na=False)]
        if not profile_rows.empty:
            selected.append(profile_rows)
            continue
        status = group.get("Status curadoria", pd.Series("", index=group.index)).astype(str).str.strip()
        curated_rows = group[status.ne("")]
        if not curated_rows.empty:
            selected.append(curated_rows)
            continue
        selected.append(group)
    return pd.concat(selected, ignore_index=True) if selected else emissions


def clean_emission_text(value: object, *, max_len: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def clean_emission_type(value: object, class_text: str) -> str:
    text = clean_emission_text(value, max_len=60)
    haystack = f"{text} {class_text}".lower()
    if "senior" in haystack or "sênior" in haystack:
        return "Sênior"
    if "mezan" in haystack:
        return "Mezanino"
    if "subordin" in haystack or "júnior" in haystack or "junior" in haystack:
        return "Subordinada"
    return text


def normalize_date_label(value: object) -> str:
    raw_text = str(value or "")
    embedded = extract_date_from_text(raw_text)
    if embedded:
        return embedded
    text = clean_emission_text(raw_text, max_len=40)
    if "não identific" in text.lower():
        return ""
    if "não textual" in text.lower():
        return ""
    return text


def extract_date_from_text(value: object) -> str:
    text = str(value or "")
    match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if match:
        return match.group(1)
    match = re.search(r"_(\d{4})-(\d{2})-(\d{2})\.pdf\b", text)
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return ""


def normalize_remuneration(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    direct = re.search(r"\b(?:DI|CDI)\s*\+\s*\d{1,2}(?:[,.]\d{1,4})?\s*%\s*a\.?a\.?", text, flags=re.IGNORECASE)
    if direct:
        return normalize_di_spread_label(direct.group(0))
    direct = re.search(r"\b(?:DI|CDI)\s*\+\s*\d{1,2}(?:[,.]\d{1,4})?\s*%", text, flags=re.IGNORECASE)
    if direct:
        return normalize_di_spread_label(direct.group(0))
    spread = re.search(
        r"(?:taxa\s+di|cdi).*?(?:spread|acrescid[ao]s?\s+de|acrescid[ao]?\s+de).*?(\d{1,2}(?:[,.]\d{1,4})?\s*%)",
        text,
        flags=re.IGNORECASE,
    )
    if spread:
        return normalize_di_spread_label(f"DI + {spread.group(1).replace('.', ',')}")
    if "residual" in text.lower():
        return "Residual / sem parâmetro definido"
    if len(text) <= 100 and any(token in text.lower() for token in ["di", "cdi", "%", "benchmark"]):
        return text
    return ""


def normalize_di_spread_label(value: object) -> str:
    text = clean_emission_text(value, max_len=90)
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_amortization(value: object) -> str:
    text = clean_emission_text(value, max_len=220)
    if not text:
        return ""
    lowered = text.lower()
    has_date = bool(re.search(r"\d{2}/\d{2}/\d{4}", text))
    has_percent = "%" in text
    has_schedule_word = any(token in lowered for token in ["amort", "vnu", "vencimento", "resgate"])
    if has_date and (has_percent or has_schedule_word):
        return clean_emission_text(text, max_len=180)
    if has_percent and has_schedule_word and len(text) <= 180:
        return text
    if "sem calendário fixo" in lowered:
        return "Sem calendário fixo identificado"
    return ""


def parse_money_value(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    if "não inform" in text.lower() or "não fix" in text.lower() or "depende" in text.lower():
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned or cleaned in {"-", ",", "."}:
        return None
    if "," in cleaned:
        integer, decimal = cleaned.rsplit(",", 1)
        integer_digits = re.sub(r"\D", "", integer)
        decimal_digits = re.sub(r"\D", "", decimal)[:2].ljust(2, "0")
        if not integer_digits:
            return None
        return float(f"{integer_digits}.{decimal_digits}")
    if "." in cleaned and cleaned.count(".") == 1:
        try:
            return float(cleaned)
        except ValueError:
            pass
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return None
    return float(digits)


def is_noise_emission_row(class_text: str, remuneration: str, amortization: str, volume_mm: float | None) -> bool:
    haystack = " ".join([class_text, remuneration, amortization]).lower()
    has_structured_value = volume_mm is not None and volume_mm >= 1.0
    has_terms = any(token in haystack for token in ["di +", "cdi", "amort", "sênior", "senior", "subordin", "mezan"])
    if not has_structured_value and not has_terms:
        return True
    if len(haystack) > 260 and not has_structured_value:
        return True
    if "índice regulamento" in haystack or "obrigações, vedações" in haystack:
        return True
    return False


def simplify_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    text = re.sub(r"[^\w\s%+.,/-]", "", text)
    return text


def group_rows(rows: list[dict[str, object]], *, key: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or ""), []).append(row)
    return grouped


def summarize_with_date(row: dict[str, object] | None, field: str) -> str:
    if not row:
        return "—"
    value = display(row.get(field))
    if value == "—":
        return "—"
    date = display(row.get("date"))
    return value if date == "—" else f"{value} ({date})"


def format_cnpj(cnpj_digits: object) -> str:
    digits = normalize_cnpj(cnpj_digits)
    if len(digits) != 14:
        return str(cnpj_digits or "")
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def normalize_cnpj(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def short_name(value: object) -> str:
    text = str(value or "").strip()
    replacements = [
        r"\bFUNDO DE INVESTIMENTO EM DIREITOS\s+CREDIT[ÓO]RIOS\b",
        r"\bFIDC SEGMENTO FINANCEIRO\b",
        r"\bSEGMENTO MEIOS DE PAGAMENTO\b",
        r"\bDE RESPONSABILIDADE LIMITADA\b",
        r"\bRESPONSABILIDADE LIMITADA\b",
        r"\bDE RESP LIMITADA\b",
        r"\bRESP LIMITADA\b",
        r"\bRESP LTDA\b",
        r"\bLIMITADA\b",
    ]
    for pattern in replacements:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDE\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bRESP\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    if not text:
        return "FIDC"
    return text[:36].rstrip()


def safe_token(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_text.strip().lower())
    return token.strip("_") or "deep_dive"


def comp_sort(value: object) -> str:
    text = str(value or "")
    match = re.fullmatch(r"(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    return text


def date_sort(value: object) -> str:
    text = str(value or "")
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    match = re.search(r"(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}-01"
    return text


if __name__ == "__main__":
    main()
