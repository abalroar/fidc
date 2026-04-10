from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd


COMPETENCIA_COLUMN_RE = re.compile(r"^\d{2}/\d{4}$")


@dataclass(frozen=True)
class FundonetDashboardData:
    competencias: list[str]
    latest_competencia: str
    fund_info: dict[str, str]
    summary: dict[str, float | str | None]
    asset_history_df: pd.DataFrame
    composition_latest_df: pd.DataFrame
    segment_latest_df: pd.DataFrame
    liquidity_latest_df: pd.DataFrame
    maturity_latest_df: pd.DataFrame
    quota_pl_history_df: pd.DataFrame
    subordination_history_df: pd.DataFrame
    return_history_df: pd.DataFrame
    return_summary_df: pd.DataFrame
    event_history_df: pd.DataFrame
    default_history_df: pd.DataFrame
    default_buckets_latest_df: pd.DataFrame
    holder_latest_df: pd.DataFrame
    rate_negotiation_latest_df: pd.DataFrame
    tracking_latest_df: pd.DataFrame
    methodology_notes: list[str]


def build_dashboard_data(
    *,
    wide_csv_path: Path,
    listas_csv_path: Path,
    docs_csv_path: Path,
) -> FundonetDashboardData:
    wide_df = pd.read_csv(wide_csv_path, dtype=str, keep_default_na=False)
    listas_df = pd.read_csv(listas_csv_path, dtype=str, keep_default_na=False)
    docs_df = pd.read_csv(docs_csv_path, dtype=str, keep_default_na=False)

    competencias = _extract_competencias(wide_df)
    if not competencias:
        raise ValueError("O CSV wide não possui colunas de competência para montar o dashboard.")

    latest_competencia = competencias[-1]
    wide_lookup = wide_df.set_index("tag_path", drop=False)

    quota_pl_history_df = _build_quota_pl_history(
        wide_lookup=wide_lookup,
        listas_df=listas_df,
        competencias=competencias,
    )
    subordination_history_df = _build_subordination_history(quota_pl_history_df)
    return_history_df = _build_return_history(
        wide_lookup=wide_lookup,
        listas_df=listas_df,
        competencias=competencias,
    )
    return_summary_df = _build_return_summary(
        return_history_df=return_history_df,
        latest_competencia=latest_competencia,
    )
    event_history_df = _build_event_history(
        wide_lookup=wide_lookup,
        listas_df=listas_df,
        competencias=competencias,
    )
    asset_history_df = _build_asset_history(
        wide_lookup=wide_lookup,
        competencias=competencias,
    )
    default_history_df = _build_default_history(
        wide_lookup=wide_lookup,
        competencias=competencias,
    )

    composition_latest_df = _build_composition_latest_df(asset_history_df)
    segment_latest_df = _build_segment_latest_df(
        wide_lookup=wide_lookup,
        latest_competencia=latest_competencia,
    )
    liquidity_latest_df = _build_liquidity_latest_df(
        wide_lookup=wide_lookup,
        latest_competencia=latest_competencia,
    )
    maturity_latest_df = _build_maturity_latest_df(
        wide_lookup=wide_lookup,
        latest_competencia=latest_competencia,
    )
    default_buckets_latest_df = _build_default_buckets_latest_df(
        wide_lookup=wide_lookup,
        latest_competencia=latest_competencia,
    )
    holder_latest_df = _build_holder_latest_df(
        wide_lookup=wide_lookup,
        listas_df=listas_df,
        latest_competencia=latest_competencia,
    )
    rate_negotiation_latest_df = _build_rate_negotiation_latest_df(
        wide_lookup=wide_lookup,
        latest_competencia=latest_competencia,
    )
    fund_info = _build_fund_info(
        wide_lookup=wide_lookup,
        docs_df=docs_df,
        competencias=competencias,
        latest_competencia=latest_competencia,
    )
    summary = _build_summary(
        latest_competencia=latest_competencia,
        asset_history_df=asset_history_df,
        subordination_history_df=subordination_history_df,
        default_history_df=default_history_df,
        event_history_df=event_history_df,
    )
    tracking_latest_df = _build_tracking_latest_df(
        summary=summary,
        asset_history_df=asset_history_df,
        latest_competencia=latest_competencia,
    )

    methodology_notes = [
        "Alocação e composição da carteira usam os saldos reportados no IME e podem divergir da metodologia proprietária do administrador.",
        "Direitos creditórios priorizam o campo CVM DICRED/VL_DICRED e usam campos legados CRED_EXISTE apenas como fallback.",
        "Índice de subordinação é calculado como PL subordinado dividido pelo PL total das cotas reportadas.",
        "Indices de cobertura, rating, benchmark, custodiante e auditor nao sao derivados diretamente do IME e exigem fonte complementar.",
        "Fluxo de direitos creditórios usa aquisições e alienações reportadas no IME; o PDF de referência pode chamar esse bloco de liquidações.",
    ]

    return FundonetDashboardData(
        competencias=competencias,
        latest_competencia=latest_competencia,
        fund_info=fund_info,
        summary=summary,
        asset_history_df=asset_history_df,
        composition_latest_df=composition_latest_df,
        segment_latest_df=segment_latest_df,
        liquidity_latest_df=liquidity_latest_df,
        maturity_latest_df=maturity_latest_df,
        quota_pl_history_df=quota_pl_history_df,
        subordination_history_df=subordination_history_df,
        return_history_df=return_history_df,
        return_summary_df=return_summary_df,
        event_history_df=event_history_df,
        default_history_df=default_history_df,
        default_buckets_latest_df=default_buckets_latest_df,
        holder_latest_df=holder_latest_df,
        rate_negotiation_latest_df=rate_negotiation_latest_df,
        tracking_latest_df=tracking_latest_df,
        methodology_notes=methodology_notes,
    )


