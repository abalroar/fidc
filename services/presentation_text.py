"""Portable public copy; documentary evidence remains unchanged on disk."""
from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from zipfile import ZipFile


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


_PERSONAL_PATH = re.compile(r"(?:file://)?(?:/?(?:Users|home)/[^/\s]+/[^\s<>\"'|;,)]*|[A-Za-z]:[\\/]Users[\\/][^\s<>\"'|;,)]+)")
_SUPPLIED_REFERENCE = re.compile(
    r"\b(?:img_\d+\.(?:jpe?g|png)|(?:foto|fotografia|imagem|material|tabela|quadro)\s+(?:do usuario|da imagem|de referencia|enviad[oa]|fornecid[oa]|anexad[oa]|extern[oa])|(?:auto\s*iv|proposta)\s+(?:da|na)\s+(?:foto|imagem))\b"
)
_REFERENCE_CUE = re.compile(r"img_\d+|(?:foto|fotografia|imagem|material|tabela|quadro)\s+(?:do usu|de refer|envi|forneci|anexa|extern)|(?:auto\s*iv|proposta)\s+(?:da|na)\s+(?:foto|imagem)", re.I)
_MISSING = re.compile(
    r"\b(?:nao\s+(?:localizad[oa]s?|identificad[oa]s?|confirmad[oa]s?|disponive[li]s?|informad[oa]s?|extraid[oa]s?|verificad[oa]s?|determinad[oa]s?|preenchid[oa]s?|certificad[oa]s?|transcrit[oa]s?|individualizad[oa]s?|segregad[oa]s?|explicitad[oa]s?|especificad[oa]s?|recuperave[li]s?|acessive[li]s?|obtido|obtida)"
    r"|sem\s+(?:competencia|dados|informacao|informacoes|documento|documentos|corpus|evidencia|texto extraivel|acesso|proxy|metrica|spread final|calendario preenchido))\b"
)
_REQUEST = re.compile(r"^(?:conferir|confirmar|consultar|obter|validar|requer|depende|dependente|aguarda|a confirmar|a localizar|pendente|pendencia|lacuna|pdf sem texto|http\s*\d|erro de acesso|acesso bloqueado|timeout)\b")
_REFERENCE = re.compile(r"\b(?:suplementos?|apensos?|apendices?|anexos?|regulamentos?|contratos?|atos?|bookbuilding|cccb|ccb)\b")
_REMISSION_START = re.compile(r"^(?:remetid[oa]s?|remissao|conforme|segundo|vide|ver|nos termos|de acordo|definid[oa]s?|estabelecid[oa]s?|previst[oa]s?|fixad[oa]s?|determinad[oa]s?)\b|^(?:(?:senior|mezanino|junior)\s*:\s*)?(?:di|cdi|ipca)\s*\+\s*(?:spread|sobretaxa)\b")
_REFERENCE_SUBJECT = re.compile(r"^(?:(?:senior|mezanino|junior|\d+[aªº]?\s*serie)\s*:\s*)?(?:prazos?|taxas?|remuneracao|sobretaxa|spread|fator|cronograma|amortizacao|juros|pagamentos|calendario|carencia|vencimento|percentual|minimo|limites?|condicoes|termos|datas?|benchmark|vnu|principal|investimento|series?|suplementos?|apensos?|apendices?|anexos?|regulamentos?|metas?|indice|politica de provisao|por apendice|por suplemento|modelos?)\b")
_VALUE = re.compile(r"\d\s*(?:%|a\.a\.|a\.m\.|dias?|du\b|d\.u\.|meses|anos?|parcelas?|mil|mi\b)|[≥≤<>]=?\s*\d|r\$|\b(?:di|cdi|ipca)\s*\+\s*\d|\d{2}/\d{2}/\d{4}")
_QUALIFICATION = re.compile(r"diverg|inconsisten|por extenso|numeral|indicativ|historico|aprovad|autorizacao|regulamento de\s*\d{4}")
_SUBSTANTIVE = re.compile(r"\b(?:mensal|trimestral|semestral|anual|vedad[oa]s?|permitid[oa]s?|sem coobrigacao|sem carencia|sem revolvencia|sem benchmark|nao aplicavel|residual|incluid[oa]|integrada|prioridade|waterfall|liquidacao|hedge|cessao fiduciaria|alienacao fiduciaria|pl da classe|patrimonio liquido|profissionais|qualificados|opcoes)\b")


