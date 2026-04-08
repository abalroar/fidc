from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FundoResolution:
    cnpj: str
    id_fundo: Optional[str]


@dataclass(frozen=True)
class DocumentoFundo:
    id: int
    categoria: str
    tipo: str
    especie: str
    data_referencia: Optional[str]
    data_entrega: Optional[str]
    nome_arquivo: Optional[str]
    raw: Dict[str, Any]

    @property
    def periodo_ordenacao(self) -> datetime:
        raw = self.data_referencia or self.data_entrega
        if raw:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed = datetime.strptime(raw[:19], fmt)
                    return datetime(parsed.year, parsed.month, 1)
                except ValueError:
                    continue
        return datetime(1900, 1, 1)

    @property
    def coluna_informe(self) -> str:
        base = self.data_referencia or self.data_entrega or f"DOC-{self.id}"
        return f"{base} | id={self.id}"
