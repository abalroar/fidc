from __future__ import annotations

import pandas as pd


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_pct(numerator: object, denominator: object) -> float | None:
    num = _float_or_none(numerator)
    den = _float_or_none(denominator)
    if num is None or den is None or den <= 0:
        return None
    return float(num / den * 100.0)


def _event_lookup_value(event_summary_latest_df: pd.DataFrame, event_type: str, field: str) -> float | None:
    if event_summary_latest_df.empty or field not in event_summary_latest_df.columns:
        return None
    matches = event_summary_latest_df[event_summary_latest_df["event_type"] == event_type]
    if matches.empty:
        return None
    return _float_or_none(matches.iloc[0].get(field))


def _latest_top_segment(segment_latest_df: pd.DataFrame) -> tuple[str | None, float | None]:
    if segment_latest_df.empty:
        return None, None
    ordered = segment_latest_df.sort_values("valor", ascending=False)
    row = ordered.iloc[0]
    return str(row.get("segmento") or "").strip() or None, _float_or_none(row.get("percentual"))


def _latest_row_value(df: pd.DataFrame, column: str) -> float | None:
    if df.empty or column not in df.columns:
        return None
    ordered = df.sort_values("competencia_dt")
    return _float_or_none(ordered.iloc[-1].get(column))


def _metric_row(
    *,
    risk_block: str,
    risk_block_order: int,
    metric_id: str,
    label: str,
    value: object,
    unit: str,
    criticality: str,
    source_data: str,
    transformation: str,
    final_variable: str,
    formula: str,
    pipeline: str,
    interpretation: str,
    limitation: str,
    state: str,
) -> dict[str, object]:
    return {
        "risk_block": risk_block,
        "risk_block_order": risk_block_order,
        "metric_id": metric_id,
        "label": label,
        "value": _float_or_none(value),
        "unit": unit,
        "criticality": criticality,
        "source_data": source_data,
        "transformation": transformation,
        "final_variable": final_variable,
        "formula": formula,
        "pipeline": pipeline,
        "interpretation": interpretation,
        "limitation": limitation,
        "state": state,
    }


