"""ANBIMA rankings and annex views consumed from the published shared payload."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

ORANGE = "#FF6200"
SECTOR_COLORS = {"Financeiro": "#12151A", "Agro, Indústria e Comércio": ORANGE,
                 "Fomento Mercantil": "#8D9399", "Outros": "#BEC2C5", "FIC-FIDC": "#73787D", "N/D": "#D7DADD"}


def number(value, places=1):
    if value is None or pd.isna(value):
        return "N/D"
    return f"{float(value):,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def ranking_chart(frame: pd.DataFrame, role: str):
    rows = frame[frame.role.eq(role)].sort_values("rank").head(8).copy()
    ibba = frame[frame.role.eq(role) & frame.participant.eq("ITAU BBA")]
    if not ibba.empty and "ITAU BBA" not in set(rows.participant):
        rows = pd.concat([rows, ibba]).sort_values("rank")
    rows["R$ bi"] = rows.volume_brl / 1e9
    rows["Casa"] = rows.participant
    chart = alt.Chart(rows).mark_bar().encode(
        x=alt.X("R$ bi:Q", title="Volume creditado · R$ bi"),
        y=alt.Y("Casa:N", sort=rows.Casa.tolist(), title=None),
        color=alt.condition(alt.datum.Casa == "ITAU BBA", alt.value(ORANGE), alt.value("#73787D")),
        tooltip=["Casa:N", alt.Tooltip("rank:Q", title="Posição", format=".0f"),
                 alt.Tooltip("R$ bi:Q", format=",.2f"), alt.Tooltip("share:Q", title="Participação", format=".2%")],
    ).properties(height=310, title=role)
    return chart


def render_anbima_analysis(payload: dict) -> None:
    data = payload.get("anbima_analysis") or {}
    if not data:
        return
    meta = data["comparison_meta"]
    period = meta["period_label"]
    st.markdown("## ANBIMA / IBBA · emissões e coordenação")
    st.caption(f"Ranking de Renda Fixa e Híbridos · {period} · fontes consultadas em {data['source_as_of_date']}. Valores creditados por participante conforme o papel.")
    positions = pd.DataFrame(data["ibba_positions"])
    fidc = positions[positions.scope.eq("FIDC")].set_index("role")
    summary = data["fidc_summary"]
    cols = st.columns(4)
    cols[0].metric("FIDC · originação ANBIMA", f"R$ {number(summary['volume_brl']/1e9)} bi")
    cols[1].metric("Registros de FIDC no anexo", str(summary["registrations"]))
    cols[2].metric("IBBA · originação FIDC", number(fidc.loc["Originação", "share"]*100)+"%")
    cols[3].metric("IBBA · distribuição FIDC", number(fidc.loc["Distribuição", "share"]*100)+"%")
    market_tab, ranking_tab, sector_tab, top_market_tab = st.tabs(["Mercado e produtos ANBIMA", "IBBA e rankings ANBIMA", "Setores e Top 15 FIDC", "Top 15 ANBIMA · mercado"])
    with market_tab:
        products = pd.DataFrame(data["products"])
        products["R$ bi"] = products.volume_brl / 1e9
        st.markdown("### Produtos no anexo de originação")
        st.altair_chart(alt.Chart(products).mark_bar(color=ORANGE).encode(
            x=alt.X("R$ bi:Q"), y=alt.Y("classe_label:N", title=None, sort="-x"),
            tooltip=[alt.Tooltip("classe_label:N", title="Instrumento"), alt.Tooltip("R$ bi:Q", format=",.2f"), alt.Tooltip("share:Q", format=".2%")],
        ).properties(height=370), width="stretch", key="industry-anbima-products")
        st.caption("Anexo de originação, Tipos 1 e 2; empresas ligadas (Tipo 3) ficam em recorte próprio. O universo do ranking depende das operações informadas e das regras de crédito da ANBIMA.")
    with ranking_tab:
        window_label = st.selectbox("Janela do ranking ANBIMA", ["Acumulado no ano", "Últimos 12 meses"], key="industry-anbima-window")
        window = {"Acumulado no ano":"acumulado_ano", "Últimos 12 meses":"ultimos_12_meses"}[window_label]
        st.caption(f"Janela: {data['windows'][window]['label']} · {data['windows'][window]['start']} a {data['windows'][window]['end']}.")
        all_positions = pd.DataFrame(data["ibba_positions_all"])
        current_positions = all_positions[all_positions.window.eq(window)]
        st.markdown("### Posição do Itaú BBA por recorte")
        shown = current_positions[current_positions.ranking_code.isin(["1", "1.3", "1.3.1", "2", "3"])].copy()
        shown["R$ bi"] = shown.volume_brl.map(lambda value: number(value/1e9) if pd.notna(value) else "N/D")
        shown["Participação"] = shown.share.map(lambda value: number(value*100)+"%" if pd.notna(value) else "N/D")
        shown["Posição"] = shown["rank"].map(lambda value: str(int(value)) if pd.notna(value) else "N/D")
        st.dataframe(shown[["scope", "role", "Posição", "R$ bi", "Participação", "status"]].rename(columns={"scope":"Recorte", "role":"Papel", "status":"Situação"}), hide_index=True, width="stretch")
        st.caption("Recortes sobrepostos: FIDC integra securitização e renda fixa. As linhas não devem ser somadas. A distribuição de empresas ligadas não é publicada neste ranking.")
        ranking = pd.DataFrame(data["ranking_all"])
        ranking = ranking[ranking.window.eq(window)]
        primary = ["FIDC", "Renda fixa", "Securitização", "Híbridos", "Empresas ligadas"]
        scope = st.selectbox("Recorte do ranking ANBIMA", primary + sorted(set(ranking.scope)-set(primary)), key="industry-anbima-ranking-scope")
        selected = ranking[ranking.scope.eq(scope)]
        for column, role in zip(st.columns(2), ["Originação", "Distribuição"]):
            with column:
                if selected[selected.role.eq(role)].empty:
                    st.info(f"{role}: ranking não publicado para este recorte.")
                else:
                    st.altair_chart(ranking_chart(selected, role), width="stretch", key=f"industry-anbima-ranking-{role}")
        st.markdown("### Visão por produto · posição do IBBA")
        product_positions = current_positions[~current_positions.ranking_code.isin(["1", "1.3", "1.3.1", "2", "3"])].copy()
        product_positions["Volume IBBA · R$ bi"] = product_positions.volume_brl.map(lambda value: number(value/1e9,2) if pd.notna(value) else "N/D")
        product_positions["Mercado · R$ bi"] = product_positions.universe_volume_brl.map(lambda value: number(value/1e9,2) if pd.notna(value) else "N/D")
        product_positions["IBBA · %"] = product_positions.share.map(lambda value: number(value*100,2)+"%" if pd.notna(value) else "N/D")
        product_positions["Posição"] = product_positions["rank"].map(lambda value: str(int(value)) if pd.notna(value) else "N/D")
        st.dataframe(product_positions[["scope","role","Mercado · R$ bi","Volume IBBA · R$ bi","Posição","IBBA · %","status"]].rename(columns={"scope":"Produto/recorte","role":"Papel","status":"Situação"}), hide_index=True, width="stretch")
        st.caption("As duas janelas usam os valores oficiais do ranking. O anexo de encerramento corrente cobre o acumulado do ano; ele não reconstrói os últimos 12 meses.")
    with sector_tab:
        st.markdown("### Emissões por Setor · ANBIMA")
        sectors = pd.DataFrame(data["fidc_sectors"])
        sectors["R$ bi"] = sectors.volume_brl / 1e9
        order = sectors.category.tolist()
        color = alt.Color("category:N", title="Setor", scale=alt.Scale(domain=list(SECTOR_COLORS), range=list(SECTOR_COLORS.values())), legend=None)
        for column, metric, title in zip(st.columns(2), ["R$ bi", "share"], ["Emissões por Setor · R$ bi", "Emissões por Setor · % do Total"]):
            with column:
                st.altair_chart(alt.Chart(sectors).mark_bar().encode(
                    x=alt.X(f"{metric}:Q", title="R$ bi" if metric=="R$ bi" else "% do Total", axis=alt.Axis(format=",.1f" if metric=="R$ bi" else ".1%")),
                    y=alt.Y("category:N", title=None, sort=order), color=color,
                    tooltip=[alt.Tooltip("category:N",title="Setor"), alt.Tooltip("R$ bi:Q",format=",.3f"),alt.Tooltip("share:Q",format=".2%")],
                ).properties(height=265,title=title), width="stretch", key=f"industry-anbima-sector-{metric}")
        st.caption(f"Denominador: R$ {number(summary['volume_brl']/1e9,2)} bi do anexo de originação FIDC, Tipo 1. Taxonomia oficial/analítica do estudo associada por CNPJ; cobertura de classificação: {number(summary['classification_volume_coverage']*100,2)}%. FIC-FIDC e N/D, quando presentes, integram o total.")
        top = pd.DataFrame(data["fidc_top15"])
        st.markdown(f"### Top 15 emissões de FIDC · ANBIMA · {period}")
        top["R$ bi"] = top.volume_brl.map(lambda value: number(value/1e9,3))
        top["IBBA na originação"] = top.ibba_participant.map({True:"Sim",False:"Não"})
        top["Crédito IBBA · R$ bi"] = top.ibba_volume_brl.map(lambda value: number(value/1e9,3))
        st.dataframe(top[["rank","emissor","registro_cvm","data_encerramento","R$ bi","IBBA na originação","Crédito IBBA · R$ bi","category"]].rename(columns={"rank":"#","emissor":"Emissor","registro_cvm":"Registro CVM","data_encerramento":"Último encerramento","category":"Setor"}), hide_index=True, width="stretch", height=610)
        st.caption(f"Subtotal Top 15: R$ {number(summary['top15_volume_brl']/1e9,2)} bi; {number(summary['top15_share']*100,1)}% do universo. IBBA participa da originação de {summary['top15_ibba_registrations']} registros. Um registro pode conter mais de uma classe ou encerramento no anexo.")
    with top_market_tab:
        st.markdown(f"### Top 15 emissões · renda fixa e híbridos · {period}")
        market = data["market_summary"]
        top = pd.DataFrame(data["market_top15"])
        top["R$ bi"] = top.volume_brl.map(lambda value: number(value/1e9,3))
        top["IBBA na originação"] = top.ibba_participant.map({True:"Sim",False:"Não"})
        top["Crédito IBBA · R$ bi"] = top.ibba_volume_brl.map(lambda value: number(value/1e9,3))
        st.dataframe(top[["rank","emissor","products","data_encerramento","R$ bi","IBBA na originação","Crédito IBBA · R$ bi","registros_cvm"]].rename(columns={"rank":"#","emissor":"Emissor","products":"Produto","data_encerramento":"Encerramento","registros_cvm":"Registros CVM"}), hide_index=True, width="stretch", height=610)
        st.caption(f"Subtotal Top 15: R$ {number(market['top15_volume_brl']/1e9,2)} bi; {number(market['top15_share']*100,1)}% dos R$ {number(market['volume_brl']/1e9,2)} bi do anexo de originação, Tipos 1 e 2. IBBA participa de {market['top15_ibba_operations']} operações. Unidade: emissor e data de encerramento, com todos os registros vinculados preservados. Empresas ligadas ficam fora deste total.")
    with st.expander("Fontes e regras · ANBIMA", expanded=False):
        for note in data["notes"]:
            st.caption(note)
        sources = data.get("sources") or {}
        for kind, title in [("ranking_workbook", "Ranking oficial"), ("annex_workbook", "Anexo de encerramento")]:
            url = sources.get(kind,{}).get("url")
            if url: st.markdown(f"[{title}]({url})")
        for key, label in [("ranking_all","Ranking ANBIMA · CSV"),("fidc_deals","Emissões FIDC ANBIMA · CSV"),("fidc_sectors","Setores ANBIMA · CSV"),("market_operations","Operações de renda fixa e híbridos · CSV")]:
            st.download_button(label,pd.DataFrame(data[key]).to_csv(index=False,sep=";",decimal=",").encode("utf-8-sig"),file_name=f"ANBIMA_{key}_{data['source_reference_competence'].replace('-','')}.csv",mime="text/csv",key=f"industry-anbima-download-{key}")
