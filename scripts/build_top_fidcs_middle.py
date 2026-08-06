"""Resolve the Top FIDCs Middle table from official sources.

Takes the curated input list (fund CNPJ, fund name, assignor, total) and fills
what — and only what — the official bases can confirm:

* **CVM, Ofertas Públicas de Distribuição** — the reference offer of each fund:
  registered volume, lead coordinator (``Nome_Lider``) and placement regime
  (``Regime_distribuicao``, the field that says firm commitment vs best
  efforts);
* **ANBIMA, Fundos 175 características público** — the official type and focus
  of the class.

Anything the bases do not state is written as ``Não identificado``.  Nothing is
inferred: the assignor is *not* assumed to be the originator, and the placement
regime is never guessed from the coordinator.

    python scripts/build_top_fidcs_middle.py --cvm-archive oferta_distribuicao.zip
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry_public_offers import SOURCE_URL as CVM_SOURCE_URL  # noqa: E402

DEFAULT_DATA_DIR = Path("data/industry_study")
INPUT_NAME = "top_fidcs_middle_input.csv"
OUTPUT_NAME = "top_fidcs_middle_resolved.csv"
CLASSIFICATION_NAME = "industry_anbima_classification.csv.gz"

PERIOD_START = "2026-01-01"
PERIOD_END = "2026-06-30"

UNKNOWN = "Não identificado"

#: Placement regime, verbatim from the CVM offer registration.
REGIME_LABELS = {
    "GARANTIA FIRME DE COLOCACAO": "Sim",
    "MELHORES ESFORCOS": "Não",
    "MISTO": "Misto",
}

#: Short names for the lead coordinators that show up in this list.
LEADER_SHORT = {
    "SINGULARE": "Singulare",
    "DAYCOVAL": "Daycoval",
    "QI ": "QI",
    "ITAU BBA": "Itaú BBA",
    "FINAXIS": "Finaxis",
    "UBS BB": "UBS BB",
    "ABC BRASIL": "ABC Brasil",
    "SANTANDER": "Santander",
    "XP ": "XP",
    "CARMEL": "Carmel",
    "OLIVEIRA TRUST": "Oliv. Trust",
    "VORTX": "Vórtx",
    "BRL TRUST": "BRL Trust",
    "HEMERA": "Hemera",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cvm-archive", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser.parse_args()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _ascii_upper(value: object) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.upper().strip()


def short_leader(name: str) -> str:
    upper = _ascii_upper(name)
    for token, label in LEADER_SHORT.items():
        if token in upper:
            return label
    return str(name).split()[0].title() if name else UNKNOWN


def load_offers(archive: Path) -> pd.DataFrame:
    with ZipFile(archive) as zipped:
        frame = pd.read_csv(
            zipped.open("oferta_resolucao_160.csv"),
            sep=";",
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )
    frame["cnpj"] = frame["CNPJ_Emissor"].map(_digits)
    frame["closing_date"] = pd.to_datetime(frame["Data_Encerramento"], errors="coerce")
    frame["volume_brl"] = pd.to_numeric(frame["Valor_Total_Registrado"], errors="coerce")
    return frame[
        frame["Status_Requerimento"].eq("Oferta Encerrada")
        & frame["closing_date"].notna()
        & frame["volume_brl"].gt(0)
    ]


def resolve(data_dir: Path, archive: Path) -> pd.DataFrame:
    source = pd.read_csv(data_dir / INPUT_NAME, sep=";", dtype={"cnpj_fundo": str})
    offers = load_offers(archive)
    classification = pd.read_csv(data_dir / CLASSIFICATION_NAME, dtype=str).set_index(
        "cnpj_fundo"
    )

    rows: list[dict[str, object]] = []
    for record in source.itertuples():
        cnpj = str(record.cnpj_fundo)
        fund_offers = offers[offers["cnpj"].eq(cnpj)]
        window = fund_offers[
            fund_offers["closing_date"].between(PERIOD_START, PERIOD_END)
        ]
        scope = "1S26"
        if window.empty and not fund_offers.empty:
            window = fund_offers[
                fund_offers["closing_date"].eq(fund_offers["closing_date"].max())
            ]
            scope = "oferta mais recente"
        if window.empty:
            scope = "sem oferta registrada"

        leaders = sorted({str(value).strip() for value in window["Nome_Lider"] if str(value).strip()})
        regimes = sorted({_ascii_upper(value) for value in window["Regime_distribuicao"]})
        itau = [name for name in leaders if "ITAU BBA" in _ascii_upper(name)]

        if not leaders:
            coordinator = UNKNOWN
        elif itau:
            coordinator = "Sim – IBBA Líder"
        else:
            coordinator = "Não – " + " / ".join(short_leader(name) for name in leaders)

        if not regimes:
            firm = UNKNOWN
        else:
            labels = {REGIME_LABELS.get(value, UNKNOWN) for value in regimes}
            firm = labels.pop() if len(labels) == 1 else "Misto"

        anbima = (
            classification.loc[cnpj] if cnpj in classification.index else None
        )
        if anbima is not None and isinstance(anbima, pd.DataFrame):
            anbima = anbima.iloc[0]

        rows.append(
            {
                "ordem": int(record.ordem),
                "fidc": record.fidc,
                "cnpj_fundo": cnpj,
                "cedente_informado": record.cedente,
                "tipo_anbima": (
                    str(anbima["tipo_anbima"]) if anbima is not None and str(anbima["tipo_anbima"]).strip() else UNKNOWN
                ),
                "foco_anbima": (
                    str(anbima["foco_anbima"]) if anbima is not None and str(anbima["foco_anbima"]).strip() else UNKNOWN
                ),
                "volume_emissao_brl": float(window["volume_brl"].sum()) if not window.empty else float("nan"),
                "ofertas_consideradas": int(len(window)),
                "escopo_oferta": scope,
                "data_referencia": (
                    window["closing_date"].max().date().isoformat() if not window.empty else ""
                ),
                "coordenador_lider": " | ".join(leaders) if leaders else UNKNOWN,
                "ibba_coordenou": coordinator,
                "regime_distribuicao": " | ".join(regimes) if regimes else UNKNOWN,
                "garantia_firme": firm,
                "originador": UNKNOWN,
                "total_cessoes_brl": float(record.total_brl),
                "fonte_volume": "CVM, Ofertas Públicas de Distribuição (RCVM 160)",
                "fonte_classificacao": "ANBIMA, Fundos 175 características público",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    resolved = resolve(args.data_dir, args.cvm_archive)
    output = args.data_dir / OUTPUT_NAME
    resolved.to_csv(output, index=False)
    confirmed = int(resolved["volume_emissao_brl"].notna().sum())
    print(f"resolvidos: {output}")
    print(f"  fundos: {len(resolved)} | com oferta identificada na CVM: {confirmed}")
    print(f"  fonte CVM: {CVM_SOURCE_URL}")


if __name__ == "__main__":
    main()
