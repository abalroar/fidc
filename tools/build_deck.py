# -*- coding: utf-8 -*-
"""Deck de analise de credito, gerado dos mesmos CSVs do workbook.

Regras: apenas shapes, tabelas e graficos nativos do Office. Paleta laranja,
preto e cinzas. Hierarquia por tamanho, peso e espacamento - nunca por cor de texto.
Sem imagens, sem cartoes de indicador, sem selo de rodape, sem setas tipograficas.
"""
import csv, os, sys
from pptx import Presentation
from pptx.util import Emu, Pt, Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "solfacil_claude")
OUTDIR = os.path.join(ROOT, "outputs", "solfacil")

# ---------------------------------------------------------------- paleta
LARANJA     = RGBColor(0xFF, 0xBC, 0x00)
LARANJA_ESC = RGBColor(0xC0, 0x8F, 0x00)
LARANJA_CLA = RGBColor(0xFF, 0xE0, 0x8A)
PRETO       = RGBColor(0x00, 0x00, 0x00)
CINZA_ESC   = RGBColor(0x32, 0x34, 0x36)
CINZA_MED   = RGBColor(0x6E, 0x6E, 0x6E)
CINZA_CLARO = RGBColor(0xBF, 0xBF, 0xBF)
CINZA_FUNDO = RGBColor(0xF2, 0xF2, 0xF2)
BRANCO      = RGBColor(0xFF, 0xFF, 0xFF)

FONTE = "Calibri"

# ---------------------------------------------------------------- grade, em EMU
SL_W, SL_H = Emu(12192000), Emu(6858000)
MARGEM     = Emu(548640)           # 0,6"
UTIL_W     = Emu(12192000 - 2 * 548640)
Y_TITULO   = Emu(411480)           # 0,45"
H_TITULO   = Emu(365760)           # 0,40"
Y_SUB      = Emu(795528)
H_SUB      = Emu(320040)
Y_CORPO    = Emu(1417320)          # 1,55"
Y_RODAPE   = Emu(6217920)          # 6,80"
H_RODAPE   = Emu(274320)
COLS = 12
GUT = Emu(137160)


def col_x(i):
    passo = (UTIL_W.emu - GUT.emu * (COLS - 1)) / COLS
    return Emu(int(MARGEM.emu + i * (passo + GUT.emu)))


def col_w(n):
    passo = (UTIL_W.emu - GUT.emu * (COLS - 1)) / COLS
    return Emu(int(n * passo + (n - 1) * GUT.emu))


def ler(nome):
    with open(os.path.join(DATA, nome), encoding="utf-8") as fh:
        r = list(csv.reader(fh))
    return r[0], r[1:]


def txt(sl, x, y, w, h, texto, tam=12, negrito=False, cor=PRETO, alinh=PP_ALIGN.LEFT,
        espaco=0, anchor=MSO_ANCHOR.TOP, italico=False):
    cx = sl.shapes.add_textbox(x, y, w, h)
    tf = cx.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    linhas = texto.split("\n")
    for i, ln in enumerate(linhas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinh
        p.space_after = Pt(espaco)
        r = p.add_run(); r.text = ln
        r.font.size = Pt(tam); r.font.bold = negrito; r.font.italic = italico
        r.font.color.rgb = cor; r.font.name = FONTE
    return cx


def cabecalho(sl, eyebrow, titulo, subtitulo=None):
    """Faixa de titulo. Hierarquia por tamanho e peso, nao por cor."""
    txt(sl, MARGEM, Emu(228600), col_w(9), Emu(160020), eyebrow.upper(), tam=9,
        negrito=True, cor=CINZA_MED)
    txt(sl, MARGEM, Y_TITULO, col_w(11), H_TITULO, titulo, tam=23, negrito=True, cor=PRETO)
    if subtitulo:
        txt(sl, MARGEM, Y_SUB, col_w(11), H_SUB, subtitulo, tam=12.5, cor=CINZA_ESC)
    ln = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGEM, Emu(1188720), col_w(2), Emu(27432))
    ln.fill.solid(); ln.fill.fore_color.rgb = LARANJA
    ln.line.fill.background(); ln.shadow.inherit = False


def rodape(sl, fonte_txt):
    """Linha informativa de fonte e data-base. Texto puro: sem caixa, fundo ou borda."""
    txt(sl, MARGEM, Y_RODAPE, UTIL_W, H_RODAPE, fonte_txt, tam=8.5, cor=CINZA_MED)


def leitura(sl, y, texto, w=None):
    """Uma frase de leitura de credito, destacada por peso e tamanho, nao por cor."""
    txt(sl, MARGEM, y, w or UTIL_W, Emu(365760), texto, tam=12, negrito=True, cor=PRETO)


def sem_sombra(shp):
    shp.shadow.inherit = False
    return shp


