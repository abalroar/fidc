"""A carteira de subordinação: registro, resolução e troca de slides."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_subordinacao import (  # noqa: E402
    ORIGEM_CARTEIRA_101,
    ORIGEM_MANUAL,
    RegistryError,
    dumbbell_figure,
    format_cnpj,
    load_registry,
    normalize_cnpj,
    remove_entry,
    resolve_portfolio,
    save_entry,
    seed_registry,
    short_fund_name,
)

FUNDO_A = "11111111000191"
FUNDO_B = "22222222000172"
FUNDO_MORTO = "33333333000153"


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Uma base mínima com o que ``resolve_portfolio`` lê."""

    monthly = pd.DataFrame(
        [
            # O fundo A reportou até julho; o B parou em junho.  A resolução
            # tem de dar a cada um a sua própria competência mais recente.
            {"competencia": "2026-06", "cnpj": FUNDO_A, "denominacao": "FIDC A",
             "pl": 100e6, "subordinacao_pct": 0.20},
            {"competencia": "2026-07", "cnpj": FUNDO_A, "denominacao": "FIDC A",
             "pl": 120e6, "subordinacao_pct": 0.25},
            {"competencia": "2026-06", "cnpj": FUNDO_B, "denominacao": "FIDC B",
             "pl": 80e6, "subordinacao_pct": 0.08},
            # Sem PL a linha não conta como reporte.
            {"competencia": "2026-07", "cnpj": FUNDO_B, "denominacao": "FIDC B",
             "pl": 0.0, "subordinacao_pct": None},
            # Parou de reportar bem antes do corte.
            {"competencia": "2025-01", "cnpj": FUNDO_MORTO, "denominacao": "FIDC Morto",
             "pl": 10e6, "subordinacao_pct": 0.30},
        ]
    )
    monthly.to_csv(tmp_path / "vehicle_monthly.csv.gz", index=False, compression="gzip")
    pd.DataFrame(
        [{"cnpj_fundo": FUNDO_A, "cnpj_classe": FUNDO_A, "tipo_anbima": "Financeiro",
          "foco_anbima": "Consignado"},
         {"cnpj_fundo": FUNDO_B, "cnpj_classe": FUNDO_B, "tipo_anbima": "Outros",
          "foco_anbima": ""}]
    ).to_csv(tmp_path / "industry_anbima_classification.csv.gz", index=False, compression="gzip")
    return tmp_path


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def test_o_cnpj_entra_com_ou_sem_mascara(data_dir: Path) -> None:
    save_entry(cnpj="11.111.111/0001-91", subordinacao_minima_pct=15, data_dir=data_dir)

    registry = load_registry(data_dir)

    assert registry["cnpj"].tolist() == [FUNDO_A]
    assert format_cnpj(FUNDO_A) == "11.111.111/0001-91"


def test_um_cnpj_incompleto_e_recusado(data_dir: Path) -> None:
    with pytest.raises(RegistryError, match="14 dígitos"):
        save_entry(cnpj="111", subordinacao_minima_pct=15, data_dir=data_dir)


def test_salvar_sem_nenhum_minimo_e_recusado(data_dir: Path) -> None:
    """Sem mínimo não existe comparação — a linha não teria função."""

    with pytest.raises(RegistryError, match="ao menos um"):
        save_entry(cnpj=FUNDO_A, data_dir=data_dir)


def test_um_minimo_fora_da_escala_e_recusado(data_dir: Path) -> None:
    with pytest.raises(RegistryError, match="entre 0 e 100"):
        save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=150, data_dir=data_dir)


def test_o_estrutural_nao_pode_ser_menor_que_o_junior(data_dir: Path) -> None:
    """O estrutural soma o mezanino ao júnior; menor que o júnior é erro de digitação."""

    with pytest.raises(RegistryError, match="não pode ser menor"):
        save_entry(
            cnpj=FUNDO_A,
            subordinacao_minima_pct=20,
            subordinacao_estrutural_pct=10,
            data_dir=data_dir,
        )


def test_salvar_o_mesmo_cnpj_duas_vezes_substitui_a_linha(data_dir: Path) -> None:
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=15, data_dir=data_dir)
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=18, fonte="Regulamento novo",
               data_dir=data_dir)

    registry = load_registry(data_dir)

    assert len(registry) == 1
    assert registry.iloc[0]["subordinacao_minima_pct"] == 18
    assert registry.iloc[0]["fonte"] == "Regulamento novo"


