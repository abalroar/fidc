"""Standalone deck: ANBIMA fixed-income origination ranking, Itaú BBA position.

Reads only the artefacts materialized by
``scripts/build_anbima_fixed_income_ranking.py`` and renders a short, native
and fully editable 16:9 PowerPoint for the Itaú BBA president.

Scope is the consolidated fixed-income ranking (ANBIMA Tipo 1), accumulated in
the year through the cut-off date, decomposed into its published subdivisions
and with a dedicated cut on FIDC (Tipo 1.3.1).  It deliberately does not touch
the industry deck contract in ``services/industry_ppt_export.py``.

    python scripts/build_anbima_ranking_president_deck.py
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.bba_deck import (  # noqa: E402
    BLACK,
    Deck,
    GRAY_100,
    GRAY_300,
    GRAY_500,
    GRAY_700,
    GRAY_900,
    ORANGE,
    WHITE,
    fmt_mm,
    fmt_pct as _pct,
    fmt_rank as _rank,
)
from services.anbima_executive_package import display_name as _display_name  # noqa: E402


def _bi(value: float) -> str:
    """Format a BRL amount as R$ billions with one decimal."""

    return fmt_mm(value / 1e9)

DEFAULT_DATA_DIR = Path("data/industry_study")
DEFAULT_OUTPUT = Path(
    "outputs/anbima_ranking_rf_presidente/"
    "ANBIMA_Ranking_Renda_Fixa_Itau_BBA_1S26.pptx"
)

FONT_KICKER = "RANKING ANBIMA · RENDA FIXA"
HOUSE = "ITAU BBA"
KICKER = FONT_KICKER

SOURCE_LINE = (
    "Fonte: ANBIMA, Ranking de Renda Fixa e Híbridos — Originação (Valor), "
    "Tipo 1: Renda Fixa Consolidado, acumulado 2026 · referência Junho/2026"
)

#: Published sub-rankings that decompose the consolidated fixed-income number.
SUBDIVISIONS: tuple[tuple[str, str], ...] = (
    ("1.1", "Renda fixa — curto prazo"),
    ("1.2", "Renda fixa — longo prazo"),
    ("1.3", "Securitização"),
    ("1.3.1", "Securitização · FIDC"),
    ("1.3.2", "Securitização · CRI"),
    ("1.3.3", "Securitização · CRA"),
)

METHODOLOGY: tuple[tuple[str, str], ...] = (
    (
        "O ranking credita todos os coordenadores, não só o líder",
        "Cada coordenador e coordenador contratado recebe a fatia que lhe cabe "
        "na operação. O líder apenas reporta a operação à ANBIMA.",
    ),
    (
        "O rateio é contratual",
        "Garantia firme: proporção da garantia definida em contrato. Melhores "
        "esforços: proporção do fee de coordenação e/ou estruturação.",
    ),
    (
        "O mês de referência é o do anúncio de encerramento",
        "Não é a data de registro nem a de emissão. Operações fora do prazo de "
        "envio escorregam para o ranking do trimestre seguinte.",
    ),
    (
        "É um ranking declaratório",
        "Operação cujo formulário-padrão não foi enviado não entra. Boa parte "
        "do mercado liderado por administradores e DTVMs fica de fora.",
    ),
    (
        "Operações de empresas ligadas saem do Tipo 1",
        "Coordenador com participação de 10% ou mais na emissora, cedente ou "
        "originadora vai para o Tipo 3, apurado à parte.",
    ),
    (
        "Perímetro do Tipo 1",
        "Debêntures simples, notas promissórias, notas comerciais, CPR-F e "
        "securitização (FIDC, CRI, CRA, CR). FII, FIAGRO e FIP-IE ficam nas "
        "operações híbridas e não entram.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--house",
        default=HOUSE,
        help="Participante em destaque no ranking (default: ITAU BBA).",
    )
    return parser.parse_args()


def _load(data_dir: Path) -> tuple[pd.DataFrame, dict]:
    official = pd.read_csv(data_dir / "anbima_rf_ranking_official.csv")
    manifest = json.loads(
        (data_dir / "anbima_rf_ranking_manifest.json").read_text(encoding="utf-8")
    )
    return official, manifest


def _accumulated(official: pd.DataFrame, code: str) -> pd.DataFrame:
    return official[
        official["measure"].eq("originacao_valor")
        & official["window"].eq("acumulado_ano")
        & official["ranking_code"].eq(code)
    ]


def build(data_dir: Path, output: Path, house: str) -> Path:
    official, manifest = _load(data_dir)
    consolidated = _accumulated(official, "1")
    if consolidated.empty:
        raise SystemExit(
            "anbima_rf_ranking_official.csv sem o bloco Tipo 1; rode "
            "scripts/build_anbima_fixed_income_ranking.py antes."
        )

    universe = float(consolidated["value_brl_or_count"].sum())
    ranked = consolidated.sort_values("rank")
    participants = int(consolidated["participant"].nunique())
    house_row = ranked[ranked["participant"].eq(house)]
    if house_row.empty:
        raise SystemExit(f"Participante {house!r} ausente no ranking consolidado.")
    house_row = house_row.iloc[0]
    cutoff = manifest.get("period", {}).get("end", "")
    cutoff_label = (
        date.fromisoformat(cutoff).strftime("%d/%m/%Y") if cutoff else "n/d"
    )

    deck = Deck(KICKER)

    # ---------------------------------------------------------------- capa
    cover = deck.prs.slides.add_slide(deck.prs.slide_layouts[6])
    cover.background.fill.solid()
    cover.background.fill.fore_color.rgb = deck.rgb(WHITE)
    deck.block(cover, 0.0, 0.0, 0.22, 7.5, ORANGE)
    deck.text(cover, KICKER, 0.92, 2.28, 8.0, 0.26, size=11, color=ORANGE, bold=True)
    deck.text(
        cover,
        "Posição do Itaú BBA na originação de renda fixa",
        0.92,
        2.72,
        11.4,
        0.7,
        size=30,
        color=BLACK,
        bold=True,
    )
    deck.text(
        cover,
        "Primeiro semestre de 2026 · Ranking ANBIMA de Renda Fixa e Híbridos",
        0.92,
        3.52,
        11.4,
        0.34,
        size=14,
        color=GRAY_700,
    )
    deck.rule(cover, 0.92, 4.08, 3.2, color=GRAY_300, height=0.018)
    deck.text(
        cover,
        f"Data-corte {cutoff_label} · referência Junho/2026 · publicado em 27/07/2026",
        0.92,
        4.32,
        11.4,
        0.3,
        size=11,
        color=GRAY_500,
    )
    deck.text(
        cover,
        "Análise Setorial de Crédito — Itaú BBA",
        0.92,
        6.62,
        6.0,
        0.28,
        size=10,
        color=GRAY_500,
    )

    # ------------------------------------------------- resultado do 1S26
    slide = deck.slide("O Itaú BBA encerrou o 1S26 em 2º lugar, com 22,9% do mercado apurado")

    for index, (label, value, note) in enumerate(
        (
            ("Volume originado", f"R$ {_bi(float(house_row['value_brl_or_count']))} bi", "1S26"),
            ("Participação", _pct(float(house_row["share"]), 1), "do mercado apurado"),
            ("Posição", _rank(house_row["rank"]), f"entre {participants} coordenadores"),
            ("Mercado apurado", f"R$ {_bi(universe)} bi", "universo do ranking"),
        )
    ):
        x = 0.62 + index * 3.06
        deck.block(slide, x, 1.45, 2.86, 1.16, GRAY_100)
        deck.text(slide, label.upper(), x + 0.2, 1.6, 2.5, 0.22, size=9, color=GRAY_500, bold=True)
        deck.text(slide, value, x + 0.2, 1.86, 2.5, 0.42, size=20, color=BLACK, bold=True)
        deck.text(slide, note, x + 0.2, 2.3, 2.5, 0.22, size=9, color=GRAY_500)

    top = ranked.head(10)
    rows = [["#", "Coordenador", "Volume (R$ bi)", "Part."]]
    highlight = None
    for position, (_, row) in enumerate(top.iterrows()):
        if row["participant"] == house:
            highlight = position
        rows.append(
            [
                _rank(row["rank"]),
                _display_name(row["participant"]),
                _bi(float(row["value_brl_or_count"])),
                _pct(float(row["share"]), 1),
            ]
        )
    deck.table(
        slide,
        rows,
        0.62,
        2.88,
        [0.7, 6.2, 2.6, 2.55],
        highlight=highlight,
        row_height=0.33,
    )
    deck.footer(slide, SOURCE_LINE)

    # -------------------------------------------- decomposição do share
    slide = deck.slide("A liderança do Itaú BBA está em securitização; a perda foi em dívida corporativa")

    rows = [["Subdivisão do Tipo 1", "Mercado (R$ bi)", "Itaú BBA (R$ bi)", "Part.", "Pos."]]
    for code, label in SUBDIVISIONS:
        block = _accumulated(official, code)
        if block.empty:
            continue
        block_universe = float(block["value_brl_or_count"].sum())
        entry = block[block["participant"].eq(house)]
        if entry.empty:
            volume, share, position = 0.0, float("nan"), float("nan")
        else:
            volume = float(entry["value_brl_or_count"].iloc[0])
            share = float(entry["share"].iloc[0])
            position = entry["rank"].iloc[0]
        rows.append(
            [
                label,
                _bi(block_universe),
                _bi(volume),
                _pct(share, 1),
                _rank(position),
            ]
        )
    bottom = deck.table(
        slide,
        rows,
        0.62,
        1.5,
        [5.0, 2.3, 2.3, 1.4, 1.05],
        row_height=0.46,
        align_right_from=1,
    )

    deck.block(slide, 0.62, bottom + 0.28, 12.05, 1.38, GRAY_100)
    deck.text(
        slide,
        "LEITURA",
        0.92,
        bottom + 0.45,
        3.0,
        0.22,
        size=9,
        color=ORANGE,
        bold=True,
    )
    deck.text(
        slide,
        "O bloco de longo prazo — debêntures e notas comerciais — responde por 79% do mercado "
        "apurado e é onde o Itaú BBA aparece em 2º, com 20,9%. Em securitização, que responde "
        "por 16% do mercado, o banco é 1º com 37,6%. A troca de liderança no consolidado do "
        "semestre veio da dívida corporativa, não da securitização.",
        0.92,
        bottom + 0.72,
        11.45,
        0.85,
        size=12,
        color=GRAY_900,
    )
    deck.footer(
        slide,
        "Fonte: ANBIMA, Ranking de Renda Fixa e Híbridos — Originação (Valor), "
        "subdivisões Tipo 1.1, 1.2 e 1.3, acumulado 2026 · referência Junho/2026",
    )

    # -------------------------------------------------------------- FIDC
    fidc = _accumulated(official, "1.3.1").sort_values("rank")
    fidc_counts = official[
        official["measure"].eq("originacao_numero_operacoes")
        & official["window"].eq("acumulado_ano")
        & official["ranking_code"].eq("1.3.1")
    ].set_index("participant")["value_brl_or_count"]
    fidc_distribution = official[
        official["measure"].eq("distribuicao_valor")
        & official["window"].eq("acumulado_ano")
        & official["ranking_code"].eq("1.3.1")
    ].set_index("participant")

    if not fidc.empty:
        fidc_universe = float(fidc["value_brl_or_count"].sum())
        fidc_house = fidc[fidc["participant"].eq(house)].iloc[0]
        # A syndicated operation credits one unit to each coordinator, so the
        # per-participant counts do not add up to the number of operations.
        # The operation total comes from the annex, deduplicated by operation.
        share_table = pd.read_csv(data_dir / "anbima_rf_ranking_participant_share.csv")
        fidc_scope = share_table[
            share_table["scope"].eq("fidc")
            & share_table["measure"].eq("originacao_valor")
        ]
        fidc_operations = (
            int(fidc_scope["universe_operations"].iloc[0])
            if not fidc_scope.empty
            else 0
        )
        house_operations = int(fidc_counts.get(house, 0))

        slide = deck.slide(
            "Em FIDC o Itaú BBA lidera com 45,7%, mais que o dobro do segundo colocado"
        )
        for index, (label, value, note) in enumerate(
            (
                (
                    "Volume originado",
                    f"R$ {_bi(float(fidc_house['value_brl_or_count']))} bi",
                    "1S26",
                ),
                ("Participação", _pct(float(fidc_house["share"]), 1), "do mercado apurado"),
                ("Posição", _rank(fidc_house["rank"]), "entre 11 coordenadores ativos"),
                (
                    "Operações",
                    f"{house_operations} de {fidc_operations}",
                    "originadas no semestre",
                ),
            )
        ):
            x = 0.62 + index * 3.06
            deck.block(slide, x, 1.45, 2.86, 1.16, GRAY_100)
            deck.text(slide, label.upper(), x + 0.2, 1.6, 2.5, 0.22, size=9, color=GRAY_500, bold=True)
            deck.text(slide, value, x + 0.2, 1.86, 2.5, 0.42, size=20, color=BLACK, bold=True)
            deck.text(slide, note, x + 0.2, 2.3, 2.5, 0.22, size=9, color=GRAY_500)

        rows = [["#", "Coordenador", "Volume (R$ bi)", "Part.", "Nº ops"]]
        highlight = None
        active = fidc[fidc["value_brl_or_count"] > 0].head(9)
        for position, (_, row) in enumerate(active.iterrows()):
            if row["participant"] == house:
                highlight = position
            rows.append(
                [
                    _rank(row["rank"]),
                    _display_name(row["participant"]),
                    _bi(float(row["value_brl_or_count"])),
                    _pct(float(row["share"]), 1),
                    str(int(fidc_counts.get(row["participant"], 0))),
                ]
            )
        bottom = deck.table(
            slide,
            rows,
            0.62,
            2.92,
            [0.7, 5.0, 2.5, 1.9, 1.95],
            highlight=highlight,
            row_height=0.30,
        )

        house_distribution = (
            float(fidc_distribution.loc[house, "share"])
            if house in fidc_distribution.index
            else float("nan")
        )
        deck.text(
            slide,
            "Na distribuição — o esforço efetivo de colocação — o Itaú BBA também é 1º, com "
            f"{_pct(house_distribution, 1)}. O mercado apurado de FIDC no ranking é de "
            f"R$ {_bi(fidc_universe)} bi, contra R$ 65,5 bi de cotas de FIDC registradas na CVM "
            "no mesmo período: o ranking cobre a parcela disputada, sem as operações de "
            "empresas ligadas e sem as ofertas não reportadas à ANBIMA.",
            0.62,
            bottom + 0.26,
            12.05,
            0.62,
            size=11,
            color=GRAY_700,
        )
        deck.footer(
            slide,
            "Fonte: ANBIMA, Ranking de Renda Fixa e Híbridos — Originação e Distribuição "
            "(Valor), Tipo 1.3.1, acumulado 2026 · CVM, ofertas públicas de distribuição",
        )

    # ------------------------------------------------------- metodologia
    slide = deck.slide("Como a ANBIMA apura o ranking")
    cursor = 1.5
    for index, (title, body) in enumerate(METHODOLOGY):
        column = index % 2
        if column == 0 and index:
            cursor += 1.72
        x = 0.62 + column * 6.2
        deck.block(slide, x, cursor, 0.045, 1.06, ORANGE)
        deck.text(slide, title, x + 0.28, cursor, 5.5, 0.5, size=13, color=BLACK, bold=True)
        deck.text(slide, body, x + 0.28, cursor + 0.46, 5.5, 0.95, size=11, color=GRAY_700)
    deck.footer(
        slide,
        "Fonte: ANBIMA, Metodologia do Ranking de Renda Fixa e Híbridos (fev/2026), "
        "capítulos II a VII",
    )

    # ------------------------------------------------ fontes e ressalvas
    slide = deck.slide("Fontes, reprodutibilidade e ressalvas")

    sources = manifest.get("sources", {})
    rows = [["Insumo", "Arquivo", "SHA-256 (12)"]]
    for label, key in (
        ("Ranking publicado", "ranking_workbook"),
        ("Anexo de encerramento", "annex_workbook"),
        ("Ofertas públicas CVM", "cvm_archive"),
    ):
        entry = sources.get(key, {})
        # The CVM archive may be supplied from anywhere on disk; name it by its
        # canonical download URL so the deck never shows a local path.
        reference = str(entry.get("url") or entry.get("path") or "")
        rows.append(
            [
                label,
                Path(reference).name or "—",
                str(entry.get("sha256", ""))[:12] or "—",
            ]
        )
    bottom = deck.table(
        slide, rows, 0.62, 1.5, [3.1, 6.4, 2.5], row_height=0.38, align_right_from=3
    )

    notes = (
        (
            "Reprodução auditada",
            "Somar o anexo operação a operação reconstrói o ranking publicado ao centavo: "
            "divergência máxima de R$ 0,0000076 em originação e distribuição.",
        ),
        (
            "Entidade jurídica",
            "A ANBIMA consolida o grupo sob o rótulo único ITAU BBA e não segrega Itaú BBA "
            "Assessoria Financeira S.A. do Banco Itaú BBA S.A. Na base CVM do 1S26, todas as "
            "ofertas lideradas pelo grupo saíram sob a Assessoria Financeira.",
        ),
        (
            "Universo do ranking",
            "O ranking cobre 71% do volume de renda fixa registrado na CVM no 1S26. A diferença "
            "vem de operações de empresas ligadas e de ofertas cujos formulários não foram "
            "enviados à ANBIMA.",
        ),
    )
    cursor = bottom + 0.3
    for title, body in notes:
        deck.text(slide, title, 0.62, cursor, 3.1, 0.3, size=11, color=ORANGE, bold=True)
        deck.text(slide, body, 3.85, cursor, 8.82, 0.72, size=11, color=GRAY_900)
        cursor += 0.86

    deck.footer(
        slide,
        "Reproduzível por scripts/build_anbima_fixed_income_ranking.py · "
        "data.anbima.com.br/publicacoes/ranking-de-renda-fixa-e-hibridos",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(output)
    return output


def main() -> None:
    args = parse_args()
    path = build(args.data_dir, args.output, args.house)
    print(f"deck: {path}")


if __name__ == "__main__":
    main()
