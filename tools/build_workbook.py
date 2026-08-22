# -*- coding: utf-8 -*-
"""Monta o workbook analitico a partir de data/solfacil/*.csv.

Paleta unica: laranja, preto e tons de cinza. Nenhum verde, vermelho ou azul.
Toda tabela e ListObject nomeado tbl_*. Todo grafico e nativo.
"""
import csv, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, LineChart, AreaChart, Reference, Series
from openpyxl.chart.marker import Marker
from openpyxl.drawing.line import LineProperties
from openpyxl.chart.shapes import GraphicalProperties

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "solfacil_claude")
OUTDIR = os.path.join(ROOT, "outputs", "solfacil")

# ---------------------------------------------------------------- paleta
LARANJA      = "FFBC00"
LARANJA_ESC  = "C08F00"
LARANJA_CLA  = "FFE08A"
PRETO        = "000000"
CINZA_ESC    = "323436"
CINZA_MED    = "6E6E6E"
CINZA_CLARO  = "BFBFBF"
CINZA_FUNDO  = "F2F2F2"
BRANCO       = "FFFFFF"

F_TITULO  = Font(name="Calibri", size=15, bold=True, color=PRETO)
F_LEITURA = Font(name="Calibri", size=10.5, color=CINZA_ESC)
F_META    = Font(name="Calibri", size=9, italic=True, color=CINZA_MED)
F_CAB     = Font(name="Calibri", size=10, bold=True, color=BRANCO)
F_CORPO   = Font(name="Calibri", size=10, color=PRETO)
F_SUB     = Font(name="Calibri", size=11, bold=True, color=PRETO)

FILL_CAB  = PatternFill("solid", fgColor=CINZA_ESC)
FILL_FAIXA = PatternFill("solid", fgColor=LARANJA)
BORDA_BASE = Border(bottom=Side(style="thin", color=CINZA_CLARO))


def ler(nome):
    with open(os.path.join(DATA, nome), encoding="utf-8") as fh:
        r = list(csv.reader(fh))
    return r[0], r[1:]


def numerico(v):
    if not isinstance(v, str):
        return v
    if v in ("n/d", "n/a", "", None):
        return v
    t = v.replace(".", "").replace(",", ".") if (v.count(",") == 1 and v.replace(",", "").replace(".", "").replace("-", "").isdigit()) else v
    try:
        f = float(t)
        return int(f) if f == int(f) and abs(f) < 1e15 and "." not in t else f
    except ValueError:
        return v


def aba(wb, nome, titulo, leitura, meta):
    ws = wb.create_sheet(nome)
    ws.sheet_view.showGridLines = False
    ws["A1"] = titulo; ws["A1"].font = F_TITULO
    ws["A2"] = leitura; ws["A2"].font = F_LEITURA
    ws["A3"] = meta; ws["A3"].font = F_META
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 30
    ws["A2"].alignment = Alignment(vertical="top", wrap_text=False)
    return ws


def tabela(ws, cols, rows, nome_tabela, linha0=5, larguras=None, wrap_cols=()):
    """Escreve uma tabela nativa comecando em linha0. Devolve (primeira_linha_dados, ultima_linha)."""
    for j, c in enumerate(cols, start=1):
        cel = ws.cell(row=linha0, column=j, value=c)
        cel.font = F_CAB; cel.fill = FILL_CAB
        cel.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[linha0].height = 30
    for i, r in enumerate(rows, start=linha0 + 1):
        for j, v in enumerate(r, start=1):
            cel = ws.cell(row=i, column=j, value=numerico(v))
            cel.font = F_CORPO
            cel.border = BORDA_BASE
            if cols[j - 1] in wrap_cols:
                cel.alignment = Alignment(vertical="top", wrap_text=True)
            else:
                cel.alignment = Alignment(vertical="top")
    fim = linha0 + len(rows)
    ref = f"A{linha0}:{get_column_letter(len(cols))}{fim}"
    t = Table(displayName=nome_tabela, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=False,
                                      showColumnStripes=False, showFirstColumn=False, showLastColumn=False)
    ws.add_table(t)
    if larguras:
        for letra, w in larguras.items():
            ws.column_dimensions[letra].width = w
    else:
        for j, c in enumerate(cols, start=1):
            largura = max(12, min(40, len(c) + 4))
            if rows:
                largura = max(largura, min(46, max(len(str(r[j - 1])) for r in rows[:60]) + 2))
            ws.column_dimensions[get_column_letter(j)].width = largura
    ws.freeze_panes = ws.cell(row=linha0 + 1, column=1)
    return linha0 + 1, fim


def nota(ws, linha, texto):
    ws.cell(row=linha, column=1, value=texto).font = F_LEITURA
    ws.cell(row=linha, column=1).alignment = Alignment(vertical="top", wrap_text=False)


def estilo_serie(s, cor, linha=False):
    gp = GraphicalProperties(solidFill=cor)
    gp.line = LineProperties(solidFill=cor, w=22000) if linha else LineProperties(noFill=True)
    s.graphicalProperties = gp


# ================================================================ construcao
wb = Workbook()
wb.remove(wb.active)
DB = "Data-base: FIDCs em 31/07/2026 | CRIs na ultima competencia por operacao | escopo publico ate 22/08/2026"

