from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from scripts.extract_receita_cnpj_registry import main
from services.receita_cnpj_bulk import (
    SOURCE_LABEL,
    discover_receita_zip_files,
    extract_receita_cnpj_registry,
    normalize_target_cnpj,
)


TARGET_CNPJ = "01027058000191"


def _csv_bytes(rows: list[list[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("latin-1")


def _write_zip(path: Path, rows: list[list[object]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{path.stem}.CSV", _csv_bytes(rows))


def _company_row(
    root: str,
    name: str,
    *,
    capital: str = "100000000,50",
    porte: str = "05",
) -> list[object]:
    return [root, name, "2046", "49", capital, porte, ""]


def _establishment_row(
    root: str,
    order: str,
    dv: str,
    *,
    fantasy: str,
    cnae: str,
    uf: str,
    municipality: str,
) -> list[object]:
    row: list[object] = [""] * 21
    row[0] = root
    row[1] = order
    row[2] = dv
    row[3] = "1"
    row[4] = fantasy
    row[5] = "02"
    row[6] = "20200101"
    row[11] = cnae
    row[19] = uf
    row[20] = municipality
    return row


def _build_snapshot(directory: Path) -> None:
    directory.mkdir()
    noise_company = _company_row("99999999", "EMPRESA FORA DO RECORTE")
    noise_establishment = _establishment_row(
        "99999999",
        "0001",
        "99",
        fantasy="FORA",
        cnae="0111301",
        uf="GO",
        municipality="9373",
    )
    for index in range(10):
        company_rows = [noise_company]
        establishment_rows = [noise_establishment]
        if index == 7:
            company_rows.append(_company_row("01027058", "CIELO S.A."))
        if index == 8:
            establishment_rows.append(
                _establishment_row(
                    "01027058",
                    "0001",
                    "91",
                    fantasy="CIELO",
                    cnae="6613400",
                    uf="SP",
                    municipality="7107",
                )
            )
        _write_zip(directory / f"Empresas{index}.zip", company_rows)
        _write_zip(directory / f"Estabelecimentos{index}.zip", establishment_rows)
    _write_zip(directory / "Simples.zip", [["99999999", "S", "", "", "S", ""], ["01027058", "N", "", "", "N", ""]])
    _write_zip(
        directory / "Cnaes.zip",
        [["0111301", "Cultivo de arroz"], ["6613400", "Administração de cartões de crédito"]],
    )
    _write_zip(
        directory / "Municipios.zip",
        [["9373", "GOIÂNIA"], ["7107", "SÃO PAULO"]],
    )


def test_normalize_target_cnpj_recovers_leading_zero() -> None:
    assert normalize_target_cnpj("1.027.058/0001-91") == TARGET_CNPJ
    assert normalize_target_cnpj("1027058000191") == TARGET_CNPJ
    assert normalize_target_cnpj("01.027.058/0001-91") == TARGET_CNPJ
    assert normalize_target_cnpj("416968000101") == "00416968000101"
    with pytest.raises(ValueError, match="12, 13 ou 14"):
        normalize_target_cnpj("123")


def test_discovery_requires_all_ten_heavy_parts(tmp_path: Path) -> None:
    _write_zip(tmp_path / "Empresas0.zip", [["1"]])
    _write_zip(tmp_path / "Estabelecimentos0.zip", [["1"]])
    _write_zip(tmp_path / "Simples.zip", [["1"]])
    _write_zip(tmp_path / "Cnaes.zip", [["1"]])
    _write_zip(tmp_path / "Municipios.zip", [["1"]])
    with pytest.raises(FileNotFoundError, match="Empresas incompletos"):
        discover_receita_zip_files(tmp_path)
    partial = discover_receita_zip_files(tmp_path, strict_parts=False)
    assert [path.name for path in partial["empresas"]] == ["Empresas0.zip"]


def test_selective_extraction_joins_official_blocks_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "receita"
    _build_snapshot(source)

    result = extract_receita_cnpj_registry(
        source,
        ["1027058000191", "12.345.678/0001-90"],
        snapshot_date="2026-01-17",
        chunksize=1,
    )

    assert list(result.registry["cnpj"]) == [TARGET_CNPJ, "12345678000190"]
    found = result.registry.loc[result.registry["cnpj"] == TARGET_CNPJ].iloc[0]
    assert bool(found["cadastro_encontrado"]) is True
    assert found["cnpj_formatado"] == "01.027.058/0001-91"
    assert found["razao_social"] == "CIELO S.A."
    assert found["natureza_juridica_codigo"] == "2046"
    assert found["capital_social_reais"] == pytest.approx(100_000_000.50)
    assert found["porte_receita"] == "Demais"
    assert found["matriz_filial"] == "Matriz"
    assert found["situacao_cadastral"] == "Ativa"
    assert found["cnae_codigo"] == "6613400"
    assert found["cnae_principal"] == "Administração de cartões de crédito"
    assert found["secao_cnae"] == "K"
    assert found["uf"] == "SP"
    assert found["municipio"] == "SÃO PAULO"
    assert found["simples"] == "Não"
    assert found["mei"] == "Não"
    assert found["fonte"] == SOURCE_LABEL
    assert found["snapshot_date"] == "2026-01-17"
    assert found["source_empresas_zip"] == "Empresas7.zip"
    assert found["source_estabelecimentos_zip"] == "Estabelecimentos8.zip"
    expected_hash = hashlib.sha256((source / "Empresas7.zip").read_bytes()).hexdigest()
    assert found["source_empresas_sha256"] == expected_hash

    missing = result.registry.loc[result.registry["cnpj"] == "12345678000190"].iloc[0]
    assert bool(missing["cadastro_encontrado"]) is False
    assert missing["razao_social"] == ""
    assert result.manifest["target_cnpjs"] == 2
    assert result.manifest["cadastros_encontrados"] == 1
    assert result.manifest["cadastros_nao_encontrados"] == 1
    assert len(result.manifest["zip_hashes_sha256"]) == 23

    # O leitor nao extrai os CSVs internos para o diretorio do snapshot.
    assert sorted(path.suffix for path in source.iterdir()) == [".zip"] * 23


def test_cli_writes_utf8_registry_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "receita"
    _build_snapshot(source)
    targets = tmp_path / "targets.csv"
    pd.DataFrame({"cedente_cnpj": ["1027058000191"]}).to_csv(targets, index=False)
    output = tmp_path / "out" / "cadastro.csv.gz"
    manifest = tmp_path / "out" / "manifest.json"

    exit_code = main(
        [
            "--source-dir",
            str(source),
            "--targets-file",
            str(targets),
            "--cnpj-column",
            "cedente_cnpj",
            "--snapshot-date",
            "2026-01-17",
            "--output-csv",
            str(output),
            "--manifest-json",
            str(manifest),
            "--chunksize",
            "1",
        ]
    )

    assert exit_code == 0
    exported = pd.read_csv(output, dtype={"cnpj": str})
    assert exported.loc[0, "cnpj"] == TARGET_CNPJ
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source"] == SOURCE_LABEL
    assert payload["cadastros_encontrados"] == 1
