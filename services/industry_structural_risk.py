"""Single structural-risk dataframe shared by the deck, workbook and explorer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


MVP_SLIDE_OVERRIDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "industry_study"
    / "structural_mvp_slide_overrides.csv"
)
FINANCEIRO_AGRO_RISK_REVIEW_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "industry_study"
    / "carteira_101_financeiro_agro_risk_review.csv"
)
MVP_SLIDE_CATEGORIES = frozenset(
    {
        "Financeiro",
        "Adquirência",
        "Agro / Revenda",
        "Risco Corporativo",
        "Consignado INSS e FGTS",
        "Factoring",
    }
)
FINANCEIRO_AGRO_RISK_REVIEW_COLUMNS = (
    "cnpj",
    "categoria_atual",
    "categoria_proposta",
    "categoria_candidata",
    "subtipo_risco",
    "status",
    "applied_flag",
    "middle_market_status",
    "racional",
    "evidencia",
)
FINANCEIRO_AGRO_RISK_REVIEW_CURRENT_CATEGORIES = frozenset(
    {"Financeiro", "Agro / Revenda"}
)
FINANCEIRO_AGRO_RISK_REVIEW_STATUSES = frozenset(
    {
        "MANTER_ALTA",
        "MANTER_ASTERISCO",
        "APLICAR_ALTA",
        "PENDENTE_FONTE_PRIMARIA",
        "PENDENTE_DOCUMENTAL",
        "PENDENTE_TIPO_LASTRO",
    }
)
FINANCEIRO_AGRO_RISK_OUTPUT_COLUMNS = (
    "categoria_risco_atual",
    "categoria_risco_proposta",
    "subtipo_risco_diagnosticado",
    "reclassificacao_proposta_flag",
    "status_avaliacao_reclassificacao",
    "fundamento_avaliacao_reclassificacao",
    "fonte_avaliacao_reclassificacao",
    "middle_market_status",
    "middle_market_evidencia",
    "middle_market_porte_documentado_flag",
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


def _load_mvp_slide_overrides(
    path: Path = MVP_SLIDE_OVERRIDE_PATH,
) -> pd.DataFrame:
    """Load the auditable, slide-only taxonomy overlay.

    The analytical and official taxonomies remain unchanged.  This overlay only
    selects which of the six MVP slides receives a Carteira I vehicle.
    """

    columns = ["cnpj", "categoria_mvp", "fonte", "motivo"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    overrides = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(columns).difference(overrides.columns)
    if missing:
        raise ValueError(
            "overlay MVP sem colunas obrigatórias: " + ", ".join(sorted(missing))
        )
    overrides = overrides.loc[:, columns].copy()
    overrides["cnpj"] = overrides["cnpj"].str.replace(r"\D", "", regex=True)
    if not overrides["cnpj"].str.fullmatch(r"\d{14}").all():
        raise ValueError("overlay MVP contém CNPJ inválido")
    if overrides["cnpj"].duplicated().any():
        raise ValueError("overlay MVP contém CNPJ duplicado")
    invalid = sorted(set(overrides["categoria_mvp"]).difference(MVP_SLIDE_CATEGORIES))
    if invalid:
        raise ValueError("overlay MVP contém categoria inválida: " + ", ".join(invalid))
    if overrides[["fonte", "motivo"]].apply(lambda column: column.str.strip().eq("")).any().any():
        raise ValueError("overlay MVP exige fonte e motivo para toda decisão")
    return overrides


def _validate_financeiro_agro_risk_review(
    review: pd.DataFrame,
    *,
    expected_rows: int | None = None,
) -> pd.DataFrame:
    """Validate the explicit per-CNPJ review without deriving missing facts.

    ``categoria_candidata`` is deliberately informational.  A candidate never
    changes the proposed category unless ``applied_flag`` is ``SIM``.
    """

    missing = set(FINANCEIRO_AGRO_RISK_REVIEW_COLUMNS).difference(review.columns)
    if missing:
        raise ValueError(
            "ledger Financeiro/Agro sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )
    validated = review.loc[:, FINANCEIRO_AGRO_RISK_REVIEW_COLUMNS].copy()
    for column in FINANCEIRO_AGRO_RISK_REVIEW_COLUMNS:
        validated[column] = validated[column].fillna("").astype(str).str.strip()
    validated["cnpj"] = validated["cnpj"].str.replace(r"\D", "", regex=True)
    if not validated["cnpj"].str.fullmatch(r"\d{14}").all():
        raise ValueError("ledger Financeiro/Agro contém CNPJ inválido")
    if validated["cnpj"].duplicated().any():
        raise ValueError("ledger Financeiro/Agro contém CNPJ duplicado")
    if expected_rows is not None and len(validated) != expected_rows:
        raise ValueError(
            "ledger Financeiro/Agro deve conter "
            f"{expected_rows} CNPJs; contém {len(validated)}"
        )

    invalid_current = sorted(
        set(validated["categoria_atual"]).difference(
            FINANCEIRO_AGRO_RISK_REVIEW_CURRENT_CATEGORIES
        )
    )
    if invalid_current:
        raise ValueError(
            "ledger Financeiro/Agro contém categoria atual inválida: "
            + ", ".join(invalid_current)
        )
    invalid_proposed = sorted(
        set(validated["categoria_proposta"]).difference(MVP_SLIDE_CATEGORIES)
    )
    if invalid_proposed:
        raise ValueError(
            "ledger Financeiro/Agro contém categoria proposta inválida: "
            + ", ".join(invalid_proposed)
        )
    invalid_status = sorted(
        set(validated["status"]).difference(
            FINANCEIRO_AGRO_RISK_REVIEW_STATUSES
        )
    )
    if invalid_status:
        raise ValueError(
            "ledger Financeiro/Agro contém status inválido: "
            + ", ".join(invalid_status)
        )
    invalid_applied = sorted(
        set(validated["applied_flag"]).difference({"SIM", "NAO"})
    )
    if invalid_applied:
        raise ValueError(
            "ledger Financeiro/Agro contém applied_flag inválido: "
            + ", ".join(invalid_applied)
        )
    invalid_middle_market = sorted(
        set(validated["middle_market_status"]).difference(
            {"Não", "Candidato", "Pendente"}
        )
    )
    if invalid_middle_market:
        raise ValueError(
            "ledger Financeiro/Agro contém middle_market_status inválido: "
            + ", ".join(invalid_middle_market)
        )

    required_text = (
        "categoria_atual",
        "categoria_proposta",
        "subtipo_risco",
        "status",
        "applied_flag",
        "middle_market_status",
        "racional",
        "evidencia",
    )
    blank_required = [
        column
        for column in required_text
        if validated[column].eq("").any()
    ]
    if blank_required:
        raise ValueError(
            "ledger Financeiro/Agro contém campos obrigatórios vazios: "
            + ", ".join(blank_required)
        )

    applied = validated["applied_flag"].eq("SIM")
    if not validated.loc[applied, "status"].eq("APLICAR_ALTA").all():
        raise ValueError(
            "ledger Financeiro/Agro exige status APLICAR_ALTA quando "
            "applied_flag=SIM"
        )
    if validated.loc[applied, "categoria_atual"].eq(
        validated.loc[applied, "categoria_proposta"]
    ).any():
        raise ValueError(
            "ledger Financeiro/Agro exige mudança de categoria quando "
            "applied_flag=SIM"
        )
    pending_or_maintained = ~applied
    if not validated.loc[pending_or_maintained, "categoria_atual"].eq(
        validated.loc[pending_or_maintained, "categoria_proposta"]
    ).all():
        raise ValueError(
            "ledger Financeiro/Agro mantém categoria atual quando "
            "applied_flag=NAO"
        )
    return validated.reset_index(drop=True)


def _load_financeiro_agro_risk_review(
    path: Path = FINANCEIRO_AGRO_RISK_REVIEW_PATH,
) -> pd.DataFrame:
    """Load the 72-case, semicolon-delimited documentary review ledger."""

    if not path.exists():
        raise FileNotFoundError(f"ledger Financeiro/Agro não localizado: {path}")
    review = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
    return _validate_financeiro_agro_risk_review(review, expected_rows=72)


def _apply_financeiro_agro_risk_review(
    rows: pd.DataFrame,
    review: pd.DataFrame,
) -> pd.DataFrame:
    """Attach reviewed fields and apply only explicitly approved categories."""

    output = rows.copy()
    if output.empty:
        for column in FINANCEIRO_AGRO_RISK_OUTPUT_COLUMNS:
            if column not in output.columns:
                output[column] = pd.Series(dtype="object")
        return output
    if "cnpj" not in output.columns:
        raise KeyError("base estrutural sem coluna cnpj")
    if output["cnpj"].astype(str).duplicated().any():
        raise ValueError("base estrutural contém CNPJ duplicado")

    validated = _validate_financeiro_agro_risk_review(review)
    current_category = output.get(
        "mvp_slide_categoria", pd.Series("N/D", index=output.index)
    ).fillna("N/D").astype(str)
    output["categoria_risco_atual"] = current_category
    output["categoria_risco_proposta"] = current_category
    output["subtipo_risco_diagnosticado"] = "N/D"
    output["reclassificacao_proposta_flag"] = False
    output["status_avaliacao_reclassificacao"] = "fora da revisão Financeiro/Agro"
    output["fundamento_avaliacao_reclassificacao"] = "N/D"
    output["fonte_avaliacao_reclassificacao"] = "N/D"
    output["middle_market_status"] = "N/D"
    output["middle_market_evidencia"] = "N/D"
    output["middle_market_porte_documentado_flag"] = pd.NA

    indexed_review = validated.set_index("cnpj")
    normalized_cnpj = output["cnpj"].astype(str).str.replace(r"\D", "", regex=True)
    matched = normalized_cnpj.isin(indexed_review.index)
    for row_index in output.index[matched]:
        decision = indexed_review.loc[normalized_cnpj.loc[row_index]]
        applied = decision["applied_flag"] == "SIM"
        output.at[row_index, "categoria_risco_atual"] = decision["categoria_atual"]
        output.at[row_index, "categoria_risco_proposta"] = decision[
            "categoria_proposta"
        ]
        output.at[row_index, "subtipo_risco_diagnosticado"] = decision[
            "subtipo_risco"
        ]
        output.at[row_index, "reclassificacao_proposta_flag"] = applied
        output.at[row_index, "status_avaliacao_reclassificacao"] = decision[
            "status"
        ]
        output.at[row_index, "fundamento_avaliacao_reclassificacao"] = decision[
            "racional"
        ]
        output.at[row_index, "fonte_avaliacao_reclassificacao"] = decision[
            "evidencia"
        ]
        output.at[row_index, "middle_market_status"] = decision[
            "middle_market_status"
        ]
        output.at[row_index, "middle_market_evidencia"] = decision["evidencia"]
        output.at[row_index, "middle_market_porte_documentado_flag"] = (
            False if decision["middle_market_status"] == "Não" else pd.NA
        )
        output.at[row_index, "mvp_slide_categoria_original"] = decision[
            "categoria_atual"
        ]
        output.at[row_index, "mvp_slide_categoria"] = decision[
            "categoria_proposta" if applied else "categoria_atual"
        ]
        if applied:
            output.at[row_index, "mvp_slide_categoria_override_flag"] = True
            output.at[row_index, "mvp_slide_categoria_fonte"] = decision[
                "evidencia"
            ]
            output.at[row_index, "mvp_slide_categoria_motivo"] = decision[
                "racional"
            ]
    return output


def build_portfolio_structural_risk(
    *,
    portfolio: PortfolioCurationResult,
    comparison: PortfolioFlagshipComparisonResult,
    config: StructuralRiskConfig | None = None,
    risk_review: pd.DataFrame | None = None,
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
                "N/D",
            ),
            "minimo_estrutural_natureza": nature,
            "minimo_estrutural_texto": np.where(
                support.notna(),
                detail.get("suporte_estrutural_minimo_texto", "N/D"),
                "N/D",
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

    mvp_category = assets["categoria"].replace(
        {
            "Consignado INSS": "Consignado INSS e FGTS",
            "Consignado FGTS": "Consignado INSS e FGTS",
        }
    )
    assets["mvp_slide_categoria"] = mvp_category.where(
        mvp_category.isin(MVP_SLIDE_CATEGORIES), "N/D"
    )
    assets["mvp_slide_categoria_original"] = assets["mvp_slide_categoria"]
    assets["mvp_slide_categoria_override_flag"] = False
    assets["mvp_slide_categoria_fonte"] = "N/D"
    assets["mvp_slide_categoria_motivo"] = "N/D"
    overrides = _load_mvp_slide_overrides().set_index("cnpj")
    override_category = assets["cnpj"].map(overrides["categoria_mvp"])
    override_mask = override_category.notna()
    assets.loc[override_mask, "mvp_slide_categoria"] = override_category[override_mask]
    assets.loc[override_mask, "mvp_slide_categoria_override_flag"] = True
    assets.loc[override_mask, "mvp_slide_categoria_fonte"] = assets.loc[
        override_mask, "cnpj"
    ].map(overrides["fonte"])
    assets.loc[override_mask, "mvp_slide_categoria_motivo"] = assets.loc[
        override_mask, "cnpj"
    ].map(overrides["motivo"])
    if risk_review is None:
        risk_review = _load_financeiro_agro_risk_review()
    assets = _apply_financeiro_agro_risk_review(assets, risk_review)
    current_for_band = _numeric(assets, "sub_pl_atual")
    assets["mvp_faixa_sub_atual"] = pd.cut(
        current_for_band,
        bins=[-np.inf, 0.10, 0.15, 0.20, 0.35, 0.60, np.inf],
        labels=["< 10%", "10%–15%", "15%–20%", "20%–35%", "35%–60%", "≥ 60%"],
        right=False,
    ).astype("object")
    assets["mvp_elegivel_flag"] = (
        assets["mvp_slide_categoria"].ne("N/D")
        & current_for_band.notna()
        & _numeric(assets, "sub_jr_min_regulamento").notna()
        & _numeric(assets, "pl_atual").gt(0)
    )
    mvp_floor = _numeric(assets, "sub_jr_min_regulamento")
    mvp_distance = current_for_band - mvp_floor
    mvp_comparable = assets["comparacao_estrutural_completa_flag"].fillna(False).astype(bool)
    assets["mvp_situacao_piso"] = np.select(
        [
            current_for_band.isna() | mvp_floor.isna(),
            ~mvp_comparable,
            mvp_distance.lt(0),
            mvp_distance.lt(config.thin_headroom_pp),
        ],
        ["N/D", "incomparável", "abaixo do piso", "até 2 p.p. acima"],
        default="acima do piso",
    )

    taxonomy_rows: list[dict[str, object]] = []
    for order, (_, group_name, _, _) in enumerate(PORTFOLIO_FLAGSHIP_GROUPS, start=1):
        group = assets[assets["categoria"].eq(group_name)]
        peer = benchmark.loc[group_name]
        pl = _numeric(group, "pl_atual")
        current = _numeric(group, "sub_pl_atual")
        group_structural = _numeric(group, "suporte_total_min_documental")
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
    structural_count = int(support.notna().sum())
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
        "mvp_cnpjs_elegiveis": int(assets["mvp_elegivel_flag"].sum()),
        "mvp_cnpjs_com_override_editorial": int(
            assets["mvp_slide_categoria_override_flag"].sum()
        ),
        "mvp_categorias": len(MVP_SLIDE_CATEGORIES),
        "risk_review_cnpjs": int(
            assets["status_avaliacao_reclassificacao"].ne(
                "fora da revisão Financeiro/Agro"
            ).sum()
        ),
        "risk_review_reclassificacoes_aplicadas": int(
            assets["reclassificacao_proposta_flag"].sum()
        ),
        "mvp_nota": "O MVP exibe somente CNPJs com Sub/PL atual, piso documental e PL do veículo; pisos não júnior aparecem com asterisco e estruturas não equivalentes recebem sinal neutro.",
        "fonte": portfolio.summary.get("fonte"),
    }
    return PortfolioStructuralRiskResult(
        assets=assets.sort_values("ordem").reset_index(drop=True),
        taxonomy=taxonomy,
        watchlist=watchlist.reset_index(drop=True),
        summary=summary,
    )