# ---------------------------------------------------------------- 00_Painel
c, r = ler("00_painel.csv")
ws = aba(wb, "00_Painel", "Painel do programa Solfacil",
         "Sete FIDCs financiam a carteira enquanto ela e originada; seis operacoes de CRI compram pools fechados e alongam o funding. O quadro abaixo so traz numeros detalhados nas abas seguintes.",
         DB + " | Fontes: ver 17_Fontes")
ini, fim = tabela(ws, c, r, "tbl_00_Painel", larguras={"A": 42, "B": 14, "C": 24, "D": 74, "E": 14, "F": 30},
                  wrap_cols=("leitura",))

linha = fim + 3
ws.cell(row=linha, column=1, value="MAPA DO PROGRAMA").font = F_SUB
linha += 1
mapa = [
    ("1. ORIGINACAO", "Solfacil e cerca de 4 mil integradores | CCB pre-fixada de PF e PJ | destinacao a sistema fotovoltaico"),
    ("2. WAREHOUSE", "FIDCs I a VII | compram e financiam a carteira durante a originacao | revolvencia e reinvestimento"),
    ("3. TAKE-OUT", "Kanastra 1a a 4a e VERT 174a e 177a | cessao definitiva sem coobrigacao | novo patrimonio separado por emissao"),
    ("4. INVESTIDORES", "Super Senior ate Subordinado Jr. | series publicas ao mercado e serie privada retida pela originadora"),
]
for nome_etapa, desc in mapa:
    cel = ws.cell(row=linha, column=1, value=nome_etapa)
    cel.font = Font(name="Calibri", size=10, bold=True, color=PRETO)
    cel.fill = FILL_FAIXA
    cel.alignment = Alignment(vertical="center", horizontal="center")
    ws.cell(row=linha, column=2, value=desc).font = F_CORPO
    ws.row_dimensions[linha].height = 18
    linha += 1

linha += 2
ws.cell(row=linha, column=1, value="INDICE DAS ABAS").font = F_SUB
linha += 1
INDICE = [
    ("01_Veiculos", "Um a um: os 7 FIDCs e as 6 operacoes de CRI, com prestadores e coordenadores"),
    ("02_Series", "As 34 series de CRI e as 34 classes de cotas de FIDC, com taxa, prazo e rating"),
    ("03_Elegibilidade", "Criterio a criterio, com a redacao literal, e o que mudou entre operacoes"),
    ("04_Concentracao", "Cap contratual por devedor contra o limite ANBIMA"),
    ("05_Prazos_WAM", "O descasamento de prazo na mesma escala de meses"),
    ("06_Waterfall", "A ordem de pagamentos nos dois regimes"),
    ("06b_Waterfall_Visual", "Os dois regimes lado a lado, degrau a degrau"),
    ("07_Subordinada", "Quando a subordinada pode sair e o que ja saiu"),
    ("08_PDD", "Provisao por faixa de atraso e o efeito vagao"),
    ("09_Eventos", "Gatilhos de desalavancagem, resgate e recompra"),
    ("09b_Garantias", "Onde esta a garantia real - e onde nao esta"),
    ("10_Subscritores", "Quem comprou na emissao, por tipo de investidor"),
    ("11_Matriz_FIDC_CRI", "Quais fundos cederam e quais poderiam ceder para cada CRI"),
    ("11b_Cessoes", "Uma linha por cessao documentada"),
    ("12_Custo_Captacao", "Taxa por serie e evolucao do spread por camada"),
    ("13_Cronograma", "A curva de amortizacao projetada e o que ja foi pago"),
    ("14_Antes_Depois", "O que mudou nos FIDCs cedentes depois do take-out"),
    ("15_FIDC_vs_CRI", "Onde o CRI ganha, onde nao ganha e o que nao da para afirmar"),
    ("16_Conflitos", "Divergencias entre fontes e a decisao adotada em cada uma"),
    ("17_Fontes", "O inventario completo, incluindo o que nao foi localizado"),
    ("18_Metodologia", "A formula e o qualificador de cada metrica"),
    ("19_Glossario", "O jargao em portugues direto"),
    ("20_Lacunas", "O que falta e a quem pedir"),
]
for nm, desc in INDICE:
    cel = ws.cell(row=linha, column=1, value=nm)
    cel.font = Font(name="Calibri", size=10, color=PRETO, underline="single")
    cel.hyperlink = f"#'{nm if nm != '13_Cronograma' else '13_Cronograma_Pagamentos'}'!A1"
    ws.cell(row=linha, column=2, value=desc).font = F_CORPO
    linha += 1

# ---------------------------------------------------------------- 01_Veiculos
c, r = ler("01_veiculos.csv")
ws = aba(wb, "01_Veiculos", "Veiculos do programa",
         "Uma linha por veiculo. Os FIDCs II e IV sao os unicos cujo nome oficial e CNPJ constam de documento primario - eles aparecem nomeados nos Prospectos das duas primeiras emissoes de CRI.",
         DB)
tabela(ws, c, r, "tbl_01_Veiculos", wrap_cols=("demais_coordenadores", "participantes_especiais", "agente_fiduciario", "escriturador", "coordenador_lider", "nome_oficial", "administrador"))

