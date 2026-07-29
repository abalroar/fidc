"""Materialize documentary candidates for historical Top 20 ANBIMA review.

The ranking uses CVM monthly PL and the versioned ANBIMA snapshot already
joined to ``base_fundo_cnpj.csv.gz``. Regulations are read page by page. Every
classification produced here remains a documentary candidate for manual
approval; official ANBIMA and CVM fields are never overwritten.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import sys
import unicodedata

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import FundosNetClient, REGULAMENTO_CATEGORIA_ID  # noqa: E402
from services.fundonet_documents import select_latest_public_document  # noqa: E402
from services.industry_taxonomy_review import ANBIMA_REFERENCE_DATE, normalize_cnpj  # noqa: E402


DEFAULT_PERIODS = ("2023-12", "2024-12", "2025-12", "2026-06")
DISPLAY_TYPES = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    "Outros",
)
OUTPUT_COLUMNS = (
    "review_scope",
    "rank_reference",
    "cnpj_fundo",
    "nome_fidc",
    "document_id",
    "document_reference_date",
    "document_url",
    "local_path",
    "pagina_clausula",
    "cedent_originator_explicit",
    "evidence_summary",
    "tipo_anbima_sugerido",
    "foco_anbima_sugerido",
    "tabela_ii_sugerida_documental",
    "taxonomia_funcional_n1_sugerida",
    "taxonomia_funcional_n2_sugerida",
    "reclassification_status",
    "confianca_documental",
    "perimeter_proposal",
    "is_fic_fidc_suggested",
    "manual_validation_reason",
    "reading_method",
    "source_limitations",
)


DOCUMENT_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "adquirencia",
        "patterns": (
            r"ARRANJOS? DE PAGAMENTO",
            r"AGENDA DE RECEBIVEIS",
            r"CREDENCIADORAS?|SUBCREDENCIADORAS?",
            r"LIQUIDACAO.{0,120}TRANSACOES?.{0,80}(?:CARTAO|PAGAMENTO)",
        ),
        "tipo": "Agro, Indústria e Comércio",
        "foco": "Recebíveis Comerciais",
        "tabela_ii": "Adquirência",
        "n1": "Meios de Pagamento e Cartões",
        "n2": "Arranjos de pagamento/adquirência",
    },
    {
        "rule_id": "precatorios_judicial",
        "patterns": (
            r"PRECATORIOS?",
            r"DIREITOS? CREDITORIOS?.{0,120}(?:ACOES? JUDICIAIS|LITIGIOS?|DISPUTAS? JUDICIAIS)",
        ),
        "tipo": "Outros",
        "foco": "Poder Público",
        "tabela_ii": "Ações judiciais",
        "n1": "Judicial/Precatórios/NPL",
        "n2": "Precatórios/direitos judiciais",
    },
    {
        "rule_id": "npl_recuperacao",
        "patterns": (
            r"CREDITOS? INADIMPLIDOS?",
            r"NON[ -]?PERFORMING|\bNPL\b",
            r"RECUPERACAO DE CREDITOS?",
        ),
        "tipo": "Outros",
        "foco": "Recuperação",
        "tabela_ii": "N/D",
        "n1": "Judicial/Precatórios/NPL",
        "n2": "Não padronizado/NPL",
    },
    {
        "rule_id": "ccb_capital_giro",
        "patterns": (
            r"CEDULAS? DE CREDITO BANCARIO",
            r"CAPITAL DE GIRO",
        ),
        "tipo": "Financeiro",
        "foco": "Multicarteira Financeiro",
        "tabela_ii": "Financeiro",
        "n1": "Crédito PJ",
        "n2": "CCB/Notas comerciais/Capital de giro",
    },
    {
        "rule_id": "consignado",
        "patterns": (r"CREDITO CONSIGNADO", r"CONSIGNACAO EM FOLHA"),
        "tipo": "Financeiro",
        "foco": "Crédito Consignado",
        "tabela_ii": "Financeiro",
        "n1": "Crédito PF",
        "n2": "Consignado/INSS",
    },
    {
        "rule_id": "veiculos",
        "patterns": (
            r"FINANCIAMENTO DE VEICULOS?",
            r"ALIENACAO FIDUCIARIA.{0,80}VEICULOS?",
        ),
        "tipo": "Financeiro",
        "foco": "Financiamento de Veículos",
        "tabela_ii": "Financeiro",
        "n1": "Crédito PF",
        "n2": "Auto/Veículos",
    },
    {
        "rule_id": "imobiliario",
        "patterns": (
            r"CREDITO IMOBILIARIO",
            r"FINANCIAMENTO IMOBILIARIO",
        ),
        "tipo": "Financeiro",
        "foco": "Crédito Imobiliário",
        "tabela_ii": "Imobiliário",
        "n1": "Imobiliário",
        "n2": "Imobiliário",
    },
    {
        "rule_id": "agronegocio",
        "patterns": (
            r"CEDULAS? DE PRODUTO RURAL",
            r"CADEIAS? PRODUTIVAS? DO AGRONEGOCIO",
            r"PRODUTORES? RURAIS?",
        ),
        "tipo": "Agro, Indústria e Comércio",
        "foco": "Agronegócio",
        "tabela_ii": "Agronegócio",
        "n1": "Agro",
        "n2": "Agro",
    },
    {
        "rule_id": "credito_corporativo",
        "patterns": (
            r"DEBENTURES?",
            r"NOTAS? COMERCIAIS?",
            r"CREDITO CORPORATIVO",
        ),
        "tipo": "Agro, Indústria e Comércio",
        "foco": "Crédito Corporativo",
        "tabela_ii": "Financeiro",
        "n1": "Crédito PJ",
        "n2": "Crédito privado/mercado de capitais",
    },
    {
        "rule_id": "recebiveis_comerciais",
        "patterns": (
            r"DUPLICATAS?",
            r"VENDAS? MERCANTIS?",
            r"DIREITOS? CREDITORIOS?.{0,300}PRESTACAO DE SERVICOS?",
            r"PRESTACAO DE SERVICOS?.{0,300}DIREITOS? CREDITORIOS?",
        ),
        "tipo": "Agro, Indústria e Comércio",
        "foco": "Recebíveis Comerciais",
        "tabela_ii": "Comercial",
        "n1": "Crédito PJ",
        "n2": "Recebíveis comerciais/multissetorial",
    },
)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(
        r"\s+", " ", "".join(char for char in text if not unicodedata.combining(char))
    ).upper().strip()


def _document_url(cnpj: str) -> str:
    return (
        "https://fnet.bmfbovespa.com.br/fnet/publico/"
        f"abrirGerenciadorDocumentosCVM?cnpjFundo={cnpj}"
    )


def _repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def build_top20_universe(base: pd.DataFrame, periods: tuple[str, ...]) -> pd.DataFrame:
    frame = base[
        base["competencia"].astype(str).isin(periods)
        & ~base["is_fic_fidc"].fillna(False).astype(bool)
    ].copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    frame["pl"] = pd.to_numeric(frame["pl"], errors="coerce")
    frame["tipo_exibicao"] = frame["anbima_tipo"].where(
        frame["anbima_tipo"].isin(DISPLAY_TYPES[:-1]), "Outros"
    )
    frame = frame[frame["pl"].gt(0)].sort_values(
        ["competencia", "tipo_exibicao", "pl", "cnpj_fundo"],
        ascending=[True, True, False, True],
    )
    frame["rank_tipo"] = frame.groupby(
        ["competencia", "tipo_exibicao"]
    ).cumcount() + 1
    top = frame[frame["rank_tipo"].le(20)].copy()
    if len(top) != 80 * len(periods):
        raise ValueError("ranking histórico incompleto para as competências solicitadas")
    return top


def extract_pdf_pages(content: bytes) -> list[str]:
    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(re.sub(r"\s+", " ", page.extract_text() or "").strip())
        except Exception:  # noqa: BLE001
            pages.append("")
    return pages


def _page_evidence(
    pages: list[str], patterns: tuple[str, ...]
) -> tuple[int, str] | None:
    for page_number, page in enumerate(pages, start=1):
        folded = _fold(page)
        for pattern in patterns:
            match = re.search(pattern, folded)
            if match:
                start = max(0, match.start() - 150)
                end = min(len(folded), match.end() + 330)
                return page_number, folded[start:end]
    return None


def classify_regulation_pages(pages: list[str]) -> dict[str, object]:
    matches: list[tuple[dict[str, object], int, str]] = []
    for rule in DOCUMENT_RULES:
        evidence = _page_evidence(pages, rule["patterns"])
        if evidence:
            matches.append((rule, evidence[0], evidence[1]))
    matched_ids = {str(rule["rule_id"]) for rule, _page, _snippet in matches}
    dominance = {
        "adquirencia": {"recebiveis_comerciais"},
        "consignado": {"ccb_capital_giro", "recebiveis_comerciais"},
        "veiculos": {"ccb_capital_giro", "recebiveis_comerciais"},
        "imobiliario": {"ccb_capital_giro", "credito_corporativo"},
        "agronegocio": {"recebiveis_comerciais", "credito_corporativo"},
    }
    dominated = {
        rule_id
        for winner, rule_ids in dominance.items()
        if winner in matched_ids
        for rule_id in rule_ids
    }
    matches = [
        match for match in matches if str(match[0]["rule_id"]) not in dominated
    ]

    participant_patterns = (
        r"(?:CEDENTE|ORIGINADOR)(?:ES)?.{0,180}?CNPJ.{0,40}",
        r"CNPJ.{0,40}.{0,80}?(?:CEDENTE|ORIGINADOR)",
    )
    participant = _page_evidence(pages, participant_patterns)
    participant_text = (
        f"Candidato textual para validação (p. {participant[0]}): {participant[1]}"
        if participant
        else "N/D"
    )
    if not matches:
        return {
            "tipo": "",
            "foco": "",
            "tabela_ii": "",
            "n1": "",
            "n2": "",
            "status": "ambigua",
            "confidence": "baixa",
            "pages": "N/D",
            "evidence": "Regulamento lido sem correspondência documental específica nas regras controladas.",
            "participant": participant_text,
            "reason": "Classificação requer leitura manual da política de investimento e do Anexo Descritivo.",
        }

    unique_pairs = {
        (str(rule["n1"]), str(rule["n2"])) for rule, _page, _evidence in matches
    }
    selected_rule = matches[0][0]
    unambiguous = len(unique_pairs) == 1
    evidence_text = " | ".join(
        f"p. {page}: {rule['rule_id']} - {snippet}"
        for rule, page, snippet in matches[:3]
    )
    return {
        "tipo": selected_rule["tipo"] if unambiguous else "",
        "foco": selected_rule["foco"] if unambiguous else "",
        "tabela_ii": selected_rule["tabela_ii"] if unambiguous else "",
        "n1": selected_rule["n1"] if unambiguous else "",
        "n2": selected_rule["n2"] if unambiguous else "",
        "status": "potencial_reclassificacao" if unambiguous else "ambigua",
        "confidence": "media" if unambiguous else "baixa",
        "pages": ", ".join(f"p. {page}" for _rule, page, _snippet in matches[:3]),
        "evidence": evidence_text[:4000],
        "participant": participant_text[:1600],
        "reason": (
            "Validar manualmente o trecho, o papel econômico e a materialidade da carteira antes de aprovar."
            if unambiguous
            else "O regulamento contém mais de uma família de recebíveis; selecionar uma categoria exige leitura manual e avaliação de materialidade."
        ),
    }


def _local_regulations(inventory_path: Path) -> dict[str, dict[str, str]]:
    if not inventory_path.exists():
        return {}
    inventory = pd.read_csv(inventory_path, dtype=str, keep_default_na=False)
    inventory["cnpj_fundo"] = inventory["cnpj_fundo"].map(normalize_cnpj)
    local_exists = inventory.get("local_exists", pd.Series("", index=inventory.index)).map(
        lambda value: str(value).strip().casefold() in {"true", "1", "sim"}
    )
    frame = inventory[
        inventory.get("document_class", pd.Series("", index=inventory.index))
        .astype(str)
        .str.casefold()
        .eq("regulamento")
        & local_exists
    ].copy()
    frame["_date"] = pd.to_datetime(frame.get("document_date"), errors="coerce")
    frame = frame.sort_values(
        ["cnpj_fundo", "_date", "documento_id"],
        ascending=[True, False, False],
        na_position="last",
    ).drop_duplicates("cnpj_fundo", keep="first")
    return {
        str(row["cnpj_fundo"]): {
            "document_id": str(row.get("documento_id") or ""),
            "document_date": str(row.get("document_date") or ""),
            "local_path": str(row.get("local_path") or ""),
        }
        for row in frame.to_dict(orient="records")
    }


def _fetch_or_load(
    cnpj: str,
    local: dict[str, str] | None,
    raw_dir: Path,
    timeout: int,
) -> tuple[bytes, str, str, str, str]:
    if local:
        path = ROOT / local["local_path"]
        if path.is_file() and path.stat().st_size:
            content = path.read_bytes()
            if content.startswith(b"%PDF"):
                return (
                    content,
                    local["document_id"],
                    local["document_date"],
                    _repo_relative(path),
                    "corpus_local_versionado",
                )
    cached = sorted((raw_dir / cnpj).glob("*_regulamento.pdf"), reverse=True)
    if cached and cached[0].stat().st_size:
        path = cached[0]
        document_id = path.name.split("_", 1)[0]
        return (
            path.read_bytes(),
            document_id,
            "",
            _repo_relative(path),
            "cache_local_da_execucao",
        )
    client = FundosNetClient(timeout_seconds=timeout, max_retries=2)
    documents = client.listar_documentos(
        cnpj, categoria_id=REGULAMENTO_CATEGORIA_ID
    )
    latest = select_latest_public_document(documents)
    if latest is None:
        return b"", "", "", "", "sem_regulamento_listado"
    content = client.download_documento(latest.id)
    fund_dir = raw_dir / cnpj
    fund_dir.mkdir(parents=True, exist_ok=True)
    path = fund_dir / f"{latest.id}_regulamento.pdf"
    path.write_bytes(content)
    return (
        content,
        str(latest.id),
        latest.data_referencia_dt.isoformat() if latest.data_referencia_dt else "",
        _repo_relative(path),
        "fundosnet_download",
    )


def _review_one(
    fund: dict[str, object],
    *,
    local: dict[str, str] | None,
    raw_dir: Path,
    timeout: int,
) -> dict[str, object]:
    cnpj = str(fund["cnpj_fundo"])
    try:
        content, document_id, document_date, local_path, source_status = _fetch_or_load(
            cnpj, local, raw_dir, timeout
        )
        pages = extract_pdf_pages(content) if content.startswith(b"%PDF") else []
        result = classify_regulation_pages(pages)
        extraction_status = (
            f"leitura integral automatizada de {len(pages)} páginas por pypdf"
            if pages
            else "documento sem texto PDF extraível"
        )
        limitation = (
            "A leitura automatizada localiza famílias de recebíveis e candidatos textuais; a decisão permanece manual. "
            f"Fonte do arquivo: {source_status}. Fotografia ANBIMA: {ANBIMA_REFERENCE_DATE}."
        )
    except Exception as exc:  # noqa: BLE001
        document_id = ""
        document_date = ""
        local_path = ""
        result = classify_regulation_pages([])
        extraction_status = "falha de obtenção ou leitura"
        limitation = f"{type(exc).__name__}: {exc}"
    return {
        "review_scope": "top20_por_tipo_periodos_2023_2026",
        "rank_reference": str(fund.get("rank_reference") or ""),
        "cnpj_fundo": cnpj,
        "nome_fidc": str(fund.get("denominacao") or ""),
        "document_id": document_id,
        "document_reference_date": document_date,
        "document_url": _document_url(cnpj),
        "local_path": local_path,
        "pagina_clausula": result["pages"],
        "cedent_originator_explicit": result["participant"],
        "evidence_summary": result["evidence"],
        "tipo_anbima_sugerido": result["tipo"],
        "foco_anbima_sugerido": result["foco"],
        "tabela_ii_sugerida_documental": result["tabela_ii"],
        "taxonomia_funcional_n1_sugerida": result["n1"],
        "taxonomia_funcional_n2_sugerida": result["n2"],
        "reclassification_status": result["status"],
        "confianca_documental": result["confidence"],
        "perimeter_proposal": "",
        "is_fic_fidc_suggested": False,
        "manual_validation_reason": result["reason"],
        "reading_method": extraction_status,
        "source_limitations": limitation,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("data/industry_study/generated_revision/base_fundo_cnpj.csv.gz"),
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=Path("data/raw/industry_top20_taxonomy")
    )
    parser.add_argument("--periods", nargs="+", default=list(DEFAULT_PERIODS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=45)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    periods = tuple(str(period) for period in args.periods)
    base = pd.read_csv(args.base, dtype={"cnpj_fundo": str}, low_memory=False)
    top = build_top20_universe(base, periods)
    latest_rows = (
        top.sort_values(["cnpj_fundo", "competencia", "pl"])
        .drop_duplicates("cnpj_fundo", keep="last")
        .copy()
    )
    appearances = (
        top.groupby("cnpj_fundo", as_index=False)
        .agg(
            rank_reference=(
                "rank_tipo",
                lambda values: ", ".join(str(int(value)) for value in values),
            )
        )
    )
    latest_rows = latest_rows.merge(appearances, on="cnpj_fundo", how="left")
    local = _local_regulations(args.data_dir / "document_inventory.csv.gz")
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    records = latest_rows.to_dict(orient="records")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                _review_one,
                fund,
                local=local.get(str(fund["cnpj_fundo"])),
                raw_dir=args.raw_dir,
                timeout=args.timeout,
            ): fund
            for fund in records
        }
        for position, future in enumerate(as_completed(futures), start=1):
            fund = futures[future]
            rows.append(future.result())
            print(
                f"[{position}/{len(records)}] {fund['cnpj_fundo']} {str(fund['denominacao'])[:70]}",
                flush=True,
            )

    output = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS)).sort_values(
        ["nome_fidc", "cnpj_fundo"]
    )
    if len(output) != top["cnpj_fundo"].nunique() or output["cnpj_fundo"].duplicated().any():
        raise ValueError("saída documental não reconciliou os CNPJs únicos do Top 20")
    output_path = args.data_dir / "industry_top20_taxonomy_document_review.csv"
    output.to_csv(output_path, index=False)
    manifest = {
        "schema_version": "industry-top20-taxonomy-document-review/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periods": list(periods),
        "ranking_rows": int(len(top)),
        "unique_funds": int(len(output)),
        "documents_found": int(output["document_id"].astype(str).str.strip().ne("").sum()),
        "documentary_candidates": int(output["tipo_anbima_sugerido"].astype(str).str.strip().ne("").sum()),
        "source": "CVM Informe Mensal, fotografia ANBIMA versionada e FundosNet/B3",
        "official_fields_mutated": False,
    }
    manifest_path = args.data_dir / "industry_top20_taxonomy_document_review_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[ok] {len(output)} fundos em {output_path}", flush=True)


if __name__ == "__main__":
    main()
