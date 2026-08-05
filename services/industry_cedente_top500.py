"""Top-500 FIDC cedent analysis built directly from CVM monthly reports.

The module is deliberately independent from the legacy single-competence
``industry_cedente_triage`` service.  It accepts in-memory frames or CVM CSV/
ZIP files, preserves the reported identifiers and percentages, and produces
deterministic analytical frames without materialising files.

Two data rules are central:

* Table IV selects one record per CNPJ with Fund rows ahead of Class rows;
  rows are never summed.
* ``PR_CEDENTE`` is used only to select a dominant cedent.  The whole fund PL
  is assigned to that dominant cedent, so the segment composition closes to
  100% of the Top 500 PL.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeAlias

import pandas as pd


SCHEMA_VERSION = "fidc-cedente-top500/v2"
DEFAULT_COMPETENCES = ("202312", "202412", "202512", "202606")
DEFAULT_CUTOFF_RANK = 500

TableSource: TypeAlias = pd.DataFrame | str | Path
RegistrySource: TypeAlias = pd.DataFrame | Mapping[str, Mapping[str, Any]] | None

_TABLE_BLOCKS = (
    ("TAB_I2A12", "com_retencao", 0),
    ("TAB_I2B12", "sem_retencao", 1),
)

_SEGMENT_ORDER = {
    "IFs": 0,
    "Agro": 1,
    "Infra e Energia": 2,
    "Large": 3,
    "Potencial Middle": 4,
    "Não classificado": 5,
    "Não informado": 6,
    "Sem cedente": 7,
}

_IF_NAME_PHRASES = (
    "QI",
    "BMP",
    "MAREE",
    "MULTIPLIKE",
    "PICPAY",
    "LISTO",
    "IFOOD PAGO",
    "CREDSYSTEM",
    "PARATI",
    "TRADEMASTER",
    "CAPITAL CONSIG",
    "MEUCASHCARD",
)

_IF_FINANCIAL_PHRASES = (
    "SCD",
    "IP",
    "BANCO",
    "SOCIEDADE DE CREDITO",
    "INSTITUICAO DE PAGAMENTO",
    "SECURITIZADORA",
    "FINANCEIRA",
)

_AGRO_NAME_PHRASES = (
    "RURAL",
    "AGRO",
    "FERTILIZANTE",
    "AGRICOLA",
    "AGROPECUARIA",
    "USINA",
    "ACUCAREIRA",
    "DEFENSIVO",
    "SEMENTE",
    "CEREAIS",
)

_INFRA_NAME_PHRASES = (
    "ENERGIA",
    "INFRAESTRUTURA",
    "ELETRIC",
    "SANEAMENTO",
    "TRANSMISSAO",
    "PETROLEO",
    "COMBUSTIVEL",
    "GAS",
    "RODOVIA",
    "FERROVIA",
    "PORTUARI",
    "AEROPORT",
    "TELECOM",
)

_DEFAULT_LARGE_NAME_PHRASES = (
    "PETROBRAS",
    "BRF",
    "MARFRIG",
    "RENAULT",
    "GENERAL MOTORS",
    "HYUNDAI",
    "HONDA",
    "STELLANTIS",
    "VOLKSWAGEN",
    "BAYER",
    "CARGILL",
    "SYNGENTA",
    "J&F",
    "PHILCO",
    "CONASA",
)

_REGISTRY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "documento": (
        "cedente_doc_key",
        "cnpj_cpf",
        "cnpj_cpf_cedente",
        "cnpj_do_cedente",
        "cnpj",
        "documento",
        "CNPJ/CPF",
        "CNPJ/CPF do cedente",
    ),
    "razao_social": (
        "razao_social",
        "razao_social_cedente",
        "Razão social",
        "Razão social do cedente",
    ),
    "cnae_codigo": (
        "cnae_codigo",
        "cnae_principal_codigo",
        "cnae_fiscal",
        "CNAE (cód.)",
        "CNAE codigo",
    ),
    "cnae_principal": (
        "cnae_principal",
        "cnae_principal_descricao",
        "cnae_fiscal_descricao",
        "CNAE principal",
    ),
    "secao_cnae": ("secao_cnae", "Seção CNAE"),
    "porte_receita": ("porte_receita", "porte", "Porte Receita"),
    "capital_social_reais": (
        "capital_social_reais",
        "capital_social",
        "Capital social (R$)",
    ),
    "simples": ("simples", "opcao_pelo_simples", "Simples"),
    "mei": ("mei", "opcao_pelo_mei", "MEI"),
    "uf": ("uf", "UF"),
    "municipio": ("municipio", "Município"),
    "situacao_cadastral": ("situacao_cadastral", "Situação cadastral"),
    "matriz_filial": ("matriz_filial", "Matriz/filial"),
    "natureza_cedente": ("natureza_cedente", "Natureza do cedente"),
    "segmento": ("segmento", "Segmento"),
    "criterio_segmento": ("criterio_segmento", "Critério do segmento"),
}


@dataclass(frozen=True)
class CedenteTop500Result:
    """Frames produced for one competence."""

    competencia: str
    top500: pd.DataFrame
    vinculos: pd.DataFrame
    fundos_sem_cedente: pd.DataFrame
    exclusoes: pd.DataFrame
    cobertura: pd.DataFrame
    pl_por_segmento: pd.DataFrame
    reparos_fonte: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "top500": self.top500.copy(),
            "vinculos": self.vinculos.copy(),
            "fundos_sem_cedente": self.fundos_sem_cedente.copy(),
            "exclusoes": self.exclusoes.copy(),
            "cobertura": self.cobertura.copy(),
            "pl_por_segmento": self.pl_por_segmento.copy(),
            "reparos_fonte": self.reparos_fonte.copy(),
        }


def _ascii_upper(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().upper()


def _digits(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\D", "", text)


def _normalize_cnae_code(value: object) -> str:
    """Preserve the seven-digit CNAE contract after Excel numeric coercion."""

    digits = _digits(value)
    if not digits:
        return ""
    return digits.zfill(7) if len(digits) <= 7 else digits


def _parse_number(value: object) -> float:
    if value is None or pd.isna(value):
        return float("nan")
    text = str(value).strip().replace("R$", "").replace("%", "").replace(" ", "")
    if not text:
        return float("nan")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _canonical_columns(frame: pd.DataFrame) -> dict[str, str]:
    return {_ascii_upper(column): str(column) for column in frame.columns}


def _find_column(
    frame: pd.DataFrame,
    candidates: Sequence[str],
    *,
    required: bool = False,
) -> str | None:
    columns = _canonical_columns(frame)
    for candidate in candidates:
        match = columns.get(_ascii_upper(candidate))
        if match is not None:
            return match
    if required:
        raise ValueError(f"coluna ausente; esperado um de {list(candidates)}")
    return None


def _filter_competence(frame: pd.DataFrame, competencia: str) -> pd.DataFrame:
    date_column = _find_column(frame, ("DT_COMPTC", "data", "competencia"))
    if date_column is None:
        return frame.copy()
    target = f"{competencia[:4]}-{competencia[4:6]}"
    values = frame[date_column].fillna("").astype(str).str.strip()
    compact = values.str.replace(r"\D", "", regex=True).str[:6]
    mask = values.str.startswith(target) | compact.eq(competencia)
    return frame.loc[mask].copy()


def _valid_repaired_cvm_row(fields: Sequence[str], *, source_name: str) -> bool:
    """Validate the stable prefix shared by CVM FIDC monthly tables."""

    if len(fields) < 4:
        return False
    if _ascii_upper(fields[0]) not in {"FUNDO", "CLASSE"}:
        return False
    if len(_digits(fields[1])) not in {12, 13, 14}:
        return False
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fields[3]).strip()):
        return False
    if "tab_iv" in source_name.lower():
        return all(not str(value).strip() or pd.notna(_parse_number(value)) for value in fields[-2:])
    return True


def _repair_cvm_csv_text(
    text: str,
    *,
    source_name: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Repair isolated unpaired quotes under a fail-closed structural gate.

    The December 2024 annual CVM archive contains two physical records with a
    single orphan quote.  A standards-compliant CSV parser joins every line
    between them into one record.  We repair only a physical line that:

    * contains exactly one quote;
    * already has the same delimiter count as the header;
    * yields the expected number of fields after the quote is removed; and
    * preserves the shared CVM prefix (record type, document and ISO date).

    Any other unbalanced-quote shape aborts the build instead of guessing.
    """

    lines = text.splitlines()
    if not lines:
        return text, []
    delimiter = ";" if lines[0].count(";") else ","
    expected_delimiters = lines[0].count(delimiter)
    expected_fields = expected_delimiters + 1
    repairs: list[dict[str, Any]] = []
    repaired_lines = list(lines)
    for line_number, line in enumerate(lines[1:], start=2):
        if line.count('"') % 2 == 0:
            continue
        if line.count('"') != 1 or line.count(delimiter) != expected_delimiters:
            raise ValueError(
                f"CSV {source_name} linha {line_number} tem aspas desbalanceadas "
                "fora do reparo estrutural permitido"
            )
        candidate = line.replace('",;', ';') if delimiter == ";" and '",;' in line else line
        action = (
            "remove_unpaired_quote_and_adjacent_comma"
            if candidate != line
            else "remove_unpaired_quote"
        )
        candidate = candidate.replace('"', "")
        fields = next(csv.reader([candidate], delimiter=delimiter, quotechar='"'))
        if len(fields) != expected_fields or not _valid_repaired_cvm_row(
            fields, source_name=source_name
        ):
            raise ValueError(
                f"CSV {source_name} linha {line_number} falhou no gate estrutural "
                "após tentativa de reparar aspa órfã"
            )
        repairs.append(
            {
                "fonte": source_name,
                "linha_fisica": line_number,
                "acao": action,
                "documento_fundo": _digits(fields[1]).zfill(14),
                "denominacao_reparada": str(fields[2]).strip(),
                "data_referencia": str(fields[3]).strip(),
            }
        )
        repaired_lines[line_number - 1] = candidate
    trailing_newline = "\n" if text.endswith(("\n", "\r")) else ""
    return "\n".join(repaired_lines) + trailing_newline, repairs