# ---------------------------------------------------------------- 02_Series
c, r = ler("02_series.csv")
ws = aba(wb, "02_Series", "Series de CRI e classes de cotas de FIDC",
         "34 series de CRI (5+5+6+7+6+5) e 34 classes de cotas de FIDC. Sao dimensoes diferentes e nao se somam. Lote base, quantidade subscrita e valor reportado ficam em colunas separadas: teto de oferta nunca e colocacao realizada.",
         DB + " | Fontes: laminas, comunicados, prospectos e ANX-DECK")
tabela(ws, c, r, "tbl_02_Series", wrap_cols=("taxa_teto_lamina", "taxa_contratada", "perna_que_prevaleceu", "rating_nota", "quantidade_ofertada_lote_base", "fonte_id"))

# ---------------------------------------------------------------- 03_Elegibilidade
c, r = ler("03_elegibilidade.csv")
ws = aba(wb, "03_Elegibilidade", "Criterios de elegibilidade, criterio a criterio",
         "O cap por devedor endureceu de CRI-III para CRI-V e passou a ser escalonado pela integralizacao: 0,15% no inicio, 0,07% com o pool maduro - 30% mais granular que o limite fixo de 0,10% de CRI-III. CRI-V tambem introduziu a vedacao a parcela balao e o enquadramento do PJ na Resolucao CMN 5.118, que CRI-III nao trazia.",
         DB + " | Redacao literal das laminas de CRI-I, CRI-III e CRI-V")
ini, fim = tabela(ws, c, r, "tbl_03_Elegibilidade",
                  wrap_cols=("cap_individual_pct_patrimonio_separado", "taxa_retorno_minima_pro_forma",
                             "quem_atesta_elegibilidade", "vedacoes_expressas", "redacao_literal",
                             "adimplencia_na_cessao", "amortizacao_mensal_sem_balao", "enquadramento_PJ"))
linha = fim + 3
ws.cell(row=linha, column=1, value="LINHAS DERIVADAS: O QUE APERTA E QUANTO").font = F_SUB
c2, r2 = ler("03b_elegibilidade_deltas.csv")
tabela(ws, c2, r2, "tbl_03b_Deltas", linha0=linha + 1,
       wrap_cols=("o_que_muda", "leitura_de_credito"))
ws.column_dimensions["B"].width = 80
ws.column_dimensions["C"].width = 70
nota(ws, linha + 1 + len(r2) + 3,
     "Nota: em CRI-V os Criterios de Elegibilidade sao verificados sobre dados enviados pela Gestora do Cedente Fundo - evidencia textual de que o cedente e um FIDC, e nao apenas a originadora direta.")

# ---------------------------------------------------------------- 04_Concentracao
import solfacil_criterios as C_
c, r = ler("04_concentracao.csv")
ws = aba(wb, "04_Concentracao", "Concentracao: limite contratual contra limite de mercado",
         C_.NOTA_CONCENTRACAO, DB)
ini, fim = tabela(ws, c, r, "tbl_04_Concentracao",
                  wrap_cols=("cap_individual_escalonado", "classificacao_ANBIMA"))
ws.column_dimensions["C"].width = 60
ws.column_dimensions["M"].width = 60

ch = BarChart(); ch.type = "bar"; ch.style = None
ch.title = "Cap individual por devedor, em % do Patrimonio Separado (escala logaritmica)"
ch.y_axis.title = "% do Patrimonio Separado"
dados = Reference(ws, min_col=2, min_row=ini - 1, max_row=ini + 5)
cats = Reference(ws, min_col=1, min_row=ini, max_row=ini + 5)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
estilo_serie(ch.series[0], LARANJA)
ch.legend = None; ch.height = 7.5; ch.width = 17
ws.add_chart(ch, f"A{fim + 3}")
nota(ws, fim + 20, "O limite ANBIMA de 20% por devedor nao aparece no grafico porque esta duas ordens de grandeza acima da escala contratual: seria uma barra 80 a 285 vezes maior que a maior das seis.")

# ---------------------------------------------------------------- 05_Prazos_WAM
c, r = ler("05_prazos_wam.csv")
ws = aba(wb, "05_Prazos_WAM", "Descasamento de prazo, tudo em meses",
         "O ativo pode ir a 3.845 dias (126 meses) por recebivel, com media ponderada de ate 2.000 dias (66 meses). O passivo tem vencimento legal de 58 a 144 meses, mas duration muito menor - e a duration varia por operacao, nao pelo programa: 38 a 43 meses em CRI-I, 59 a 119 em CRI-III e apenas 22 a 23 em CRI-V.",
         DB + " | Duration aproximada, sujeita a reducao por amortizacao extraordinaria")
ini, fim = tabela(ws, c, r, "tbl_05_Prazos")

# Grafico: series publicas de CRI com duration conhecida, na mesma escala de meses
sub = [(x[0], x[2], x[3], x[5], x[8], x[11], x[13]) for x in r
       if x[1] == "CRI" and x[13] not in ("n/d", "n/a", "")]
base = fim + 3
ws.cell(row=base, column=1, value="COMPARACAO NA MESMA ESCALA DE MESES").font = F_SUB
hdr = ["Serie", "WAM contratual max (meses)", "Prazo max do recebivel (meses)",
       "Duration (meses)", "Prazo legal da serie (meses)"]
