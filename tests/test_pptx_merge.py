from __future__ import annotations

from io import BytesIO
import posixpath
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree
from openpyxl import load_workbook
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
import pytest

from services.pptx_merge import PptxMergeError, merge_pptx_bytes


def _native_deck_bytes(
    *,
    slide_title: str,
    chart_title: str,
    chart_values: tuple[float, float],
    include_table: bool = False,
    width_inches: float = 13.333,
) -> bytes:
    presentation = Presentation()
    presentation.slide_width = Inches(width_inches)
    presentation.slide_height = Inches(7.5)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Inches(0.4), Inches(0.2), Inches(5), Inches(0.4)).text = slide_title

    chart_data = CategoryChartData()
    chart_data.categories = ["jan/26", "fev/26"]
    chart_data.add_series(chart_title, chart_values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.4),
        Inches(0.9),
        Inches(6),
        Inches(4),
        chart_data,
    ).chart
    chart.has_title = True
    chart.chart_title.text_frame.text = chart_title

    if include_table:
        table = slide.shapes.add_table(
            2,
            2,
            Inches(7.0),
            Inches(0.9),
            Inches(5.5),
            Inches(1.2),
        ).table
        table.cell(0, 0).text = "Escopo"
        table.cell(0, 1).text = "Valor"
        table.cell(1, 0).text = "Fundo B"
        table.cell(1, 1).text = "12,34%"

    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_merge_pptx_bytes_preserves_native_charts_tables_and_embedded_workbooks() -> None:
    primary = _native_deck_bytes(
        slide_title="Deck principal",
        chart_title="Gráfico principal",
        chart_values=(1.0, 2.0),
    )
    appendix = _native_deck_bytes(
        slide_title="Deck complementar",
        chart_title="Gráfico complementar",
        chart_values=(10.0, 20.0),
        include_table=True,
    )

    merged = merge_pptx_bytes(primary, appendix)

    presentation = Presentation(BytesIO(merged))
    assert len(presentation.slides) == 2
    assert "Deck principal" in "\n".join(
        shape.text for shape in presentation.slides[0].shapes if hasattr(shape, "text")
    )
    assert "Deck complementar" in "\n".join(
        shape.text for shape in presentation.slides[1].shapes if hasattr(shape, "text")
    )
    assert sum(bool(getattr(shape, "has_chart", False)) for shape in presentation.slides[0].shapes) == 1
    assert sum(bool(getattr(shape, "has_chart", False)) for shape in presentation.slides[1].shapes) == 1
    tables = [shape.table for shape in presentation.slides[1].shapes if getattr(shape, "has_table", False)]
    assert len(tables) == 1
    assert tables[0].cell(1, 0).text == "Fundo B"

    with ZipFile(BytesIO(merged)) as archive:
        chart_parts = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/charts/chart") and name.endswith(".xml")
        )
        workbook_parts = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/embeddings/") and name.endswith(".xlsx")
        )
        slide_two_relationships = archive.read("ppt/slides/_rels/slide2.xml.rels").decode("utf-8")
        workbook_values = [
            load_workbook(BytesIO(archive.read(name)), data_only=False).active["B2"].value
            for name in workbook_parts
        ]

    assert len(chart_parts) == 2
    assert len(workbook_parts) == 2
    assert sorted(workbook_values) == [1.0, 10.0]
    assert "/chart" in slide_two_relationships
    assert "slideLayout" in slide_two_relationships

    # A second Office-package round trip must keep both native objects intact.
    roundtrip = BytesIO()
    presentation.save(roundtrip)
    reopened = Presentation(BytesIO(roundtrip.getvalue()))
    assert len(reopened.slides) == 2
    assert any(getattr(shape, "has_table", False) for shape in reopened.slides[1].shapes)
    assert any(getattr(shape, "has_chart", False) for shape in reopened.slides[1].shapes)


def test_merge_pptx_bytes_rejects_different_slide_sizes() -> None:
    primary = _native_deck_bytes(
        slide_title="Principal",
        chart_title="A",
        chart_values=(1.0, 2.0),
    )
    appendix = _native_deck_bytes(
        slide_title="Apêndice",
        chart_title="B",
        chart_values=(3.0, 4.0),
        width_inches=10.0,
    )

    with pytest.raises(PptxMergeError, match="tamanho de slide diferente"):
        merge_pptx_bytes(primary, appendix)