def _read_csv_bytes(payload: bytes, *, source_name: str = "fonte_csv") -> pd.DataFrame:
    for encoding in ("latin-1", "utf-8-sig", "utf-8"):
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError:
            continue
        text, repairs = _repair_cvm_csv_text(text, source_name=source_name)
        separator = ";" if text.splitlines() and text.splitlines()[0].count(";") else ","
        frame = pd.read_csv(
            io.StringIO(text),
            sep=separator,
            dtype=str,
            keep_default_na=False,
        )
        frame.attrs["source_repairs"] = repairs
        return frame
    raise ValueError("CSV não pôde ser decodificado")


def _member_for_table(
    archive: zipfile.ZipFile,
    *,
    table: str,
    competencia: str,
) -> str:
    token = f"_{table.lower()}_"
    candidates = sorted(
        name
        for name in archive.namelist()
        if token in name.lower() and name.lower().endswith(".csv")
    )
    if not candidates:
        raise ValueError(f"ZIP sem CSV da tabela {table}")
    monthly_suffix = f"_{competencia}.csv"
    annual_suffix = f"_{competencia[:4]}.csv"
    for suffix in (monthly_suffix, annual_suffix):
        matches = [name for name in candidates if name.lower().endswith(suffix)]
        if matches:
            return matches[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"ZIP contém múltiplos CSVs de {table} sem correspondência com {competencia}")


def load_cvm_table(
    source: TableSource,
    *,
    competencia: str,
    table: str,
) -> pd.DataFrame:
    """Load a CVM table from a DataFrame, extracted CSV, directory, or ZIP."""

    if not re.fullmatch(r"\d{6}", str(competencia)):
        raise ValueError("competencia deve seguir YYYYMM")
    if isinstance(source, pd.DataFrame):
        frame = source.copy()
    else:
        path = Path(source)
        if path.is_dir():
            monthly = path / f"inf_mensal_fidc_{table}_{competencia}.csv"
            annual = path / f"inf_mensal_fidc_{table}_{competencia[:4]}.csv"
            zip_monthly = path / f"inf_mensal_fidc_{competencia}.zip"
            zip_annual = path / f"inf_mensal_fidc_{competencia[:4]}.zip"
            matches = [candidate for candidate in (monthly, annual, zip_monthly, zip_annual) if candidate.exists()]
            if not matches:
                raise FileNotFoundError(f"tabela {table} de {competencia} ausente em {path}")
            path = matches[0]
        if not path.exists():
            raise FileNotFoundError(path)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                member = _member_for_table(archive, table=table, competencia=competencia)
                source_name = f"{path.name}!{member}"
                frame = _read_csv_bytes(archive.read(member), source_name=source_name)
        else:
            frame = _read_csv_bytes(path.read_bytes(), source_name=path.name)
    repairs = list(frame.attrs.get("source_repairs", []))
    frame.columns = [str(column).strip() for column in frame.columns]
    output = _filter_competence(frame, str(competencia)).reset_index(drop=True)
    output.attrs["source_repairs"] = repairs
    return output