def bloco(sl, x, y, w, h, texto, fundo, cor_txt=BRANCO, tam=10.5, negrito=True,
          forma=MSO_SHAPE.RECTANGLE):
    s = sl.shapes.add_shape(forma, x, y, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = fundo
    s.line.color.rgb = fundo; s.line.width = Pt(0.75)
    sem_sombra(s)
    tf = s.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(45720)
    tf.margin_top = tf.margin_bottom = Emu(27432)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = texto
    r.font.size = Pt(tam); r.font.bold = negrito
    r.font.color.rgb = cor_txt; r.font.name = FONTE
    return s


def tabela(sl, x, y, w, h, cabecalhos, linhas, larguras=None, tam=9.5, tam_cab=9.5,
           altura_cab=Emu(320040), altura_linha=None, alinh_centro=()):
    n_l, n_c = len(linhas) + 1, len(cabecalhos)
    gf = sl.shapes.add_table(n_l, n_c, x, y, w, h)
    tb = gf.table
    tb.first_row = False; tb.horz_banding = False
    if larguras:
        total = sum(larguras)
        for j, frac in enumerate(larguras):
            tb.columns[j].width = Emu(int(w.emu * frac / total))
    tb.rows[0].height = altura_cab
    if altura_linha:
        for i in range(1, n_l):
            tb.rows[i].height = altura_linha
    for j, c in enumerate(cabecalhos):
        cel = tb.cell(0, j)
        cel.text = ""
        cel.fill.solid(); cel.fill.fore_color.rgb = CINZA_ESC
        cel.margin_left = cel.margin_right = Emu(54864)
        cel.margin_top = cel.margin_bottom = Emu(27432)
        cel.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cel.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER if j in alinh_centro else PP_ALIGN.LEFT
        r = p.add_run(); r.text = c
        r.font.size = Pt(tam_cab); r.font.bold = True
        r.font.color.rgb = BRANCO; r.font.name = FONTE
    for i, linha in enumerate(linhas, start=1):
        for j, v in enumerate(linha):
            cel = tb.cell(i, j)
            cel.text = ""
            cel.fill.solid(); cel.fill.fore_color.rgb = BRANCO
            cel.margin_left = cel.margin_right = Emu(54864)
            cel.margin_top = cel.margin_bottom = Emu(22860)
            cel.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cel.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if j in alinh_centro else PP_ALIGN.LEFT
            r = p.add_run(); r.text = str(v)
            r.font.size = Pt(tam)
            r.font.bold = (j == 0)
            r.font.color.rgb = PRETO; r.font.name = FONTE
    return tb


def estilizar_gr(gr, cores, legenda=True, tam=9.5):
    gr.has_title = False
    gr.font.size = Pt(tam); gr.font.name = FONTE
    gr.font.color.rgb = CINZA_ESC
    if legenda:
        gr.has_legend = True
        gr.legend.position = XL_LEGEND_POSITION.BOTTOM
        gr.legend.include_in_layout = False
        gr.legend.font.size = Pt(tam)
    else:
        gr.has_legend = False
    for s, cor in zip(gr.series, cores):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = cor
        s.format.line.color.rgb = cor
    return gr


prs = Presentation()
prs.slide_width, prs.slide_height = SL_W, SL_H
VAZIO = prs.slide_layouts[6]
FONTE_PADRAO = ("Fontes: laminas, prospectos, comunicados e anuncios de oferta CVM das seis emissoes; "
                "2o Aditamento ao Termo de Securitizacao da 2a emissao Kanastra; analise de credito Solfacil de 21/08/2026. "
                "Data-base: FIDCs em 31/07/2026; CRIs na ultima competencia por operacao; escopo publico ate 22/08/2026.")

# ============================================================ 1. Capa
sl = prs.slides.add_slide(VAZIO)
txt(sl, MARGEM, Emu(1005840), col_w(8), Emu(228600), "SOLFACIL | CREDITO ESTRUTURADO",
    tam=10.5, negrito=True, cor=CINZA_MED)
txt(sl, MARGEM, Emu(1325880), col_w(9), Emu(731520),
    "Sete warehouses FIDC, seis take-outs em CRI", tam=33, negrito=True, cor=PRETO)
txt(sl, MARGEM, Emu(2103120), col_w(8), Emu(457200),
    "Elegibilidade, ordem de pagamentos, extracao de subordinada, investidores e custo de funding.\n"
    "Cada numero deste deck resolve para uma linha de CSV com fonte identificada.",
    tam=13, cor=CINZA_ESC, espaco=3)
b = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGEM, Emu(2011680), col_w(2), Emu(27432))
b.fill.solid(); b.fill.fore_color.rgb = LARANJA; b.line.fill.background(); sem_sombra(b)

tabela(sl, MARGEM, Emu(2925763), col_w(7), Emu(1600200),
       ["O universo", "Quantidade", "Como fecha"],
       [["Veiculos", "13", "7 FIDCs de warehouse e 6 operacoes de CRI de take-out"],
        ["Series de CRI", "34", "5 + 5 + 6 + 7 + 6 + 5, contando a serie privada de cada operacao"],
        ["Volume nominal", "R$ 3.670,7 mi", "R$ 3.563,7 mi publicos e R$ 107,0 mi de series privadas retidas"],
        ["Classes de cotas FIDC", "34", "Dimensao diferente das series de CRI; nao se somam"]],
       larguras=[0.26, 0.16, 0.58], tam=10.5, altura_linha=Emu(365760))

txt(sl, col_x(8), Emu(2925763), col_w(4), Emu(1600200),
    "O que este deck responde\n\n"
    "Se o recebivel pode ir a 126 meses e o pool a 66, quantos anos tem cada serie de CRI, "
    "e quem carrega o risco de refinanciamento.\n\n"
    "Como cada operacao escolhe o que compra, criterio a criterio.\n\n"
    "Quando a subordinada da originadora pode sair, e o que ja saiu.",
    tam=11, cor=CINZA_ESC, espaco=5)
rodape(sl, FONTE_PADRAO)

# ============================================================ 2. Mapa do programa (fluxo com conectores nativos)
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Estrutura", "O programa em quatro etapas",
          "O FIDC financia a carteira enquanto ela nasce; o CRI compra um pool fechado e alonga o passivo.")
etapas = [
    ("ORIGINACAO", "Solfacil e cerca de 4 mil\nintegradores ativos\n\nCCB pre-fixada de PF e PJ\ncom destinacao a sistema\nfotovoltaico"),
    ("WAREHOUSE", "FIDCs I a VII\n\nCompram e financiam a\ncarteira durante a\noriginacao, com\nrevolvencia"),
    ("TAKE-OUT", "Kanastra 1a a 4a\nVERT 174a e 177a\n\nCessao definitiva sem\ncoobrigacao; novo\npatrimonio separado"),
    ("INVESTIDORES", "Super Senior ate\nSubordinado Jr.\n\nSeries publicas ao mercado\ne serie privada retida\npela originadora"),
]
larg = col_w(3)
y_cx = Emu(1874520)
h_cx = Emu(1965960)
caixas = []
for i, (tit, corpo) in enumerate(etapas):
    x = Emu(int(MARGEM.emu + i * (larg.emu + Emu(228600).emu)))
    if x.emu + larg.emu > SL_W.emu - MARGEM.emu:
        x = Emu(SL_W.emu - MARGEM.emu - larg.emu)
    cx = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y_cx, larg, h_cx)
    cx.fill.solid(); cx.fill.fore_color.rgb = BRANCO
    cx.line.color.rgb = CINZA_CLARO; cx.line.width = Pt(1)
    sem_sombra(cx)
    tf = cx.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(114300); tf.margin_top = Emu(0)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.text = ""
    caixas.append(cx)
    faixa = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y_cx, larg, Emu(342900))
    faixa.fill.solid(); faixa.fill.fore_color.rgb = LARANJA if i in (1, 2) else CINZA_ESC
    faixa.line.fill.background(); sem_sombra(faixa)
    ftf = faixa.text_frame; ftf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = ftf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = f"{i + 1}.  {tit}"
    r.font.size = Pt(11); r.font.bold = True; r.font.name = FONTE
    r.font.color.rgb = PRETO if i in (1, 2) else BRANCO
    txt(sl, Emu(x.emu + Emu(114300).emu), Emu(y_cx.emu + Emu(457200).emu),
        Emu(larg.emu - Emu(228600).emu), Emu(1417320), corpo, tam=10, cor=CINZA_ESC, espaco=0)