def test_remover_tira_o_cnpj_do_registro(data_dir: Path) -> None:
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=15, data_dir=data_dir)
    save_entry(cnpj=FUNDO_B, subordinacao_minima_pct=5, data_dir=data_dir)

    remove_entry(FUNDO_A, data_dir)

    assert load_registry(data_dir)["cnpj"].tolist() == [FUNDO_B]


def test_a_semeadura_preserva_o_que_o_analista_editou(tmp_path: Path) -> None:
    """A Carteira 101 e a inclusão manual moram no mesmo arquivo; semear de
    novo não pode apagar a decisão de quem editou à mão."""

    pd.DataFrame(
        [{"cnpj_fundo": FUNDO_A, "documento_id_regulamento": "123",
          "documento_data_regulamento": "2026-01-01", "pagina_clausula": "10",
          "subordinacao_minima_junior_pct": "12.5", "suporte_estrutural_minimo_pct": "",
          "status_curadoria_documental": "documentado"}]
    ).to_csv(tmp_path / "industry_carteira_1_document_curation.csv", index=False)
    pd.DataFrame([{"cnpj_fundo": FUNDO_A, "nome_foto": "FIDC A"}]).to_csv(
        tmp_path / "industry_carteira_1_scope.csv", index=False
    )
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=99, origem=ORIGEM_MANUAL,
               data_dir=tmp_path)

    seeded = seed_registry(tmp_path)

    linha = seeded[seeded["cnpj"].eq(FUNDO_A)].iloc[0]
    assert linha["subordinacao_minima_pct"] == 99
    assert linha["origem"] == ORIGEM_MANUAL

    forcado = seed_registry(tmp_path, overwrite=True)

    assert forcado[forcado["cnpj"].eq(FUNDO_A)].iloc[0]["origem"] == ORIGEM_CARTEIRA_101


# ---------------------------------------------------------------------------
# Resolução
# ---------------------------------------------------------------------------

def test_cada_fundo_entra_com_a_sua_competencia_mais_recente(data_dir: Path) -> None:
    """Julho para um, junho para outro: a carteira mistura sem preferir um mês."""

    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=15, data_dir=data_dir)
    save_entry(cnpj=FUNDO_B, subordinacao_minima_pct=10, data_dir=data_dir)

    frame = resolve_portfolio(data_dir).frame.set_index("cnpj")

    assert frame.at[FUNDO_A, "competencia"] == "2026-07"
    assert frame.at[FUNDO_B, "competencia"] == "2026-06"
    # E o valor é o da competência escolhida, não o da anterior.
    assert frame.at[FUNDO_A, "sub_atual_pct"] == pytest.approx(25.0)
    assert frame.at[FUNDO_A, "pl_mm"] == pytest.approx(120.0)


def test_a_fracao_do_informe_vira_ponto_percentual(data_dir: Path) -> None:
    """O Informe reporta 0,08; o mínimo do registro está em 10 p.p."""

    save_entry(cnpj=FUNDO_B, subordinacao_minima_pct=10, data_dir=data_dir)

    linha = resolve_portfolio(data_dir).frame.iloc[0]

    assert linha["sub_atual_pct"] == pytest.approx(8.0)
    assert linha["folga_pp"] == pytest.approx(-2.0)
    assert bool(linha["abaixo_do_minimo"]) is True


def test_o_fundo_que_parou_de_reportar_sai_do_grafico(data_dir: Path) -> None:
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=15, data_dir=data_dir)
    save_entry(cnpj=FUNDO_MORTO, subordinacao_minima_pct=15, data_dir=data_dir)

    ativos = resolve_portfolio(data_dir).frame
    todos = resolve_portfolio(data_dir, somente_ativos=False).frame

    assert ativos["cnpj"].tolist() == [FUNDO_A]
    assert set(todos["cnpj"]) == {FUNDO_A, FUNDO_MORTO}


def test_o_estrutural_manda_quando_existe(data_dir: Path) -> None:
    """Havendo mezanino, a comparação é contra Sub+Mez, e o slide diz isso."""

    save_entry(
        cnpj=FUNDO_A,
        subordinacao_minima_pct=10,
        subordinacao_estrutural_pct=22,
        data_dir=data_dir,
    )

    linha = resolve_portfolio(data_dir).frame.iloc[0]

    assert linha["referencia_pct"] == pytest.approx(22.0)
    assert linha["referencia_tipo"] == "Estrutural (Sub+Mez)"
    assert linha["folga_pp"] == pytest.approx(3.0)


