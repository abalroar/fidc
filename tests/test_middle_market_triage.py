"""A triagem de prováveis clientes Middle Market entre os cedentes."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.middle_market_triage import (  # noqa: E402
    CAPITAL_MAXIMO,
    CAPITAL_MINIMO,
    IMPROVAVEL,
    NAO_AVALIADO,
    PROVAVEL,
    triar,
)


def test_a_faixa_de_capital_separa_o_middle_das_pontas() -> None:
    dentro = triar(
        "11111111000191",
        razao_social="LISTO INSTITUICAO DE PAGAMENTO LTDA",
        capital_social=16_500_000,
        situacao="ATIVA",
    )
    pequeno = triar(
        "22222222000172", razao_social="PADARIA DO ZE LTDA", capital_social=50_000,
        situacao="ATIVA",
    )
    grande = triar(
        "33333333000153", razao_social="CARGILL AGRICOLA S A",
        capital_social=8_179_542_524, situacao="ATIVA",
    )

    assert dentro.classificacao == PROVAVEL
    assert pequeno.classificacao == IMPROVAVEL and "piso" in pequeno.motivo
    assert grande.classificacao == IMPROVAVEL and "teto" in grande.motivo


def test_as_bordas_da_faixa_pertencem_ao_provavel() -> None:
    for capital in (CAPITAL_MINIMO, CAPITAL_MAXIMO):
        veredito = triar(
            "11111111000191", razao_social="EMPRESA X", capital_social=capital,
            situacao="ATIVA",
        )
        assert veredito.classificacao == PROVAVEL


def test_o_cedente_que_e_fundo_nao_e_cliente() -> None:
    """FIDC cedendo para FIDC é estrutura da operação, não cliente da mesa."""

    por_nome = triar(
        "11111111000191",
        razao_social="SB CREDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS",
        capital_social=50_000_000,
        situacao="ATIVA",
    )
    por_cnae = triar(
        "22222222000172", razao_social="VEICULO X", cnae="6470101",
        capital_social=50_000_000, situacao="ATIVA",
    )

    assert por_nome.classificacao == IMPROVAVEL
    assert por_cnae.classificacao == IMPROVAVEL
    assert "fundo" in por_nome.motivo


def test_banco_e_contraparte_e_nao_middle() -> None:
    assert triar(
        "11111111000191", razao_social="BANCO PINE S/A", capital_social=100_000_000,
        situacao="ATIVA",
    ).classificacao == IMPROVAVEL
    assert triar(
        "22222222000172", razao_social="INSTITUICAO X", cnae="6422100",
        capital_social=100_000_000, situacao="ATIVA",
    ).classificacao == IMPROVAVEL


def test_pessoa_fisica_e_cedente_pulverizado() -> None:
    assert triar("12345678901").classificacao == IMPROVAVEL


def test_ausencia_de_dado_nao_vira_improvavel() -> None:
    """Não saber não é o mesmo que saber que não; a distinção é o ponto."""

    sem_cadastro = triar("11111111000191")
    sem_capital = triar("22222222000172", razao_social="EMPRESA Y", situacao="ATIVA")

    assert sem_cadastro.classificacao == NAO_AVALIADO
    assert sem_capital.classificacao == NAO_AVALIADO


def test_cadastro_baixado_nao_e_cliente() -> None:
    assert triar(
        "11111111000191", razao_social="EMPRESA Z", capital_social=10_000_000,
        situacao="BAIXADA",
    ).classificacao == IMPROVAVEL


def test_o_campo_ausente_do_cadastro_nao_quebra_a_triagem() -> None:
    """Colunas do cadastro curado chegam como NaN, e NaN não é string."""

    veredito = triar(
        "11111111000191",
        razao_social=float("nan"),
        situacao=float("nan"),
        capital_social=float("nan"),
        uf=float("nan"),
    )

    assert veredito.classificacao == NAO_AVALIADO
    assert veredito.razao_social == ""


# ---------------------------------------------------------------------------
# A base publicada
# ---------------------------------------------------------------------------

def _triagem() -> pd.DataFrame:
    return pd.read_csv(
        ROOT / "data" / "industry_study" / "top100_cedentes_middle_triagem.csv", dtype=str
    )


def _review() -> pd.DataFrame:
    return pd.read_csv(
        ROOT / "data" / "industry_study" / "top100_fidcs_middle_review.csv", dtype=str
    )


def test_a_triagem_publica_traz_o_motivo_de_cada_linha() -> None:
    frame = _triagem()

    assert len(frame) > 0
    assert frame["motivo"].notna().all()
    assert set(frame["classificacao"]) <= {PROVAVEL, IMPROVAVEL, NAO_AVALIADO}


def test_a_revisao_sugere_middle_so_onde_ha_cedente_de_porte() -> None:
    """A sugestão não pode vazar para os cem: ela vem de uma máscara.

    ``Series.map`` aplica a função também ao ausente, e foi assim que os cem
    fundos saíram sugeridos na primeira versão.
    """

    review = _review()
    sugeridos = review["MIDDLE (preencher)"].eq("Provável")

    assert sugeridos.sum() < len(review)
    # Toda sugestão tem um cedente de porte por trás, nomeado na coluna ao lado.
    assert review.loc[sugeridos, "Cedente Provável Middle"].notna().all()
    assert review.loc[~sugeridos, "Cedente Provável Middle"].isna().all()


def test_o_originador_dos_top_fidcs_middle_sai_do_informe() -> None:
    """A coluna saía "Não identificado" em 16 de 16 por falta de fonte."""

    resolved = pd.read_csv(
        ROOT / "data" / "industry_study" / "top_fidcs_middle_resolved.csv", dtype=str
    )
    identificados = resolved["originador"].ne("Não identificado")

    assert identificados.sum() >= 15
    assert resolved.loc[identificados, "originador_fonte"].str.contains(
        "Informe Mensal"
    ).all()


# ---------------------------------------------------------------------------
# Exportações
# ---------------------------------------------------------------------------

def test_as_bases_analiticas_saem_como_bytes_da_base_atual() -> None:
    """O botão serve bytes construídos na hora, não um artefato velho em disco."""

    from services.middle_market_exports import (
        build_carteira101_subordinacao_xlsx_bytes,
        build_cedentes_triagem_csv_bytes,
        build_revalidacao_secoes_csv_bytes,
        build_top100_middle_xlsx_bytes,
        build_validacao_analistas_xlsx_bytes,
    )

    data_dir = ROOT / "data" / "industry_study"
    xlsx = (
        build_top100_middle_xlsx_bytes(data_dir),
        build_carteira101_subordinacao_xlsx_bytes(data_dir),
        build_validacao_analistas_xlsx_bytes(data_dir),
    )
    csv = (
        build_cedentes_triagem_csv_bytes(data_dir),
        build_revalidacao_secoes_csv_bytes(data_dir),
    )

    for conteudo in xlsx:
        assert conteudo.startswith(b"PK")  # um .xlsx é um zip
    for conteudo in csv:
        assert b"," in conteudo and len(conteudo) > 1000


def test_um_csv_truncado_falha_na_exportacao_e_nao_na_mao_de_quem_baixou(
    tmp_path: Path,
) -> None:
    """Ler e revalidar antes de servir é o que transforma corrupção em erro."""

    import pytest

    from services.middle_market_exports import TRIAGE_NAME, build_cedentes_triagem_csv_bytes

    (tmp_path / TRIAGE_NAME).write_text("", encoding="utf-8")

    with pytest.raises(Exception):
        build_cedentes_triagem_csv_bytes(tmp_path)


def test_as_bases_entram_na_chave_de_cache_das_exportacoes() -> None:
    """Sem isso, atualizar a triagem continuaria servindo o download anterior."""

    import os

    import tabs.tab_industry_study as painel
    from services.middle_market_exports import TRIAGE_NAME

    caminho = painel._DATA_DIR / TRIAGE_NAME
    antes = painel._industry_export_signature()
    original = caminho.read_bytes()
    marca = caminho.stat().st_mtime
    try:
        caminho.write_bytes(original + b"\n")
        depois = painel._industry_export_signature()
    finally:
        caminho.write_bytes(original)
        os.utime(caminho, (marca, marca))

    assert depois != antes
