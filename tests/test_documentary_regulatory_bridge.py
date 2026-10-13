import json
from services import regulatory_profiles as profiles


def test_typed_criteria_override_heuristic_without_enabling_old_first_percent_checker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = tmp_path / 'data/regulatory_profiles'
    old.mkdir(parents=True)
    (old / 'documentary_review_old.csv').write_text(
        'CNPJ,Critério,Monitorabilidade IME,Limite/regra\n11111111000111,Alocação,direto,50%\n'
    )
    typed = tmp_path / 'typed'
    typed.mkdir()
    monkeypatch.setattr(profiles, 'DOCUMENTARY_DILIGENCE_DIR', typed)
    (typed / '11111111000111.json').write_text(json.dumps({
        'schema_version': 2, 'cnpj': '11111111000111', 'fund_name': 'Fundo A',
        'criteria': [{'criterion_id': 'allocation', 'label': 'Alocação', 'value': '51% após 180 dias',
                      'status': 'confirmed', 'sources': [{'document_id': 123456, 'reference_date': '2026-03-20', 'page': 14}],
                      'rule': {'limit': 51, 'initial_days': 180}}]
    }))
    profile = profiles.load_curated_regulatory_profile('11111111000111')
    row = profile.criteria_df.iloc[0]
    assert row['Limite/regra'] == '51% após 180 dias'
    assert row['Condição de alerta sugerida'] == ''
    assert row['Monitorabilidade IME'] == 'Comparação documental na aba Documentos'
    assert 'página 14' in row['Fonte']


def test_identity_mismatch_cannot_replace_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, 'DOCUMENTARY_DILIGENCE_DIR', tmp_path)
    (tmp_path / '11111111000111.json').write_text(json.dumps({'schema_version': 2, 'cnpj': '22222222000122'}))
    assert profiles._documentary_criteria('11111111000111') is None