def build_risk_metrics_df(
    *,
    latest_competencia: str,
    summary: dict[str, float | str | None],
    asset_history_df: pd.DataFrame,
    segment_latest_df: pd.DataFrame,
    subordination_history_df: pd.DataFrame,
    default_history_df: pd.DataFrame,
    event_summary_latest_df: pd.DataFrame,
) -> pd.DataFrame:
    del latest_competencia
    top_segment_label, top_segment_pct = _latest_top_segment(segment_latest_df)
    direitos_creditorios_monitoramento = _float_or_none(summary.get("inadimplencia_denominador"))
    if direitos_creditorios_monitoramento is None or direitos_creditorios_monitoramento <= 0:
        direitos_creditorios_monitoramento = _float_or_none(summary.get("direitos_creditorios"))
    del asset_history_df
    del subordination_history_df
    del default_history_df
    del event_summary_latest_df

    rows = [
        _metric_row(
            risk_block="Risco de crédito",
            risk_block_order=1,
            metric_id="inadimplencia_pct",
            label="Inadimplência / direitos creditórios",
            value=summary.get("inadimplencia_pct"),
            unit="%",
            criticality="critico",
            source_data="COMPMT_DICRED + APLIC_ATIVO",
            transformation="Usa vencidos reportados na malha de prazo; se a linha de vencidos vier vazia, cai para o aging de inadimplência.",
            final_variable="summary['inadimplencia_pct']",
            formula="inadimplencia_total / dc_total_reportado_por_vencimento * 100",
            pipeline="Informe Mensal -> _build_default_history -> default_history_df.[inadimplencia_total, direitos_creditorios] -> _build_summary -> summary['inadimplencia_pct']",
            interpretation="Mostra o peso dos créditos vencidos dentro do total de direitos creditórios reportado na mesma malha de vencimento.",
            limitation="Depende do preenchimento consistente dos quadros de vencidos e prazo pelo administrador; não substitui perda esperada nem leitura por devedor.",
            state="calculado" if summary.get("inadimplencia_pct") is not None else "nao_calculavel",
        ),
        _metric_row(
            risk_block="Risco de crédito",
            risk_block_order=1,
            metric_id="provisao_pct_direitos",
            label="Provisão / direitos creditórios",
            value=_safe_pct(summary.get("provisao_total"), direitos_creditorios_monitoramento),
            unit="%",
            criticality="monitorar",
            source_data="APLIC_ATIVO + COMPMT_DICRED",
            transformation="Soma da provisão reportada em _build_default_history.",
            final_variable="tracking_latest_df['Provisão / direitos creditórios']",
            formula="provisao_total / dc_total_reportado_por_vencimento * 100",
            pipeline="Informe Mensal -> _build_default_history -> default_history_df.provisao_total -> build_risk_metrics_df",
            interpretation="Mostra quanto da carteira está coberto por provisão contábil reportada.",
            limitation="Depende da política contábil do fundo e não equivale a perda econômica realizada.",
            state="calculado" if _safe_pct(summary.get('provisao_total'), direitos_creditorios_monitoramento) is not None else "nao_calculavel",
        ),
        _metric_row(
            risk_block="Risco de crédito",
            risk_block_order=1,
            metric_id="provisao_pct_inadimplencia",
            label="Provisão / inadimplência",
            value=_safe_pct(summary.get("provisao_total"), summary.get("inadimplencia_total")),
            unit="%",
            criticality="monitorar",
            source_data="APLIC_ATIVO/CRED_EXISTE + APLIC_ATIVO/DICRED",
            transformation="Relação entre provisão reportada e saldos inadimplentes.",
            final_variable="tracking_latest_df['Provisão / inadimplência']",
            formula="provisao_total / inadimplencia_total * 100",
            pipeline="Informe Mensal -> _build_default_history -> default_history_df.[provisao_total, inadimplencia_total] -> build_risk_metrics_df",
            interpretation="Mostra o quanto a inadimplência reportada está provisionada.",
            limitation="Sem inadimplência reportada a métrica não se aplica; também não captura recompras ou resolução de cessão.",
            state=(
                "calculado"
                if _safe_pct(summary.get("provisao_total"), summary.get("inadimplencia_total")) is not None
                else "nao_aplicavel_sem_inadimplencia"
            ),
        ),
        _metric_row(
            risk_block="Risco de crédito",
            risk_block_order=1,
            metric_id="concentracao_segmento_proxy",
            label=f"Concentração setorial proxy ({top_segment_label or 'N/D'})",
            value=top_segment_pct,
            unit="%",
            criticality="monitorar",
            source_data="CART_SEGMT",
            transformation="Seleciona o maior percentual do quadro setorial da CVM.",
            final_variable="segment_latest_df.iloc[0]['percentual']",
            formula="max(percentual_setorial)",
            pipeline="Informe Mensal -> _build_segment_latest_df -> segment_latest_df.percentual -> build_risk_metrics_df",
            interpretation="Sinal rápido de concentração da carteira pelo maior segmento reportado.",
            limitation="Não é concentração por devedor, cedente ou sacado; serve apenas como sinal preliminar.",
            state="calculado" if top_segment_pct is not None else "nao_disponivel_na_fonte",
        ),
        _metric_row(
            risk_block="Risco estrutural",
            risk_block_order=2,
            metric_id="subordinacao_pct",
            label="Índice de subordinação",
            value=summary.get("subordinacao_pct"),
            unit="%",
            criticality="critico",
            source_data="OUTRAS_INFORM/DESC_SERIE_CLASSE",
            transformation="Calcula PL subordinado e PL total a partir de qt. de cotas * valor da cota.",
            final_variable="summary['subordinacao_pct']",
            formula="pl_subordinada / pl_total * 100",
            pipeline="Informe Mensal -> _build_quota_pl_history -> _build_subordination_history -> _build_summary",
            interpretation="Mostra o colchão subordinado disponível antes da classe sênior.",
            limitation="Não substitui covenants contratuais de cobertura, overcollateral ou subordinação mínima documental.",
            state="calculado" if summary.get("subordinacao_pct") is not None else "nao_calculavel",
        ),
        _metric_row(
            risk_block="Risco estrutural",
            risk_block_order=2,
            metric_id="pl_subordinada",
            label="PL subordinado",
            value=summary.get("pl_subordinada"),
            unit="R$",
            criticality="monitorar",
            source_data="OUTRAS_INFORM/DESC_SERIE_CLASSE",
            transformation="Soma o PL das classes subordinadas a partir de qt. de cotas * valor da cota.",
            final_variable="summary['pl_subordinada']",
            formula="Σ(qt_cotas_subordinadas * valor_cota_subordinada)",
            pipeline="Informe Mensal -> _build_quota_pl_history -> _build_subordination_history -> _build_summary",
            interpretation="Mostra o volume nominal do colchão subordinado reportado.",
            limitation="Não capta sozinha reforços estruturais extras como reservas, cobertura ou spread excedente.",
            state="calculado" if summary.get("pl_subordinada") is not None else "nao_calculavel",
        ),
    ]
    return pd.DataFrame(rows).sort_values(["risk_block_order", "criticality", "label"]).reset_index(drop=True)


