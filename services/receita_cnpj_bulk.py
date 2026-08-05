"""Leitura seletiva dos Dados Abertos do CNPJ da Receita Federal.

O leitor trabalha diretamente sobre os ZIPs oficiais, sem extrair o cadastro
completo para disco e sem realizar chamadas de rede.  Somente as raizes e os
estabelecimentos correspondentes aos CNPJs solicitados permanecem em memoria.

Layout esperado no diretorio fonte:

* ``Empresas0.zip`` a ``Empresas9.zip``;
* ``Estabelecimentos0.zip`` a ``Estabelecimentos9.zip``;
* ``Simples.zip``;
* ``Cnaes.zip``;
* ``Municipios.zip``.

Os CSVs da Receita nao possuem cabecalho, usam ``latin-1`` e delimitador
``;``.  O contrato abaixo segue o leiaute nacional publicado para esses cinco
blocos.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import pandas as pd


SCHEMA_VERSION = "receita-cnpj-bulk-registry/v1"
SOURCE_LABEL = "Receita Federal · Dados Abertos do CNPJ"

_COMPANY_USECOLS = [0, 1, 2, 4, 5]
_ESTABLISHMENT_USECOLS = [0, 1, 2, 3, 4, 5, 6, 11, 19, 20]
_SIMPLES_USECOLS = [0, 1, 4]
_LOOKUP_USECOLS = [0, 1]

_PORTE_LABELS = {
    "00": "Não informado",
    "01": "Microempresa",
    "03": "Empresa de pequeno porte",
    "05": "Demais",
}

_MATRIZ_FILIAL_LABELS = {"1": "Matriz", "2": "Filial"}

_SITUACAO_LABELS = {
    "01": "Nula",
    "02": "Ativa",
    "03": "Suspensa",
    "04": "Inapta",
    "08": "Baixada",
}

_SECAO_CNAE_BY_DIVISION = (
    (1, 3, "A"),
    (5, 9, "B"),
    (10, 33, "C"),
    (35, 35, "D"),
    (36, 39, "E"),
    (41, 43, "F"),
    (45, 47, "G"),
    (49, 53, "H"),
    (55, 56, "I"),
    (58, 63, "J"),
    (64, 66, "K"),
    (68, 68, "L"),
    (69, 75, "M"),
    (77, 82, "N"),
    (84, 84, "O"),
    (85, 85, "P"),
    (86, 88, "Q"),
    (90, 93, "R"),
    (94, 96, "S"),
    (97, 97, "T"),
    (99, 99, "U"),
)


@dataclass(frozen=True)
class ReceitaCnpjBulkResult:
    """Cadastro seletivo e manifesto de proveniencia."""

    registry: pd.DataFrame
    manifest: dict[str, Any]


@dataclass(frozen=True)
class _SourceFiles:
    empresas: tuple[Path, ...]
    estabelecimentos: tuple[Path, ...]
    simples: Path
    cnaes: Path
    municipios: Path

    @property
    def all(self) -> tuple[Path, ...]:
        return (
            *self.empresas,
            *self.estabelecimentos,
            self.simples,
            self.cnaes,
            self.municipios,
        )


def normalize_target_cnpj(value: object) -> str:
    """Normalize um CNPJ-alvo, recuperando um ou dois zeros iniciais perdidos."""

    if value is None or pd.isna(value):
        raise ValueError("CNPJ-alvo ausente")
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if len(digits) in {12, 13}:
        digits = digits.zfill(14)
    if len(digits) != 14:
        raise ValueError(f"CNPJ-alvo deve ter 12, 13 ou 14 digitos: {value!r}")
    return digits


def format_cnpj(cnpj: str) -> str:
    digits = normalize_target_cnpj(cnpj)
    return (
        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:]}"
    )


def _sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _indexed_parts(paths: Iterable[Path], stem: str) -> dict[int, Path]:
    pattern = re.compile(rf"^{re.escape(stem)}(\d+)\.zip$", re.IGNORECASE)
    found: dict[int, Path] = {}
    for path in paths:
        match = pattern.match(path.name)
        if match:
            index = int(match.group(1))
            if index in found:
                raise ValueError(f"Parte duplicada para {stem}{index}: {path}")
            found[index] = path
    return found


def _single_zip(paths: Iterable[Path], stem: str) -> Path:
    matches = [path for path in paths if path.name.casefold() == f"{stem}.zip".casefold()]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Esperado exatamente um {stem}.zip; encontrados {len(matches)}"
        )
    return matches[0]


def discover_receita_zip_files(
    source_dir: str | Path,
    *,
    strict_parts: bool = True,
) -> Mapping[str, tuple[Path, ...] | Path]:
    """Localize os ZIPs do snapshot e valide os dez blocos pesados."""

    directory = Path(source_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Diretorio da Receita inexistente: {directory}")
    paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".zip"),
        key=lambda path: path.name.casefold(),
    )
    empresas = _indexed_parts(paths, "Empresas")
    estabelecimentos = _indexed_parts(paths, "Estabelecimentos")
    expected = set(range(10))
    if strict_parts:
        if set(empresas) != expected:
            missing = sorted(expected - set(empresas))
            extra = sorted(set(empresas) - expected)
            raise FileNotFoundError(
                f"Blocos Empresas incompletos; faltantes={missing}, extras={extra}"
            )
        if set(estabelecimentos) != expected:
            missing = sorted(expected - set(estabelecimentos))
            extra = sorted(set(estabelecimentos) - expected)
            raise FileNotFoundError(
                f"Blocos Estabelecimentos incompletos; faltantes={missing}, extras={extra}"
            )
    elif not empresas or not estabelecimentos:
        raise FileNotFoundError("Pasta deve conter ao menos um bloco Empresas e Estabelecimentos")

    files = _SourceFiles(
        empresas=tuple(empresas[index] for index in sorted(empresas)),
        estabelecimentos=tuple(estabelecimentos[index] for index in sorted(estabelecimentos)),
        simples=_single_zip(paths, "Simples"),
        cnaes=_single_zip(paths, "Cnaes"),
        municipios=_single_zip(paths, "Municipios"),
    )
    return {
        "empresas": files.empresas,
        "estabelecimentos": files.estabelecimentos,
        "simples": files.simples,
        "cnaes": files.cnaes,
        "municipios": files.municipios,
    }


def _source_files_from_mapping(
    mapping: Mapping[str, tuple[Path, ...] | Path],
) -> _SourceFiles:
    empresas = mapping["empresas"]
    estabelecimentos = mapping["estabelecimentos"]
    if not isinstance(empresas, tuple) or not isinstance(estabelecimentos, tuple):
        raise TypeError("Grupos Empresas/Estabelecimentos invalidos")
    simples = mapping["simples"]
    cnaes = mapping["cnaes"]
    municipios = mapping["municipios"]
    if not all(isinstance(path, Path) for path in (simples, cnaes, municipios)):
        raise TypeError("ZIPs auxiliares invalidos")
    return _SourceFiles(
        empresas=empresas,
        estabelecimentos=estabelecimentos,
        simples=simples,
        cnaes=cnaes,
        municipios=municipios,
    )


def _zip_members(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        members = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX/")
            and not Path(info.filename).name.startswith(".")
        ]
    if not members:
        raise ValueError(f"ZIP sem CSV legivel: {path}")
    return sorted(members)


def _iter_zip_chunks(
    path: Path,
    *,
    usecols: Sequence[int],
    chunksize: int,
) -> Iterator[pd.DataFrame]:
    for member in _zip_members(path):
        with zipfile.ZipFile(path) as archive, archive.open(member) as handle:
            yield from pd.read_csv(
                handle,
                sep=";",
                encoding="latin-1",
                header=None,
                usecols=list(usecols),
                dtype=str,
                chunksize=chunksize,
                keep_default_na=False,
                na_filter=False,
                on_bad_lines="error",
            )


def _zfill(series: pd.Series, width: int) -> pd.Series:
    return series.astype(str).str.replace(r"\D", "", regex=True).str.zfill(width)


def _first_rows_by_key(
    paths: Sequence[Path],
    *,
    usecols: Sequence[int],
    chunksize: int,
    key_builder: Any,
    wanted: set[str],
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    remaining = set(wanted)
    for path in paths:
        if not remaining:
            break
        for chunk in _iter_zip_chunks(path, usecols=usecols, chunksize=chunksize):
            keys = key_builder(chunk)
            mask = keys.isin(remaining)
            if not mask.any():
                continue
            selected = chunk.loc[mask].copy()
            selected["_key"] = keys.loc[mask]
            for row in selected.to_dict(orient="records"):
                key = str(row.pop("_key"))
                if key not in found:
                    row["_source_zip"] = path.name
                    found[key] = row
                    remaining.discard(key)
    return found


def _read_lookup(
    path: Path,
    *,
    chunksize: int,
    key_width: int,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for chunk in _iter_zip_chunks(path, usecols=_LOOKUP_USECOLS, chunksize=chunksize):
        keys = _zfill(chunk[0], key_width)
        for key, description in zip(keys, chunk[1].astype(str), strict=False):
            values.setdefault(str(key), description.strip())
    return values


def _decimal_ptbr(value: object) -> float | None:
    text = str(value or "").strip().replace(".", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _yes_no_label(value: object) -> str:
    code = str(value or "").strip().upper()
    return {"S": "Sim", "N": "Não"}.get(code, "")


def _cnae_section(cnae: str) -> str:
    digits = re.sub(r"\D", "", str(cnae))
    if len(digits) < 2:
        return ""
    division = int(digits[:2])
    for start, end, section in _SECAO_CNAE_BY_DIVISION:
        if start <= division <= end:
            return section
    return ""


def _validate_snapshot_date(snapshot_date: str | date) -> str:
    if isinstance(snapshot_date, date):
        return snapshot_date.isoformat()
    try:
        return date.fromisoformat(str(snapshot_date)).isoformat()
    except ValueError as exc:
        raise ValueError("snapshot_date deve estar no formato YYYY-MM-DD") from exc


def extract_receita_cnpj_registry(
    source_dir: str | Path,
    target_cnpjs: Iterable[object],
    *,
    snapshot_date: str | date,
    chunksize: int = 250_000,
    strict_parts: bool = True,
) -> ReceitaCnpjBulkResult:
    """Extraia somente os CNPJs solicitados do snapshot local da Receita.

    A funcao devolve todos os alvos, inclusive os nao localizados. Os hashes
    SHA-256 dos ZIPs ficam no manifesto e, para cada registro encontrado, nas
    colunas de proveniencia de cada bloco usado.
    """

    if chunksize <= 0:
        raise ValueError("chunksize deve ser positivo")
    normalized_targets = sorted({normalize_target_cnpj(value) for value in target_cnpjs})
    if not normalized_targets:
        raise ValueError("Informe ao menos um CNPJ-alvo")
    snapshot = _validate_snapshot_date(snapshot_date)
    files = _source_files_from_mapping(
        discover_receita_zip_files(source_dir, strict_parts=strict_parts)
    )
    hashes = {path.name: _sha256_file(path) for path in files.all}

    target_set = set(normalized_targets)
    target_roots = {cnpj[:8] for cnpj in normalized_targets}

    company_rows = _first_rows_by_key(
        files.empresas,
        usecols=_COMPANY_USECOLS,
        chunksize=chunksize,
        key_builder=lambda chunk: _zfill(chunk[0], 8),
        wanted=target_roots,
    )
    establishment_rows = _first_rows_by_key(
        files.estabelecimentos,
        usecols=_ESTABLISHMENT_USECOLS,
        chunksize=chunksize,
        key_builder=lambda chunk: (
            _zfill(chunk[0], 8) + _zfill(chunk[1], 4) + _zfill(chunk[2], 2)
        ),
        wanted=target_set,
    )
    simples_rows = _first_rows_by_key(
        (files.simples,),
        usecols=_SIMPLES_USECOLS,
        chunksize=chunksize,
        key_builder=lambda chunk: _zfill(chunk[0], 8),
        wanted=target_roots,
    )

    cnae_lookup = _read_lookup(files.cnaes, chunksize=chunksize, key_width=7)
    municipio_lookup = _read_lookup(files.municipios, chunksize=chunksize, key_width=4)

    records: list[dict[str, Any]] = []
    for cnpj in normalized_targets:
        root = cnpj[:8]
        company = company_rows.get(root, {})
        establishment = establishment_rows.get(cnpj, {})
        simples = simples_rows.get(root, {})
        company_zip = str(company.get("_source_zip", ""))
        establishment_zip = str(establishment.get("_source_zip", ""))
        simples_zip = str(simples.get("_source_zip", ""))
        cnae = str(establishment.get(11, "")).strip().zfill(7) if establishment else ""
        municipio_code = (
            str(establishment.get(20, "")).strip().zfill(4) if establishment else ""
        )
        porte_code = str(company.get(5, "")).strip().zfill(2) if company else ""
        matriz_code = str(establishment.get(3, "")).strip() if establishment else ""
        situacao_code = (
            str(establishment.get(5, "")).strip().zfill(2) if establishment else ""
        )
        found = bool(establishment)
        records.append(
            {
                "cnpj": cnpj,
                "cnpj_formatado": format_cnpj(cnpj),
                "cnpj_basico": root,
                "cadastro_encontrado": found,
                "razao_social": str(company.get(1, "")).strip(),
                "natureza_juridica_codigo": str(company.get(2, "")).strip().zfill(4)
                if company
                else "",
                "capital_social_reais": _decimal_ptbr(company.get(4, "")),
                "porte_empresa_codigo": porte_code,
                "porte_receita": _PORTE_LABELS.get(porte_code, ""),
                "identificador_matriz_filial_codigo": matriz_code,
                "matriz_filial": _MATRIZ_FILIAL_LABELS.get(matriz_code, ""),
                "nome_fantasia": str(establishment.get(4, "")).strip(),
                "situacao_cadastral_codigo": situacao_code,
                "situacao_cadastral": _SITUACAO_LABELS.get(situacao_code, ""),
                "data_situacao_cadastral": str(establishment.get(6, "")).strip(),
                "cnae_codigo": cnae,
                "cnae_principal": cnae_lookup.get(cnae, ""),
                "secao_cnae": _cnae_section(cnae),
                "uf": str(establishment.get(19, "")).strip(),
                "municipio_codigo": municipio_code,
                "municipio": municipio_lookup.get(municipio_code, ""),
                "simples_codigo": str(simples.get(1, "")).strip().upper(),
                "simples": _yes_no_label(simples.get(1, "")),
                "mei_codigo": str(simples.get(4, "")).strip().upper(),
                "mei": _yes_no_label(simples.get(4, "")),
                "fonte": SOURCE_LABEL,
                "snapshot_date": snapshot,
                "source_empresas_zip": company_zip,
                "source_empresas_sha256": hashes.get(company_zip, ""),
                "source_estabelecimentos_zip": establishment_zip,
                "source_estabelecimentos_sha256": hashes.get(establishment_zip, ""),
                "source_simples_zip": simples_zip,
                "source_simples_sha256": hashes.get(simples_zip, ""),
                "source_cnaes_zip": files.cnaes.name,
                "source_cnaes_sha256": hashes[files.cnaes.name],
                "source_municipios_zip": files.municipios.name,
                "source_municipios_sha256": hashes[files.municipios.name],
            }
        )

    registry = pd.DataFrame.from_records(records)
    found_count = int(registry["cadastro_encontrado"].sum())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_LABEL,
        "snapshot_date": snapshot,
        "source_dir_name": Path(source_dir).name,
        "target_cnpjs": len(normalized_targets),
        "cadastros_encontrados": found_count,
        "cadastros_nao_encontrados": len(normalized_targets) - found_count,
        "chunksize": chunksize,
        "strict_parts": strict_parts,
        "zip_hashes_sha256": dict(sorted(hashes.items())),
        "zip_groups": {
            "empresas": [path.name for path in files.empresas],
            "estabelecimentos": [path.name for path in files.estabelecimentos],
            "simples": files.simples.name,
            "cnaes": files.cnaes.name,
            "municipios": files.municipios.name,
        },
    }
    return ReceitaCnpjBulkResult(registry=registry, manifest=manifest)


def write_receita_cnpj_registry(
    result: ReceitaCnpjBulkResult,
    *,
    output_csv: str | Path,
    manifest_json: str | Path,
) -> None:
    """Grave cadastro UTF-8 e manifesto JSON, criando apenas os pais necessarios."""

    output_path = Path(output_csv)
    manifest_path = Path(manifest_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    result.registry.to_csv(output_path, index=False, encoding="utf-8-sig")
    manifest_path.write_text(
        json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
