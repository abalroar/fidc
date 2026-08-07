"""Consolida, numa tabela só, cada alteração feita na revisão do Agro / Revenda.

As três planilhas de auditoria da revisão respondem perguntas diferentes — o que
aconteceu com cada estrutura da tabela interna, quanto o mínimo mudou, e o que o
regulamento de cada fundo adicional sustenta. Esta aqui junta as três numa linha
por alteração, no formato ``o que mudou / de que valor / para que valor / por
quê``, para que uma auditoria consiga percorrer a revisão inteira sem abrir três
arquivos e cruzar CNPJ na mão.

A tabela é derivada: as fontes são os CSVs de auditoria e a carteira já
resolvida, de modo que ela acompanha o que o pipeline realmente publica.

    python scripts/build_agro_revenda_auditoria_consolidada.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.carteira_subordinacao import (  # noqa: E402
    DEFAULT_DATA_DIR,
    ORIGEM_OVERRIDE,
    OVERRIDES_NAME,
    resolve_portfolio,
)

AUDITORIA_NAME = "agro_revenda_auditoria_tabela_interna.csv"
RECONCILIACAO_NAME = "agro_revenda_reconciliacao_minimo.csv"
ADICIONAIS_NAME = "agro_revenda_revisao_adicionais.csv"
SAIDA_NAME = "agro_revenda_auditoria_consolidada.csv"

FONTE_INTERNA = "Tabela interna de exposições agro — revisada por analista"

COLUNAS = [
    "id",
    "tipo_de_alteracao",
    "estrutura_tabela_interna",
    "fundo",
    "cnpj",
    "campo_alterado",
    "valor_anterior",
    "valor_novo",
    "fonte",
    "motivo",
    "artefato",
]


def _pct(valor: object) -> str:
    """Percentual com uma casa, ou travessão quando não há valor."""

    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor == "":
        return "—"
    return f"{float(valor):.1f}"


def construir(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    auditoria = pd.read_csv(data_dir / AUDITORIA_NAME, dtype=str).fillna("")
    reconciliacao = pd.read_csv(data_dir / RECONCILIACAO_NAME, dtype=str).fillna("")
    adicionais = pd.read_csv(data_dir / ADICIONAIS_NAME, dtype=str).fillna("")
    carteira = resolve_portfolio(data_dir=data_dir).frame

    por_cnpj = carteira.set_index("cnpj")
    linhas: list[dict[str, object]] = []

    # 1. O destino de cada uma das doze estruturas da tabela interna.
    for _, row in auditoria.iterrows():
        situacao = row["Situação"]
        linhas.append(
            {
                "tipo_de_alteracao": "Reconciliação da tabela interna",
                "estrutura_tabela_interna": row["Nome na tabela interna"],
                "fundo": row["Nome na nossa base"] or "—",
                "cnpj": row["CNPJ"],
                "campo_alterado": "presença no universo comparável",
                "valor_anterior": (
                    "presente" if situacao == "Já no slide 18" else "ausente"
                ),
                "valor_novo": situacao,
                "fonte": FONTE_INTERNA,
                "motivo": row["Critério do matching"],
                "artefato": AUDITORIA_NAME,
            }
        )

    # 2. O mínimo de subordinação, valor a valor.
    for _, row in reconciliacao.iterrows():
        cnpj = row["CNPJ"]
        divergiu = row["Divergiu?"] == "True"
        extraido = row["Mín. leitura automática"]
        linhas.append(
            {
                "tipo_de_alteracao": (
                    "Override do mínimo (divergência)"
                    if divergiu
                    else "Override do mínimo (confirmação)"
                ),
                "estrutura_tabela_interna": row["Estrutura"],
                "fundo": por_cnpj["fundo"].get(cnpj, "—"),
                "cnpj": cnpj,
                "campo_alterado": "subordinacao_minima_pct → referencia_pct",
                "valor_anterior": _pct(extraido),
                "valor_novo": _pct(row["Mín. tabela interna"]),
                "fonte": FONTE_INTERNA,
                "motivo": (
                    "Leitura automática diverge da tabela interna; prevalece o analista."
                    if divergiu
                    else (
                        "Estrutura ausente da base; o mínimo do analista entra na inclusão."
                        if not extraido
                        else "Leitura automática e tabela interna coincidem; override fixa a fonte."
                    )
                ),
                "artefato": RECONCILIACAO_NAME,
            }
        )

    # 3. Onde o override mexeu na folga publicada.
    for _, row in reconciliacao[reconciliacao["Divergiu?"] == "True"].iterrows():
        cnpj = row["CNPJ"]
        if cnpj not in por_cnpj.index:
            continue
        fundo = por_cnpj.loc[cnpj]
        atual = float(fundo["sub_atual_pct"])
        linhas.append(
            {
                "tipo_de_alteracao": "Folga recalculada",
                "estrutura_tabela_interna": row["Estrutura"],
                "fundo": fundo["fundo"],
                "cnpj": cnpj,
                "campo_alterado": "folga_pp",
                "valor_anterior": _pct(atual - float(row["Mín. leitura automática"])),
                "valor_novo": _pct(fundo["folga_pp"]),
                "fonte": FONTE_INTERNA,
                "motivo": "Consequência aritmética do mínimo revisado sobre a mesma subordinação atual.",
                "artefato": OVERRIDES_NAME,
            }
        )

    # 4. As classificações decididas na revisão, inclusive as contraintuitivas.
    #    O motivo vem do override, que separa a justificativa da categoria da
    #    justificativa do mínimo.
    overrides = pd.read_csv(data_dir / OVERRIDES_NAME, dtype=str).fillna("")
    motivos = overrides.set_index("cnpj")["categoria_motivo"]
    estruturas = overrides.set_index("cnpj")["estrutura_tabela_interna"]
    introduzidos = carteira[carteira["origem"].eq(ORIGEM_OVERRIDE)]
    for fundo in introduzidos.itertuples():
        linhas.append(
            {
                "tipo_de_alteracao": "Classificação estrutural",
                "estrutura_tabela_interna": estruturas.get(fundo.cnpj, "—"),
                "fundo": fundo.fundo,
                "cnpj": fundo.cnpj,
                "campo_alterado": "categoria_estrutural",
                "valor_anterior": "—",
                "valor_novo": fundo.categoria_estrutural,
                "fonte": FONTE_INTERNA,
                "motivo": motivos.get(fundo.cnpj, "") or "—",
                "artefato": OVERRIDES_NAME,
            }
        )

    # 5. O que a releitura dos regulamentos disse sobre cada fundo adicional.
    for _, row in adicionais.iterrows():
        manter = row["Manter Agro/Revenda?"]
        linhas.append(
            {
                "tipo_de_alteracao": "Revalidação documental",
                "estrutura_tabela_interna": "—",
                "fundo": row["Fundo"],
                "cnpj": row["CNPJ"],
                "campo_alterado": "evidência documental de Agro / Revenda",
                "valor_anterior": "Agro / Revenda",
                "valor_novo": (
                    "Agro / Revenda (sustentado)"
                    if manter == "Sim"
                    else "Agro / Revenda (sem evidência no regulamento)"
                ),
                "fonte": "Regulamento vigente na FundosNET",
                "motivo": (
                    f"Pontuação {row['Pontuação agro no regulamento']} em termos"
                    f" de lastro agro: {row['Termos']}."
                    if manter == "Sim"
                    else "O regulamento não traz vocabulário de operação agro; mantido e sinalizado para revisão."
                ),
                "artefato": ADICIONAIS_NAME,
            }
        )

    # 6. Os mínimos que só valem sob condição — o run-off, tipicamente.  Ficam
    #    fora da folga de propósito: descrevem um regime que ainda não vigora.
    condicionais = overrides[overrides["subordinacao_minima_condicional_pct"].ne("")]
    for _, row in condicionais.iterrows():
        linhas.append(
            {
                "tipo_de_alteracao": "Mínimo condicional registrado",
                "estrutura_tabela_interna": row["estrutura_tabela_interna"],
                "fundo": por_cnpj["fundo"].get(row["cnpj"], row["fundo"]),
                "cnpj": row["cnpj"],
                "campo_alterado": "minimo_condicional_pct",
                "valor_anterior": "—",
                "valor_novo": f"{_pct(row['subordinacao_minima_condicional_pct'])} ({row['condicao']})",
                "fonte": FONTE_INTERNA,
                "motivo": (
                    f"A tabela interna dá dois mínimos. O vigente entra na folga; este"
                    f" passa a valer em {row['condicao'].lower()} e fica registrado ao lado."
                ),
                "artefato": OVERRIDES_NAME,
            }
        )

    tabela = pd.DataFrame(linhas)
    tabela.insert(0, "id", [f"A{n:03d}" for n in range(1, len(tabela) + 1)])
    return tabela[COLUNAS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    tabela = construir(args.data_dir)
    destino = args.data_dir / SAIDA_NAME
    tabela.to_csv(destino, index=False)
    print(f"{len(tabela)} alterações em {destino}")
    print(tabela["tipo_de_alteracao"].value_counts().to_string())


if __name__ == "__main__":
    main()