for i in range(3):
    a = caixas[i]; b_ = caixas[i + 1]
    seta = sl.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW,
        Emu(a.left.emu + a.width.emu + Emu(45720).emu),
        Emu(y_cx.emu + int(h_cx.emu / 2) - Emu(68580).emu),
        Emu(Emu(228600).emu - Emu(91440).emu), Emu(137160))
    seta.fill.solid(); seta.fill.fore_color.rgb = CINZA_MED
    seta.line.fill.background(); sem_sombra(seta)

leitura(sl, Emu(4114800),
        "Tres fundos - II, IV e VI - foram reutilizados em varios take-outs. O programa nao cria um warehouse por emissao de CRI.")
txt(sl, MARGEM, Emu(4525963), UTIL_W, Emu(731520),
    "Os FIDCs cedentes de CRI-I e CRI-II estao nomeados em documento primario: Green Solfacil II (CNPJ 42.462.306/0001-00) e "
    "Green Solfacil IV (CNPJ 44.909.456/0001-44), ambos administrados pelo Banco Genial. Das demais operacoes, o vinculo vem da "
    "analise de credito: as laminas de CRI-III e CRI-V nao nomeiam nenhum fundo e remetem ao Termo de Securitizacao.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Fontes: Prospectos Definitivos da 1a e da 2a emissoes Kanastra (secao 11.1.2 e definicao de Cedentes); laminas de CRI-III e CRI-V; analise de credito Solfacil de 21/08/2026.")

# ============================================================ 3. Linha do tempo das seis emissoes
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Programa", "Seis take-outs em 31 meses",
          "Escala de tempo real: a distancia entre as barras e a distancia entre as emissoes.")
gr_dados = CategoryChartData()
gr_dados.categories = ["Kanastra 1a\njan/2024", "Kanastra 2a\njun/2024", "Kanastra 3a\nmai/2025",
                       "Kanastra 4a\nset/2025", "VERT 174a\nmai/2026", "VERT 177a\njul/2026"]
gr_dados.add_series("Series publicas (R$ mi)", (588.0, 727.5, 727.5, 436.5, 456.5, 627.6))
gr_dados.add_series("Serie privada Subordinado Jr. (R$ mi)", (15.0, 22.5, 22.5, 13.5, 14.1, 19.4))
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, MARGEM, Y_CORPO, col_w(12), Emu(3383280), gr_dados)
gr = gf.chart
estilizar_gr(gr, [CINZA_ESC, LARANJA])
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9)
leitura(sl, Emu(4937760),
        "O volume por operacao nao cresce em linha reta: cai 40% da 3a para a 4a emissao Kanastra e a VERT 174a coloca R$ 456,5 mi contra um lote base de R$ 727,5 mi.")
txt(sl, MARGEM, Emu(5349240), UTIL_W, Emu(640080),
    "A serie privada Subordinado Jr. e a retencao da originadora e ficou estavel entre 2,49% e 3,00% do total em todas as seis operacoes. "
    "Ela e colocada sem esforco de venda, subscrita integralmente pela Solfacil e/ou partes relacionadas - e por isso nao aparece nos "
    "anuncios de encerramento, que so registram a oferta publica.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Series publicas: montante reportado por serie. CRI-VI (VERT 177a) tem montante por serie n/d; o total de R$ 647,1 mi vem da analise de credito. " + FONTE_PADRAO)

# ============================================================ 4. Tamanho por camada
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Estrutura de capital", "Como cada operacao se divide entre camadas",
          "A camada Super Senior concentra de 43% a 70% de cada emissao; a retencao da originadora fica sempre perto de 3%.")
gr_dados = CategoryChartData()
gr_dados.categories = ["Kanastra 1a", "Kanastra 2a", "Kanastra 3a", "Kanastra 4a", "VERT 174a"]
gr_dados.add_series("Super Senior", (360.0, 487.5, 487.5, 292.5, 329.5))
gr_dados.add_series("Senior", (90.0, 135.0, 135.0, 81.0, 70.6))
gr_dados.add_series("Mezanino", (108.0, 75.0, 75.0, 45.0, 37.6))
gr_dados.add_series("Subordinado", (30.0, 30.0, 30.0, 18.0, 18.8))
gr_dados.add_series("Subordinado Jr. (privada)", (15.0, 22.5, 22.5, 13.5, 14.1))
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, MARGEM, Y_CORPO, col_w(8), Emu(3383280), gr_dados)
gr = gf.chart
estilizar_gr(gr, [PRETO, CINZA_ESC, CINZA_MED, CINZA_CLARO, LARANJA])
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9)

txt(sl, col_x(8), Y_CORPO, col_w(4), Emu(365760), "O que sustenta o rating", tam=13, negrito=True, cor=PRETO)
tabela(sl, col_x(8), Emu(1874520), col_w(4), Emu(1691640),
       ["Razao de cobertura", "Patamar"],
       [["Super Senior", "159%"], ["Senior", "123%"], ["Mezanino", "110%"], ["Subordinada", "105%"],
        ["Indice de Atraso de Estoque", "max. 15%"]],
       larguras=[0.66, 0.34], tam=10, alinh_centro=(1,), altura_linha=Emu(283464))
txt(sl, col_x(8), Emu(3657600), col_w(4), Emu(1005840),
    "Patamares contratuais da 2a emissao Kanastra, a unica operacao cujo Termo de Securitizacao "
    "consolidado esta no acervo. Cada camada so recebe se a sua cobertura e todas as acima estiverem "
    "enquadradas na Data de Pagamento.",
    tam=10, cor=CINZA_ESC, espaco=3)
leitura(sl, Emu(4937760),
        "CRI-VI nao entra no grafico: a VERT 177a nao publicou montante por serie. O total de R$ 647,1 mi esta na capa, mas nao pode ser dividido por camada com dado publico.")
rodape(sl, "Super Senior de Kanastra 3a, 4a e VERT 174a soma as subseries A e B, emitidas por vasos comunicantes. " + FONTE_PADRAO)

# ============================================================ 5. Elegibilidade, tabela larga
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Selecao do pool", "Elegibilidade, criterio a criterio",
          "Redacao literal das laminas. O CRI compra um recorte mais curto e mais granular do que o mandato do warehouse permite originar.")