linhas_g = [[f"{s[0]} {s[1]} {s[2]}", numerico(s[3]), numerico(s[4]), numerico(s[6]), numerico(s[5])] for s in sub]
gi, gf = tabela(ws, hdr, linhas_g, "tbl_05_Comparacao", linha0=base + 1)

ch = BarChart(); ch.type = "bar"; ch.grouping = "clustered"
ch.title = "Prazo do ativo contra prazo do passivo, por serie de CRI"
ch.x_axis.title = "Meses"
dados = Reference(ws, min_col=2, max_col=5, min_row=gi - 1, max_row=gf)
cats = Reference(ws, min_col=1, min_row=gi, max_row=gf)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
for s, cor in zip(ch.series, [CINZA_ESC, PRETO, LARANJA, CINZA_CLARO]):
    estilo_serie(s, cor)
ch.height = 16; ch.width = 26
ws.add_chart(ch, f"H{base + 1}")

# ---------------------------------------------------------------- 06_Waterfall
import solfacil_estrutura as E_
c, r = ler("06_waterfall.csv")
ws = aba(wb, "06_Waterfall", "Ordem de pagamentos",
         E_.NOTA_WATERFALL, DB + " | Unica ordem integralmente documentada: CRI-II (2o Aditamento ao Termo de Securitizacao)")
tabela(ws, c, r, "tbl_06_Waterfall",
       wrap_cols=("regime", "gatilho_de_mudanca_para_sequencial", "quem_recebe_juros_antes_de_principal",
                  "subordinado_jr_prioridade", "cash_sweep", "condicionalidade", "reserva_de_juros",
                  "reserva_para_resgate_antecipado", "senior_prioridade", "mezanino_prioridade",
                  "subordinado_prioridade", "nome_contratual"))

# ---------------------------------------------------------------- 06b_Waterfall_Visual
c, r = ler("06b_waterfall_degraus.csv")
ws = aba(wb, "06b_Waterfall_Visual", "Os dois regimes, degrau a degrau",
         "A esquerda, o regime pro rata condicionado: cada camada so recebe se as coberturas acima estiverem enquadradas, e recebe ate um saldo alvo. A direita, o sequencial: some a condicao de cobertura e some o alvo - a camada de cima e paga ate 98% antes de a proxima receber principal.",
         DB + " | Fonte: ANX-TS2-K2, clausulas 6.5.1 e 6.5.2")
pro = [x for x in r if x[1] == "Pro rata"]
seq = [x for x in r if x[1] == "Sequencial"]
ws.cell(row=5, column=1, value="REGIME PRO RATA CONDICIONADO").font = F_SUB
ws.cell(row=5, column=5, value="REGIME SEQUENCIAL").font = F_SUB
INTENS = {"Despesa": CINZA_CLARO, "SS": PRETO, "S": CINZA_ESC, "M": CINZA_MED, "Sub": LARANJA_ESC, "Jr": LARANJA, "Fim": CINZA_FUNDO}


def bloco(ws, linha, col, ordem, item, desc, cor, cor_texto=BRANCO):
    a = ws.cell(row=linha, column=col, value=f"{ordem}  {item}")
    a.fill = PatternFill("solid", fgColor=cor)
    a.font = Font(name="Calibri", size=9, bold=True, color=cor_texto)
    a.alignment = Alignment(vertical="center", horizontal="center")
    b = ws.cell(row=linha, column=col + 1, value=desc)
    b.font = Font(name="Calibri", size=9, color=PRETO)
    b.alignment = Alignment(vertical="center")


def cor_do_degrau(desc):
    d = desc.lower()
    if "despesa" in d or "investimentos permitidos" in d:
        return INTENS["Despesa"], PRETO
    if "premio final" in d:
        return INTENS["Jr"], PRETO
    if "5a serie" in d:
        return INTENS["Jr"], PRETO
    if "4a serie" in d:
        return INTENS["Sub"], BRANCO
    if "3a serie" in d:
        return INTENS["M"], BRANCO
    if "2a serie" in d:
        return INTENS["S"], BRANCO
    if "1a serie" in d:
        return INTENS["SS"], BRANCO
    if "extraordinaria" in d:
        return INTENS["Despesa"], PRETO
    return CINZA_FUNDO, PRETO


for i, x in enumerate(pro):
    cor, ct = cor_do_degrau(x[4])
    bloco(ws, 6 + i, 1, x[2], x[3], x[4], cor, ct)
for i, x in enumerate(seq):
    cor, ct = cor_do_degrau(x[4])
    bloco(ws, 6 + i, 5, x[2], x[3], x[4], cor, ct)
ws.column_dimensions["A"].width = 14; ws.column_dimensions["B"].width = 88
ws.column_dimensions["C"].width = 3
ws.column_dimensions["E"].width = 14; ws.column_dimensions["F"].width = 88
nota(ws, 6 + max(len(pro), len(seq)) + 2,
     "Legenda de intensidade: preto = Super Senior, cinza escuro = Senior, cinza medio = Mezanino, laranja escuro = Subordinado, laranja = Subordinado Jr., cinza claro = despesas e sobras. A cor indica a camada, nao risco nem severidade.")

