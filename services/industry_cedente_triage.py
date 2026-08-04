"""Ingestão auditável do mapa de cedentes da Tabela I do Informe Mensal.

O módulo mantém o perímetro restrito ao workbook ``FIDC_Cedentes_202606``:

* valida o contrato editorial da aba ``Leia-me`` e os cabeçalhos das três abas;
* liga ``Fundo x Cedente`` a ``Cedentes consolidados`` pelo documento declarado;
* preserva a razão social da coluna K e os atributos cadastrais consolidados;
* reduz repetições fundo--cedente sem apagar blocos, ordens ou percentuais;
* materializa uma fila Top N e a curva completa de cobertura por PL.

``PL alcançado`` continua sendo uma métrica de priorização: ele soma o PL dos
fundos que mencionam o cedente e não representa exposição econômica ao cedente.
Sacado e faturamento não existem no workbook e não são inferidos aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

import pandas as pd


SCHEMA_VERSION = "fidc-cedente-triage/v1"
DEFAULT_COMPETENCE = "202606"
DEFAULT_CUTOFF_RANK = 437
TARGET_COVERAGE_SHARES = (0.50, 0.70, 0.80, 0.90)

SHEET_README = "Leia-me"
SHEET_PRIORITY = "Priorização por PL"
SHEET_FUND_CEDENT = "Fundo x Cedente"
SHEET_CONSOLIDATED = "Cedentes consolidados"
REQUIRED_SHEETS = (
    SHEET_README,
    SHEET_PRIORITY,
    SHEET_FUND_CEDENT,
    SHEET_CONSOLIDATED,
)

PRIORITY_HEADERS = (
    "Rank PL",
    "CNPJ do fundo",
    "Fundo",
    "PL (R$)",
    "% do PL da indústria",
    "PL acumulado %",
    "Cedentes declarados",
    "Administrador",
)
FUND_CEDENT_HEADERS = (
    "Rank PL do fundo",
    "CNPJ do fundo",
    "Fundo",
    "PL do fundo (R$)",
    "PL acumulado %",
    "Bloco",
    "Ordem",
    "Doc do cedente",
    "Tipo",
    "% na carteira",
    "Razão social do cedente",
    "Nome fantasia",
    "CNAE principal",
    "Porte na Receita",
    "Capital social (R$)",
    "Optante Simples",
    "MEI",
    "UF",
    "Situação cadastral",
    "Matriz/Filial",
    "Início de atividade",
)
CONSOLIDATED_HEADERS = (
    "Doc do cedente",
    "Tipo",
    "Razão social",
    "CNAE principal",
    "Porte na Receita",
    "Capital social (R$)",
    "Optante Simples",
    "MEI",
    "UF",
    "Fundos em que aparece",
    "PL alcançado (R$)",
    "Maior % em um fundo",
    "Fundos (lista)",
)

README_REQUIRED_LABELS = (
    "O que a CVM entrega",
    "O que a CVM NÃO entrega",
    "Cobertura",
    "Sobre o campo Porte da Receita",
    "Regra de preenchimento",
)
README_REQUIRED_PHRASES = (
    "Tabela I",
    "não existe campo de sacado",
    "4.311 fundos",
    "1.908 declaram",
    "38,7% do PL",
    "R$ 30 a 500 mi",
    "Célula vazia significa ausência na fonte",
)

LIMITATIONS = (
    "A Tabela I identifica cedente; sacado ou devedor nomeado exige leitura documental.",
    "Porte na Receita separa ME, EPP e Demais; Demais não confirma faturamento entre R$ 30 mi e R$ 500 mi.",
    "Capital social é apenas sinal cadastral de porte e não equivale a receita.",
    "PL alcançado soma o PL integral dos fundos que mencionam o cedente e não mede exposição ao cedente.",
    "Percentuais ausentes, não positivos ou acima de 100% permanecem como declarados e recebem flag de qualidade.",
    "CPF e documentos com formato ou dígito verificador irregular permanecem na fila sem correção ou preenchimento inferido.",
)


@dataclass(frozen=True)
class CedenteWorkbook:
    readme: pd.DataFrame
    priority: pd.DataFrame
    fund_cedent: pd.DataFrame
    consolidated: pd.DataFrame
    source_sha256: str


class CedenteWorkbookContractError(ValueError):
    """Indica quebra explícita no contrato do workbook de origem."""


def _clean_text(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value).strip())


def _fold_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _clean_text(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", _clean_text(value))


def _to_numeric(series: pd.Series, *, integer: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.astype("Int64") if integer else numeric.astype(float)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_cnpj_digits(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def check_digit(base: str, weights: tuple[int, ...]) -> str:
        remainder = sum(
            int(character) * weight
            for character, weight in zip(base, weights, strict=True)
        ) % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = check_digit(
        digits[:12],
        (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    second = check_digit(
        digits[:12] + first,
        (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    return digits[-2:] == first + second


def _valid_cpf_digits(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    def check_digit(base: str, weights: tuple[int, ...]) -> str:
        total = sum(
            int(character) * weight
            for character, weight in zip(base, weights, strict=True)
        )
        value = (total * 10) % 11
        return "0" if value == 10 else str(value)

    first = check_digit(digits[:9], (10, 9, 8, 7, 6, 5, 4, 3, 2))
    second = check_digit(
        digits[:9] + first,
        (11, 10, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    return digits[-2:] == first + second


def normalize_cedente_document(value: object, declared_type: object) -> tuple[str, str, str]:
    """Return ``(raw, key, status)`` without inventing a missing leading zero."""

    raw = _clean_text(value)
    kind = _fold_text(declared_type)
    digits = _digits(raw)
    if kind == "cnpj" and len(digits) == 14:
        status = "cnpj_valido" if _valid_cnpj_digits(digits) else "cnpj_dv_invalido"
        return raw, f"CNPJ|{digits}", status
    if kind == "cpf" and len(digits) == 11:
        status = "cpf_valido" if _valid_cpf_digits(digits) else "cpf_dv_invalido"
        return raw, f"CPF|{digits}", status
    irregular_token = _fold_text(raw).upper() or "VAZIO"
    return raw, f"IRREGULAR|{irregular_token}", "irregular"


def _validate_headers(frame: pd.DataFrame, expected: Iterable[str], sheet: str) -> None:
    actual = tuple(_clean_text(value) for value in frame.columns)
    expected_tuple = tuple(expected)
    if actual != expected_tuple:
        raise CedenteWorkbookContractError(
            f"Cabeçalhos inesperados em {sheet}: esperado={expected_tuple!r}; atual={actual!r}"
        )


def validate_readme_contract(readme: pd.DataFrame) -> dict[str, Any]:
    """Validate the workbook's explicit statements before any materialization."""

    if readme.shape[0] < 12 or readme.shape[1] < 2:
        raise CedenteWorkbookContractError("A aba Leia-me deve cobrir ao menos A1:B12")
    title = _clean_text(readme.iloc[0, 0])
    if "jun/26" not in _fold_text(title):
        raise CedenteWorkbookContractError("A competência jun/26 não está declarada no título do Leia-me")

    labels = {_clean_text(value) for value in readme.iloc[:, 0].tolist() if _clean_text(value)}
    missing_labels = [label for label in README_REQUIRED_LABELS if label not in labels]
    if missing_labels:
        raise CedenteWorkbookContractError(f"Rótulos ausentes no Leia-me: {missing_labels}")

    readme_text = " ".join(_clean_text(value) for value in readme.to_numpy().ravel())
    folded = _fold_text(readme_text)
    missing_phrases = [
        phrase for phrase in README_REQUIRED_PHRASES if _fold_text(phrase) not in folded
    ]
    if missing_phrases:
        raise CedenteWorkbookContractError(
            f"Declarações obrigatórias ausentes no Leia-me: {missing_phrases}"
        )
    return {
        "title": title,
        "required_labels": list(README_REQUIRED_LABELS),
        "required_phrases": list(README_REQUIRED_PHRASES),
        "status": "validado",
    }


