from __future__ import annotations

import argparse
import html
import math
import sqlite3
from pathlib import Path

import pandas as pd


DEFAULT_DB = Path("data/fidc_credit_strategy/fidc_credit_strategy.sqlite")
DEFAULT_OUTPUT = Path("reports/fidc_strategy_static_20260609.html")


PALETTE = {
    "ink": "#17212b",
    "muted": "#637083",
    "line": "#dfe6ec",
    "paper": "#fbfcfd",
    "blue": "#25282d",
    "teal": "#59626d",
    "orange": "#ff5a00",
    "red": "#d96a00",
    "green": "#4c8061",
    "gold": "#b3832f",
}


def brl(value: object) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    if abs(number) >= 1e9:
        return f"R$ {number / 1e9:,.1f} bi".replace(",", "_").replace(".", ",").replace("_", ".")
    if abs(number) >= 1e6:
        return f"R$ {number / 1e6:,.0f} mi".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {number:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: object, digits: int = 1) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    return f"{number:.{digits}f}%".replace(".", ",")


def num(value: object, digits: int = 0) -> str:
    number = number_or_nan(value)
    if math.isnan(number):
        return "-"
    return f"{number:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def number_or_nan(value: object) -> float:
    try:
        if value is None:
            return math.nan
        number = float(value)
        return number if math.isfinite(number) else math.nan
    except (TypeError, ValueError):
        return math.nan


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def read_sql(db: Path, query: str) -> pd.DataFrame:
    with sqlite3.connect(db) as conn:
        return pd.read_sql_query(query, conn)


def money_axis(value: float) -> str:
    return brl(value).replace("R$ ", "")


def short_label(label: str, max_len: int = 38) -> str:
    label = str(label)
    return label if len(label) <= max_len else label[: max_len - 1] + "…"


def table_html(frame: pd.DataFrame, formatters: dict[str, callable] | None = None, max_rows: int = 12) -> str:
    formatters = formatters or {}
    if frame.empty:
        return "<p class='empty'>Sem dados suficientes para este corte.</p>"
    clipped = frame.head(max_rows).copy()
    head = "".join(f"<th>{esc(col)}</th>" for col in clipped.columns)
    rows = []
    for _, row in clipped.iterrows():
        cells = []
        for col, value in row.items():
            formatter = formatters.get(col)
            text = formatter(value) if formatter else value
            cells.append(f"<td>{esc(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def bar_chart(
    frame: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    color: str,
    width: int = 920,
    row_h: int = 30,
    value_fmt=brl,
    max_rows: int = 14,
) -> str:
    data = frame[[label_col, value_col]].dropna().copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data[data[value_col].notna() & (data[value_col] > 0)].head(max_rows)
    if data.empty:
        return "<p class='empty'>Sem dados para gráfico.</p>"
    left = 260
    right = 126
    top = 38
    height = top + row_h * len(data) + 22
    max_value = float(data[value_col].max()) or 1
    plot_w = width - left - right
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='20'>{esc(title)}</text>",
    ]
    for i, row in enumerate(data.itertuples(index=False)):
        label = getattr(row, label_col)
        value = float(getattr(row, value_col))
        y = top + i * row_h
        bar_w = max(2, plot_w * value / max_value)
        svg.extend(
            [
                f"<text class='axis-label' x='{left - 10}' y='{y + 18}' text-anchor='end'>{esc(short_label(label))}</text>",
                f"<rect x='{left}' y='{y + 5}' width='{plot_w}' height='16' rx='2' fill='#f0f3f6'/>",
                f"<rect x='{left}' y='{y + 5}' width='{bar_w:.1f}' height='16' rx='2' fill='{color}'/>",
                f"<text class='value-label' x='{left + bar_w + 8:.1f}' y='{y + 18}'>{esc(value_fmt(value))}</text>",
            ]
        )
    svg.append("</svg>")
    return "\n".join(svg)


