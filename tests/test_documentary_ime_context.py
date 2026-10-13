from pathlib import Path
from tests.test_documentary_ime_comparison import CNPJ, dashboard
from services.documentary_ime_comparison import build_documentary_observations
from services.documentary_ime_comparison import _header_cnpj, _cnpj


def observed(criterion):
    return build_documentary_observations(
        {'cnpj': CNPJ, 'criteria': [{'criterion_id': criterion, 'status': 'confirmed',
         'applicability': 'applicable', 'rule': {}, 'sources': [{'document_id': 123456,
         'reference_date': '2025-03-20', 'page': 14}]}]},
        competence='06/2026', dashboard=dashboard(),
        cache_root=Path(__file__).parent / 'fixtures/no_documentary_ime')[0]


def test_aggregate_pdd_never_certifies_operation_level_curve():
    item = observed('pdd')
    assert item['comparison_required']
    assert item['context_value'] == 1 / 97 * 100
    assert item['observed_value'] is None
    assert item['status'] == 'not_comparable'
    assert 'por operação' in item['reason']


def test_cash_is_visible_but_never_equated_to_contractual_reserve():
    item = observed('liquidity_reserve')
    assert item['context_value'] == 2
    assert item['context_unit'] == 'currency'
    assert item['observed_value'] is None
    assert 'não comprovam a reserva' in item['reason']


def test_concentration_requires_individual_exposures():
    item = observed('concentration')
    assert item['comparison_required']
    assert item['context_value'] is None
    assert 'exposição individual' in item['reason']


def test_integer_serialized_cnpj_recovers_omitted_leading_zero_without_name_alias():
    assert _header_cnpj('8417544000165') == '08417544000165'
    assert _header_cnpj('08.417.544/0001-65') == '08417544000165'
    assert _cnpj('8417544000165') == '08417544000165'
    assert _cnpj('fundo8417544000165') != '08417544000165'
