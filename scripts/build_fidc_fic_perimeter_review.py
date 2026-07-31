#!/usr/bin/env python3
"""Find FIDCs that are, in fact, quota feeders reported outside the FIC bucket.

The industry builder initializes ``is_fic_fidc`` as a legacy nominal signal
derived locally from the registered corporate name.  This script adds curated
quantitative confirmations for vehicles that the upstream signal did not
select.

Some vehicles registered as FIDC never buy a receivable — they hold quotas of
other FIDCs.  Left in the direct universe they double count.  This script
identifies them
from two independent pieces of evidence:

* the fund reports its receivables portfolio and reports it as **zero** in every
  competence where it appears; and
* the same monthly report allocates its assets to ``VL_COTA_FIDC`` — quotas of
  other FIDCs — which is downloaded here straight from FundosNet.

Within this quantitative review, the registered corporate name is recorded as
context and does not decide the override.  The broader perimeter still retains
the separate legacy nominal signal.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fundonet_client import FundosNetClient  # noqa: E402
from services.industry_taxonomy_review import normalize_cnpj  # noqa: E402


LOGGER = logging.getLogger("fic_perimeter")

DEFAULT_PERIODS = ("2023-12", "2024-12", "2025-12", "2026-06")
DEFAULT_DATA_DIR = Path("data/industry_study")
DEFAULT_RAW_DIR = Path("data/raw/fic_perimeter")
REVIEW_FILENAME = "industry_fic_perimeter_review.csv"
OVERRIDES_FILENAME = "fic_perimeter_overrides.csv"

#: Share of the reported assets that must sit in FIDC quotas for the vehicle to
#: be a feeder rather than a fund holding cash between acquisitions.
FEEDER_MIN_SHARE = 0.5

#: Corporate forms used as context in this quantitative review.
FEEDER_NAME_PATTERN = re.compile(
    r"EM COTAS DE FUND|EM COTAS DE FI|FIC DE FIDC|FIC DE FUNDO|FIC-FIDC|FIC FIDC",
    re.IGNORECASE,
)

REVIEW_COLUMNS: tuple[str, ...] = (
    "cnpj_fundo",
    "denominacao",
    "pl_ultima_competencia",
    "competencia_referencia",
    "competencias_sem_direitos_creditorios",
    "competencias_observadas",
    "forma_de_fic_no_nome",
    "informe_documento_id",
    "informe_competencia",
    "vl_cota_fidc",
    "vl_cota_fidc_nao_padrao",
    "vl_soma_aplicacoes",
    "share_cotas_fidc",
    "vl_direitos_creditorios",
    "veredito",
    "evidencia",
    "limitacao",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--periods", default=",".join(DEFAULT_PERIODS))
    parser.add_argument(
        "--min-pl",
        type=float,
        default=0.0,
        help="só consulta o informe de fundos com PL acima deste valor",
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def _boolean(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin({"true", "1", "sim"})


def build_candidates(data_dir: Path, periods: tuple[str, ...]) -> pd.DataFrame:
    """Funds outside the legacy signal that never report receivables."""

    base = pd.read_csv(
        data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz",
        dtype=str,
        keep_default_na=False,
    )
    base["cnpj_fundo"] = base["cnpj_fundo"].map(normalize_cnpj)
    for column in ("pl", "carteira_dc"):
        base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
    for column in ("is_fic_fidc", "reports_carteira_dc"):
        base[column] = _boolean(base[column])
    # O sinal de perímetro vale para o CNPJ inteiro, não para uma competência.
    # Um veículo que comprou recebíveis em qualquer mês da série não é um
    # alimentador estrutural, e marcá-lo como FIC apagaria carteira real do mix.
    # A verificação de ausência de direitos creditórios usa, por isso, todo o
    # histórico disponível, e não apenas as competências de referência.
    ever_held = (
        base[base["carteira_dc"].gt(0.0)]["cnpj_fundo"].unique().tolist()
    )
    scoped = base[
        base["competencia"].isin(periods)
        & ~base["is_fic_fidc"]
        & ~base["cnpj_fundo"].isin(ever_held)
    ].copy()

    without_receivables = (
        scoped["reports_carteira_dc"] & scoped["carteira_dc"].eq(0.0) & scoped["pl"].gt(0.0)
    )
    zero_counts = (
        scoped[without_receivables].groupby("cnpj_fundo").size().rename("competencias_sem_dc")
    )
    total_counts = scoped.groupby("cnpj_fundo").size().rename("competencias_observadas")
    counts = pd.concat([zero_counts, total_counts], axis=1).dropna(subset=["competencias_sem_dc"])
    structural = counts[counts["competencias_sem_dc"] == counts["competencias_observadas"]]

    latest = periods[-1]
    snapshot = (
        scoped.sort_values("competencia")
        .drop_duplicates("cnpj_fundo", keep="last")
        .set_index("cnpj_fundo")
    )
    latest_pl = (
        scoped[scoped["competencia"].eq(latest)].set_index("cnpj_fundo")["pl"]
    )
    frame = structural.join(snapshot[["denominacao"]]).reset_index()
    frame["pl_ultima_competencia"] = frame["cnpj_fundo"].map(latest_pl).fillna(0.0)
    frame["competencia_referencia"] = latest
    frame["forma_de_fic_no_nome"] = frame["denominacao"].map(
        lambda value: bool(FEEDER_NAME_PATTERN.search(str(value)))
    )
    return frame.sort_values("pl_ultima_competencia", ascending=False).reset_index(drop=True)


def _decimal(value: str) -> float:
    text = str(value or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _read_monthly_report(payload: bytes) -> dict[str, float]:
    """Read the asset allocation block of a structured monthly report."""

    text = payload.decode("utf-8", "replace")
    if "<" not in text:
        return {}
    wanted = (
        "VL_COTA_FIDC",
        "VL_COTA_FIDC_NAO_PADRAO",
        "VL_SOM_APLIC_ATIVO",
        "VL_DICRED",
        "VL_CARTEIRA",
    )
    found: dict[str, float] = {}
    for tag in wanted:
        match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
        if match:
            found[tag] = _decimal(match.group(1))
    return found


def inspect_fund(
    cnpj: str, raw_dir: Path, competence: str, timeout: int
) -> dict[str, object]:
    """Download the latest structured monthly report and read its allocation."""

    fund_dir = raw_dir / cnpj
    cached = sorted(fund_dir.glob("*_ime.xml")) if fund_dir.is_dir() else []
    if cached:
        payload = cached[-1].read_bytes()
        return {
            "cnpj_fundo": cnpj,
            "informe_documento_id": cached[-1].name.split("_", 1)[0],
            "informe_competencia": competence,
            **_read_monthly_report(payload),
        }
    client = FundosNetClient(timeout_seconds=timeout, max_retries=2)
    try:
        documents = client.listar_documentos(cnpj)
    except Exception as error:  # noqa: BLE001
        return {"cnpj_fundo": cnpj, "erro": f"listagem: {type(error).__name__}"}
    monthly = [
        document
        for document in documents
        if "informe mensal" in f"{document.tipo}".casefold()
    ]
    if not monthly:
        return {"cnpj_fundo": cnpj, "erro": "sem informe mensal publicado"}
    monthly.sort(
        key=lambda document: (document.data_referencia_dt or date.min, document.id)
    )
    latest = monthly[-1]
    try:
        payload = client.download_documento(latest.id)
    except Exception as error:  # noqa: BLE001
        return {"cnpj_fundo": cnpj, "erro": f"download: {type(error).__name__}"}
    fund_dir.mkdir(parents=True, exist_ok=True)
    (fund_dir / f"{latest.id}_ime.xml").write_bytes(payload)
    return {
        "cnpj_fundo": cnpj,
        "informe_documento_id": str(latest.id),
        "informe_competencia": str(latest.data_referencia or competence),
        **_read_monthly_report(payload),
    }


def build_review(candidates: pd.DataFrame, reports: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.merge(reports, on="cnpj_fundo", how="left")
    for column in (
        "VL_COTA_FIDC",
        "VL_COTA_FIDC_NAO_PADRAO",
        "VL_SOM_APLIC_ATIVO",
        "VL_DICRED",
    ):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    quotas = frame["VL_COTA_FIDC"] + frame["VL_COTA_FIDC_NAO_PADRAO"]
    total = frame["VL_SOM_APLIC_ATIVO"]
    frame["share_cotas_fidc"] = 0.0
    positive = total > 0
    frame.loc[positive, "share_cotas_fidc"] = quotas[positive] / total[positive]

    frame["veredito"] = "sem_evidencia_suficiente"
    frame.loc[
        (frame["share_cotas_fidc"] >= FEEDER_MIN_SHARE) & frame["VL_DICRED"].eq(0.0),
        "veredito",
    ] = "fic_confirmado"
    frame.loc[frame["VL_DICRED"].gt(0.0), "veredito"] = "compra_direitos_creditorios"
    # Após o merge, as linhas que deram certo trazem NaN em ``erro``; convertê-las
    # com ``astype(str)`` produziria a string "nan", que marcaria todo o universo
    # como indisponível.
    failures = (
        frame.get("erro", pd.Series("", index=frame.index))
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("nan", "")
    )
    frame.loc[failures.ne(""), "veredito"] = "informe_indisponivel"

    frame["evidencia"] = [
        (
            f"Informe mensal {row['informe_competencia']} (id {row['informe_documento_id']}): "
            f"cotas de FIDC R$ {(row['VL_COTA_FIDC'] + row['VL_COTA_FIDC_NAO_PADRAO']):,.2f} "
            f"de R$ {row['VL_SOM_APLIC_ATIVO']:,.2f} aplicados "
            f"({row['share_cotas_fidc']:.0%}); direitos creditórios R$ {row['VL_DICRED']:,.2f}. "
            f"A base reporta carteira de direitos creditórios igual a zero em "
            f"{int(row['competencias_sem_dc'])} de {int(row['competencias_observadas'])} "
            "competências observadas."
        )
        if str(row.get("informe_documento_id") or "").strip() not in {"", "nan"}
        else str(row.get("erro") or "Informe mensal não obtido.")
        for _index, row in frame.iterrows()
    ]
    frame["limitacao"] = ""
    frame.loc[frame["veredito"].eq("informe_indisponivel"), "limitacao"] = (
        "Informe mensal estruturado não obtido no FundosNet; o veredito depende "
        "apenas da ausência de carteira de direitos creditórios na base."
    )
    frame = frame.rename(
        columns={
            "competencias_sem_dc": "competencias_sem_direitos_creditorios",
            "VL_COTA_FIDC": "vl_cota_fidc",
            "VL_COTA_FIDC_NAO_PADRAO": "vl_cota_fidc_nao_padrao",
            "VL_SOM_APLIC_ATIVO": "vl_soma_aplicacoes",
            "VL_DICRED": "vl_direitos_creditorios",
        }
    )
    for column in REVIEW_COLUMNS:
        if column not in frame:
            frame[column] = ""
    return frame[list(REVIEW_COLUMNS)].sort_values(
        "pl_ultima_competencia", ascending=False
    ).reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    periods = tuple(part.strip() for part in args.periods.split(",") if part.strip())
    candidates = build_candidates(args.data_dir, periods)
    LOGGER.info("candidatos estruturais: %d", len(candidates))
    if args.min_pl:
        candidates = candidates[candidates["pl_ultima_competencia"].ge(args.min_pl)]
    if args.limit:
        candidates = candidates.head(args.limit)
    LOGGER.info("consultando o informe de %d fundos", len(candidates))

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                inspect_fund, cnpj, args.raw_dir, periods[-1], args.timeout
            ): cnpj
            for cnpj in candidates["cnpj_fundo"]
        }
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 25 == 0:
                LOGGER.info("informes lidos: %d/%d", index, len(futures))

    review = build_review(candidates, pd.DataFrame(results))
    review_path = args.data_dir / REVIEW_FILENAME
    review.to_csv(review_path, index=False)
    LOGGER.info("%s: %s", review_path, review["veredito"].value_counts().to_dict())

    confirmed = review[review["veredito"].eq("fic_confirmado")]
    overrides = pd.DataFrame(
        {
            "cnpj_fundo": confirmed["cnpj_fundo"],
            "denominacao": confirmed["denominacao"],
            "is_fic_fidc": True,
            "evidencia": confirmed["evidencia"],
            "fonte": "Informe Mensal Estruturado CVM via FundosNet",
            "revisado_em_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
        }
    )
    overrides_path = args.data_dir / OVERRIDES_FILENAME
    overrides.to_csv(overrides_path, index=False)
    LOGGER.info("%d correções de perímetro gravadas em %s", len(overrides), overrides_path)
    print(
        json.dumps(
            {
                "candidatos": int(len(review)),
                "veredito": review["veredito"].value_counts().to_dict(),
                "pl_fic_confirmado_brl": float(
                    confirmed["pl_ultima_competencia"].astype(float).sum()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
