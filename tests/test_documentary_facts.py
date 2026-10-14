import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services import documentary_facts as facts
from services.documentary_facts_catalog import ROW_BY_ID, ROWS, rows_for_types
from services.documentary_facts_validation import check_answer, copied_sequence, numbers_in, unsupported_names, unsupported_numbers


def _fact(display, value=None, status="confirmed", basis=""):
    payload = {"display": display, "status": status,
               "sources": [{"kind": "Regulamento", "date": "01/01/2026", "page": 3, "clause": "cl. 4.1", "excerpt": display}]}
    if value is not None:
        payload["value"] = value
    if basis:
        payload["basis"] = basis
    return payload


def _absent(display="Não prevista"):
    return {"display": display, "status": "absent", "reason": "sem previsão", "sources": []}


def _portfolio(*cnpjs):
    return SimpleNamespace(id="p", name="Carteira", funds=[SimpleNamespace(cnpj=c, display_name=f"Alfa {c[-2:]}") for c in cnpjs])


class _Store:
    """Temporary facts and IME folders patched into the module."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.facts_dir, self.ime_dir = root / "facts", root / "ime"
        self.facts_dir.mkdir()
        self.ime_dir.mkdir()
        self._patches = [patch.object(facts, "FACTS_DIR", self.facts_dir), patch.object(facts, "IME_DIR", self.ime_dir)]
        for item in self._patches:
            item.start()
        self._clear()
        return self

    def __exit__(self, *exc):
        for item in self._patches:
            item.stop()
        self._clear()
        self._tmp.cleanup()

    @staticmethod
    def _clear():
        for cached in (facts._load, facts._ime_values, facts._peer_index):
            cached.cache_clear()

    def fund(self, cnpj, fund_type, rows, approved=True):
        payload = {"schema_version": 1, "cnpj": cnpj, "name": f"FUNDO {cnpj}", "fund_type": fund_type,
                   "facts": {"fund_type": {"display": fund_type, "status": "confirmed", "sources": []}, **rows},
                   "leitura": f"Leitura {cnpj}", "documents": {}, "validation": {"approved": approved, "issues": []}}
        (self.facts_dir / f"{cnpj}.json").write_text(json.dumps(payload, ensure_ascii=False))

    def ime(self, cnpj, competence, values):
        (self.ime_dir / f"{cnpj}_{competence}.json").write_text(json.dumps({"status": "parsed", "values": values}))


class ValidationTests(unittest.TestCase):
    def test_numbers_and_names_must_come_from_the_cited_passage(self):
        passage = "o saldo devido pelo mesmo Devedor não deverá exceder R$ 150.000,00 (cento e cinquenta mil reais); Parati Crédito"
        self.assertEqual(unsupported_numbers("R$ 150 mil", passage), [])
        self.assertEqual(unsupported_numbers("R$ 200 mil", passage), ["200000"])
        self.assertEqual(unsupported_names("Parati CFI", passage), [])
        self.assertEqual(unsupported_names("Banco Itaú Unibanco", passage), ["Banco", "Unibanco"])
        self.assertEqual(numbers_in("40% na 1ª integralização"), [40.0])

    def test_answers_cannot_copy_clauses_use_gap_phrases_or_exceed_the_cell(self):
        row = ROW_BY_ID["eligibility"]
        passage = "a Classe somente poderá adquirir os Direitos Creditórios que atendam cumulativamente aos seguintes critérios"
        copied = "a Classe somente poderá adquirir os Direitos Creditórios que atendam"
        self.assertTrue(copied_sequence(copied, passage))
        self.assertTrue(any("cópia literal" in p for p in check_answer(row, copied, "confirmed", [{"excerpt": passage}], "")))
        self.assertTrue(any("frase de lacuna" in p for p in check_answer(row, "Síntese pendente", "confirmed", [{"excerpt": "x"}], "")))
        self.assertTrue(any("caracteres" in p for p in check_answer(row, "x" * 91, "confirmed", [{"excerpt": "x" * 91}], "")))
        self.assertTrue(any("motivo" in p for p in check_answer(row, "n/d", "nd", [], "")))

    def test_modules_follow_fund_types(self):
        consignado = {row.id for row in rows_for_types({"Consignado privado"})}
        fic = {row.id for row in rows_for_types({"FIC"})}
        self.assertIn("age_limit", consignado)
        self.assertNotIn("investee", consignado)
        self.assertIn("investee", fic)
        self.assertNotIn("age_limit", fic)
        self.assertLessEqual({row.id for row in ROWS if row.module == "core"}, consignado & fic)


class ViewTests(unittest.TestCase):
    def test_side_by_side_moves_identical_rows_and_monitors_the_ime(self):
        with _Store() as store:
            store.fund("11111111000111", "Consignado privado", {
                "sub_senior": _fact("5% · subord./PL", 5, basis="jr/PL"), "admin_fee": _fact("0,10% a.a."), "perf_fee": _absent()})
            store.fund("22222222000122", "Consignado privado", {
                "sub_senior": _fact("1% · subord./PL", 1, basis="jr/PL"), "admin_fee": _fact("0,05% a.a."), "perf_fee": _absent()})
            for cnpj, sub in (("11111111000111", 8.0), ("22222222000122", 3.0)):
                store.ime(cnpj, "202608", {"net_asset_value": 100.0, "subordinated_quotas": sub,
                                           "subordinated_and_mezzanine_quotas": sub, "credit_rights": 95.0, "pdd": 5.0})
            view = facts.build_view(_portfolio("11111111000111", "22222222000122"))
        self.assertEqual((view.layout, view.competence), ("side_by_side", "202608"))
        protection = next(s for s in view.sections if s.title == "Estrutura e proteção")
        rows = dict(protection.rows)
        self.assertEqual(rows["Subordinação mínima da sênior"], ["5% · subord./PL", "1% · subord./PL"])
        self.assertEqual(rows["↳ Folga sobre o mínimo"], ["+3,0 p.p.", "+2,0 p.p."])
        costs = next(s for s in view.sections if s.title == "Custos e remuneração")
        self.assertTrue(any("Taxa de performance" in note for note in costs.common))
        self.assertTrue(any("de 1% (Alfa 22) a 5% (Alfa 11)" in note for note in protection.differences))

    def test_coverage_protection_is_not_compared_with_the_ime(self):
        with _Store() as store:
            store.fund("33333333000133", "Energia solar", {"sub_senior": _fact("Cobertura sênior ≥ 133,3%", 133.3, basis="cobertura")})
            store.ime("33333333000133", "202609", {"net_asset_value": 100.0, "subordinated_and_mezzanine_quotas": 20.0})
            fact = facts.load_facts("33333333000133")["facts"]["sub_senior"]
            observation = facts.observe("sub_senior", fact, facts._ime_values("33333333000133", "202609"), "Energia solar")
        self.assertIsNone(observation.observed)
        self.assertIn("cobertura", observation.note)
        self.assertEqual(facts._unit_kind("Cobertura sênior ≥ 133,3%"), "cov")

    def test_single_fund_uses_peers_and_baskets_wait_for_every_fund(self):
        with _Store() as store:
            for index, value in enumerate((5, 10, 15, 20)):
                store.fund(f"4444444400014{index}", "FIC", {"allocation": _fact(f"≥ {value}% do PL", value)})
            view = facts.build_view(_portfolio("44444444000140"))
            store.fund("55555555000155", "FIC", {}, approved=False)
            ready_pair = facts.portfolio_ready(_portfolio("44444444000140", "44444444000141"))
            pending = facts.portfolio_ready(_portfolio("44444444000140", "55555555000155"))
            missing = facts.portfolio_ready(_portfolio("44444444000140", "66666666000166"))
        self.assertEqual((view.layout, view.peers_label), ("single", "Pares: FIC"))
        allocation = dict(next(s for s in view.sections if s.title == "Elegibilidade e concentração").rows)["Alocação mínima em DC"]
        self.assertTrue(allocation[1].startswith("mediana 15%") and allocation[1].endswith("n=3"))
        self.assertTrue(ready_pair)
        self.assertFalse(pending)
        self.assertFalse(missing)

    def test_pl_over_senior_peers_are_not_pooled_with_subordination_shares(self):
        with _Store() as store:
            for index, value in enumerate((10, 20, 30)):
                store.fund(f"8888888800018{index}", "Veículos", {"sub_senior": _fact(f"{value}% · subord./PL", value, basis="jr/PL")})
            store.fund("88888888000189", "Veículos", {"sub_senior": _fact("PL/sênior ≥ 125%", 125, basis="PL/sr")})
            view = facts.build_view(_portfolio("88888888000180"))
        protection = dict(next(s for s in view.sections if s.title == "Estrutura e proteção").rows)
        self.assertEqual(protection["Subordinação mínima da sênior"][1], "pares insuficientes")

    def test_large_baskets_use_the_transposed_layout(self):
        cnpjs = [f"7777777700{index:04d}" for index in range(10)]
        with _Store() as store:
            for cnpj in cnpjs:
                store.fund(cnpj, "Crédito pessoal", {"admin_fee": _fact("0,10% a.a.")})
            view = facts.build_view(_portfolio(*cnpjs))
        self.assertEqual(view.layout, "transposed")
        self.assertEqual(len(view.transposed), 10)
        self.assertIn("Taxa de administração", view.transposed[0])


class PublishedFactsTests(unittest.TestCase):
    def test_published_facts_are_approved_short_and_grounded(self):
        for path in facts.FACTS_DIR.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["validation"]["approved"], path.name)
            for row_id, fact in payload["facts"].items():
                self.assertLessEqual(len(fact["display"]), 90, (path.name, row_id))
                if fact["status"] == "confirmed" and row_id != "fund_type":
                    self.assertTrue(fact["sources"], (path.name, row_id))
                    evidence = " ".join(s["excerpt"] for s in fact["sources"])
                    self.assertEqual(unsupported_numbers(fact["display"], evidence), [], (path.name, row_id))
                if fact["status"] in {"nd", "not_applicable", "absent"}:
                    self.assertTrue(fact["reason"], (path.name, row_id))


if __name__ == "__main__":
    unittest.main()
