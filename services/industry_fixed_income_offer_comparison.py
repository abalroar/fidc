"""Compare closed FIDC offerings with the eligible fixed-income universe.

The comparison uses the official CVM public-offering dataset and keeps the
same release cut-off used by the industry deck: 30 June 2026.  Rows are
deduplicated by ``Numero_Requerimento`` before aggregation.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import math
import unicodedata
from typing import Any
from zipfile import ZipFile

import numpy as np
import pandas as pd


SOURCE_DATASET = "oferta_resolucao_160.csv"
SOURCE_URL = (
    "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/"
    "oferta_distribuicao.zip"
)
SOURCE_AS_OF_DATE = "2026-07-24"
SOURCE_ARCHIVE_SHA256 = (
    "46a5a3c35e500dd4560a5a4b286a7a302311ea02b397c1a67821bc197514b4e5"
)
RELEASE_CUTOFF = "2026-06-30"
OUTPUT_FILENAME = "industry_fixed_income_offer_comparison.csv"

FIDC_INSTRUMENT = "COTAS DE FIDC"
EXCLUDED_INSTRUMENTS = (
    "Cotas de FII",
    "Cotas de FIF",
    "Cotas de FIP",
    "Cotas de FIAGRO - FII",
    "Cotas de FIAGRO - FIP",
    "Cotas de FIAGRO - FIDC",
    "Ações",
    "Cotas de Fundos de Infra",
    "Cotas de Funcine",
    "Certificado de depósito de ações (Unit)",
    "Debêntures Conversíveis",
    "Cotas de FIAGRO",
)

PERIODS: tuple[dict[str, Any], ...] = (
    {
        "period_order": 1,
        "period_label": "2023 FY",
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "is_full_year": True,
        "previous_period_label": "N/D — base inicia em 2023",
        "previous_period_start": "",
        "previous_period_end": "",
    },
    {
        "period_order": 2,
        "period_label": "2024 FY",
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "is_full_year": True,
        "previous_period_label": "2023 FY",
        "previous_period_start": "2023-01-01",
        "previous_period_end": "2023-12-31",
    },
    {
        "period_order": 3,
        "period_label": "2025 FY",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "is_full_year": True,
        "previous_period_label": "2024 FY",
        "previous_period_start": "2024-01-01",
        "previous_period_end": "2024-12-31",
    },
    {
        "period_order": 4,
        "period_label": "2026 jan-jun",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "is_full_year": False,
        "previous_period_label": "2025 jan-jun",
        "previous_period_start": "2025-01-01",
        "previous_period_end": "2025-06-30",
    },
)

INSTRUMENT_LABELS = {
    FIDC_INSTRUMENT: "FIDCs",
    "DEBENTURES": "Debêntures",
    "CERTIFICADOS DE RECEBIVEIS IMOBILIARIOS": "CRI",
    "NOTAS COMERCIAIS": "Notas comerciais",
    "CERTIFICADOS DE RECEBIVEIS DO AGRONEGOCIO": "CRA",
    "OUTROS TITULOS DE SECURITIZACAO": "Outros títulos de securitização",
    "CEDULA DE PRODUTO RURAL FINANCEIRA": "CPR-F",
    "CERTIFICADO DE DIREITOS CREDITORIOS DO AGRONEGOCIO": "CDCA",
    "CERTIFICADOS DE RECEBIVEIS": "Certificados de recebíveis",
    "NOTAS PROMISSORIAS": "Notas promissórias",
}

OUTPUT_COLUMNS = (
    "view_order",
    "view",
    "series_order",
    "series_label",
    "instrument_official",
    "selected_2025_rank",
    "period_order",
    "period_label",
    "period_start",
    "period_end",
    "is_full_year",
    "closed_offers",
    "registered_volume_brl",
    "share_of_period_view_volume",
    "previous_period_label",
    "previous_period_start",
    "previous_period_end",
    "previous_registered_volume_brl",
    "yoy_growth",
    "yoy_comparable",
    "universe_closed_offers",
    "universe_registered_volume_brl",
    "source_dataset",
    "source_url",
    "source_as_of_date",
    "source_archive_sha256",
    "latest_source_closing_date",
    "scope",
    "excluded_instruments",
    "methodology",
)


class FixedIncomeOfferComparisonError(ValueError):
    """Raised when the public-offering comparison violates its contract."""


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.upper().split())


def _archive_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_source(
    archive_path: str | Path,
    *,
    expected_archive_sha256: str | None,
) -> tuple[pd.DataFrame, str]:
    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo CVM de ofertas ausente: {path}")
    digest = _archive_sha256(path)
    if expected_archive_sha256 and digest != expected_archive_sha256:
        raise FixedIncomeOfferComparisonError(
            "SHA-256 do arquivo CVM diverge do snapshot esperado: " + digest
        )
    with ZipFile(path) as archive:
        if SOURCE_DATASET not in archive.namelist():
            raise FixedIncomeOfferComparisonError(
                f"Tabela {SOURCE_DATASET} ausente no arquivo CVM."
            )
        source = pd.read_csv(
            archive.open(SOURCE_DATASET),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )
    required = (
        "Numero_Requerimento",
        "Data_Encerramento",
        "Status_Requerimento",
        "Valor_Mobiliario",
        "Tipo_Oferta",
        "Valor_Total_Registrado",
    )
    missing = [column for column in required if column not in source]
    if missing:
        raise FixedIncomeOfferComparisonError(
            "Colunas CVM obrigatórias ausentes: " + ", ".join(missing)
        )

    source["instrument_norm"] = source["Valor_Mobiliario"].map(normalize_text)
    source["data_encerramento"] = pd.to_datetime(
        source["Data_Encerramento"], errors="coerce"
    )
    source["registered_volume_brl"] = pd.to_numeric(
        source["Valor_Total_Registrado"], errors="coerce"
    )
    excluded = {normalize_text(value) for value in EXCLUDED_INSTRUMENTS}
    selected = source.loc[
        source["Status_Requerimento"].map(normalize_text).eq("OFERTA ENCERRADA")
        & source["Tipo_Oferta"].map(normalize_text).eq("PRIMARIA")
        & source["data_encerramento"].notna()
        & source["data_encerramento"].le(RELEASE_CUTOFF)
        & source["registered_volume_brl"].gt(0)
        & ~source["instrument_norm"].isin(excluded)
    ].copy()
    selected["Numero_Requerimento"] = selected["Numero_Requerimento"].str.strip()
    if selected["Numero_Requerimento"].eq("").any():
        raise FixedIncomeOfferComparisonError(
            "Numero_Requerimento vazio no universo selecionado."
        )
    duplicates = selected.duplicated("Numero_Requerimento", keep=False)
    if duplicates.any():
        comparison = [
            "Data_Encerramento",
            "Valor_Mobiliario",
            "Valor_Total_Registrado",
        ]
        conflicts = [
            str(requirement)
            for requirement, group in selected.loc[duplicates].groupby(
                "Numero_Requerimento"
            )
            if len(group[comparison].drop_duplicates()) != 1
        ]
        if conflicts:
            raise FixedIncomeOfferComparisonError(
                "Numero_Requerimento com linhas conflitantes: "
                + ", ".join(conflicts[:5])
            )
        selected = selected.drop_duplicates("Numero_Requerimento", keep="first")
    return selected, digest


def _period_scope(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame.loc[frame["data_encerramento"].between(start, end)].copy()


def _metrics(frame: pd.DataFrame) -> tuple[int, float]:
    return (
        int(frame["Numero_Requerimento"].nunique()),
        float(frame["registered_volume_brl"].sum()),
    )


def _instrument_label(instrument: str) -> str:
    return INSTRUMENT_LABELS.get(instrument, instrument.title())


def build_fixed_income_offer_comparison(
    archive_path: str | Path,
    *,
    source_as_of_date: str = SOURCE_AS_OF_DATE,
    expected_archive_sha256: str | None = SOURCE_ARCHIVE_SHA256,
    top_instruments: int = 4,
) -> pd.DataFrame:
    """Build the two requested views and their comparable YoY deltas."""

    source, digest = _read_source(
        archive_path,
        expected_archive_sha256=expected_archive_sha256,
    )
    base_2025 = _period_scope(source, "2025-01-01", "2025-12-31")
    ranking_2025 = (
        base_2025.loc[~base_2025["instrument_norm"].eq(FIDC_INSTRUMENT)]
        .groupby("instrument_norm", as_index=False)["registered_volume_brl"]
        .sum()
        .sort_values(
            ["registered_volume_brl", "instrument_norm"],
            ascending=[False, True],
            kind="stable",
        )
        .head(top_instruments)
        .reset_index(drop=True)
    )
    if len(ranking_2025) != top_instruments:
        raise FixedIncomeOfferComparisonError(
            f"2025 não contém {top_instruments} instrumentos elegíveis."
        )
    ranking_2025["selected_2025_rank"] = np.arange(1, len(ranking_2025) + 1)
    top_rank = dict(
        zip(
            ranking_2025["instrument_norm"],
            ranking_2025["selected_2025_rank"],
            strict=True,
        )
    )
    top_series = [FIDC_INSTRUMENT, *ranking_2025["instrument_norm"].tolist()]
    exclusions = " | ".join(EXCLUDED_INSTRUMENTS)
    scope = (
        "Oferta primária | status oficial Oferta Encerrada | "
        "Data_Encerramento no período | Valor_Total_Registrado positivo | "
        "instrumentos da lista de exclusão removidos"
    )
    methodology = (
        "Uma oferta = Numero_Requerimento. 2024/2025 YoY compara anos completos; "
        "2026 compara jan-jun/26 com jan-jun/25. Os instrumentos materiais são os "
        "quatro maiores tipos não FIDC por volume registrado em 2025FY."
    )
    rows: list[dict[str, Any]] = []

    for period in PERIODS:
        current = _period_scope(
            source, period["period_start"], period["period_end"]
        )
        current_offers, current_volume = _metrics(current)
        previous = (
            _period_scope(
                source,
                period["previous_period_start"],
                period["previous_period_end"],
            )
            if period["previous_period_start"]
            else source.iloc[0:0].copy()
        )

        views = (
            (
                1,
                "FIDCs vs demais elegíveis",
                (
                    (1, "FIDCs", FIDC_INSTRUMENT, 0),
                    (2, "Demais elegíveis", "__REST__", 0),
                ),
            ),
            (
                2,
                "FIDCs vs instrumentos materiais de 2025",
                tuple(
                    (
                        index + 1,
                        _instrument_label(instrument),
                        instrument,
                        int(top_rank.get(instrument, 0)),
                    )
                    for index, instrument in enumerate(top_series)
                ),
            ),
        )
        for view_order, view, series in views:
            current_series_values: list[tuple[int, str, str, int, int, float, float]] = []
            for series_order, label, instrument, selected_rank in series:
                if instrument == "__REST__":
                    current_scope = current.loc[
                        ~current["instrument_norm"].eq(FIDC_INSTRUMENT)
                    ]
                    previous_scope = previous.loc[
                        ~previous["instrument_norm"].eq(FIDC_INSTRUMENT)
                    ]
                    official = "Todos os instrumentos elegíveis, exceto Cotas de FIDC"
                else:
                    current_scope = current.loc[
                        current["instrument_norm"].eq(instrument)
                    ]
                    previous_scope = previous.loc[
                        previous["instrument_norm"].eq(instrument)
                    ]
                    official = instrument
                offers, volume = _metrics(current_scope)
                _, previous_volume = _metrics(previous_scope)
                current_series_values.append(
                    (
                        series_order,
                        label,
                        official,
                        selected_rank,
                        offers,
                        volume,
                        previous_volume,
                    )
                )
            view_total = sum(item[5] for item in current_series_values)
            for (
                series_order,
                label,
                official,
                selected_rank,
                offers,
                volume,
                previous_volume,
            ) in current_series_values:
                yoy_comparable = bool(period["previous_period_start"])
                rows.append(
                    {
                        "view_order": view_order,
                        "view": view,
                        "series_order": series_order,
                        "series_label": label,
                        "instrument_official": official,
                        "selected_2025_rank": selected_rank,
                        "period_order": period["period_order"],
                        "period_label": period["period_label"],
                        "period_start": period["period_start"],
                        "period_end": period["period_end"],
                        "is_full_year": period["is_full_year"],
                        "closed_offers": offers,
                        "registered_volume_brl": volume,
                        "share_of_period_view_volume": (
                            volume / view_total if view_total else 0.0
                        ),
                        "previous_period_label": period["previous_period_label"],
                        "previous_period_start": period["previous_period_start"],
                        "previous_period_end": period["previous_period_end"],
                        "previous_registered_volume_brl": (
                            previous_volume if yoy_comparable else np.nan
                        ),
                        "yoy_growth": (
                            volume / previous_volume - 1
                            if yoy_comparable and previous_volume > 0
                            else np.nan
                        ),
                        "yoy_comparable": yoy_comparable
                        and previous_volume > 0,
                        "universe_closed_offers": current_offers,
                        "universe_registered_volume_brl": current_volume,
                        "source_dataset": SOURCE_DATASET,
                        "source_url": SOURCE_URL,
                        "source_as_of_date": source_as_of_date,
                        "source_archive_sha256": digest,
                        "latest_source_closing_date": RELEASE_CUTOFF,
                        "scope": scope,
                        "excluded_instruments": exclusions,
                        "methodology": methodology,
                    }
                )
    output = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    return validate_fixed_income_offer_comparison(output)


def validate_fixed_income_offer_comparison(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in OUTPUT_COLUMNS if column not in frame]
    if missing:
        raise FixedIncomeOfferComparisonError(
            "Comparativo sem colunas: " + ", ".join(missing)
        )
    result = frame.loc[:, OUTPUT_COLUMNS].copy()
    if len(result) != 28:
        raise FixedIncomeOfferComparisonError(
            f"Comparativo deveria conter 28 linhas; contém {len(result)}."
        )
    key = ["view", "series_label", "period_label"]
    if result.duplicated(key).any():
        raise FixedIncomeOfferComparisonError(
            "Comparativo contém chaves duplicadas."
        )
    expected_periods = [period["period_label"] for period in PERIODS]
    if (
        result.sort_values("period_order")["period_label"].drop_duplicates().tolist()
        != expected_periods
    ):
        raise FixedIncomeOfferComparisonError(
            "Comparativo contém períodos inesperados."
        )
    for column in (
        "view_order",
        "series_order",
        "selected_2025_rank",
        "period_order",
        "closed_offers",
        "registered_volume_brl",
        "share_of_period_view_volume",
        "universe_closed_offers",
        "universe_registered_volume_brl",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any() or not np.isfinite(
            result[column].to_numpy(dtype=float)
        ).all():
            raise FixedIncomeOfferComparisonError(
                f"Comparativo contém valor inválido em {column}."
            )
        if (result[column] < 0).any():
            raise FixedIncomeOfferComparisonError(
                f"Comparativo contém valor negativo em {column}."
            )
    for column in ("previous_registered_volume_brl", "yoy_growth"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("is_full_year", "yoy_comparable"):
        if result[column].dtype != bool:
            normalized = result[column].astype(str).str.strip().str.casefold()
            if not normalized.isin({"true", "false", "1", "0"}).all():
                raise FixedIncomeOfferComparisonError(
                    f"Comparativo contém booleano inválido em {column}."
                )
            result[column] = normalized.isin({"true", "1"})

    if not result.loc[result["period_label"].eq("2023 FY"), "yoy_growth"].isna().all():
        raise FixedIncomeOfferComparisonError(
            "2023 deve permanecer sem YoY porque a base começa nesse ano."
        )
    comparable = result["yoy_comparable"]
    expected_yoy = (
        result.loc[comparable, "registered_volume_brl"]
        / result.loc[comparable, "previous_registered_volume_brl"]
        - 1
    )
    if not np.isclose(
        result.loc[comparable, "yoy_growth"],
        expected_yoy,
        rtol=1e-10,
        atol=1e-10,
    ).all():
        raise FixedIncomeOfferComparisonError(
            "Crescimento YoY não reconcilia com os volumes comparáveis."
        )

    view_a = result[result["view"].eq("FIDCs vs demais elegíveis")]
    for _, period in view_a.groupby("period_label"):
        if len(period) != 2:
            raise FixedIncomeOfferComparisonError(
                "Visão FIDC versus demais deve conter duas séries por período."
            )
        if not math.isclose(
            float(period["registered_volume_brl"].sum()),
            float(period["universe_registered_volume_brl"].iloc[0]),
            rel_tol=1e-10,
            abs_tol=1e-4,
        ):
            raise FixedIncomeOfferComparisonError(
                "FIDCs e demais não reconciliam com o universo elegível."
            )
    view_b = result[
        result["view"].eq("FIDCs vs instrumentos materiais de 2025")
    ]
    if view_b["series_label"].nunique() != 5:
        raise FixedIncomeOfferComparisonError(
            "Visão de instrumentos materiais deve conter FIDCs e quatro pares."
        )
    if view_b.groupby("period_label").size().ne(5).any():
        raise FixedIncomeOfferComparisonError(
            "Visão de instrumentos materiais incompleta."
        )
    fidc_a = view_a[view_a["series_label"].eq("FIDCs")].sort_values(
        "period_order"
    )
    fidc_b = view_b[view_b["series_label"].eq("FIDCs")].sort_values(
        "period_order"
    )
    if not np.isclose(
        fidc_a["registered_volume_brl"],
        fidc_b["registered_volume_brl"],
        rtol=1e-12,
        atol=1e-4,
    ).all():
        raise FixedIncomeOfferComparisonError(
            "Volume de FIDCs diverge entre as duas visões."
        )
    return result.sort_values(
        ["view_order", "period_order", "series_order"], kind="stable"
    ).reset_index(drop=True)


def load_materialized_fixed_income_offer_comparison(
    data_dir: str | Path,
) -> pd.DataFrame:
    path = Path(data_dir) / OUTPUT_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Comparativo de ofertas ausente: {path}")
    return validate_fixed_income_offer_comparison(
        pd.read_csv(path, low_memory=False)
    )


def write_fixed_income_offer_comparison(
    frame: pd.DataFrame,
    output_dir: str | Path,
) -> Path:
    output = validate_fixed_income_offer_comparison(frame)
    path = Path(output_dir) / OUTPUT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    return path


__all__ = [
    "EXCLUDED_INSTRUMENTS",
    "FixedIncomeOfferComparisonError",
    "OUTPUT_FILENAME",
    "RELEASE_CUTOFF",
    "SOURCE_ARCHIVE_SHA256",
    "SOURCE_AS_OF_DATE",
    "SOURCE_DATASET",
    "SOURCE_URL",
    "build_fixed_income_offer_comparison",
    "load_materialized_fixed_income_offer_comparison",
    "normalize_text",
    "validate_fixed_income_offer_comparison",
    "write_fixed_income_offer_comparison",
]
