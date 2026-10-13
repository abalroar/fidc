from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pandas as pd
import pytest

from services.documentary_ime_comparison import build_documentary_observations, normalize_documentary_competence, resolve_documentary_reference
from services.documentary_ime_comparison import IME_TRANSFORMATION_VERSION


CNPJ = "60010416000112"
OTHER = "63953620000165"


def portfolio(*cnpjs):
    return SimpleNamespace(funds=[SimpleNamespace(cnpj=c) for c in cnpjs])


def dashboard(cnpj=CNPJ, *, competences=("02/2026", "06/2026"), subordinate=(4.403413507281979, 5.721992103450954)):
    return SimpleNamespace(
        fund_info={"cnpj_fundo": cnpj}, competencias=list(competences),
        subordination_history_df=pd.DataFrame([{"competencia": c, "pl_total_oficial": 100.0, "pl_subordinada_strict": value, "pl_mezzanino": 0.0, "pl_subordinada": value, "pl_reconciliacao_warning": False} for c, value in zip(competences, subordinate)]),
        dc_canonical_history_df=pd.DataFrame([{"competencia": c, "dc_total_canonico": 97.0, "dc_vencidos_canonico": 6.0} for c in competences]),
        asset_history_df=pd.DataFrame([{"competencia": c, "disponibilidades": 2.0} for c in competences]),
        default_history_df=pd.DataFrame([{"competencia": c, "provisao_total": 1.0} for c in competences]),
    )


def fund(**rule_overrides):
    rule = {"operator": ">=", "limit": 5.0, "unit": "percent", "numerator": "subordinated_quotas", "denominator": "net_asset_value", "frequency": "daily", "cure_days": 10, "cure_unit": "dias úteis", "effective_from": "2025-03-21", "layer": "class"}
    rule.update(rule_overrides)
    return {"cnpj": CNPJ, "criteria": [{"criterion_id": "subordination", "applicability": "applicable", "status": "confirmed", "sources": [{"document_id": 993786, "reference_date": "2025-03-20", "page": "14", "clause": "5.3"}], "rule": rule}]}


def observe(f=None, competence="02/2026", d=None):
    # Isolate the synthetic dashboard from snapshots in the developer checkout.
    return build_documentary_observations(f or fund(), competence=competence, dashboard=d or dashboard(), cache_root=Path(__file__).parent / "fixtures" / "no_documentary_ime")[0]


def test_reference_requires_all_declared_cnpjs(tmp_path):
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), {CNPJ: dashboard()}, source_root=tmp_path)
    assert result["competence"] is None
    assert result["declared_count"] == 2
    assert result["available_count"] == 1
    assert result["missing_cnpjs"] == [OTHER]


def test_reference_uses_common_month_and_exact_class_identity(tmp_path):
    other = dashboard(OTHER, competences=("02/2026",), subordinate=(2.0,))
    other.fund_info = {"cnpj_fundo": CNPJ, "cnpj_classe": OTHER}
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), {CNPJ: dashboard(), OTHER: other}, source_root=tmp_path)
    assert result["competence"] == "02/2026"
    assert result["available_count"] == 2
    assert result["latest_observed"] == "06/2026"


def test_documented_cancellation_can_exclude_declared_fund_without_ime(tmp_path):
    url = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
    path = tmp_path / ".cache/cvm-cadastro" / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("registro_fundo.csv", f"CNPJ_Fundo;Data_Cancelamento;Situacao\n{OTHER};2024-10-31;Cancelado\n")
        archive.writestr("registro_classe.csv", "CNPJ_Classe;Data_Registro\n")
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), {CNPJ: dashboard()}, source_root=tmp_path)
    assert result["competence"] == "06/2026"
    assert result["declared_count"] == 2
    assert result["eligible_count"] == 1
    assert "Cancelado em 31/10/2024" in result["excluded"][OTHER]


def test_daily_rule_compares_monthly_snapshot_and_preserves_cure_limit():
    below = observe()
    assert below["observed_value"] == pytest.approx(4.403413507281979)
    assert below["status"] == "observed_below_limit"
    assert below["headroom"] == pytest.approx(-0.5965864927180209)
    assert "não comprova apuração diária" in below["reason"]
    assert "10 dias úteis" in below["reason"]
    inside = observe(competence="06/2026")
    assert inside["status"] == "compliant_snapshot"
    assert inside["observed_value"] == pytest.approx(5.721992103450954)
    assert "snapshot mensal" in inside["reason"]


