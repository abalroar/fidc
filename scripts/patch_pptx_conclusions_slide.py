#!/usr/bin/env python3
"""Insere o slide "Principais Conclusões" em um deck executivo da indústria de FIDCs.

O slide entra após "OFERTAS ENCERRADAS · ORIGINADORES NOMINÁVEIS" (posição 27) e os
números de página impressos nos slides seguintes são incrementados. O conteúdo espelha
o bloco "27. Principais conclusões" de scripts/build_fidc_revision_artifacts.mjs; este
script existe para aplicar o mesmo slide a decks já gerados quando o runtime do
@oai/artifact-tool não está disponível.

Uso:
    python3 scripts/patch_pptx_conclusions_slide.py entrada.pptx saida.pptx
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

EMU = 9525  # EMU por pixel a 96 dpi (grade usada pelo deck: 1280x720 px)
NS = (
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
)
SLIDE_CT = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
LAYOUT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
SLIDE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"

C_ORANGE = "EC7000"
C_BLACK = "151515"
C_MID = "73787D"
C_NOTE = "8D9399"
C_LINE = "D7DADD"

INSERT_AFTER_POSITION = 26  # slide "Originadores nomináveis"; o novo slide vira o 27
PAGE_SHAPE_X = 1170 * EMU   # âncora do número de página no rodapé

TITLE = (
    "Varejo ainda marginal, serviços verticalizados e originação em alta; "
    "gestão é a função menos concentrada"
)
SOURCE = (
    "Fonte: CVM, ANBIMA e FundosNet; mai/26, salvo ofertas até 17/jul/26. "
    "Métricas detalhadas nos slides anteriores e no apêndice."
)
CONCLUSIONS = [
    (
        "DISTRIBUIÇÃO · RCVM 175",
        "A abertura ao varejo ainda não mudou o perfil da demanda",
        "Ticket médio de R$ 82,7 mi (mediana R$ 21,6 mi) em 2026, PF com 4,2% do volume "
        "colocado e 59% dos fundos acima de R$ 200 mi com até 10 contas: o FIDC segue "
        "veículo de captação institucional, não produto de prateleira.",
    ),
    (
        "FUNÇÕES · CONCENTRAÇÃO",
        "Gestão é a atividade menos concentrada",
        "O Top 10 da gestão detém 35,7% do PL ex-FIC em mai/26, contra 71,8% na "
        "administração e 72,8% na custódia; no Top 5, 24,2% contra cerca de 50%. É a "
        "camada com maior espaço para casas independentes.",
    ),
    (
        "VERTICALIZAÇÃO",
        "Administração e custódia andam juntas em 87,4% do PL",
        "3.702 fundos (87,7% do total) mantêm as duas funções no mesmo conglomerado em "
        "mai/26: 53,4% do PL bruto com gestor terceiro e 34,0% em monoestruturas, com "
        "as três funções internalizadas.",
    ),
    (
        "COMBO COMPLETO",
        "BTG é o banco que mais oferta o pacote adm + gestão + custódia",
        "São 73 FIDCs monoestrutura (R$ 67,7 bi) em mai/26; excluídos os 6 FIDCs "
        "proprietários consolidados na DF 1T26 (R$ 28,6 bi), restam 67 FIDCs de "
        "terceiros com o combo completo (R$ 39,0 bi).",
    ),
    (
        "INDEPENDENTES",
        "Independentes lideram administração e custódia",
        "QI Tech é nº 1 geral em administração (R$ 122,5 bi) e custódia (R$ 120,6 bi) — "
        "escala herdada da Singulare; Oliveira Trust é a maior gestora independente "
        "(R$ 34,0 bi, nº 3 geral). Na CBSF, em liquidação desde jan/26, 19% do PL "
        "continuante já migrou.",
    ),
    (
        "ORIGINAÇÕES",
        "O ritmo de emissão segue no maior nível da série",
        "841 ofertas encerradas somam R$ 69,6 bi em 2026 até 17/jul; jan–mai registra "
        "R$ 51,5 bi, +15% sobre 2025 e +45% sobre 2024. CloudWalk fez a maior oferta "
        "única do ano (R$ 5,5 bi).",
    ),
    (
        "ROUBA-MONTE",
        "Trocas de administrador movem pouco: 7,2% do estoque",
        "257 FIDCs mudaram de administrador entre dez/24 e dez/25 (R$ 33,0 bi "
        "comparáveis). O maior fluxo bilateral foi Cielo: Oliveira Trust → Bradesco, "
        "R$ 8,9 bi; movimentos relevantes seguem eventos societários. Gestão e "
        "custódia não têm série observável.",
    ),
    (
        "QUALIDADE DO DADO",
        "A leitura fina da indústria ainda exige curadoria documental",
        "Outros concentra 41,7% do PL ex-FIC na taxonomia ANBIMA e 197 veículos "
        "reportam inadimplência acima da carteira (cap de R$ 14,6 bi); a classificação "
        "oficial não descreve o lastro dos maiores fundos.",
    ),
]

_shape_id = 100


def _next_id() -> int:
    global _shape_id
    _shape_id += 1
    return _shape_id


def text_shape(text, x, y, w, h, size_pt_100, color, *, bold=False, anchor="t",
               align="l", line_spacing=100000):
    bold_attr = ' b="1"' if bold else ""
    rpr = (
        f'sz="{size_pt_100}"{bold_attr}'
        f'><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        '<a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/>'
    )
    sid = _next_id()
    return (
        f'<p:sp {NS}><p:nvSpPr><p:cNvPr id="{sid}" name="Rectangle {sid}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x * EMU}" y="{y * EMU}"/>'
        f'<a:ext cx="{w * EMU}" cy="{h * EMU}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
        '<a:ln w="0"><a:noFill/><a:prstDash val="solid"/></a:ln></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" '
        f'anchor="{anchor}"><a:normAutofit/></a:bodyPr><a:lstStyle/>'
        f'<a:p><a:pPr algn="{align}"><a:lnSpc><a:spcPct val="{line_spacing}"/></a:lnSpc>'
        f'<a:buNone/><a:defRPr {rpr}</a:defRPr></a:pPr>'
        f'<a:r><a:rPr {rpr}</a:rPr><a:t>{escape(text)}</a:t></a:r></a:p></p:txBody></p:sp>'
    )


def rect_shape(x, y, w, h_emu, color):
    sid = _next_id()
    return (
        f'<p:sp {NS}><p:nvSpPr><p:cNvPr id="{sid}" name="Rectangle {sid}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x * EMU}" y="{y * EMU}"/>'
        f'<a:ext cx="{w * EMU}" cy="{h_emu}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        '<a:ln w="0"><a:noFill/><a:prstDash val="solid"/></a:ln></p:spPr></p:sp>'
    )


def build_slide_xml(page_number: int) -> str:
    shapes = [
        text_shape("PRINCIPAIS CONCLUSÕES", 60, 27, 720, 20, 900, C_ORANGE, bold=True),
        text_shape(TITLE, 60, 53, 1160, 49, 1800, C_BLACK, bold=True, anchor="ctr"),
        rect_shape(60, 110, 1160, EMU, C_LINE),
        rect_shape(60, 667, 1160, EMU, C_LINE),
        text_shape(SOURCE, 60, 674, 1050, 18, 788, C_NOTE, anchor="ctr"),
        text_shape(str(page_number), 1170, 673, 50, 18, 788, C_NOTE, anchor="ctr", align="r"),
    ]
    for index, (kicker, claim, detail) in enumerate(CONCLUSIONS):
        x = 60 if index < 4 else 660
        y = 128 + (index % 4) * 132
        shapes.append(text_shape(kicker, x, y, 560, 16, 825, C_ORANGE, bold=True))
        shapes.append(text_shape(claim, x, y + 20, 560, 22, 1125, C_BLACK, bold=True))
        shapes.append(
            text_shape(detail, x, y + 44, 560, 68, 975, C_MID, line_spacing=105000)
        )
        if index % 4 < 3:
            shapes.append(rect_shape(x, y + 122, 560, 7144, C_LINE))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f"<p:sld {NS}><p:cSld><p:bg><p:bgPr><a:solidFill>"
        '<a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
        '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        "</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
        '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
        "</a:xfrm></p:grpSpPr>"
        + "".join(shapes)
        + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )


def slide_order(root: Path) -> list[tuple[str, str]]:
    """Retorna [(r_id, caminho relativo do slide)] na ordem do sldIdLst."""
    rels = (root / "ppt/_rels/presentation.xml.rels").read_text(encoding="utf-8-sig")
    targets = {}
    for match in re.finditer(r"<Relationship\b[^>]*/>", rels):
        chunk = match.group(0)
        rid = re.search(r'Id="([^"]+)"', chunk).group(1)
        target = re.search(r'Target="([^"]+)"', chunk).group(1)
        if re.search(r"slides/slide\d+\.xml$", target):
            normalized = target.lstrip("/")
            if normalized.startswith("ppt/"):
                normalized = normalized[len("ppt/"):]
            targets[rid] = normalized
    presentation = (root / "ppt/presentation.xml").read_text(encoding="utf-8-sig")
    order = []
    for match in re.finditer(r'<p:sldId\b[^>]*\br:id="([^"]+)"[^>]*/>', presentation):
        rid = match.group(1)
        if rid in targets:
            order.append((rid, targets[rid]))
    return order


def patch(input_path: Path, output_path: Path) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="conclusoes_"))
    try:
        with zipfile.ZipFile(input_path) as archive:
            names = archive.namelist()
            archive.extractall(workdir)

        order = slide_order(workdir)
        if len(order) < INSERT_AFTER_POSITION:
            raise SystemExit(f"Deck tem {len(order)} slides; esperado >= {INSERT_AFTER_POSITION}.")
        anchor_rid, anchor_target = order[INSERT_AFTER_POSITION - 1]
        anchor_xml = (workdir / "ppt" / anchor_target).read_text(encoding="utf-8-sig")
        if "ORIGINADORES NOMIN" not in anchor_xml:
            raise SystemExit(
                f"Slide {INSERT_AFTER_POSITION} ({anchor_target}) não é o de originadores; abortando."
            )
        for _, target in order:
            if "PRINCIPAIS CONCLUS" in (workdir / "ppt" / target).read_text(encoding="utf-8-sig"):
                raise SystemExit("O deck já contém o slide de Principais Conclusões; abortando.")

        max_slide = max(
            int(re.search(r"slide(\d+)\.xml$", target).group(1)) for _, target in order
        )
        new_name = f"slide{max_slide + 1}.xml"
        new_page = INSERT_AFTER_POSITION + 1

        (workdir / "ppt/slides" / new_name).write_text(
            build_slide_xml(new_page), encoding="utf-8"
        )

        # rels do novo slide: aponta para o mesmo layout do slide âncora
        anchor_rels_path = workdir / "ppt/slides/_rels" / (Path(anchor_target).name + ".rels")
        layout_target = "../slideLayouts/slideLayout1.xml"
        if anchor_rels_path.exists():
            found = re.search(
                r'Target="([^"]*slideLayouts/slideLayout\d+\.xml)"',
                anchor_rels_path.read_text(encoding="utf-8-sig"),
            )
            if found:
                layout_target = found.group(1)
        (workdir / "ppt/slides/_rels" / f"{new_name}.rels").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{LAYOUT_REL}" Target="{layout_target}"/>'
            "</Relationships>",
            encoding="utf-8",
        )

        # [Content_Types].xml
        ct_path = workdir / "[Content_Types].xml"
        content_types = ct_path.read_text(encoding="utf-8-sig")
        override = f'<Override PartName="/ppt/slides/{new_name}" ContentType="{SLIDE_CT}"/>'
        content_types = content_types.replace("</Types>", override + "</Types>")
        ct_path.write_text(content_types, encoding="utf-8")

        # presentation.xml.rels
        rels_path = workdir / "ppt/_rels/presentation.xml.rels"
        rels = rels_path.read_text(encoding="utf-8-sig")
        new_rid = "rIdConclusoes27"
        if new_rid in rels:
            raise SystemExit("rId do slide de conclusões já existe; abortando.")
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="{new_rid}" Type="{SLIDE_REL}" Target="slides/{new_name}"/>'
            "</Relationships>",
        )
        rels_path.write_text(rels, encoding="utf-8")

        # presentation.xml: insere o sldId após o slide âncora
        presentation_path = workdir / "ppt/presentation.xml"
        presentation = presentation_path.read_text(encoding="utf-8-sig")
        max_sld_id = max(int(m) for m in re.findall(r'<p:sldId\b[^>]*\bid="(\d+)"', presentation))
        anchor_entry = re.search(
            rf'<p:sldId\b[^>]*\br:id="{re.escape(anchor_rid)}"[^>]*/>', presentation
        ).group(0)
        r_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        presentation = presentation.replace(
            anchor_entry,
            anchor_entry + f'<p:sldId id="{max_sld_id + 1}" r:id="{new_rid}" {r_ns}/>',
        )
        presentation_path.write_text(presentation, encoding="utf-8")

        # renumera as páginas impressas dos slides seguintes (27..N -> 28..N+1)
        for position in range(len(order), INSERT_AFTER_POSITION, -1):
            _, target = order[position - 1]
            slide_path = workdir / "ppt" / target
            xml = slide_path.read_text(encoding="utf-8-sig")
            pattern = re.compile(
                rf'(<a:off x="{PAGE_SHAPE_X}"[^>]*>(?:(?!</p:sp>).)*?<a:t[^>]*>)\s*{position}\s*(</a:t>)',
                re.S,
            )
            xml, count = pattern.subn(rf"\g<1>{position + 1}\g<2>", xml, count=1)
            if count != 1:
                raise SystemExit(f"Número de página {position} não encontrado em {target}.")
            slide_path.write_text(xml, encoding="utf-8")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            ordered = names + [
                f"ppt/slides/{new_name}",
                f"ppt/slides/_rels/{new_name}.rels",
            ]
            for name in ordered:
                archive.write(workdir / name, name)
        print(f"OK: {output_path} ({len(order) + 1} slides)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.input.exists():
        sys.exit(f"Arquivo não encontrado: {args.input}")
    patch(args.input, args.output)


if __name__ == "__main__":
    main()
