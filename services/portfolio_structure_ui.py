from __future__ import annotations

from services.portfolio_store import PortfolioRecord
from services.dashboard_ui import indicator_help_html
from services.fidc_book import load_fidc_book_index
from functools import lru_cache
from typing import Any


# This is a UI rollout boundary, not a new portfolio or a calculation basket.
_PILOT_PORTFOLIO_ID = "7681d350f2994945ada0590b0e3703c2"
_PILOT_CNPJS = frozenset({
    "42085816000105", "42085830000109", "42102603000144", "44124617000194",
    "54218673000141", "54218941000125", "54219179000100", "54248022000102",
    "57609282000146", "60356171000180", "62393679000183",
})


def structure_pilot_enabled(portfolio: PortfolioRecord) -> bool:
    return (
        portfolio.id == _PILOT_PORTFOLIO_ID
        and len(portfolio.funds) == len(_PILOT_CNPJS)
        and {fund.cnpj for fund in portfolio.funds} == _PILOT_CNPJS
    )


@lru_cache(maxsize=1)
def _book_metrics() -> dict[str, Any]:
    return {metric.metric_id: metric for metric in load_fidc_book_index().metrics}


def structural_snapshot_help_html(label: str, dashboard: Any) -> str:
    """Read the same glossary and calculation memory used by the existing app."""
    components = {
        "Ativo total": ("Ativo total", "", "Ativos totais reportados na base da análise."),
        "DCs totais": ("Direitos creditórios totais", "", "Estoque de direitos creditórios na base canônica do painel."),
        "PL total": ("PL total", "pl", ""),
        "Vencidos": ("Inadimplência observada (IME) / DCs", "", "Saldo vencido na base canônica do painel."),
        "Cobertura de provisão": ("Cobertura de provisão / vencidos totais (linha RHS)", "cobertura_provisao", ""),
        "Subordinação reportada": ("Subordinação reportada (IME) — linha", "subordinacao_reportada", ""),
    }
    component, metric_id, definition = components[label]
    metric = _book_metrics().get(metric_id)
    aggregate = dashboard.fund_info.get("aggregation_scope") == "portfolio"
    if aggregate:
        component = {
            "Ativo total": "Ativo total agregado",
            "DCs totais": "Direitos creditórios totais agregados",
            "Subordinação reportada": "Subordinação reportada agregada",
        }.get(label, component)
    memory = getattr(dashboard, "executive_memory_df", None)
    row: dict[str, Any] = {}
    if memory is not None and "componente" in memory.columns:
        matches = memory.loc[memory["componente"].eq(component)]
        if not matches.empty:
            row = matches.iloc[0].to_dict()
    # The Vencidos card is the numerator only, whereas its memory row is a ratio.
    formula = row.get("numerador", "Saldo vencido canônico") if label == "Vencidos" else row.get("formula", metric.formula if metric is not None else "")
    if aggregate and not row:
        formula = {
            "PL total": "Soma do PL dos fundos na mesma competência comum.",
            "Vencidos": "Soma dos saldos vencidos canônicos dos fundos na mesma competência comum.",
            "Cobertura de provisão": "Soma das provisões / soma dos saldos vencidos × 100; exige saldo vencido positivo.",
        }.get(label, formula)
    source = row.get("fonte_efetiva") or row.get("fonte_cvm")
    source_text = f"Informe Mensal CVM/Fundos.NET · {source}" if source else "Informe Mensal CVM/Fundos.NET"
    unit = "%" if label in {"Cobertura de provisão", "Subordinação reportada"} else "R$"
    page = metric.page_ids[0] if metric is not None and metric.page_ids else "metricas-estruturais"
    items = (
        ("Definição", metric.summary if metric is not None else definition),
        ("Fórmula", formula),
        ("Fonte", source_text),
        ("Unidade", unit),
        ("Competência", dashboard.latest_competencia),
        ("Perímetro", dashboard.fund_info.get("nome_fundo") or dashboard.fund_info.get("nome_classe") or "Escopo identificado acima"),
        ("Ressalva", row.get("observacao", "")),
    )
    return indicator_help_html(label, items, glossary_page=page)