# ---------------------------------------------------------------- 07_Subordinada
c, r = ler("07_subordinada.csv")
ws = aba(wb, "07_Subordinada", "Saque da subordinada: quando pode sair",
         E_.NOTA_SUBORDINADA, DB)
tabela(ws, c, r, "tbl_07_Subordinada",
       wrap_cols=("testes_exigidos", "indices_de_cobertura", "trava_temporal", "vedacoes_pos_evento",
                  "impacto_na_senior", "saque_permitido", "quem_solicita", "quorum"))

# ---------------------------------------------------------------- 08_PDD
c, r = ler("08_pdd.csv")
ws = aba(wb, "08_PDD", "Provisao por faixa de atraso",
         E_.NOTA_PDD, DB + " | Curva inicial: CRI-I, CRI-II, FIDC IV e V | Curva posterior: CRI-III a CRI-VI, FIDC VI e VII")
ini, fim = tabela(ws, c, r, "tbl_08_PDD",
                  wrap_cols=("base_de_incidencia", "efeito_vagao", "tratamento_do_dia_181", "curva", "metrica"))

base = fim + 3
ws.cell(row=base, column=1, value="AS DUAS CURVAS DE PROVISAO, LADO A LADO").font = F_SUB
hdr = ["Faixa de atraso", "Curva inicial (CRI-I e CRI-II)", "Curva posterior (CRI-III a CRI-VI)"]
faixas = ["Ate 15 dias", "16 a 30", "31 a 60", "61 a 90", "91 a 120", "121 a 150", "151 a 180", "Acima de 180"]
ini_v = [0.0, 1.0, 3.0, 10.0, 30.0, 50.0, 70.0, 100.0]
pos_v = [0.0, 1.5, 5.0, 10.0, 37.0, 58.0, 78.0, 100.0]
linhas_g = [[f, i, p] for f, i, p in zip(faixas, ini_v, pos_v)]
gi, gf = tabela(ws, hdr, linhas_g, "tbl_08_Curvas", linha0=base + 1)
ch = BarChart(); ch.type = "col"; ch.grouping = "clustered"
ch.title = "Percentual provisionado por faixa de atraso"
ch.y_axis.title = "% do valor presente do recebivel"; ch.x_axis.title = "Faixa de atraso"
dados = Reference(ws, min_col=2, max_col=3, min_row=gi - 1, max_row=gf)
cats = Reference(ws, min_col=1, min_row=gi, max_row=gf)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
estilo_serie(ch.series[0], CINZA_CLARO); estilo_serie(ch.series[1], LARANJA)
ch.height = 9; ch.width = 20
ws.add_chart(ch, f"F{base + 1}")
nota(ws, gf + 3, "A curva posterior reconhece 7 p.p. a mais na faixa de 91 a 120 dias e 8 p.p. a mais entre 121 e 180 - reconhecimento mais conservador, nao piora do ativo.")

# ---------------------------------------------------------------- 09_Eventos
c, r = ler("09_eventos.csv")
ws = aba(wb, "09_Eventos", "Eventos e gatilhos",
         "Os gatilhos numericos so estao integralmente documentados em CRI-II: Indice de Atraso de Estoque limitado a 15%, rebaixamento de 2 niveis de rating e desenquadramento das Razoes de Cobertura em 2 datas consecutivas ou 4 alternadas em 12 meses. Vencimento antecipado e 'nao aplicavel' por escrito em CRI-III e CRI-V - registrado como documentado, nao como lacuna.",
         DB)
tabela(ws, c, r, "tbl_09_Eventos",
       wrap_cols=("descricao_do_gatilho", "parametro_numerico", "consequencia_automatica",
                  "quorum_de_dispensa", "prazo_de_cura", "status"))

# ---------------------------------------------------------------- 09b_Garantias
c, r = ler("09b_garantias.csv")
ws = aba(wb, "09b_Garantias", "Garantias: onde estao e onde nao estao",
         E_.NOTA_GARANTIAS, DB)
tabela(ws, c, r, "tbl_09b_Garantias",
       wrap_cols=("garantia_no_ambito_do_veiculo", "garantia_sobre_os_direitos_creditorios",
                  "onde_e_contratada", "coobrigacao_do_cedente", "redacao_literal", "status"))

# ---------------------------------------------------------------- 10_Subscritores
import solfacil_mercado as M_
c, r = ler("10c_concentracao_subscritores.csv")
ws = aba(wb, "10_Subscritores", "Quem comprou na emissao",
         "55,6% da serie Super Senior de CRI-I foi para uma unica instituicao financeira ligada ao emissor ou ao consorcio - 200.000 de 360.000 CRI, um so subscritor - enquanto 989 pessoas fisicas ficaram com 42,2%. Categoria nao e titular: as colunas separam a maior categoria do maior titular unico.",
         "Data-base: 23/02/2024 (Anuncio de Encerramento de CRI-I) | Posicao corrente: n/d em todas as operacoes")
ini, fim = tabela(ws, c, r, "tbl_10_Concentracao",
                  wrap_cols=("maior_categoria", "maior_titular_unico_categoria"))
