from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
import re
from typing import Any

import pandas as pd
import streamlit as st

from services.deep_dive_ppt_export import build_deep_dive_pptx_bytes
from services.deep_dive_store import (
    deep_dive_matches_portfolio,
    list_deep_dives,
    load_deep_dive_table,
)
from services.fundonet_dashboard import build_dashboard_data
from services.fundonet_service import InformeMensalService
from services.ime_loader import load_or_extract_informe
from services.ime_period import current_default_end_month, shift_month
from services.monitoring_metrics import build_monitoring_tables, read_wide_csv
from services.portfolio_store import portfolio_basket_signature
from tabs.ime_portfolio_support import (
    build_portfolio_record_label_lookup,
    list_saved_portfolios,
)


_CSS = """
<style>
.deepdive-kicker {
    color: #6b7280;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.deepdive-title {
    color: #1f1f1f;
    font-size: 1.55rem;
    font-weight: 650;
    line-height: 1.15;
    margin: 0.1rem 0 0.25rem 0;
}
.deepdive-subtitle {
    color: #6b7280;
    font-size: 0.86rem;
    line-height: 1.35;
    margin-bottom: 0.65rem;
}
.deepdive-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin: 0.45rem 0 0.8rem 0;
}
.deepdive-chip {
    background: #f7f7f7;
    border: 1px solid #e0e0e0;
    border-radius: 999px;
    color: #4d4d4d;
    display: inline-flex;
    font-size: 0.74rem;
    line-height: 1.15;
    padding: 5px 9px;
}
.deepdive-table-wrap {
    border: 1px solid #d9dee5;
    border-radius: 4px;
    max-width: 100%;
    overflow-x: auto;
}
.deepdive-table {
    border-collapse: collapse;
    font-size: 0.76rem;
    table-layout: fixed;
    width: 100%;
}
.deepdive-table th {
    background: #111827;
    border-right: 1px solid rgba(255,255,255,0.14);
    color: #ffffff;
    font-weight: 650;
    line-height: 1.18;
    padding: 6px 7px;
    text-align: center;
    vertical-align: middle;
}
.deepdive-table th:first-child {
    text-align: left;
    width: 230px;
}
.deepdive-table th.highlight {
    background: #ec7000;
}
.deepdive-table td {
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #eeeeee;
    color: #1f1f1f;
    line-height: 1.20;
    padding: 5px 7px;
    text-align: center;
    vertical-align: middle;
    word-break: normal;
    overflow-wrap: anywhere;
}
.deepdive-table td.longtext {
    font-size: 0.72rem;
    line-height: 1.26;
    text-align: left;
    vertical-align: top;
}
.deepdive-cell-list {
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.deepdive-cell-list div {
    border-bottom: 1px solid #eeeeee;
    padding-bottom: 3px;
}
.deepdive-cell-list div:last-child {
    border-bottom: 0;
    padding-bottom: 0;
}
.deepdive-table td:first-child {
    background: #f7f7f7;
    font-weight: 650;
    text-align: left;
}
.deepdive-table td.highlight {
    background: #fff2e8;
}
.deepdive-table tr:nth-child(even) td:not(:first-child):not(.highlight) {
    background: #fbfbfb;
}
.deepdive-live-note {
    color: #6b7280;
    font-size: 0.74rem;
    line-height: 1.25;
    margin: 0.25rem 0 0.55rem 0;
}
</style>
"""

_LIVE_IME_ROWS = {
    "PL (R$ mm)": "PL (R$ MM)",
    "Direitos creditórios / PL": "Dir Cred / PL",
    "Vencidos Over 30d / crédito": "Vencidos Over 30 d / Crédito",
    "Vencidos Over 60d / crédito": "Vencidos Over 60 d / Crédito",
    "Vencidos Over 90d / crédito": "Vencidos Over 90 d / Crédito",
    "Vencidos Over 180d / crédito": "Vencidos Over 180 d / Crédito",
    "Vencidos Over 360d / crédito": "Vencidos Over 360 d / Crédito",
    "PDD / crédito": "PDD / Crédito",
    "PDD / vencidos": "PDD / Venc Total",
    "Cotas sênior / PL": "Cotas SR / PL %",
    "Cotas mezanino / PL": "Cotas MZ / PL %",
    "Cotas subordinadas / PL": "Cotas Sub / PL %",
}

_LONG_TEXT_ROWS = {
    "Emissões detectadas (data, classe, preço e volume)",
    "Remuneração-alvo por emissão detectada",
    "Amortização/vencimento por emissão detectada",
    "Hedges permitidos",
}