def test_merge_pptx_bytes_rejects_incompatible_theme_chain() -> None:
    primary = _native_deck_bytes(
        slide_title="Principal",
        chart_title="A",
        chart_values=(1.0, 2.0),
    )
    appendix = _native_deck_bytes(
        slide_title="Apêndice",
        chart_title="B",
        chart_values=(3.0, 4.0),
    )
    mutated = BytesIO()
    with ZipFile(BytesIO(appendix), "r") as source, ZipFile(mutated, "w", compression=ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "ppt/theme/theme1.xml":
                payload = payload.replace(b"Office Theme", b"Merged Theme")
            target.writestr(info, payload)

    with pytest.raises(PptxMergeError, match="layout/master/tema incompatível"):
        merge_pptx_bytes(primary, mutated.getvalue())


def test_merge_pptx_bytes_returns_primary_unchanged_without_appendices() -> None:
    primary = _native_deck_bytes(
        slide_title="Principal",
        chart_title="A",
        chart_values=(1.0, 2.0),
    )

    assert merge_pptx_bytes(primary) == primary


def test_merge_pptx_bytes_rejects_invalid_payload() -> None:
    primary = _native_deck_bytes(
        slide_title="Principal",
        chart_title="A",
        chart_values=(1.0, 2.0),
    )

    with pytest.raises(PptxMergeError, match="não é um PPTX válido"):
        merge_pptx_bytes(primary, b"not-a-pptx")


_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _noted_deck(title: str) -> bytes:
    payload = _native_deck_bytes(slide_title=title, chart_title=f"PL {title}", chart_values=(0.0, 12.3), include_table=True)
    prs = Presentation(BytesIO(payload))
    prs.slides[0].notes_slide.notes_text_frame.text = f"Fonte {title}\nCNPJ 00000000000100\nPL: zero válido e 12,3\nRessalva integral {title}"
    output = BytesIO(); prs.save(output)
    return output.getvalue()


def _rewrite_package(payload, transform):
    with ZipFile(BytesIO(payload)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    transform(files)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
        for name, content in files.items(): target.writestr(name, content)
    return output.getvalue()


def _assert_single_notes_master(payload):
    with ZipFile(BytesIO(payload)) as archive:
        parts = set(archive.namelist())
        master_paths = [path for path in parts if path.startswith("ppt/notesMasters/") and path.endswith(".xml")]
        assert len(master_paths) == 1
        presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
        ids = presentation.findall(f"{{{_P}}}notesMasterIdLst/{{{_P}}}notesMasterId")
        assert len(ids) == 1
        relations = etree.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        master_relations = [node for node in relations if node.get("Type") == f"{_R}/notesMaster"]
        assert len(master_relations) == 1
        assert ids[0].get(f"{{{_R}}}id") == master_relations[0].get("Id")
        assert "ppt/" + master_relations[0].get("Target") == master_paths[0]
        for path in parts:
            if not path.endswith(".rels"):
                continue
            owner = "" if path == "_rels/.rels" else posixpath.join(posixpath.dirname(posixpath.dirname(path)), posixpath.basename(path)[:-5])
            for node in etree.fromstring(archive.read(path)):
                if node.get("TargetMode") == "External": continue
                target = node.get("Target", "")
                resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))
                assert resolved in parts
                if node.get("Type") == f"{_R}/notesMaster":
                    assert resolved == master_paths[0]
        overrides = [node.get("PartName") for node in etree.fromstring(archive.read("[Content_Types].xml")) if node.tag == f"{{{_CT}}}Override"]
        assert all(name.lstrip("/") in parts for name in overrides)


def test_merge_shares_one_compatible_notes_master_and_retains_all_notes_native_parts_and_relationships():
    first, second = _noted_deck("A"), _noted_deck("B")
    result = merge_pptx_bytes(first, second)
    _assert_single_notes_master(result)
    prs = Presentation(BytesIO(result))
    assert [slide.notes_slide.notes_text_frame.text for slide in prs.slides] == [Presentation(BytesIO(payload)).slides[0].notes_slide.notes_text_frame.text for payload in (first, second)]
    protected = ("ppt/charts/", "ppt/embeddings/", "ppt/slideMasters/", "ppt/slideLayouts/", "ppt/fonts/")
    with ZipFile(BytesIO(result)) as destination:
        available = [destination.read(path) for path in destination.namelist() if path.startswith(protected)]
        for payload in (first, second):
            with ZipFile(BytesIO(payload)) as source:
                for path in source.namelist():
                    if path.startswith(protected): assert source.read(path) in available
    assert len(prs.slides) == 2
    assert [list(shape.chart.series[0].values) for slide in prs.slides for shape in slide.shapes if shape.has_chart] == [[0.0, 12.3], [0.0, 12.3]]


def test_merge_without_appendices_preserves_a_valid_single_notes_master_payload():
    primary = _noted_deck("A")
    assert merge_pptx_bytes(primary) == primary


def test_merge_accepts_equivalent_notes_chain_with_different_local_relationship_ids():
    first = _noted_deck("A")
    def rename_id(files):
        path = "ppt/notesMasters/_rels/notesMaster1.xml.rels"
        root = etree.fromstring(files[path])
        root[0].set("Id", "rIdTheme999")
        root[0].set("TargetMode", "Internal")
        files[path] = etree.tostring(root)
    second = _rewrite_package(_noted_deck("B"), rename_id)
    result = merge_pptx_bytes(first, second)
    _assert_single_notes_master(result)
    assert "Ressalva integral B" in Presentation(BytesIO(result)).slides[1].notes_slide.notes_text_frame.text