def _extract_competencias(wide_df: pd.DataFrame) -> list[str]:
    competencias = [column for column in wide_df.columns if COMPETENCIA_COLUMN_RE.fullmatch(str(column))]
    return sorted(competencias, key=_competencia_sort_key)


def _competencia_sort_key(label: str) -> tuple[int, int]:
    month, year = label.split("/")
    return int(year), int(month)


def _competencia_to_timestamp(label: str) -> pd.Timestamp:
    return pd.to_datetime(f"01/{label}", format="%d/%m/%Y")


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return str(value).strip() in {"", "nan", "None", "<NA>"}


def _display_value(value: object) -> str:
    return "" if _is_blank(value) else str(value).strip()


def _to_numeric(value: object) -> float | None:
    if _is_blank(value):
        return None
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def _get_wide_series(wide_lookup: pd.DataFrame, competencias: list[str], tag_path: str) -> pd.Series:
    if tag_path not in wide_lookup.index:
        return pd.Series([pd.NA] * len(competencias), index=competencias, dtype="object")
    row = wide_lookup.loc[tag_path]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return pd.Series([row.get(competencia, pd.NA) for competencia in competencias], index=competencias, dtype="object")


def _numeric_series(wide_lookup: pd.DataFrame, competencias: list[str], tag_path: str) -> pd.Series:
    raw_series = _get_wide_series(wide_lookup, competencias, tag_path)
    numeric = pd.to_numeric(raw_series, errors="coerce")
    numeric.index = competencias
    return numeric.fillna(0.0)


def _numeric_series_first_available(
    wide_lookup: pd.DataFrame,
    competencias: list[str],
    tag_paths: list[str],
) -> pd.Series:
    output = pd.Series([0.0] * len(competencias), index=competencias, dtype="float64")
    for tag_path in tag_paths:
        candidate = _numeric_series(wide_lookup, competencias, tag_path)
        output = output.where(output > 0, candidate)
    return output.fillna(0.0)


def _direitos_creditorios_series(wide_lookup: pd.DataFrame, competencias: list[str]) -> pd.Series:
    primary = _numeric_series_first_available(
        wide_lookup,
        competencias,
        [
            "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED",
            "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_SOM_CART_SEGMT",
        ],
    )
    legacy = (
        _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_VENC_ADIMPL")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_VENC_INAD")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_EXISTE_INAD")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_EXISTE_VENC_INAD")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_EXISTE_INAD")
    )
    return primary.where(primary > 0, legacy).fillna(0.0)


def _build_fund_info(
    *,
    wide_lookup: pd.DataFrame,
    docs_df: pd.DataFrame,
    competencias: list[str],
    latest_competencia: str,
) -> dict[str, str]:
    docs_ok_df = docs_df
    if "processamento" in docs_df.columns:
        docs_ok_df = docs_df[docs_df["processamento"] == "ok"].copy()
        if docs_ok_df.empty:
            docs_ok_df = docs_df.copy()
    docs_ok_df["competencia_ord"] = docs_ok_df["competencia"].map(_competencia_to_timestamp)
    latest_doc = docs_ok_df.sort_values("competencia_ord").iloc[-1]

    def wide_value(tag_path: str) -> str:
        return _display_value(_get_wide_series(wide_lookup, [latest_competencia], tag_path).iloc[0])

    return {
        "nome_fundo": _display_value(latest_doc.get("nome_fundo", "")),
        "fundo_ou_classe": _display_value(latest_doc.get("fundo_ou_classe", "")),
        "cnpj_fundo": wide_value("DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO"),
        "cnpj_classe": wide_value("DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE"),
        "cnpj_administrador": wide_value("DOC_ARQ/CAB_INFORM/NR_CNPJ_ADM"),
        "nome_classe": wide_value("DOC_ARQ/CAB_INFORM/NM_CLASSE"),
        "condominio": wide_value("DOC_ARQ/CAB_INFORM/TP_CONDOMINIO"),
        "classe_unica": wide_value("DOC_ARQ/CAB_INFORM/CLASS_UNICA"),
        "periodo_analisado": f"{competencias[0]} a {latest_competencia}",
        "ultima_competencia": latest_competencia,
        "ultima_entrega": _display_value(latest_doc.get("data_entrega", "")),
    }


def _build_summary(
    *,
    latest_competencia: str,
    asset_history_df: pd.DataFrame,
    subordination_history_df: pd.DataFrame,
    default_history_df: pd.DataFrame,
    event_history_df: pd.DataFrame,
) -> dict[str, float | str | None]:
    asset_row = _latest_row(asset_history_df, latest_competencia)
    subordination_row = _latest_row(subordination_history_df, latest_competencia)
    default_row = _latest_row(default_history_df, latest_competencia)
    latest_events_df = event_history_df[event_history_df["competencia"] == latest_competencia].copy()
    direitos_creditorios = _float_or_none(asset_row.get("direitos_creditorios"))
    carteira = _float_or_none(asset_row.get("carteira"))
    outros_ativos = _float_or_none(asset_row.get("outros_ativos_carteira"))
    alocacao_pct = _float_or_none(asset_row.get("alocacao_pct"))
    if carteira and carteira > 0 and (direitos_creditorios is None or direitos_creditorios <= 0):
        direitos_creditorios = None
        outros_ativos = None
        alocacao_pct = None

    return {
        "pl_total": _float_or_none(subordination_row.get("pl_total")),
        "pl_senior": _float_or_none(subordination_row.get("pl_senior")),
        "pl_subordinada": _float_or_none(subordination_row.get("pl_subordinada")),
        "ativos_totais": _float_or_none(asset_row.get("ativos_totais")),
        "carteira": carteira,
        "direitos_creditorios": direitos_creditorios,
        "outros_ativos_carteira": outros_ativos,
        "alocacao_pct": alocacao_pct,
        "subordinacao_pct": _float_or_none(subordination_row.get("subordinacao_pct")),
        "inadimplencia_total": _float_or_none(default_row.get("inadimplencia_total")),
        "inadimplencia_pct": _float_or_none(default_row.get("inadimplencia_pct")),
        "provisao_total": _float_or_none(default_row.get("provisao_total")),
        "emissao_mes": _sum_event_metric(latest_events_df, "emissao", "valor_total"),
        "resgate_mes": _sum_event_metric(latest_events_df, "resgate", "valor_total"),
        "amortizacao_mes": _sum_event_metric(latest_events_df, "amortizacao", "valor_total"),
    }


