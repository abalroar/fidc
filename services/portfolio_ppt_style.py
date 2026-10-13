"""Visual contract for the portfolio PowerPoint, expressed in points."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioPptStyle:
    width: float = 960
    height: float = 540
    margin: float = 30
    title_top: float = 17
    title_size: float = 25
    context_top: float = 61
    context_size: float = 12
    content_top: float = 105
    content_bottom: float = 478
    footer_top: float = 498
    footer_size: float = 9
    font: str = "Calibri"
    text: str = "24282E"
    muted: str = "626970"
    orange: str = "EC7000"
    grid: str = "E8EAED"
    white: str = "FFFFFF"
    good: str = "16713B"
    bad: str = "B32624"
    table_size: float = 11
    table_min_size: float = 10
    section_size: float = 13
    chart_size: float = 11
    chart_series_limit: int = 4
    month_columns: int = 13
    gap: float = 24
    line_width: float = 1.6

    @property
    def content_width(self) -> float:
        return self.width - self.margin * 2


DEFAULT_STYLE = PortfolioPptStyle()

# These keys identify series, rather than their position in a particular chart.
# Green and red belong to documented financial comparisons, never to series.
SERIES_COLORS = {
    "inadimplencia_pct": "EC7000", "over_1_pct": "EC7000",
    "over_30_pct": "24282E", "over_60_pct": "626970",
    "over_90_pct": "8B9199", "over_180_pct": "ACB1B7",
    "over_360_pct": "C4C8CD", "provisao_pct_direitos": "8B9199",
    "pdd_pct": "8B9199", "cobertura_pct": "626970",
    "cobertura_pdd_over90_pct": "626970", "pl": "24282E",
    "carteira_bruta_ex360": "EC7000", "duration_months": "626970",
    "npl_over30_ex360_pct": "EC7000", "npl_over90_ex360_pct": "24282E",
    "pdd_npl_over90_ex360_pct": "626970", "pl_total": "24282E",
    "carteira_ex360": "EC7000", "subordinacao_total_ex360_pct": "626970",
}

SNAPSHOT_SERIES_KEYS = {
    "PL total": "pl_total", "Carteira bruta ex-360": "carteira_ex360",
    "Subordinação ex-360": "subordinacao_total_ex360_pct",
    "NPL > 1d ex-360": "npl_over1_ex360_pct",
    "NPL > 90d ex-360": "npl_over90_ex360_pct",
    "Cobertura PDD / NPL > 90d": "pdd_npl_over90_ex360_pct",
    "Duration estimada": "duration_months",
    "Cobertura provisão / vencidos · IME": "cobertura_pct",
}


def series_color(key: str, style: PortfolioPptStyle = DEFAULT_STYLE) -> str:
    """Stable neutral shades for other series, including different share classes."""
    if key in SERIES_COLORS:
        return SERIES_COLORS[key]
    metric = key.rsplit(":", 1)[-1]
    if metric in SERIES_COLORS:
        return SERIES_COLORS[metric]
    shades = (style.text, style.muted, "8B9199", "ACB1B7")
    return shades[sum((index + 1) * ord(char) for index, char in enumerate(key)) % len(shades)]