def bar_dot_chart(
    frame: pd.DataFrame,
    label_col: str,
    bar_col: str,
    dot_col: str,
    title: str,
    dot_label: str,
    width: int = 980,
    row_h: int = 34,
    max_rows: int = 14,
) -> str:
    data = frame[[label_col, bar_col, dot_col]].copy()
    data[bar_col] = pd.to_numeric(data[bar_col], errors="coerce")
    data[dot_col] = pd.to_numeric(data[dot_col], errors="coerce")
    data = data[data[bar_col].notna() & (data[bar_col] > 0)].head(max_rows)
    if data.empty:
        return "<p class='empty'>Sem dados para gráfico.</p>"
    left = 284
    right = 176
    top = 48
    plot_w = width - left - right
    height = top + row_h * len(data) + 24
    max_bar = float(data[bar_col].max()) or 1
    dot_values = data[dot_col].dropna()
    max_dot = max(float(dot_values.max()) if not dot_values.empty else 1, 1)
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='22'>{esc(title)}</text>",
        f"<text class='legend' x='{left}' y='40'>Barra = volume | ponto = {esc(dot_label)}</text>",
    ]
    for i, row in enumerate(data.itertuples(index=False)):
        label = getattr(row, label_col)
        bar_value = float(getattr(row, bar_col))
        dot_value = getattr(row, dot_col)
        y = top + i * row_h
        bar_w = max(2, plot_w * bar_value / max_bar)
        svg.extend(
            [
                f"<text class='axis-label' x='{left - 10}' y='{y + 20}' text-anchor='end'>{esc(short_label(label))}</text>",
                f"<rect x='{left}' y='{y + 6}' width='{plot_w}' height='18' rx='2' fill='#f0f3f6'/>",
                f"<rect x='{left}' y='{y + 6}' width='{bar_w:.1f}' height='18' rx='2' fill='{PALETTE['blue']}'/>",
                f"<text class='value-label' x='{left + bar_w + 8:.1f}' y='{y + 20}'>{esc(brl(bar_value))}</text>",
            ]
        )
        if not pd.isna(dot_value):
            dot_x = left + plot_w * float(dot_value) / max_dot
            svg.extend(
                [
                    f"<circle cx='{dot_x:.1f}' cy='{y + 15}' r='6' fill='{PALETTE['orange']}' stroke='white' stroke-width='2'/>",
                    f"<text class='dot-label' x='{dot_x + 9:.1f}' y='{y + 19}'>{esc(pct(dot_value, 2))}</text>",
                ]
            )
    svg.append("</svg>")
    return "\n".join(svg)


def heatmap_svg(frame: pd.DataFrame, title: str, width: int = 1040, max_rows: int = 10) -> str:
    if frame.empty:
        return "<p class='empty'>Sem dados para heatmap.</p>"
    data = frame.copy()
    data["subtipo"] = data["setor_n1"].astype(str) + " | " + data["setor_n2"].astype(str)
    top = data[["subtipo", "funds"]].drop_duplicates().sort_values("funds", ascending=False).head(max_rows)["subtipo"].tolist()
    data = data[data["subtipo"].isin(top)].copy()
    features = list(data["feature_label"].drop_duplicates())
    rows = top
    cell_w = 44
    cell_h = 24
    left = 220
    top_px = 62
    height = top_px + cell_h * len(rows) + 190
    values = {
        (r["subtipo"], r["feature_label"]): float(r["feature_share"]) * 100
        for _, r in data.iterrows()
    }
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>",
        f"<text class='chart-title' x='0' y='22'>{esc(title)}</text>",
        f"<text class='legend' x='0' y='42'>Frequência equal-weight: percentual dos fundos lidos cujo regulamento contém a cláusula.</text>",
    ]
    for i, row_label in enumerate(rows):
        y = top_px + i * cell_h
        svg.append(f"<text class='axis-label' x='{left - 8}' y='{y + 17}' text-anchor='end'>{esc(short_label(row_label, 30))}</text>")
        for j, feature in enumerate(features):
            value = values.get((row_label, feature), math.nan)
            intensity = 0 if math.isnan(value) else value / 100
            color = interpolate_color("#e8f4ef", "#275b82", intensity)
            x = left + j * cell_w
            svg.append(f"<rect x='{x}' y='{y}' width='{cell_w - 1}' height='{cell_h - 1}' fill='{color}'/>")
    for j, feature in enumerate(features):
        x = left + j * cell_w + 12
        svg.append(f"<text class='axis-label' transform='translate({x},{top_px + cell_h * len(rows) + 10}) rotate(60)'>{esc(short_label(feature, 18))}</text>")
    svg.append("</svg>")
    return "\n".join(svg)