def test_unavailable_contract_asset_base_does_not_use_pl_proxy():
    row = observe(fund(numerator="credit_rights", denominator="assets", limit=50.0))
    assert row["status"] == "not_comparable"
    assert row["observed_value"] is None
    assert "não são intercambiáveis" in row["reason"]


def test_future_document_cannot_certify_historical_ime():
    row = observe(fund(effective_from="2026-08-27"))
    assert row["status"] == "version_not_applicable"
    assert row["observed_value"] is not None
    assert row["headroom"] is None


def test_document_date_alone_does_not_assume_effective_date():
    row = observe(fund(effective_from=None, effective_status="document_date_only"))
    assert row["status"] == "not_comparable"
    assert "Vigência efetiva não comprovada" in row["reason"]


def test_historical_expired_rule_and_future_source_are_inapplicable():
    assert observe(fund(effective_to="2026-01-31"))["status"] == "version_not_applicable"
    data = fund(effective_from=None)
    data["criteria"][0]["sources"][0]["reference_date"] = "2026-08-27"
    assert observe(data)["status"] == "version_not_applicable"


def test_source_without_location_does_not_certify_rule():
    data = fund()
    data["criteria"][0]["sources"] = [{"document_id": 993786, "reference_date": "2025-03-20"}]
    assert observe(data)["status"] == "not_comparable"


def test_subclass_rule_cannot_use_class_aggregate():
    row = observe(fund(layer="subclass"))
    assert row["status"] == "not_comparable"
    assert "saldo individual" in row["reason"]


@pytest.mark.parametrize("status", ["version_conflict", "access_blocked", "parse_failed", "clause_not_found", "referenced_document_missing", "extraction_pending"])
def test_unconfirmed_rule_never_certifies_a_snapshot(status):
    data = fund()
    data["criteria"][0]["status"] = status
    assert observe(data)["status"] == "not_comparable"


def test_zero_denominator_and_missing_cash_are_not_zero_ratios():
    d = dashboard()
    d.subordination_history_df["pl_total_oficial"] = 0.0
    row = observe(d=d)
    assert row["status"] == "not_comparable"
    assert row["observed_value"] is None
    d = dashboard()
    d.asset_history_df["disponibilidades"] = None
    row = observe(fund(numerator="cash", limit=1.0), d=d)
    assert row["status"] == "ime_unavailable"
    assert row["observed_value"] is None


def test_reconciliation_and_identity_failures_suspend_comparison():
    d = dashboard()
    d.subordination_history_df["pl_reconciliacao_warning"] = True
    assert observe(d=d)["status"] == "ime_unavailable"
    row = observe(d=dashboard(OTHER))
    assert row["status"] == "ime_unavailable"
    assert "Identidade" in row["reason"]


