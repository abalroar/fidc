"""Monta as duas bases da apuração documental da carteira.

``carteira_apuracao_documental.csv``
    Por que cada FIDC não reporta inadimplência e/ou PDD: as cláusulas do
    regulamento que justificariam o silêncio, a contraprova de terceiro
    (rating, demonstração financeira, verificação de lastro) e — explicitamente
    — o que não foi localizado.

``carteira_subordinacao_validacao.csv``
    O mínimo de subordinação em uso confrontado com o que o regulamento diz,
    com documento, página e trecho literal.

As duas nascem do mesmo acervo baixado da FundosNET, que não mora no
repositório (são centenas de megabytes de PDF extraído).  ``--docs-dir`` aponta
para o cache; o que fica versionado são os CSVs, com a evidência de cada linha.

    python scripts/build_carteira_apuracao.py --docs-dir <cache> [--extra <cache>]
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_apuracao_documental import (  # noqa: E402
    FAMILIAS,
    SEM_MEDICAO,
    medir_terceiro,
    varrer_clausulas,
    varrer_contraprova,
)
from services.carteira_estresse import nao_reportantes  # noqa: E402
from services.carteira_provisao import attach_provisao  # noqa: E402
from services.carteira_subordinacao import (  # noqa: E402
    DEFAULT_DATA_DIR,
    load_registry,
    resolve_portfolio,
    short_fund_name,
)
from services.carteira_validacao_subordinacao import validar  # noqa: E402

APURACAO_NAME = "carteira_apuracao_documental.csv"
VALIDACAO_NAME = "carteira_subordinacao_validacao.csv"

SEM_ACERVO = "sem documento no acervo"


def carregar_acervo(pastas: list[Path]) -> dict[str, list[dict]]:
    """CNPJ → documentos, com o regulamento mais recente à frente."""

    acervo: dict[str, list[dict]] = {}
    for pasta in pastas:
        for arquivo in sorted(Path(pasta).glob("*.json.gz")):
            registro = json.loads(gzip.decompress(arquivo.read_bytes()))
            acervo.setdefault(registro["cnpj"], []).extend(registro["documentos"])
    for documentos in acervo.values():
        documentos.sort(
            key=lambda d: (
                d.get("categoria") != "Regulamento",
                -(len(d.get("data_entrega") or "")),
                d.get("data_entrega") or "",
            ),
            reverse=False,
        )
    return acervo


def _regulamentos(acervo: dict[str, list[dict]]) -> dict[str, list[tuple[str, list[str]]]]:
    saida: dict[str, list[tuple[str, list[str]]]] = {}
    for cnpj, documentos in acervo.items():
        lista: list[tuple[str, list[str]]] = []
        regulamentos = [
            d for d in documentos if d.get("categoria") == "Regulamento" and d.get("pages")
        ]
        regulamentos.sort(key=lambda d: (d.get("data_entrega") or ""), reverse=True)
        for documento in regulamentos:
            identificador = (
                f"Regulamento {documento['id']} · {(documento.get('data_entrega') or '')[:10]}"
            )
            lista.append((identificador, documento["pages"]))
        for documento in documentos:
            tipo = (documento.get("tipo") or "").strip()
            if tipo in {"Prospecto", "Lâmina de Oferta de FIDC"} and documento.get("pages"):
                lista.append((f"{tipo} {documento['id']}", documento["pages"]))
        if lista:
            saida[cnpj] = lista
    return saida


def _diagnostico(clausulas: dict, contraprova: dict, medicao: dict) -> tuple[str, str]:
    """A frase da última coluna e a lista do que ficou em branco."""

    sustentam = [
        FAMILIAS[chave]["rotulo"]
        for chave, achado in clausulas.items()
        if achado["achou"] and achado["sinal"] == "afirmativa"
    ]
    negativas = [
        FAMILIAS[chave]["rotulo"]
        for chave, achado in clausulas.items()
        if achado["achou"] and achado["sinal"] == "negativa"
    ]
    fontes = contraprova["fontes"]

    partes: list[str] = []
    if sustentam:
        partes.append("Regulamento: " + "; ".join(sustentam))
    if negativas:
        partes.append("cessão sem regresso (" + "; ".join(negativas) + ")")
    if medicao["veredito"] != SEM_MEDICAO:
        partes.append(
            f"Informe Trimestral {medicao['referencia']}: vencidos "
            f"{medicao['vencidos_brl']:,.2f} e PDD {medicao['pdd_brl']:,.2f} "
            f"— {medicao['veredito']}"
        )
    elif fontes:
        partes.append("terceiro cita o tema em " + ", ".join(fontes))
    if not partes:
        partes.append("nada localizado nos documentos")

    lacunas: list[str] = []
    if not sustentam:
        lacunas.append("nenhuma cláusula que justifique ausência de inadimplência")
    if medicao["veredito"] == SEM_MEDICAO:
        lacunas.append("sem medição estruturada de terceiro para confirmar o zero")
    return " · ".join(partes), "; ".join(lacunas)


def construir_apuracao(data_dir: Path, acervo: dict[str, list[dict]]) -> pd.DataFrame:
    carteira = attach_provisao(resolve_portfolio(data_dir).frame, data_dir)
    carteira = carteira.assign(rotulo=carteira["fundo"].map(short_fund_name))
    pendentes = nao_reportantes(carteira)

    linhas: list[dict[str, object]] = []
    for fundo in pendentes.itertuples():
        documentos = acervo.get(fundo.cnpj) or []
        if not documentos:
            linhas.append(
                {
                    "cnpj": fundo.cnpj,
                    "fundo": fundo.rotulo,
                    "secao": fundo.categoria_estrutural,
                    "caso": fundo.caso,
                    "carteira_mm": fundo.carteira_dc / 1e6,
                    "inadimplencia_mm": fundo.dc_inadimplentes / 1e6,
                    "pdd_mm": (fundo.pdd_brl or 0) / 1e6,
                    "diagnostico": SEM_ACERVO,
                    "lacunas": "baixar o dossiê do fundo na FundosNET",
                    "contraprova_fontes": "",
                    "contraprova_trecho": "",
                }
            )
            continue

        clausulas = varrer_clausulas(documentos)
        contraprova = varrer_contraprova(documentos)
        medicao = medir_terceiro(documentos)
        diagnostico, lacunas = _diagnostico(clausulas, contraprova, medicao)

        linha: dict[str, object] = {
            "cnpj": fundo.cnpj,
            "fundo": fundo.rotulo,
            "secao": fundo.categoria_estrutural,
            "caso": fundo.caso,
            "carteira_mm": fundo.carteira_dc / 1e6,
            "inadimplencia_mm": fundo.dc_inadimplentes / 1e6,
            "pdd_mm": (fundo.pdd_brl or 0) / 1e6,
            "diagnostico": diagnostico,
            "lacunas": lacunas,
            "contraprova_fontes": ", ".join(contraprova["fontes"]),
            "contraprova_trecho": (
                contraprova["achados"][0]["trecho"] if contraprova["achados"] else ""
            ),
            "terceiro_veredito": medicao["veredito"],
            "terceiro_competencia": medicao.get("referencia", ""),
            "terceiro_vencidos_brl": medicao.get("vencidos_brl", ""),
            "terceiro_pdd_brl": medicao.get("pdd_brl", ""),
            "terceiro_documento": medicao.get("documento", ""),
        }
        for chave, achado in clausulas.items():
            linha[f"{chave}"] = "sim" if achado["achou"] else "não"
            linha[f"{chave}_sinal"] = achado["sinal"]
            linha[f"{chave}_fonte"] = (
                f"{achado['documento']} p.{achado['pagina']}" if achado["achou"] else ""
            )
            linha[f"{chave}_trecho"] = achado["trecho"]
        linhas.append(linha)
    return pd.DataFrame(linhas)


def construir_validacao(data_dir: Path, acervo: dict[str, list[dict]]) -> pd.DataFrame:
    registro = load_registry(data_dir)
    resultado = validar(registro, _regulamentos(acervo))
    carteira = resolve_portfolio(data_dir, somente_ativos=False).frame
    nomes = carteira.set_index("cnpj")["fundo"].map(short_fund_name)
    resultado.insert(1, "fundo", resultado["cnpj"].map(nomes).fillna(""))
    resultado["fonte_no_registro"] = resultado["cnpj"].map(
        registro.set_index("cnpj")["fonte"]
    )
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--docs-dir", type=Path, nargs="+", required=True)
    args = parser.parse_args()

    acervo = carregar_acervo(list(args.docs_dir))
    print(f"acervo: {len(acervo)} CNPJs")

    apuracao = construir_apuracao(args.data_dir, acervo)
    apuracao.to_csv(args.data_dir / APURACAO_NAME, index=False)
    print(f"{len(apuracao)} linhas em {APURACAO_NAME}")
    print(apuracao["diagnostico"].str.slice(0, 46).value_counts().to_string())

    validacao = construir_validacao(args.data_dir, acervo)
    validacao.to_csv(args.data_dir / VALIDACAO_NAME, index=False)
    print(f"\n{len(validacao)} linhas em {VALIDACAO_NAME}")
    print(validacao["veredito"].value_counts().to_string())


if __name__ == "__main__":
    main()