def _read_data_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, header=3, dtype=object).dropna(how="all")


def load_cedente_workbook(path: Path) -> CedenteWorkbook:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    excel = pd.ExcelFile(path)
    missing_sheets = [sheet for sheet in REQUIRED_SHEETS if sheet not in excel.sheet_names]
    if missing_sheets:
        raise CedenteWorkbookContractError(f"Abas obrigatórias ausentes: {missing_sheets}")

    readme = pd.read_excel(path, sheet_name=SHEET_README, header=None, dtype=object)
    validate_readme_contract(readme)
    priority = _read_data_sheet(path, SHEET_PRIORITY)
    fund_cedent = _read_data_sheet(path, SHEET_FUND_CEDENT)
    consolidated = _read_data_sheet(path, SHEET_CONSOLIDATED)
    _validate_headers(priority, PRIORITY_HEADERS, SHEET_PRIORITY)
    _validate_headers(fund_cedent, FUND_CEDENT_HEADERS, SHEET_FUND_CEDENT)
    _validate_headers(consolidated, CONSOLIDATED_HEADERS, SHEET_CONSOLIDATED)
    return CedenteWorkbook(
        readme=readme,
        priority=priority,
        fund_cedent=fund_cedent,
        consolidated=consolidated,
        source_sha256=_sha256_file(path),
    )