@pytest.mark.parametrize("change", ["master", "theme", "image", "url"])
def test_merge_rejects_incompatible_notes_chain_even_when_main_master_xml_is_equal(change):
    first = _noted_deck("A")
    def related_content(files, value):
        path = "ppt/notesMasters/_rels/notesMaster1.xml.rels"
        root = etree.fromstring(files[path])
        node = etree.SubElement(root, f"{{{_REL}}}Relationship", Id="rIdAdditional")
        node.set("Type", f"{_R}/image" if change == "image" else f"{_R}/hyperlink")
        if change == "url":
            node.set("TargetMode", "External"); node.set("Target", value)
        else:
            node.set("Target", "../media/notes-asset.png")
            files["ppt/media/notes-asset.png"] = value
            types = etree.fromstring(files["[Content_Types].xml"])
            etree.SubElement(types, f"{{{_CT}}}Default", Extension="png", ContentType="image/png")
            files["[Content_Types].xml"] = etree.tostring(types)
        files[path] = etree.tostring(root)
    if change in {"image", "url"}:
        first = _rewrite_package(first, lambda files: related_content(files, b"original-native-note-asset" if change == "image" else "https://example.com/original-notes-source"))
    def incompatible(files):
        if change == "master":
            root = etree.fromstring(files["ppt/notesMasters/notesMaster1.xml"])
            root.find(f"{{{_P}}}cSld").set("name", "Different notes template")
            files["ppt/notesMasters/notesMaster1.xml"] = etree.tostring(root)
        elif change == "theme":
            files["ppt/theme/theme2.xml"] = files["ppt/theme/theme2.xml"].replace(b"Calibri", b"Arial")
        else:
            related_content(files, b"distinct-native-note-asset" if change == "image" else "https://example.com/different-notes-source")
    second = _rewrite_package(_noted_deck("B"), incompatible)
    with pytest.raises(PptxMergeError, match="Notes masters incompatíveis"):
        merge_pptx_bytes(first, second)


def test_notes_signature_resolves_xml_hyperlink_ids_to_identical_external_content():
    def linked(files, relationship_id):
        path = "ppt/notesMasters/_rels/notesMaster1.xml.rels"
        relations = etree.fromstring(files[path])
        etree.SubElement(relations, f"{{{_REL}}}Relationship", Id=relationship_id, Type=f"{_R}/hyperlink", Target="https://example.com/same-notes-source", TargetMode="External")
        files[path] = etree.tostring(relations)
        master = etree.fromstring(files["ppt/notesMasters/notesMaster1.xml"])
        properties = master.find(f".//{{{_P}}}cNvPr")
        link = etree.SubElement(properties, "{http://schemas.openxmlformats.org/drawingml/2006/main}hlinkClick")
        link.set(f"{{{_R}}}id", relationship_id)
        files["ppt/notesMasters/notesMaster1.xml"] = etree.tostring(master)
    first = _rewrite_package(_noted_deck("A"), lambda files: linked(files, "rIdNotesLinkA"))
    second = _rewrite_package(_noted_deck("B"), lambda files: linked(files, "rIdNotesLinkB"))
    result = merge_pptx_bytes(first, second)
    _assert_single_notes_master(result)
    with ZipFile(BytesIO(result)) as archive:
        rels = etree.fromstring(archive.read("ppt/notesMasters/_rels/notesMaster1.xml.rels"))
        assert any(node.get("Target") == "https://example.com/same-notes-source" for node in rels)


def test_merger_can_normalize_compatible_legacy_duplicates_without_appendices():
    primary = _noted_deck("A")
    def legacy_duplicate(files):
        files["ppt/notesMasters/notesMaster2.xml"] = files["ppt/notesMasters/notesMaster1.xml"]
        files["ppt/notesMasters/_rels/notesMaster2.xml.rels"] = files["ppt/notesMasters/_rels/notesMaster1.xml.rels"]
        types = etree.fromstring(files["[Content_Types].xml"])
        etree.SubElement(types, f"{{{_CT}}}Override", PartName="/ppt/notesMasters/notesMaster2.xml", ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml")
        files["[Content_Types].xml"] = etree.tostring(types)
    legacy = _rewrite_package(primary, legacy_duplicate)
    result = merge_pptx_bytes(legacy)
    _assert_single_notes_master(result)
    assert Presentation(BytesIO(result)).slides[0].notes_slide.notes_text_frame.text == Presentation(BytesIO(primary)).slides[0].notes_slide.notes_text_frame.text
