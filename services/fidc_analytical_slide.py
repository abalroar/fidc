"""Native IBBA-style FIDC analytical slides and auditable Excel workbook."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import textwrap
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from pptx.util import Inches, Pt

from services.bba_deck import GRAY_100, GRAY_500, GRAY_700, ORANGE, Deck, fmt_mm
from services.fund_name_display import short_fund_name
from services.presentation_text import public_document_text
from services.regulatory_profiles import load_regulatory_profile


ROOT = Path(__file__).resolve().parents[1]
VEHICLE_MONTHLY = ROOT / "data/industry_study/vehicle_monthly.csv.gz"
RDB_EVIDENCE = ROOT / "data/regulatory_profiles/meutudo_ago26_rdb_evidence.csv"


@dataclass
class Issuance:
    date: str
    series: str
    quota_class: str
    volume_mm: float | None
    remuneration: str
    amortization: str
    source: str


@dataclass
class FidcSlideData:
    name: str
    cnpj: str
    competence: str = "N/D"
    classification: str = "N/D"
    pl_mm: float | None = None
    receivables_pct_pl: float | None = None
    senior_pct_pl: float | None = None
    subordinated_pct_pl: float | None = None
    identified_issuance_volume_mm: float | None = None
    first_issuance: str = "N/D"
    last_issuance: str = "N/D"
    minimum_subordination: str = "N/D"
    issuances: list[Issuance] = field(default_factory=list)
    rdb_status: str = "Não localizado"
    rdb_finding: str = "N/D"
    rdb_source: str = "N/D"
    validations: list[str] = field(default_factory=list)


def normalize_cnpj(value: object) -> str:
    return re.sub(r"\D", "", str(value or "")).zfill(14)


def _display(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else "N/D"


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _money_mm(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    # A number starts with a digit; a lone "." (e.g. "...") is not a volume.
    match = re.search(r"(?:R\$\s*)?(\d[\d\.]*(?:,\d+)?)", text)
    if not match:
        return None
    number = float(match.group(1).replace(".", "").replace(",", "."))
    return number / 1_000_000


def _date(value: object) -> pd.Timestamp | None:
    parsed = pd.to_datetime(str(value or "").strip(), dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _short_name(name: str) -> str:
    cleaned = re.sub(r"\b(FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS|RESPONSABILIDADE LIMITADA|RESP LIMITADA)\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip(" -")[:56]


def _clean_remuneration(value: object) -> str:
    text = _display(value)
    supported = re.search(r"\b(CDI|DI\s*\+|Taxa DI|IPCA|IGP-M|prefixad|residual|conforme (?:boletim|suplemento|regulamento)|não aplicável|N/D)\b", text, re.I)
    return text if supported and len(text) <= 180 else "N/D — texto extraído sem associação confiável"


# Columns of vehicle_monthly.csv.gz read by build_slide_data.
_VEHICLE_COLUMNS = ("cnpj", "competencia", "denominacao", "classificacao_anbima", "pl", "carteira_dc", "vl_cotas_subordinadas")
_VEHICLE_TEXT_COLUMNS = ("cnpj", "competencia", "denominacao", "classificacao_anbima")
_VEHICLE_CHUNK_ROWS = 50_000


def _vehicle_monthly_rows(cnpjs: set[str]) -> pd.DataFrame:
    """Rows of the requested CNPJs only, with the columns the slide uses.

    The file holds every FIDC since 2013 (~240k rows × ~95 columns). Reading it
    whole costs ~1.5 GB of transient memory per request, enough to kill the
    Streamlit Cloud process. Reading in chunks keeps the peak to one chunk of
    seven columns; rows keep the file order, so the latest-row choice below is
    unchanged.
    """
    path = VEHICLE_MONTHLY
    if not cnpjs or not path.exists():
        return pd.DataFrame()
    header = pd.read_csv(path, nrows=0).columns
    usecols = [column for column in _VEHICLE_COLUMNS if column in header]
    dtype = {column: str for column in _VEHICLE_TEXT_COLUMNS if column in usecols}
    parts = []
    with pd.read_csv(path, usecols=usecols, dtype=dtype, chunksize=_VEHICLE_CHUNK_ROWS) as reader:
        for chunk in reader:
            normalized = chunk["cnpj"].map(normalize_cnpj)
            selected = chunk[normalized.isin(cnpjs)]
            if not selected.empty:
                parts.append(selected.assign(_cnpj=normalized[selected.index]))
    if not parts:
        return pd.DataFrame()
    monthly = pd.concat(parts, ignore_index=True)
    monthly["_date"] = pd.to_datetime(monthly["competencia"], errors="coerce")
    return monthly


def build_slide_data(funds: Iterable[object]) -> list[FidcSlideData]:
    funds = tuple(funds)
    monthly = _vehicle_monthly_rows({normalize_cnpj(getattr(fund, "cnpj", "")) for fund in funds})
    evidence = pd.read_csv(RDB_EVIDENCE, dtype=str, keep_default_na=False) if RDB_EVIDENCE.exists() else pd.DataFrame()
    if not evidence.empty:
        evidence["_cnpj"] = evidence["CNPJ"].map(normalize_cnpj)
    result: list[FidcSlideData] = []
    for fund in funds:
        cnpj = normalize_cnpj(getattr(fund, "cnpj", ""))
        name = _display(getattr(fund, "display_name", ""))
        data = FidcSlideData(name=_short_name(name), cnpj=cnpj)
        rows = monthly[monthly["_cnpj"].eq(cnpj)].sort_values("_date") if not monthly.empty else pd.DataFrame()
        if not rows.empty:
            row = rows.iloc[-1]
            if data.name == "N/D":
                data.name = _short_name(_display(row.get("denominacao")))
            data.competence = row["_date"].strftime("%m/%Y") if not pd.isna(row["_date"]) else _display(row.get("competencia"))
            data.classification = _display(row.get("classificacao_anbima"))
            pl = _number(row.get("pl")); dc = _number(row.get("carteira_dc")); sub = _number(row.get("vl_cotas_subordinadas"))
            data.pl_mm = pl / 1_000_000 if pl is not None else None
            data.receivables_pct_pl = dc / pl if dc is not None and pl else None
            data.subordinated_pct_pl = sub / pl if sub is not None and pl else None
            data.senior_pct_pl = 1 - data.subordinated_pct_pl if data.subordinated_pct_pl is not None else None
        profile = load_regulatory_profile(cnpj)
        if profile is not None and not profile.emissions_df.empty:
            seen: set[tuple[str, str, str, str]] = set()
            for _, row in profile.emissions_df.iterrows():
                date_value = _date(row.get("Data emissão / 1ª integralização")) or _date(row.get("Data deliberação"))
                if profile.profile_type in {"heurístico", "triagem estruturada"}:
                    continue
                series = _display(row.get("Cota/Classe")); volume_text = _display(row.get("Volume")); source = _display(row.get("Fonte"))
                key = (date_value.strftime("%Y-%m-%d") if date_value is not None else "", series.lower(), volume_text, source.split(";")[0])
                if key in seen:
                    continue
                seen.add(key)
                data.issuances.append(Issuance(
                    date=date_value.strftime("%m/%Y") if date_value is not None else "N/D",
                    series=series,
                    quota_class=_display(row.get("Tipo")),
                    volume_mm=_money_mm(row.get("Volume")),
                    remuneration=_clean_remuneration(row.get("Remuneração")),
                    amortization=_display(row.get("Amortização principal")),
                    source=source,
                ))
            dated = [(_date(i.date), i) for i in data.issuances if i.date != "N/D"]
            data.issuances.sort(key=lambda item: (_date(item.date) or pd.Timestamp.max, item.series))
            economic_issuances = [i for i in data.issuances if "evento" not in i.quota_class.lower() and "incorpora" not in i.series.lower() and "cisão" not in i.series.lower()]
            volumes = [i.volume_mm for i in economic_issuances if i.volume_mm is not None]
            data.identified_issuance_volume_mm = sum(volumes) if volumes else None
            valid_dates = sorted(_date(i.date) for i in economic_issuances if i.date != "N/D" and _date(i.date) is not None)
            if valid_dates:
                data.first_issuance, data.last_issuance = valid_dates[0].strftime("%m/%Y"), valid_dates[-1].strftime("%m/%Y")
        if profile is not None and profile.profile_type in {"curado", "curado parcial"} and not profile.criteria_df.empty:
            criteria = profile.criteria_df
            mask = criteria.apply(lambda row: "subord" in " ".join(map(str, row.values)).lower(), axis=1)
            if mask.any():
                data.minimum_subordination = _display(criteria.loc[mask].iloc[0].get("Limite/regra"))
        ev = evidence[evidence["_cnpj"].eq(cnpj)] if not evidence.empty else pd.DataFrame()
        if not ev.empty:
            row = ev.iloc[0]
            data.rdb_status = _display(row.get("Status")); data.rdb_finding = _display(row.get("Achado regulamento"))
            data.rdb_source = f"{_display(row.get('Documento'))} · p. {_display(row.get('Página'))}"
        _validate(data)
        result.append(data)
    return result


def _validate(data: FidcSlideData) -> None:
    if data.senior_pct_pl is not None and data.subordinated_pct_pl is not None:
        if abs(data.senior_pct_pl + data.subordinated_pct_pl - 1) > 0.01:
            data.validations.append("Divergência: sênior + subordinada difere de 100%.")
    if data.pl_mm is None:
        data.validations.append("PL atual indisponível na base mensal.")
    if not data.issuances:
        data.validations.append("Histórico de emissões não reconstruído com confiança.")
    elif any(i.date == "N/D" for i in data.issuances):
        data.validations.append("Há emissões sem data confiável; primeira/última emissão podem ser parciais.")
    if data.rdb_status == "Não localizado":
        data.validations.append("RDB não localizado nos documentos extraídos; ausência não prova inexistência.")


def _pct(value: float | None) -> str:
    return "N/D" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def _money(value: float | None) -> str:
    return "N/D" if value is None else f"R$ {fmt_mm(value)} mm"


def build_fidc_analytical_pptx_bytes(
    funds: Iterable[object], *, portfolio_name: str, generated_at: datetime | None = None,
    compact: bool = False,
) -> bytes:
    funds = list(funds)
    # Presentation names must not change the analytical rows or the Excel data.
    data = build_slide_data(funds)
    legal_names = {
        normalize_cnpj(getattr(fund, "cnpj", "")): _display(getattr(fund, "display_name", ""))
        for fund in funds
    }
    display_data = [
        replace(item, name=_presentation_name(legal_names.get(item.cnpj) or item.name))
        for item in data
    ]
    generated_at = generated_at or datetime.now(ZoneInfo("America/Sao_Paulo"))
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    generation_date = generated_at.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
    deck = Deck("CRÉDITO ESTRUTURADO | CURADORIA DOCUMENTAL")
    all_rdb_missing = compact and bool(display_data) and all(item.rdb_status == "Não localizado" for item in display_data)
    portfolio_rdb_note = (
        f"RDB não localizado em {len(display_data)}/{len(display_data)} fundos nos documentos consultados. "
        "Ausência não prova inexistência; detalhamento integral nas notas."
        if all_rdb_missing else None
    )
    portfolio_rdb_notes = [f"Carteira: {portfolio_name}"]
    if all_rdb_missing:
        portfolio_rdb_notes.append(portfolio_rdb_note)
        for item in display_data:
            portfolio_rdb_notes.extend([
                f"{legal_names.get(item.cnpj, item.name)} · CNPJ {item.cnpj}",
                f"RDB: {item.rdb_status} · {item.rdb_finding} · Fonte: {_public_source(item.rdb_source)}",
            ])
    else:
        _render_rdb_synthesis(deck, display_data, portfolio_name, generation_date=generation_date, legal_names=legal_names)
    for index, item in enumerate(display_data):
        _render_fund_slides(
            deck, item, generation_date=generation_date, legal_name=legal_names.get(item.cnpj, item.name),
            compact=compact, shared_rdb_missing=all_rdb_missing,
            portfolio_rdb_note=portfolio_rdb_note if index == 0 else None,
            portfolio_rdb_notes=portfolio_rdb_notes if index == 0 and all_rdb_missing else (),
        )
    if compact:
        for slide in deck.prs.slides:
            _style_compact_slide(slide)
    from services.presentation_text import public_pptx_bytes
    output = BytesIO(); deck.prs.save(output); return public_pptx_bytes(output.getvalue())


def _presentation_name(value: object) -> str:
    text = _display(value)
    # Use canonical aliases without the helper's fallback character slicing.
    return short_fund_name(text, max_length=max(28, len(text))) or text


def _public_source(value: object) -> str:
    text = public_document_text(value)
    text = re.sub(
        r"(?<![\w:/])(?:\.{1,2}/)?(?:data|reports)/[^\s|;]+",
        lambda match: match.group(0).rsplit("/", 1)[-1],
        text,
    )
    text = re.sub(r"\s*\|\s*(?=\||;|$)", "", text)
    return re.sub(r"\s+", " ", text).strip(" |;")


def _cell_lines(value: object, width: float, size: float) -> list[str]:
    characters = max(10, int((width - .12) * 72 / (size * .53)))
    lines = []
    for paragraph in str(value).splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=characters, break_long_words=False, break_on_hyphens=False) or [""])
    return lines


def _row_height(row: list[str], widths: list[float], size: float) -> float:
    return max(.34, max(len(_cell_lines(value, width, size)) for value, width in zip(row, widths)) * size / 72 * 1.28 + .08)


def _native_readable_table(deck: Deck, slide, rows: list[list[str]], x: float, y: float, widths: list[float], *, size: float, aligns: str) -> float:
    deck.native_table(slide, rows, x, y, widths, row_height=.34, header_height=.34, size=size, aligns=aligns)
    table_shape = slide.shapes[-1]
    # The shared scaffold styles the first paragraph. Continued lines must
    # carry that same font instead of inheriting the Office theme's 18 pt.
    for row_index, row in enumerate(table_shape.table.rows):
        for cell in row.cells:
            reference = cell.text_frame.paragraphs[0]
            reference_font = reference.runs[0].font
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = reference.alignment
                paragraph.space_before = paragraph.space_after = Pt(0)
                paragraph.line_spacing = 1.0
                for run in paragraph.runs:
                    run.font.name = reference_font.name
                    run.font.size = Pt(size - 1 if row_index == 0 else size)
                    run.font.bold = reference_font.bold
                    run.font.color.rgb = reference_font.color.rgb
    for row_index, values in enumerate(rows[1:], 1):
        table_shape.table.rows[row_index].height = Inches(_row_height(values, widths, size))
    table_shape.height = sum(row.height for row in table_shape.table.rows)
    return y + table_shape.height / 914400


def _table_pages(rows: list[list[str]], widths: list[float], *, size: float, maximum_height: float, maximum_rows: int | None = None) -> list[list[list[str]]]:
    pages = []
    page = []
    height = .34
    maximum_lines = max(1, int((maximum_height - .42) / (size / 72 * 1.28)))
    for row in rows:
        lines = [_cell_lines(value, width, size) for value, width in zip(row, widths)]
        # A clause longer than a page continues intact on the next page.
        chunks = max(1, max((len(value) + maximum_lines - 1) // maximum_lines for value in lines))
        for chunk_index in range(chunks):
            chunk = ["\n".join(value[chunk_index * maximum_lines:(chunk_index + 1) * maximum_lines]) for value in lines]
            if chunk_index and len(row) > 1:
                chunk[0] = f"{row[0]} (continuação)"
                if len(chunk) > 1 and not chunk[1]:
                    chunk[1] = row[1]
            row_height = _row_height(chunk, widths, size)
            if page and (height + row_height > maximum_height or (maximum_rows and len(page) >= maximum_rows)):
                pages.append(page); page = []; height = .34
            page.append(chunk); height += row_height
    if page or not pages:
        pages.append(page)
    return pages


def _rdb_conclusion(data: list[FidcSlideData]) -> str:
    if not data:
        return "Sem fundos disponíveis para esta leitura documental."
    counts = Counter(_display(item.rdb_status) for item in data)
    if set(counts) == {"Não localizado"}:
        return "RDB não localizado nos documentos consultados. A ausência de evidência não comprova inexistência."
    states = "; ".join(f"{status}: {count}" for status, count in counts.items())
    return f"Resultado por fundo — {states}. A leitura se limita aos documentos consultados."


def _style_compact_slide(slide) -> None:
    """Apply the portfolio font scale without changing financial text values."""
    for shape in slide.shapes:
        if shape.has_text_frame:
            is_title = .5 <= shape.top / 914400 <= .6
            footer = shape.top / 914400 >= 7
            if is_title:
                shape.top = Inches(.50)
                shape.height = Inches(.60)
            for paragraph in shape.text_frame.paragraphs:
                paragraph.space_before = paragraph.space_after = Pt(0)
                paragraph.line_spacing = 1.0
                for run in paragraph.runs:
                    current_size = run.font.size or paragraph.font.size
                    current = current_size.pt if current_size else 10
                    if footer:
                        size = 9
                    elif is_title:
                        size = 22 if len(shape.text) <= 100 else 13
                    else:
                        size = next((value for value in (10, 11, 13, 22, 32) if value >= current), 32)
                    run.font.name = "Calibri"
                    run.font.size = Pt(size)
                    if footer:
                        run.font.color.rgb = Deck.rgb(GRAY_700)
        if shape.has_table:
            for row_index, row in enumerate(shape.table.rows):
                for cell in row.cells:
                    for paragraph in cell.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run.font.name = "Calibri"
                            run.font.size = Pt(10)
                            if row_index == 0:
                                run.font.color.rgb = Deck.rgb(GRAY_700)


def _control_pages(validations: list[str], *, width: float, height: float) -> list[str]:
    lines = [line for issue in dict.fromkeys(validations) for line in _cell_lines(f"• {issue}", width, 10)]
    maximum_lines = max(1, int(height / (10 / 72 * 1.28)))
    return ["\n".join(lines[start:start + maximum_lines]) for start in range(0, len(lines), maximum_lines)]


def _render_rdb_synthesis(deck: Deck, data: list[FidcSlideData], portfolio_name: str, *, generation_date: str, legal_names: dict[str, str]) -> None:
    widths = [2.95, 1.5, 7.6]
    pages = _table_pages(
        [[_presentation_name(item.name), item.rdb_status, item.rdb_finding] for item in data],
        widths, size=10, maximum_height=4.12,
    )
    for page_index, page in enumerate(pages, 1):
        suffix = f" ({page_index}/{len(pages)})" if len(pages) > 1 else ""
        slide = deck.slide(f"{portfolio_name} | RDB — leitura documental{suffix}")
        deck.text(slide, "Leitura contratual por veículo", .62, 1.34, 4.0, .3, size=12, bold=True)
        _native_readable_table(deck, slide, [["FIDC / classe", "Status", "Leitura"], *page], .62, 1.72, widths, size=10, aligns="lll")
        deck.text(slide, "Conclusão documental", .62, 6.13, 2.0, .24, size=10, color=ORANGE, bold=True)
        deck.text(slide, _rdb_conclusion(data), 2.75, 6.10, 9.92, .52, size=10, color=GRAY_700)
        deck.footer(slide, f"Fundos.NET/B3 · Referências por fundo nas notas. Gerado em {generation_date}.")
        notes = [f"Carteira: {portfolio_name}", f"Geração: {generation_date}", _rdb_conclusion(data)]
        for item in data:
            notes.extend([f"{legal_names.get(item.cnpj, item.name)} · CNPJ {item.cnpj}", f"RDB: {item.rdb_status} · {item.rdb_finding}", f"Fonte: {_public_source(item.rdb_source)}"])
        slide.notes_slide.notes_text_frame.text = "\n".join(notes)


def _render_fund_slides(
    deck: Deck, data: FidcSlideData, *, generation_date: str, legal_name: str,
    compact: bool = False, shared_rdb_missing: bool = False,
    portfolio_rdb_note: str | None = None, portfolio_rdb_notes: Iterable[str] = (),
) -> None:
    table_size = 10 if compact else 9
    table_height = 4.62 if compact else 4.78
    issuance_rows = [[issuance.date, issuance.series, _money(issuance.volume_mm).replace("R$ ", ""), issuance.remuneration] for issuance in data.issuances]
    first_widths = [.65, 2.05, .9, 1.65]
    continued_widths = [.65, 3.0, .9, 4.7]
    first_pages = _table_pages(issuance_rows, first_widths, size=table_size, maximum_height=table_height, maximum_rows=7)
    chunks = [first_pages[0]]
    remaining = [row for group in first_pages[1:] for row in group]
    if remaining:
        chunks.extend(_table_pages(remaining, continued_widths, size=table_size, maximum_height=table_height, maximum_rows=7))
    visible_controls = list(data.validations)
    if compact and shared_rdb_missing:
        visible_controls = [value for value in visible_controls if value != "RDB não localizado nos documentos extraídos; ausência não prova inexistência."]
    control_pages = _control_pages(visible_controls, width=2.53, height=3.1) if compact else []
    extensive_minimum = compact and len(_cell_lines(data.minimum_subordination, 3.73, 11)) > 3
    for page, chunk in enumerate(chunks, 1):
        title = f"{_presentation_name(data.name)} | estrutura e emissões" + (f" ({page}/{len(chunks)})" if len(chunks) > 1 else "")
        slide = deck.slide(title)
        if len(title) > 58:
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text == title:
                    shape.text_frame.paragraphs[0].font.size = Pt(17.5)
        if page == 1:
            snapshot = [
                ["Snapshot", "Valor"], ["PL atual", _money(data.pl_mm)], ["Direitos creditórios / PL", _pct(data.receivables_pct_pl)],
                ["Cotas sênior / PL", _pct(data.senior_pct_pl)], ["Cotas subordinadas / PL", _pct(data.subordinated_pct_pl)],
                ["Volume emitido identificado", _money(data.identified_issuance_volume_mm)], ["Primeira / última emissão", f"{data.first_issuance} / {data.last_issuance}"],
            ]
            if compact:
                _native_readable_table(deck, slide, snapshot, .62, 1.43, [2.18, 1.55], size=10, aligns="lr")
            else:
                deck.native_table(slide, snapshot, .62, 1.43, [2.18, 1.55], row_height=.34, header_height=.34, size=9, aligns="lr")
            deck.text(slide, "Emissões e remuneração", 4.62, 1.40, 4.0, .3, size=11, bold=True)
            x, w = 4.62, 5.25
        else:
            deck.text(slide, "Emissões e remuneração — continuação", .62, 1.40, 5.0, .3, size=11, bold=True)
            x, w = .62, 9.25
        rows = [["Data", "Série / classe", "Volume", "Remuneração"], *chunk]
        if not chunk:
            rows.append(["N/D", "Dados insuficientes para reconstrução", "N/D", "N/D"])
        _native_readable_table(deck, slide, rows, x, 1.76, first_widths if page == 1 else continued_widths, size=table_size, aligns="llrl")
        if page == 1:
            if compact:
                deck.text(slide, "Subordinação mínima", .62, 4.20, 3.73, .24, size=11, color=ORANGE, bold=True)
                minimum = "Regra extensa — leitura integral na continuação e nas notas." if extensive_minimum else data.minimum_subordination
                deck.text(slide, minimum, .62, 4.53, 3.73, .48, size=11, bold=True)
            else:
                deck.text(slide, "Subordinação mínima", .62, 4.37, 2.0, .24, size=10, color=ORANGE, bold=True)
                deck.text(slide, data.minimum_subordination, 2.45, 4.34, 1.9, .36, size=11, bold=True)
            deck.text(slide, "RDB", .62, 5.13 if compact else 4.91, 2.0, .24, size=10, color=ORANGE, bold=True)
            finding = f"{data.rdb_status}: {data.rdb_finding}"
            if len(_cell_lines(finding, 3.73, table_size)) > 5:
                finding = f"{data.rdb_status}. Leitura completa nas notas."
            deck.text(slide, finding, .62, 5.46 if compact else 5.19, 3.73, .76 if compact else .92, size=table_size, color=GRAY_700)
            deck.text(slide, "Perfil de amortização", 10.15, 1.40, 2.3, .3, size=11, bold=True)
            if compact:
                deck.text(slide, "Cronograma quantificável: N/D. Textos documentais nas notas.", 10.15, 1.80, 2.53, .76, size=10, color=GRAY_700)
                deck.text(slide, "Controles", 10.15, 3.0, 2.53, .24, size=11, color=ORANGE, bold=True)
                deck.text(slide, control_pages[0] if control_pages else "Demais controles registrados nas notas.", 10.15, 3.34, 2.53, 3.10, size=10, color=GRAY_700)
                if portfolio_rdb_note:
                    deck.text(slide, portfolio_rdb_note, .62, 6.64, 12.05, .24, size=10, color=GRAY_700)
            else:
                deck.block(slide, 10.15, 1.76, 2.53, 3.67, GRAY_100)
                deck.text(slide, "Dados insuficientes para reconstrução confiável do waterfall.", 10.42, 3.05, 2.0, .7, size=10, color=GRAY_500, bold=True, align=1)
                deck.text(slide, "Controles", 10.15, 5.62, 1.3, .22, size=9, color=ORANGE, bold=True)
                deck.text(slide, "\n".join(f"• {x}" for x in data.validations[:3]) or "• Sem divergência material identificada", 10.15, 5.88, 2.53, .72, size=7.5, color=GRAY_700)
        sources = sorted({_public_source(i.source) for i in data.issuances if i.source != "N/D"})
        deck.footer(slide, f"CVM · {data.competence} | Fundos.NET/B3 · Fontes nas notas. Gerado em {generation_date}.")
        notes = [f"{legal_name} · CNPJ {data.cnpj}", f"Posição CVM: {data.competence}", f"Geração: {generation_date}", f"RDB: {data.rdb_status} · {data.rdb_finding}", f"Fonte RDB: {_public_source(data.rdb_source)}", "Emissões:"]
        notes.extend(f"{i.date} · {i.series} · {_money(i.volume_mm)} · {i.remuneration} · Amortização: {i.amortization} · Fonte: {_public_source(i.source)}" for i in data.issuances)
        notes.extend(["Fontes:", *sources, "Controles:", *data.validations])
        if compact:
            notes.append(f"Subordinação mínima: {data.minimum_subordination}")
        if page == 1 and portfolio_rdb_notes:
            notes.extend(["Cobertura RDB da cesta completa:", *portfolio_rdb_notes])
        slide.notes_slide.notes_text_frame.text = "\n".join(notes)
    if compact:
        if extensive_minimum:
            minimum_rows = _table_pages([[data.minimum_subordination]], [12.05], size=10, maximum_height=4.78)
            for index, rows in enumerate(minimum_rows, 1):
                title = f"{_presentation_name(data.name)} | subordinação mínima"
                if len(minimum_rows) > 1:
                    title += f" ({index}/{len(minimum_rows)})"
                slide = deck.slide(title)
                _native_readable_table(deck, slide, [["Regra documental integral"], *rows], .62, 1.76, [12.05], size=10, aligns="l")
                deck.footer(slide, f"CVM · {data.competence} | Fundos.NET/B3 · Fontes nas notas. Gerado em {generation_date}.")
                slide.notes_slide.notes_text_frame.text = "\n".join(notes)
        for index, controls in enumerate(control_pages[1:], 2):
            slide = deck.slide(f"{_presentation_name(data.name)} | controles documentais ({index}/{len(control_pages)})")
            deck.text(slide, "Controles — continuação", .62, 1.40, 8, .3, size=11, bold=True)
            deck.text(slide, controls, .62, 1.86, 12.05, 4.8, size=10, color=GRAY_700)
            deck.footer(slide, f"CVM · {data.competence} | Fundos.NET/B3 · Fontes nas notas. Gerado em {generation_date}.")
            slide.notes_slide.notes_text_frame.text = "\n".join(notes)


def _portfolio_rdb_evidence(
    evidence: pd.DataFrame,
    data: list[FidcSlideData],
    legal_names: dict[str, str],
) -> tuple[pd.DataFrame, int, int]:
    if "CNPJ" not in evidence.columns:
        raise ValueError("O cadastro documental de RDB não contém a coluna CNPJ.")
    selected_cnpjs = {normalize_cnpj(item.cnpj) for item in data}
    evidence_cnpjs = evidence["CNPJ"].map(normalize_cnpj)
    selected = evidence.loc[evidence_cnpjs.isin(selected_cnpjs)].copy()
    located_cnpjs = set(evidence_cnpjs.loc[selected.index])
    missing_rows = []
    for item in data:
        cnpj = normalize_cnpj(item.cnpj)
        if cnpj in located_cnpjs:
            continue
        row = dict.fromkeys(evidence.columns, "N/D")
        values = {
            "CNPJ": item.cnpj,
            "Fundo": legal_names.get(cnpj, item.name),
            "Status": "Não localizado",
            "Achado regulamento": "Nenhum registro de RDB localizado no cadastro documental consultado.",
            "Função documentada": "N/D; não inferido.",
        }
        row.update({key: value for key, value in values.items() if key in row})
        missing_rows.append(row)
    if missing_rows:
        selected = pd.concat([selected, pd.DataFrame(missing_rows, columns=evidence.columns)], ignore_index=True)
    return selected, len(evidence) - int(evidence_cnpjs.isin(selected_cnpjs).sum()), len(missing_rows)


def build_fidc_analytical_xlsx_bytes(
    funds: Iterable[object], *, portfolio_name: str, portfolio_mode: bool = False,
) -> bytes:
    portfolio_funds = tuple(funds) if portfolio_mode else None
    data = build_slide_data(portfolio_funds if portfolio_mode else funds)
    wb = Workbook(); wb.remove(wb.active)
    _write_sheet(wb, "Snapshot", [
        ["Carteira", "CNPJ", "FIDC", "Competência", "PL (R$ mm)", "DC / PL", "Sênior / PL", "Subordinada / PL", "Volume emitido (R$ mm)", "Primeira emissão", "Última emissão", "Subordinação mínima"]
    ] + [[portfolio_name, d.cnpj, d.name, d.competence, d.pl_mm, d.receivables_pct_pl, d.senior_pct_pl, d.subordinated_pct_pl, d.identified_issuance_volume_mm, d.first_issuance, d.last_issuance, d.minimum_subordination] for d in data], "tbSnapshot")
    _write_sheet(wb, "Emissões", [["CNPJ", "FIDC", "Data", "Série / classe", "Tipo", "Volume (R$ mm)", "Remuneração", "Amortização", "Fonte"]] + [[d.cnpj, d.name, i.date, i.series, i.quota_class, i.volume_mm, i.remuneration, i.amortization, i.source] for d in data for i in d.issuances], "tbEmissoes")
    evidence = pd.read_csv(RDB_EVIDENCE, dtype=str, keep_default_na=False)
    if portfolio_mode:
        legal_names = {normalize_cnpj(fund.cnpj): fund.display_name for fund in portfolio_funds}
        evidence, excluded_rdb_rows, missing_rdb_funds = _portfolio_rdb_evidence(evidence, data, legal_names)
    _write_sheet(wb, "RDB", [list(evidence.columns)] + evidence.values.tolist(), "tbRDB")
    _write_sheet(wb, "Validações", [["CNPJ", "FIDC", "Controle / divergência"]] + [[d.cnpj, d.name, issue] for d in data for issue in (d.validations or ["Sem divergência material identificada"])] , "tbValidacoes")
    ws = wb.create_sheet("Metodologia"); ws.append(["Campo", "Regra"])
    for row in [("Separação", "extração → normalização → cálculos → validação → renderização"), ("PL e composição", "última competência disponível por CNPJ em vehicle_monthly.csv.gz"), ("Emissões", "perfil regulatório curado; deduplicação por data, série, volume e primeira fonte"), ("Waterfall", "somente produzido com cronograma documental quantificável; caso contrário, N/D"), ("RDB", "matriz documental por CNPJ, com página e status explícito/parcial/não localizado")]: ws.append(row)
    if portfolio_mode:
        ws.append(["RDB — perímetro", f"CNPJs exatos da cesta. {excluded_rdb_rows} registro(s) de outros CNPJs excluído(s)."])
        ws.append(["RDB — lacunas", f"{missing_rdb_funds} fundo(s) sem registro no cadastro consultado, indicados como Não localizado e N/D. Ausência de evidência documental não comprova inexistência de RDB."])
    _style_sheet(ws); output = BytesIO(); wb.save(output); return output.getvalue()


def _write_sheet(wb: Workbook, title: str, rows: list[list[object]], table_name: str) -> None:
    ws = wb.create_sheet(title)
    for row in rows or [["N/D"]]: ws.append(row)
    _style_sheet(ws)
    if ws.max_row >= 2 and ws.max_column >= 1:
        ref = f"A1:{ws.cell(ws.max_row, ws.max_column).coordinate}"
        table = Table(displayName=table_name, ref=ref); table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False, showLastColumn=False)
        ws.add_table(table)
        # Excel rejects a worksheet filter overlapping the native table filter.
        ws.auto_filter.ref = None


def _style_sheet(ws) -> None:
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="14315C"); cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF"); cell.alignment = Alignment(vertical="center")
    for column in ws.columns:
        letter = column[0].column_letter; ws.column_dimensions[letter].width = min(55, max(11, max(len(str(c.value or "")) for c in column) + 2))
        for cell in column[1:]: cell.font = Font(name="Arial", size=9); cell.alignment = Alignment(vertical="top", wrap_text=True)


__all__ = ["FidcSlideData", "Issuance", "build_slide_data", "build_fidc_analytical_pptx_bytes", "build_fidc_analytical_xlsx_bytes"]