def normalize_document(value: object, declared_type: object = "") -> dict[str, Any]:
    """Normalise a cedent identifier while preserving the source value.

    CVM CNPJs with 13 digits receive an unequivocal leading zero.  Repeated
    all-zero and all-nine identifiers remain visible but are flagged as
    fictitious and do not count towards real coverage.
    """

    raw = "" if value is None or pd.isna(value) else str(value).strip()
    digits_raw = _digits(value)
    declared = _ascii_upper(declared_type)
    zfill_flag = False
    zfill_13_flag = False
    inferred_type = declared if declared in {"CNPJ", "CPF"} else ""
    digits_norm = digits_raw
    if len(digits_raw) in {12, 13} and inferred_type != "CPF":
        digits_norm = digits_raw.zfill(14)
        inferred_type = "CNPJ"
        zfill_flag = True
        zfill_13_flag = len(digits_raw) == 13
    elif len(digits_raw) == 14:
        inferred_type = "CNPJ"
    elif len(digits_raw) == 11:
        inferred_type = "CPF"
    elif not inferred_type:
        inferred_type = "IRREGULAR"

    fictitious = bool(
        digits_norm
        and len(set(digits_norm)) == 1
        and digits_norm[0] in {"0", "9"}
    )
    valid_length = (
        (inferred_type == "CNPJ" and len(digits_norm) == 14)
        or (inferred_type == "CPF" and len(digits_norm) == 11)
    )
    if not digits_norm:
        status = "ausente"
        key = ""
    elif fictitious:
        status = "documento_ficticio"
        key = f"{inferred_type}|{digits_norm}"
    elif valid_length and zfill_flag:
        status = f"cnpj_zfill_{len(digits_raw)}"
        key = f"{inferred_type}|{digits_norm}"
    elif valid_length:
        status = f"{inferred_type.lower()}_comprimento_valido"
        key = f"{inferred_type}|{digits_norm}"
    else:
        inferred_type = "IRREGULAR"
        status = "documento_irregular"
        key = f"IRREGULAR|{digits_norm}"
    return {
        "documento_raw": raw,
        "documento_digitos_raw": digits_raw,
        "documento_digitos_norm": digits_norm,
        "documento_tipo": inferred_type,
        "documento_key": key,
        "documento_status": status,
        "cnpj_zfill_flag": zfill_flag,
        "cnpj_zfill_13_flag": zfill_13_flag,
        "documento_ficticio_flag": fictitious,
        "documento_real_flag": bool(valid_length and not fictitious),
    }


def _fund_document(value: object) -> dict[str, Any]:
    normalized = normalize_document(value, "CNPJ")
    return {
        "raw": normalized["documento_raw"],
        "digits": normalized["documento_digitos_norm"],
        "zfill": normalized["cnpj_zfill_flag"],
        "zfill13": normalized["cnpj_zfill_13_flag"],
        "valid": normalized["documento_tipo"] == "CNPJ"
        and len(normalized["documento_digitos_norm"]) == 14
        and not normalized["documento_ficticio_flag"],
    }