linha = fim + 3
ws.cell(row=linha, column=1, value="TABELA LITERAL DO FORMULARIO CVM - CRI-I").font = F_SUB
c2, r2 = ler("10_subscritores_longa.csv")
gi, gf = tabela(ws, c2, r2, "tbl_10_Longa", linha0=linha + 1, wrap_cols=("tipo_de_investidor",))
ws.column_dimensions["D"].width = 74
linha = gf + 3
ws.cell(row=linha, column=1, value="DISTRIBUICAO INICIAL AGREGADA POR OPERACAO").font = F_SUB
c3, r3 = ler("10b_subscritores_agregado.csv")
gi2, gf2 = tabela(ws, c3, r3, "tbl_10_Agregado", linha0=linha + 1, wrap_cols=("fonte_da_posicao",))
nota(ws, gf2 + 3, M_.NOTA_SUBSCRITORES)

# ---------------------------------------------------------------- 11_Matriz_FIDC_CRI
c, r = ler("11_matriz_fidc_cri.csv")
ws = aba(wb, "11_Matriz_FIDC_CRI", "Matriz de cessao: 7 FIDCs por 6 CRIs",
         M_.NOTA_MATRIZ, DB)
CRIS = ["CRI-I", "CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI"]
FIDCS = ["FIDC-I", "FIDC-II", "FIDC-III", "FIDC-IV", "FIDC-V", "FIDC-VI", "FIDC-VII"]
estado = {(x[0], x[1]): x[2] for x in r}
hdr = ["FIDC"] + CRIS
linhas_m = [[f] + [estado.get((f, k), "n/d") for k in CRIS] for f in FIDCS]
ini, fim = tabela(ws, hdr, linhas_m, "tbl_11_Matriz")
for i in range(ini, fim + 1):
    for j in range(2, 8):
        cel = ws.cell(row=i, column=j)
        cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if cel.value == "Cedeu":
            cel.font = Font(name="Calibri", size=10, bold=True, color=PRETO)
    ws.row_dimensions[i].height = 30
for j in range(2, 8):
    ws.column_dimensions[get_column_letter(j)].width = 22
linha = fim + 3
ws.cell(row=linha, column=1, value="DETALHE POR CELULA").font = F_SUB
c2, r2 = ler("11_matriz_fidc_cri.csv")
gi, gf = tabela(ws, c2, r2, "tbl_11_Detalhe", linha0=linha + 1,
                wrap_cols=("criterio_que_bloqueia_ou_evidencia",))
ws.column_dimensions["D"].width = 90

# ---------------------------------------------------------------- 11b_Cessoes
c, r = ler("11b_cessoes.csv")
ws = aba(wb, "11b_Cessoes", "Cessoes documentadas",
         "Uma linha por cessao. Volume cedido, percentual do pool e preco por lote sao n/d nas seis operacoes - o ledger de cessoes nao e publico e e o item 4 da lista de lacunas.",
         DB)
tabela(ws, c, r, "tbl_11b_Cessoes", wrap_cols=("pct_do_pool_do_CRI", "fidc_cedente"))

# ---------------------------------------------------------------- 12_Custo_Captacao
c, r = ler("12_custo_captacao.csv")
ws = aba(wb, "12_Custo_Captacao", "Custo de captacao",
         M_.NOTA_CUSTO, DB)
ini, fim = tabela(ws, c, r, "tbl_12_Custo", wrap_cols=("observacao", "status"))
ws.column_dimensions["G"].width = 90

linha = fim + 3
ws.cell(row=linha, column=1, value="EVOLUCAO DO SPREAD POR CAMADA AO LONGO DAS SEIS OPERACOES").font = F_SUB
c2, r2 = ler("12b_spread_por_camada.csv")
gi, gf = tabela(ws, c2, r2, "tbl_12b_Spread", linha0=linha + 1, wrap_cols=("unidade", "fonte_id"))

# Grafico apenas das camadas comparaveis em DI+ (mezanino e subordinado)
base = gf + 3
ws.cell(row=base, column=1, value="SERIES COMPARAVEIS EM DI + SPREAD").font = F_SUB
hdr = ["Operacao", "Mezanino (DI + %)", "Subordinado (DI + %)"]
ops = ["CRI-II", "CRI-III", "CRI-IV", "CRI-V", "CRI-VI"]
mez = [6.00, 5.75, 5.50, 5.50, 5.50]
sub_ = [10.00, 10.00, 10.00, 8.00, 8.00]
linhas_g = [[o, m, s] for o, m, s in zip(ops, mez, sub_)]
gi2, gf2 = tabela(ws, hdr, linhas_g, "tbl_12_Evolucao", linha0=base + 1)
ch = LineChart()
ch.title = "Spread contratado sobre 100% do DI, por camada"
ch.y_axis.title = "% a.a. sobre o DI"; ch.x_axis.title = "Operacao"
dados = Reference(ws, min_col=2, max_col=3, min_row=gi2 - 1, max_row=gf2)
cats = Reference(ws, min_col=1, min_row=gi2, max_row=gf2)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
for s, cor in zip(ch.series, [LARANJA, CINZA_ESC]):
    s.graphicalProperties = GraphicalProperties()
    s.graphicalProperties.line = LineProperties(solidFill=cor, w=28000)
    s.marker = Marker(symbol="circle", size=6)
    s.smooth = False