def _latest_row(df: pd.DataFrame, competencia: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="object")
    matches = df[df["competencia"] == competencia]
    if matches.empty:
        return df.sort_values("competencia_dt").iloc[-1]
    return matches.sort_values("competencia_dt").iloc[-1]


def _float_or_none(value: object) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_event_metric(event_df: pd.DataFrame, event_type: str, field: str) -> float:
    if event_df.empty or field not in event_df.columns:
        return 0.0
    subset = event_df[event_df["event_type"] == event_type]
    if subset.empty:
        return 0.0
    return float(pd.to_numeric(subset[field], errors="coerce").fillna(0.0).sum())


def _build_asset_history(
    *,
    wide_lookup: pd.DataFrame,
    competencias: list[str],
) -> pd.DataFrame:
    ativos_totais = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_SOM_APLIC_ATIVO",
    )
    carteira = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_CARTEIRA",
    )
    liquidez_total = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ",
    )
    direitos_creditorios = _direitos_creditorios_series(wide_lookup, competencias)
    disponibilidades = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB",
    )
    valores_mobiliarios = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VALORES_MOB/VL_SOM_VALORES_MOB",
    )
    titulos_publicos = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_TITPUB_FED",
    )
    outros_ativos_reportados = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/OUTROS_ATIVOS/VL_SOM_OUTROS_ATIVOS",
    )
    aquisicoes = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/NEGOC_DICRED_MES/AQUISICOES/VL_DICRED_AQUIS",
    )
    alienacoes = _numeric_series(
        wide_lookup,
        competencias,
        "DOC_ARQ/LISTA_INFORM/NEGOC_DICRED_MES/DICRED_MES_ALIEN/VL_DICRED_ALIEN",
    )

    df = pd.DataFrame(
        {
            "competencia": competencias,
            "competencia_dt": [_competencia_to_timestamp(competencia) for competencia in competencias],
            "ativos_totais": ativos_totais.values,
            "carteira": carteira.values,
            "direitos_creditorios": direitos_creditorios.values,
            "disponibilidades": disponibilidades.values,
            "valores_mobiliarios": valores_mobiliarios.values,
            "titulos_publicos": titulos_publicos.values,
            "outros_ativos_reportados": outros_ativos_reportados.values,
            "liquidez_total": liquidez_total.values,
            "aquisicoes": aquisicoes.values,
            "alienacoes": alienacoes.values,
        }
    )
    df["outros_ativos_carteira"] = (df["carteira"] - df["direitos_creditorios"]).clip(lower=0.0)
    df["alocacao_pct"] = (df["direitos_creditorios"] / df["carteira"]).where(df["carteira"] > 0).mul(100.0)
    return df


def _build_composition_latest_df(asset_history_df: pd.DataFrame) -> pd.DataFrame:
    eligible_rows = asset_history_df[
        (asset_history_df["carteira"] > 0) & (asset_history_df["direitos_creditorios"] > 0)
    ].copy()
    if eligible_rows.empty:
        latest_row = asset_history_df.sort_values("competencia_dt").iloc[-1]
    else:
        latest_row = eligible_rows.sort_values("competencia_dt").iloc[-1]
    rows = [
        ("Direitos creditórios", latest_row.get("direitos_creditorios")),
        ("Valores mobiliários", latest_row.get("valores_mobiliarios")),
        ("Títulos públicos federais", latest_row.get("titulos_publicos")),
        ("Outros ativos", latest_row.get("outros_ativos_reportados")),
        ("Disponibilidades", latest_row.get("disponibilidades")),
    ]
    output_rows = [
        {"competencia": latest_row["competencia"], "categoria": label, "valor": float(value)}
        for label, value in rows
        if _float_or_none(value) is not None and float(value) > 0
    ]
    known_other = sum(row["valor"] for row in output_rows if row["categoria"] != "Direitos creditórios")
    residual_other = _float_or_none(latest_row.get("outros_ativos_carteira")) or 0.0
    if residual_other > 0 and known_other <= 0:
        output_rows.append(
            {
                "competencia": latest_row["competencia"],
                "categoria": "Outros ativos da carteira",
                "valor": residual_other,
            }
        )
    if not output_rows:
        output_rows.append(
            {
                "competencia": latest_row["competencia"],
                "categoria": "Carteira",
                "valor": float(latest_row.get("carteira") or 0.0),
            }
        )
    total = sum(row["valor"] for row in output_rows)
    for row in output_rows:
        row["percentual"] = (row["valor"] / total * 100.0) if total > 0 else pd.NA
    return pd.DataFrame(output_rows)


