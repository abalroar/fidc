"""Published documentary baskets retain exact registry exclusions without a ZIP."""
import json
from types import SimpleNamespace

from services import documentary_ime_comparison as comparison


def test_managed_worktree_uses_its_own_portable_evidence(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git_dir = tmp_path / "main/.git/worktrees/checkout"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..")
    (checkout / ".git").write_text(f"gitdir: {git_dir}")
    monkeypatch.delenv("FIDC_DOCUMENTARY_SOURCE_ROOT", raising=False)
    monkeypatch.setattr(comparison, "__file__", str(checkout / "services/documentary_ime_comparison.py"))
    assert comparison._source_root() == checkout


def save_registry(root, *, source_url=None):
    directory = root / "data/documentary_diligence"
    directory.mkdir(parents=True)
    path = directory / "registry_statuses.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "observed_at": "2026-10-13T06:00:00Z",
        "source_url": source_url or "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip",
        "source_sha256": "a" * 64,
        "cnpjs": {
            "11111111000111": {"Data_Registro": "2020-01-01", "Data_Cancelamento": "2024-05-15", "Situacao": "CANCELADO"},
            "22222222000122": {"Data_Registro": "2020-01-01", "Data_Cancelamento": "", "Situacao": "EM FUNCIONAMENTO NORMAL"},
        },
    }))
    return path


def test_cancelled_fund_does_not_destroy_common_position_in_public_checkout(tmp_path, monkeypatch):
    save_registry(tmp_path)
    portfolio = SimpleNamespace(funds=[SimpleNamespace(cnpj=cnpj) for cnpj in ("11111111000111", "22222222000122")])
    monkeypatch.setattr(comparison, "_index", lambda root: {})
    monkeypatch.setattr(comparison, "_portable_candidates", lambda cnpj, root: {"08/2026": [({}, {}, "")]} if cnpj == "22222222000122" else {})
    result = comparison.resolve_documentary_reference(portfolio, source_root=tmp_path)
    assert result["competence"] == "08/2026"
    assert result["eligible_count"] == 1
    assert "2024" in result["excluded"]["11111111000111"]
    assert "SHA256" in result["excluded"]["11111111000111"]


def test_portable_registry_requires_official_source_and_exact_cnpj(tmp_path):
    path = save_registry(tmp_path, source_url="https://example.com/registry.zip")
    assert comparison._registry_statuses(tmp_path, {"11111111000111"}) == {}
    data = json.loads(path.read_text())
    data["source_url"] = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
    path.write_text(json.dumps(data))
    assert comparison._registry_statuses(tmp_path, {"33333333000133"}) == {}


def test_portable_registry_missing_hash_does_not_infer_exclusion(tmp_path):
    path = save_registry(tmp_path)
    data = json.loads(path.read_text())
    data.pop("source_sha256")
    path.write_text(json.dumps(data))
    assert comparison._registry_statuses(tmp_path, {"11111111000111"}) == {}
