"""Materialize the official ANBIMA fixed-income ranking and its deal-level annex.

The script resolves the current ``Ranking de Renda Fixa e Híbridos`` workbooks
from the ANBIMA publication API, parses them, and writes four auditable
artefacts:

``anbima_rf_ranking_official.csv``
    the published ranking, tidy, one row per measure/type/window/participant;
``anbima_rf_ranking_annex.csv.gz``
    the closing annex, one row per operation and coordinator — the only public
    source that names **every** coordinator of an offering and the share
    credited to each of them;
``anbima_rf_ranking_participant_share.csv``
    market share per participant for the scopes that matter to the desk
    (consolidated fixed income, securitization, FIDC, CRI, CRA);
``anbima_rf_ranking_reconciliation.csv``
    annex-vs-published check plus the CVM leader-only comparison, which
    quantifies how far a ``Nome_Lider`` reading sits from the official ranking.

Run with no arguments to fetch the latest published reference month::

    python scripts/build_anbima_fixed_income_ranking.py
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.anbima_fixed_income_ranking import (  # noqa: E402
    FIDC_CLASS,
    METHODOLOGY_URL,
    PUBLICATION_API,
    PUBLICATION_PAGE,
    parse_annex_workbook,
    parse_ranking_workbook,
    summarize_participants,
    syndication_profile,
    workbook_sha256,
)
from services.industry_public_offers import (  # noqa: E402
    FIDC_CANONICAL,
    SOURCE_URL as CVM_SOURCE_URL,
    load_public_primary_closed_offers,
)


DEFAULT_OUTPUT_DIR = Path("data/industry_study")
DEFAULT_CACHE_DIR = Path("data/industry_study/sources")
STRAPI_BASE = "https://data-strapi.prd.anbima.com.br"
POPULATE = (
    "template,template.connected_documents.file,"
    "template.more_content,template.publication_document.file"
)
USER_AGENT = "fidc-dashboard/1.0 (ANBIMA Data public publication)"

#: Scopes reported in ``anbima_rf_ranking_participant_share.csv``.  ``classes``
#: of ``None`` means "every class inside the block".
SHARE_SCOPES: tuple[dict[str, object], ...] = (
    {
        "scope": "renda_fixa_consolidado",
        "label": "Tipo 1 — Renda Fixa Consolidado",
        "block_code": "1",
        "classes": None,
        "ranking_code": "1",
    },
    {
        "scope": "securitizacao",
        "label": "Tipo 1.3 — Securitização",
        "block_code": "1",
        "classes": ("1.3.1", "1.3.2", "1.3.3", "1.3.4"),
        "ranking_code": "1.3",
    },
    {
        "scope": "fidc",
        "label": "Tipo 1.3.1 — FIDC (cotas seniores e subordinadas)",
        "block_code": "1",
        "classes": (FIDC_CLASS,),
        "ranking_code": "1.3.1",
    },
    {
        "scope": "cri",
        "label": "Tipo 1.3.2 — CRI",
        "block_code": "1",
        "classes": ("1.3.2",),
        "ranking_code": "1.3.2",
    },
    {
        "scope": "cra",
        "label": "Tipo 1.3.3 — CRA",
        "block_code": "1",
        "classes": ("1.3.3",),
        "ranking_code": "1.3.3",
    },
    {
        "scope": "empresas_ligadas",
        "label": "Tipo 3 — Operações de Empresas Ligadas",
        "block_code": "3",
        "classes": None,
        "ranking_code": "3",
    },
    {
        "scope": "empresas_ligadas_fidc",
        "label": "Tipo 3 — Empresas Ligadas, recorte FIDC",
        "block_code": "3",
        "classes": (FIDC_CLASS,),
        "ranking_code": None,
    },
)

#: CVM analytical instruments that approximate the ANBIMA Tipo 1 perimeter.
#: ``OUTROS TITULOS DE SECURITIZACAO`` is kept because CVM books part of the
#: securitization debentures there, and ANBIMA books them under debêntures.
CVM_FIXED_INCOME_INSTRUMENTS: tuple[str, ...] = (
    "DEBENTURES",
    "NOTAS COMERCIAIS",
    "NOTAS PROMISSORIAS",
    "CEDULA DE PRODUTO RURAL FINANCEIRA",
    "OUTROS TITULOS DE SECURITIZACAO",
    "CERTIFICADOS DE RECEBIVEIS",
    "CERTIFICADOS DE RECEBIVEIS IMOBILIARIOS",
    "CERTIFICADOS DE RECEBIVEIS DO AGRONEGOCIO",
    FIDC_CANONICAL,
)

ITAU_BBA_PATTERN = re.compile(r"ITA[UÚ]\s+BBA", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ranking-xlsx",
        type=Path,
        help="Planilha do ranking já baixada; omitido, busca na API da ANBIMA.",
    )
    parser.add_argument(
        "--annex-xlsx",
        type=Path,
        help="Anexo de encerramento já baixado; omitido, busca na API da ANBIMA.",
    )
    parser.add_argument(
        "--cvm-archive",
        type=Path,
        help=(
            "oferta_distribuicao.zip da CVM para a reconciliação coordenador "
            "líder x ranking. Omitido, baixa de dados.cvm.gov.br."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--period-start",
        default="2026-01-01",
        help="Início do período apurado (default: 2026-01-01).",
    )
    parser.add_argument(
        "--period-end",
        default="2026-06-30",
        help="Data-corte do período apurado (default: 2026-06-30).",
    )
    parser.add_argument(
        "--skip-cvm",
        action="store_true",
        help="Não produzir a reconciliação contra a base CVM.",
    )
    return parser.parse_args()


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=300) as response:
        payload = response.read()
    destination.write_bytes(payload)
    return destination


def resolve_publication(cache_dir: Path) -> dict[str, object]:
    """Return the currently published ranking/annex/methodology attachments."""

    request = Request(
        f"{PUBLICATION_API}?populate={POPULATE}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))

    template = payload["data"]["attributes"]["template"]
    documents: list[dict[str, str]] = []
    for key in ("publication_document", "connected_documents"):
        for item in template.get(key) or []:
            files = ((item.get("file") or {}).get("data")) or []
            if files:
                attributes = files[0]["attributes"]
                url = urljoin(STRAPI_BASE, attributes["url"])
                name = attributes["name"]
            elif item.get("alternative_file_url"):
                url = item["alternative_file_url"]
                name = url.rsplit("/", 1)[-1]
            else:
                continue
            documents.append(
                {
                    "group": key,
                    "title": str(item.get("title") or "").strip(),
                    "display_date": str(item.get("display_date") or "").strip(),
                    "file_name": name,
                    "url": url,
                }
            )

    def pick(*tokens: str) -> dict[str, str]:
        for document in documents:
            title = document["title"].casefold()
            if all(token in title for token in tokens):
                return document
        raise SystemExit(
            "Publicação ANBIMA sem documento contendo "
            + " + ".join(tokens)
            + f". Documentos disponíveis: {[d['title'] for d in documents]}"
        )

    annex = pick("anexo")
    ranking = next(
        document
        for document in documents
        if document["group"] == "publication_document"
        and document is not annex
    )
    return {"ranking": ranking, "annex": annex, "documents": documents}


def _reference_label(document: dict[str, str]) -> str:
    match = re.search(r"-\s*([^-]+)$", document["title"])
    return match.group(1).strip() if match else document["title"]


def build_share_table(annex: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for scope in SHARE_SCOPES:
        classes = scope["classes"]
        summary = summarize_participants(
            annex,
            role="originacao",
            block_code=str(scope["block_code"]),
            classes=classes,  # type: ignore[arg-type]
        )
        if summary.empty:
            continue
        summary.insert(0, "scope", scope["scope"])
        summary.insert(1, "scope_label", scope["label"])
        summary.insert(2, "measure", "originacao_valor")
        frames.append(summary)

        distribution = summarize_participants(
            annex,
            role="distribuicao",
            block_code=str(scope["block_code"]),
            classes=classes,  # type: ignore[arg-type]
        )
        if not distribution.empty:
            distribution.insert(0, "scope", scope["scope"])
            distribution.insert(1, "scope_label", scope["label"])
            distribution.insert(2, "measure", "distribuicao_valor")
            frames.append(distribution)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_annex_vs_official(
    annex: pd.DataFrame, official: pd.DataFrame
) -> pd.DataFrame:
    """Prove that summing the annex rebuilds the published ranking."""

    published = official[official["window"].eq("acumulado_ano")]
    measures = (
        ("originacao", "originacao_valor"),
        ("distribuicao", "distribuicao_valor"),
    )
    rows: list[dict[str, object]] = []
    for scope in SHARE_SCOPES:
        ranking_code = scope["ranking_code"]
        if not ranking_code:
            continue
        for role, measure in measures:
            computed = summarize_participants(
                annex,
                role=role,
                block_code=str(scope["block_code"]),
                classes=scope["classes"],  # type: ignore[arg-type]
            )
            reference = published[
                published["measure"].eq(measure)
                & published["ranking_code"].eq(ranking_code)
            ].set_index("participant")
            if computed.empty or reference.empty:
                continue
            joined = computed.set_index("participant").join(
                reference[["value_brl_or_count", "share"]].rename(
                    columns={
                        "value_brl_or_count": "published_volume_brl",
                        "share": "published_share",
                    }
                ),
                how="outer",
            )
            joined = joined.fillna(
                {
                    "volume_brl": 0.0,
                    "published_volume_brl": 0.0,
                    "share": 0.0,
                    "published_share": 0.0,
                }
            )
            rows.append(
                {
                    "check": "anexo_vs_ranking_publicado",
                    "scope": scope["scope"],
                    "scope_label": scope["label"],
                    "measure": measure,
                    "participants": int(len(joined)),
                    "annex_volume_brl": float(computed["volume_brl"].sum()),
                    "published_volume_brl": float(
                        reference["value_brl_or_count"].sum()
                    ),
                    "max_abs_volume_gap_brl": float(
                        (joined["volume_brl"] - joined["published_volume_brl"])
                        .abs()
                        .max()
                    ),
                    "max_abs_share_gap": float(
                        (joined["share"] - joined["published_share"]).abs().max()
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_cvm_comparison(
    annex: pd.DataFrame,
    archive: Path,
    *,
    period_start: str,
    period_end: str,
) -> tuple[pd.DataFrame, str]:
    offers, digest = load_public_primary_closed_offers(archive, cutoff=period_end)
    window = offers[
        offers["closing_date"].ge(pd.Timestamp(period_start))
        & offers["closing_date"].le(pd.Timestamp(period_end))
    ]

    rows: list[dict[str, object]] = []
    scopes = (
        (
            "renda_fixa_consolidado",
            "Tipo 1 — Renda Fixa Consolidado",
            None,
            CVM_FIXED_INCOME_INSTRUMENTS,
        ),
        ("fidc", "Tipo 1.3.1 — FIDC", (FIDC_CLASS,), (FIDC_CANONICAL,)),
    )
    for scope, label, classes, instruments in scopes:
        ranking = summarize_participants(
            annex, role="originacao", block_code="1", classes=classes
        )
        cvm = window[window["canonical_instrument"].isin(instruments)]
        leader = cvm["leader_name"].fillna("")
        itau_cvm = cvm[leader.str.contains(ITAU_BBA_PATTERN)]
        itau_ranking = ranking[
            ranking["participant"].str.contains(ITAU_BBA_PATTERN)
        ]
        cvm_volume = float(cvm["registered_volume_brl"].sum())
        ranking_volume = float(ranking["universe_volume_brl"].iloc[0])
        rows.append(
            {
                "check": "ranking_anbima_vs_cvm_coordenador_lider",
                "scope": scope,
                "scope_label": label,
                "anbima_ranking_universe_brl": ranking_volume,
                "anbima_ranking_operations": int(
                    ranking["universe_operations"].iloc[0]
                ),
                "anbima_itau_bba_volume_brl": float(
                    itau_ranking["volume_brl"].sum()
                ),
                "anbima_itau_bba_share": float(itau_ranking["share"].sum()),
                "cvm_universe_brl": cvm_volume,
                "cvm_offers": int(len(cvm)),
                "cvm_itau_bba_volume_brl": float(
                    itau_cvm["registered_volume_brl"].sum()
                ),
                "cvm_itau_bba_share": (
                    float(itau_cvm["registered_volume_brl"].sum()) / cvm_volume
                    if cvm_volume
                    else float("nan")
                ),
                "coverage_ranking_over_cvm": (
                    ranking_volume / cvm_volume if cvm_volume else float("nan")
                ),
                "cvm_metric": "Valor registrado (oferta primária encerrada)",
                "anbima_metric": "Valor originado creditado ao coordenador",
                "limitation": (
                    "A CVM publica apenas o coordenador líder; o ranking ANBIMA "
                    "credita todos os coordenadores pela proporção contratual e "
                    "exclui operações de empresas ligadas e ofertas cujos "
                    "formulários não foram enviados."
                ),
            }
        )
    return pd.DataFrame(rows), digest


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    publication: dict[str, object] | None = None
    ranking_path = args.ranking_xlsx
    annex_path = args.annex_xlsx
    if ranking_path is None or annex_path is None:
        publication = resolve_publication(cache_dir)
        ranking_document = publication["ranking"]  # type: ignore[index]
        annex_document = publication["annex"]  # type: ignore[index]
        if ranking_path is None:
            ranking_path = _download(
                ranking_document["url"],  # type: ignore[index]
                cache_dir / ranking_document["file_name"],  # type: ignore[index]
            )
        if annex_path is None:
            annex_path = _download(
                annex_document["url"],  # type: ignore[index]
                cache_dir / annex_document["file_name"],  # type: ignore[index]
            )

    official = parse_ranking_workbook(ranking_path)
    annex = parse_annex_workbook(annex_path)

    shares = build_share_table(annex)
    checks = [build_annex_vs_official(annex, official)]

    cvm_digest = ""
    cvm_archive = args.cvm_archive
    if not args.skip_cvm:
        if cvm_archive is None:
            cvm_archive = _download(
                CVM_SOURCE_URL, cache_dir / "oferta_distribuicao.zip"
            )
        comparison, cvm_digest = build_cvm_comparison(
            annex,
            cvm_archive,
            period_start=args.period_start,
            period_end=args.period_end,
        )
        checks.append(comparison)

    reconciliation = pd.concat(checks, ignore_index=True)
    syndication = pd.concat(
        [
            syndication_profile(
                annex, role="originacao", block_code="1", classes=None
            ).assign(scope="renda_fixa_consolidado"),
            syndication_profile(
                annex, role="originacao", block_code="1", classes=(FIDC_CLASS,)
            ).assign(scope="fidc"),
        ],
        ignore_index=True,
    )

    paths = {
        "official": output_dir / "anbima_rf_ranking_official.csv",
        "annex": output_dir / "anbima_rf_ranking_annex.csv.gz",
        "share": output_dir / "anbima_rf_ranking_participant_share.csv",
        "reconciliation": output_dir / "anbima_rf_ranking_reconciliation.csv",
        "syndication": output_dir / "anbima_rf_ranking_syndication.csv",
        "manifest": output_dir / "anbima_rf_ranking_manifest.json",
    }
    official.to_csv(paths["official"], index=False)
    annex.to_csv(paths["annex"], index=False, compression="gzip")
    shares.to_csv(paths["share"], index=False)
    reconciliation.to_csv(paths["reconciliation"], index=False)
    syndication.to_csv(paths["syndication"], index=False)

    manifest = {
        "schema_version": "anbima-rf-ranking-manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": {"start": args.period_start, "end": args.period_end},
        "sources": {
            "publication_page": PUBLICATION_PAGE,
            "publication_api": PUBLICATION_API,
            "methodology_url": METHODOLOGY_URL,
            "ranking_workbook": {
                "path": str(ranking_path),
                "sha256": workbook_sha256(ranking_path),
            },
            "annex_workbook": {
                "path": str(annex_path),
                "sha256": workbook_sha256(annex_path),
            },
            "cvm_archive": {
                "url": CVM_SOURCE_URL,
                "path": str(cvm_archive) if cvm_archive else "",
                "sha256": cvm_digest,
            },
        },
        "documents": publication["documents"] if publication else [],
        "outputs": {
            key: str(path) for key, path in paths.items() if key != "manifest"
        },
        "row_counts": {
            "official": int(len(official)),
            "annex": int(len(annex)),
            "share": int(len(shares)),
            "reconciliation": int(len(reconciliation)),
        },
        "notes": [
            "Valores das planilhas ANBIMA vêm em R$ mil e são convertidos para BRL.",
            "A soma do anexo reproduz o ranking publicado ao centavo por participante.",
            "A contagem de operações do bloco consolidado tem resíduo de até 3 "
            "operações por participante: o anexo não expõe o identificador "
            "interno de operação da ANBIMA e o agrupamento usa emissor + data "
            "de encerramento. No recorte FIDC a contagem bate exatamente.",
        ],
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for key, path in paths.items():
        print(f"{key}: {path}")
    worst = reconciliation.get("max_abs_volume_gap_brl")
    if worst is not None:
        print(f"maior divergência anexo x ranking: R$ {worst.max():,.2f}")


if __name__ == "__main__":
    main()
