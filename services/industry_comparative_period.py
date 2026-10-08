"""One reporting cut for current FIDC comparisons and their prior-year window."""

from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re


MONTH_LABELS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


@dataclass(frozen=True)
class ComparisonCut:
    year: int
    month: int

    @classmethod
    def from_competence(cls, competence: str) -> "ComparisonCut":
        match = re.fullmatch(r"(\d{4})-?(\d{2})", str(competence).strip())
        if match is None:
            raise ValueError("Competência consolidada deve usar AAAA-MM ou AAAAMM")
        year, month = map(int, match.groups())
        if not 1900 <= year <= 9999 or not 1 <= month <= 12:
            raise ValueError("Competência consolidada inválida")
        return cls(year, month)

    @classmethod
    def from_data_dir(cls, data_dir: str | Path) -> "ComparisonCut":
        data_dir = Path(data_dir)
        status_path = data_dir / "industry_competence_status.csv"
        if status_path.is_file():
            with status_path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                if not {"competencia", "publication_status"}.issubset(reader.fieldnames or ()):
                    raise ValueError("Status de competências sem os campos obrigatórios")
                cuts = [cls.from_competence(row["competencia"]) for row in reader
                        if row["publication_status"] == "completa"]
            if not cuts:
                raise ValueError("Nenhuma competência consolidada disponível")
            return max(cuts, key=lambda cut: (cut.year, cut.month))
        # Older published datasets preserve their last validated snapshot here.
        metadata_path = data_dir / "metadata.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            snapshot = metadata.get("competencia_snapshot")
            if snapshot:
                return cls.from_competence(str(snapshot))
        raise ValueError("Competência consolidada não identificada na base")

    @property
    def competence(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def period_end(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    @property
    def previous_period_end(self) -> date:
        year = self.year - 1
        return date(year, self.month, calendar.monthrange(year, self.month)[1])

    def period_id(self, year: int | None = None) -> str:
        return f"{self.year if year is None else year} jan-{MONTH_LABELS[self.month - 1]}"

    def period_label(self, year: int | None = None) -> str:
        selected_year = self.year if year is None else year
        span = "jan" if self.month == 1 else f"jan–{MONTH_LABELS[self.month - 1]}"
        return f"{span}/{selected_year % 100:02d}"

    def period_key(self, year: int | None = None) -> str:
        selected_year = self.year if year is None else year
        return f"{MONTH_LABELS[self.month - 1]}{selected_year % 100:02d}"

    def to_meta(self) -> dict[str, object]:
        return {
            "current_year": self.year,
            "current_period_start": date(self.year, 1, 1).isoformat(),
            "current_period_end": self.period_end.isoformat(),
            "previous_period_end": self.previous_period_end.isoformat(),
            "period_label": self.period_label(),
            "previous_period_label": self.period_label(self.year - 1),
            "current_period_id": self.period_id(),
            "previous_period_id": self.period_id(self.year - 1),
            "current_period_key": self.period_key(),
            "previous_period_key": self.period_key(self.year - 1),
            "month_count": self.month,
        }
