"""Carteira de direitos creditórios, PDD e inadimplência dos fundos da carteira.

O Informe Mensal traz os três números, mas em lugares diferentes: carteira e
inadimplência já vêm no ``vehicle_monthly`` que a carteira lê, e a provisão sai
da Tabela I, no campo *redução ao valor recuperável*, materializada por
``scripts/build_carteira_provisao.py``.

O que este módulo faz é juntá-los **na competência que cada fundo usa** — a
carteira mistura meses de propósito, cada fundo entra com o seu mais recente —
e separar três coisas que um gráfico ingênuo confunde:

``reportado``
    o fundo declarou um valor positivo;

``zero declarado``
    o fundo declarou zero, o que é uma informação e não uma lacuna: a CVM nunca
    deixa o campo em branco na Tabela I;

``sem informe``
    o fundo não consta da competência, ou não tem carteira de direitos
    creditórios — e aí o quociente não existe, em vez de valer zero.

Um fundo sem carteira não vira 0% de PDD: vira ausência.  Essa distinção é a
razão de o módulo existir.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
PROVISAO_NAME = "carteira_provisao_monthly.csv.gz"

#: Os três estados que um indicador pode ter, na ordem em que a legenda os lê.
REPORTADO = "reportado"
ZERO_DECLARADO = "zero declarado"
SEM_DADO = "sem informe"
ESTADOS = (REPORTADO, ZERO_DECLARADO, SEM_DADO)

#: A barra é contexto de escala e fica neutra de propósito; o ponto é a
#: mensagem e é o único elemento com cor própria.  A separação também é de
#: forma — barra contra ponto —, então a identidade nunca depende só da cor.
COLOR_CARTEIRA = "#8892A0"
COLOR_PDD = "#1D6FA5"
COLOR_INAD = "#B4532A"
COLOR_INK = "#12151A"
COLOR_MUTED = "#6B7178"
COLOR_GRID = "#E4E6E8"
SURFACE = "#FFFFFF"

SERIE_CARTEIRA = "Carteira de direitos creditórios"
SERIE_PDD = "PDD / Carteira"
SERIE_INAD = "Inadimplência / Carteira"


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


def _estado(valor: pd.Series, base: pd.Series) -> pd.Series:
    """Reportado, zero declarado ou sem informe — nessa ordem de decisão."""

    return pd.Series(
        np.where(
            base.isna() | base.le(0) | valor.isna(),
            SEM_DADO,
            np.where(valor.gt(0), REPORTADO, ZERO_DECLARADO),
        ),
        index=valor.index,
        dtype=object,
    )


def attach_provisao(
    frame: pd.DataFrame, data_dir: Path = DEFAULT_DATA_DIR
) -> pd.DataFrame:
    """A carteira resolvida com carteira de crédito, PDD e inadimplência.

    O join é por ``(cnpj, competencia)``, e não só por CNPJ: casar a PDD de
    junho com a carteira de março de um fundo que parou de reportar produziria
    um quociente que nunca existiu.
    """

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
    base = saida["carteira_dc"].where(saida["carteira_dc"].gt(0))
    saida["pdd_sobre_carteira_pct"] = saida["pdd_brl"] / base * 100.0
    saida["inad_sobre_carteira_pct"] = saida["dc_inadimplentes"] / base * 100.0
    saida["pdd_estado"] = _estado(saida["pdd_brl"], saida["carteira_dc"])
    saida["inad_estado"] = _estado(saida["dc_inadimplentes"], saida["carteira_dc"])
    return saida


def cobertura(frame: pd.DataFrame) -> dict[str, int]:
    """Quantos fundos reportam cada coisa — o cabeçalho honesto do gráfico."""

    return {
        "fundos": int(len(frame)),
        "com_carteira": int(frame["carteira_dc"].fillna(0).gt(0).sum()),
        "inad_reportada": int(frame["inad_estado"].eq(REPORTADO).sum()),
        "inad_zero": int(frame["inad_estado"].eq(ZERO_DECLARADO).sum()),
        "inad_sem_dado": int(frame["inad_estado"].eq(SEM_DADO).sum()),
        "pdd_reportada": int(frame["pdd_estado"].eq(REPORTADO).sum()),
        "pdd_zero": int(frame["pdd_estado"].eq(ZERO_DECLARADO).sum()),
        "pdd_sem_dado": int(frame["pdd_estado"].eq(SEM_DADO).sum()),
    }


def por_categoria(frame: pd.DataFrame) -> pd.DataFrame:
    """A mesma leitura agregada por seção, com quociente ponderado.

    A média dos quocientes de cada fundo daria peso igual a um fundo de R$ 5 mm
    e a outro de R$ 5 bi.  O quociente da soma é o que a seção de fato carrega.
    """

    grupos = frame.groupby("categoria_estrutural", as_index=False).agg(
        carteira_dc=("carteira_dc", "sum"),
        pdd_brl=("pdd_brl", "sum"),
        dc_inadimplentes=("dc_inadimplentes", "sum"),
        fundos=("cnpj", "count"),
        pdd_reportada=("pdd_estado", lambda s: int(s.eq(REPORTADO).sum())),
        inad_reportada=("inad_estado", lambda s: int(s.eq(REPORTADO).sum())),
    )
    base = grupos["carteira_dc"].where(grupos["carteira_dc"].gt(0))
    grupos["carteira_mm"] = grupos["carteira_dc"] / 1e6
    grupos["pdd_mm"] = grupos["pdd_brl"] / 1e6
    grupos["pdd_sobre_carteira_pct"] = grupos["pdd_brl"] / base * 100.0
    grupos["inad_sobre_carteira_pct"] = grupos["dc_inadimplentes"] / base * 100.0
    grupos["pdd_estado"] = _estado(grupos["pdd_brl"], grupos["carteira_dc"])
    grupos["inad_estado"] = _estado(grupos["dc_inadimplentes"], grupos["carteira_dc"])
    grupos["rotulo"] = grupos["categoria_estrutural"]
    return grupos.sort_values("carteira_mm", ascending=False).reset_index(drop=True)


def chart_frame(
    frame: pd.DataFrame, *, rotulo: str = "rotulo", indicador: str = "pdd"
) -> pd.DataFrame:
    """O formato longo que o gráfico consome, já ordenado por carteira."""

    coluna = "pdd_sobre_carteira_pct" if indicador == "pdd" else "inad_sobre_carteira_pct"
    estado = "pdd_estado" if indicador == "pdd" else "inad_estado"
    serie = SERIE_PDD if indicador == "pdd" else SERIE_INAD

    data = frame[frame["carteira_dc"].fillna(0).gt(0)].copy()
    data = data.sort_values("carteira_mm", ascending=False).reset_index(drop=True)
    data["rotulo"] = data[rotulo]
    data["quociente_pct"] = data[coluna].fillna(0.0)
    data["estado"] = data[estado]
    data["serie"] = serie
    # Um zero declarado é plotado no zero, com marca vazada: ele está no eixo
    # porque o fundo disse zero, não porque o dado sumiu.
    data["preenchido"] = data["estado"].eq(REPORTADO)
    return data


def limite_do_eixo(valores: pd.Series) -> float | None:
    """Até onde o eixo do quociente vai antes de um outlier achatar o resto.

    Um fundo em run-off com PDD de 276% da carteira estica a escala e deixa os
    outros oitenta e dois colados no zero.  O corte só entra quando o extremo é
    de fato desproporcional, e o que passa dele não é escondido: vira triângulo
    no topo, com o valor escrito ao lado.
    """

    limpos = valores.dropna()
    limpos = limpos[limpos.gt(0)]
    if len(limpos) < 5:
        return None
    # ``lower`` em vez de interpolar: numa amostra pequena o próprio outlier
    # entra na interpolação do percentil e esconde que ele é um outlier.
    p90 = float(limpos.quantile(0.90, interpolation="lower"))
    topo = float(limpos.max())
    if p90 <= 0 or topo <= p90 * 2.5:
        return None
    return float(np.ceil(p90 * 1.25))


def altair_carteira_pdd(
    frame: pd.DataFrame,
    *,
    rotulo: str = "rotulo",
    indicador: str = "pdd",
    height: int = 360,
    largura_por_barra: int = 20,
    largura_minima: int = 560,
):
    """Carteira em barras e o quociente em pontos, no eixo secundário.

    O eixo secundário é o que a leitura de crédito pede: volume e taxa lado a
    lado, fundo a fundo.  Ele carrega o risco conhecido de sugerir correlação
    pelo alinhamento arbitrário das escalas, e a defesa aqui é tripla — as duas
    escalas ancoradas em zero, as séries separadas por **forma** (barra contra
    ponto) e não só por cor, e os dois eixos empilhados do mesmo lado, para que
    continuem visíveis quando o gráfico é largo o bastante para rolar.
    """

    import altair as alt

    data = chart_frame(frame, rotulo=rotulo, indicador=indicador)
    if data.empty:
        return alt.Chart(pd.DataFrame({"x": [0], "y": [0]})).mark_text(
            text="Nenhum fundo desta seleção reporta carteira de direitos creditórios.",
            color=COLOR_MUTED,
            size=13,
        ).encode().properties(height=height)

    cor_ponto = COLOR_PDD if indicador == "pdd" else COLOR_INAD
    titulo_ponto = SERIE_PDD if indicador == "pdd" else SERIE_INAD
    ordem = data["rotulo"].tolist()
    largura = max(largura_minima, len(ordem) * largura_por_barra)

    # O extremo é mantido no gráfico, mas no topo e escrito: sem o corte, um
    # fundo em run-off achata os outros oitenta e dois contra o zero.
    teto = limite_do_eixo(data["quociente_pct"])
    data["excede"] = False if teto is None else data["quociente_pct"].gt(teto)
    data["plotado_pct"] = (
        data["quociente_pct"] if teto is None else data["quociente_pct"].clip(upper=teto)
    )
    escala_ponto = alt.Scale(domainMin=0, nice=True) if teto is None else alt.Scale(
        domain=[0, teto], nice=False, clamp=True
    )

    eixo_x = alt.X(
        "rotulo:N",
        sort=ordem,
        title=None,
        axis=alt.Axis(
            labelAngle=-45,
            labelLimit=140,
            labelFontSize=9,
            labelColor=COLOR_MUTED,
            ticks=False,
            domainColor=COLOR_INK,
        ),
    )
    dicas = [
        alt.Tooltip("rotulo:N", title="FIDC"),
        alt.Tooltip("competencia:N", title="competência"),
        alt.Tooltip("carteira_mm:Q", title="carteira R$ mm", format=",.1f"),
        alt.Tooltip("pdd_mm:Q", title="PDD R$ mm", format=",.1f"),
        alt.Tooltip("pdd_sobre_carteira_pct:Q", title="PDD / carteira %", format=",.2f"),
        alt.Tooltip(
            "inad_sobre_carteira_pct:Q", title="inadimplência / carteira %", format=",.2f"
        ),
        alt.Tooltip("estado:N", title="estado do dado"),
    ]
    dicas = [d for d in dicas if d.shorthand.split(":")[0] in data.columns]

    # Uma fresta de superfície entre barras vizinhas: coladas, elas viram um
    # histograma e sugerem continuidade entre fundos que não têm nenhuma.
    barras = (
        alt.Chart(data)
        .mark_bar(color=COLOR_CARTEIRA, size=max(4, int(largura_por_barra * 0.62)))
        .encode(
            x=eixo_x,
            y=alt.Y(
                "carteira_mm:Q",
                title="Carteira de direitos creditórios (R$ mm)",
                scale=alt.Scale(domainMin=0, nice=True),
                axis=alt.Axis(
                    gridColor=COLOR_GRID,
                    domain=False,
                    ticks=False,
                    titleColor=COLOR_CARTEIRA,
                    labelColor=COLOR_MUTED,
                    labelFontSize=9,
                ),
            ),
            tooltip=dicas,
        )
    )
    eixo_quociente = alt.Y(
        "plotado_pct:Q",
        title=f"{titulo_ponto} (%)",
        scale=escala_ponto,
        axis=alt.Axis(
            grid=False,
            domain=False,
            ticks=False,
            orient="left",
            offset=92,
            # O título do segundo eixo sai deitado, acima da escala: dois
            # títulos girados no mesmo canto se sobrepõem e viram um borrão.
            titleAngle=0,
            titleAlign="left",
            titleBaseline="bottom",
            titleX=-92,
            titleY=-8,
            titleColor=cor_ponto,
            labelColor=COLOR_MUTED,
            labelFontSize=9,
        ),
    )
    pontos = (
        alt.Chart(data)
        .mark_point(size=90, strokeWidth=1.8, stroke=cor_ponto)
        .encode(
            x=eixo_x,
            y=eixo_quociente,
            # Reportado é ponto cheio; zero declarado é vazado, e a diferença
            # entre "declarou zero" e "não declarou" não fica só na cor.
            fill=alt.Fill(
                "preenchido:N",
                scale=alt.Scale(domain=[True, False], range=[cor_ponto, SURFACE]),
                legend=None,
            ),
            tooltip=dicas,
        )
        .transform_filter(alt.datum.estado != SEM_DADO)
        .transform_filter(alt.datum.excede == False)  # noqa: E712 — Vega precisa do literal
    )
    # Quem passa do teto vira triângulo no topo, com o valor real escrito: o
    # ponto sai da escala, não do gráfico.
    acima = (
        alt.Chart(data)
        .mark_point(size=110, shape="triangle-up", filled=True, color=cor_ponto)
        .encode(x=eixo_x, y=eixo_quociente, tooltip=dicas)
        .transform_filter(alt.datum.excede == True)  # noqa: E712
    )
    acima_texto = (
        alt.Chart(data)
        .mark_text(dy=-11, fontSize=9, fontWeight="bold", color=cor_ponto)
        .encode(
            x=eixo_x,
            y=eixo_quociente,
            text=alt.Text("quociente_pct:Q", format=",.0f"),
            tooltip=dicas,
        )
        .transform_filter(alt.datum.excede == True)  # noqa: E712
    )
    # Onde não há informe o ponto não é plotado em lugar nenhum — some do eixo,
    # e a marca no rodapé diz que o buraco é de dado, não de valor.
    ausentes = (
        alt.Chart(data)
        .mark_text(text="s/d", dy=8, fontSize=8, color=COLOR_MUTED, baseline="top")
        .encode(x=eixo_x, y=alt.value(height - 4), tooltip=dicas)
        .transform_filter(alt.datum.estado == SEM_DADO)
    )
    return (
        alt.layer(barras, pontos, acima, acima_texto, ausentes)
        .resolve_scale(y="independent")
        .properties(height=height, width=largura, padding={"top": 22, "right": 20})
    )


__all__ = [
    "COLOR_CARTEIRA",
    "COLOR_INAD",
    "COLOR_PDD",
    "ESTADOS",
    "PROVISAO_NAME",
    "REPORTADO",
    "SEM_DADO",
    "SERIE_INAD",
    "SERIE_PDD",
    "ZERO_DECLARADO",
    "altair_carteira_pdd",
    "attach_provisao",
    "chart_frame",
    "cobertura",
    "load_provisao",
    "por_categoria",
]