_REVERSE_ENGINEERING_PROMPT = """Você é Codex trabalhando no repositório local `/fidc`.

Tarefa: atualizar o Deep Dive de UMA ÚNICA carteira específica, com o mesmo nível de profundidade usado na curadoria Pravaler. Não faça atualização em massa. Não processe outras carteiras. Não tente economizar tempo reduzindo escopo.

INPUTS DA EXECUÇÃO:
- Nome da carteira: [NOME_DA_CARTEIRA]
- CNPJs dos fundos: [LISTA_DE_CNPJS]
- Caminho do repositório: /Users/matheusjprates/fidc
- Caminhos locais relevantes: [data/raw, reports, data/regulatory_profiles, data/deep_dives, caches IME]
- Período de análise: [PERÍODO]
- Deep Dive ID esperado: [DEEP_DIVE_ID]
- Outputs esperados: comparison_main.csv, emissions.csv, thresholds.csv, evidence/performance_metrics_enriched.csv, manifest.json, PPTX QA editável

REGRAS INEGOCIÁVEIS:
1. Analise apenas esta carteira. É proibido atualizar todas as carteiras.
2. Não faça batch.
3. Não misture documentos de outros grupos econômicos.
4. Não use LLM nem API externa nesta etapa.
5. Use apenas dados já inventariados no repositório: `reports/regulatory_document_inventory.csv`, `reports/regulatory_criteria_matrix.csv`, `data/regulatory_profiles/*`, `data/regulatory_knowledge/*`, `data/raw/*` e caches IME locais.
6. Não use inferência fraca para preencher thresholds, preço, spread, prazo, remuneração, cronograma, volume ou quantidade de cotas.
7. Toda afirmação material precisa ter fonte: arquivo, data, seção, página, cláusula ou ID documental quando disponível.
8. Lacunas devem aparecer como lacunas, não como zeros, médias, extrapolações ou estimativas.
9. Conflitos entre documentos devem ser registrados.
10. O resultado precisa ser utilizável na aba Deep Dive e exportável em PPTX editável.
11. Não rasterize tabelas no PPTX.
12. Preserve pacotes Deep Dive existentes, dados curados, modelo MC3 e arquivos locais não rastreados.
13. Preserve a separação: documentos/emissões/thresholds são offline e versionados; métricas IME devem ser atualizadas ao vivo pela aba usando `load_or_extract_informe` quando aplicável.

ETAPA 1 — SINCRONIZAÇÃO E ESCOPO:
- Rode `git pull --rebase`.
- Verifique `git status`.
- Identifique a carteira em `portfolios.json`.
- Confirme CNPJs e nomes dos fundos.
- Liste somente documentos e caches relacionados aos CNPJs informados.
- Não toque em arquivos não rastreados sem necessidade.

ETAPA 2 — INVENTÁRIO DOCUMENTAL DA CARTEIRA:
Para cada CNPJ, inventarie todos os documentos disponíveis no repo:
- regulamentos;
- regulamentos consolidados;
- suplementos;
- atas de assembleia;
- anúncios de início/encerramento;
- documentos de emissão;
- fatos relevantes;
- relatórios trimestrais;
- demonstrações financeiras;
- relatórios de rating;
- comunicados a cotistas;
- XML/IME;
- arquivos auxiliares.

Use preferencialmente:
- `reports/regulatory_document_inventory.csv`;
- `reports/regulatory_criteria_matrix.csv`;
- `data/raw/<cnpj>/`;
- `data/regulatory_knowledge/`;
- `data/regulatory_profiles/`;
- caches IME existentes.

Conte páginas de PDFs quando isso for útil para indicar cobertura documental. Não use quantidade de PDFs como métrica principal se páginas forem mais informativas.

ETAPA 3 — LEITURA E EXTRAÇÃO DOCUMENTAL:
Leia documentos relevantes um a um. Dê prioridade a documentos de emissão, suplementos, atas e regulamentos mais recentes, mas não ignore versões antigas quando forem necessárias para reconstruir histórico.

Extraia, por emissão/série/classe:
- fundo;
- CNPJ;
- classe/série;
- tipo de cota: sênior, mezanino, subordinada;
- data de deliberação;
- data de emissão / primeira integralização;
- data de encerramento/oferta;
- quantidade emitida;
- VNU/preço unitário;
- volume total;
- remuneração-alvo / benchmark / CDI + spread / IPCA + spread;
- se o spread veio de bookbuilding, ato ou suplemento;
- prazo;
- carência;
- juros;
- amortização;
- vencimento;
- fonte documental;
- status de curadoria.

Se o valor final não estiver localizado, escreva explicitamente:
- `spread final não localizado`;
- `sobretaxa definida em bookbuilding`;
- `sobretaxa definida em ato`;
- `sobretaxa definida em suplemento`;
- `prazo remetido ao suplemento`;
- `cronograma fechado não identificado`;
conforme o caso.

ETAPA 4 — REGULAMENTO MAIS RECENTE E CRITÉRIOS MONITORÁVEIS:
Para cada fundo, identifique o regulamento/documento vigente mais recente disponível.

Extraia critérios monitoráveis ou parcialmente monitoráveis via IME:
- subordinação mínima;
- relação mínima;
- alocação mínima em direitos creditórios;
- índice de atraso / inadimplência por faixa;
- PDD / cobertura;
- reserva de liquidez / caixa;
- derivativos/hedge permitidos;
- concentração;
- eventos de avaliação;
- eventos de liquidação;
- vencimento antecipado;
- waivers/amendments relevantes.

Para cada critério, registre:
- limite;
- comparação;
- evento;
- métrica IME correspondente;
- grau de monitorabilidade: monitorável, monitorável com ressalva, parcial, não monitorável;
- fonte exata.

Não transforme regra jurídica em métrica se o IME não tiver granularidade suficiente.

ETAPA 5 — CONFRONTO COM DADOS ESTRUTURADOS DO APP:
Compare achados documentais com os dados estruturados já usados pelo app:
- IME / Fundos.NET;
- `build_monitoring_tables`;
- Deep Dive live IME metrics;
- caches locais;
- dados de PL, direitos creditórios, vencidos, PDD, cotas/PL, subordinação.

Separe:
- dados documentais offline;
- dados IME ao vivo;
- lacunas;
- divergências;
- limitações metodológicas.

ETAPA 6 — PERSISTÊNCIA:
Crie ou atualize arquivos específicos da carteira, seguindo padrão auditável:
- `data/regulatory_profiles/<slug_carteira>_cotas_emissoes_pagamentos.csv`
- `data/regulatory_profiles/<slug_carteira>_criteria_monitoraveis_ime.csv`
- `data/deep_dives/<deep_dive_id>/tables/emissions.csv`
- `data/deep_dives/<deep_dive_id>/tables/thresholds.csv`
- `data/deep_dives/<deep_dive_id>/tables/comparison_main.csv`
- `data/deep_dives/<deep_dive_id>/evidence/performance_metrics_enriched.csv`
- `data/deep_dives/<deep_dive_id>/manifest.json`

Se o gerador ainda não suportar uma curadoria específica para esta carteira, implemente a menor generalização segura, sem hardcode frágil, sem quebrar Pravaler e sem quebrar carteiras já existentes.

ETAPA 7 — FORMATO DO COMPARATIVO:
A tabela principal deve ter:
- primeira coluna: `Nome`;
- demais colunas: um fundo por coluna;
- linhas para métricas IME ao vivo;
- linhas para emissões detectadas;
- linhas para remuneração-alvo por emissão;
- linhas para amortização/vencimento;
- linhas para subordinação mínima;
- linhas para alocação mínima;
- linhas para eventos de avaliação/liquidação;
- linhas para reserva/caixa;
- linhas para hedges permitidos;
- linhas para lacunas relevantes.

Texto longo deve quebrar de forma legível no Streamlit e no PPTX. Não deixe `...` truncando cronogramas ou emissões.

ETAPA 8 — PPTX EDITÁVEL:
Gere PPTX QA com `services.deep_dive_ppt_export.build_deep_dive_pptx_bytes`.
Verifique:
- tabelas reais editáveis;
- cabeçalho preservado;
- múltiplos slides quando necessário;
- sem texto truncado;
- sem reticências indevidas;
- sem rasterização;
- layout institucional sóbrio.

ETAPA 9 — VALIDAÇÕES:
Antes de encerrar, rode:
- `py_compile` nos arquivos Python alterados;
- validação de CSV com pandas;
- contagem de emissões por fundo;
- checagem de remuneração vazia;
- checagem de amortização/vencimento vazio;
- checagem de colunas esperadas em `comparison_main.csv`;
- geração e abertura estrutural do PPTX via `python-pptx`;
- `git diff --check`.

Critérios mínimos:
- nenhuma remuneração deve ficar vazia sem justificativa textual;
- nenhuma lacuna deve virar zero;
- cada emissão deve ter fonte;
- cada threshold deve ter fonte;
- o pacote deve aparecer na aba Deep Dive;
- o PPTX deve ser editável.

ETAPA 10 — ENTREGA:
Informe:
- carteira processada;
- CNPJs processados;
- documentos/fontes usados;
- número de emissões/classes detectadas por fundo;
- principais spreads/benchmarks encontrados;
- principais lacunas;
- critérios monitoráveis por IME;
- arquivos alterados;
- validações realizadas;
- hash do commit, se houver commit;
- status do push.

Se for pedido commit/push:
- adicione somente arquivos rastreados e relevantes;
- não adicione PDFs soltos, relatórios temporários ou arquivos não relacionados;
- faça commit com mensagem objetiva;
- faça push."""