def make_cache(root: Path, *, raw_cnpj=CNPJ):
    directory = root / ".cache/fundonet-ime/test"
    directory.mkdir(parents=True)
    fields = {"wide_csv_path": "wide.csv", "docs_csv_path": "docs.csv"}
    (directory / "manifest.json").write_text(json.dumps({"cnpj_fundo": CNPJ, "competencias": ["02/2026"], "files": fields}))
    with (directory / "wide.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["tag_path", "02/2026"])
        writer.writerow(["DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO", raw_cnpj])
        writer.writerow(["DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ", "100"])
        writer.writerow(["DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB", "2"])
    (directory / "docs.csv").write_text("documento_id,competencia,versao,data_entrega\n1138236,02/2026,1,13/03/2026 21:53\n")
    return root


def test_cache_reader_selects_month_and_records_ime_document(tmp_path):
    root = make_cache(tmp_path)
    row = build_documentary_observations(fund(numerator="cash", limit=1.0), competence="2026-02", cache_root=root)[0]
    assert row["observed_value"] == pytest.approx(2.0)
    assert row["competence"] == "02/2026"
    assert row["source"]["document_id"] == "1138236"
    assert row["status"] == "compliant_snapshot"


def test_cache_header_cnpj_mismatch_is_explicit(tmp_path):
    root = make_cache(tmp_path, raw_cnpj=OTHER)
    row = build_documentary_observations(fund(numerator="cash"), competence="02/2026", cache_root=root)[0]
    assert row["status"] == "ime_unavailable"
    assert "CNPJ no cabeçalho" in row["reason"]


def test_semantic_nonapplicable_subordination_stays_nonapplicable():
    data = fund()
    data["criteria"][0]["applicability"] = "not_applicable"
    assert observe(data)["status"] == "not_comparable"
    assert "não aplicável" in observe(data)["reason"]


def test_documentary_export_uses_reviewed_facts_pages(monkeypatch):
    from tabs import portfolio_page, documentary_facts_view
    from services import documentary_facts, deep_dive_ppt_export
    p = SimpleNamespace(id="new", name="Cesta", funds=[SimpleNamespace(cnpj=CNPJ)])
    pages = (SimpleNamespace(title="Regra 1"), SimpleNamespace(title="Regra 2"))
    manifest = SimpleNamespace(deep_dive_id="documentary_facts_new")
    monkeypatch.setattr(documentary_facts, "portfolio_ready", lambda p: True)
    monkeypatch.setattr(documentary_facts_view, "facts_comparison_content", lambda p: (manifest, list(pages)))
    calls = []
    def export(manifest, content, **kwargs):
        calls.append((manifest, content, kwargs))
        return b"pptx"
    monkeypatch.setattr(deep_dive_ppt_export, "build_document_comparison_pptx_bytes", export)
    assert portfolio_page._build_documentary_portfolio_deck(p, portfolio_mode=True) == b"pptx"
    assert calls[0][1] == pages
    assert calls[0][2] == {"portfolio_mode": True, "compact": False}


@pytest.mark.parametrize("raw,expected", [("2026-02", "02/2026"), ("2026-02-28", "02/2026"), ("02/2026", "02/2026"), ("N/D", None), ("13/2026", None)])
def test_competence_accepts_explicit_month_formats(raw, expected):
    assert normalize_documentary_competence(raw) == expected


def make_portable(root, cnpj=CNPJ, competence="02/2026", *, version=2, cash=7.0, raw_cnpj=None):
    directory = root / "data/documentary_diligence"
    relative = f"ime/{cnpj}_{competence[3:]}{competence[:2]}.json"
    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cnpj": raw_cnpj or cnpj, "competence": competence, "status": "parsed", "transformation_version": IME_TRANSFORMATION_VERSION,
        "values": {"net_asset_value": 100.0, "cash": cash, "subordinated_quotas": 7.0, "senior_quotas": 93.0},
        "source": {"type": "ime_document", "cnpj": cnpj, "competence": competence, "document_id": 1234567,
                   "version": version, "delivered_at": "2026-03-14T21:53:00", "url": "https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento?id=1234567",
                   "sha256": "a" * 64, "fields": ["net_asset_value", "cash"]}, "error": "",
    }))
    index_path = directory / "ime_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"schema_version": 1, "cnpjs": {}}
    entry = index["cnpjs"].setdefault(cnpj, {"competences": [], "snapshots": {}})
    entry["competences"].append(competence)
    entry["snapshots"][competence] = relative
    index_path.write_text(json.dumps(index))
    return path


def test_portable_reference_works_without_cache_and_requires_every_declared_cnpj(tmp_path):
    make_portable(tmp_path, competence="08/2026")
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), source_root=tmp_path)
    assert result["competence"] is None
    assert result["missing_cnpjs"] == [OTHER]
    make_portable(tmp_path, competence="07/2026")
    make_portable(tmp_path, OTHER, competence="07/2026")
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), source_root=tmp_path)
    assert result["competence"] == "07/2026"
    assert result["latest_observed"] == "08/2026"


def test_portable_and_original_cache_months_combine_with_dashboard_months(tmp_path):
    make_cache(tmp_path)
    make_portable(tmp_path, CNPJ, "08/2026")
    make_portable(tmp_path, OTHER, "08/2026")
    result = resolve_documentary_reference(portfolio(CNPJ, OTHER), {CNPJ: dashboard(), OTHER: dashboard(OTHER)}, source_root=tmp_path)
    assert result["competence"] == "08/2026"
    assert result["common_competences"] == ["02/2026", "06/2026", "08/2026"]


@pytest.mark.parametrize("cache_version,expected_cash,expected_type", [(1, 7.0, "ime_document"), (3, 2.0, "ime_cache")])
def test_snapshot_selects_highest_version_across_portable_and_cache(tmp_path, cache_version, expected_cash, expected_type):
    make_cache(tmp_path)
    docs_path = tmp_path / ".cache/fundonet-ime/test/docs.csv"
    docs_path.write_text(f"documento_id,competencia,versao,data_entrega\n1138236,02/2026,{cache_version},13/03/2026 21:53\n")
    make_portable(tmp_path)
    row = build_documentary_observations(fund(numerator="cash", limit=1), competence="02/2026", dashboard=dashboard(), cache_root=tmp_path)[0]
    assert row["observed_value"] == pytest.approx(expected_cash)
    assert row["source"]["type"] == expected_type