cab = ["Criterio", "FIDCs (faixa dos sete)", "CRI-I  jan/2024", "CRI-III  mai/2025", "CRI-V  mai/2026"]
linhas = [
    ["Taxa da CCB", "Fixa", "Pre-fixada", "Pre-fixada", "Pre-fixada"],
    ["Moeda do pagamento", "Reais (VI e VII)", "n/d na lamina", "n/d na lamina", "Reais, explicito"],
    ["Cap por devedor", "2% a 20% do patrimonio", "0,10% do Patrimonio Separado", "0,10% do Patrimonio Separado",
     "0,15% ate 470.600 cotas;\n0,07% a partir de 750.000"],
    ["Cap dos 10 maiores", "1% a 10%", "1% do Patrimonio Separado", "Nao consta", "Nao consta"],
    ["WAM do pool", "2.000 a 2.400 dias", "2.000 dias", "2.000 dias", "2.000 dias corridos,\nsobre o valor presente"],
    ["Prazo max. por recebivel", "ate 4.760 dias (FIDC V)", "3.845 dias", "3.845 dias", "3.845 dias corridos"],
    ["Devedor inadimplente", "Vedado (II a VII)", "Vedado na Data de Oferta", "Vedado na Data de Oferta", "Vedado na Data de Oferta"],
    ["Parcela balao final", "n/d", "Nao consta", "Nao consta", "Vedada expressamente"],
    ["Idade maxima PF", "71 anos (VI e VII)", "71 anos", "71 anos", "71 anos"],
    ["Pessoa juridica", "2 anos de constituicao", "2 anos de constituicao", "2 anos de constituicao",
     "2 anos e enquadrada na\nResolucao CMN 5.118"],
    ["Carencia maxima", "180 a 366 dias", "185 dias", "185 dias", "185 dias"],
    ["Valor presente max. PF / PJ", "R$ 201-500 mil / 500-700 mil", "R$ 350 mil / R$ 600 mil",
     "R$ 350 mil / R$ 700 mil", "R$ 350 mil / R$ 700 mil"],
    ["Seasoning minimo", "n/d", "Nao exigido", "Nao exigido", "Nao exigido"],
    ["Quem atesta", "Gestora / administrador", "Emissora, com dados dos Cedentes",
     "Emissora, com dados dos Cedentes", "Emissora, com dados da Gestora\ndo Cedente Fundo e da Solfacil"],
]
tabela(sl, MARGEM, Emu(1417320), col_w(12), Emu(4114800), cab, linhas,
       larguras=[0.19, 0.20, 0.20, 0.20, 0.21], tam=8.5, tam_cab=9,
       altura_cab=Emu(274320), altura_linha=Emu(228600))
leitura(sl, Emu(5715000),
        "Nenhuma das seis operacoes exige safra performada, MoB minimo ou historico de inadimplencia do lote: a selecao e documental, nao de performance.")
rodape(sl, "Faixa dos FIDCs conforme parametros da analise de credito; colunas de CRI com redacao literal das laminas de 15/01/2024, 22/04/2025 e 17/04/2026. CRI-II, CRI-IV e CRI-VI seguem o mesmo desenho, com laminas ausentes do acervo.")

# ============================================================ 6. Prazos na mesma escala
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Descasamento de prazo", "O ativo e longo; o passivo, muito mais curto",
          "Tudo em meses, na mesma escala. A duration nao e caracteristica do programa: e caracteristica de cada operacao.")
gr_dados = CategoryChartData()
gr_dados.categories = ["Prazo max. do\nrecebivel", "WAM contratual\ndo pool",
                       "Duration\nCRI-I", "Duration\nCRI-III", "Duration\nCRI-V"]
gr_dados.add_series("Meses", (126.3, 65.7, 41.1, 90.5, 22.4))
gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, MARGEM, Y_CORPO, col_w(7), Emu(3200400), gr_dados)
gr = gf.chart
estilizar_gr(gr, [LARANJA], legenda=False)
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9.5)
gr.plots[0].has_data_labels = True
gr.plots[0].data_labels.font.size = Pt(9)
gr.plots[0].data_labels.font.color.rgb = PRETO

txt(sl, col_x(7), Y_CORPO, col_w(5), Emu(320040), "Duration media das series publicas", tam=13, negrito=True, cor=PRETO)
tabela(sl, col_x(7), Emu(1828800), col_w(5), Emu(1417320),
       ["Operacao", "Duration", "Vencimento legal"],
       [["CRI-I  Kanastra 1a", "1.146 a 1.311 dias", "2031 a 2034"],
        ["CRI-III  Kanastra 3a", "1.806 a 3.632 dias", "2030 a 2037"],
        ["CRI-V  VERT 174a", "659 a 713 dias", "2031 a 2038"]],
       larguras=[0.36, 0.32, 0.32], tam=10, altura_linha=Emu(320040))
txt(sl, col_x(7), Emu(3383280), col_w(5), Emu(1188720),
    "A mesma camada Mezanino tem duration de 3.632 dias em CRI-III e de 690 dias em CRI-V - cinco vezes menos. "
    "Tratar a faixa curta de CRI-V como padrao do programa seria erro material.\n\n"
    "O WAM observado de cada pool nao e publicado em nenhuma operacao: so existe o teto contratual.",
    tam=10.5, cor=CINZA_ESC, espaco=4)
leitura(sl, Emu(4937760),
        "Quem carrega o risco de refinanciamento e o investidor do CRI, por extensao: se a carteira amortizar mais devagar que o previsto, a duration alonga ate o vencimento legal.")
txt(sl, MARGEM, Emu(5349240), UTIL_W, Emu(548640),
    "A amortizacao de toda serie e condicionada a 'caso exista disponibilidade' e ao Saldo Devedor Target - o cronograma do Anexo I e alvo, "
    "nao promessa. A contrapartida do investidor e o resgate compulsorio: quando 98% do valor unitario ja foi amortizado e ha caixa, a serie e resgatada de uma vez.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Duration aproximada informada nas laminas, sujeita a reducao por amortizacao extraordinaria. Conversao para meses a 30,4375 dias. CRI-II, CRI-IV e CRI-VI nao publicam duration. " + FONTE_PADRAO)

# ============================================================ 7. Waterfall nos dois regimes
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Ordem de pagamentos", "O regime chamado de pro rata nao paga em paralelo",
          "Cada camada so recebe se a cobertura dela e a de todas as acima estiverem enquadradas - e recebe ate um saldo alvo, nao ate o cronograma.")
COL_A, COL_B = MARGEM, col_x(6)
LARG = col_w(5)
txt(sl, COL_A, Emu(1417320), LARG, Emu(274320), "REGIME PRO RATA CONDICIONADO", tam=11, negrito=True, cor=PRETO)
txt(sl, COL_B, Emu(1417320), LARG, Emu(274320), "REGIME SEQUENCIAL", tam=11, negrito=True, cor=PRETO)
txt(sl, COL_A, Emu(1691640), LARG, Emu(228600), "Vigente ate o mes 47", tam=9.5, cor=CINZA_MED)
txt(sl, COL_B, Emu(1691640), LARG, Emu(228600), "A partir do mes 48 ou de Evento de Desalavancagem", tam=9.5, cor=CINZA_MED)