def build_coverage_gap_df() -> pd.DataFrame:
    rows = [
        {
            "tema": "Índice de cobertura",
            "status": "Exige fonte complementar",
            "por_que_importa": "Ajuda a avaliar proteção econômica da classe sênior além da subordinação nominal.",
            "fonte_necessaria": "Regulamento + relatório mensal/monitoramento",
        },
        {
            "tema": "Relação mínima e covenants equivalentes",
            "status": "Exige fonte complementar",
            "por_que_importa": "Pode antecipar eventos de avaliação e deterioração estrutural.",
            "fonte_necessaria": "Regulamento + relatório mensal/monitoramento",
        },
        {
            "tema": "Reservas e excesso de spread",
            "status": "Exige fonte complementar",
            "por_que_importa": "São amortecedores relevantes para cotas seniores e não aparecem de forma padronizada no Informe Mensal.",
            "fonte_necessaria": "Regulamento + relatório mensal/monitoramento",
        },
        {
            "tema": "Cedente, originador, devedor e coobrigação",
            "status": "Exige fonte complementar",
            "por_que_importa": "São determinantes do risco operacional e da leitura correta do crédito.",
            "fonte_necessaria": "Relatório mensal + regulamento + documentos de oferta",
        },
        {
            "tema": "Eventos de avaliação e liquidação antecipada",
            "status": "Exige fonte complementar",
            "por_que_importa": "O Informe Mensal não reconstrói sozinho a malha de gatilhos contratuais da estrutura.",
            "fonte_necessaria": "Regulamento + fatos relevantes + assembleias",
        },
        {
            "tema": "Rating e público-alvo",
            "status": "Exige fonte complementar",
            "por_que_importa": "Importa para a leitura da tranche e da oferta, mas não deve ser inferido do Informe Mensal.",
            "fonte_necessaria": "Documentos de oferta + relatórios de rating + regulamento",
        },
        {
            "tema": "Verificação de lastro",
            "status": "Exige fonte complementar",
            "por_que_importa": "Afeta risco operacional e qualidade da carteira além do que o Informe Mensal mostra.",
            "fonte_necessaria": "Regulamento + ofícios CVM + relatórios operacionais",
        },
    ]
    return pd.DataFrame(rows)