ch.height = 9; ch.width = 19
ws.add_chart(ch, f"F{base + 1}")
nota(ws, gf2 + 3, "CRI-I nao entra no grafico: suas quatro series publicas sao pre-fixadas e nao ha spread sobre DI a comparar. A queda de spread e consistente com melhora de percepcao de risco, mas o dado publico nao permite atribuir causa - mudaram tambem o indexador, a camada e o ciclo de juros.")

# ---------------------------------------------------------------- 13_Cronograma_Pagamentos
c, r = ler("13_cronograma_pagamentos.csv")
ws = aba(wb, "13_Cronograma_Pagamentos", "Cronograma de pagamentos: projetado e realizado",
         "So a 1a serie de CRI-II tem cronograma contratual de principal - as outras quatro amortizam ate um Saldo Devedor Target, entao o Anexo I delas e calendario de datas, nao curva de principal. Toda linha traz a coluna status: Projetado vem do Anexo I, Realizado vem dos informes mensais.",
         "Fonte do projetado: ANX-TS2-K2, Anexo I | Fonte do realizado: ANX-DECK, anexo A3")
ini, fim = tabela(ws, c, r, "tbl_13_Cronograma")

# Curva de morte da 1a serie (unica com percentual contratual)
s1 = [x for x in r if x[1] == "1a"]
base = fim + 3
ws.cell(row=base, column=1, value="CURVA DE AMORTIZACAO PROJETADA - CRI-II, 1a SERIE (SUPER SENIOR)").font = F_SUB
hdr = ["Pagamento", "Data", "Saldo remanescente (% do VNU)"]
linhas_g = [[numerico(x[3]), x[4], numerico(x[8])] for x in s1]
gi, gf = tabela(ws, hdr, linhas_g, "tbl_13_Curva", linha0=base + 1)
ch = AreaChart(); ch.grouping = "standard"
ch.title = "Saldo remanescente da 1a serie de CRI-II ao longo dos 60 pagamentos"
ch.y_axis.title = "% do Valor Nominal Unitario"; ch.x_axis.title = "Numero do pagamento"
dados = Reference(ws, min_col=3, min_row=gi - 1, max_row=gf)
cats = Reference(ws, min_col=1, min_row=gi, max_row=gf)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
estilo_serie(ch.series[0], LARANJA)
ch.legend = None; ch.height = 10; ch.width = 24
ws.add_chart(ch, f"F{base + 1}")
nota(ws, gf + 3, "O ponto de 98% amortizado - que dispara o resgate compulsorio da serie - e atingido no 59o pagamento, em 08/05/2029, um pagamento antes do vencimento. As demais series nao tem percentual contratual e por isso nao aparecem no grafico.")

linha = gf + 5
ws.cell(row=linha, column=1, value="AMORTIZACAO REALIZADA POR CAMADA (AGREGADA)").font = F_SUB
c2, r2 = ler("13b_amortizacao_realizada.csv")
gi2, gf2 = tabela(ws, c2, r2, "tbl_13b_Realizado", linha0=linha + 1)
nota(ws, gf2 + 3, "O realizado publico e agregado por camada - primeira e ultima ocorrencia, meses com pagamento e total. A serie mes a mes por camada nao consta dos informes disponiveis, entao a curva realizada nao pode ser desenhada sem os informes mensais completos.")

# ---------------------------------------------------------------- 14_Antes_Depois
import solfacil_sintese as Z_
c, r = ler("14_antes_depois.csv")
ws = aba(wb, "14_Antes_Depois", "Antes e depois do take-out",
         "Janela de duas competencias nos FIDCs VI e VII, em torno do take-out da VERT 177a de 31/07/2026. As competencias t-3 a t+3 pedidas nao existem: o evento e a ultima competencia disponivel.",
         "Data-base: 30/06/2026 e 31/07/2026 | Fonte: CVM Informe Mensal FIDC, via ANX-DECK")
ini, fim = tabela(ws, c, r, "tbl_14_AntesDepois", wrap_cols=("evento",))
ws.column_dimensions["I"].width = 60

base = fim + 3
ws.cell(row=base, column=1, value="PL E CARTEIRA NAS DUAS COMPETENCIAS").font = F_SUB
hdr = ["Competencia", "PL FIDC VI (R$ mi)", "Carteira FIDC VI (R$ mi)", "PL FIDC VII (R$ mi)", "Carteira FIDC VII (R$ mi)"]
linhas_g = [["30/06/2026 (t-1)", 437.4, 399.3, 564.7, 544.1],
            ["31/07/2026 (t=0, take-out)", 211.1, 147.7, 619.6, 446.1]]
gi, gf = tabela(ws, hdr, linhas_g, "tbl_14_Serie", linha0=base + 1)
ch = LineChart()
ch.title = "PL e carteira dos dois FIDCs cedentes, com marcador na competencia do take-out"
ch.y_axis.title = "R$ mi"
dados = Reference(ws, min_col=2, max_col=5, min_row=gi - 1, max_row=gf)
cats = Reference(ws, min_col=1, min_row=gi, max_row=gf)
ch.add_data(dados, titles_from_data=True); ch.set_categories(cats)
for s, cor in zip(ch.series, [PRETO, CINZA_MED, LARANJA_ESC, LARANJA]):
    s.graphicalProperties = GraphicalProperties()
    s.graphicalProperties.line = LineProperties(solidFill=cor, w=28000)
    s.marker = Marker(symbol="circle", size=7)
    s.smooth = False