PRO = [("Despesas e Reserva de Despesas", CINZA_CLARO, PRETO),
       ("Super Senior ate o Saldo Target", PRETO, BRANCO),
       ("Senior, se cobertura Super Senior enquadrada", CINZA_ESC, BRANCO),
       ("Mezanino, se as duas acima enquadradas", CINZA_MED, BRANCO),
       ("Subordinado, se as tres acima enquadradas", LARANJA_ESC, BRANCO),
       ("Subordinado Jr., se as quatro enquadradas", LARANJA, PRETO),
       ("Sobra: amortizacao extraordinaria proporcional", CINZA_CLARO, PRETO)]
SEQ = [("Despesas e Reserva de Despesas", CINZA_CLARO, PRETO),
       ("Super Senior ate 98% do valor unitario", PRETO, BRANCO),
       ("Senior ate 98% - sem condicao de cobertura", CINZA_ESC, BRANCO),
       ("Mezanino ate 98%", CINZA_MED, BRANCO),
       ("Subordinado ate 98%", LARANJA_ESC, BRANCO),
       ("Subordinado Jr., por ultimo", LARANJA, PRETO),
       ("Premio Final: todo o remanescente ao Subordinado Jr.", CINZA_CLARO, PRETO)]
Y0 = Emu(1965960); H_B = Emu(365760); GAP = Emu(91440)
for i, ((ta, ca, xa), (tb, cb, xb)) in enumerate(zip(PRO, SEQ)):
    y = Emu(Y0.emu + i * (H_B.emu + GAP.emu))
    bloco(sl, COL_A, y, LARG, H_B, f"{i + 1}.  {ta}", ca, xa, tam=10)
    bloco(sl, COL_B, y, LARG, H_B, f"{i + 1}.  {tb}", cb, xb, tam=10)
    if i < len(PRO) - 1:
        for col in (COL_A, COL_B):
            c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                        Emu(col.emu + int(LARG.emu / 2)), Emu(y.emu + H_B.emu),
                                        Emu(col.emu + int(LARG.emu / 2)), Emu(y.emu + H_B.emu + GAP.emu))
            c.line.color.rgb = CINZA_MED; c.line.width = Pt(1)

seta = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Emu(col_x(5).emu + Emu(45720).emu),
                           Emu(3474720), Emu(320040), Emu(182880))
seta.fill.solid(); seta.fill.fore_color.rgb = CINZA_MED
seta.line.fill.background(); sem_sombra(seta)
leitura(sl, Emu(5257800),
        "A diferenca entre os dois regimes nao e a ordem das camadas - e a condicao: no sequencial somem as travas de cobertura e some o alvo.")
rodape(sl, "Clausulas 6.5.1 (28 degraus) e 6.5.2 (21 degraus) do 2o Aditamento ao Termo de Securitizacao da 2a emissao Kanastra, consolidado e registrado na JUCEMG em 10/06/2025. Resumo por camada; a sequencia literal completa esta na aba 06b do workbook.")

# ============================================================ 8. Subordinada
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Retencao de risco", "Quando a subordinada da originadora pode sair",
          "Nos sete FIDCs ela ja recebeu principal. Nos CRIs a saida nao depende de pedido nem de quorum - e automatica, mas condicionada.")
cab = ["Veiculo", "Quem decide", "Testes exigidos", "Trava", "Principal ja pago"]
linhas = [
    ["FIDC I", "Cotista subordinado pede;\nadministrador autoriza", "Pisos, cobertura e ausencia de evento", "Limites do regulamento", "R$ 130,4 mi"],
    ["FIDC II", "Cotista subordinado", "Metas, indices e liquidez pro forma", "Antes do sequencial, se enquadrado", "R$ 160,8 mi"],
    ["FIDC III", "Cotista subordinado", "Subordinacao, cobertura e ausencia de evento", "Pro rata vigente", "R$ 101,4 mi"],
    ["FIDC IV", "Regra publica incompleta", "n/d no acervo", "n/d", "R$ 438,9 mi"],
    ["FIDC V", "Cotista subordinado", "Indices, caixa e ausencia de evento", "Limites do regulamento", "R$ 34,4 mi"],
    ["FIDC VI", "Titulares de 75% da junior", "Subordinacao e cobertura pro forma;\nreserva de MTM; sem eventos", "136,0% / 113,3% / 106,3%", "R$ 183,2 mi"],
    ["FIDC VII", "Titulares de 75% da junior", "Mesmos testes do VI", "3 meses apos Evento de Venda", "R$ 7,7 mi"],
    ["CRI-II", "Automatico na Data de Pagamento", "As quatro Razoes de Cobertura enquadradas\ne saldo acima do Target", "Carencia ate o 13o pagamento", "R$ 6,8 mi"],
]
tabela(sl, MARGEM, Emu(1417320), col_w(12), Emu(3474720), cab, linhas,
       larguras=[0.11, 0.20, 0.33, 0.22, 0.14], tam=9, tam_cab=9.5,
       altura_cab=Emu(274320), altura_linha=Emu(365760), alinh_centro=(4,))
leitura(sl, Emu(5029200),
        "R$ 1,06 bi de mezanino e junior ja saiu dos sete fundos. A ocorrencia comprova extracao economica; a aderencia contratual, nao.")
txt(sl, MARGEM, Emu(5440680), UTIL_W, Emu(640080),
    "O que falta para fechar: os demonstrativos dos testes de subordinacao, cobertura e reservas na data de cada amortizacao. "
    "Sem eles, sabe-se que o principal saiu, mas nao se cada saida respeitou os pisos naquela competencia. "
    "No CRI ha um detalhe estrutural adicional: a serie Subordinado Jr. recebe o Premio Final - todo o remanescente do patrimonio separado - "
    "depois que as series publicas sao resgatadas, o que faz sua taxa declarada subestimar o retorno economico.",
    tam=10.5, cor=CINZA_ESC, espaco=3)
rodape(sl, "Principal subordinado observado nos informes mensais ate 31/07/2026 (FIDCs) e 01/05/2026 (CRI-II). " + FONTE_PADRAO)

# ============================================================ 9. PDD e efeito vagao
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Risco de credito", "Duas curvas de provisao, e por que a razao passa de 100%",
          "A curva posterior reconhece mais perda entre 91 e 180 dias. Reconhecimento mais conservador, nao piora do ativo.")
gr_dados = CategoryChartData()
gr_dados.categories = ["Ate 15d", "16-30", "31-60", "61-90", "91-120", "121-150", "151-180", "> 180"]
gr_dados.add_series("Curva inicial  CRI-I e CRI-II", (0.0, 1.0, 3.0, 10.0, 30.0, 50.0, 70.0, 100.0))
gr_dados.add_series("Curva posterior  CRI-III a CRI-VI", (0.0, 1.5, 5.0, 10.0, 37.0, 58.0, 78.0, 100.0))
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MARGEM, Y_CORPO, col_w(7), Emu(3200400), gr_dados)
gr = gf.chart
estilizar_gr(gr, [CINZA_CLARO, LARANJA])
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9)