def build_mini_glossary_df() -> pd.DataFrame:
    rows = [
        {
            "termo": "Subordinação",
            "definicao_curta": "Colchão de capital subordinado que absorve perdas antes da classe sênior.",
            "variacao_importante": "Não substitui cobertura, reservas ou covenants contratuais.",
        },
        {
            "termo": "Inadimplência reportada",
            "definicao_curta": "Saldos vencidos inadimplentes reportados no Informe Mensal da CVM.",
            "variacao_importante": "Não equivale automaticamente a perda esperada nem a política contábil do fundo.",
        },
        {
            "termo": "Informe Mensal",
            "definicao_curta": "Documento periódico da CVM usado aqui como base padronizada de acompanhamento.",
            "variacao_importante": "Nem todo risco estrutural relevante aparece nele; regulamento e relatório mensal seguem necessários.",
        },
        {
            "termo": "Resgate solicitado",
            "definicao_curta": "Pressão de saída já pedida por cotistas, ainda não necessariamente paga.",
            "variacao_importante": "No XML real há divergência entre `VL_PAGO` e `VL_COTAS`; por isso a leitura é operacional, não jurídica.",
        },
    ]
    return pd.DataFrame(rows)


def build_current_dashboard_inventory_df() -> pd.DataFrame:
    rows = [
        {
            "nome_variavel": "summary.direitos_creditorios",
            "nome_exibido": "Direitos creditórios",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral",
            "fonte_dado": "DICRED/VL_DICRED com fallback legado",
            "formula": "_direitos_creditorios_series -> _build_asset_history -> _build_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_direitos_creditorios_series; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "summary.pl_total",
            "nome_exibido": "PL total",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral",
            "fonte_dado": "DESC_SERIE_CLASSE",
            "formula": "_build_quota_pl_history -> _build_subordination_history -> _build_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_build_subordination_history; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "summary.subordinacao_pct",
            "nome_exibido": "Subordinação",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Cotas",
            "fonte_dado": "DESC_SERIE_CLASSE",
            "formula": "pl_subordinada / pl_total * 100",
            "arquivo_py": "services/fundonet_dashboard.py:_build_subordination_history; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "percentual",
            "unidade": "%",
        },
        {
            "nome_variavel": "summary.inadimplencia_pct",
            "nome_exibido": "Inadimplência",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Inadimplência",
            "fonte_dado": "COMPMT_DICRED + aging de inadimplência",
            "formula": "inadimplencia_total / dc_total_reportado_por_vencimento * 100",
            "arquivo_py": "services/fundonet_dashboard.py:_build_default_history; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "percentual",
            "unidade": "%",
        },
        {
            "nome_variavel": "summary.alocacao_pct",
            "nome_exibido": "Alocação",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Ativo e carteira",
            "fonte_dado": "VL_CARTEIRA + DICRED/VL_DICRED",
            "formula": "direitos_creditorios / carteira * 100",
            "arquivo_py": "services/fundonet_dashboard.py:_build_asset_history; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "percentual",
            "unidade": "%",
        },
        {
            "nome_variavel": "summary.provisao_total",
            "nome_exibido": "Provisão",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Inadimplência",
            "fonte_dado": "APLIC_ATIVO/CRED_EXISTE + APLIC_ATIVO/DICRED",
            "formula": "_build_default_history -> _build_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_build_default_history; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "summary.liquidez_imediata",
            "nome_exibido": "Liquidez imediata",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Ativo e carteira",
            "fonte_dado": "OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ",
            "formula": "_latest_path_value -> _build_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_build_summary; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "summary.liquidez_30",
            "nome_exibido": "Liquidez até 30 dias",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Ativo e carteira",
            "fonte_dado": "OUTRAS_INFORM/LIQUIDEZ/VL_ATIV_LIQDEZ_30",
            "formula": "_latest_path_value -> _build_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_build_summary; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "summary.resgate_solicitado_mes",
            "nome_exibido": "Resgate solicitado",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Visão geral / Liquidez",
            "fonte_dado": "CAPTA_RESGA_AMORTI/RESG_SOLIC",
            "formula": "_sum_latest_path_groups_with_status(VL_PAGO|VL_COTAS)",
            "arquivo_py": "services/fundonet_dashboard.py:_build_summary; tabs/tab_fidc_ime.py:_render_overview_metrics",
            "tipo": "monetaria",
            "unidade": "R$",
        },
        {
            "nome_variavel": "tracking_latest_df.*",
            "nome_exibido": "Tabela Indicadores calculados",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Monitoramento estrutural",
            "fonte_dado": "Resumo + asset_history + wide_lookup",
            "formula": "_build_tracking_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_tracking_latest_df; tabs/tab_fidc_ime.py:_render_monitoring_section",
            "tipo": "tabela_derivada",
            "unidade": "mista",
        },
        {
            "nome_variavel": "event_summary_latest_df.*",
            "nome_exibido": "Resumo dos eventos",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Monitoramento estrutural / Eventos",
            "fonte_dado": "CAPTA_RESGA_AMORTI",
            "formula": "_build_event_summary_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_event_summary_latest_df; tabs/tab_fidc_ime.py:_render_events_section",
            "tipo": "tabela_evento",
            "unidade": "mista",
        },
        {
            "nome_variavel": "asset_history_df.ativos_totais|carteira|direitos_creditorios",
            "nome_exibido": "Evolução do Ativo",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira",
            "fonte_dado": "APLIC_ATIVO + DICRED",
            "formula": "_build_asset_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_asset_history; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "serie_historica",
            "unidade": "R$",
        },
        {
            "nome_variavel": "composition_latest_df.*",
            "nome_exibido": "Composição do Ativo",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira",
            "fonte_dado": "APLIC_ATIVO",
            "formula": "_build_composition_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_composition_latest_df; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "composicao",
            "unidade": "R$ e %",
        },
        {
            "nome_variavel": "segment_latest_df.*",
            "nome_exibido": "Carteira por segmento",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira",
            "fonte_dado": "CART_SEGMT",
            "formula": "_build_segment_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_segment_latest_df; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "composicao",
            "unidade": "R$ e %",
        },
        {
            "nome_variavel": "liquidity_latest_df.*",
            "nome_exibido": "Liquidez reportada",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira / Tabelas CVM",
            "fonte_dado": "OUTRAS_INFORM/LIQUIDEZ",
            "formula": "_build_liquidity_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_liquidity_latest_df; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "bucket",
            "unidade": "R$",
        },
        {
            "nome_variavel": "maturity_latest_df.*",
            "nome_exibido": "Prazo de vencimento dos direitos creditórios",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira",
            "fonte_dado": "COMPMT_DICRED_AQUIS + COMPMT_DICRED_SEM_AQUIS",
            "formula": "_build_maturity_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_maturity_latest_df; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "bucket",
            "unidade": "R$",
        },
        {
            "nome_variavel": "asset_history_df.aquisicoes|alienacoes",
            "nome_exibido": "Fluxo dos direitos creditórios",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Ativo e carteira",
            "fonte_dado": "NEGOC_DICRED_MES",
            "formula": "_build_asset_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_asset_history; tabs/tab_fidc_ime.py:_render_asset_section",
            "tipo": "serie_historica",
            "unidade": "R$",
        },
        {
            "nome_variavel": "default_history_df.inadimplencia_total|provisao_total|pendencia_total",
            "nome_exibido": "Saldos de crédito problemático",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Inadimplência",
            "fonte_dado": "APLIC_ATIVO/CRED_EXISTE + APLIC_ATIVO/DICRED",
            "formula": "_build_default_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_default_history; tabs/tab_fidc_ime.py:_render_default_section",
            "tipo": "serie_historica",
            "unidade": "R$",
        },
        {
            "nome_variavel": "default_history_df.inadimplencia_pct",
            "nome_exibido": "Inadimplência relativa",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Inadimplência",
            "fonte_dado": "APLIC_ATIVO/CRED_EXISTE + APLIC_ATIVO/DICRED",
            "formula": "inadimplencia_total / direitos_creditorios * 100",
            "arquivo_py": "services/fundonet_dashboard.py:_build_default_history; tabs/tab_fidc_ime.py:_render_default_section",
            "tipo": "percentual",
            "unidade": "%",
        },
        {
            "nome_variavel": "default_buckets_latest_df.*",
            "nome_exibido": "Aging da inadimplência",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Inadimplência",
            "fonte_dado": "COMPMT_DICRED_AQUIS + COMPMT_DICRED_SEM_AQUIS",
            "formula": "_build_default_buckets_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_default_buckets_latest_df; tabs/tab_fidc_ime.py:_render_default_section",
            "tipo": "bucket",
            "unidade": "R$",
        },
        {
            "nome_variavel": "quota_pl_history_df.*",
            "nome_exibido": "Patrimônio líquido das cotas",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Cotas, PL e remuneração",
            "fonte_dado": "OUTRAS_INFORM/DESC_SERIE_CLASSE",
            "formula": "_build_quota_pl_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_quota_pl_history; tabs/tab_fidc_ime.py:_render_quota_section",
            "tipo": "serie_historica",
            "unidade": "R$",
        },
        {
            "nome_variavel": "return_history_df.retorno_mensal_pct",
            "nome_exibido": "Rentabilidade mensal das cotas",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Cotas, PL e remuneração",
            "fonte_dado": "OUTRAS_INFORM/RENT_MES",
            "formula": "_build_return_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_return_history; tabs/tab_fidc_ime.py:_render_quota_section",
            "tipo": "serie_historica",
            "unidade": "%",
        },
        {
            "nome_variavel": "return_summary_df.*",
            "nome_exibido": "Resumo de rentabilidade",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Cotas, PL e remuneração",
            "fonte_dado": "OUTRAS_INFORM/RENT_MES",
            "formula": "_build_return_summary",
            "arquivo_py": "services/fundonet_dashboard.py:_build_return_summary; tabs/tab_fidc_ime.py:_render_quota_section",
            "tipo": "tabela_derivada",
            "unidade": "%",
        },
        {
            "nome_variavel": "performance_vs_benchmark_latest_df.*",
            "nome_exibido": "Benchmark x realizado",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Cotas, PL e remuneração",
            "fonte_dado": "OUTRAS_INFORM/DESEMP",
            "formula": "_build_performance_vs_benchmark_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_performance_vs_benchmark_latest_df; tabs/tab_fidc_ime.py:_render_quota_section",
            "tipo": "tabela_derivada",
            "unidade": "% e bps",
        },
        {
            "nome_variavel": "event_history_df.*",
            "nome_exibido": "Eventos de cotas por competência",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Emissões, resgates e amortizações",
            "fonte_dado": "CAPTA_RESGA_AMORTI",
            "formula": "_build_event_history + _decorate_event_history",
            "arquivo_py": "services/fundonet_dashboard.py:_build_event_history; tabs/tab_fidc_ime.py:_render_events_section",
            "tipo": "serie_historica",
            "unidade": "R$ e %",
        },
        {
            "nome_variavel": "holder_latest_df.*",
            "nome_exibido": "Cotistas",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Tabelas CVM",
            "fonte_dado": "NUM_COTISTAS",
            "formula": "_build_holder_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_holder_latest_df; tabs/tab_fidc_ime.py:_render_cvm_tables_section",
            "tipo": "tabela",
            "unidade": "quantidade",
        },
        {
            "nome_variavel": "rate_negotiation_latest_df.*",
            "nome_exibido": "Taxas de negociação de direitos creditórios",
            "aba_origem": "tomaconta FIDCs",
            "bloco_ui_atual": "Tabelas CVM",
            "fonte_dado": "TAXA_NEGOC_DICRED_MES",
            "formula": "_build_rate_negotiation_latest_df",
            "arquivo_py": "services/fundonet_dashboard.py:_build_rate_negotiation_latest_df; tabs/tab_fidc_ime.py:_render_cvm_tables_section",
            "tipo": "tabela",
            "unidade": "%",
        },
    ]
    return pd.DataFrame(rows)