def _build_segment_latest_df(*, wide_lookup: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    competencias = [latest_competencia]
    rows = [
        ("Indústria", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_IND"),
        ("Mercado imobiliário", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_MERC_IMOBIL"),
        ("Comércio", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/SEGMT_COMERC/VL_SOM_SEGMT_COMERC"),
        ("Serviços", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/SEGMT_SERV/VL_SOM_SEGMT_SERV"),
        ("Agronegócio", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_AGRONEG"),
        ("Financeiro", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/SEGMT_FINANC/VL_SOM_SEGMT_FINANC"),
        ("Cartão de crédito", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_CART_CRED"),
        ("Factoring", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/SEGMT_FACT/VL_SOM_SEGMT_FACT"),
        ("Setor público", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/SEGMT_SETOR_PUBLIC/VL_SOM_SEGMT_SETOR_PUBLIC"),
        ("Ações judiciais", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_ACAO_JUDIC"),
        ("Propriedade intelectual", "DOC_ARQ/LISTA_INFORM/CART_SEGMT/VL_PROPRD_MARCA_PATENT"),
    ]
    output = []
    for segmento, tag_path in rows:
        valor = float(_numeric_series(wide_lookup, competencias, tag_path).iloc[0])
        output.append({"segmento": segmento, "valor": valor})
    frame = pd.DataFrame(output)
    total = float(frame["valor"].sum()) if not frame.empty else 0.0
    frame["percentual"] = (frame["valor"] / total * 100.0) if total > 0 else pd.NA
    positive = frame[frame["valor"] > 0].copy()
    return positive.reset_index(drop=True) if not positive.empty else frame


def _build_liquidity_latest_df(*, wide_lookup: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    competencias = [latest_competencia]
    buckets = [
        ("Liquidez total", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ"),
        ("30 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_30"),
        ("60 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_60"),
        ("90 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_90"),
        ("180 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_180"),
        ("360 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_360"),
        ("Mais de 360 dias", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_MAIS_360"),
    ]
    rows = []
    for horizonte, tag_path in buckets:
        valor = float(_numeric_series(wide_lookup, competencias, tag_path).iloc[0])
        rows.append({"horizonte": horizonte, "valor": valor})
    return pd.DataFrame(rows)


def _build_maturity_latest_df(*, wide_lookup: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    competencias = [latest_competencia]
    rows = [
        {
            "faixa": "Vencidos",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_SOM_INAD_VENC",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_SOM_INAD_VENC",
                ],
            ),
        },
        {
            "faixa": "Em 30 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_30",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_30",
                ],
            ),
        },
        {
            "faixa": "31 a 60 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_31_60",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_31_60",
                ],
            ),
        },
        {
            "faixa": "61 a 90 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_61_90",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_61_90",
                ],
            ),
        },
        {
            "faixa": "91 a 120 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_91_120",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_91_120",
                ],
            ),
        },
        {
            "faixa": "121 a 150 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_121_150",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_121_150",
                ],
            ),
        },
        {
            "faixa": "151 a 180 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_151_180",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_151_180",
                ],
            ),
        },
        {
            "faixa": "Acima de 180 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_181_360",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_361_720",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_721_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_PRAZO_VENC_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_181_360",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_361_720",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_721_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_PRAZO_VENC_1080",
                ],
            ),
        },
    ]
    return pd.DataFrame(rows)


def _sum_latest_paths(wide_lookup: pd.DataFrame, competencias: list[str], tag_paths: list[str]) -> float:
    total = 0.0
    for tag_path in tag_paths:
        total += float(_numeric_series(wide_lookup, competencias, tag_path).iloc[0])
    return total


def _build_default_history(
    *,
    wide_lookup: pd.DataFrame,
    competencias: list[str],
) -> pd.DataFrame:
    direitos_creditorios = _direitos_creditorios_series(wide_lookup, competencias)
    inadimplencia_total = (
        _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_TOTAL_VENC_INAD")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_TOTAL_VENC_INAD")
    )
    provisao_total = (
        _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_PROVIS_REDUC_RECUP")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_PROVIS_REDUC_RECUP")
    )
    pendencia_total = (
        _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/CRED_EXISTE/VL_CRED_VENC_PEND")
        + _numeric_series(wide_lookup, competencias, "DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/DICRED/VL_DICRED_VENC_PEND")
    )

    df = pd.DataFrame(
        {
            "competencia": competencias,
            "competencia_dt": [_competencia_to_timestamp(competencia) for competencia in competencias],
            "direitos_creditorios": direitos_creditorios.values,
            "inadimplencia_total": inadimplencia_total.values,
            "provisao_total": provisao_total.values,
            "pendencia_total": pendencia_total.values,
        }
    )
    df["inadimplencia_pct"] = (
        df["inadimplencia_total"] / df["direitos_creditorios"]
    ).where(df["direitos_creditorios"] > 0).mul(100.0)
    return df


def _build_default_buckets_latest_df(*, wide_lookup: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    competencias = [latest_competencia]
    rows = [
        {
            "faixa": "Ate 30 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_30",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_30",
                ],
            ),
        },
        {
            "faixa": "31 a 60 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_31_60",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_31_60",
                ],
            ),
        },
        {
            "faixa": "61 a 90 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_61_90",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_61_90",
                ],
            ),
        },
        {
            "faixa": "91 a 120 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_91_120",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_91_120",
                ],
            ),
        },
        {
            "faixa": "121 a 150 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_121_150",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_121_150",
                ],
            ),
        },
        {
            "faixa": "151 a 180 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_151_180",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_151_180",
                ],
            ),
        },
        {
            "faixa": "Acima de 180 dias",
            "valor": _sum_latest_paths(
                wide_lookup,
                competencias,
                [
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_181_360",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_361_720",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_721_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_AQUIS/VL_INAD_VENC_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_181_360",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_361_720",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_721_1080",
                    "DOC_ARQ/LISTA_INFORM/COMPMT_DICRED_SEM_AQUIS/VL_INAD_VENC_1080",
                ],
            ),
        },
    ]
    return pd.DataFrame(rows)