txt(sl, col_x(7), Y_CORPO, col_w(5), Emu(320040), "Por que PDD / >90d passa de 100%", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(7), Emu(1783080), col_w(5), Emu(1828800),
    "Dois mecanismos distintos, ambos contratuais:\n\n"
    "Primeiro, a provisao incide sobre o valor presente do recebivel - o saldo que resta da CCB - e nao sobre a parcela vencida. "
    "O numerador mede contrato inteiro; o denominador, so as parcelas atrasadas.\n\n"
    "Segundo, o Efeito Vagao: se um devedor atrasa em um contrato, todos os contratos dele passam a ser tratados pelo pior atraso, "
    "inclusive os que estao em dia.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
tabela(sl, col_x(7), Emu(3657600), col_w(5), Emu(914400),
       ["Veiculo", "PDD/carteira", "PDD / >90d"],
       [["FIDC IV", "69,9%", "550%"], ["FIDC VI", "48,8%", "581%"], ["FIDC VII", "0,2%", "3.725%"]],
       larguras=[0.40, 0.30, 0.30], tam=10, alinh_centro=(1, 2), altura_linha=Emu(228600))
leitura(sl, Emu(4937760),
        "A razao PDD sobre saldo vencido nao e cobertura de perda: e o efeito de dois denominadores diferentes somado ao arrasto entre contratos do mesmo devedor.")
txt(sl, MARGEM, Emu(5349240), UTIL_W, Emu(548640),
    "A inadimplencia por safra que as laminas descrevem tem outro denominador ainda - o total originado na safra - e separa perda bruta de perda liquida, "
    "sendo a diferenca as recuperacoes apos 90 dias. As duas metricas nao se comparam e estao em linhas separadas do workbook.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Tabelas de PDD por faixa de atraso dos Prospectos Definitivos da 1a e 2a emissoes; definicao de Efeito Vagao literal do mesmo documento. " + FONTE_PADRAO)

# ============================================================ 10. Concentracao
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Granularidade", "Dois limites, duas ordens de grandeza",
          "O limite ANBIMA de 20% por devedor classifica a operacao como pulverizada. Quem realmente morde e o cap contratual.")
gr_dados = CategoryChartData()
gr_dados.categories = ["CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V\n(pool maduro)", "CRI-VI"]
gr_dados.add_series("Cap contratual por devedor (% do Patrimonio Separado)", (0.10, 0.10, 0.10, 0.25, 0.07, 0.11))
gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MARGEM, Y_CORPO, col_w(7), Emu(2925763), gr_dados)
gr = gf.chart
estilizar_gr(gr, [LARANJA], legenda=False)
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9)
gr.plots[0].has_data_labels = True
gr.plots[0].data_labels.font.size = Pt(9.5)
gr.plots[0].data_labels.font.color.rgb = PRETO

txt(sl, col_x(7), Y_CORPO, col_w(5), Emu(320040), "O escalonamento de CRI-V", tam=13, negrito=True, cor=PRETO)
tabela(sl, col_x(7), Emu(1783080), col_w(5), Emu(731520),
       ["Integralizacao", "Cap por devedor"],
       [["Ate 470.600 cotas", "0,15%"], ["A partir de 750.000 cotas", "0,07%"]],
       larguras=[0.62, 0.38], tam=10.5, alinh_centro=(1,), altura_linha=Emu(274320))
txt(sl, col_x(7), Emu(2651760), col_w(5), Emu(1600200),
    "CRI-V e a unica operacao que amarra a granularidade ao tamanho: quanto mais integralizada a emissao, "
    "mais apertado o limite por devedor.\n\n"
    "No inicio o limite e mais folgado que o de CRI-III (0,15% contra 0,10%). Com o pool maduro fica 30% mais "
    "granular (0,07% contra 0,10%). Os dois numeros medem momentos diferentes da mesma emissao e nao devem ser "
    "comparados isoladamente.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
leitura(sl, Emu(4754880),
        "O cap ANBIMA de 20% esta 80 a 285 vezes acima do contratual. Nao cabe no mesmo grafico, e nao e ele que define a granularidade do pool.")
txt(sl, MARGEM, Emu(5166360), UTIL_W, Emu(731520),
    "Classificacao ANBIMA identica nas seis operacoes: concentracao Pulverizada, categoria Hibrido, segmento I - Outros, "
    "tipo de contrato com lastro C, por serem lastreadas em Cedulas de Credito Bancario.\n"
    "A concentracao efetivamente observada em cada pool nao e publicada em nenhuma das seis - a folga contra o limite permanece n/d.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Caps contratuais das laminas de CRI-I, III e V; CRI-II, IV e VI conforme analise de credito. Classificacao ANBIMA literal do Comunicado ao Mercado da 2a emissao. " + FONTE_PADRAO)

# ============================================================ 11. Matriz FIDC -> CRI
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Cessoes", "Quais fundos cederam para quais operacoes",
          "Estados em texto, nao em cor. 'Cedeu' significa cessao documentada; 'pode ceder' significa mandato compativel, sem cessao registrada.")
c, r = ler("11_matriz_fidc_cri.csv")
CRIS = ["CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI"]
FIDCS = ["FIDC-I", "FIDC-II", "FIDC-III", "FIDC-IV", "FIDC-V", "FIDC-VI", "FIDC-VII"]
est = {(x[0], x[1]): x[2] for x in r}
CURTO = {"Cedeu": "Cedeu", "Pode ceder": "Pode ceder", "Nao elegivel no mandato integral": "Nao elegivel"}
cab = ["FIDC"] + ["Kanastra 1a", "Kanastra 2a", "Kanastra 3a", "Kanastra 4a", "VERT 174a", "VERT 177a"]
linhas = [[f.replace("FIDC-", "FIDC ")] + [CURTO.get(est.get((f, k), "n/d"), "n/d") for k in CRIS] for f in FIDCS]
tb = tabela(sl, MARGEM, Emu(1417320), col_w(12), Emu(2560320), cab, linhas,
            larguras=[0.16] + [0.14] * 6, tam=10, altura_cab=Emu(320040),
            altura_linha=Emu(310896), alinh_centro=(1, 2, 3, 4, 5, 6))
for i in range(1, len(FIDCS) + 1):
    for j in range(1, 7):
        cel = tb.cell(i, j)
        if cel.text_frame.paragraphs[0].runs[0].text == "Cedeu":
            cel.fill.solid(); cel.fill.fore_color.rgb = LARANJA_CLA