def interpolate_color(start: str, end: str, t: float) -> str:
    t = max(0, min(1, t))
    s = tuple(int(start[i : i + 2], 16) for i in (1, 3, 5))
    e = tuple(int(end[i : i + 2], 16) for i in (1, 3, 5))
    c = tuple(round(s[i] + (e[i] - s[i]) * t) for i in range(3))
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def clean_candidate_filter(column: str = "participant_name_candidate") -> str:
    return f"""
        {column} is not null
        and trim({column}) <> ''
        and length(trim({column})) >= 6
        and upper(trim({column})) not in ('ANDAR','CEP','SALA','CONJUNTO','BAIRRO','CENTRO')
        and upper({column}) not like '% CEP %'
        and upper({column}) not like '%, CEP%'
        and upper({column}) not like '% RUA %'
        and upper({column}) not like '% AVENIDA %'
    """


def build_report(db: Path) -> str:
    meta = read_sql(db, "select key, value from study_metadata")
    meta_dict = dict(zip(meta["key"], meta["value"], strict=False)) if not meta.empty else {}
    period = read_sql(
        db,
        """
        select '2024FY' as periodo,
               sum(case when offers_2024 > 0 then 1 else 0 end) as fundos_emitidos,
               sum(case when emitted_2024 = 1 and has_regulatory_matrix = 1 then 1 else 0 end) as fundos_com_matriz,
               sum(valid_volume_2024_brl) as volume_valido_brl
        from fund_universe
        union all
        select '2025FY',
               sum(case when offers_2025 > 0 then 1 else 0 end),
               sum(case when emitted_2025 = 1 and has_regulatory_matrix = 1 then 1 else 0 end),
               sum(valid_volume_2025_brl)
        from fund_universe
        union all
        select '2026YTD',
               sum(case when offers_2026 > 0 then 1 else 0 end),
               null,
               sum(valid_volume_2026_brl)
        from fund_universe
        """,
    )
    sector = read_sql(
        db,
        """
        select setor_n1 as setor,
               sum(valid_volume_2024_brl) as volume_2024_brl,
               sum(valid_volume_2025_brl) as volume_2025_brl,
               sum(valid_volume_2026_brl) as volume_2026_brl,
               sum(pl_atual_brl) as pl_atual_brl,
               count(distinct cnpj) as fundos
        from fund_universe
        where setor_n1 not in ('Não classificado', 'Sem oferta CVM mapeada')
        group by setor_n1
        order by volume_2025_brl desc
        """,
    )
    heat_2024 = read_sql(db, "select * from regulatory_feature_heatmap_year where emission_cohort = '2024FY' and setor_n1 <> 'Não classificado'")
    heat_2025 = read_sql(db, "select * from regulatory_feature_heatmap_year where emission_cohort = '2025FY' and setor_n1 <> 'Não classificado'")
    pricing = read_sql(
        db,
        """
        select pricing_period,
               setor_n1 || ' | ' || setor_n2 as subtipo,
               volume_brl,
               coalesce(spread_cdi_median_equal_weight_aa, spread_cdi_weighted_by_issue_volume_aa, spread_cdi_weighted_by_current_pl_aa) as cdi_spread,
               spread_cdi_coverage_pct
        from pricing_senior_by_sector_year
        where volume_brl > 0 and setor_n1 <> 'Não classificado'
        order by pricing_period, volume_brl desc
        """,
    )
    ime_sub = read_sql(
        db,
        """
        select emission_cohort,
               setor_n1 || ' | ' || setor_n2 as subtipo,
               current_ime_pl_total_brl,
               actual_subordination_median_equal_weight_pct,
               actual_subordination_weighted_by_current_ime_pl_pct,
               coverage_pct
        from ime_current_subordination_by_sector_year
        where setor_n1 <> 'Não classificado'
        order by emission_cohort, current_ime_pl_total_brl desc
        """,
    )
    quota_price = read_sql(
        db,
        """
        select periodo,
               setor_n1 || ' | ' || setor_n2 as subtipo,
               quota_type,
               operation_type,
               movement_volume_brl,
               unit_price_median_equal_weight,
               unit_price_weighted_by_movement_volume
        from ime_cota_price_by_sector_year
        where quota_type = 'Sênior' and lower(operation_type) like '%capta%' and setor_n1 <> 'Não classificado'
        order by periodo, movement_volume_brl desc
        """,
    )
    participants = read_sql(
        db,
        """
        select role, participant, cast(cnpjs_unicos as integer) as fundos, cast(volume_brl as real) as volume_brl
        from market_participants_by_sector
        where participant is not null and trim(participant) <> ''
        order by volume_brl desc
        """,
    )
    cedentes = read_sql(
        db,
        f"""
        select c.participant_name_candidate as nome,
               count(distinct c.cnpj_fundo) as fundos,
               count(*) as mencoes,
               sum(coalesce(f.valid_volume_2024_brl,0) + coalesce(f.valid_volume_2025_brl,0)) as volume_2024_2025_brl,
               sum(coalesce(f.pl_atual_brl,0)) as pl_atual_brl
        from cedentes_sacados_candidates c
        left join fund_universe f on f.cnpj = c.cnpj_fundo
        where c.participant_type = 'cedente_originador' and {clean_candidate_filter('c.participant_name_candidate')}
        group by c.participant_name_candidate
        having fundos >= 1
        order by volume_2024_2025_brl desc, mencoes desc
        limit 15
        """,
    )
    sacados = read_sql(
        db,
        f"""
        select c.participant_name_candidate as nome,
               count(distinct c.cnpj_fundo) as fundos,
               count(*) as mencoes,
               sum(coalesce(f.valid_volume_2024_brl,0) + coalesce(f.valid_volume_2025_brl,0)) as volume_2024_2025_brl,
               sum(coalesce(f.pl_atual_brl,0)) as pl_atual_brl
        from cedentes_sacados_candidates c
        left join fund_universe f on f.cnpj = c.cnpj_fundo
        where c.participant_type = 'sacado_devedor' and {clean_candidate_filter('c.participant_name_candidate')}
        group by c.participant_name_candidate
        having fundos >= 1
        order by volume_2024_2025_brl desc, mencoes desc
        limit 15
        """,
    )
    fund_counts = read_sql(
        db,
        """
        select count(*) as funds,
               sum(case when has_regulatory_matrix = 1 then 1 else 0 end) as matrix_funds
        from fund_universe
        """,
    ).iloc[0]
    ime_dates = read_sql(db, "select min(ime_dt_comptc) as min_dt, max(ime_dt_comptc) as max_dt from ime_current_snapshot")
    period_cards = "".join(
        f"""
        <div class="metric">
          <div class="metric-label">{esc(row.periodo)}</div>
          <div class="metric-value">{brl(row.volume_valido_brl)}</div>
          <div class="metric-note">{num(row.fundos_emitidos)} emissores | {num(row.fundos_com_matriz) if not pd.isna(row.fundos_com_matriz) else '-'} matrizes</div>
        </div>
        """
        for row in period.itertuples(index=False)
    )
    sector_chart = bar_chart(
        sector.assign(label=sector["setor"]),
        "label",
        "volume_2025_brl",
        "2025 issuance volume by segment",
        PALETTE["teal"],
    )
    sector_table = sector[["setor", "volume_2024_brl", "volume_2025_brl", "volume_2026_brl", "pl_atual_brl", "fundos"]].rename(
        columns={
            "setor": "Segment",
            "volume_2024_brl": "2024 issuance",
            "volume_2025_brl": "2025 issuance",
            "volume_2026_brl": "2026 YTD",
            "pl_atual_brl": "Current PL",
            "fundos": "Funds",
        }
    )
    pricing_2024 = pricing[pricing["pricing_period"] == "2024FY"].head(12)
    pricing_2025 = pricing[pricing["pricing_period"] == "2025FY"].head(12)
    ime_sub_2024 = ime_sub[ime_sub["emission_cohort"] == "2024FY"].head(12)
    ime_sub_2025 = ime_sub[ime_sub["emission_cohort"] == "2025FY"].head(12)
    price_table = quota_price.head(14).rename(
        columns={
            "periodo": "Period",
            "subtipo": "Subtype",
            "movement_volume_brl": "Subscription volume",
            "unit_price_median_equal_weight": "Median unit price",
            "unit_price_weighted_by_movement_volume": "Volume-weighted price",
        }
    )[["Period", "Subtype", "Subscription volume", "Median unit price", "Volume-weighted price"]]
    top_admin = participants[participants["role"].isin(["administrador_cvm", "administrador_oferta"])].head(10)
    top_gestor = participants[participants["role"].isin(["gestor_cvm", "gestor_oferta"])].head(10)
    top_coord = participants[participants["role"].eq("coordenador_lider")].head(10)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Brazil FIDC Strategy Snapshot</title>
  <style>{css()}</style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="kicker">Brazil Private Credit / FIDC</div>
      <h1>FIDC Strategy Snapshot</h1>
      <p class="lead">A lightweight, self-contained executive view of the FIDC study. It shows the final outputs without requiring the 212 MB SQLite database.</p>
      <div class="stamp">As of {esc(meta_dict.get('as_of_date', 'n/d'))} · IME {esc(str(ime_dates.iloc[0]['min_dt']))} to {esc(str(ime_dates.iloc[0]['max_dt']))}</div>
    </section>

    <section class="grid metrics">
      <div class="metric">
        <div class="metric-label">Consolidated FIDCs</div>
        <div class="metric-value">{num(fund_counts['funds'])}</div>
        <div class="metric-note">CNPJs/classes in the universe</div>
      </div>
      <div class="metric">
        <div class="metric-label">Regulatory matrices</div>
        <div class="metric-value">{num(fund_counts['matrix_funds'])}</div>
        <div class="metric-note">Regulations read and classified</div>
      </div>
      {period_cards}
    </section>

    <section class="card">
      <h2>How to explain Brazilian securitization to a foreign investor</h2>
      <div class="two-col">
        <ul>
          <li><strong>FIDC is a bankruptcy-remote receivables vehicle.</strong> Investors buy senior/mezz/subordinated quotas backed by a defined pool of credit rights.</li>
          <li><strong>The market is naturally segmented.</strong> Brazil has consumer credit, payroll loans, FGTS loans, supplier finance, cards/payments, agribusiness, real estate, NPLs and litigation receivables.</li>
          <li><strong>CDI is the base rate language.</strong> Local investors usually read senior pricing as CDI + spread or % of CDI.</li>
          <li><strong>Credit enhancement is explicit.</strong> Subordination, reserves, eligibility criteria, concentration limits, triggers and repurchase obligations are the core structural toolkit.</li>
          <li><strong>There is room for product innovation.</strong> Some segments have material issuance volume but uneven use of reserves, triggers and concentration packages.</li>
          <li><strong>The opportunity is relative value plus structuring.</strong> Better data, cleaner covenants and verified reporting can compress spread while protecting downside.</li>
        </ul>
        <div class="callout">
          <h3>Investment-banking angle</h3>
          <p>The study is meant to identify where a bank can originate, arrange, warehouse or distribute FIDC deals with a clearer structural pitch: lower funding cost for the seller, tighter senior spread for investors, and better downside controls for credit committees.</p>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Market size and segments</h2>
      {sector_chart}
      {table_html(sector_table, {"2024 issuance": brl, "2025 issuance": brl, "2026 YTD": brl, "Current PL": brl, "Funds": num}, 12)}
    </section>

    <section class="card">
      <h2>Regulatory heatmaps: what clauses are common?</h2>
      <p class="note">These matrices read only funds with regulatory documents in the study. “No evidence” means the clause was not found by the extractor in the available regulation package.</p>
      {heatmap_svg(heat_2024, "2024 issued funds: regulation feature matrix")}
      {heatmap_svg(heat_2025, "2025 issued funds: regulation feature matrix")}
    </section>

    <section class="card">
      <h2>Senior tranche economics: issuance size vs CDI+ spread</h2>
      <p class="note">Bars show mapped senior issuance volume. Orange dots show CDI+ spread when extracted. Coverage is uneven because many offerings do not expose a clean CDI+ field in the parsed data.</p>
      {bar_dot_chart(pricing_2024, "subtipo", "volume_brl", "cdi_spread", "2024 senior pricing", "CDI+ a.a.")}
      {bar_dot_chart(pricing_2025, "subtipo", "volume_brl", "cdi_spread", "2025 senior pricing", "CDI+ a.a.")}
    </section>

    <section class="card">
      <h2>Current subordination observed in CVM monthly reports</h2>
      <p class="note">This is the economic structure observed from IME quota values, not only the minimum subordination language in regulations.</p>
      {bar_dot_chart(ime_sub_2024.rename(columns={"current_ime_pl_total_brl": "volume", "actual_subordination_median_equal_weight_pct": "dot"}), "subtipo", "volume", "dot", "2024 cohort: current PL vs actual subordination", "median subordination")}
      {bar_dot_chart(ime_sub_2025.rename(columns={"current_ime_pl_total_brl": "volume", "actual_subordination_median_equal_weight_pct": "dot"}), "subtipo", "volume", "dot", "2025 cohort: current PL vs actual subordination", "median subordination")}
    </section>

    <section class="card">
      <h2>Senior quota subscription prices from IME</h2>
      <p class="note">Unit prices are reported by quota movement and can be distorted by class conventions. Use this as a screen for follow-up, not as final pricing diligence.</p>
      {table_html(price_table, {"Subscription volume": brl, "Median unit price": lambda x: num(x, 2), "Volume-weighted price": lambda x: num(x, 2)}, 14)}
    </section>

    <section class="card">
      <h2>Platforms, managers and coordinators</h2>
      <div class="three-col">
        <div>
          <h3>Administrators</h3>
          {table_html(top_admin.rename(columns={"participant": "Name", "fundos": "Funds", "volume_brl": "Volume"})[["Name", "Funds", "Volume"]], {"Funds": num, "Volume": brl}, 10)}
        </div>
        <div>
          <h3>Managers / gestores</h3>
          {table_html(top_gestor.rename(columns={"participant": "Name", "fundos": "Funds", "volume_brl": "Volume"})[["Name", "Funds", "Volume"]], {"Funds": num, "Volume": brl}, 10)}
        </div>
        <div>
          <h3>Lead coordinators</h3>
          {table_html(top_coord.rename(columns={"participant": "Name", "fundos": "Funds", "volume_brl": "Volume"})[["Name", "Funds", "Volume"]], {"Funds": num, "Volume": brl}, 10)}
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Cedentes and sacados: candidate map</h2>
      <p class="note">These are text-extracted candidates from documents/regulations, aggregated by associated fund volume. They are useful for prioritizing manual review, but not a definitive legal list of obligors or sellers.</p>
      <div class="two-col">
        <div>
          <h3>Candidate cedentes / originators</h3>
          {table_html(cedentes.rename(columns={"nome": "Name", "fundos": "Funds", "mencoes": "Mentions", "volume_2024_2025_brl": "2024-2025 volume", "pl_atual_brl": "Current PL"}), {"Funds": num, "Mentions": num, "2024-2025 volume": brl, "Current PL": brl}, 12)}
        </div>
        <div>
          <h3>Candidate sacados / debtors</h3>
          {table_html(sacados.rename(columns={"nome": "Name", "fundos": "Funds", "mencoes": "Mentions", "volume_2024_2025_brl": "2024-2025 volume", "pl_atual_brl": "Current PL"}), {"Funds": num, "Mentions": num, "2024-2025 volume": brl, "Current PL": brl}, 12)}
        </div>
      </div>
    </section>

    <section class="card">
      <h2>What to do next</h2>
      <ol>
        <li>Pick 20 high-materiality subtypes and manually review the regulations behind the heatmap outliers.</li>
        <li>Validate CDI+ extraction and pricing fields for the largest deals with missing spread coverage.</li>
        <li>Clean the cedente/sacado candidate map into a named-party database.</li>
        <li>Turn the opportunity list into commercial theses: who to pitch, what structure, expected investor appetite, and required credit enhancement.</li>
        <li>Create an English investor deck from this static view: market, structure, participants, economics, risks and why now.</li>
      </ol>
    </section>
  </main>
