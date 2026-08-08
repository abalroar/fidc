"""Cobertura de PDD sobre a inadimplência, fundo a fundo.

Carteira de direitos creditórios e inadimplência já vêm no ``vehicle_monthly``
que a carteira lê.  A provisão não: ela sai da Tabela I do Informe Mensal, no
campo *redução ao valor recuperável*, materializada por
``scripts/build_carteira_provisao.py``.

A leitura é uma só — **PDD ÷ inadimplência** —, e o limiar é 100%: abaixo dele o
fundo provisionou menos do que já venceu.

Duas coisas o quociente não consegue dizer, e o módulo separa em vez de fingir
que valem zero:

``sem inadimplência``
    o fundo tem carteira mas nada inadimplente.  Não existe denominador, e um
    fundo sem atraso não é um fundo sem cobertura.

``sem carteira``
    o fundo não tem carteira de direitos creditórios na competência usada.

O join com a PDD é por ``(cnpj, competencia)``: a carteira mistura meses de
propósito — cada fundo entra com o seu mais recente —, e casar a PDD de junho
com a inadimplência de março inventaria um quociente que nunca existiu.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
PROVISAO_NAME = "carteira_provisao_monthly.csv.gz"

COM_COBERTURA = "com cobertura"
SEM_INADIMPLENCIA = "sem inadimplência"
SEM_CARTEIRA = "sem carteira"

#: O limiar que a barra tem de deixar óbvio: abaixo de 100% o fundo provisionou
#: menos do que já venceu.
LIMIAR_PCT = 100.0

#: O teto do eixo.  Coberturas de 300% e de 24.000% dizem a mesma coisa —
#: amplamente provisionado —, e a segunda esmaga todas as outras barras contra o
#: chão.  A barra para no teto; o rótulo em cima traz o número verdadeiro.
TETO_PCT = 200.0

#: Vermelho para quem está abaixo do limiar, verde-azulado para quem alcança.
#: O par vale ΔE 14,9 em deuteranopia, bem acima do piso, e a posição contra a
#: linha de 100% reforça a leitura sem depender da cor.
COLOR_ABAIXO = "#C8102E"
COLOR_ACIMA = "#17A398"
COLOR_INK = "#12151A"
COLOR_MUTED = "#6B7178"
COLOR_GRID = "#E4E6E8"
SURFACE = "#FFFFFF"

SERIE_ABAIXO = "Abaixo de 100%"
SERIE_ACIMA = "100% ou mais"


def load_provisao(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """A PDD por fundo e competência, se materializada."""

    path = Path(data_dir) / PROVISAO_NAME
    if not path.is_file():
        return pd.DataFrame(columns=["competencia", "cnpj", "pdd_brl"])
    frame = pd.read_csv(path, dtype={"cnpj": str}, low_memory=False)
    frame["cnpj"] = frame["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    frame["competencia"] = frame["competencia"].astype(str)
    frame["pdd_brl"] = pd.to_numeric(frame["pdd_brl"], errors="coerce")
    return frame.drop_duplicates(["competencia", "cnpj"], keep="last")


def attach_provisao(
    frame: pd.DataFrame, data_dir: Path = DEFAULT_DATA_DIR
) -> pd.DataFrame:
    """A carteira resolvida com PDD, inadimplência e a cobertura entre as duas."""

    provisao = load_provisao(data_dir)
    saida = frame.copy()
    for coluna in ("carteira_dc", "dc_inadimplentes"):
        saida[coluna] = pd.to_numeric(saida.get(coluna), errors="coerce")

    if len(provisao):
        chave = provisao.set_index(["cnpj", "competencia"])["pdd_brl"]
        saida["pdd_brl"] = pd.MultiIndex.from_arrays(
            [saida["cnpj"], saida["competencia"].astype(str)]
        ).map(chave)
    else:
        saida["pdd_brl"] = np.nan

    saida["carteira_mm"] = saida["carteira_dc"] / 1e6
    saida["pdd_mm"] = saida["pdd_brl"] / 1e6
    saida["inad_mm"] = saida["dc_inadimplentes"] / 1e6

    tem_carteira = saida["carteira_dc"].fillna(0).gt(0)
    tem_inad = saida["dc_inadimplentes"].fillna(0).gt(0)
    saida["cobertura_pct"] = (
        saida["pdd_brl"].fillna(0.0)
        / saida["dc_inadimplentes"].where(tem_inad)
        * 100.0
    )
    saida["cobertura_estado"] = np.where(
        ~tem_carteira,
        SEM_CARTEIRA,
        np.where(tem_inad, COM_COBERTURA, SEM_INADIMPLENCIA),
    )
    return saida


def formatar_pct(valor: float) -> str:
    """O rótulo da barra: curto o bastante para caber sobre ela.

    Abaixo de dez, uma casa decimal; daí para cima, inteiro com separador de
    milhar — ``24.884%`` ocupa o mesmo espaço que ``0,4%``.
    """

    if valor is None or pd.isna(valor):
        return "—"
    if valor < 10:
        return f"{valor:.1f}%".replace(".", ",")
    return f"{valor:,.0f}%".replace(",", ".")


def chart_frame(frame: pd.DataFrame, *, rotulo: str = "rotulo") -> pd.DataFrame:
    """Só quem tem cobertura definida, da maior para a menor."""

    data = frame[frame["cobertura_estado"].eq(COM_COBERTURA)].copy()
    data["rotulo"] = data[rotulo]
    data = data.sort_values("cobertura_pct", ascending=False).reset_index(drop=True)
    data["faixa"] = np.where(
        data["cobertura_pct"].ge(LIMIAR_PCT), SERIE_ACIMA, SERIE_ABAIXO
    )
    # A barra para no teto; o rótulo em cima continua trazendo o número real.
    data["altura_pct"] = data["cobertura_pct"].clip(upper=TETO_PCT)
    data["etiqueta"] = data["cobertura_pct"].map(formatar_pct)
    return data


def altair_cobertura(
    frame: pd.DataFrame,
    *,
    rotulo: str = "rotulo",
    height: int = 420,
    largura_por_barra: int = 48,
    largura_minima: int = 560,
):
    """Uma barra por fundo, com o nome e o valor sempre visíveis."""

    import altair as alt

    data = chart_frame(frame, rotulo=rotulo)
    if data.empty:
        return alt.Chart(pd.DataFrame({"x": [0], "y": [0]})).mark_text(
            text="Nenhum fundo desta seleção tem inadimplência para cobrir.",
            color=COLOR_MUTED,
            size=13,
        ).encode().properties(height=height)

    ordem = data["rotulo"].tolist()
    largura = max(largura_minima, len(ordem) * largura_por_barra)
    eixo_x = alt.X(
        "rotulo:N",
        sort=ordem,
        title=None,
        axis=alt.Axis(
            labelAngle=-45,
            labelLimit=200,
            labelFontSize=10,
            labelColor=COLOR_INK,
            # Sem isto o Vega esconde um nome sim, outro não, assim que eles se
            # encostam — e o pedido é que todo fundo apareça nomeado.
            labelOverlap=False,
            ticks=False,
            domainColor=COLOR_INK,
        ),
    )
    eixo_y = alt.Y(
        "altura_pct:Q",
        title="PDD / Inadimplência (%)",
        scale=alt.Scale(domain=[0, TETO_PCT], nice=False, clamp=True),
        axis=alt.Axis(
            gridColor=COLOR_GRID,
            domain=False,
            ticks=False,
            labelColor=COLOR_MUTED,
            values=[0, 50, 100, 150, 200],
        ),
    )
    cor = alt.Color(
        "faixa:N",
        scale=alt.Scale(
            domain=[SERIE_ABAIXO, SERIE_ACIMA], range=[COLOR_ABAIXO, COLOR_ACIMA]
        ),
        legend=alt.Legend(title=None, orient="top", direction="horizontal"),
    )
    dicas = [
        alt.Tooltip("rotulo:N", title="FIDC"),
        alt.Tooltip("categoria_estrutural:N", title="categoria"),
        alt.Tooltip("competencia:N", title="competência"),
        alt.Tooltip("pdd_mm:Q", title="PDD R$ mm", format=",.2f"),
        alt.Tooltip("inad_mm:Q", title="inadimplência R$ mm", format=",.2f"),
        alt.Tooltip("cobertura_pct:Q", title="cobertura %", format=",.1f"),
    ]
    dicas = [d for d in dicas if d.shorthand.split(":")[0] in data.columns]

    barras = (
        alt.Chart(data)
        .mark_bar(size=max(6, int(largura_por_barra * 0.62)))
        .encode(x=eixo_x, y=eixo_y, color=cor, tooltip=dicas)
    )
    # O rótulo vai em todas as barras, e não só nas notáveis: é ele que devolve
    # o número que o teto do eixo corta.
    etiquetas = (
        alt.Chart(data)
        .mark_text(dy=-6, fontSize=9, color=COLOR_INK, baseline="bottom")
        .encode(x=eixo_x, y=eixo_y, text="etiqueta:N", tooltip=dicas)
    )
    limiar = (
        alt.Chart(pd.DataFrame({"y": [LIMIAR_PCT]}))
        .mark_rule(strokeDash=[4, 3], strokeWidth=1, color=COLOR_INK)
        .encode(y=alt.Y("y:Q", title=None, scale=alt.Scale(domain=[0, TETO_PCT])))
    )
    return (
        alt.layer(limiar, barras, etiquetas)
        .properties(height=height, width=largura, padding={"top": 10, "right": 16})
    )


def cobertura_figure(
    frame: pd.DataFrame,
    *,
    rotulo: str = "rotulo",
    figsize: tuple[float, float] = (12.0, 2.9),
    dpi: int = 200,
):
    """A mesma leitura do site, em imagem, para o slide.

    O eixo do site é vetorial e rola; a lâmina não rola, então aqui os nomes
    saem na vertical e o rótulo fica só em quem está abaixo do limiar — que é o
    conjunto sobre o qual a tabela ao lado fala.
    """

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    data = chart_frame(frame, rotulo=rotulo)
    figura, eixo = plt.subplots(figsize=figsize, dpi=dpi)
    figura.patch.set_facecolor(SURFACE)
    eixo.set_facecolor(SURFACE)
    if data.empty:
        eixo.set_axis_off()
        figura.tight_layout()
        return figura

    posicao = np.arange(len(data))
    cores = np.where(data["faixa"].eq(SERIE_ACIMA), COLOR_ACIMA, COLOR_ABAIXO)
    eixo.bar(posicao, data["altura_pct"], color=cores, width=0.74, zorder=3)
    eixo.axhline(LIMIAR_PCT, color=COLOR_INK, linewidth=0.9, linestyle=(0, (4, 3)), zorder=4)

    for x, linha in zip(posicao, data.itertuples()):
        if linha.faixa == SERIE_ACIMA:
            continue
        eixo.text(
            x, linha.altura_pct + 4, linha.etiqueta, ha="center", va="bottom",
            fontsize=4.6, color=COLOR_INK, rotation=90, zorder=5,
        )

    eixo.set_xticks(posicao)
    eixo.set_xticklabels(
        [str(n)[:24] for n in data["rotulo"]], rotation=90, fontsize=4.4, color=COLOR_MUTED
    )
    eixo.set_xlim(-0.8, len(data) - 0.2)
    eixo.set_ylim(0, TETO_PCT * 1.16)
    eixo.set_yticks([0, 50, 100, 150, 200])
    eixo.set_yticklabels(["0", "50", "100%", "150", "200"], fontsize=6, color=COLOR_MUTED)
    eixo.set_ylabel("PDD / Inadimplência", fontsize=6.5, color=COLOR_MUTED)
    eixo.grid(axis="y", color=COLOR_GRID, linewidth=0.6, zorder=0)
    eixo.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        eixo.spines[lado].set_visible(False)
    eixo.spines["bottom"].set_color(COLOR_INK)
    eixo.tick_params(axis="both", length=0)
    eixo.legend(
        handles=[
            Patch(facecolor=COLOR_ABAIXO, label=SERIE_ABAIXO),
            Patch(facecolor=COLOR_ACIMA, label=SERIE_ACIMA),
        ],
        loc="upper right", frameon=False, fontsize=6.5, ncol=2, handlelength=1.1,
    )
    figura.tight_layout(pad=0.4)
    return figura


def figure_png_bytes(figura, *, dpi: int = 200) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    figura.savefig(buffer, format="png", dpi=dpi, facecolor=SURFACE)
    return buffer.getvalue()


__all__ = [
    "COLOR_ABAIXO",
    "COLOR_ACIMA",
    "COM_COBERTURA",
    "LIMIAR_PCT",
    "PROVISAO_NAME",
    "SEM_CARTEIRA",
    "SEM_INADIMPLENCIA",
    "TETO_PCT",
    "altair_cobertura",
    "attach_provisao",
    "cobertura_figure",
    "figure_png_bytes",
    "chart_frame",
    "formatar_pct",
    "load_provisao",
]