txt(sl, MARGEM, Emu(4114800), col_w(6), Emu(320040), "O que e documento e o que e deducao", tam=13, negrito=True, cor=PRETO)
txt(sl, MARGEM, Emu(4480560), col_w(6), Emu(1188720),
    "Apenas CRI-I e CRI-II tem os cedentes nomeados em documento primario: os Prospectos Definitivos definem 'Cedentes' "
    "como o Green Solfacil II e o Green Solfacil IV, e listam os dois como representantes de mais de 10% dos direitos "
    "creditorios cedidos.\n\n"
    "As demais celulas 'Cedeu' vem da analise de credito de 21/08/2026, nao dos documentos de oferta.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
txt(sl, col_x(6), Emu(4114800), col_w(6), Emu(320040), "O rastro do Cedente Fundo em CRI-V", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(6), Emu(4480560), col_w(6), Emu(1188720),
    "A lamina de CRI-V registra que os Criterios de Elegibilidade sao verificados com dados enviados eletronicamente "
    "pela Gestora do Cedente Fundo e pela Solfacil, e pela instituicao custodiante do respectivo cedente.\n\n"
    "E evidencia textual de que ha um FIDC cedente - mas o documento nao o nomeia. O nome esta no Termo de "
    "Securitizacao, que precisa ser obtido no Fundos.NET.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
rodape(sl, "Volume cedido, percentual do pool e preco por lote sao n/d nas seis operacoes: o ledger de cessoes nao e publico. FIDC V marcado como nao elegivel no mandato integral por admitir CPR-F e prazo de ate 4.760 dias, acima do teto de 3.845 dias dos CRI.")

# ============================================================ 12. Curva de morte
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Amortizacao", "A curva de morte da unica serie com cronograma contratual",
          "Das cinco series de CRI-II, so a Super Senior tem percentual de amortizacao no Anexo I. As outras quatro amortizam ate um saldo alvo.")
c, r = ler("13_cronograma_pagamentos.csv")
s1 = [x for x in r if x[1] == "1a"]
cats, vals = [], []
for x in s1:
    n = int(x[3])
    if n % 4 == 0 or n == 1:
        cats.append(x[4] if x[4] != "Data de Vencimento" else "Venc.")
        vals.append(float(x[8]))
gr_dados = CategoryChartData()
gr_dados.categories = cats
gr_dados.add_series("Saldo remanescente (% do valor nominal unitario)", vals)
gf = sl.shapes.add_chart(XL_CHART_TYPE.AREA, MARGEM, Y_CORPO, col_w(8), Emu(3383280), gr_dados)
gr = gf.chart
estilizar_gr(gr, [LARANJA], legenda=False)
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(8)

txt(sl, col_x(8), Y_CORPO, col_w(4), Emu(320040), "O ponto que dispara o resgate", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(8), Emu(1783080), col_w(4), Emu(1417320),
    "O saldo cruza 2% do valor nominal unitario - ou seja, 98% amortizado - no 59o dos 60 pagamentos, em 08/05/2029.\n\n"
    "A partir dali a emissora constitui a Reserva para Resgate Antecipado e a serie e resgatada integralmente na "
    "data seguinte, um pagamento antes do vencimento.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
tabela(sl, col_x(8), Emu(3383280), col_w(4), Emu(1005840),
       ["Serie de CRI-II", "Cronograma"],
       [["1a  Super Senior", "60 datas com %"], ["2a  Senior", "96 datas, sem %"],
        ["3a e 4a", "120 datas, sem %"], ["5a  Sub. Jr.", "144 datas, sem %"]],
       larguras=[0.52, 0.48], tam=9.5, altura_linha=Emu(228600))
leitura(sl, Emu(4937760),
        "A ausencia de percentual nas outras quatro series nao e lacuna documental: elas amortizam ate um Saldo Devedor Target, entao o Anexo I delas e calendario, nao curva de principal.")
txt(sl, MARGEM, Emu(5349240), UTIL_W, Emu(548640),
    "A curva realizada por camada nao pode ser desenhada: o publico disponivel e agregado - primeira e ultima ocorrencia, meses com pagamento e total por camada - "
    "e nao a serie mes a mes. Ate 01/05/2026, CRI-II ja amortizou R$ 258,7 mi de Senior, R$ 31,7 mi de Mezanino, R$ 7,8 mi de Subordinado e R$ 6,8 mi de Subordinado Jr.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Anexo I do 2o Aditamento ao Termo de Securitizacao da 2a emissao Kanastra: 540 linhas de cronograma, 60 delas com percentual contratual. Saldo reconstruido por composicao dos percentuais sobre o saldo remanescente; fecha em zero no vencimento.")

# ============================================================ 13. Custo e evolucao do spread
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Custo de captacao", "O spread caiu nas duas camadas comparaveis",
          "Series indexadas a 100% do DI, unicas comparaveis entre operacoes sem recorrer a curva de juros.")
gr_dados = CategoryChartData()
gr_dados.categories = ["Kanastra 2a\njun/2024", "Kanastra 3a\nmai/2025", "Kanastra 4a\nset/2025",
                       "VERT 174a\nmai/2026", "VERT 177a\njul/2026"]
gr_dados.add_series("Mezanino  DI + %", (6.00, 5.75, 5.50, 5.50, 5.50))
gr_dados.add_series("Subordinado  DI + %", (10.00, 10.00, 10.00, 8.00, 8.00))
gf = sl.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, MARGEM, Y_CORPO, col_w(7), Emu(3200400), gr_dados)
gr = gf.chart
estilizar_gr(gr, [LARANJA, CINZA_ESC])
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9)
for s in gr.series:
    s.format.line.width = Pt(2.25)
    s.smooth = False