def _build_holder_latest_df(
    *,
    wide_lookup: pd.DataFrame,
    listas_df: pd.DataFrame,
    latest_competencia: str,
) -> pd.DataFrame:
    competencias = [latest_competencia]
    rows: list[dict[str, object]] = []
    total_fields = [
        ("Resumo", "Total de cotistas", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/NUM_COTISTAS/QT_TOTAL_COTISTAS"),
        ("Resumo", "Cotistas sênior", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/NUM_COTISTAS/QT_TOTAL_COTISTAS_SENIOR"),
        ("Resumo", "Cotistas subordinada", "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/NUM_COTISTAS/QT_TOTAL_COTISTAS_SUBORD"),
    ]
    for grupo, categoria, tag_path in total_fields:
        rows.append(
            {
                "grupo": grupo,
                "categoria": categoria,
                "quantidade": float(_numeric_series(wide_lookup, competencias, tag_path).iloc[0]),
            }
        )

    rows.extend(
        _build_holder_series_rows(
            listas_df=listas_df,
            latest_competencia=latest_competencia,
            list_token="NUM_COTISTAS/CLASSE_SENIOR",
            grupo="Sênior",
            label_fields=("SERIE",),
        )
    )
    rows.extend(
        _build_holder_series_rows(
            listas_df=listas_df,
            latest_competencia=latest_competencia,
            list_token="NUM_COTISTAS/CLASSE_SUBORD",
            grupo="Subordinada",
            label_fields=("TIPO", "SERIE"),
        )
    )

    holder_desc_labels = {
        "QNT_PSS_FSC": "Pessoa física",
        "QNT_PSS_JRD": "Pessoa jurídica",
        "BNC_CMR": "Banco comercial",
        "CRT_DTR": "Corretora/distribuidora",
        "OTR_PSS_JRD": "Outras pessoas jurídicas",
        "INV_RSD": "Investidor residente",
        "ENT_ABR_PRD_CMP": "Entidade aberta de previdência",
        "ENT_FCH_PRD": "Entidade fechada de previdência",
        "RGM_PRP_PRD_SRV_PBL": "Regime próprio de previdência",
        "SCD_SGR_RSG": "Sociedade seguradora/resseguradora",
        "SCD_CPT_ARD_MER": "Sociedade de capitalização/arrendamento",
        "FND_INV_CTS": "Fundo de investimento em cotas",
        "FND_INV_IMB": "Fundo imobiliário",
        "OTR_FND_INV": "Outros fundos de investimento",
        "CLB_INV": "Clube de investimento",
        "CAMOTR": "Outros",
    }
    for xml_group, grupo in [
        ("CLS_SENIOR", "Perfil sênior"),
        ("CLS_SUBORDINADA", "Perfil subordinada"),
    ]:
        for tag, label in holder_desc_labels.items():
            valor = float(
                _numeric_series(
                    wide_lookup,
                    competencias,
                    f"DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/NUM_COTISTAS_DESC/{xml_group}/{tag}",
                ).iloc[0]
            )
            if valor > 0:
                rows.append({"grupo": grupo, "categoria": label, "quantidade": valor})

    frame = pd.DataFrame(rows, columns=["grupo", "categoria", "quantidade"])
    if frame.empty:
        return frame
    return frame[frame["quantidade"].fillna(0.0) > 0].reset_index(drop=True)


def _build_holder_series_rows(
    *,
    listas_df: pd.DataFrame,
    latest_competencia: str,
    list_token: str,
    grupo: str,
    label_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    if listas_df.empty:
        return []
    subset = listas_df[
        (listas_df["competencia"] == latest_competencia)
        & (listas_df["list_group_path"].str.contains(list_token, regex=False, na=False))
    ].copy()
    if subset.empty:
        return []
    pivot = (
        subset.pivot_table(
            index=["list_group_path", "list_index"],
            columns="tag",
            values="valor_excel",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    rows = []
    for _, row in pivot.iterrows():
        label = _resolve_class_label(
            row=row,
            class_kind="senior" if grupo == "Sênior" else "subordinada",
            default_label=grupo,
            label_fields=label_fields,
        )
        quantidade = _to_numeric(row.get("QT_COTISTAS")) or 0.0
        if quantidade > 0:
            rows.append({"grupo": grupo, "categoria": label, "quantidade": quantidade})
    return rows


def _build_rate_negotiation_latest_df(*, wide_lookup: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    if "tag_path" not in wide_lookup.columns or latest_competencia not in wide_lookup.columns:
        return pd.DataFrame(columns=["grupo", "operacao", "taxa_min", "taxa_media", "taxa_max"])
    subset = wide_lookup[
        wide_lookup["tag_path"].astype(str).str.startswith("DOC_ARQ/LISTA_INFORM/TAXA_NEGOC_DICRED_MES/")
        & wide_lookup["tag"].isin(["TX_MIN", "TX_MEDIO", "TX_MAX"])
    ].copy()
    if subset.empty:
        return pd.DataFrame(columns=["grupo", "operacao", "taxa_min", "taxa_media", "taxa_max"])
    subset["valor"] = pd.to_numeric(subset[latest_competencia], errors="coerce").fillna(0.0)
    subset["contexto"] = subset["sub_bloco"].map(_humanize_rate_context)
    pivot = (
        subset.pivot_table(index="contexto", columns="tag", values="valor", aggfunc="first")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in ["TX_MIN", "TX_MEDIO", "TX_MAX"]:
        if column not in pivot.columns:
            pivot[column] = 0.0
    pivot["grupo"] = pivot["contexto"].map(lambda value: str(value).split(" / ", 1)[0])
    pivot["operacao"] = pivot["contexto"].map(lambda value: str(value).split(" / ", 1)[1] if " / " in str(value) else str(value))
    output = pivot.rename(columns={"TX_MIN": "taxa_min", "TX_MEDIO": "taxa_media", "TX_MAX": "taxa_max"})
    output = output[["grupo", "operacao", "taxa_min", "taxa_media", "taxa_max"]].copy()
    positive = output[(output[["taxa_min", "taxa_media", "taxa_max"]].abs().sum(axis=1) > 0)].copy()
    return positive.reset_index(drop=True) if not positive.empty else output.reset_index(drop=True)


def _build_tracking_latest_df(
    *,
    summary: dict[str, float | str | None],
    asset_history_df: pd.DataFrame,
    latest_competencia: str,
) -> pd.DataFrame:
    asset_row = _latest_row(asset_history_df, latest_competencia)
    aquisicoes = _float_or_none(asset_row.get("aquisicoes")) or 0.0
    alienacoes = _float_or_none(asset_row.get("alienacoes")) or 0.0
    direitos_creditorios = _float_or_none(summary.get("direitos_creditorios"))
    provisao_total = _float_or_none(summary.get("provisao_total")) or 0.0
    inadimplencia_total = _float_or_none(summary.get("inadimplencia_total")) or 0.0
    rows = [
        {
            "indicador": "Alocação em direitos creditórios",
            "valor": summary.get("alocacao_pct"),
            "unidade": "%",
            "fonte": "APLIC_ATIVO/DICRED",
            "interpretação": "Participação dos direitos creditórios na carteira.",
        },
        {
            "indicador": "Índice de subordinação",
            "valor": summary.get("subordinacao_pct"),
            "unidade": "%",
            "fonte": "OUTRAS_INFORM/DESC_SERIE_CLASSE",
            "interpretação": "PL subordinado dividido pelo PL total das cotas.",
        },
        {
            "indicador": "Inadimplência / direitos creditórios",
            "valor": summary.get("inadimplencia_pct"),
            "unidade": "%",
            "fonte": "APLIC_ATIVO + COMPMT_DICRED",
            "interpretação": "Saldos vencidos inadimplentes sobre direitos creditórios.",
        },
        {
            "indicador": "Provisão / direitos creditórios",
            "valor": (provisao_total / direitos_creditorios * 100.0) if direitos_creditorios else None,
            "unidade": "%",
            "fonte": "APLIC_ATIVO",
            "interpretação": "Provisão reportada sobre direitos creditórios.",
        },
        {
            "indicador": "Provisão / inadimplência",
            "valor": (provisao_total / inadimplencia_total * 100.0) if inadimplencia_total else None,
            "unidade": "%",
            "fonte": "APLIC_ATIVO",
            "interpretação": "Cobertura contábil dos saldos inadimplentes.",
        },
        {
            "indicador": "Aquisições / direitos creditórios",
            "valor": (aquisicoes / direitos_creditorios * 100.0) if direitos_creditorios else None,
            "unidade": "%",
            "fonte": "NEGOC_DICRED_MES",
            "interpretação": "Originação/aquisição no mês sobre a carteira de direitos creditórios.",
        },
        {
            "indicador": "Alienações / direitos creditórios",
            "valor": (alienacoes / direitos_creditorios * 100.0) if direitos_creditorios else None,
            "unidade": "%",
            "fonte": "NEGOC_DICRED_MES",
            "interpretação": "Alienações no mês sobre a carteira de direitos creditórios.",
        },
    ]
    return pd.DataFrame(rows)


def _build_quota_pl_history(
    *,
    wide_lookup: pd.DataFrame,
    listas_df: pd.DataFrame,
    competencias: list[str],
) -> pd.DataFrame:
    frames = [
        _build_scalar_class_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="senior",
            default_label="Senior",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SENIOR/",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_COTAS"),
        ),
        _build_scalar_class_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="subordinada",
            default_label="Subordinada",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/DESC_SERIE_CLASSE_SUBORD/",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_COTAS"),
        ),
        _build_list_class_frame(
            listas_df=listas_df,
            class_kind="senior",
            default_label="Senior",
            list_token="DESC_SERIE_CLASSE_SENIOR",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_COTAS"),
        ),
        _build_list_class_frame(
            listas_df=listas_df,
            class_kind="subordinada",
            default_label="Subordinada",
            list_token="DESC_SERIE_CLASSE_SUBORD",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_COTAS"),
        ),
    ]
    base_df = _finalize_class_frame(
        frames=frames,
        competencias=competencias,
        numeric_fields=("QT_COTAS", "VL_COTAS"),
    )
    if base_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "class_kind", "label", "qt_cotas", "vl_cota", "pl"])
    base_df = base_df.rename(columns={"QT_COTAS": "qt_cotas", "VL_COTAS": "vl_cota"})
    base_df["pl"] = base_df["qt_cotas"].fillna(0.0) * base_df["vl_cota"].fillna(0.0)
    return base_df


def _build_subordination_history(quota_pl_history_df: pd.DataFrame) -> pd.DataFrame:
    if quota_pl_history_df.empty:
        return pd.DataFrame(
            columns=[
                "competencia",
                "competencia_dt",
                "pl_total",
                "pl_senior",
                "pl_subordinada",
                "subordinacao_pct",
            ]
        )

    grouped = (
        quota_pl_history_df.groupby(["competencia", "competencia_dt", "class_kind"], dropna=False)["pl"]
        .sum()
        .unstack(fill_value=0.0)
        .reset_index()
    )
    grouped["pl_senior"] = grouped.get("senior", 0.0)
    grouped["pl_subordinada"] = grouped.get("subordinada", 0.0)
    grouped["pl_total"] = grouped["pl_senior"] + grouped["pl_subordinada"]
    grouped["subordinacao_pct"] = (
        grouped["pl_subordinada"] / grouped["pl_total"]
    ).where(grouped["pl_total"] > 0).mul(100.0)
    return grouped[
        ["competencia", "competencia_dt", "pl_total", "pl_senior", "pl_subordinada", "subordinacao_pct"]
    ]


def _build_return_history(
    *,
    wide_lookup: pd.DataFrame,
    listas_df: pd.DataFrame,
    competencias: list[str],
) -> pd.DataFrame:
    frames = [
        _build_scalar_class_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="senior",
            default_label="Senior",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SENIOR/",
            label_fields=("SERIE",),
            value_fields=("PR_APURADA",),
        ),
        _build_scalar_class_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="subordinada",
            default_label="Subordinada",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/RENT_MES/RENT_CLASSE_SUBORD/",
            label_fields=("TIPO", "SERIE"),
            value_fields=("PR_APURADA",),
        ),
        _build_list_class_frame(
            listas_df=listas_df,
            class_kind="senior",
            default_label="Senior",
            list_token="RENT_CLASSE_SENIOR",
            label_fields=("SERIE",),
            value_fields=("PR_APURADA",),
        ),
        _build_list_class_frame(
            listas_df=listas_df,
            class_kind="subordinada",
            default_label="Subordinada",
            list_token="RENT_CLASSE_SUBORD",
            label_fields=("TIPO", "SERIE"),
            value_fields=("PR_APURADA",),
        ),
    ]
    base_df = _finalize_class_frame(
        frames=frames,
        competencias=competencias,
        numeric_fields=("PR_APURADA",),
    )
    if base_df.empty:
        return pd.DataFrame(columns=["competencia", "competencia_dt", "class_kind", "label", "retorno_mensal_pct"])
    base_df = base_df.rename(columns={"PR_APURADA": "retorno_mensal_pct"})
    return base_df


