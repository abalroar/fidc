from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEEP_DIVE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DeepDiveTableSpec:
    id: str
    title: str
    source_file: str
    subtitle: str = ""
    first_column: str = "Nome"
    kind: str = "comparison_matrix"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DeepDiveTableSpec":
        return cls(
            id=str(payload.get("id") or "").strip(),
            title=str(payload.get("title") or payload.get("id") or "").strip(),
            source_file=str(payload.get("source_file") or "").strip(),
            subtitle=str(payload.get("subtitle") or "").strip(),
            first_column=str(payload.get("first_column") or "Nome").strip() or "Nome",
            kind=str(payload.get("kind") or "comparison_matrix").strip() or "comparison_matrix",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "source_file": self.source_file,
            "first_column": self.first_column,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class DeepDiveManifest:
    deep_dive_id: str
    title: str
    subtitle: str
    portfolio_id: str
    portfolio_signature: str
    generated_at: str
    source: str
    confidentiality: str
    funds: tuple[dict[str, str], ...]
    tables: tuple[DeepDiveTableSpec, ...]
    warnings: tuple[str, ...]
    package_dir: Path
    schema_version: int = DEEP_DIVE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, package_dir: Path) -> "DeepDiveManifest":
        tables = tuple(
            spec
            for spec in (DeepDiveTableSpec.from_dict(item) for item in payload.get("tables") or [])
            if spec.id and spec.source_file
        )
        funds = tuple(
            {
                "cnpj": str(item.get("cnpj") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "short_name": str(item.get("short_name") or item.get("name") or "").strip(),
            }
            for item in payload.get("funds") or []
            if isinstance(item, dict)
        )
        audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
        return cls(
            schema_version=int(payload.get("schema_version") or DEEP_DIVE_SCHEMA_VERSION),
            deep_dive_id=str(payload.get("deep_dive_id") or package_dir.name).strip(),
            title=str(payload.get("title") or package_dir.name).strip(),
            subtitle=str(payload.get("subtitle") or "").strip(),
            portfolio_id=str(payload.get("portfolio_id") or "").strip(),
            portfolio_signature=str(payload.get("portfolio_signature") or "").strip(),
            generated_at=str(payload.get("generated_at") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            confidentiality=str(payload.get("confidentiality") or "Uso interno").strip(),
            funds=funds,
            tables=tables,
            warnings=tuple(str(item).strip() for item in (audit.get("warnings") or payload.get("warnings") or []) if str(item).strip()),
            package_dir=package_dir,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "deep_dive_id": self.deep_dive_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "portfolio_id": self.portfolio_id,
            "portfolio_signature": self.portfolio_signature,
            "generated_at": self.generated_at,
            "source": self.source,
            "confidentiality": self.confidentiality,
            "funds": list(self.funds),
            "tables": [table.to_dict() for table in self.tables],
            "audit": {"warnings": list(self.warnings)},
        }


@dataclass(frozen=True)
class LoadedDeepDiveTable:
    spec: DeepDiveTableSpec
    rows: int
    columns: tuple[str, ...]
