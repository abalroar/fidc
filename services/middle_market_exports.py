"""As bases analíticas que a seção de exportações entrega prontas.

Cada função devolve **bytes**, e não um caminho: é isso que o botão de download
do Streamlit consome, e é o que garante que o arquivo servido saiu da mesma
base que a página está exibindo — nunca de um artefato antigo em disco.

Os artefatos vêm de lugares distintos e não têm um construtor comum, então cada
um traz o seu:

``build_top100_middle_xlsx_bytes``
    A planilha de revisão do universo Middle: tabela do Excel com filtro,
    ordenação e lista suspensa na coluna ``MIDDLE``.

``build_cedentes_triagem_csv_bytes``
    Um par fundo–cedente por linha, com capital social, CNAE e o **motivo** da
    classificação — é por ele que a triagem se contesta caso a caso.

``build_revalidacao_secoes_csv_bytes``
    A leitura dos regulamentos que confirma ou corrige a seção de cada FIDC da
    carteira, com o trecho literal que sustenta cada veredito.

``build_carteira101_subordinacao_xlsx_bytes``
    Subordinação atual contra o mínimo, com o gráfico de bolhas nativo.

``build_agro_auditoria_csv_bytes``
    Uma linha por alteração da revisão do Agro / Revenda — o que mudou, de que
    valor para que valor, por quê e em que artefato.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"

REVIEW_NAME = "top100_fidcs_middle_review.csv"
TRIAGE_NAME = "top100_cedentes_middle_triagem.csv"
REVALIDATION_NAME = "carteira_revalidacao_secoes.csv"
AGRO_AUDIT_NAME = "agro_revenda_auditoria_consolidada.csv"
APURACAO_NAME = "carteira_apuracao_documental.csv"
VALIDACAO_NAME = "carteira_subordinacao_validacao.csv"

#: Arquivos que estas exportações leem.  Entram na chave de cache da seção,
#: senão uma atualização de base continuaria servindo o download anterior.
EXPORT_DATA_INPUTS: tuple[str, ...] = (
    REVIEW_NAME,
    TRIAGE_NAME,
    REVALIDATION_NAME,
    AGRO_AUDIT_NAME,
    APURACAO_NAME,
    VALIDACAO_NAME,
)


def _csv_bytes(path: Path) -> bytes:
    """O CSV como está em disco, validado como tabela antes de sair.

    Ler e reescrever em vez de copiar os bytes crus garante que um arquivo
    truncado ou corrompido falhe aqui — e o botão apareça desabilitado com o
    motivo — em vez de chegar ilegível na mão de quem baixou.
    """

    frame = pd.read_csv(path, dtype=str)
    if frame.empty:
        raise ValueError(f"{path.name} está vazio.")
    buffer = BytesIO()
    frame.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue()


def build_top100_middle_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    from scripts.build_top100_middle_review_xlsx import write_workbook
    from services.top100_middle_deck import load_review

    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "top100.xlsx"
        write_workbook(load_review(data_dir), destino)
        return destino.read_bytes()


def build_cedentes_triagem_csv_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _csv_bytes(Path(data_dir) / TRIAGE_NAME)


def build_revalidacao_secoes_csv_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _csv_bytes(Path(data_dir) / REVALIDATION_NAME)


def build_carteira101_subordinacao_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    import tempfile

    from scripts.build_carteira101_subordinacao_xlsx import build_frame, write_workbook

    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "carteira101.xlsx"
        write_workbook(build_frame(data_dir), destino)
        return destino.read_bytes()


def build_agro_auditoria_csv_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    return _csv_bytes(Path(data_dir) / AGRO_AUDIT_NAME)


def build_apuracao_xlsx_bytes(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    """A munição da apuração: cláusulas, contraprova e a lista do que falta."""

    import tempfile

    from scripts.build_carteira_apuracao_xlsx import (
        CABECALHO_BRANCO,
        CABECALHO_VALIDACAO,
        _cabecalho_apuracao,
        _escrever,
        montar_em_branco,
    )
    from openpyxl import Workbook

    pasta = Path(data_dir)
    apuracao = pd.read_csv(pasta / APURACAO_NAME, dtype={"cnpj": str}).fillna("")
    validacao = pd.read_csv(pasta / VALIDACAO_NAME, dtype={"cnpj": str}).fillna("")
    branco = montar_em_branco(apuracao, validacao)

    workbook = Workbook()
    workbook.remove(workbook.active)
    _escrever(workbook, "Apuração", _cabecalho_apuracao(), apuracao, "Apuracao")
    _escrever(workbook, "Subordinação", CABECALHO_VALIDACAO, validacao, "Subordinacao")
    _escrever(workbook, "Em branco", CABECALHO_BRANCO, branco, "EmBranco")

    with tempfile.TemporaryDirectory() as temporaria:
        destino = Path(temporaria) / "apuracao.xlsx"
        workbook.save(destino)
        return destino.read_bytes()


__all__ = [
    "AGRO_AUDIT_NAME",
    "APURACAO_NAME",
    "VALIDACAO_NAME",
    "EXPORT_DATA_INPUTS",
    "REVALIDATION_NAME",
    "REVIEW_NAME",
    "TRIAGE_NAME",
    "build_agro_auditoria_csv_bytes",
    "build_apuracao_xlsx_bytes",
    "build_carteira101_subordinacao_xlsx_bytes",
    "build_cedentes_triagem_csv_bytes",
    "build_revalidacao_secoes_csv_bytes",
    "build_top100_middle_xlsx_bytes",
]
