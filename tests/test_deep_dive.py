from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from services.deep_dive_ppt_export import build_deep_dive_pptx_bytes
from services.deep_dive_store import list_deep_dives, load_deep_dive_table


def _write_package(root: Path) -> Path:
    package = root / "sample"
    (package / "tables").mkdir(parents=True)
    (package / "tables" / "comparison.csv").write_text(
        'Nome,FIDC A,FIDC B\nPL,R$ 100 mm,R$ 200 mm\nNPL Over 90,"1,0%","2,0%"\n',
        encoding="utf-8",
    )
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "deep_dive_id": "sample",
                "title": "Deep Dive Teste",
                "subtitle": "Comparativo",
                "generated_at": "2026-05-13T10:00:00-03:00",
                "source": "teste",
                "funds": [{"cnpj": "00.000.000/0001-00", "name": "FIDC A", "short_name": "FIDC A"}],
                "tables": [
                    {
                        "id": "comparison",
                        "title": "Comparativo",
                        "source_file": "tables/comparison.csv",
                        "first_column": "Nome",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return package


def test_deep_dive_store_loads_manifest_and_table(tmp_path: Path) -> None:
    _write_package(tmp_path)
    manifests = list_deep_dives(tmp_path)
    assert len(manifests) == 1
    assert manifests[0].title == "Deep Dive Teste"

    frame = load_deep_dive_table(manifests[0], manifests[0].tables[0])
    assert list(frame.columns) == ["Nome", "FIDC A", "FIDC B"]
    assert frame.iloc[0]["FIDC A"] == "R$ 100 mm"


def test_deep_dive_pptx_is_editable_office_package(tmp_path: Path) -> None:
    _write_package(tmp_path)
    manifest = list_deep_dives(tmp_path)[0]
    frame = pd.DataFrame({"Nome": ["PL", "NPL"], "FIDC A": ["R$ 100 mm", "1,0%"], "FIDC B": ["R$ 200 mm", "2,0%"]})
    pptx = build_deep_dive_pptx_bytes(manifest, [(manifest.tables[0], frame)], highlighted_column="FIDC B")

    assert pptx.startswith(b"PK")
    path = tmp_path / "out.pptx"
    path.write_bytes(pptx)
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "ppt/presentation.xml" in names
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "Deep Dive Teste" in slide_xml
        assert "R$ 100 mm" in slide_xml