def normalize_tab_iv(frame: pd.DataFrame, *, competencia: str) -> pd.DataFrame:
    """Resolve Table IV to one Fund-first record per CNPJ."""

    source = _filter_competence(frame, competencia).reset_index(drop=True).copy()
    if source.empty:
        return pd.DataFrame()
    cnpj_column = _find_column(source, ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"), required=True)
    type_column = _find_column(source, ("TP_FUNDO_CLASSE", "TP_REGISTRO"))
    pl_column = _find_column(source, ("TAB_IV_A_VL_PL", "VL_PATRIM_LIQ", "PL"), required=True)
    name_column = _find_column(
        source,
        (
            "DENOM_SOCIAL",
            "DENOM_SOCIAL_FUNDO_CLASSE",
            "DENOM_SOCIAL_FUNDO",
            "DENOM_SOCIAL_CLASSE",
        ),
    )
    admin_column = _find_column(
        source,
        ("ADMINISTRADOR", "DENOM_SOCIAL_ADMINISTRADOR", "DENOM_SOCIAL_ADMIN"),
    )
    source["_source_row"] = range(1, len(source) + 1)
    fund_docs = source[cnpj_column].map(_fund_document)
    source["cnpj_fundo_raw"] = fund_docs.map(lambda item: item["raw"])
    source["cnpj_fundo"] = fund_docs.map(lambda item: item["digits"])
    source["cnpj_fundo_zfill_flag"] = fund_docs.map(lambda item: item["zfill"])
    source["cnpj_fundo_zfill_13_flag"] = fund_docs.map(lambda item: item["zfill13"])
    source["cnpj_fundo_valido_flag"] = fund_docs.map(lambda item: item["valid"])
    source = source.loc[source["cnpj_fundo_valido_flag"]].copy()
    if source.empty:
        return pd.DataFrame()
    source["tp_registro"] = (
        source[type_column].fillna("").astype(str).str.strip()
        if type_column
        else "Fundo"
    )
    normalized_type = source["tp_registro"].map(_ascii_upper)
    source["_type_priority"] = normalized_type.map({"FUNDO": 0, "CLASSE": 1}).fillna(2)
    source["pl_fundo_reais"] = source[pl_column].map(_parse_number)
    source["pl_reported_flag"] = source[pl_column].fillna("").astype(str).str.strip().ne("")
    source["fundo"] = source[name_column].fillna("").astype(str).str.strip() if name_column else ""
    source["administrador"] = (
        source[admin_column].fillna("").astype(str).str.strip() if admin_column else ""
    )
    stable_columns = sorted(str(column) for column in frame.columns)
    source["_stable_key"] = source[stable_columns].fillna("").astype(str).agg("\x1f".join, axis=1)
    grouped = source.groupby("cnpj_fundo", sort=False, dropna=False)
    source["tab_iv_source_rows"] = grouped["cnpj_fundo"].transform("size").astype(int)
    source["tab_iv_source_types"] = grouped["tp_registro"].transform(
        lambda values: " | ".join(sorted(set(values.astype(str))))
    )
    source["tab_iv_pl_values"] = grouped["pl_fundo_reais"].transform(
        lambda values: " | ".join(
            format(float(value), ".15g")
            for value in sorted(set(values.dropna().astype(float)))
        )
    )
    source["_pl_missing"] = source["pl_fundo_reais"].isna()
    selected = (
        source.sort_values(
            ["cnpj_fundo", "_type_priority", "_pl_missing", "_stable_key"],
            kind="mergesort",
        )
        .drop_duplicates("cnpj_fundo", keep="first")
        .copy()
    )
    selected["tab_iv_duplicate_rows_dropped"] = selected["tab_iv_source_rows"] - 1
    selected["tab_iv_selection_rule"] = "registro_unico"
    duplicate = selected["tab_iv_source_rows"].gt(1)
    both_types = selected["tab_iv_source_types"].map(
        lambda text: {_ascii_upper(item) for item in str(text).split("|")}
        >= {"FUNDO", "CLASSE"}
    )
    selected.loc[duplicate & both_types, "tab_iv_selection_rule"] = "fundo_preferido_sobre_classe"
    selected.loc[duplicate & ~both_types, "tab_iv_selection_rule"] = "desempate_deterministico_mesmo_tipo"
    selected["competencia"] = competencia
    selected["data"] = f"{competencia[:4]}-{competencia[4:6]}-01"
    columns = [
        "competencia",
        "data",
        "cnpj_fundo_raw",
        "cnpj_fundo",
        "cnpj_fundo_zfill_flag",
        "cnpj_fundo_zfill_13_flag",
        "fundo",
        "administrador",
        "tp_registro",
        "pl_fundo_reais",
        "pl_reported_flag",
        "tab_iv_source_rows",
        "tab_iv_duplicate_rows_dropped",
        "tab_iv_source_types",
        "tab_iv_pl_values",
        "tab_iv_selection_rule",
    ]
    return selected[columns].sort_values("cnpj_fundo", kind="mergesort").reset_index(drop=True)


def rank_top500(
    tab_iv: pd.DataFrame,
    *,
    competencia: str,
    cutoff_rank: int = DEFAULT_CUTOFF_RANK,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the deduplicated industry universe and its Top N by reported PL."""

    if cutoff_rank <= 0:
        raise ValueError("cutoff_rank deve ser positivo")
    universe = normalize_tab_iv(tab_iv, competencia=competencia)
    if universe.empty:
        return universe, universe.copy()
    eligible = universe.loc[universe["pl_fundo_reais"].notna()].copy()
    eligible = eligible.sort_values(
        ["pl_fundo_reais", "cnpj_fundo"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    eligible["rank_pl"] = range(1, len(eligible) + 1)
    industry_pl = float(universe["pl_fundo_reais"].sum(min_count=1))
    eligible["pl_industria_reais"] = industry_pl
    eligible["pl_industria_pct"] = (
        eligible["pl_fundo_reais"] / industry_pl if industry_pl else float("nan")
    )
    eligible["pl_industria_acumulado_pct"] = eligible["pl_industria_pct"].cumsum()
    top = eligible.head(cutoff_rank).copy().reset_index(drop=True)
    return universe, top


def _slot_column(frame: pd.DataFrame, prefix: str, stem: str, order: int) -> str | None:
    return _find_column(
        frame,
        (
            f"{prefix}_{stem}_{order}",
            f"{prefix}_{stem}{order}",
        ),
    )


def melt_table_i(
    frame: pd.DataFrame,
    top500: pd.DataFrame,
    *,
    competencia: str,
) -> pd.DataFrame:
    """Union Fund/Class Table I rows and melt I2A/I2B cedent slots."""

    source = _filter_competence(frame, competencia).reset_index(drop=True).copy()
    if source.empty or top500.empty:
        return pd.DataFrame()
    cnpj_column = _find_column(source, ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"), required=True)
    type_column = _find_column(source, ("TP_FUNDO_CLASSE", "TP_REGISTRO"))
    name_column = _find_column(
        source,
        ("DENOM_SOCIAL", "DENOM_SOCIAL_FUNDO_CLASSE", "DENOM_SOCIAL_FUNDO"),
    )
    source["_source_row"] = range(1, len(source) + 1)
    source["cnpj_fundo"] = source[cnpj_column].map(lambda value: _fund_document(value)["digits"])
    source = source.loc[source["cnpj_fundo"].isin(set(top500["cnpj_fundo"]))].copy()
    if source.empty:
        return pd.DataFrame()
    found_identifier_column = False
    records: list[dict[str, Any]] = []
    top_fields = top500.set_index("cnpj_fundo")
    for row in source.to_dict(orient="records"):
        cnpj_fundo = str(row["cnpj_fundo"])
        top_row = top_fields.loc[cnpj_fundo]
        for prefix, block, block_order in _TABLE_BLOCKS:
            for order in range(1, 10):
                doc_column = _slot_column(source, prefix, "CPF_CNPJ_CEDENTE", order)
                if doc_column is None:
                    continue
                found_identifier_column = True
                raw_document = row.get(doc_column, "")
                if not _digits(raw_document):
                    continue
                percentage_column = _slot_column(source, prefix, "PR_CEDENTE", order)
                type_slot_column = _slot_column(source, prefix, "TP_PESSOA_CEDENTE", order)
                normalized = normalize_document(
                    raw_document,
                    row.get(type_slot_column, "") if type_slot_column else "",
                )
                percentage_raw = row.get(percentage_column, "") if percentage_column else ""
                percentage_points = _parse_number(percentage_raw)
                records.append(
                    {
                        "competencia": competencia,
                        "data": f"{competencia[:4]}-{competencia[4:6]}-01",
                        "rank_pl": int(top_row["rank_pl"]),
                        "cnpj_fundo": cnpj_fundo,
                        "fundo": str(top_row["fundo"]),
                        "pl_fundo_reais": float(top_row["pl_fundo_reais"]),
                        "tp_registro_tabela_i": (
                            str(row.get(type_column, "Fundo")).strip() if type_column else "Fundo"
                        ),
                        "fundo_tabela_i": (
                            str(row.get(name_column, "")).strip() if name_column else ""
                        ),
                        "bloco": block,
                        "bloco_ordem": block_order,
                        "ordem": order,
                        "percentual_cedente_raw": str(percentage_raw).strip(),
                        "percentual_cedente_pontos": percentage_points,
                        "percentual_cedente": (
                            percentage_points / 100.0
                            if pd.notna(percentage_points)
                            else float("nan")
                        ),
                        "percentual_reportado_flag": bool(pd.notna(percentage_points)),
                        "percentual_acima_100_flag": bool(
                            pd.notna(percentage_points) and percentage_points > 100.0
                        ),
                        "source_row": int(row["_source_row"]),
                        **{
                            "cedente_documento_raw": normalized["documento_raw"],
                            "cedente_documento_digitos_raw": normalized["documento_digitos_raw"],
                            "cedente_documento": normalized["documento_digitos_norm"],
                            "cedente_tipo": normalized["documento_tipo"],
                            "cedente_doc_key": normalized["documento_key"],
                            "cedente_documento_status": normalized["documento_status"],
                            "cedente_cnpj_zfill_flag": normalized["cnpj_zfill_flag"],
                            "cedente_cnpj_zfill_13_flag": normalized["cnpj_zfill_13_flag"],
                            "cedente_documento_ficticio_flag": normalized["documento_ficticio_flag"],
                            "cedente_real_flag": normalized["documento_real_flag"],
                        },
                    }
                )
    if not found_identifier_column:
        raise ValueError("Tabela I sem campos TAB_I2A12/TAB_I2B12 de cedente")
    if not records:
        return pd.DataFrame()
    output = pd.DataFrame.from_records(records)
    key = ["competencia", "cnpj_fundo", "bloco", "ordem", "cedente_doc_key"]
    output["_percent_missing"] = output["percentual_cedente"].isna()
    output["_type_priority"] = output["tp_registro_tabela_i"].map(_ascii_upper).map(
        {"FUNDO": 0, "CLASSE": 1}
    ).fillna(2)
    output["_stable_key"] = output.fillna("").astype(str).agg("\x1f".join, axis=1)
    output["linhas_duplicadas_chave"] = output.groupby(key, dropna=False)[
        "cedente_doc_key"
    ].transform("size")
    output = (
        output.sort_values(
            key + ["_percent_missing", "percentual_cedente", "_type_priority", "_stable_key"],
            ascending=[True, True, True, True, True, True, False, True, True],
            kind="mergesort",
        )
        .drop_duplicates(key, keep="first")
        .drop(columns=["_percent_missing", "_type_priority", "_stable_key"])
    )
    return output.sort_values(
        ["rank_pl", "bloco_ordem", "ordem", "cedente_doc_key"], kind="mergesort"
    ).reset_index(drop=True)


def _registry_column(frame: pd.DataFrame, canonical: str) -> str | None:
    return _find_column(frame, _REGISTRY_ALIASES[canonical])


def _registry_frame(source: RegistrySource) -> pd.DataFrame:
    if source is None:
        return pd.DataFrame(columns=["cedente_doc_key"])
    if isinstance(source, Mapping) and not isinstance(source, pd.DataFrame):
        rows = []
        for document, values in source.items():
            row = dict(values)
            row.setdefault("documento", document)
            rows.append(row)
        frame = pd.DataFrame(rows)
    else:
        frame = source.copy()  # type: ignore[union-attr]
    if frame.empty:
        return pd.DataFrame(columns=["cedente_doc_key"])
    document_column = _registry_column(frame, "documento")
    if document_column is None:
        raise ValueError("cadastro/override sem coluna de documento")
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        raw_document = row.get(document_column, "")
        if str(raw_document).startswith(("CNPJ|", "CPF|", "IRREGULAR|")):
            key = str(raw_document)
        else:
            key = normalize_document(raw_document)["documento_key"]
        if not key:
            continue
        normalized: dict[str, Any] = {"cedente_doc_key": key}
        for canonical in _REGISTRY_ALIASES:
            if canonical == "documento":
                continue
            column = _registry_column(frame, canonical)
            normalized[canonical] = row.get(column, "") if column else ""
        rows.append(normalized)
    if not rows:
        return pd.DataFrame(columns=["cedente_doc_key"])
    output = pd.DataFrame(rows)
    output["cnae_codigo"] = output["cnae_codigo"].map(_normalize_cnae_code)
    output["_filled_fields"] = output.replace("", pd.NA).notna().sum(axis=1)
    output["_stable_key"] = output.fillna("").astype(str).agg("\x1f".join, axis=1)
    output = (
        output.sort_values(
            ["cedente_doc_key", "_filled_fields", "_stable_key"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .drop_duplicates("cedente_doc_key", keep="first")
        .drop(columns=["_filled_fields", "_stable_key"])
    )
    return output.reset_index(drop=True)


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = _ascii_upper(phrase)
    if len(normalized) <= 3 and " " not in normalized:
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(normalized)}(?![A-Z0-9])", text))
    return normalized in text


def _matches_any(text: str, phrases: Sequence[str]) -> str | None:
    for phrase in phrases:
        if _contains_phrase(text, phrase):
            return phrase
    return None


def _cnae_digits(value: object) -> str:
    return _digits(value)


def classify_natureza(record: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(natureza, criterion)`` from current cadastral fields."""

    name = _ascii_upper(record.get("razao_social", ""))
    cnae = _cnae_digits(record.get("cnae_codigo", ""))
    if cnae.startswith("6911"):
        return "Escritório de advocacia", "CNAE 6911"
    if cnae.startswith(("6462", "6463")) or _matches_any(name, ("HOLDING", "PARTICIPACOES")):
        return "Holding/participação", "CNAE/nome de holding"
    if _matches_any(name, ("FUNDO DE INVESTIMENTO", "FIDC", "SECURITIZADORA")):
        return "Fundo/securitizadora", "nome de fundo/securitizadora"
    if _matches_any(name, ("PREFEITURA", "MUNICIPIO", "ESTADO DE", "UNIAO FEDERAL", "SECRETARIA")):
        return "Ente público", "nome de ente público"
    financial_name = _matches_any(name, _IF_NAME_PHRASES + _IF_FINANCIAL_PHRASES)
    financial_cnae = cnae[:2] in {"64", "65", "66"} and not cnae.startswith(("6462", "6463"))
    if financial_name or financial_cnae:
        return "Instituição financeira", (
            f"nome financeiro: {financial_name}" if financial_name else f"CNAE {cnae[:2]}"
        )
    if name or cnae:
        return "Operacional", "cadastro operacional residual"
    return "Não classificado", "cadastro não resolvido"


def classify_segmento(
    record: Mapping[str, Any],
    *,
    large_name_phrases: Sequence[str] = _DEFAULT_LARGE_NAME_PHRASES,
) -> tuple[str, str]:
    """Apply the ordered fallback segment taxonomy required by the study."""

    if bool(record.get("cedente_documento_ficticio_flag", False)):
        return "Não informado", "documento fictício 0/9"
    name = _ascii_upper(record.get("razao_social", ""))
    cnae = _cnae_digits(record.get("cnae_codigo", ""))
    section = _ascii_upper(record.get("secao_cnae", ""))[:1]
    capital = _parse_number(record.get("capital_social_reais", ""))
    if not name and not cnae:
        return "Não classificado", "cadastro não resolvido"
    if cnae.startswith("6911"):
        return "Não classificado", "CNAE 6911 · cessão de precatório/honorário"

    financial_name = _matches_any(name, _IF_NAME_PHRASES + _IF_FINANCIAL_PHRASES)
    financial_cnae = cnae[:2] in {"64", "65", "66"} and not cnae.startswith(("6462", "6463"))
    if financial_name or financial_cnae:
        return "IFs", (
            f"nome financeiro: {financial_name}" if financial_name else f"CNAE financeiro {cnae[:2]}"
        )

    agro_name = _matches_any(name, _AGRO_NAME_PHRASES)
    agro_cnae = section == "A" or cnae.startswith(("20134", "20517", "10716", "10724"))
    if agro_name or agro_cnae:
        return "Agro", f"nome agro: {agro_name}" if agro_name else f"CNAE/seção agro {cnae or section}"

    infra_name = _matches_any(name, _INFRA_NAME_PHRASES)
    infra_cnae = section in {"B", "D", "E", "H"} or cnae[:2] in {
        "05", "06", "07", "08", "09", "35", "36", "37", "38", "39", "49", "50", "51", "52", "53", "61"
    }
    if infra_name or infra_cnae:
        return "Infra e Energia", (
            f"nome infra/energia: {infra_name}" if infra_name else f"CNAE/seção infra {cnae or section}"
        )

    large_name = _matches_any(name, tuple(large_name_phrases))
    vehicle_cnae = cnae.startswith(("2910", "2920"))
    large_capital = pd.notna(capital) and float(capital) >= 300_000_000
    if large_name or vehicle_cnae or large_capital:
        if large_name:
            criterion = f"grupo large pelo nome: {large_name}"
        elif vehicle_cnae:
            criterion = f"CNAE de montadora {cnae}"
        else:
            criterion = "capital social >= R$ 300 mi"
        return "Large", criterion
    return "Potencial Middle", "resíduo cadastral; faturamento não confirmado"


def enrich_and_classify_links(
    links: pd.DataFrame,
    *,
    cadastro: RegistrySource = None,
    registry_overrides: RegistrySource = None,
    large_name_phrases: Sequence[str] = _DEFAULT_LARGE_NAME_PHRASES,
) -> pd.DataFrame:
    if links.empty:
        return links.copy()
    base = _registry_frame(cadastro)
    overrides = _registry_frame(registry_overrides)
    output = links.copy()
    if not base.empty:
        output = output.merge(base, on="cedente_doc_key", how="left", validate="many_to_one")
    else:
        for canonical in _REGISTRY_ALIASES:
            if canonical != "documento":
                output[canonical] = ""
    if not overrides.empty:
        override_columns = [column for column in overrides.columns if column != "cedente_doc_key"]
        renamed = {column: f"{column}__override" for column in override_columns}
        output = output.merge(
            overrides.rename(columns=renamed), on="cedente_doc_key", how="left", validate="many_to_one"
        )
        for column in override_columns:
            override = output[f"{column}__override"]
            populated = override.notna() & override.astype(str).str.strip().ne("")
            if bool(populated.any()):
                output[column] = output[column].astype("object")
                output.loc[populated, column] = override.loc[populated].astype("object").to_numpy()
            output = output.drop(columns=f"{column}__override")
    for canonical in _REGISTRY_ALIASES:
        if canonical == "documento":
            continue
        if canonical not in output.columns:
            output[canonical] = ""
        output[canonical] = output[canonical].fillna("")
    output["cadastro_resolvido_flag"] = output[["razao_social", "cnae_codigo"]].apply(
        lambda row: any(str(value).strip() for value in row), axis=1
    )
    nature_values: list[str] = []
    nature_criteria: list[str] = []
    segment_values: list[str] = []
    segment_criteria: list[str] = []
    for record in output.to_dict(orient="records"):
        nature_override = str(record.get("natureza_cedente", "")).strip()
        segment_override = str(record.get("segmento", "")).strip()
        criterion_override = str(record.get("criterio_segmento", "")).strip()
        nature, nature_criterion = classify_natureza(record)
        segment, segment_criterion = classify_segmento(
            record, large_name_phrases=large_name_phrases
        )
        nature_values.append(nature_override or nature)
        nature_criteria.append("registry override" if nature_override else nature_criterion)
        segment_values.append(segment_override or segment)
        segment_criteria.append(
            criterion_override
            or ("registry override" if segment_override else segment_criterion)
        )
    output["natureza_cedente"] = nature_values
    output["criterio_natureza"] = nature_criteria
    output["segmento"] = segment_values
    output["criterio_segmento"] = segment_criteria
    return output


def select_dominant_cedents(links: pd.DataFrame) -> pd.DataFrame:
    """Mark one real dominant cedent per fund using PR and source order."""

    if links.empty:
        output = links.copy()
        output["cedente_dominante_flag"] = pd.Series(dtype=bool)
        output["dominante_todos_percentuais_ausentes_flag"] = pd.Series(dtype=bool)
        return output
    output = links.copy()
    output["cedente_dominante_flag"] = False
    output["dominante_todos_percentuais_ausentes_flag"] = False
    real = output.loc[output["cedente_real_flag"]].copy()
    if real.empty:
        return output
    group_key = ["competencia", "cnpj_fundo"]
    all_missing = real.groupby(group_key)["percentual_cedente"].transform(
        lambda values: values.isna().all()
    )
    real["_all_missing"] = all_missing
    real["_percent_missing"] = real["percentual_cedente"].isna()
    real["_type_priority"] = real["tp_registro_tabela_i"].map(_ascii_upper).map(
        {"FUNDO": 0, "CLASSE": 1}
    ).fillna(2)
    real = real.sort_values(
        group_key
        + [
            "_percent_missing",
            "percentual_cedente",
            "bloco_ordem",
            "ordem",
            "_type_priority",
            "cedente_doc_key",
        ],
        ascending=[True, True, True, False, True, True, True, True],
        kind="mergesort",
    )
    dominant_indices = real.groupby(group_key, sort=False).head(1).index
    output.loc[dominant_indices, "cedente_dominante_flag"] = True
    missing_map = (
        real.groupby(group_key, sort=False)["_all_missing"].first().to_dict()
    )
    output["dominante_todos_percentuais_ausentes_flag"] = [
        bool(missing_map.get((row.competencia, row.cnpj_fundo), False))
        for row in output.itertuples()
    ]
    return output


def _gap_reason(group: pd.DataFrame | None) -> str:
    if group is None or group.empty:
        return "sem_cedente_tabela_i"
    fake = group["cedente_documento_ficticio_flag"].astype(bool)
    irregular = group["cedente_documento_status"].eq("documento_irregular")
    if fake.all():
        return "somente_documento_ficticio"
    if irregular.all():
        return "somente_documento_irregular"
    if (fake | irregular).all():
        return "somente_documentos_invalidos"
    return "sem_cedente_real_identificado"


def _attach_dominant_to_top(top500: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    output = top500.copy()
    dominant_defaults: Mapping[str, Any] = {
        "cedente_dominante_documento": "",
        "cedente_dominante_doc_key": "",
        "cedente_dominante_razao_social": "",
        "cedente_dominante_natureza": "",
        "cedente_dominante_segmento": "",
        "cedente_dominante_criterio_segmento": "",
        "cedente_dominante_percentual_declarado": float("nan"),
        "cedente_dominante_percentuais_ausentes_flag": False,
    }
    if links.empty:
        output["cedente_real_declarado_flag"] = False
        output["motivo_sem_cedente"] = "sem_cedente_tabela_i"
        for column, value in dominant_defaults.items():
            output[column] = value
        return output
    real_by_fund = links.groupby("cnpj_fundo")["cedente_real_flag"].any().to_dict()
    groups = {cnpj: group for cnpj, group in links.groupby("cnpj_fundo", sort=False)}
    output["cedente_real_declarado_flag"] = (
        output["cnpj_fundo"].map(real_by_fund).fillna(False).astype(bool)
    )
    output["motivo_sem_cedente"] = [
        "" if bool(has_real) else _gap_reason(groups.get(cnpj))
        for cnpj, has_real in zip(output["cnpj_fundo"], output["cedente_real_declarado_flag"])
    ]
    dominant = links.loc[links["cedente_dominante_flag"]].copy()
    if dominant.empty:
        for column, value in dominant_defaults.items():
            output[column] = value
        return output
    dominant = dominant.rename(
        columns={
            "cedente_documento": "cedente_dominante_documento",
            "cedente_doc_key": "cedente_dominante_doc_key",
            "razao_social": "cedente_dominante_razao_social",
            "natureza_cedente": "cedente_dominante_natureza",
            "segmento": "cedente_dominante_segmento",
            "criterio_segmento": "cedente_dominante_criterio_segmento",
            "percentual_cedente": "cedente_dominante_percentual_declarado",
            "dominante_todos_percentuais_ausentes_flag": "cedente_dominante_percentuais_ausentes_flag",
        }
    )
    dominant_columns = [
        "cnpj_fundo",
        "cedente_dominante_documento",
        "cedente_dominante_doc_key",
        "cedente_dominante_razao_social",
        "cedente_dominante_natureza",
        "cedente_dominante_segmento",
        "cedente_dominante_criterio_segmento",
        "cedente_dominante_percentual_declarado",
        "cedente_dominante_percentuais_ausentes_flag",
    ]
    return output.merge(dominant[dominant_columns], on="cnpj_fundo", how="left", validate="one_to_one")


def build_funds_without_cedent(top500: pd.DataFrame) -> pd.DataFrame:
    if top500.empty:
        return top500.copy()
    return top500.loc[~top500["cedente_real_declarado_flag"]].copy().reset_index(drop=True)


def build_exclusions(links: pd.DataFrame) -> pd.DataFrame:
    if links.empty:
        return links.copy()
    exclusions = links.loc[~links["cedente_real_flag"]].copy()
    exclusions["motivo_exclusao"] = "documento_irregular"
    exclusions.loc[
        exclusions["cedente_documento_ficticio_flag"], "motivo_exclusao"
    ] = "documento_ficticio_0_9"
    return exclusions.reset_index(drop=True)


def build_coverage_summary(
    universe: pd.DataFrame,
    top500: pd.DataFrame,
    links: pd.DataFrame,
    *,
    competencia: str,
) -> pd.DataFrame:
    industry_pl = float(universe["pl_fundo_reais"].sum(min_count=1)) if not universe.empty else 0.0
    top_pl = float(top500["pl_fundo_reais"].sum(min_count=1)) if not top500.empty else 0.0
    identified = top500.loc[top500.get("cedente_real_declarado_flag", False)].copy()
    identified_pl = float(identified["pl_fundo_reais"].sum(min_count=1)) if not identified.empty else 0.0
    rank_last_pl = (
        float(top500.sort_values("rank_pl").iloc[-1]["pl_fundo_reais"])
        if not top500.empty
        else float("nan")
    )
    fake_links = (
        int(links["cedente_documento_ficticio_flag"].sum()) if not links.empty else 0
    )
    zfill_links = int(links["cedente_cnpj_zfill_flag"].sum()) if not links.empty else 0
    zfill_13_links = int(links["cedente_cnpj_zfill_13_flag"].sum()) if not links.empty else 0
    real_documents = (
        int(links.loc[links["cedente_real_flag"], "cedente_doc_key"].nunique())
        if not links.empty
        else 0
    )
    return pd.DataFrame(
        [
            {
                "competencia": competencia,
                "data": f"{competencia[:4]}-{competencia[4:6]}-01",
                "fundos_industria": int(len(universe)),
                "pl_industria_reais": industry_pl,
                "fundos_top500": int(len(top500)),
                "pl_top500_reais": top_pl,
                "pl_top500_sobre_industria_pct": top_pl / industry_pl if industry_pl else float("nan"),
                "pl_ultimo_fundo_top_reais": rank_last_pl,
                "fundos_com_cedente_real": int(len(identified)),
                "fundos_com_cedente_real_pct": len(identified) / len(top500) if len(top500) else float("nan"),
                "pl_fundos_com_cedente_real_reais": identified_pl,
                "pl_identificado_sobre_top500_pct": identified_pl / top_pl if top_pl else float("nan"),
                "fundos_sem_cedente_real": int(len(top500) - len(identified)),
                "pl_sem_cedente_real_reais": top_pl - identified_pl,
                "vinculos_documento_ficticio": fake_links,
                "vinculos_cnpj_zfill": zfill_links,
                "vinculos_cnpj_zfill_13": zfill_13_links,
                "cedentes_reais_distintos": real_documents,
            }
        ]
    )


def build_segment_pl(top500: pd.DataFrame, *, competencia: str) -> pd.DataFrame:
    """Assign each fund's complete PL to its dominant cedent segment."""

    if top500.empty:
        return pd.DataFrame()
    frame = top500.copy()
    segment_series = (
        frame["cedente_dominante_segmento"]
        if "cedente_dominante_segmento" in frame.columns
        else pd.Series("", index=frame.index, dtype="object")
    )
    frame["segmento_atribuido"] = segment_series.fillna("")
    frame.loc[~frame["cedente_real_declarado_flag"], "segmento_atribuido"] = "Sem cedente"
    frame.loc[
        frame["cedente_real_declarado_flag"] & frame["segmento_atribuido"].eq(""),
        "segmento_atribuido",
    ] = "Não classificado"
    total_pl = float(frame["pl_fundo_reais"].sum(min_count=1))
    identified_pl = float(
        frame.loc[frame["segmento_atribuido"].ne("Sem cedente"), "pl_fundo_reais"].sum(min_count=1)
    )
    rows: list[dict[str, Any]] = []
    for segment, group in frame.groupby("segmento_atribuido", sort=False):
        pl = float(group["pl_fundo_reais"].sum(min_count=1))
        documents = (
            group.get("cedente_dominante_doc_key", pd.Series(dtype=str))
            .fillna("")
            .astype(str)
        )
        rows.append(
            {
                "competencia": competencia,
                "data": f"{competencia[:4]}-{competencia[4:6]}-01",
                "segmento": segment,
                "pl_dominante_reais": pl,
                "pl_sobre_top500_pct": pl / total_pl if total_pl else float("nan"),
                "pl_sobre_identificado_pct": (
                    pl / identified_pl
                    if identified_pl and segment != "Sem cedente"
                    else float("nan")
                ),
                "fundos_dominante": int(len(group)),
                "cedentes_dominantes_distintos": int(documents.loc[documents.ne("")].nunique()),
                "pl_top500_denominador_reais": total_pl,
                "pl_identificado_denominador_reais": identified_pl,
            }
        )
    output = pd.DataFrame(rows)
    output["_order"] = output["segmento"].map(_SEGMENT_ORDER).fillna(99)
    return output.sort_values(["_order", "segmento"], kind="mergesort").drop(
        columns="_order"
    ).reset_index(drop=True)


def build_cedente_top500(
    competencia: str,
    tab_iv_source: TableSource,
    tab_i_source: TableSource,
    *,
    cadastro: RegistrySource = None,
    registry_overrides: RegistrySource = None,
    cutoff_rank: int = DEFAULT_CUTOFF_RANK,
    large_name_phrases: Sequence[str] = _DEFAULT_LARGE_NAME_PHRASES,
) -> CedenteTop500Result:
    """Build all Top-500 analytical frames for one competence."""

    tab_iv = load_cvm_table(tab_iv_source, competencia=competencia, table="tab_IV")
    tab_i = load_cvm_table(tab_i_source, competencia=competencia, table="tab_I")
    source_repairs = pd.DataFrame.from_records(
        [
            {"competencia": competencia, "tabela": table, **repair}
            for table, frame in (("Tabela IV", tab_iv), ("Tabela I", tab_i))
            for repair in frame.attrs.get("source_repairs", [])
        ]
    )
    universe, top = rank_top500(tab_iv, competencia=competencia, cutoff_rank=cutoff_rank)
    links = melt_table_i(tab_i, top, competencia=competencia)
    links = enrich_and_classify_links(
        links,
        cadastro=cadastro,
        registry_overrides=registry_overrides,
        large_name_phrases=large_name_phrases,
    )
    links = select_dominant_cedents(links)
    top = _attach_dominant_to_top(top, links)
    gaps = build_funds_without_cedent(top)
    exclusions = build_exclusions(links)
    coverage = build_coverage_summary(universe, top, links, competencia=competencia)
    segment_pl = build_segment_pl(top, competencia=competencia)
    return CedenteTop500Result(
        competencia=competencia,
        top500=top.reset_index(drop=True),
        vinculos=links.reset_index(drop=True),
        fundos_sem_cedente=gaps,
        exclusoes=exclusions,
        cobertura=coverage,
        pl_por_segmento=segment_pl,
        reparos_fonte=source_repairs,
    )


def build_multi_competence_top500(
    sources: Mapping[str, Mapping[str, TableSource] | tuple[TableSource, TableSource]],
    *,
    cadastro: RegistrySource = None,
    registry_overrides: RegistrySource = None,
    cutoff_rank: int = DEFAULT_CUTOFF_RANK,
    large_name_phrases: Sequence[str] = _DEFAULT_LARGE_NAME_PHRASES,
) -> dict[str, pd.DataFrame]:
    """Build and concatenate deterministic outputs for multiple competences.

    Each mapping value may be ``{"tab_iv": source, "tab_i": source}`` or a
    ``(tab_iv, tab_i)`` tuple.
    """

    results: list[CedenteTop500Result] = []
    for competencia in sorted(sources):
        entry = sources[competencia]
        if isinstance(entry, Mapping):
            try:
                tab_iv_source = entry["tab_iv"]
                tab_i_source = entry["tab_i"]
            except KeyError as exc:
                raise ValueError(f"fontes de {competencia} exigem tab_iv e tab_i") from exc
        else:
            if len(entry) != 2:
                raise ValueError(f"fontes de {competencia} exigem par (tab_iv, tab_i)")
            tab_iv_source, tab_i_source = entry
        results.append(
            build_cedente_top500(
                competencia,
                tab_iv_source,
                tab_i_source,
                cadastro=cadastro,
                registry_overrides=registry_overrides,
                cutoff_rank=cutoff_rank,
                large_name_phrases=large_name_phrases,
            )
        )
    frames: dict[str, pd.DataFrame] = {}
    for name in (
        "top500",
        "vinculos",
        "fundos_sem_cedente",
        "exclusoes",
        "cobertura",
        "pl_por_segmento",
        "reparos_fonte",
    ):
        parts = [getattr(result, name) for result in results if not getattr(result, name).empty]
        frames[name] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return frames


__all__ = [
    "CedenteTop500Result",
    "DEFAULT_COMPETENCES",
    "DEFAULT_CUTOFF_RANK",
    "SCHEMA_VERSION",
    "build_cedente_top500",
    "build_coverage_summary",
    "build_exclusions",
    "build_funds_without_cedent",
    "build_multi_competence_top500",
    "build_segment_pl",
    "classify_natureza",
    "classify_segmento",
    "enrich_and_classify_links",
    "load_cvm_table",
    "melt_table_i",
    "normalize_document",
    "normalize_tab_iv",
    "rank_top500",
    "select_dominant_cedents",
]