def _build_return_summary(return_history_df: pd.DataFrame, latest_competencia: str) -> pd.DataFrame:
    if return_history_df.empty:
        return pd.DataFrame(columns=["class_kind", "label", "retorno_mes_pct", "retorno_ano_pct", "retorno_12m_pct"])

    latest_year = _competencia_sort_key(latest_competencia)[0]
    rows: list[dict[str, object]] = []
    for (class_kind, label), group in return_history_df.groupby(["class_kind", "label"], dropna=False):
        ordered = group.sort_values("competencia_dt").copy()
        monthly = pd.to_numeric(ordered["retorno_mensal_pct"], errors="coerce")
        if monthly.dropna().empty:
            continue
        latest_return = float(monthly.dropna().iloc[-1])
        year_mask = ordered["competencia_dt"].dt.year == latest_year
        rows.append(
            {
                "class_kind": class_kind,
                "label": label,
                "retorno_mes_pct": latest_return,
                "retorno_ano_pct": _compound_percent(monthly[year_mask]),
                "retorno_12m_pct": _compound_percent(monthly.tail(12)),
            }
        )
    return pd.DataFrame(rows).sort_values(["class_kind", "label"]).reset_index(drop=True)


def _compound_percent(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    compounded = (1.0 + (numeric / 100.0)).prod() - 1.0
    return float(compounded * 100.0)


def _build_event_history(
    *,
    wide_lookup: pd.DataFrame,
    listas_df: pd.DataFrame,
    competencias: list[str],
) -> pd.DataFrame:
    frames = [
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="senior",
            default_label="Senior",
            event_type="emissao",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SENIOR/",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="emissao",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/CAPT_MES/CLASSE_SUBORD/",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="senior",
            default_label="Senior",
            event_type="resgate",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/RESG_MES/CLASSE_SENIOR/",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="resgate",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/RESG_MES/CLASSE_SUBORD/",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="senior",
            default_label="Senior",
            event_type="amortizacao",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SENIOR/",
            label_fields=("SERIE",),
            value_fields=("VL_COTA", "VL_TOTAL"),
        ),
        _build_scalar_event_frame(
            wide_lookup=wide_lookup,
            competencias=competencias,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="amortizacao",
            base_path="DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/CAPTA_RESGA_AMORTI/AMORT/CLASSE_SUBORD/",
            label_fields=("TIPO", "SERIE"),
            value_fields=("VL_COTA", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="senior",
            default_label="Senior",
            event_type="emissao",
            list_token="CAPT_MES/CLASSE_SENIOR",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="emissao",
            list_token="CAPT_MES/CLASSE_SUBORD",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="senior",
            default_label="Senior",
            event_type="resgate",
            list_token="RESG_MES/CLASSE_SENIOR",
            label_fields=("SERIE",),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="resgate",
            list_token="RESG_MES/CLASSE_SUBORD",
            label_fields=("TIPO", "SERIE"),
            value_fields=("QT_COTAS", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="senior",
            default_label="Senior",
            event_type="amortizacao",
            list_token="AMORT/CLASSE_SENIOR",
            label_fields=("SERIE",),
            value_fields=("VL_COTA", "VL_TOTAL"),
        ),
        _build_list_event_frame(
            listas_df=listas_df,
            class_kind="subordinada",
            default_label="Subordinada",
            event_type="amortizacao",
            list_token="AMORT/CLASSE_SUBORD",
            label_fields=("TIPO", "SERIE"),
            value_fields=("VL_COTA", "VL_TOTAL"),
        ),
    ]
    base_df = _finalize_class_frame(
        frames=frames,
        competencias=competencias,
        numeric_fields=("QT_COTAS", "VL_TOTAL", "VL_COTA"),
    )
    if base_df.empty:
        return pd.DataFrame(
            columns=[
                "competencia",
                "competencia_dt",
                "class_kind",
                "label",
                "event_type",
                "qt_cotas",
                "valor_total",
                "valor_cota",
            ]
        )
    rename_map = {"QT_COTAS": "qt_cotas", "VL_TOTAL": "valor_total", "VL_COTA": "valor_cota"}
    base_df = base_df.rename(columns=rename_map)
    numeric_columns = [column for column in ["qt_cotas", "valor_total", "valor_cota"] if column in base_df.columns]
    if numeric_columns:
        numeric_frame = base_df[numeric_columns].fillna(0.0)
        base_df = base_df[(numeric_frame.abs().sum(axis=1) > 0)].copy()
    return base_df


def _build_scalar_class_frame(
    *,
    wide_lookup: pd.DataFrame,
    competencias: list[str],
    class_kind: str,
    default_label: str,
    base_path: str,
    label_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> pd.DataFrame:
    all_fields = tuple(dict.fromkeys((*label_fields, *value_fields)))
    extracted = {
        field: _get_wide_series(wide_lookup, competencias, f"{base_path}{field}")
        for field in all_fields
    }
    if not any(_has_any_value(extracted[field]) for field in value_fields):
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for competencia in competencias:
        row: dict[str, object] = {"competencia": competencia, "class_kind": class_kind}
        for field in all_fields:
            row[field] = extracted[field].loc[competencia]
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["label"] = frame.apply(
        lambda row: _resolve_class_label(
            row=row,
            class_kind=class_kind,
            default_label=default_label,
            label_fields=label_fields,
        ),
        axis=1,
    )
    return frame


def _build_list_class_frame(
    *,
    listas_df: pd.DataFrame,
    class_kind: str,
    default_label: str,
    list_token: str,
    label_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> pd.DataFrame:
    if listas_df.empty:
        return pd.DataFrame()
    subset = listas_df[listas_df["list_group_path"].str.contains(list_token, regex=False, na=False)].copy()
    if subset.empty:
        return pd.DataFrame()
    pivot = (
        subset.pivot_table(
            index=["competencia", "list_group_path", "list_index"],
            columns="tag",
            values="valor_excel",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    if pivot.empty:
        return pd.DataFrame()
    pivot["class_kind"] = class_kind
    pivot["label"] = pivot.apply(
        lambda row: _resolve_class_label(
            row=row,
            class_kind=class_kind,
            default_label=default_label,
            label_fields=label_fields,
        ),
        axis=1,
    )
    return pivot


def _build_scalar_event_frame(
    *,
    wide_lookup: pd.DataFrame,
    competencias: list[str],
    class_kind: str,
    default_label: str,
    event_type: str,
    base_path: str,
    label_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> pd.DataFrame:
    frame = _build_scalar_class_frame(
        wide_lookup=wide_lookup,
        competencias=competencias,
        class_kind=class_kind,
        default_label=default_label,
        base_path=base_path,
        label_fields=label_fields,
        value_fields=value_fields,
    )
    if frame.empty:
        return frame
    frame["event_type"] = event_type
    return frame


def _build_list_event_frame(
    *,
    listas_df: pd.DataFrame,
    class_kind: str,
    default_label: str,
    event_type: str,
    list_token: str,
    label_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> pd.DataFrame:
    frame = _build_list_class_frame(
        listas_df=listas_df,
        class_kind=class_kind,
        default_label=default_label,
        list_token=list_token,
        label_fields=label_fields,
        value_fields=value_fields,
    )
    if frame.empty:
        return frame
    frame["event_type"] = event_type
    return frame


def _resolve_class_label(
    *,
    row: pd.Series,
    class_kind: str,
    default_label: str,
    label_fields: tuple[str, ...],
) -> str:
    for field in label_fields:
        raw_value = row.get(field)
        if not _is_blank(raw_value):
            return str(raw_value).strip()
    list_index = _to_numeric(row.get("list_index"))
    if list_index is not None and class_kind == "senior":
        return f"{default_label} {int(list_index)}"
    if list_index is not None and int(list_index) > 1:
        return f"{default_label} {int(list_index)}"
    return default_label


def _humanize_rate_context(sub_bloco: object) -> str:
    raw = str(sub_bloco or "").strip()
    if not raw:
        return "Taxas / Não identificado"
    parts = raw.split("/")
    if len(parts) >= 2:
        grupo = _humanize_rate_token(parts[-2])
        operacao = _humanize_rate_token(parts[-1])
        return f"{grupo} / {operacao}"
    return _humanize_rate_token(parts[-1])


def _humanize_rate_token(token: str) -> str:
    normalized = token.upper().replace("TAXA_NEGOC_DICRED_MES_", "")
    replacements = {
        "AQUIS": "Com aquisição",
        "SEM_AQUIS": "Sem aquisição",
        "VALOR_MOBILI": "Valores mobiliários",
        "TITPUB_FED": "Títulos públicos federais",
        "CDB": "CDB",
        "ATIV_RF": "Ativos de renda fixa",
        "DESC_COMPRA": "Desconto compra",
        "DESC_VENDA": "Desconto venda",
        "JUROS_COMPRA": "Juros compra",
        "JUROS_VENDA": "Juros venda",
    }
    if normalized in replacements:
        return replacements[normalized]
    for suffix in ["DESC_COMPRA", "DESC_VENDA", "JUROS_COMPRA", "JUROS_VENDA"]:
        if normalized.endswith(suffix):
            return replacements[suffix]
    return normalized.replace("_", " ").title()


def _has_any_value(series: pd.Series) -> bool:
    return any(not _is_blank(value) for value in series.tolist())


def _finalize_class_frame(
    *,
    frames: list[pd.DataFrame],
    competencias: list[str],
    numeric_fields: tuple[str, ...],
) -> pd.DataFrame:
    usable_frames = [frame for frame in frames if not frame.empty]
    if not usable_frames:
        return pd.DataFrame()

    combined = pd.concat(usable_frames, ignore_index=True, sort=False)
    combined = combined[combined["competencia"].isin(competencias)].copy()
    combined["competencia_dt"] = combined["competencia"].map(_competencia_to_timestamp)
    for field in numeric_fields:
        if field in combined.columns:
            combined[field] = pd.to_numeric(combined[field], errors="coerce")

    dedupe_columns = [column for column in ["competencia", "class_kind", "label", "event_type"] if column in combined.columns]
    combined = combined.sort_values(["competencia_dt", "class_kind", "label"], kind="stable")
    combined = combined.drop_duplicates(subset=dedupe_columns, keep="last")

    existing_numeric = [field for field in numeric_fields if field in combined.columns]
    if existing_numeric:
        combined = combined.dropna(subset=existing_numeric, how="all")

    return combined.reset_index(drop=True)