def test_sem_subordinacao_no_informe_o_fundo_nao_e_comparavel(data_dir: Path) -> None:
    save_entry(cnpj="44444444000134", subordinacao_minima_pct=10, data_dir=data_dir)

    frame = resolve_portfolio(data_dir, somente_ativos=False).frame
    linha = frame[frame["cnpj"].eq("44444444000134")].iloc[0]

    assert bool(linha["comparavel"]) is False


# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------

def test_o_grafico_desenha_um_par_de_pontos_por_fundo(data_dir: Path) -> None:
    save_entry(cnpj=FUNDO_A, subordinacao_minima_pct=15, data_dir=data_dir)
    save_entry(cnpj=FUNDO_B, subordinacao_minima_pct=10, data_dir=data_dir)

    figure = dumbbell_figure(resolve_portfolio(data_dir).frame)
    axes = figure.axes[0]

    assert len(axes.collections) >= 3  # hastes + dois conjuntos de pontos
    pontos = [c for c in axes.collections if hasattr(c, "get_offsets") and len(c.get_offsets()) == 2]
    assert len(pontos) == 2


def test_o_grafico_vazio_nao_quebra(data_dir: Path) -> None:
    figure = dumbbell_figure(resolve_portfolio(data_dir).frame)

    assert figure.axes


def test_o_nome_do_fundo_perde_a_boilerplate_registral() -> None:
    assert short_fund_name(
        "ATLANTA FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA"
    ) == "Atlanta"
    assert short_fund_name("CLASSE ÚNICA DO FIDC CRÉDITO NITRO AGRO") == "Crédito Nitro Agro"
    assert normalize_cnpj("11.111.111/0001-91") == FUNDO_A


# ---------------------------------------------------------------------------
# Deck
# ---------------------------------------------------------------------------

def test_a_troca_de_slides_nao_duplica_partes_no_pacote() -> None:
    """Trocar slides removendo e recriando emitiria dois ``slideN.xml``.

    O ``next_partname`` do python-pptx devolve um nome já ocupado quando a
    numeração das partes tem buraco — que é o que remover um slide do meio do
    deck produz.  Por isso a troca reescreve no lugar, e este teste guarda
    exatamente essa propriedade: nenhum nome de parte repetido depois de
    reescrever a carteira **e** acrescentar o ranking.
    """

    import warnings
    from io import BytesIO

    from pptx import Presentation

    from services.anbima_executive_export import append_anbima_slides
    from services.carteira_deck import REPLACED_SLIDE_RANGE, replace_structural_slides
    from services.industry_ppt_export import build_industry_pptx_bytes

    data_dir = ROOT / "data" / "industry_study"
    presentation = Presentation(BytesIO(build_industry_pptx_bytes(data_dir)))
    antes = len(presentation.slides)

    escritos = replace_structural_slides(presentation, data_dir)
    append_anbima_slides(presentation, data_dir)

    assert escritos == REPLACED_SLIDE_RANGE[1] - REPLACED_SLIDE_RANGE[0] + 1
    with warnings.catch_warnings(record=True) as capturados:
        warnings.simplefilter("always")
        buffer = BytesIO()
        presentation.save(buffer)
    duplicadas = [w for w in capturados if "Duplicate name" in str(w.message)]
    assert duplicadas == []

    reaberto = Presentation(BytesIO(buffer.getvalue()))
    assert len(reaberto.slides) > antes
    primeiro, ultimo = REPLACED_SLIDE_RANGE
    for numero in range(primeiro, ultimo + 1):
        slide = list(reaberto.slides)[numero - 1]
        textos = " ".join(
            shape.text_frame.text for shape in slide.shapes if shape.has_text_frame
        )
        assert "CARTEIRA 101" in textos
        assert any(shape.shape_type == 13 for shape in slide.shapes)


def test_a_aba_carteira_esta_no_menu_da_industria() -> None:
    from tabs.tab_industry_study import INDUSTRY_VIEW_TABS

    assert "Carteira" in INDUSTRY_VIEW_TABS


def test_o_registro_participa_da_chave_de_cache_das_exportacoes(tmp_path: Path) -> None:
    """Salvar um fundo tem de invalidar o deck; sem isso o site serve o antigo."""

    import tabs.tab_industry_study as painel
    from services.carteira_subordinacao import registry_path

    antes = painel._industry_export_signature()
    caminho = registry_path(painel._DATA_DIR)
    original = caminho.read_bytes()
    marca = caminho.stat().st_mtime
    try:
        caminho.write_bytes(original + b"\n99999999000199,,10,,False,manual,,,,\n")
        depois = painel._industry_export_signature()
    finally:
        caminho.write_bytes(original)
        import os

        os.utime(caminho, (marca, marca))

    assert depois != antes
