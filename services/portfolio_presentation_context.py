"""Presentation references copied from producer metadata; no financial rules."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PortfolioPresentationContext:
    name: str
    fund_count: int
    requested_window: str
    historical_window: str
    common_position: str
    latest_observed: str
    consulted_at: str
    source: str = "Informe Mensal · CVM/Fundos.NET"

    def reference_lines(self) -> tuple[str, ...]:
        return (
            f"Carteira: {self.name} ({self.fund_count} fundos)",
            f"Consulta solicitada: {self.requested_window}",
            f"Histórico selecionado: {self.historical_window}",
            f"Posição comum: {self.common_position}",
            f"Última competência observada: {self.latest_observed}",
            f"Fonte mensal: {self.source}",
            f"Consulta: {self.consulted_at}",
            "Fundos individuais usam sua própria competência; documentos conservam a data de leitura.",
        )


def build_portfolio_presentation_context(*, analysis, portfolio, period, generated_at=None):
    metadata = getattr(analysis.outputs, "metadata", {}) or {}
    bundle = analysis.aggregate_bundle
    common = getattr(getattr(bundle, "dashboard", None), "latest_competencia", "") or "N/D"
    coverage = getattr(bundle, "competence_coverage_df", None)
    latest = common
    if coverage is not None and not coverage.empty:
        latest = str(coverage.iloc[-1].get("competencia") or "N/D")
    elif common == "N/D":
        latest = str(metadata.get("latest_competencia") or "N/D")
    now = generated_at or datetime.now(ZoneInfo("America/Sao_Paulo"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    now = now.astimezone(ZoneInfo("America/Sao_Paulo"))
    return PortfolioPresentationContext(
        name=portfolio.name,
        fund_count=len(portfolio.funds),
        requested_window=period.label,
        historical_window=str(metadata.get("display_period_label") or metadata.get("period_label") or period.label),
        common_position=str(common),
        latest_observed=str(latest),
        consulted_at=now.strftime("%d/%m/%Y %H:%M BRT"),
    )
