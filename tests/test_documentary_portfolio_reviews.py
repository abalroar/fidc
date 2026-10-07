from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from services.documentary_portfolio_reviews import (
    COMMON_ROWS, analytical_rows, build_comparisons, publish_portfolio,
    read_review, replace_selected_rows,
)
from services.document_curation_contract import finalize_document_curation
from services.portfolio_store import PortfolioFund, PortfolioRecord
from services.regulatory_profiles import load_curated_regulatory_profile


READING = '2026-10-07T15:00:00-03:00'


def review(cnpj, label):
    return {'cnpj': cnpj, 'label': label, 'reviewed_at': READING,
            'scope_note': 'Regulamento inacessível; fonte necessária explicitada',
            'facts': {theme: {} for theme in COMMON_ROWS},
            'sources_reviewed': [], 'key_findings': []}


def portfolio():
    return PortfolioRecord('selected', 'Carteira existente',
        (PortfolioFund('11111111000111', 'A'), PortfolioFund('22222222000122', 'B')),
        READING, READING)


def test_complete_basket_and_explicit_gaps_have_matching_cell_sources():
    p = portfolio()
    reviews = {f.cnpj: review(f.cnpj, 'Mesmo nome') for f in p.funds}
    tables, evidence, mapping = build_comparisons(p, reviews)
    assert set(mapping.values()) == {f.cnpj for f in p.funds}
    assert len(mapping) == 2
    for name, frame in tables.items():
        assert list(frame.columns) == ['Critério', *mapping]
        for label, cnpj in mapping.items():
            for _, row in frame.iterrows():
                source = evidence[(evidence.Tabela == name) & (evidence.CNPJ == cnpj) & (evidence.Critério == row['Critério'])].iloc[0]
                assert source.Valor == row[label]
                assert source.Fonte


def test_series_aliases_do_not_become_false_missing_remuneration():
    p = portfolio(); reviews = {f.cnpj: review(f.cnpj, f.display_name) for f in p.funds}
    reviews[p.funds[0].cnpj]['facts']['comparison_emissions']['Remuneração sênior'] = {
        'value': 'DI + 2,00% a.a.', 'source': 'Suplemento ID 123 p.4', 'note': 'Taxa final'}
    _, emissions, costs = analytical_rows(reviews, list(p.funds))
    assert 'DI + 2,00%' in emissions.iloc[0]['Remuneração']
    assert 'ID 123' in emissions.iloc[0]['Fonte']
    assert not emissions.isin(['', '—', 'N/D']).any().any()
    assert set(costs[costs.CNPJ == '11.111.111/0001-11'].Item) >= {'Administração', 'Gestão'}


def test_inaccessible_rule_never_becomes_direct_ime_control():
    p = portfolio(); reviews = {f.cnpj: review(f.cnpj, f.display_name) for f in p.funds}
    reviews[p.funds[0].cnpj]['facts']['comparison_mechanics']['Alocação mínima'] = {
        'value': 'Não confirmado: regulamento inacessível', 'source': 'Falha HTTP520', 'note': 'Obter regulamento'}
    criteria, _, _ = analytical_rows(reviews, list(p.funds))
    assert set(criteria[criteria.Critério == 'Alocação mínima']['Monitorabilidade IME']) == {'nao_monitoravel'}


def test_scoped_csv_update_preserves_other_cnpj_values(tmp_path):
    path = tmp_path / 'shared.csv'
    pd.DataFrame([{'CNPJ': '11111111000111', 'value': 'old', 'legacy': 'x'},
                  {'CNPJ': '33333333000133', 'value': 'unchanged', 'legacy': ''}]).to_csv(path, index=False)
    replace_selected_rows(path, pd.DataFrame([{'CNPJ': '11111111000111', 'value': 'new'}]), {'11111111000111'})
    result = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert result[result.CNPJ == '33333333000133'].iloc[0].to_dict() == {'CNPJ': '33333333000133', 'value': 'unchanged', 'legacy': ''}
    assert result[result.CNPJ == '11111111000111'].iloc[0].legacy == 'Não informado nas fontes consultadas'


def test_rebuild_preserves_reading_date_and_unrelated_index(tmp_path):
    p = portfolio(); reviews = {f.cnpj: review(f.cnpj, f.display_name) for f in p.funds}
    root = tmp_path / 'deep_dives'; root.mkdir()
    other = {'deep_dive_id': 'other', 'generated_at': '2000-01-01', 'custom': 'keep'}
    (root / 'index.json').write_text(json.dumps({'deep_dives': [other]}))
    result = publish_portfolio(p, reviews, root)
    assert result.generated_at == READING
    checked = finalize_document_curation(result.package_dir, p, output_root=root, check_only=True)
    assert checked.export_exists
    assert json.loads((root / 'index.json').read_text())['deep_dives'][0] == other


def test_review_requires_matching_identity_and_timezone(tmp_path):
    r = review('11111111000111', 'A'); path = tmp_path / '11111111000111.json'
    r['reviewed_at'] = '2026-10-07T15:00:00'; path.write_text(json.dumps(r))
    with pytest.raises(ValueError, match='fuso'): read_review(r['cnpj'], tmp_path)
    r['reviewed_at'] = READING; r['cnpj'] = '22222222000122'; path.write_text(json.dumps(r))
    with pytest.raises(ValueError, match='Identidade'): read_review('11111111000111', tmp_path)


def test_failed_inventory_is_explicit_even_when_legacy_count_is_zero(tmp_path):
    r = review('11111111000111', 'A'); r['inventory_count'] = 0
    r['inventory_error'] = 'HTTP520'
    (tmp_path / '11111111000111.json').write_text(json.dumps(r))
    loaded = read_review(r['cnpj'], tmp_path)
    assert 'indisponível' in loaded['metrics']['inventory_count']


def test_reviewed_profile_overrides_previous_manual_without_mutating_files(tmp_path):
    for filename, value in [('manual_criteria.csv', '7% (antigo)'), ('documentary_review_criteria.csv', '25% / 30% / 35%')]:
        pd.DataFrame([{'CNPJ': '11111111000111', 'Critério': 'Subordinação mínima',
                      'Limite/regra': value, 'Monitorabilidade IME': 'monitoravel com ressalva'}]).to_csv(tmp_path / filename, index=False)
    profile = load_curated_regulatory_profile('11111111000111', base_dir=tmp_path)
    assert profile.criteria_df.iloc[0]['Limite/regra'] == '25% / 30% / 35%'
