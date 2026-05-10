from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from services.regulatory_knowledge import normalize_cnpj


REGULATORY_PROFILES_DIR = Path("data/regulatory_profiles")


@dataclass(frozen=True)
class CuratedRegulatoryProfile:
    cnpj: str
    emissions_df: pd.DataFrame
    criteria_df: pd.DataFrame
    source_files: tuple[Path, ...]

    @property
    def available(self) -> bool:
        return not self.emissions_df.empty or not self.criteria_df.empty


def load_curated_regulatory_profile(
    cnpj: str,
    *,
    base_dir: Path = REGULATORY_PROFILES_DIR,
) -> CuratedRegulatoryProfile | None:
    digits = normalize_cnpj(cnpj)
    if len(digits) != 14 or not base_dir.exists():
        return None

    emissions_frames: list[pd.DataFrame] = []
    criteria_frames: list[pd.DataFrame] = []
    sources: list[Path] = []

    for path in sorted(base_dir.glob("*.csv")):
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, pd.errors.ParserError):
            continue
        if "CNPJ" not in frame.columns:
            continue
        frame = frame[frame["CNPJ"].map(normalize_cnpj) == digits].copy()
        if frame.empty:
            continue
        sources.append(path)
        if {"Cota/Classe", "Amortização principal"}.issubset(frame.columns):
            emissions_frames.append(frame)
        elif {"Critério", "Monitorabilidade IME"}.issubset(frame.columns):
            criteria_frames.append(frame)

    emissions_df = _concat_or_empty(emissions_frames)
    criteria_df = _concat_or_empty(criteria_frames)
    if emissions_df.empty and criteria_df.empty:
        return None
    return CuratedRegulatoryProfile(
        cnpj=digits,
        emissions_df=emissions_df,
        criteria_df=criteria_df,
        source_files=tuple(dict.fromkeys(sources)),
    )


def payment_calendar_rows(emissions_df: pd.DataFrame) -> list[dict[str, str]]:
    if emissions_df.empty:
        return []

    rows: list[dict[str, str]] = []
    for _, item in emissions_df.iterrows():
        cota = str(item.get("Cota/Classe") or "").strip()
        tipo = str(item.get("Tipo") or "").strip()
        source = str(item.get("Fonte") or "").strip()

        juros = str(item.get("Juros/remuneração") or "").strip()
        if _has_calendar_info(juros):
            rows.append(
                {
                    "Data/janela": "Recorrente",
                    "Cota/Classe": cota,
                    "Tipo": tipo,
                    "Evento": "Juros/remuneração",
                    "Detalhe": juros,
                    "Fonte": source,
                }
            )

        amortizacao = str(item.get("Amortização principal") or "").strip()
        if not _has_calendar_info(amortizacao):
            continue

        dated = _dated_payment_entries(amortizacao)
        if dated:
            for date_label, detail in dated:
                rows.append(
                    {
                        "Data/janela": date_label,
                        "Cota/Classe": cota,
                        "Tipo": tipo,
                        "Evento": "Amortização principal",
                        "Detalhe": detail,
                        "Fonte": source,
                    }
                )
            continue

        rows.append(
            {
                "Data/janela": _payment_window_label(amortizacao),
                "Cota/Classe": cota,
                "Tipo": tipo,
                "Evento": "Amortização principal",
                "Detalhe": amortizacao,
                "Fonte": source,
            }
        )
    return rows


def _concat_or_empty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)


def _has_calendar_info(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return lowered not in {
        "não identificado",
        "não identificada",
        "não identificado nos pdfs baixados",
        "sem calendário fixo identificado",
    }


def _dated_payment_entries(value: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for match in re.finditer(r"(\d{2}/\d{2}/\d{4})\s*:\s*([^;]+)", value):
        entries.append((match.group(1), match.group(2).strip()))
    return entries


def _payment_window_label(value: str) -> str:
    match = re.search(r"(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", value)
    if match:
        return f"{match.group(1)} → {match.group(2)}"
    return "Conforme regra"