def render_tab_deep_dive() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    manifests = list_deep_dives()
    st.markdown("<div class='deepdive-kicker'>Análise offline</div>", unsafe_allow_html=True)
    st.markdown("<div class='deepdive-title'>Deep Dive</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='deepdive-subtitle'>Pacotes comparativos gerados por extração offline, versionados no repositório e exportáveis em PPTX editável.</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Prompt para atualizar Deep Dives", expanded=False):
        st.code(_REVERSE_ENGINEERING_PROMPT, language="markdown")

    if not manifests:
        st.info("Nenhum pacote em `data/deep_dives/`.")
        return

    portfolios = list_saved_portfolios()
    portfolio_labels = build_portfolio_record_label_lookup(portfolios)
    portfolio_options = ["Todos", *[portfolio.id for portfolio in portfolios]]
    selected_portfolio_id = st.selectbox(
        "Carteira",
        options=portfolio_options,
        format_func=lambda value: "Todos os Deep Dives" if value == "Todos" else portfolio_labels.get(value, value),
        key="deep_dive_portfolio",
    )
    selected_portfolio = next((portfolio for portfolio in portfolios if portfolio.id == selected_portfolio_id), None)
    selected_signature = portfolio_basket_signature(selected_portfolio.funds) if selected_portfolio else ""
    available = [
        manifest
        for manifest in manifests
        if selected_portfolio_id == "Todos" or deep_dive_matches_portfolio(manifest, selected_portfolio_id, selected_signature)
    ]
    if not available:
        st.warning("Não há Deep Dive salvo para a carteira selecionada.")
        return

    manifest = st.selectbox(
        "Material",
        options=available,
        format_func=lambda item: f"{item.title} · {item.generated_at or item.deep_dive_id}",
        key="deep_dive_manifest",
    )
    _render_manifest_header(manifest)

    if not manifest.tables:
        st.warning("Pacote sem tabelas configuradas.")
        return
    table_spec = st.selectbox(
        "Tabela",
        options=list(manifest.tables),
        format_func=lambda item: item.title,
        key=f"deep_dive_table::{manifest.deep_dive_id}",
    )
    frame = load_deep_dive_table(manifest, table_spec)
    if frame.empty:
        st.warning("Tabela vazia ou arquivo ausente.")
        return
    live_audit = pd.DataFrame()
    if table_spec.id == "comparison_main":
        frame, live_audit = _apply_live_ime_metrics(frame, manifest)

    highlight_options = ["Nenhuma", *frame.columns[1:].tolist()]
    highlighted_column = st.selectbox(
        "Coluna em destaque",
        options=highlight_options,
        index=0,
        key=f"deep_dive_highlight::{manifest.deep_dive_id}::{table_spec.id}",
    )
    highlight_value = None if highlighted_column == "Nenhuma" else highlighted_column

    top_cols = st.columns([1, 1, 4], gap="small")
    with top_cols[0]:
        st.download_button(
            "Baixar CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with top_cols[1]:
        try:
            pptx_bytes = build_deep_dive_pptx_bytes(
                manifest,
                [(table_spec, frame)],
                highlighted_column=highlight_value,
            )
            st.download_button(
                "Baixar PPTX",
                data=pptx_bytes,
                file_name=f"{_safe_token(manifest.deep_dive_id)}_{_safe_token(table_spec.id)}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
        except RuntimeError as exc:
            st.warning(str(exc))

    _render_comparison_table(frame, highlighted_column=highlight_value)

    with st.expander("Fontes e lacunas", expanded=False):
        if manifest.warnings:
            for warning in manifest.warnings:
                st.caption(f"- {warning}")
        if not live_audit.empty:
            st.markdown("**Atualização IME ao vivo**")
            st.dataframe(live_audit, hide_index=True, use_container_width=True)
        st.dataframe(_source_files_df(manifest), hide_index=True, use_container_width=True)


def _render_manifest_header(manifest: Any) -> None:
    chips = [
        f"{len(manifest.funds)} fundo(s)",
        manifest.generated_at or "sem timestamp",
        manifest.source or "fonte offline",
        manifest.confidentiality,
    ]
    st.markdown(
        "<div class='deepdive-chip-row'>"
        + "".join(f"<span class='deepdive-chip'>{escape(chip)}</span>" for chip in chips if chip)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_comparison_table(frame: pd.DataFrame, *, highlighted_column: str | None) -> None:
    header_cells = []
    for column in frame.columns:
        css_class = " class='highlight'" if column == highlighted_column else ""
        header_cells.append(f"<th{css_class}>{escape(str(column))}</th>")
    rows: list[str] = []
    for _, row in frame.iterrows():
        cells = []
        row_label = str(row.get(frame.columns[0], ""))
        is_long_row = row_label in _LONG_TEXT_ROWS
        for column in frame.columns:
            classes = []
            if column == highlighted_column:
                classes.append("highlight")
            if is_long_row and column != frame.columns[0]:
                classes.append("longtext")
            css_class = f" class='{' '.join(classes)}'" if classes else ""
            cells.append(f"<td{css_class}>{_cell_html(row.get(column, '—'), long_text=is_long_row and column != frame.columns[0])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        "<div class='deepdive-table-wrap'><table class='deepdive-table'><thead><tr>"
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _cell_html(value: object, *, long_text: bool) -> str:
    text = str(value if value is not None else "—").strip() or "—"
    if text.lower() in {"nan", "none", "<na>"}:
        text = "—"
    if not long_text or text == "—":
        return escape(text).replace("\n", "<br>")
    items = [item.strip() for item in re.split(r"\s+\|\s+|\n+", text) if item.strip()]
    if len(items) <= 1:
        return escape(text)
    return "<div class='deepdive-cell-list'>" + "".join(f"<div>{escape(item)}</div>" for item in items) + "</div>"


def _apply_live_ime_metrics(frame: pd.DataFrame, manifest: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty or not getattr(manifest, "funds", None):
        return frame, pd.DataFrame()
    first_col = frame.columns[0]
    if first_col not in frame.columns:
        return frame, pd.DataFrame()
    output = frame.copy()
    label_mask = output[first_col].astype(str)
    if not label_mask.isin({"Última competência IME", *_LIVE_IME_ROWS.keys()}).any():
        return output, pd.DataFrame()

    end_month = current_default_end_month()
    audit_rows: list[dict[str, object]] = []
    for fund in manifest.funds:
        cnpj = _digits(fund.get("cnpj"))
        column = _find_fund_column(output, fund)
        if not cnpj or column is None:
            continue
        metrics = _load_live_ime_metrics(cnpj, end_month.isoformat())
        audit_rows.append(
            {
                "Fundo": column,
                "CNPJ": _format_cnpj(cnpj),
                "Competência": metrics.get("competencia") or "—",
                "Cache": metrics.get("cache_status") or "—",
                "Status": metrics.get("status") or "OK",
            }
        )
        if metrics.get("status") != "OK":
            continue
        _set_row_value(output, first_col, "Última competência IME", column, str(metrics.get("competencia") or "—"))
        for row_label, indicator in _LIVE_IME_ROWS.items():
            value = metrics.get("values", {}).get(indicator, "—")
            _set_row_value(output, first_col, row_label, column, value)
    return output, pd.DataFrame(audit_rows)


def _find_fund_column(frame: pd.DataFrame, fund: dict[str, str]) -> str | None:
    candidates = [
        str(fund.get("short_name") or "").strip(),
        str(fund.get("name") or "").strip(),
        _short_name(fund.get("name") or fund.get("cnpj") or ""),
    ]
    columns = list(frame.columns[1:])
    normalized = {_normalize_text(column): column for column in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        match = normalized.get(_normalize_text(candidate))
        if match:
            return match
    return None


def _set_row_value(frame: pd.DataFrame, first_col: str, row_label: str, column: str, value: str) -> None:
    mask = frame[first_col].astype(str).eq(row_label)
    if mask.any() and column in frame.columns:
        frame.loc[mask, column] = value


@st.cache_data(ttl=1800, show_spinner=False)
def _load_live_ime_metrics(cnpj: str, end_month_iso: str) -> dict[str, Any]:
    end_month = date.fromisoformat(end_month_iso)
    start_month = shift_month(end_month, -5)
    try:
        cached = load_or_extract_informe(
            cnpj_fundo=cnpj,
            data_inicial=start_month,
            data_final=end_month,
        )
        result = cached.result
        cache_status = cached.cache_status
        latest_month = _latest_competencia_month(result.competencias)
        if cached.cache_status == "hit" and latest_month is not None and latest_month < end_month:
            try:
                fresh = InformeMensalService().run(
                    cnpj_fundo=cnpj,
                    data_inicial=start_month,
                    data_final=end_month,
                    progress_callback=None,
                )
                fresh_latest = _latest_competencia_month(fresh.competencias)
                if fresh_latest is not None and fresh_latest >= latest_month:
                    result = fresh
                    cache_status = "live_probe"
            except Exception:  # noqa: BLE001
                cache_status = "hit"
        competencias = list(result.competencias or [])
        if not competencias:
            return {"status": "sem competência IME", "cache_status": cache_status, "values": {}}
        competencia = sorted(competencias, key=_competencia_sort_key)[-1]
        wide_df = read_wide_csv(result.wide_csv_path)
        dashboard_data = None
        try:
            dashboard_data = build_dashboard_data(
                wide_csv_path=result.wide_csv_path,
                listas_csv_path=result.listas_csv_path,
                docs_csv_path=result.docs_csv_path,
            )
        except Exception:  # noqa: BLE001
            dashboard_data = None
        tables = build_monitoring_tables(
            wide_df,
            competencias,
            cnpj=cnpj,
            overrides={},
            dashboard_data=dashboard_data,
        )
        values: dict[str, str] = {}
        for indicator in _LIVE_IME_ROWS.values():
            values[indicator] = _metric_from_indicators(tables.indicators_df, indicator, competencia)
        return {
            "status": "OK",
            "cache_status": cache_status,
            "competencia": competencia,
            "values": values,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": f"{exc.__class__.__name__}: {exc}", "cache_status": "erro", "values": {}}


def _metric_from_indicators(indicators_df: pd.DataFrame, indicator: str, competencia: str) -> str:
    if indicators_df.empty or competencia not in indicators_df.columns:
        return "—"
    match = indicators_df[indicators_df["indicador"].astype(str).eq(indicator)]
    if match.empty:
        return "—"
    row = match.iloc[0]
    return _format_live_metric(row.get(competencia), row.get("unidade"))


def _format_live_metric(value: object, unit: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _display(value)
    unit_text = str(unit or "")
    if "R$ bruto" in unit_text:
        return f"R$ {_br_number(numeric / 1_000_000, 0)} mm"
    if "R$ MM" in unit_text:
        return f"R$ {_br_number(numeric, 0)} mm"
    if unit_text in {"ratio", "%"} or "/" in unit_text:
        if unit_text == "ratio":
            numeric *= 100
        return f"{_br_number(numeric, 1)}%"
    return _br_number(numeric, 1)


def _competencia_sort_key(value: object) -> tuple[int, int]:
    text = str(value or "")
    try:
        month, year = text.split("/", 1)
        return int(year), int(month)
    except Exception:  # noqa: BLE001
        return (0, 0)


def _latest_competencia_month(competencias: list[str] | tuple[str, ...]) -> date | None:
    parsed = []
    for competencia in competencias or []:
        year, month = _competencia_sort_key(competencia)
        if year > 0 and month > 0:
            parsed.append(date(year, month, 1))
    return max(parsed) if parsed else None


def _display(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return "—"
    return text


def _br_number(value: float, decimals: int) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _format_cnpj(value: object) -> str:
    digits = _digits(value)
    if len(digits) != 14:
        return str(value or "")
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _short_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    replacements = [
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
        "FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS",
        "RESPONSABILIDADE LIMITADA",
        "RESP LIMITADAL",
        "RESP LIMITADA",
        "LIMITADA",
    ]
    for token in replacements:
        text = re.sub(token, "", text, flags=re.IGNORECASE).strip(" -")
    return text or str(value or "")


def _source_files_df(manifest: Any) -> pd.DataFrame:
    rows = [
        {
            "Tabela": table.title,
            "Arquivo": str(Path(table.source_file)),
            "Tipo": table.kind,
        }
        for table in manifest.tables
    ]
    return pd.DataFrame(rows)


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip().lower())
    return token.strip("_") or "deep_dive"
