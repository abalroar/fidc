from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Premissas:
    volume: float
    tx_cessao_am: float
    tx_cessao_cdi_aa: Optional[float]
    custo_adm_aa: float
    custo_min: float
    inadimplencia: float
    proporcao_senior: float
    taxa_senior: float
    proporcao_mezz: float
    taxa_mezz: float

    @property
    def proporcao_sub_jr(self) -> float:
        return 1.0 - self.proporcao_senior - self.proporcao_mezz


@dataclass(frozen=True)
class PeriodResult:
    indice: int
    data: datetime
    dc: int
    du: int
    delta_dc: int
    delta_du: int
    pre_di: Optional[float]
    taxa_senior: Optional[float]
    fra_senior: Optional[float]
    taxa_mezz: Optional[float]
    fra_mezz: Optional[float]
    carteira: float
    fluxo_carteira: float
    pl_fidc: float
    custos_adm: float
    inadimplencia_despesa: float
    principal_senior: float
    juros_senior: float
    pmt_senior: float
    vp_pmt_senior: float
    pl_senior: float
    fluxo_remanescente: float
    principal_mezz: float
    juros_mezz: float
    pmt_mezz: float
    pl_mezz: float
    fluxo_remanescente_mezz: float
    principal_sub_jr: float
    juros_sub_jr: float
    pmt_sub_jr: float
    pl_sub_jr: float
    subordinacao_pct: Optional[float]
    pl_sub_jr_modelo: Optional[float] = field(default=None)
    subordinacao_pct_modelo: Optional[float] = field(default=None)


@dataclass(frozen=True)
class ModelKpis:
    xirr_senior: Optional[float]
    xirr_mezz: Optional[float]
    xirr_sub_jr: Optional[float]
    taxa_retorno_sub_jr_cdi: Optional[float]
    duration_senior_anos: Optional[float]
    pre_di_duration: Optional[float]