def test_portable_snapshot_null_and_wrong_identity_are_explicit(tmp_path):
    make_portable(tmp_path, cash=None)
    row = build_documentary_observations(fund(numerator="cash"), competence="02/2026", cache_root=tmp_path)[0]
    assert row["status"] == "ime_unavailable"
    assert row["observed_value"] is None
    make_portable(tmp_path, raw_cnpj=OTHER)
    result = resolve_documentary_reference(portfolio(CNPJ), source_root=tmp_path)
    assert result["available_count"] == 0
    assert result["missing_cnpjs"] == [CNPJ]
    row = build_documentary_observations(fund(), competence="02/2026", cache_root=tmp_path)[0]
    assert row["status"] == "ime_unavailable"
    assert "Identidade" in row["reason"]


def test_portable_index_rejects_paths_outside_published_directory(tmp_path):
    path = make_portable(tmp_path)
    index_path = tmp_path / "data/documentary_diligence/ime_index.json"
    index = json.loads(index_path.read_text())
    index["cnpjs"][CNPJ]["snapshots"]["02/2026"] = "../../outside.json"
    index_path.write_text(json.dumps(index))
    assert resolve_documentary_reference(portfolio(CNPJ), source_root=tmp_path)["available_count"] == 0
    assert path.exists()


def test_default_portable_data_is_found_next_to_deployed_module(tmp_path, monkeypatch):
    from services import documentary_ime_comparison as service
    make_portable(tmp_path)
    monkeypatch.setattr(service, "__file__", str(tmp_path / "services/documentary_ime_comparison.py"))
    result = service.resolve_documentary_reference(portfolio(CNPJ))
    assert result["competence"] == "02/2026"
    row = service.build_documentary_observations(fund(numerator="cash"), competence="02/2026")[0]
    assert row["source"]["type"] == "ime_document"
    assert row["observed_value"] == pytest.approx(7.0)


def test_initial_grace_requires_proven_inception_and_retains_observation():
    row = observe(fund(initial_days=180))
    assert row["status"] == "not_comparable"
    assert row["observed_value"] is not None
    assert "data de início/primeira integralização" in row["reason"]
    row = observe(fund(initial_days=180, initial_date="2025-12-01"))
    assert row["status"] == "version_not_applicable"
    row = observe(fund(initial_days=180, initial_date="2025-03-21"), competence="06/2026")
    assert row["status"] == "compliant_snapshot"


@pytest.mark.parametrize("senior", [None, 0.0, 93.0])
def test_rule_requiring_senior_does_not_assume_its_existence(senior):
    d = dashboard()
    d.subordination_history_df["pl_senior"] = senior
    row = observe(fund(requires_senior_outstanding=True), competence="06/2026", d=d)
    assert row["status"] == ("compliant_snapshot" if senior else "not_comparable")
    assert row["observed_value"] is not None


def test_historical_version_is_inapplicable_even_when_asset_metric_is_unavailable():
    row = observe(fund(numerator="agribusiness_credit_rights", effective_from="2026-03-23"))
    assert row["status"] == "version_not_applicable"
    assert row["observed_value"] is None


def test_declared_zero_pl_and_empty_quotas_preserve_zero_without_calculating_ratios(tmp_path):
    from services.documentary_ime_comparison import _cache_snapshot
    make_cache(tmp_path)
    directory = tmp_path / ".cache/fundonet-ime/test"
    wide = directory / "wide.csv"
    wide.write_text(wide.read_text().replace("VL_PATRIM_LIQ,100", "VL_PATRIM_LIQ,0"))
    values, source, error = _cache_snapshot(str(directory), json.dumps({"wide_csv_path": "wide.csv", "docs_csv_path": "docs.csv"}), CNPJ, "02/2026", wide.stat().st_mtime_ns)
    assert error == ""
    assert values["net_asset_value"] == 0.0
    assert values["cash"] == 2.0
    assert values["subordinated_quotas"] is None
    assert values["senior_quotas"] is None
    assert "PL oficial" in source["warnings"][0]
    row = build_documentary_observations(fund(), competence="02/2026", cache_root=tmp_path)[0]
    assert row["status"] == "not_comparable"
    assert row["observed_value"] is None
    assert "Denominador IME nulo" in row["reason"]