def normalize_priority(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.rename(
        columns={
            "Rank PL": "rank_pl_fundo",
            "CNPJ do fundo": "cnpj_fundo_raw",
            "Fundo": "fundo",
            "PL (R$)": "pl_fundo_reais",
            "% do PL da indústria": "pl_fundo_pct_industria_origem",
            "PL acumulado %": "pl_acumulado_pct_origem",
            "Cedentes declarados": "cedentes_declarados_fundo",
            "Administrador": "administrador",
        }
    ).copy()
    out["rank_pl_fundo"] = _to_numeric(out["rank_pl_fundo"], integer=True)
    out["pl_fundo_reais"] = _to_numeric(out["pl_fundo_reais"])
    out["pl_fundo_pct_industria_origem"] = _to_numeric(
        out["pl_fundo_pct_industria_origem"]
    )
    out["pl_acumulado_pct_origem"] = _to_numeric(out["pl_acumulado_pct_origem"])
    out["cedentes_declarados_fundo"] = _to_numeric(
        out["cedentes_declarados_fundo"], integer=True
    ).fillna(0)
    out["cnpj_fundo"] = out["cnpj_fundo_raw"].map(_digits)
    for column in ("fundo", "administrador", "cnpj_fundo_raw"):
        out[column] = out[column].map(_clean_text)
    out = out.sort_values("rank_pl_fundo", kind="stable").reset_index(drop=True)

    if out["rank_pl_fundo"].isna().any() or out["rank_pl_fundo"].duplicated().any():
        raise CedenteWorkbookContractError("Rank PL deve ser preenchido e único")
    expected_ranks = list(range(1, len(out) + 1))
    if out["rank_pl_fundo"].astype(int).tolist() != expected_ranks:
        raise CedenteWorkbookContractError("Rank PL deve formar a sequência 1..N")
    if out["cnpj_fundo"].str.len().ne(14).any() or out["cnpj_fundo"].duplicated().any():
        raise CedenteWorkbookContractError("CNPJ do fundo deve ser único e ter 14 dígitos")
    if out["pl_fundo_reais"].isna().any():
        raise CedenteWorkbookContractError("PL do fundo deve ser numérico")
    # PL negativo é uma qualidade observada no Informe Mensal. Ele permanece no
    # denominador e recebe flag, em vez de ser eliminado ou convertido em zero.
    out["pl_negativo_flag"] = out["pl_fundo_reais"].lt(0)
    return out


def normalize_fund_cedents(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.rename(
        columns={
            "Rank PL do fundo": "rank_pl_fundo",
            "CNPJ do fundo": "cnpj_fundo_raw",
            "Fundo": "fundo",
            "PL do fundo (R$)": "pl_fundo_reais",
            "PL acumulado %": "pl_acumulado_pct_origem",
            "Bloco": "bloco",
            "Ordem": "ordem",
            "Doc do cedente": "cedente_doc_raw",
            "Tipo": "cedente_tipo",
            "% na carteira": "percentual_na_carteira_origem",
            "Razão social do cedente": "cedente_razao_social_coluna_k",
            "Nome fantasia": "cedente_nome_fantasia_fundo_x",
            "CNAE principal": "cedente_cnae_principal_fundo_x",
            "Porte na Receita": "cedente_porte_receita_fundo_x",
            "Capital social (R$)": "cedente_capital_social_reais_fundo_x",
            "Optante Simples": "cedente_optante_simples_fundo_x",
            "MEI": "cedente_mei_fundo_x",
            "UF": "cedente_uf_fundo_x",
            "Situação cadastral": "cedente_situacao_cadastral_fundo_x",
            "Matriz/Filial": "cedente_matriz_filial_fundo_x",
            "Início de atividade": "cedente_inicio_atividade_fundo_x",
        }
    ).copy()
    out.insert(0, "linha_origem_excel", range(5, 5 + len(out)))
    out["rank_pl_fundo"] = _to_numeric(out["rank_pl_fundo"], integer=True)
    out["ordem"] = _to_numeric(out["ordem"], integer=True)
    out["pl_fundo_reais"] = _to_numeric(out["pl_fundo_reais"])
    out["pl_acumulado_pct_origem"] = _to_numeric(out["pl_acumulado_pct_origem"])
    out["percentual_na_carteira_origem"] = _to_numeric(
        out["percentual_na_carteira_origem"]
    )
    out["cedente_capital_social_reais_fundo_x"] = _to_numeric(
        out["cedente_capital_social_reais_fundo_x"]
    )
    out["cnpj_fundo"] = out["cnpj_fundo_raw"].map(_digits)
    documents = out.apply(
        lambda row: normalize_cedente_document(row["cedente_doc_raw"], row["cedente_tipo"]),
        axis=1,
        result_type="expand",
    )
    documents.columns = ["cedente_doc_raw", "cedente_doc_key", "cedente_documento_status"]
    out[["cedente_doc_raw", "cedente_doc_key", "cedente_documento_status"]] = documents
    text_columns = [
        "cnpj_fundo_raw",
        "fundo",
        "bloco",
        "cedente_tipo",
        "cedente_razao_social_coluna_k",
        "cedente_nome_fantasia_fundo_x",
        "cedente_cnae_principal_fundo_x",
        "cedente_porte_receita_fundo_x",
        "cedente_optante_simples_fundo_x",
        "cedente_mei_fundo_x",
        "cedente_uf_fundo_x",
        "cedente_situacao_cadastral_fundo_x",
        "cedente_matriz_filial_fundo_x",
        "cedente_inicio_atividade_fundo_x",
    ]
    for column in text_columns:
        out[column] = out[column].map(_clean_text)
    pct = out["percentual_na_carteira_origem"]
    out["percentual_ausente_flag"] = pct.isna()
    out["percentual_nao_positivo_flag"] = pct.notna() & pct.le(0)
    out["percentual_acima_100_flag"] = pct.notna() & pct.gt(1)
    out["percentual_invalido_flag"] = (
        out["percentual_ausente_flag"]
        | out["percentual_nao_positivo_flag"]
        | out["percentual_acima_100_flag"]
    )
    return out


def normalize_consolidated(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.rename(
        columns={
            "Doc do cedente": "cedente_doc_raw_consolidado",
            "Tipo": "cedente_tipo_consolidado",
            "Razão social": "cedente_razao_social_consolidada",
            "CNAE principal": "cedente_cnae_principal",
            "Porte na Receita": "cedente_porte_receita",
            "Capital social (R$)": "cedente_capital_social_reais",
            "Optante Simples": "cedente_optante_simples",
            "MEI": "cedente_mei",
            "UF": "cedente_uf",
            "Fundos em que aparece": "fundos_em_que_aparece",
            "PL alcançado (R$)": "pl_alcancado_reais",
            "Maior % em um fundo": "maior_pct_em_um_fundo",
            "Fundos (lista)": "fundos_lista",
        }
    ).copy()
    documents = out.apply(
        lambda row: normalize_cedente_document(
            row["cedente_doc_raw_consolidado"], row["cedente_tipo_consolidado"]
        ),
        axis=1,
        result_type="expand",
    )
    documents.columns = [
        "cedente_doc_raw_consolidado",
        "cedente_doc_key",
        "cedente_documento_status_consolidado",
    ]
    out[
        [
            "cedente_doc_raw_consolidado",
            "cedente_doc_key",
            "cedente_documento_status_consolidado",
        ]
    ] = documents
    for column in (
        "cedente_tipo_consolidado",
        "cedente_razao_social_consolidada",
        "cedente_cnae_principal",
        "cedente_porte_receita",
        "cedente_optante_simples",
        "cedente_mei",
        "cedente_uf",
        "fundos_lista",
    ):
        out[column] = out[column].map(_clean_text)
    for column in (
        "cedente_capital_social_reais",
        "pl_alcancado_reais",
        "maior_pct_em_um_fundo",
    ):
        out[column] = _to_numeric(out[column])
    out["fundos_em_que_aparece"] = _to_numeric(
        out["fundos_em_que_aparece"], integer=True
    )
    if out["cedente_doc_key"].duplicated().any():
        duplicates = out.loc[out["cedente_doc_key"].duplicated(False), "cedente_doc_key"].tolist()
        raise CedenteWorkbookContractError(
            f"Cedentes consolidados deve ter documento único; duplicados={duplicates[:10]}"
        )
    return out


def join_fund_cedents(
    fund_cedent: pd.DataFrame, consolidated: pd.DataFrame
) -> pd.DataFrame:
    joined = fund_cedent.merge(
        consolidated,
        on="cedente_doc_key",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    missing = joined["_merge"].ne("both")
    if missing.any():
        sample = joined.loc[missing, ["cedente_doc_raw", "cedente_doc_key"]].head(10)
        raise CedenteWorkbookContractError(
            "Documentos de Fundo x Cedente sem correspondência em Cedentes consolidados: "
            f"{sample.to_dict(orient='records')}"
        )
    joined = joined.drop(columns="_merge")
    k = joined["cedente_razao_social_coluna_k"].map(_fold_text)
    consolidated_name = joined["cedente_razao_social_consolidada"].map(_fold_text)
    joined["razao_social_match_flag"] = (
        k.ne("") & consolidated_name.ne("") & k.eq(consolidated_name)
    )
    return joined


def _unique_nonblank(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _first_nonblank(values: Iterable[object]) -> object:
    for value in values:
        if _clean_text(value):
            return value
    return ""


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _declaration_record(row: pd.Series) -> dict[str, Any]:
    pct = row["percentual_na_carteira_origem"]
    return {
        "bloco": _clean_text(row["bloco"]),
        "linha_origem_excel": int(row["linha_origem_excel"]),
        "ordem": None if pd.isna(row["ordem"]) else int(row["ordem"]),
        "percentual": None if pd.isna(pct) else float(pct),
        "percentual_acima_100_flag": bool(row["percentual_acima_100_flag"]),
        "percentual_ausente_flag": bool(row["percentual_ausente_flag"]),
        "percentual_nao_positivo_flag": bool(row["percentual_nao_positivo_flag"]),
    }


def consolidate_fund_cedents(joined: pd.DataFrame) -> pd.DataFrame:
    """Return one row per fund/document with full declaration evidence in JSON."""

    rows: list[dict[str, Any]] = []
    group_columns = ["cnpj_fundo", "cedente_doc_key"]
    joined = joined.sort_values("linha_origem_excel", kind="stable")
    for (_, _), group in joined.groupby(group_columns, sort=False, dropna=False):
        first = group.iloc[0]
        blocks = _unique_nonblank(group["bloco"])
        declarations = [_declaration_record(row) for _, row in group.iterrows()]
        pct_values = group["percentual_na_carteira_origem"].dropna().astype(float).tolist()
        names_k = _unique_nonblank(group["cedente_razao_social_coluna_k"])
        same_block_duplicate = any(group["bloco"].value_counts(dropna=False).gt(1))
        cross_block_duplicate = len(set(blocks)) > 1
        status = _clean_text(first["cedente_documento_status"])
        porte = _clean_text(first["cedente_porte_receita"])
        simples = _fold_text(first["cedente_optante_simples"])
        mei = _fold_text(first["cedente_mei"])
        hard_exclusion = porte in {"Microempresa", "Empresa de Pequeno Porte"} or (
            simples == "sim" or mei == "sim"
        )
        if status != "cnpj_valido":
            triage_status = "identidade_nao_resolvida"
            triage_limitation = (
                "CPF ou documento com formato/DV irregular; requer validação de identidade."
            )
        elif hard_exclusion:
            triage_status = "fora_faixa_por_cadastro"
            triage_limitation = "ME, EPP, Simples ou MEI exclui a faixa pretendida."
        else:
            triage_status = "candidato_revisao_manual"
            triage_limitation = (
                "Cadastro não confirma faturamento de R$ 30 mi a R$ 500 mi; requer fonte pública de receita."
            )
        rows.append(
            {
                "rank_pl_fundo": int(first["rank_pl_fundo"]),
                "cnpj_fundo": _clean_text(first["cnpj_fundo"]),
                "cnpj_fundo_raw": _clean_text(first["cnpj_fundo_raw"]),
                "fundo": _clean_text(first["fundo"]),
                "pl_fundo_reais": float(first["pl_fundo_reais"]),
                "pl_negativo_flag": bool(float(first["pl_fundo_reais"]) < 0),
                "pl_acumulado_pct_origem": float(first["pl_acumulado_pct_origem"]),
                "cedente_declarado_flag": True,
                "cedente_doc_raw": _clean_text(first["cedente_doc_raw"]),
                "cedente_doc_key": _clean_text(first["cedente_doc_key"]),
                "cedente_tipo": _clean_text(first["cedente_tipo"]),
                "cedente_documento_status": status,
                "cedente_razao_social_coluna_k": _clean_text(_first_nonblank(names_k)),
                "cedente_razoes_coluna_k_json": _json_dumps(names_k),
                "cedente_razao_social_consolidada": _clean_text(
                    first["cedente_razao_social_consolidada"]
                ),
                "razao_social_match_flag": bool(group["razao_social_match_flag"].all()),
                "cedente_cnae_principal": _clean_text(first["cedente_cnae_principal"]),
                "cedente_porte_receita": porte,
                "cedente_capital_social_reais": first["cedente_capital_social_reais"],
                "cedente_optante_simples": _clean_text(first["cedente_optante_simples"]),
                "cedente_mei": _clean_text(first["cedente_mei"]),
                "cedente_uf": _clean_text(first["cedente_uf"]),
                "fundos_em_que_aparece": first["fundos_em_que_aparece"],
                "pl_alcancado_reais": first["pl_alcancado_reais"],
                "maior_pct_em_um_fundo": first["maior_pct_em_um_fundo"],
                "fundos_lista": _clean_text(first["fundos_lista"]),
                "linhas_declaracao_origem": len(group),
                "blocos_declarados": " | ".join(blocks),
                "ordens_declaradas_json": _json_dumps(
                    [None if pd.isna(value) else int(value) for value in group["ordem"]]
                ),
                "percentuais_declarados_json": _json_dumps(pct_values),
                "declaracoes_json": _json_dumps(declarations),
                "duplicidade_fundo_cedente_flag": len(group) > 1,
                "duplicidade_cruza_blocos_flag": cross_block_duplicate,
                "duplicidade_mesmo_bloco_flag": same_block_duplicate,
                "percentual_ausente_flag": bool(group["percentual_ausente_flag"].any()),
                "percentual_nao_positivo_flag": bool(
                    group["percentual_nao_positivo_flag"].any()
                ),
                "percentual_acima_100_flag": bool(
                    group["percentual_acima_100_flag"].any()
                ),
                "percentual_invalido_flag": bool(group["percentual_invalido_flag"].any()),
                "soma_percentuais_declarados": sum(pct_values) if pct_values else pd.NA,
                "filtro_exclusao_me_epp_simples_flag": hard_exclusion,
                "middle_market_triage_status": triage_status,
                "middle_market_limitation": triage_limitation,
            }
        )
    return pd.DataFrame(rows)


def build_coverage_curve(priority: pd.DataFrame, *, cutoff_rank: int) -> pd.DataFrame:
    out = priority.copy().sort_values("rank_pl_fundo", kind="stable").reset_index(drop=True)
    total_pl = float(out["pl_fundo_reais"].sum())
    if total_pl <= 0:
        raise CedenteWorkbookContractError("PL total deve ser positivo")
    out["cedente_declarado_flag"] = out["cedentes_declarados_fundo"].gt(0)
    out["pl_com_cedente_reais"] = out["pl_fundo_reais"].where(
        out["cedente_declarado_flag"], 0.0
    )
    out["pl_sem_cedente_reais"] = out["pl_fundo_reais"].where(
        ~out["cedente_declarado_flag"], 0.0
    )
    out["pl_total_acumulado_reais"] = out["pl_fundo_reais"].cumsum()
    out["pl_total_acumulado_pct"] = out["pl_total_acumulado_reais"] / total_pl
    out["fundos_com_cedente_acumulado"] = out["cedente_declarado_flag"].cumsum().astype(int)
    out["fundos_sem_cedente_acumulado"] = (
        (~out["cedente_declarado_flag"]).cumsum().astype(int)
    )
    out["pl_com_cedente_acumulado_reais"] = out["pl_com_cedente_reais"].cumsum()
    out["pl_sem_cedente_acumulado_reais"] = out["pl_sem_cedente_reais"].cumsum()
    out["pl_com_cedente_acumulado_pct_industria"] = (
        out["pl_com_cedente_acumulado_reais"] / total_pl
    )
    out["pl_sem_cedente_acumulado_pct_industria"] = (
        out["pl_sem_cedente_acumulado_reais"] / total_pl
    )
    out["pl_com_cedente_pct_dentro_corte"] = (
        out["pl_com_cedente_acumulado_reais"] / out["pl_total_acumulado_reais"]
    )
    out["dentro_corte_recomendado_flag"] = out["rank_pl_fundo"].le(cutoff_rank)
    out["corte_recomendado_flag"] = out["rank_pl_fundo"].eq(cutoff_rank)
    out["marco_cobertura"] = ""
    for target in TARGET_COVERAGE_SHARES:
        reached = out.index[out["pl_total_acumulado_pct"].ge(target)]
        if len(reached):
            out.loc[reached[0], "marco_cobertura"] = f"{int(target * 100)}pct_pl"
    return out


def _gap_row(row: pd.Series) -> dict[str, Any]:
    return {
        "rank_pl_fundo": int(row["rank_pl_fundo"]),
        "cnpj_fundo": _clean_text(row["cnpj_fundo"]),
        "cnpj_fundo_raw": _clean_text(row["cnpj_fundo_raw"]),
        "fundo": _clean_text(row["fundo"]),
        "pl_fundo_reais": float(row["pl_fundo_reais"]),
        "pl_negativo_flag": bool(float(row["pl_fundo_reais"]) < 0),
        "pl_acumulado_pct_origem": float(row["pl_acumulado_pct_origem"]),
        "cedente_declarado_flag": False,
        "cedente_doc_raw": "",
        "cedente_doc_key": "",
        "cedente_tipo": "",
        "cedente_documento_status": "ausente_tabela_i",
        "cedente_razao_social_coluna_k": "",
        "cedente_razoes_coluna_k_json": "[]",
        "cedente_razao_social_consolidada": "",
        "razao_social_match_flag": False,
        "cedente_cnae_principal": "",
        "cedente_porte_receita": "",
        "cedente_capital_social_reais": pd.NA,
        "cedente_optante_simples": "",
        "cedente_mei": "",
        "cedente_uf": "",
        "fundos_em_que_aparece": pd.NA,
        "pl_alcancado_reais": pd.NA,
        "maior_pct_em_um_fundo": pd.NA,
        "fundos_lista": "",
        "linhas_declaracao_origem": 0,
        "blocos_declarados": "",
        "ordens_declaradas_json": "[]",
        "percentuais_declarados_json": "[]",
        "declaracoes_json": "[]",
        "duplicidade_fundo_cedente_flag": False,
        "duplicidade_cruza_blocos_flag": False,
        "duplicidade_mesmo_bloco_flag": False,
        "percentual_ausente_flag": True,
        "percentual_nao_positivo_flag": False,
        "percentual_acima_100_flag": False,
        "percentual_invalido_flag": True,
        "soma_percentuais_declarados": pd.NA,
        "filtro_exclusao_me_epp_simples_flag": False,
        "middle_market_triage_status": "sem_cedente_tabela_i",
        "middle_market_limitation": (
            "Tabela I sem cedente declarado; requer leitura de regulamento ou relatório de rating."
        ),
    }


def build_top_queue(
    priority: pd.DataFrame,
    consolidated_pairs: pd.DataFrame,
    *,
    cutoff_rank: int,
) -> pd.DataFrame:
    top = priority[priority["rank_pl_fundo"].le(cutoff_rank)].copy()
    pairs = consolidated_pairs[consolidated_pairs["rank_pl_fundo"].le(cutoff_rank)].copy()
    declared_funds = set(pairs["cnpj_fundo"])
    gap_rows = [
        _gap_row(row)
        for _, row in top[~top["cnpj_fundo"].isin(declared_funds)].iterrows()
    ]
    if gap_rows:
        pairs = pd.concat([pairs, pd.DataFrame(gap_rows)], ignore_index=True, sort=False)
    pairs = pairs.merge(
        top[
            [
                "cnpj_fundo",
                "cedentes_declarados_fundo",
                "administrador",
                "pl_fundo_pct_industria_origem",
            ]
        ],
        on="cnpj_fundo",
        how="left",
        validate="many_to_one",
    )
    pairs = pairs.sort_values(
        ["rank_pl_fundo", "cedente_declarado_flag", "cedente_doc_key"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)
    if pairs["cnpj_fundo"].nunique() != len(top):
        raise CedenteWorkbookContractError("A fila Top N deve preservar todos os fundos do corte")
    return pairs


def _cutoff_snapshot(curve: pd.DataFrame, rank: int) -> dict[str, Any]:
    row = curve.loc[curve["rank_pl_fundo"].eq(rank)]
    if row.empty:
        raise CedenteWorkbookContractError(f"Rank de corte ausente: {rank}")
    item = row.iloc[0]
    return {
        "rank": rank,
        "pl_acumulado_reais": float(item["pl_total_acumulado_reais"]),
        "pl_acumulado_pct": float(item["pl_total_acumulado_pct"]),
        "fundos_com_cedente": int(item["fundos_com_cedente_acumulado"]),
        "fundos_sem_cedente": int(item["fundos_sem_cedente_acumulado"]),
        "pl_com_cedente_reais": float(item["pl_com_cedente_acumulado_reais"]),
        "pl_com_cedente_pct_industria": float(
            item["pl_com_cedente_acumulado_pct_industria"]
        ),
        "pl_sem_cedente_reais": float(item["pl_sem_cedente_acumulado_reais"]),
        "pl_com_cedente_pct_dentro_corte": float(
            item["pl_com_cedente_pct_dentro_corte"]
        ),
    }


def _first_rank_at_share(curve: pd.DataFrame, share: float) -> int:
    rows = curve[curve["pl_total_acumulado_pct"].ge(share)]
    return int(rows.iloc[0]["rank_pl_fundo"]) if not rows.empty else int(curve.iloc[-1]["rank_pl_fundo"])


def _float_format(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value:.2f}"
    return f"{value:.12g}"


def _write_deterministic_csv(frame: pd.DataFrame, path: Path, *, gzip: bool) -> None:
    kwargs: dict[str, Any] = {
        "index": False,
        "encoding": "utf-8",
        "lineterminator": "\n",
        "float_format": _float_format,
    }
    if gzip:
        kwargs["compression"] = {"method": "gzip", "compresslevel": 9, "mtime": 0}
    frame.to_csv(path, **kwargs)


def materialize_cedente_triage(
    workbook_path: Path,
    output_dir: Path,
    *,
    competence: str = DEFAULT_COMPETENCE,
    cutoff_rank: int = DEFAULT_CUTOFF_RANK,
) -> dict[str, Any]:
    workbook_path = Path(workbook_path)
    output_dir = Path(output_dir)
    if not re.fullmatch(r"\d{6}", competence):
        raise ValueError("competence deve usar YYYYMM")

    source = load_cedente_workbook(workbook_path)
    readme_contract = validate_readme_contract(source.readme)
    priority = normalize_priority(source.priority)
    fund_cedent = normalize_fund_cedents(source.fund_cedent)
    consolidated = normalize_consolidated(source.consolidated)
    joined = join_fund_cedents(fund_cedent, consolidated)

    source_counts = fund_cedent.groupby("cnpj_fundo", sort=False).size()
    declared = priority.set_index("cnpj_fundo")["cedentes_declarados_fundo"].astype(int)
    aligned = declared.reindex(source_counts.index).fillna(-1).astype(int)
    if not aligned.eq(source_counts.astype(int)).all():
        raise CedenteWorkbookContractError(
            "Cedentes declarados em Priorização não reconciliam com as linhas Fundo x Cedente"
        )
    priority_declared_funds = set(priority.loc[priority["cedentes_declarados_fundo"].gt(0), "cnpj_fundo"])
    if priority_declared_funds != set(source_counts.index):
        raise CedenteWorkbookContractError(
            "O conjunto de fundos com cedente não reconcilia entre Priorização e Fundo x Cedente"
        )

    pairs = consolidate_fund_cedents(joined)
    curve = build_coverage_curve(priority, cutoff_rank=cutoff_rank)
    queue = build_top_queue(priority, pairs, cutoff_rank=cutoff_rank)

    output_dir.mkdir(parents=True, exist_ok=True)
    queue_path = output_dir / f"fidc_cedentes_top{cutoff_rank}_{competence}.csv.gz"
    curve_path = output_dir / f"fidc_cedentes_curva_cobertura_{competence}.csv"
    manifest_path = output_dir / f"fidc_cedentes_triagem_manifest_{competence}.json"
    _write_deterministic_csv(queue, queue_path, gzip=True)
    _write_deterministic_csv(curve, curve_path, gzip=False)

    total_pl = float(priority["pl_fundo_reais"].sum())
    with_cedent = priority["cedentes_declarados_fundo"].gt(0)
    duplicate_groups = int(pairs["duplicidade_fundo_cedente_flag"].sum())
    duplicate_extra_rows = int(
        (pairs.loc[pairs["duplicidade_fundo_cedente_flag"], "linhas_declaracao_origem"] - 1).sum()
    )
    threshold_ranks = {
        f"{int(share * 100)}pct_pl": _first_rank_at_share(curve, share)
        for share in TARGET_COVERAGE_SHARES
    }
    relevant_ranks = sorted(
        {rank for rank in (149, 300, cutoff_rank, 743, 1329) if rank <= len(curve)}
    )
    output_hashes = {
        queue_path.name: {"sha256": _sha256_file(queue_path), "bytes": queue_path.stat().st_size},
        curve_path.name: {"sha256": _sha256_file(curve_path), "bytes": curve_path.stat().st_size},
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "competence": competence,
        "source": {
            "file": workbook_path.name,
            "sha256": source.source_sha256,
            "readme_contract": readme_contract,
            "sheets": list(REQUIRED_SHEETS),
        },
        "contract": {
            "join": "Fundo x Cedente.Doc do cedente -> Cedentes consolidados.Doc do cedente",
            "reason_name": "Fundo x Cedente coluna K: Razão social do cedente",
            "attributes": "Cedentes consolidados colunas E:F e adjacentes",
            "duplicate_policy": (
                "Uma linha por fundo/documento; blocos, ordens, percentuais e linhas de origem preservados em JSON."
            ),
        },
        "coverage": {
            "fundos_total": len(priority),
            "pl_total_reais": total_pl,
            "fundos_com_cedente": int(with_cedent.sum()),
            "fundos_sem_cedente": int((~with_cedent).sum()),
            "pl_com_cedente_reais": float(priority.loc[with_cedent, "pl_fundo_reais"].sum()),
            "pl_sem_cedente_reais": float(priority.loc[~with_cedent, "pl_fundo_reais"].sum()),
            "pl_com_cedente_pct": float(
                priority.loc[with_cedent, "pl_fundo_reais"].sum() / total_pl
            ),
            "pl_sem_cedente_pct": float(
                priority.loc[~with_cedent, "pl_fundo_reais"].sum() / total_pl
            ),
        },
        "quality": {
            "linhas_fundo_x_cedente": len(fund_cedent),
            "fundos_fundo_x_cedente": int(fund_cedent["cnpj_fundo"].nunique()),
            "cedentes_unicos": int(consolidated["cedente_doc_key"].nunique()),
            "pares_fundo_cedente_consolidados": len(pairs),
            "grupos_duplicados_fundo_cedente": duplicate_groups,
            "linhas_adicionais_em_duplicidades": duplicate_extra_rows,
            "grupos_duplicados_cruzando_blocos": int(
                pairs["duplicidade_cruza_blocos_flag"].sum()
            ),
            "grupos_duplicados_no_mesmo_bloco": int(
                pairs["duplicidade_mesmo_bloco_flag"].sum()
            ),
            "linhas_percentual_acima_100": int(fund_cedent["percentual_acima_100_flag"].sum()),
            "linhas_percentual_nao_positivo": int(
                fund_cedent["percentual_nao_positivo_flag"].sum()
            ),
            "linhas_percentual_ausente": int(fund_cedent["percentual_ausente_flag"].sum()),
            "fundos_pl_negativo": int(priority["pl_negativo_flag"].sum()),
            "pl_negativo_reais": float(
                priority.loc[priority["pl_negativo_flag"], "pl_fundo_reais"].sum()
            ),
            "linhas_join_sem_correspondencia": 0,
            "cedentes_cnpj_dv_invalido": int(
                consolidated["cedente_documento_status_consolidado"]
                .eq("cnpj_dv_invalido")
                .sum()
            ),
            "cedentes_cpf_dv_invalido": int(
                consolidated["cedente_documento_status_consolidado"]
                .eq("cpf_dv_invalido")
                .sum()
            ),
            "cedentes_documento_irregular": int(
                consolidated["cedente_documento_status_consolidado"]
                .eq("irregular")
                .sum()
            ),
        },
        "cutoff": {
            "recommended_rank": cutoff_rank,
            "threshold_ranks": threshold_ranks,
            "snapshots": [_cutoff_snapshot(curve, rank) for rank in relevant_ranks],
            "top_queue": {
                "fundos": int(queue["cnpj_fundo"].nunique()),
                "linhas": len(queue),
                "fundos_com_cedente": int(
                    queue.loc[queue["cedente_declarado_flag"], "cnpj_fundo"].nunique()
                ),
                "fundos_sem_cedente": int(
                    queue.loc[~queue["cedente_declarado_flag"], "cnpj_fundo"].nunique()
                ),
                "pares_fundo_cedente": int(queue["cedente_declarado_flag"].sum()),
            },
        },
        "limitations": list(LIMITATIONS),
        "outputs": output_hashes,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(manifest_path)
    manifest["queue_path"] = str(queue_path)
    manifest["curve_path"] = str(curve_path)
    return manifest


__all__ = [
    "CedenteWorkbookContractError",
    "DEFAULT_COMPETENCE",
    "DEFAULT_CUTOFF_RANK",
    "SCHEMA_VERSION",
    "build_coverage_curve",
    "build_top_queue",
    "consolidate_fund_cedents",
    "join_fund_cedents",
    "load_cedente_workbook",
    "materialize_cedente_triage",
    "normalize_cedente_document",
    "normalize_consolidated",
    "normalize_fund_cedents",
    "normalize_priority",
    "validate_readme_contract",
]
