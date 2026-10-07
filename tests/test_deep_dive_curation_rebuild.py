from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import build_deep_dive_package as builder
from services.portfolio_store import PortfolioFund, PortfolioRecord, portfolio_basket_signature


COMPARISON_IDS = (
    "comparison_eligibility",
    "comparison_protection",
    "comparison_mechanics",
    "comparison_emissions",
    "comparison_payments",
    "comparison_costs",
    "comparison_monitoring",
)


def _portfolio() -> PortfolioRecord:
    return PortfolioRecord(
        id="saved-portfolio",
        name="Carteira de teste",
        funds=(PortfolioFund("11111111000111", "Nome novo A"), PortfolioFund("22222222000122", "Nome novo B")),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-10-07T00:00:00Z",
    )


def _reviewed_package(root: Path, portfolio: PortfolioRecord) -> tuple[Path, dict]:
    package = root / builder.portfolio_deep_dive_id(portfolio)
    (package / "tables").mkdir(parents=True)
    (package / "evidence").mkdir()
    (package / "exports").mkdir()
    reviewed_specs = []
    for table_id in COMPARISON_IDS:
        source_file = f"tables/{table_id}.csv"
        pd.DataFrame({"Critério": ["Regra"], "A revisado": ["15%"], "B revisado": ["20%"]}).to_csv(package / source_file, index=False)
        reviewed_specs.append({"id": table_id, "title": table_id, "source_file": source_file, "first_column": "Critério", "kind": "document_comparison"})
    pd.DataFrame({"Tabela": [COMPARISON_IDS[0]], "Critério": ["Regra"], "CNPJ": ["11111111000111"], "Valor": ["15%"], "Fonte": ["Regulamento, p. 7"], "Nota": ["Base contratual"]}).to_csv(package / "evidence/comparison_sources.csv", index=False)
    pd.DataFrame({"Tema": ["Proteção"], "Conclusão": ["Subordinação revisada"]}).to_csv(package / "tables/key_findings.csv", index=False)
    pptx = b"presentation-from-reviewed-matrices"
    (package / "exports/documentary_comparison.pptx").write_bytes(pptx)
    manifest = {
        "deep_dive_id": package.name,
        "portfolio_id": portfolio.id,
        "portfolio_signature": portfolio_basket_signature(portfolio.funds),
        "generated_at": "2026-09-01T11:22:33-03:00",
        "source": "Documentos revisados em setembro",
        "funds": [
            {"cnpj": "22.222.222/0001-22", "name": "Fundo B revisado", "short_name": "B revisado"},
            {"cnpj": "11.111.111/0001-11", "name": "Fundo A revisado", "short_name": "A revisado"},
        ],
        "comparison_columns": {"A revisado": "11111111000111", "B revisado": "22222222000122"},
        "documentary_export": {"source_file": "exports/documentary_comparison.pptx", "sha256": hashlib.sha256(pptx).hexdigest()},
        "audit": {"warnings": ["Divergência contratual preservada"], "documentary_note": "Leitura dirigida"},
        "tables": [
            {"id": "key_findings", "title": "Conclusões revisadas", "source_file": "tables/key_findings.csv", "first_column": "Tema", "kind": "source_table"},
            *reviewed_specs,
            {"id": "comparison_evidence", "title": "Fontes revisadas", "source_file": "evidence/comparison_sources.csv", "first_column": "Tabela", "kind": "source_table"},
        ],
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return package, manifest


def _mock_analytical_inputs(monkeypatch: pytest.MonkeyPatch, root: Path, portfolio: PortfolioRecord) -> None:
    coverage = pd.DataFrame({"cnpj": [fund.cnpj for fund in portfolio.funds], "fundo": [fund.display_name for fund in portfolio.funds]})
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "build_portfolio_coverage", lambda _: coverage)
    monkeypatch.setattr(builder, "enrich_performance_from_local_ime_cache", lambda *_: pd.DataFrame({"Métrica": ["PL"], "Valor": [123]}))
    monkeypatch.setattr(builder, "build_threshold_versions_for_coverage", lambda _: pd.DataFrame())
    monkeypatch.setattr(builder, "build_emissions_for_coverage", lambda _: pd.DataFrame())
    monkeypatch.setattr(builder, "build_structural_costs_for_coverage", lambda _: pd.DataFrame({"Item": ["Gestão"], "Percentual a.a.": ["0,2%"]}))
    monkeypatch.setattr(builder, "build_emission_rows", lambda *_: [])
    monkeypatch.setattr(builder, "build_comparison_main", lambda *_: pd.DataFrame({"Nome": ["PL (R$ mm)"], "Nome novo A": [123], "Nome novo B": [456]}))
    monkeypatch.setattr(builder, "build_emission_schedule_table", lambda _: pd.DataFrame({"Fonte": ["Nova base analítica"]}))
    monkeypatch.setattr(builder, "build_latest_thresholds_table", lambda *_: pd.DataFrame({"Fonte": ["Nova base analítica"]}))


