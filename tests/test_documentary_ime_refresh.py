import csv
import json

from scripts import refresh_documentary_ime as refresh
from services.fundonet_models import DocumentoFundo


def document(identifier, *, tipo='Informe Mensal Estruturado', version=1, status='AC'):
    return DocumentoFundo(identifier, 'Informes Periódicos', tipo, '', '08/2026',
                         '01/10/2026', None, None, version, status, None, {})


def test_reuses_declared_fields_and_reprocesses_old_transformation(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, 'ROOT', tmp_path)
    cnpj = '11111111000111'
    work = tmp_path / '.cache/documentary-ime' / cnpj / f'{cnpj}_202608'
    work.mkdir(parents=True)
    (work / 'wide.csv').write_text('tag_path,08/2026\nPL,318511287\\,13\n')
    (work / 'lists.csv').write_text('tag_path,valor_raw\nCotista,1\n')
    (work / 'docs.csv').write_text('documento_id,competencia,versao,data_entrega\n123456,08/2026,2,01/10/2026\n')
    base = tmp_path / 'data/documentary_diligence'
    (base / 'ime').mkdir(parents=True)
    target = base / 'ime' / f'{cnpj}_202608.json'
    target.write_text(json.dumps({'status': 'parsed', 'source': {'document_id': '123456'}, 'values': {'net_asset_value': None}}))

    def snapshot(cache, files, requested, comp, stamp):
        assert requested == cnpj and comp == '08/2026'
        with (work / 'lists.csv').open() as stream:
            assert list(csv.DictReader(stream))[0]['competencia'] == comp
        return {'net_asset_value': 318511287.13}, {'url': 'official'}, ''

    monkeypatch.setattr(refresh, '_cache_snapshot', snapshot)
    monkeypatch.setattr(refresh, 'download_xml', lambda *_: (_ for _ in ()).throw(AssertionError('Duplicate download')))
    result = refresh.fetch_fund(cnpj, [document(123456, version=2)], base)
    data = json.loads(target.read_text())
    assert result['competences'] == ['08/2026']
    assert data['transformation_version'] == refresh.TRANSFORMATION_VERSION
    assert data['values']['net_asset_value'] == 318511287.13
    assert 'declared_fields_sha256' in data['source']
    assert 'sha256' not in data['source']


def test_monthly_filter_precedes_version_selection(tmp_path, monkeypatch):
    received = []

    def latest(documents):
        received.extend(documents)
        return []

    monkeypatch.setattr(refresh, 'select_latest_documents', latest)
    result = refresh.fetch_fund('11111111000111', [document(1), document(2, tipo='Informe Trimestral Estruturado')], tmp_path)
    assert [item.id for item in received] == [1]
    assert result['competences'] == []


def test_xml_competence_mismatch_is_recorded(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(refresh, 'ROOT', tmp_path)
    monkeypatch.setattr(refresh, 'download_xml', lambda *_: b'xml')
    monkeypatch.setattr(refresh, 'parse_informe_mensal_xml', lambda *_: SimpleNamespace(metadata={'competencia_xml': '07/2026'}))
    result = refresh.fetch_fund('11111111000111', [document(1)], tmp_path)
    assert not result['snapshots']
    assert 'XML competence differs' in result['attempts'][0]['error']


def test_default_through_uses_previous_calendar_month():
    from datetime import date
    class January:
        @staticmethod
        def today():
            return date(2026, 1, 15)
    from unittest.mock import patch
    with patch.object(refresh, 'date', January):
        assert refresh.default_through() == '12/2025'
