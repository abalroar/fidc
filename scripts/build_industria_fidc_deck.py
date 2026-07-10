"""Gera o entregável executivo da Indústria de FIDCs.

Produz, a partir das bases já materializadas em ``data/industry_study`` (derivadas
do Informe Mensal FIDC + Cadastro da CVM, dados abertos), dois artefatos:

1. ``outputs/Industria_FIDC_<competencia>.xlsx``
   Planilha com GRÁFICOS NATIVOS do Office (openpyxl) — editáveis no Excel — e as
   abas de dados/metodologia que os alimentam.

2. ``outputs/Industria_FIDC_<competencia>.pptx``
   Apresentação executiva, simples, com GRÁFICOS NATIVOS do Office (python-pptx),
   inspirada no layout de decks de mercado (barras + tabelas Top N).

Uso:
    python scripts/build_industria_fidc_deck.py
    python scripts/build_industria_fidc_deck.py --industry-dir data/industry_study --out outputs
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paleta executiva (navy + laranja), próxima do estilo dos slides de referência
# ---------------------------------------------------------------------------
NAVY = "1F2A44"
NAVY_SOFT = "34405C"
ORANGE = "E8703A"
ORANGE_SOFT = "F4A97F"
GRAY = "8A94A6"
GRAY_LIGHT = "D9DEE7"
WHITE = "FFFFFF"
INK = "1A1A1A"

SEGMENT_COLORS = [ORANGE, NAVY, "5B7DB1", GRAY, ORANGE_SOFT, "9AA7BF", "C0703A", "6E7B94", GRAY_LIGHT, "B5C2D6"]

BANCO_KEYWORDS = (
    "BANCO", "BB ", "BRADESCO", "ITAU", "ITAÚ", "SANTANDER", "CAIXA", "BTG",
    "SAFRA", "DAYCOVAL", "PAN", "VOTORANTIM", "BV ", "XP ", "GENIAL", "INTER",
    "C6", "ABC BRASIL", "PINE", "BMG", "MODAL", "ORIGINAL", "SICOOB", "SICREDI",
    "BNP", "CITI", "JPMORGAN", "MASTER",
)


# ---------------------------------------------------------------------------
# Camada de dados
# ---------------------------------------------------------------------------
def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def load_datasets(industry_dir: Path) -> dict:
    snap = pd.read_csv(industry_dir / "industry_fund_snapshot.csv.gz")
    snap["pl"] = _num(snap["pl"]).fillna(0.0)
    snap["cotistas"] = _num(snap.get("cotistas"))
    admin = pd.read_csv(industry_dir / "admin_monthly.csv")
    admin["pl"] = _num(admin["pl"]).fillna(0.0)
    cot_tipo = pd.read_csv(industry_dir / "cotistas_tipo_monthly.csv")
    cot_tipo["n_cotistas"] = _num(cot_tipo["n_cotistas"]).fillna(0.0)
    return {"snap": snap, "admin": admin, "cot_tipo": cot_tipo}


def competencia_label(snap: pd.DataFrame) -> str:
    comp = str(snap["competencia"].dropna().iloc[0])
    return comp  # 'YYYY-MM'


def _month_complete(admin: pd.DataFrame) -> pd.DataFrame:
    """Remove o último mês se claramente incompleto (defasagem de entrega)."""
    plm = admin.groupby("competencia")["pl"].sum().sort_index()
    if len(plm) >= 2 and plm.iloc[-1] < 0.5 * plm.iloc[-2]:
        plm = plm.iloc[:-1]
    return plm


def evolucao_pl_anual(admin: pd.DataFrame) -> pd.DataFrame:
    """PL de indústria por ano (dezembro de cada ano; último ano = mês mais recente completo)."""
    plm = _month_complete(admin)  # Series index 'YYYY-MM' -> pl
    df = plm.rename("pl").reset_index()
    df["ano"] = df["competencia"].str.slice(0, 4).astype(int)
    # dezembro de cada ano, ou o último mês disponível do ano
    idx = df.groupby("ano")["competencia"].idxmax()
    annual = df.loc[idx].sort_values("ano").reset_index(drop=True)
    annual["pl_bi"] = (annual["pl"] / 1e9).round(0)
    return annual[["ano", "competencia", "pl_bi"]]


def composicao_segmento(snap: pd.DataFrame) -> pd.DataFrame:
    seg = (
        snap.assign(segmento=snap["segmento_principal"].fillna("Não classificado"))
        .groupby("segmento")["pl"].sum().sort_values(ascending=False) / 1e9
    )
    out = seg.rename("pl_bi").reset_index()
    out["share"] = (out["pl_bi"] / out["pl_bi"].sum())
    return out


def ranking_admin(snap: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    a = snap.groupby("admin_nome")["pl"].sum().sort_values(ascending=False) / 1e9
    out = a.rename("pl_bi").reset_index().head(top)
    out.insert(0, "#", range(1, len(out) + 1))
    out["pl_bi"] = out["pl_bi"].round(1)
    return out.rename(columns={"admin_nome": "Administrador"})


def ranking_gestor(snap: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    g = snap.groupby("gestor_nome")["pl"].sum().sort_values(ascending=False) / 1e9
    out = g.rename("pl_bi").reset_index().head(top)
    out.insert(0, "#", range(1, len(out) + 1))
    out["pl_bi"] = out["pl_bi"].round(1)
    return out.rename(columns={"gestor_nome": "Gestor"})


def _is_banco(nome: str) -> bool:
    n = str(nome or "").upper()
    return any(k in n for k in BANCO_KEYWORDS)


def pl_por_tipo_gestor(snap: pd.DataFrame) -> pd.DataFrame:
    """Aproximação heurística Independente vs Ligada a banco (por palavra-chave no nome)."""
    tmp = snap.copy()
    tmp["tipo_gestor"] = np.where(tmp["gestor_nome"].map(_is_banco), "Ligada a banco", "Independente")
    out = tmp.groupby("tipo_gestor")["pl"].sum().sort_values(ascending=False) / 1e9
    res = out.rename("pl_bi").reset_index()
    res["share"] = res["pl_bi"] / res["pl_bi"].sum()
    res["pl_bi"] = res["pl_bi"].round(1)
    return res


def top_fidcs(snap: pd.DataFrame, top: int = 25) -> pd.DataFrame:
    t = snap.sort_values("pl", ascending=False).head(top).copy()
    t["pl_bi"] = (t["pl"] / 1e9).round(2)
    t["segmento"] = t["segmento_principal"].fillna("Não classificado")
    t.insert(0, "#", range(1, len(t) + 1))
    return t[["#", "nome_exibicao", "segmento", "gestor_nome", "pl_bi"]].rename(
        columns={"nome_exibicao": "Fundo", "gestor_nome": "Gestor"}
    )


def cotistas_distribuicao(snap: pd.DataFrame, corte_bi: float = 0.2) -> pd.DataFrame:
    big = snap[snap["pl"] > corte_bi * 1e9].copy()

    def bucket(n):
        if pd.isna(n):
            return "n/d"
        n = int(n)
        if n <= 2:
            return "Até 2 cotistas"
        if n == 3:
            return "3 cotistas"
        if n == 4:
            return "4 cotistas"
        return "5 ou mais"

    order = ["Até 2 cotistas", "3 cotistas", "4 cotistas", "5 ou mais"]
    big["bucket"] = big["cotistas"].map(bucket)
    agg = (
        big[big["bucket"].isin(order)]
        .groupby("bucket")
        .agg(n_fundos=("cnpj_fundo", "count"), pl_bi=("pl", lambda s: s.sum() / 1e9))
        .reindex(order)
        .reset_index()
    )
    agg["pl_bi"] = agg["pl_bi"].round(0)
    meta = {"n_fundos": int(len(big)), "pl_bi": round(big["pl"].sum() / 1e9, 0)}
    return agg, meta


def cotistas_por_segmento_investidor(cot_tipo: pd.DataFrame) -> pd.DataFrame:
    comp = sorted(cot_tipo["competencia"].astype(str).unique())[-1]
    d = cot_tipo[cot_tipo["competencia"].astype(str) == comp]
    out = d.groupby("tipo_cotista")["n_cotistas"].sum().sort_values(ascending=False)
    out = out.rename("n_cotistas").reset_index().head(12)
    return out, comp


# ---------------------------------------------------------------------------
# Excel (gráficos nativos)
# ---------------------------------------------------------------------------
def build_excel(data: dict, comp: str, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference, Series
    from openpyxl.chart.label import DataLabelList
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    snap = data["snap"]
    wb = Workbook()

    title_font = Font(name="Calibri", size=15, bold=True, color=WHITE)
    hdr_font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    navy_fill = PatternFill("solid", fgColor=NAVY)
    orange_fill = PatternFill("solid", fgColor=ORANGE)
    thin = Side(style="thin", color=GRAY_LIGHT)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style_header(ws, row, ncols, fill=navy_fill):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=row, column=c)
            cell.fill = fill
            cell.font = hdr_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

    def banner(ws, text, ncols):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ncols, 3))
        c = ws.cell(row=1, column=1, value=text)
        c.fill = navy_fill
        c.font = title_font
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[1].height = 26

    def write_table(ws, df, start_row, header_fill=navy_fill, numfmt="#,##0.0"):
        ncols = len(df.columns)
        for j, col in enumerate(df.columns, start=1):
            ws.cell(row=start_row, column=j, value=str(col))
        style_header(ws, start_row, ncols, header_fill)
        for i, (_, r) in enumerate(df.iterrows(), start=start_row + 1):
            for j, col in enumerate(df.columns, start=1):
                v = r[col]
                cell = ws.cell(row=i, column=j, value=(None if pd.isna(v) else v))
                cell.border = border
                if isinstance(v, (int, float, np.floating, np.integer)) and not pd.isna(v):
                    cell.number_format = numfmt if isinstance(v, float) else "#,##0"
                    cell.alignment = Alignment(horizontal="center")
        return start_row + len(df) + 1

    # ---- Aba 1: Evolução do PL --------------------------------------------
    ws = wb.active
    ws.title = "Evolucao PL"
    banner(ws, "Evolução do PL da indústria de FIDCs — R$ bilhões", 3)
    annual = evolucao_pl_anual(data["admin"])
    r0 = 3
    ws.cell(row=r0, column=1, value="Ano"); ws.cell(row=r0, column=2, value="PL (R$ bi)")
    style_header(ws, r0, 2)
    for i, (_, row) in enumerate(annual.iterrows(), start=r0 + 1):
        ws.cell(row=i, column=1, value=int(row["ano"])).border = border
        c = ws.cell(row=i, column=2, value=float(row["pl_bi"])); c.border = border; c.number_format = "#,##0"
    last = r0 + len(annual)
    chart = BarChart(); chart.type = "col"; chart.title = None; chart.height = 9; chart.width = 22
    chart.style = 10
    dref = Reference(ws, min_col=2, min_row=r0, max_row=last)
    cats = Reference(ws, min_col=1, min_row=r0 + 1, max_row=last)
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    s = chart.series[0]
    s.graphicalProperties.solidFill = ORANGE
    s.graphicalProperties.line.solidFill = ORANGE
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True; chart.dLbls.numFmt = "#,##0"
    chart.legend = None
    ws.add_chart(chart, "D3")
    ws.column_dimensions["A"].width = 10; ws.column_dimensions["B"].width = 12

    # ---- Aba 2: Composição por segmento -----------------------------------
    ws = wb.create_sheet("Composicao Segmento")
    banner(ws, f"Composição do PL por segmento — {comp} (R$ bi e %)", 3)
    seg = composicao_segmento(snap)
    seg_disp = seg.copy()
    seg_disp["share_%"] = (seg_disp["share"] * 100).round(1)
    seg_disp = seg_disp.rename(columns={"segmento": "Segmento", "pl_bi": "PL (R$ bi)"})[["Segmento", "PL (R$ bi)", "share_%"]]
    r0 = 3
    end = write_table(ws, seg_disp, r0)
    chart = BarChart(); chart.type = "bar"; chart.height = 9.5; chart.width = 22; chart.style = 10
    dref = Reference(ws, min_col=2, min_row=r0, max_row=r0 + len(seg_disp))
    cats = Reference(ws, min_col=1, min_row=r0 + 1, max_row=r0 + len(seg_disp))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = NAVY
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True; chart.dLbls.numFmt = "#,##0"
    chart.legend = None
    ws.add_chart(chart, "E3")
    ws.column_dimensions["A"].width = 22

    # ---- Aba 3: Ranking Administradores -----------------------------------
    ws = wb.create_sheet("Ranking Admin")
    banner(ws, f"Ranking de Administradores por PL — {comp} (Top 10, R$ bi)", 3)
    radm = ranking_admin(snap, 10)
    r0 = 3
    write_table(ws, radm, r0)
    chart = BarChart(); chart.type = "bar"; chart.height = 9.5; chart.width = 22; chart.style = 10
    dref = Reference(ws, min_col=3, min_row=r0, max_row=r0 + len(radm))
    cats = Reference(ws, min_col=2, min_row=r0 + 1, max_row=r0 + len(radm))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = ORANGE
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True; chart.dLbls.numFmt = "#,##0.0"
    chart.legend = None
    ws.add_chart(chart, "E3")
    ws.column_dimensions["B"].width = 46

    # ---- Aba 4: Ranking Gestores ------------------------------------------
    ws = wb.create_sheet("Ranking Gestor")
    banner(ws, f"Ranking de Gestores por PL — {comp} (Top 10, R$ bi)", 3)
    rges = ranking_gestor(snap, 10)
    r0 = 3
    write_table(ws, rges, r0)
    chart = BarChart(); chart.type = "bar"; chart.height = 9.5; chart.width = 22; chart.style = 10
    dref = Reference(ws, min_col=3, min_row=r0, max_row=r0 + len(rges))
    cats = Reference(ws, min_col=2, min_row=r0 + 1, max_row=r0 + len(rges))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = NAVY
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True; chart.dLbls.numFmt = "#,##0.0"
    chart.legend = None
    ws.add_chart(chart, "E3")
    ws.column_dimensions["B"].width = 46

    # ---- Aba 5: Top 25 FIDCs ----------------------------------------------
    ws = wb.create_sheet("Top 25 FIDCs")
    banner(ws, f"Top 25 FIDCs por PL — {comp} (R$ bi)", 5)
    top = top_fidcs(snap, 25).rename(columns={"pl_bi": "PL (R$ bi)"})
    write_table(ws, top, 3, numfmt="#,##0.00")
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 40
    ws.column_dimensions["E"].width = 12

    # ---- Aba 6: Cotistas ---------------------------------------------------
    ws = wb.create_sheet("Cotistas")
    banner(ws, "Número de cotistas — fundos > R$ 200 mi de PL", 3)
    cot, meta = cotistas_distribuicao(snap)
    ws.cell(row=2, column=1, value=f"Universo: {meta['n_fundos']} fundos / R$ {meta['pl_bi']:.0f} bi de PL")
    cot_disp = cot.rename(columns={"bucket": "Faixa", "n_fundos": "# Fundos", "pl_bi": "PL (R$ bi)"})
    r0 = 4
    write_table(ws, cot_disp, r0, numfmt="#,##0")
    chart = BarChart(); chart.type = "col"; chart.height = 9.5; chart.width = 20; chart.style = 10
    dref = Reference(ws, min_col=2, min_row=r0, max_row=r0 + len(cot_disp))
    cats = Reference(ws, min_col=1, min_row=r0 + 1, max_row=r0 + len(cot_disp))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = ORANGE
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True
    chart.legend = None
    ws.add_chart(chart, "E4")
    ws.column_dimensions["A"].width = 18

    # ---- Aba 7: Segmento de investidor ------------------------------------
    ws = wb.create_sheet("Segmento Investidor")
    invs, comp_inv = cotistas_por_segmento_investidor(data["cot_tipo"])
    banner(ws, f"Nº de cotistas por segmento de investidor — {comp_inv}", 3)
    invs_disp = invs.rename(columns={"tipo_cotista": "Segmento", "n_cotistas": "# Cotistas"})
    r0 = 3
    write_table(ws, invs_disp, r0, numfmt="#,##0")
    chart = BarChart(); chart.type = "bar"; chart.height = 10; chart.width = 22; chart.style = 10
    dref = Reference(ws, min_col=2, min_row=r0, max_row=r0 + len(invs_disp))
    cats = Reference(ws, min_col=1, min_row=r0 + 1, max_row=r0 + len(invs_disp))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = NAVY
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True
    chart.legend = None
    ws.add_chart(chart, "D3")
    ws.column_dimensions["A"].width = 32

    # ---- Aba 8: Tipo de gestor (heurístico) -------------------------------
    ws = wb.create_sheet("Tipo Gestor")
    banner(ws, "PL por tipo de gestor — Independente vs Ligada a banco (heurístico)", 3)
    tg = pl_por_tipo_gestor(snap)
    tg_disp = tg.assign(**{"share_%": (tg["share"] * 100).round(1)}).rename(
        columns={"tipo_gestor": "Tipo de gestor", "pl_bi": "PL (R$ bi)"}
    )[["Tipo de gestor", "PL (R$ bi)", "share_%"]]
    r0 = 4
    ws.cell(row=2, column=1, value="Classificação heurística por palavra-chave no nome do gestor — aproximação, não oficial")
    write_table(ws, tg_disp, r0)
    chart = BarChart(); chart.type = "col"; chart.height = 9; chart.width = 16; chart.style = 10
    dref = Reference(ws, min_col=2, min_row=r0, max_row=r0 + len(tg_disp))
    cats = Reference(ws, min_col=1, min_row=r0 + 1, max_row=r0 + len(tg_disp))
    chart.add_data(dref, titles_from_data=True); chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = ORANGE
    chart.dLbls = DataLabelList(); chart.dLbls.showVal = True; chart.dLbls.numFmt = "#,##0"
    chart.legend = None
    ws.add_chart(chart, "E4")
    ws.column_dimensions["A"].width = 22

    # ---- Aba 9: Fonte & Metodologia ---------------------------------------
    ws = wb.create_sheet("Fonte e Metodologia")
    banner(ws, "Fonte e Metodologia", 2)
    notes = [
        f"Competência de referência: {comp} (último mês completo).",
        "Fonte primária: CVM Dados Abertos — Informe Mensal FIDC + Cadastro de fundos.",
        "PL: soma de TAB_IV_A_VL_PL (patrimônio líquido) por fundo/classe.",
        "PL de indústria (evolução): série mensal agregada; último mês incompleto é descartado.",
        "Atenção: a soma bruta contém dupla contagem (master-feeder, FIC-FIDC, classes senior/sub).",
        "Administrador e gestor: cadastro CVM (cad_fi / registro_fundo_classe).",
        "Segmento: taxonomia interna do projeto (segmento_principal) — análoga, não idêntica às classes ANBIMA.",
        "Independente vs banco: classificação HEURÍSTICA por palavra-chave no nome do gestor.",
        "Nº de cotistas por segmento de investidor: Informe Mensal FIDC (tabela X).",
        "Este material NÃO depende de Power BI nem de dados proprietários da ANBIMA.",
    ]
    for i, n in enumerate(notes, start=3):
        ws.cell(row=i, column=1, value=f"• {n}")
    ws.column_dimensions["A"].width = 120

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"[ok] Excel gravado: {path}")


# ---------------------------------------------------------------------------
# PowerPoint (gráficos nativos)
# ---------------------------------------------------------------------------
def build_pptx(data: dict, comp: str, path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION

    snap = data["snap"]

    def rgb(h):
        return RGBColor.from_string(h)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    SW, SH = prs.slide_width, prs.slide_height

    def add_slide():
        return prs.slides.add_slide(blank)

    def add_rect(slide, x, y, w, h, color):
        from pptx.enum.shapes import MSO_SHAPE
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        shp.fill.solid(); shp.fill.fore_color.rgb = rgb(color)
        shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def add_text(slide, x, y, w, h, text, size=18, bold=False, color=INK,
                 align=PP_ALIGN.LEFT, font="Calibri", anchor=MSO_ANCHOR.TOP):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame; tf.word_wrap = True
        tf.vertical_anchor = anchor
        p = tf.paragraphs[0]; p.alignment = align
        run = p.add_run(); run.text = text
        run.font.size = Pt(size); run.font.bold = bold
        run.font.color.rgb = rgb(color); run.font.name = font
        return tb

    def header(slide, kicker, title):
        add_rect(slide, 0, 0, SW, Inches(1.15), NAVY)
        add_rect(slide, 0, Inches(1.15), SW, Emu(45720), ORANGE)  # thin accent
        if kicker:
            add_text(slide, Inches(0.5), Inches(0.12), Inches(12), Inches(0.3),
                     kicker.upper(), size=11, bold=True, color=ORANGE_SOFT)
        add_text(slide, Inches(0.5), Inches(0.38), Inches(12.3), Inches(0.7),
                 title, size=23, bold=True, color=WHITE)

    def footer(slide):
        add_text(slide, Inches(0.5), SH - Inches(0.4), Inches(9), Inches(0.3),
                 f"Fonte: CVM Dados Abertos (Informe Mensal FIDC + Cadastro) · competência {comp} · sem Power BI",
                 size=8.5, color=GRAY)

    def style_chart(chart, colors, number_format="#,##0", show_legend=False, label_size=10):
        chart.has_title = False
        try:
            plot = chart.plots[0]
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.number_format = number_format
            dl.number_format_is_linked = False
            dl.font.size = Pt(label_size)
            dl.font.name = "Calibri"
            try:
                dl.position = XL_LABEL_POSITION.OUTSIDE_END
            except Exception:
                pass
        except Exception:
            pass
        chart.has_legend = show_legend
        if show_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(9)
        # cores por ponto
        ser = chart.series[0]
        try:
            for i, pt in enumerate(ser.points):
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(colors[i % len(colors)])
        except Exception:
            ser.format.fill.solid(); ser.format.fill.fore_color.rgb = rgb(colors[0])
        for ax in ("category_axis", "value_axis"):
            try:
                a = getattr(chart, ax)
                a.tick_labels.font.size = Pt(10); a.tick_labels.font.name = "Calibri"
            except Exception:
                pass

    def add_table(slide, df, x, y, w, h, col_widths=None, font_size=10, highlight_last=False):
        rows, cols = df.shape[0] + 1, df.shape[1]
        gtbl = slide.shapes.add_table(rows, cols, x, y, w, h).table
        for j, col in enumerate(df.columns):
            cell = gtbl.cell(0, j)
            cell.text = str(col)
            cell.fill.solid(); cell.fill.fore_color.rgb = rgb(NAVY)
            para = cell.text_frame.paragraphs[0]; para.alignment = PP_ALIGN.CENTER
            run = para.runs[0]; run.font.size = Pt(font_size); run.font.bold = True
            run.font.color.rgb = rgb(WHITE); run.font.name = "Calibri"
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for i in range(df.shape[0]):
            for j, col in enumerate(df.columns):
                v = df.iloc[i, j]
                cell = gtbl.cell(i + 1, j)
                if isinstance(v, float):
                    txt = f"{v:,.2f}" if abs(v) < 100 else f"{v:,.1f}"
                elif isinstance(v, (int, np.integer)):
                    txt = f"{int(v):,}"
                else:
                    txt = "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
                cell.text = txt
                band = "F3F5F8" if i % 2 == 0 else WHITE
                cell.fill.solid(); cell.fill.fore_color.rgb = rgb(band)
                para = cell.text_frame.paragraphs[0]
                para.alignment = PP_ALIGN.LEFT if isinstance(v, str) else PP_ALIGN.CENTER
                run = para.runs[0] if para.runs else para.add_run()
                run.font.size = Pt(font_size); run.font.name = "Calibri"; run.font.color.rgb = rgb(INK)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        if col_widths:
            total = sum(col_widths)
            for j, cw in enumerate(col_widths):
                gtbl.columns[j].width = int(w * cw / total)
        return gtbl

    # ===================== Slide 0 — Capa =====================
    s = add_slide()
    add_rect(s, 0, 0, SW, SH, NAVY)
    add_rect(s, 0, Inches(3.05), SW, Inches(0.08), ORANGE)
    add_text(s, Inches(0.8), Inches(2.1), Inches(11.7), Inches(1.0),
             "Indústria de FIDCs", size=44, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(3.25), Inches(11.7), Inches(0.7),
             "Panorama de mercado — PL, prestadores de serviço e concentração", size=20, color=ORANGE_SOFT)
    add_text(s, Inches(0.8), Inches(4.2), Inches(11.7), Inches(0.5),
             f"Competência {comp}", size=16, bold=True, color=WHITE)
    add_text(s, Inches(0.8), SH - Inches(0.9), Inches(11.7), Inches(0.5),
             "Fonte: CVM Dados Abertos (Informe Mensal FIDC + Cadastro). Reconstrução independente, sem Power BI.",
             size=11, color=GRAY_LIGHT)

    # ===================== Slide 1 — Evolução do PL =====================
    s = add_slide()
    header(s, "Crescimento da indústria", "Evolução do PL da indústria de FIDCs")
    annual = evolucao_pl_anual(data["admin"])
    cd = CategoryChartData()
    cd.categories = [str(int(a)) for a in annual["ano"]]
    cd.add_series("PL (R$ bi)", [float(v) for v in annual["pl_bi"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.5),
                            Inches(8.6), Inches(5.4), cd)
    style_chart(gf.chart, [ORANGE], number_format="#,##0")
    # variação total
    v0, v1 = float(annual["pl_bi"].iloc[0]), float(annual["pl_bi"].iloc[-1])
    growth = (v1 / v0 - 1) * 100 if v0 else 0
    add_rect(s, Inches(9.4), Inches(1.9), Inches(3.4), Inches(2.0), "F3F5F8")
    add_text(s, Inches(9.6), Inches(2.05), Inches(3.0), Inches(0.4), "PL atual", size=12, bold=True, color=NAVY)
    add_text(s, Inches(9.6), Inches(2.45), Inches(3.0), Inches(0.7), f"R$ {v1:,.0f} bi", size=30, bold=True, color=ORANGE)
    add_text(s, Inches(9.6), Inches(3.25), Inches(3.0), Inches(0.5),
             f"{annual['ano'].iloc[0]}→{annual['ano'].iloc[-1]}: +{growth:,.0f}%", size=14, bold=True, color=NAVY)
    add_text(s, Inches(9.4), Inches(4.1), Inches(3.5), Inches(2.4),
             "• Crescimento consistente ao longo do ciclo\n• Impulso por avanços regulatórios, novos recebíveis e busca por funding\n• Base bruta (com dupla contagem intra-indústria)",
             size=12, color=INK)
    footer(s)

    # ===================== Slide 2 — Composição por segmento =====================
    s = add_slide()
    header(s, "Composição", f"PL por segmento de atuação — {comp}")
    seg = composicao_segmento(snap).head(8)
    cd = CategoryChartData()
    cd.categories = list(seg["segmento"])
    cd.add_series("PL (R$ bi)", [float(v) for v in seg["pl_bi"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.5),
                            Inches(8.4), Inches(5.4), cd)
    style_chart(gf.chart, SEGMENT_COLORS, number_format="#,##0")
    # tabela share
    seg_tab = seg.copy()
    seg_tab["Share %"] = (seg_tab["share"] * 100).round(1)
    seg_tab = seg_tab.rename(columns={"segmento": "Segmento", "pl_bi": "PL (R$ bi)"})[["Segmento", "PL (R$ bi)", "Share %"]]
    add_table(s, seg_tab, Inches(9.1), Inches(1.7), Inches(3.9), Inches(4.6),
              col_widths=[2.3, 1.1, 1.0], font_size=10)
    footer(s)

    # ===================== Slide 3 — Ranking Administradores =====================
    s = add_slide()
    header(s, "Prestadores de serviço", f"Ranking de Administradores por PL — {comp}")
    radm = ranking_admin(snap, 10)
    cd = CategoryChartData()
    cd.categories = [n[:34] for n in radm["Administrador"]][::-1]
    cd.add_series("PL (R$ bi)", [float(v) for v in radm["pl_bi"]][::-1])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.5),
                            Inches(12.3), Inches(5.4), cd)
    style_chart(gf.chart, [ORANGE], number_format="#,##0.0")
    footer(s)

    # ===================== Slide 4 — Ranking Gestores =====================
    s = add_slide()
    header(s, "Prestadores de serviço", f"Ranking de Gestores por PL — {comp}")
    rges = ranking_gestor(snap, 10)
    cd = CategoryChartData()
    cd.categories = [n[:34] for n in rges["Gestor"]][::-1]
    cd.add_series("PL (R$ bi)", [float(v) for v in rges["pl_bi"]][::-1])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.5),
                            Inches(12.3), Inches(5.4), cd)
    style_chart(gf.chart, [NAVY], number_format="#,##0.0")
    footer(s)

    # ===================== Slide 5 — Top 25 FIDCs =====================
    s = add_slide()
    header(s, "Maiores veículos", f"Top 25 FIDCs por PL — {comp} (R$ bi)")
    top = top_fidcs(snap, 25).rename(columns={"pl_bi": "PL (R$ bi)"}).copy()
    top["Fundo"] = top["Fundo"].str.slice(0, 52)
    top["Gestor"] = top["Gestor"].str.slice(0, 34)
    half = 13
    left = top.iloc[:half].reset_index(drop=True)
    right = top.iloc[half:].reset_index(drop=True)
    add_table(s, left, Inches(0.35), Inches(1.5), Inches(6.35), Inches(5.6),
              col_widths=[0.4, 3.4, 1.4, 2.2, 0.9], font_size=8)
    add_table(s, right, Inches(6.95), Inches(1.5), Inches(6.35), Inches(5.6),
              col_widths=[0.4, 3.4, 1.4, 2.2, 0.9], font_size=8)
    footer(s)

    # ===================== Slide 6 — Cotistas =====================
    s = add_slide()
    header(s, "Estrutura de cotistas", "Número de cotistas — fundos > R$ 200 mi de PL")
    cot, meta = cotistas_distribuicao(snap)
    add_text(s, Inches(0.5), Inches(1.35), Inches(12), Inches(0.4),
             f"{meta['n_fundos']} fundos · R$ {meta['pl_bi']:.0f} bi de PL · estruturas mono/poucos cotistas são relevantes (veículos de crédito institucionais)",
             size=12, bold=True, color=NAVY)
    cd = CategoryChartData()
    cd.categories = list(cot["bucket"])
    cd.add_series("# Fundos", [int(v) for v in cot["n_fundos"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.2), Inches(2.0),
                            Inches(7.2), Inches(4.8), cd)
    style_chart(gf.chart, [ORANGE, ORANGE_SOFT, GRAY, NAVY], number_format="#,##0")
    cot_tab = cot.rename(columns={"bucket": "Faixa", "n_fundos": "# Fundos", "pl_bi": "PL (R$ bi)"})
    add_table(s, cot_tab, Inches(8.7), Inches(2.4), Inches(4.2), Inches(2.6),
              col_widths=[1.6, 1.0, 1.2], font_size=11)
    footer(s)

    # ===================== Slide 7 — Segmento de investidor =====================
    s = add_slide()
    invs, comp_inv = cotistas_por_segmento_investidor(data["cot_tipo"])
    header(s, "Base investidora", f"Nº de cotistas por segmento de investidor — {comp_inv}")
    cd = CategoryChartData()
    cd.categories = [n[:30] for n in invs["tipo_cotista"]][::-1]
    cd.add_series("# Cotistas", [float(v) for v in invs["n_cotistas"]][::-1])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.5),
                            Inches(12.3), Inches(5.4), cd)
    style_chart(gf.chart, [NAVY], number_format="#,##0")
    footer(s)

    # ===================== Slide 8 — Tipo de gestor (heurístico) =====================
    s = add_slide()
    header(s, "Perfil dos gestores", "PL por tipo de gestor — Independente vs Ligada a banco")
    tg = pl_por_tipo_gestor(snap)
    cd = CategoryChartData()
    cd.categories = list(tg["tipo_gestor"])
    cd.add_series("PL (R$ bi)", [float(v) for v in tg["pl_bi"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.2), Inches(1.8),
                            Inches(6.8), Inches(4.9), cd)
    style_chart(gf.chart, [ORANGE, NAVY], number_format="#,##0")
    for i, row in tg.iterrows():
        add_text(s, Inches(8.5), Inches(2.2 + i * 0.9), Inches(4.3), Inches(0.9),
                 f"{row['tipo_gestor']}: R$ {row['pl_bi']:,.0f} bi ({row['share']*100:,.0f}%)",
                 size=15, bold=True, color=(ORANGE if i == 0 else NAVY))
    add_text(s, Inches(8.5), Inches(4.6), Inches(4.5), Inches(1.8),
             "Classificação HEURÍSTICA por palavra-chave no nome do gestor. "
             "Aproximação — não substitui a taxonomia oficial ANBIMA de estrutura de gestão.",
             size=11, color=GRAY)
    footer(s)

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    print(f"[ok] PPTX gravado: {path}")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Gera Excel + PPT executivo da indústria de FIDCs.")
    ap.add_argument("--industry-dir", type=Path, default=Path("data/industry_study"))
    ap.add_argument("--out", type=Path, default=Path("outputs"))
    args = ap.parse_args()

    data = load_datasets(args.industry_dir)
    comp = competencia_label(data["snap"])
    xlsx = args.out / f"Industria_FIDC_{comp}.xlsx"
    pptx = args.out / f"Industria_FIDC_{comp}.pptx"
    build_excel(data, comp, xlsx)
    build_pptx(data, comp, pptx)
    print(f"[ok] competência {comp} — entregáveis em {args.out}/")


if __name__ == "__main__":
    main()