</body>
</html>
"""


def css() -> str:
    return f"""
    :root {{
      --ink: {PALETTE['ink']};
      --muted: {PALETTE['muted']};
      --line: {PALETTE['line']};
      --paper: {PALETTE['paper']};
      --blue: {PALETTE['blue']};
      --teal: {PALETTE['teal']};
      --orange: {PALETTE['orange']};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef2f5;
      color: var(--ink);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 34px 24px 56px; }}
    .hero {{
      background: linear-gradient(135deg, #17324d, #275f63);
      color: white;
      border-radius: 8px;
      padding: 34px 36px;
      margin-bottom: 18px;
    }}
    .kicker {{ color: #f0b266; font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ font-size: 46px; line-height: 1.02; margin: 10px 0 12px; letter-spacing: 0; }}
    h2 {{ font-size: 24px; margin: 0 0 14px; }}
    h3 {{ font-size: 15px; margin: 14px 0 8px; color: #263544; }}
    .lead {{ max-width: 760px; font-size: 18px; color: #dce7ee; margin: 0 0 16px; }}
    .stamp {{ display: inline-block; color: #dce7ee; border: 1px solid rgba(255,255,255,.25); border-radius: 999px; padding: 6px 12px; font-size: 13px; }}
    .grid.metrics {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }}
    .metric, .card {{
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(25,36,48,.05);
    }}
    .metric {{ padding: 16px; min-height: 118px; }}
    .metric-label {{ font-size: 11px; color: var(--muted); font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }}
    .metric-value {{ font-size: 25px; font-weight: 800; margin-top: 8px; }}
    .metric-note {{ color: var(--muted); font-size: 13px; margin-top: 5px; }}
    .card {{ padding: 24px; margin: 14px 0; overflow-x: auto; }}
    .two-col {{ display: grid; grid-template-columns: 1.35fr .9fr; gap: 22px; }}
    .three-col {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
    .callout {{ background: #f5f8fa; border: 1px solid var(--line); border-left: 4px solid var(--orange); border-radius: 6px; padding: 16px; }}
    .note, .empty {{ color: var(--muted); font-size: 13px; margin: 4px 0 12px; }}
    ul, ol {{ margin-top: 0; padding-left: 21px; }}
    li {{ margin: 8px 0; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }}
    th {{ text-align: left; color: #536271; background: #f4f7f9; border-bottom: 1px solid var(--line); padding: 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    td {{ border-bottom: 1px solid #edf1f4; padding: 8px; vertical-align: top; }}
    svg {{ width: 100%; height: auto; margin: 10px 0 12px; }}
    .chart-title {{ font: 700 17px Inter, Arial, sans-serif; fill: var(--ink); }}
    .legend {{ font: 12px Inter, Arial, sans-serif; fill: var(--muted); }}
    .axis-label {{ font: 11px Inter, Arial, sans-serif; fill: #536271; }}
    .value-label {{ font: 11px Inter, Arial, sans-serif; fill: var(--ink); }}
    .dot-label {{ font: 11px Inter, Arial, sans-serif; fill: var(--orange); font-weight: 700; }}
    @media (max-width: 900px) {{
      main {{ padding: 18px 12px 36px; }}
      h1 {{ font-size: 34px; }}
      .grid.metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .two-col, .three-col {{ grid-template-columns: 1fr; }}
    }}
    """


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a lightweight static FIDC strategy report.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db = Path(args.db)
    output = Path(args.output)
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    output.parent.mkdir(parents=True, exist_ok=True)
    html_text = build_report(db)
    output.write_text(html_text, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