ch.height = 10; ch.width = 22
ws.add_chart(ch, f"H{base + 1}")
nota(ws, gf + 3, Z_.NOTA_ANTES_DEPOIS)

# ---------------------------------------------------------------- 15_FIDC_vs_CRI
c, r = ler("15_fidc_vs_cri.csv")
ws = aba(wb, "15_FIDC_vs_CRI", "Onde o CRI ganha, onde nao ganha, e o que nao da para afirmar",
         "Doze dimensoes, com veredito explicito. Em quatro delas a vantagem e do FIDC, em cinco do CRI e em tres o dado publico nao sustenta veredito. A ultima coluna diz o que falta para fechar cada uma.",
         DB)
ini, fim = tabela(ws, c, r, "tbl_15_Veredito",
                  wrap_cols=("como_funciona_no_FIDC", "como_funciona_no_CRI", "evidencia", "o_que_falta_para_confirmar"))
for letra, w in {"A": 34, "B": 62, "C": 62, "D": 16, "E": 62, "F": 52}.items():
    ws.column_dimensions[letra].width = w

# ---------------------------------------------------------------- 16_Conflitos
c, r = ler("16_conflitos.csv")
ws = aba(wb, "16_Conflitos", "Divergencias entre fontes e a decisao adotada",
         "Dez casos testados. Em cinco nao havia divergencia real, so perimetro diferente - o mais importante e o total de series: os anuncios contam so as series publicas, e somando a serie privada de cada operacao chega-se exatamente a 34.",
         DB)
ini, fim = tabela(ws, c, r, "tbl_16_Conflitos",
                  wrap_cols=("valor_fonte_A", "valor_fonte_B", "decisao_adotada", "justificativa",
                             "campo_em_conflito", "fonte_A", "fonte_B"))
for letra, w in {"A": 6, "B": 34, "C": 46, "D": 30, "E": 13, "F": 46, "G": 30, "H": 13, "I": 46, "J": 84, "K": 10}.items():
    ws.column_dimensions[letra].width = w

# ---------------------------------------------------------------- 17_Fontes
c, r = ler("17_fontes.csv")
ws = aba(wb, "17_Fontes", "Inventario de fontes",
         "Doze documentos obtidos e cinco buscas registradas como nao localizadas. Ausencia confirmada e informacao: as duas ultimas linhas de busca sustentam a afirmacao de que o universo esta completo, com a limitacao declarada.",
         "Data de acesso: 22/08/2026")
ini, fim = tabela(ws, c, r, "tbl_17_Fontes",
                  wrap_cols=("documento", "tipo_de_fonte", "url_ou_origem", "trecho_pagina", "status"))
for letra, w in {"A": 20, "B": 62, "C": 44, "D": 46, "E": 13, "F": 13, "G": 74, "H": 26}.items():
    ws.column_dimensions[letra].width = w

# ---------------------------------------------------------------- 18_Metodologia
c, r = ler("18_metodologia.csv")
ws = aba(wb, "18_Metodologia", "Formula e qualificador de cada metrica",
         "Cada metrica calculada traz a formula e a ressalva que a limita. Quatro metricas pedidas ficaram sem calculo por falta de insumo publico - estao registradas como n/d, com o insumo que falta nomeado.",
         DB)
ini, fim = tabela(ws, c, r, "tbl_18_Metodologia", wrap_cols=("formula", "qualificador"))
for letra, w in {"A": 34, "B": 74, "C": 88, "D": 40}.items():
    ws.column_dimensions[letra].width = w

# ---------------------------------------------------------------- 19_Glossario
c, r = ler("19_glossario.csv")
ws = aba(wb, "19_Glossario", "Glossario",
         "Vinte e dois termos em portugues direto, sem definir jargao com jargao.", DB)
ini, fim = tabela(ws, c, r, "tbl_19_Glossario", wrap_cols=("definicao",))
ws.column_dimensions["A"].width = 38; ws.column_dimensions["B"].width = 108

# ---------------------------------------------------------------- 20_Lacunas
c, r = ler("20_lacunas.csv")
ws = aba(wb, "20_Lacunas", "O que falta e a quem pedir",
         "Dez itens, em ordem de prioridade. Os quatro primeiros bloqueiam, respectivamente, a confirmacao do universo, a ordem de pagamentos de cinco das seis operacoes, o volume efetivamente colocado e a economia da cessao.",
         DB)
ini, fim = tabela(ws, c, r, "tbl_20_Lacunas",
                  wrap_cols=("o_que_falta", "pergunta_que_responderia", "a_quem_pedir", "aba_afetada"))
for letra, w in {"A": 11, "B": 72, "C": 66, "D": 34, "E": 34}.items():
    ws.column_dimensions[letra].width = w

# ---------------------------------------------------------------- salvar
os.makedirs(OUTDIR, exist_ok=True)
hoje = "20260822"
caminho = os.path.join(OUTDIR, f"Solfacil_CRI_FIDC_{hoje}_claude.xlsx")
wb.save(caminho)
print(f"Workbook salvo: {caminho}")
print(f"Abas: {len(wb.sheetnames)}")
for n in wb.sheetnames:
    print("  -", n)
