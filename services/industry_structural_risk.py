"""Single structural-risk dataframe shared by the deck, workbook and explorer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from services.industry_flagship_curation import (
    PORTFOLIO_FLAGSHIP_GROUPS,
    PortfolioCurationResult,
    PortfolioFlagshipComparisonResult,
    _comparison_group_from_portfolio,
)
from services.structural_risk import (
    BAND_BREACH,
    BAND_THIN,
    StructuralRiskConfig,
    enrich_assets,
)


@dataclass(frozen=True)
class PortfolioStructuralRiskResult:
    assets: pd.DataFrame
    taxonomy: pd.DataFrame
    watchlist: pd.DataFrame
    summary: dict[str, object]


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column), errors="coerce")


def _weighted(values: pd.Series, weights: pd.Series) -> float | None:
    mask = values.notna() & weights.notna() & weights.gt(0)
    if not mask.any():
        return None
    return float(np.average(values[mask], weights=weights[mask]))


def build_portfolio_structural_risk(
    *,
    portfolio: PortfolioCurationResult,
    comparison: PortfolioFlagshipComparisonResult,
    config: StructuralRiskConfig | None = None,
) -> PortfolioStructuralRiskResult:
    """Materialize one auditable structural dataset for every output channel."""

    config = config or StructuralRiskConfig()
    detail = portfolio.detail.copy()
    detail["taxonomia_estrutural"] = detail.apply(
        _comparison_group_from_portfolio, axis=1
    )
    benchmark = comparison.detail.set_index("tipo_comparacao")

    junior = _numeric(detail, "subordinacao_minima_junior_pct") / 100.0
    support = _numeric(detail, "suporte_estrutural_minimo_pct") / 100.0
    structural_floor = support.where(support.notna(), junior)
    comparable = detail.get(
        "comparabilidade_tranche_flag", pd.Series("false", index=detail.index)
    ).astype(str).str.lower().eq("true")
    nature = detail.get(
        "subordinacao_minima_natureza", pd.Series("", index=detail.index)
    ).astype(str)
    exception = nature.ne("junior_pl")

    assets = pd.DataFrame(
        {
            "ordem": detail["ordem"],
            "ativo": detail["denominacao"],
            "cnpj": detail["cnpj_fundo"],
            "cnpj_formatado": detail["cnpj_fundo_formatado"],
            "categoria": detail["taxonomia_estrutural"],
            "tipo_exibicao": detail["tipo_exibicao"],
            "foco_exibicao": detail["foco_exibicao"],
            "sub_pl_atual": _numeric(detail, "subordinacao_atual_pct"),
            "sub_jr_min_regulamento": structural_floor,
            "sub_jr_min_documental": junior,
            "suporte_total_min_documental": support,
            "minimo_estrutural_display": np.where(
                support.notna(),
                detail.get("suporte_estrutural_minimo_display", "N/D"),
                detail.get("subordinacao_minima_junior_display", "N/D"),
            ),
            "minimo_estrutural_natureza": nature,
            "minimo_estrutural_texto": np.where(
                support.notna(),
                detail.get("suporte_estrutural_minimo_texto", "N/D"),
                detail.get("subordinacao_minima_texto", "N/D"),
            ),
            "minimo_estrutural_formula": detail.get(
                "subordinacao_minima_formula", "N/D"
            ),
            "excecao_asterisco_flag": exception,
            "pl_atual": _numeric(detail, "pl_atual_brl"),
            "data_ref": portfolio.summary.get("competencia"),
            "carteira_flag": "nossa",
            "comparacao_estrutural_completa_flag": comparable,
            "comparacao_estrutural_motivo": detail.get(
                "comparabilidade_tranche_motivo", "N/D"
            ),
            "fonte_documental": detail.get("subordinacao_minima_fonte", "N/D"),
            "documento_id_regulamento": detail.get(
                "documento_id_regulamento", "N/D"
            ),
            "pagina_clausula": detail.get("pagina_clausula", "N/D"),
            "status_curadoria_documental": detail.get(
                "status_curadoria_documental", "N/D"
            ),
        }
    )
    assets["mercado_categoria_mediana_sub"] = assets["categoria"].map(
        benchmark["flagship_subordinacao_mediana_pct"]
    )
    assets["mercado_categoria_media_ponderada_pl_sub"] = np.nan
    assets["mercado_categoria_q25_sub"] = np.nan
    assets["mercado_categoria_q75_sub"] = np.nan
    assets["n_comparaveis_categoria"] = assets["categoria"].map(
        benchmark["flagship_cnpjs_com_subordinacao"]
    )
    assets["comparacao_mercado_flag"] = assets["categoria"].ne("N/D")
    assets = enrich_assets(assets, config=config)

    taxonomy_rows: list[dict[str, object]] = []
    for order, (_, group_name, _, _) in enumerate(PORTFOLIO_FLAGSHIP_GROUPS, start=1):
        group = assets[assets["categoria"].eq(group_name)]
        peer = benchmark.loc[group_name]
        pl = _numeric(group, "pl_atual")
        current = _numeric(group, "sub_pl_atual")
        group_structural = _numeric(group, "sub_jr_min_regulamento")
        junior_group = _numeric(group, "sub_jr_min_documental")
        market_median = pd.to_numeric(
            pd.Series([peer.get("flagship_subordinacao_mediana_pct")]),
            errors="coerce",
        ).iloc[0]
        peer_count = int(peer["flagship_cnpjs_com_subordinacao"])
        current_median = current.median() if current.notna().any() else np.nan
        portfolio_count = int(len(group))
        if portfolio_count == 0:
            presence = "Ausente"
        elif pl.notna().sum() == 0:
            presence = "CNPJ no escopo; PL N/D"
        else:
            presence = "Presente"
        delta = (
            current_median - market_median
            if peer_count >= config.min_comparables
            and pd.notna(current_median)
            and pd.notna(market_median)
            else np.nan
        )
        if pd.isna(delta):
            market_read = "N/D"
        elif delta > config.market_in_line_pp:
            market_read = "↑ acima dos pares"
        elif delta < -config.market_in_line_pp:
            market_read = "↓ abaixo dos pares"
        else:
            market_read = "→ em linha"
        taxonomy_rows.append(
            {
                "ordem": order,
                "taxonomia": group_name,
                "presenca_carteira": presence,
                "carteira_cnpjs": portfolio_count,
                "carteira_cnpjs_com_pl": int(pl.notna().sum()),
                "carteira_pl_brl": float(pl.sum(min_count=1)) if pl.notna().any() else None,
                "carteira_sub_atual_mediana": float(current_median) if pd.notna(current_median) else None,
                "carteira_sub_atual_ponderada": _weighted(current, pl),
                "carteira_minimo_junior_cnpjs": int(junior_group.notna().sum()),
                "carteira_minimo_estrutural_cnpjs": int(group_structural.notna().sum()),
                "carteira_folga_comparavel_cnpjs": int(group["folga_pp"].notna().sum()),
                "carteira_minimo_estrutural_mediana": float(group_structural.median()) if group_structural.notna().any() else None,
                "flagship_cnpjs": int(peer["flagship_cnpjs"]),
                "flagship_cnpjs_com_subordinacao": peer_count,
                "flagship_pl_brl": peer["flagship_pl_brl"],
                "flagship_sub_atual_mediana": float(market_median) if pd.notna(market_median) else None,
                "delta_sub_atual_vs_flagship": float(delta) if pd.notna(delta) else None,
                "posicao_vs_mercado": market_read,
            }
        )
    taxonomy = pd.DataFrame(taxonomy_rows)

    severity = {BAND_BREACH: 0, BAND_THIN: 1}
    measurable = assets[assets["folga_pp"].notna()].copy()
    measurable["ordem_risco"] = measurable["situacao_regulatoria"].map(severity).fillna(2)
    watchlist = measurable.sort_values(
        ["ordem_risco", "perda_ate_gatilho", "pl_atual"],
        ascending=[True, True, False],
        kind="stable",
    ).head(12).drop(columns=["ordem_risco"])

    junior_count = int(junior.notna().sum())
    structural_count = int(structural_floor.notna().sum())
    comparable_count = int(assets["folga_pp"].notna().sum())
    summary = {
        "carteira": "Carteira 1",
        "competencia": portfolio.summary.get("competencia"),
        "cnpjs": int(len(assets)),
        "cnpjs_com_minimo_junior": junior_count,
        "cobertura_minimo_junior_pct": junior_count / len(assets),
        "cnpjs_com_minimo_estrutural": structural_count,
        "cobertura_minimo_estrutural_pct": structural_count / len(assets),
        "cnpjs_com_folga_comparavel": comparable_count,
        "cnpjs_sem_indice": int(nature.eq("sem_indice").sum()),
        "cnpjs_fora_perimetro": int(nature.eq("fora_perimetro").sum()),
        "asterisco": "* suporte total, combinado, calculado ou ajustado; a natureza está indicada por linha.",
        "nota_pl": "PL é o patrimônio do veículo; o valor encarteirado por ativo não está disponível nesta base.",
        "fonte": portfolio.summary.get("fonte"),
    }
    return PortfolioStructuralRiskResult(
        assets=assets.sort_values("ordem").reset_index(drop=True),
        taxonomy=taxonomy,
        watchlist=watchlist.reset_index(drop=True),
        summary=summary,
    )
