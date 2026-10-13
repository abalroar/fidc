import json
from services import documentary_ime_comparison as ime
from tests.test_documentary_ime_comparison import make_cache, make_portable, CNPJ


def test_old_transform_never_masks_current_declared_fields(tmp_path):
    make_cache(tmp_path)
    path=make_portable(tmp_path,version=1,cash=99)
    payload=json.loads(path.read_text());payload['transformation_version']=ime.IME_TRANSFORMATION_VERSION-1
    payload['source'].update(document_id='1138236',delivered_at='13/03/2026 21:53')
    path.write_text(json.dumps(payload))
    values,source,error=ime._snapshot(CNPJ,'02/2026',None,tmp_path)
    assert not error
    assert source['type']=='ime_cache' and values['cash']==2


def test_no_valid_source_means_refresh_needed_not_silent_old_snapshot(tmp_path):
    path=make_portable(tmp_path)
    payload=json.loads(path.read_text());payload.pop('transformation_version')
    path.write_text(json.dumps(payload))
    values,source,error=ime._snapshot(CNPJ,'02/2026',None,tmp_path)
    assert not values and 'transformação anterior' in error
