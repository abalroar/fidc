from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.deep_dive_store import write_deep_dive_index


DEFAULT_PACKAGE_ID = "sellers_vs_mercado_credito"
REPORTS = ROOT / "reports"
OUT_ROOT = ROOT / "data" / "deep_dives"


def main() -> None:
    args = parse_args()
    package_dir = args.output_root / args.deep_dive_id
    (package_dir / "tables").mkdir(parents=True, exist_ok=True)
    (package_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (package_dir / "notes").mkdir(parents=True, exist_ok=True)

    coverage = read_csv(REPORTS / "sellers_mercado_credito_document_coverage.csv")
    performance = read_csv(REPORTS / "sellers_mercado_credito_performance_metrics.csv")
    threshold_versions = read_csv(REPORTS / "sellers_mercado_credito_threshold_versions.csv")
    emissions = read_csv(REPORTS / "sellers_mercado_credito_emissions.csv")

    comparison = build_comparison_main(coverage, performance, threshold_versions, emissions)
    comparison.to_csv(package_dir / "tables" / "comparison_main.csv", index=False)
    slim_table(emissions).to_csv(package_dir / "tables" / "emissions.csv", index=False)
    slim_table(threshold_versions).to_csv(package_dir / "tables" / "thresholds.csv", index=False)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Empacota artefatos offline em um Deep Dive consumível pelo app.")
    parser.add_argument("--deep-dive-id", default=DEFAULT_PACKAGE_ID)
    parser.add_argument("--title", default="Comparativo Sellers vs Mercado Crédito")
    parser.add_argument("--subtitle", default="Estrutura, documentação, gatilhos e performance monitorável")
    parser.add_argument("--portfolio-id", default="")
    parser.add_argument("--portfolio-signature", default="")
    parser.add_argument("--output-root", type=Path, default=OUT_ROOT)
    return parser.parse_args()


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
                "subtitle": "Matriz FIDC x métrica",
                "kind": "comparison_matrix",
                "source_file": "tables/comparison_main.csv",
                "first_column": "Nome",
            },
            {
                "id": "emissions",
                "title": "Emissões e cronogramas",
                "kind": "source_table",
                "source_file": "tables/emissions.csv",
                "first_column": "Fundo",
            },
            {
                "id": "thresholds",
                "title": "Triggers e thresholds",
                "kind": "source_table",
                "source_file": "tables/thresholds.csv",
                "first_column": "fundo",
            },
        ],
        "audit": {
            "warnings": [
                "Pacote gerado exclusivamente a partir de arquivos locais já extraídos no repositório.",
                f"Tabela principal com {len(comparison)} linhas; documentos sem PDF local permanecem como lacuna.",
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
    rows: list[dict[str, str]] = []

    def add_row(label: str, values: dict[str, object]) -> None:
        row = {"Nome": label}
        for key in fund_keys:
            row[key] = display(values.get(key))
        rows.append(row)

    add_row("Grupo", {short_name(row.get("fundo")): row.get("grupo") for _, row in coverage.iterrows()})
    add_row("CNPJ", {short_name(row.get("fundo")): row.get("cnpj") for _, row in coverage.iterrows()})
    for metric in ["documentos_inventariados", "pdfs_locais_analisaveis", "documentos_sem_pdf_local", "paginas_pdf_locais"]:
        add_row(metric.replace("_", " ").capitalize(), {short_name(row.get("fundo")): row.get(metric) for _, row in coverage.iterrows()})

    latest_metrics = [
        "PL (R$)",
        "Dir Cred / PL",
        "Vencidos Over 30 d / Crédito",
        "Vencidos Over 60 d / Crédito",
        "Vencidos Over 90 d / Crédito",
        "Vencidos Over 180 d / Crédito",
        "Vencidos Over 360 d / Crédito",
        "PDD / Crédito",
        "PDD / Venc Total",
        "Cotas SR / PL %",
        "Cotas MZ / PL %",
        "Cotas Sub / PL %",
    ]
    for indicator in latest_metrics:
        add_row(indicator, latest_metric_by_fund(performance, indicator, aliases))

    add_row("Linhas de emissões/cronogramas", count_by_short_name(emissions, "CNPJ", aliases))
    add_row("Última evidência de emissão", latest_source_by_fund(emissions, "CNPJ", "Fonte", aliases))

    for key, label in [
        ("credit_rights_allocation_min", "Alocação mínima em DCs"),
        ("subordination_ratio_min", "Subordinação mínima"),
        ("default_rate_evaluation_event", "Evento avaliação por atraso"),
        ("default_rate_early_maturity", "Liquidação/vencimento por atraso"),
        ("pdd_coverage_min", "Cobertura mínima PDD"),
        ("minimum_cash_ratio", "Reserva/caixa mínimo"),
        ("permitted_hedges", "Hedges permitidos"),
    ]:
        add_row(label, latest_threshold_by_fund(threshold_versions, key, aliases))

    return pd.DataFrame(rows)


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


def latest_threshold_by_fund(threshold_versions: pd.DataFrame, key: str, aliases: dict[str, str]) -> dict[str, str]:
    if threshold_versions.empty:
        return {}
    subset = threshold_versions[threshold_versions["chave"].astype(str) == key].copy()
    if subset.empty:
        return {}
    subset["sort_key"] = subset["data_documento"].map(date_sort)
    output = {}
    for cnpj, group in subset.sort_values("sort_key").groupby(subset["cnpj"].map(normalize_cnpj), dropna=False):
        row = group.iloc[-1]
        value = " ".join(str(item) for item in [row.get("comparacao"), row.get("limite")] if str(item or "").strip())
        output[aliases.get(str(cnpj), str(row.get("nome_curto") or row.get("cnpj")))] = value or "—"
    return output


def count_by_short_name(frame: pd.DataFrame, cnpj_col: str, aliases: dict[str, str]) -> dict[str, int]:
    if frame.empty or cnpj_col not in frame.columns:
        return {}
    output: dict[str, int] = {}
    for cnpj, group in frame.groupby(frame[cnpj_col].map(normalize_cnpj), dropna=False):
        name = aliases.get(str(cnpj), short_from_cnpj_or_frame(str(cnpj), group))
        output[name] = len(group)
    return output


def latest_source_by_fund(frame: pd.DataFrame, cnpj_col: str, source_col: str, aliases: dict[str, str]) -> dict[str, str]:
    if frame.empty or cnpj_col not in frame.columns or source_col not in frame.columns:
        return {}
    output: dict[str, str] = {}
    for cnpj, group in frame.groupby(frame[cnpj_col].map(normalize_cnpj), dropna=False):
        name = aliases.get(str(cnpj), short_from_cnpj_or_frame(str(cnpj), group))
        source = str(group[source_col].replace("", pd.NA).dropna().iloc[-1]) if not group[source_col].replace("", pd.NA).dropna().empty else "—"
        output[name] = source
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