txt(sl, col_x(7), Y_CORPO, col_w(5), Emu(320040), "O que nao da para calcular", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(7), Emu(1783080), col_w(5), Emu(1691640),
    "O custo all-in de cada estrutura fica n/d, e a lacuna e nomeavel.\n\n"
    "Falta a curva DI futura da B3 em cada data-base: sem ela nao se poe pre-fixado, percentual do DI e DI mais spread "
    "na mesma regua. Quatro das seis operacoes tem series pre-fixadas.\n\n"
    "Falta tambem o custo fixo por veiculo - administracao, gestao, custodia, auditoria, rating, agente fiduciario "
    "e distribuicao amortizada. Nenhum e publico.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
tabela(sl, col_x(7), Emu(3566160), col_w(5), Emu(731520),
       ["Perna que prevaleceu no bookbuilding", "Operacao"],
       [["Perna indexada ao DI futuro", "CRI-I e CRI-V"], ["Piso fixo da lamina", "CRI-III"]],
       larguras=[0.62, 0.38], tam=10, altura_linha=Emu(274320))
leitura(sl, Emu(4937760),
        "A queda de spread e consistente com melhora de percepcao de risco, mas o dado publico nao sustenta a causalidade: mudaram tambem o indexador, a camada e o ciclo de juros.")
txt(sl, MARGEM, Emu(5349240), UTIL_W, Emu(548640),
    "Um detalhe do bookbuilding que o intervalo da lamina esconde: em CRI-III as duas series pre-fixadas pararam exatamente no piso - 15,50% e 16,50% - "
    "enquanto em CRI-I e CRI-V a perna indexada ao DI futuro prevaleceu em todas. O piso da lamina foi restricao ativa em uma das tres operacoes com intervalo publicado.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "CRI-I fora do grafico: suas quatro series publicas sao pre-fixadas e nao ha spread sobre DI a comparar. " + FONTE_PADRAO)

# ============================================================ 14. Antes x depois do take-out
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Efeito do take-out", "O que mudou nos dois FIDCs cedentes",
          "Janela de duas competencias em torno da emissao da VERT 177a. As competencias t-3 a t+3 nao existem: o evento e a ultima competencia disponivel.")
gr_dados = CategoryChartData()
gr_dados.categories = ["30/06/2026\n(antes)", "31/07/2026\n(competencia do take-out)"]
gr_dados.add_series("PL FIDC VI", (437.4, 211.1))
gr_dados.add_series("Carteira FIDC VI", (399.3, 147.7))
gr_dados.add_series("PL FIDC VII", (564.7, 619.6))
gr_dados.add_series("Carteira FIDC VII", (544.1, 446.1))
gf = sl.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, MARGEM, Y_CORPO, col_w(7), Emu(3017520), gr_dados)
gr = gf.chart
estilizar_gr(gr, [PRETO, CINZA_MED, LARANJA_ESC, LARANJA])
gr.value_axis.has_major_gridlines = True
gr.value_axis.major_gridlines.format.line.color.rgb = CINZA_CLARO
gr.value_axis.major_gridlines.format.line.width = Pt(0.5)
gr.value_axis.tick_labels.font.size = Pt(9)
gr.category_axis.tick_labels.font.size = Pt(9.5)
for s in gr.series:
    s.format.line.width = Pt(2.25)
    s.smooth = False

txt(sl, col_x(7), Y_CORPO, col_w(5), Emu(320040), "O que os dados mostram", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(7), Emu(1783080), col_w(5), Emu(1005840),
    "A carteira dos dois fundos cai R$ 349,0 mi somada e outros ativos liquidos sobem R$ 185,4 mi. "
    "O padrao e consistente com uma cessao: sai recebivel, entra caixa.",
    tam=10.5, cor=CINZA_ESC, espaco=4)
txt(sl, col_x(7), Emu(2926080), col_w(5), Emu(320040), "O que os dados nao permitem afirmar", tam=13, negrito=True, cor=PRETO)
txt(sl, col_x(7), Emu(3291840), col_w(5), Emu(1417320),
    "Que a qualidade do que ficou piorou. A PDD sobre carteira de 48,8% no FIDC VI pode ser deterioracao real ou "
    "simples efeito de denominador - vender a parte boa reduz o denominador e eleva a razao sem que nada tenha piorado.\n\n"
    "Sem o tape por CCB nao ha como separar cherry-pick de mudanca de denominador. O informe do VI tambem nao "
    "decompoe a queda de PL.",
    tam=10.5, cor=CINZA_ESC, espaco=5)
leitura(sl, Emu(4937760),
        "Uma ponte de duas competencias reconcilia valores; nao atribui causa. Para fechar a pergunta faltam a memoria contabil do FIDC VI e o ledger de cessoes por lote.")
rodape(sl, "CVM - Informe Mensal FIDC, competencias de 30/06/2026 e 31/07/2026, conforme analise de credito de 21/08/2026. Emissao da VERT 177a em 31/07/2026.")

# ============================================================ 15. Veredito FIDC x CRI
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Veredito", "Onde o CRI ganha, onde nao ganha, e o que nao da para afirmar",
          "Doze dimensoes comparadas. A terceira coluna e a que importa: o que ainda falta para fechar cada uma.")
c, r = ler("15_fidc_vs_cri.csv")
linhas = [[x[0], x[3], x[5]] for x in r]
tabela(sl, MARGEM, Emu(1417320), col_w(12), Emu(3931920),
       ["Dimensao", "Vantagem real", "O que falta para confirmar"], linhas,
       larguras=[0.24, 0.13, 0.63], tam=8.5, tam_cab=9.5,
       altura_cab=Emu(274320), altura_linha=Emu(274320), alinh_centro=(1,))
leitura(sl, Emu(5486400),
        "Cinco dimensoes favorecem o CRI, quatro favorecem o FIDC e tres nao tem veredito com dado publico. Nenhuma conclusao de custo e possivel sem a curva de juros.")
rodape(sl, "Detalhe de como cada dimensao funciona em cada veiculo, com a evidencia de cada linha, na aba 15_FIDC_vs_CRI do workbook. " + FONTE_PADRAO)

# ============================================================ 16. Lacunas
sl = prs.slides.add_slide(VAZIO)
cabecalho(sl, "Proximo passo", "O que falta e a quem pedir",
          "Dez itens em ordem de prioridade. Os quatro primeiros bloqueiam conclusoes que este deck deliberadamente nao tira.")
c, r = ler("20_lacunas.csv")
linhas = [[x[0], x[1], x[3]] for x in r]
tabela(sl, MARGEM, Emu(1417320), col_w(12), Emu(3566160),
       ["#", "O que falta", "A quem pedir"], linhas,
       larguras=[0.05, 0.63, 0.32], tam=9, tam_cab=9.5,
       altura_cab=Emu(274320), altura_linha=Emu(320040), alinh_centro=(0,))
txt(sl, MARGEM, Emu(5120640), col_w(12), Emu(320040), "Divergencias registradas e resolvidas", tam=13, negrito=True, cor=PRETO)
txt(sl, MARGEM, Emu(5440680), UTIL_W, Emu(731520),
    "Dez casos foram testados contra as fontes. Em cinco nao havia divergencia real, apenas perimetro diferente - o mais importante e o total de series: "
    "os anuncios de oferta contam so as series publicas, e somando a serie privada de cada operacao chega-se exatamente a 34, sem forcar nenhum numero. "
    "Os cinco casos com divergencia efetiva estao na aba 16_Conflitos, com a decisao adotada e a justificativa de cada uma.",
    tam=11, cor=CINZA_ESC, espaco=3)
rodape(sl, "Lista completa na aba 20_Lacunas do workbook; inventario de fontes, incluindo as buscas sem resultado, na aba 17_Fontes.")

# ---------------------------------------------------------------- salvar
os.makedirs(OUTDIR, exist_ok=True)
caminho = os.path.join(OUTDIR, "Solfacil_CRI_FIDC_20260822_claude.pptx")
prs.save(caminho)
print(f"Deck salvo: {caminho}")
print(f"Slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")