def test_noncalculable_quota_frame_retains_other_ime_fields_with_warning(tmp_path, monkeypatch):
    from services import fundonet_dashboard
    from services.documentary_ime_comparison import _cache_snapshot
    make_cache(tmp_path)
    def fail(**kwargs):
        raise ZeroDivisionError("division by zero")
    monkeypatch.setattr(fundonet_dashboard, "_build_quota_pl_history", fail)
    directory = tmp_path / ".cache/fundonet-ime/test"
    values, source, error = _cache_snapshot(str(directory), json.dumps({"wide_csv_path": "wide.csv"}), CNPJ, "02/2026", 1)
    assert error == ""
    assert values["net_asset_value"] == 100.0
    assert values["cash"] == 2.0
    assert values["subordinated_quotas"] is None
    assert "ZeroDivisionError" in source["warnings"][0]


def test_parser_list_competence_is_normalized_before_canonical_quota_reader(tmp_path):
    from services.documentary_ime_comparison import _cache_snapshot
    make_cache(tmp_path)
    directory = tmp_path / ".cache/fundonet-ime/test"
    lists = directory / "lists.csv"
    base = "DOC_ARQ/LISTA_INFORM/OUTRAS_INFORM/DESC_SERIE_CLASSE/"
    with lists.open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["competencia_xml", "list_group_path", "list_index", "tag", "valor_excel"])
        for kind, quantity in (("SENIOR", 95), ("SUBORD", 5)):
            for tag, value in (("QT_COTAS", quantity), ("VL_COTAS", 1)):
                writer.writerow(["2026-02-28", base + "DESC_SERIE_CLASSE_" + kind, 1, tag, value])
    values, source, error = _cache_snapshot(str(directory), json.dumps({"wide_csv_path": "wide.csv", "listas_csv_path": "lists.csv"}), CNPJ, "02/2026", 1)
    assert error == ""
    assert values["senior_quotas"] == 95.0
    assert values["subordinated_quotas"] == 5.0
    assert not source["warnings"]


def test_umbrella_fund_header_does_not_override_different_class_identity(tmp_path):
    make_cache(tmp_path)
    wide = tmp_path / ".cache/fundonet-ime/test/wide.csv"
    with wide.open("a") as stream:
        stream.write(f"DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE,{OTHER}\n")
    row = build_documentary_observations(fund(), competence="02/2026", cache_root=tmp_path)[0]
    assert row["status"] == "ime_unavailable"
    assert row["source"]["reported_fund_cnpj"] == CNPJ
    assert row["source"]["reported_class_cnpj"] == OTHER
    assert row["source"]["identity_basis"] == "class"
    assert f"fundo={CNPJ}, classe={OTHER}" in row["reason"]


def test_raw_xml_decimals_are_normalized_without_losing_cnpj_leading_zero(tmp_path):
    from services.documentary_ime_comparison import _cache_snapshot
    cnpj = "03311443000191"
    directory = tmp_path / "raw"
    directory.mkdir()
    with (directory / "wide.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["tag_path", "02/2026"])
        writer.writerow(["DOC_ARQ/CAB_INFORM/NR_CNPJ_FUNDO", cnpj])
        writer.writerow(["DOC_ARQ/LISTA_INFORM/PATRLIQ/VL_PATRIM_LIQ", "1234567,89"])
        writer.writerow(["DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VL_DISPONIB", "0,00"])
        writer.writerow(["DOC_ARQ/LISTA_INFORM/APLIC_ATIVO/VALORES_MOB/VL_COTA_FIDC", "950000,25"])
    values, source, error = _cache_snapshot(str(directory), json.dumps({"wide_csv_path": "wide.csv"}), cnpj, "02/2026", 1)
    assert error == ""
    assert source["reported_fund_cnpj"] == cnpj
    assert values["net_asset_value"] == 1234567.89
    assert values["cash"] == 0.0
    assert values["fidc_quotas"] == 950000.25


def test_numeric_header_omitted_leading_zero_is_restored_before_exact_comparison(tmp_path):
    from services.documentary_ime_comparison import _cache_snapshot
    expected='08417544000165'
    make_cache(tmp_path,raw_cnpj=expected[1:])
    directory=tmp_path/'.cache/fundonet-ime/test'
    wide=directory/'wide.csv'
    with wide.open('a') as stream:
        stream.write(f'DOC_ARQ/CAB_INFORM/NR_CNPJ_CLASSE,{expected[1:]}\n')
    values,source,error=_cache_snapshot(str(directory),json.dumps({'wide_csv_path':'wide.csv'}),expected,'02/2026',1)
    assert error==''
    assert values['net_asset_value']==100.0
    assert source['reported_class_cnpj']==expected
    assert source['reported_class_cnpj_raw']==expected[1:]