def public_document_text(value: object) -> str:
    """Keep primary citations while removing personal paths and supplied-photo copy."""
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    # A supplied image is a private working reference, never a published source.
    if _REFERENCE_CUE.search(text):
        parts = text.split("\n")
        text = "\n".join(part for part in parts if not _SUPPLIED_REFERENCE.search(_fold(part)))

    def portable(match: re.Match[str]) -> str:
        path = match.group(0).replace("\\", "/").rstrip("./")
        for marker in ("/data/", "/reports/"):
            if marker in path:
                return marker.lstrip("/") + path.split(marker, 1)[1]
        return path.rsplit("/", 1)[-1]

    return _PERSONAL_PATH.sub(portable, text).strip()


def document_comparison_value(value: object) -> str:
    """Use '-' for unanswered clauses, retaining actual rules, conditions and zero."""
    text = public_document_text(value)
    if _fold(text) in {"", "-", "—", "–", "nan", "none", "<na>", "n/d", "n/a"}:
        return "-"
    # Decimal rates and dates are not sentence delimiters.
    parts = re.split(r";\s*|\n|(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕ]|\d{2}/\d{2}/\d{4}\b)|(?<=[a-záéíóúãõ])\.(?=\d{2}/\d{2}/\d{4})|,\s+(?=(?:com\s+)?(?:volume|VNU|fator específico|mínimo|tarifa|rateio|integralização|vigência atual)\b)", text)
    kept = []
    revised = False
    for part in parts:
        part = part.strip()
        folded = re.sub(r"\b(em|ao|aos|por|no|nos)(?=(?:suplement|apend|anex))", r"\1 ", _fold(part))
        if re.search(r"inacessiv.*http|\bhttp\s*520|\breferencias genericas nao autorizam conclusao", folded):
            continue
        historical = re.search(r"regulamento de (\d{4})", folded)
        if kept and historical and folded.startswith("suplementos preenchidos"):
            kept[-1] += f" (regulamento de {historical.group(1)})"
            revised = True
            continue
        if "apos carencia" in folded and re.search(r"segue item .*regulamento ausente", folded):
            part = re.split(r"\s+segue item\b", part, flags=re.I)[0]
            folded = _fold(part)
            revised = True
        if not part or _MISSING.search(folded) or (_REQUEST.search(folded) and not _QUALIFICATION.search(folded)):
            continue
        if _REQUEST.search(folded) and _QUALIFICATION.search(folded):
            part = re.sub(r"^(?:Confirmar|Validar|Conferir)\s+", "", part, flags=re.I)
            part = part[:1].upper() + part[1:]
            revised = True
        if re.match(r"^suplementos? (?:de )?\d{2}/\d{2}/\d{4} referid", folded):
            continue
        if _REFERENCE.search(folded) and (_REMISSION_START.search(folded) or _REFERENCE_SUBJECT.search(folded)) and not (_VALUE.search(folded) or _SUBSTANTIVE.search(folded) or _QUALIFICATION.search(folded)):
            continue
        if folded.startswith(("sobretaxa definida em bookbuilding", "spread definido em bookbuilding")):
            continue
        kept.append(part)
    if len(kept) == len(parts) and not revised:
        return text
    for index in range(len(kept) - 1):
        if not re.search(r"\b(?:a\.a\.|a\.m\.|art\.|p\.)$", kept[index], re.I):
            kept[index] = kept[index].removesuffix(".")
    return "; ".join(kept) or "-"


def public_pptx_bytes(payload: bytes) -> bytes:
    """Remove private reference text at the last export boundary, preserving parts."""
    from lxml import etree

    changes = {}
    with ZipFile(BytesIO(payload)) as archive:
        for info in archive.infolist():
            if not info.filename.endswith((".xml", ".rels")):
                continue
            data = archive.read(info)
            xml_text = data.decode("utf-8", errors="ignore")
            if not (_PERSONAL_PATH.search(xml_text) or _REFERENCE_CUE.search(xml_text)):
                continue
            root = etree.fromstring(data)
            changed = False
            for paragraph in root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}p"):
                runs = paragraph.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t")
                original = "".join(run.text or "" for run in runs)
                clean = public_document_text(original)
                if runs and clean != original:
                    runs[0].text = clean
                    for run in runs[1:]:
                        run.text = ""
                    changed = True
            for node in root.iter():
                if node.text and _PERSONAL_PATH.search(node.text):
                    node.text = public_document_text(node.text)
                    changed = True
                for key, value in list(node.attrib.items()):
                    if _PERSONAL_PATH.search(value):
                        node.set(key, public_document_text(value))
                        changed = True
            if changed:
                changes[info.filename] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        if not changes:
            return payload
        output = BytesIO()
        with ZipFile(output, "w") as target:
            for info in archive.infolist():
                target.writestr(info, changes.get(info.filename, archive.read(info)))
        return output.getvalue()