def test_rebuild_keeps_reviewed_matrices_reading_date_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    portfolio = _portfolio()
    output_root = tmp_path / "deep_dives"
    package, before = _reviewed_package(output_root, portfolio)
    reviewed_files = [package / spec["source_file"] for spec in before["tables"]]
    reviewed_files.append(package / before["documentary_export"]["source_file"])
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in reviewed_files}
    _mock_analytical_inputs(monkeypatch, tmp_path, portfolio)

    builder.build_portfolio_package(SimpleNamespace(output_root=output_root, deep_dive_id=builder.DEFAULT_PACKAGE_ID, all_portfolios=False), portfolio)

    after = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    after_specs = {spec["id"]: spec for spec in after["tables"]}
    for spec in before["tables"]:
        assert after_specs[spec["id"]] == spec
    for field in ("generated_at", "funds", "source", "audit", "comparison_columns", "documentary_export"):
        assert after[field] == before[field]
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in reviewed_files} == hashes
    assert pd.read_csv(package / "tables/comparison_main.csv").iloc[0]["Nome novo A"] == 123
    assert "revise e finalize" in capsys.readouterr().out


@pytest.mark.parametrize("changed_identity", ["portfolio_id", "portfolio_signature", "funds"])
def test_rebuild_does_not_inherit_review_for_different_basket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_identity: str) -> None:
    portfolio = _portfolio()
    output_root = tmp_path / "deep_dives"
    package, previous = _reviewed_package(output_root, portfolio)
    if changed_identity == "funds":
        previous["funds"][0]["cnpj"] = "33.333.333/0001-33"
    else:
        previous[changed_identity] = "different-identity"
    (package / "manifest.json").write_text(json.dumps(previous), encoding="utf-8")
    _mock_analytical_inputs(monkeypatch, tmp_path, portfolio)

    builder.build_portfolio_package(SimpleNamespace(output_root=output_root, deep_dive_id=builder.DEFAULT_PACKAGE_ID, all_portfolios=False), portfolio)

    after = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert not any(spec["kind"] == "document_comparison" for spec in after["tables"])
    assert "comparison_evidence" not in {spec["id"] for spec in after["tables"]}
    assert "comparison_columns" not in after and "documentary_export" not in after
    assert after["generated_at"] != previous["generated_at"]
    assert after["funds"][0]["name"] == "Nome novo A"
    assert after["source"] != previous["source"]
    assert after["audit"] != previous["audit"]


def test_unreviewed_existing_package_uses_current_analytical_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    portfolio = _portfolio()
    output_root = tmp_path / "deep_dives"
    package, previous = _reviewed_package(output_root, portfolio)
    previous["tables"] = [spec for spec in previous["tables"] if spec["kind"] != "document_comparison"]
    (package / "manifest.json").write_text(json.dumps(previous), encoding="utf-8")
    _mock_analytical_inputs(monkeypatch, tmp_path, portfolio)

    builder.build_portfolio_package(SimpleNamespace(output_root=output_root, deep_dive_id=builder.DEFAULT_PACKAGE_ID, all_portfolios=False), portfolio)

    after = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert after["generated_at"] == previous["generated_at"]
    assert "comparison_columns" not in after and "documentary_export" not in after
    assert after["source"] != previous["source"]
    assert after["audit"] != previous["audit"]
