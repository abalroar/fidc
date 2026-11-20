"""De-para de conglomerados para consolidar gestores/administradores de FIDC.

Regra de aplicacao (a mais clean possivel):
  1. Normaliza o CNPJ para 14 digitos (zero-padding).
  2. Se o CNPJ estiver em ``config/conglomerados_fidc.json``, usa o grupo e o
     ``tipo_controle`` daquele grupo.
  3. Caso contrario, o "grupo" e o proprio nome (limpo) e o ``tipo_controle`` e
     inferido por heuristica auditavel: bancos (por palavra-chave) -> "Ligada a
     banco"; grandes fiduciarios independentes (OT/BRL Trust/BR Trust) ->
     "Independente Grande"; demais -> "Independente".

Chave = CNPJ evita falsos positivos por nome (ex.: ITAUNA nao vira Itau).
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "conglomerados_fidc.json"


def cnpj14(value) -> str:
    """Normaliza qualquer CNPJ (float/str/int) para 14 digitos."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    s = re.sub(r"\D", "", s)  # remove pontuacao
    if not s:
        return ""
    # veio como float "3.082e+13"? trata via int
    try:
        if "e" in str(value).lower() or "." in str(value):
            s = str(int(float(value)))
    except Exception:
        pass
    return s.zfill(14)[-14:]


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def _load_config() -> dict:
    data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    cnpj_to_group: dict[str, tuple[str, str]] = {}
    for g in data["grupos"]:
        for cnpj in g["cnpjs"]:
            cnpj_to_group[cnpj14(cnpj)] = (g["grupo"], g["tipo_controle"])
    return {
        "cnpj_to_group": cnpj_to_group,
        "bancos": tuple(data.get("bancos_keywords_singleton", [])),
        "indep_grande": tuple(data.get("independente_grande_keywords", [])),
        "grupos": data["grupos"],
        "meta": data.get("_meta", {}),
    }


def _tipo_controle_heuristico(nome: str) -> str:
    up = _strip_accents(str(nome or "")).upper()
    cfg = _load_config()
    if any(k in up for k in cfg["indep_grande"]):
        return "Independente Grande"
    if any(k in up for k in cfg["bancos"]):
        return "Ligada a banco"
    return "Independente"


def _clean_name(nome: str) -> str:
    return re.sub(r"\s+", " ", str(nome or "").strip())


def resolve(nome, cnpj) -> tuple[str, str]:
    """Retorna (grupo_canonico, tipo_controle) para uma entidade."""
    cfg = _load_config()
    key = cnpj14(cnpj)
    if key in cfg["cnpj_to_group"]:
        return cfg["cnpj_to_group"][key]
    nome_limpo = _clean_name(nome)
    return nome_limpo, _tipo_controle_heuristico(nome_limpo)


def consolidate(df: pd.DataFrame, nome_col: str, cnpj_col: str,
                grupo_col: str = "grupo", tipo_col: str = "tipo_controle") -> pd.DataFrame:
    """Adiciona colunas de grupo consolidado e tipo de controle a um DataFrame."""
    out = df.copy()
    res = out.apply(lambda r: resolve(r.get(nome_col), r.get(cnpj_col)), axis=1)
    out[grupo_col] = [x[0] for x in res]
    out[tipo_col] = [x[1] for x in res]
    return out


def depara_table() -> pd.DataFrame:
    """Tabela auditavel do de-para (uma linha por membro)."""
    cfg = _load_config()
    rows = []
    for g in cfg["grupos"]:
        for cnpj, nome in g["cnpjs"].items():
            rows.append({"grupo": g["grupo"], "tipo_controle": g["tipo_controle"],
                         "cnpj": cnpj14(cnpj), "entidade_original": nome})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(depara_table().to_string(index=False))
