"""Comparable documentary matrices shared by the screen and PowerPoint export."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

import pandas as pd

from services.deep_dive_store import load_deep_dive_table
from services.presentation_text import document_comparison_value, public_document_text

CELL_REFERENCES_SUBTITLE = 'Referências por célula; observações comuns no rodapé'


@dataclass(frozen=True)
class DocumentComparisonPage:
    title: str
    frame: pd.DataFrame
    notes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return "Não localizado"
    text = str(value).strip()
    return "Não localizado" if text.casefold() in {"", "—", "-", "nan", "none", "n/d"} else text


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value))


def _funds(manifest) -> list[tuple[str, str, dict]]:
    output = []
    labels: set[str] = set()
    for fund in manifest.funds:
        label = str(fund.get("short_name") or fund.get("name") or fund["cnpj"])
        if label in labels:
            label = f"{label} ({fund['cnpj']})"
        labels.add(label)
        output.append((_digits(fund["cnpj"]), label, fund))
    return output


def _load(manifest, table_id: str) -> pd.DataFrame:
    spec = next((s for s in manifest.tables if s.id == table_id), None)
    return load_deep_dive_table(manifest, spec) if spec else pd.DataFrame()


def _sources(frame: pd.DataFrame) -> tuple[str, ...]:
    columns = [c for c in frame if _fold(c) in {"fonte", "fontes"}]
    return tuple(dict.fromkeys(clean for c in columns for v in frame[c] if _text(v) != "Não localizado" if (clean := public_document_text(v))))


def presentation_comparison_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns[1:]:
        output[column] = output[column].map(document_comparison_value)
    return output


def _group_notes(manifest, page_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    evidence = _load(manifest, "comparison_evidence")
    if evidence.empty or "Tabela" not in evidence:
        return (), ()
    evidence = evidence[evidence["Tabela"].eq(page_id)]
    evidence_spec = next((spec for spec in manifest.tables if spec.id == 'comparison_evidence'), None)
    if evidence_spec is None or evidence_spec.subtitle != CELL_REFERENCES_SUBTITLE:
        notes = tuple(dict.fromkeys(clean for v in evidence.get('Nota', []) if _text(v) != 'Não localizado' if (clean := public_document_text(v))))
        return notes, _sources(evidence)
    # Cell qualifications stay attached to their exact fund/criterion in the slide
    # notes. Only common table notes occupy the visible footer; repeating every
    # cell note there multiplied the same table across dozens of slides.
    common = evidence[evidence['CNPJ'].astype(str).eq('Carteira')] if 'CNPJ' in evidence else evidence
    notes = tuple(dict.fromkeys(clean for v in common.get("Nota", []) if _text(v) != "Não localizado" if (clean := public_document_text(v))))
    if 'CNPJ' not in evidence:
        return notes, _sources(evidence)
    sources = []
    for _, row in evidence.iterrows():
        source = _text(row.get('Fonte'))
        if source == 'Não localizado':
            continue
        identity = f"CNPJ {row.get('CNPJ', 'não informado')} · {row.get('Critério', 'regra')} · {row.get('Valor', 'valor não informado')}"
        note = _text(row.get('Nota'))
        clean = public_document_text(identity + ' · ' + source + (' · Observação: ' + note if note != 'Não localizado' else ''))
        if clean:
            sources.append(clean)
    return notes, tuple(dict.fromkeys(sources))


def build_document_comparison_pages(manifest) -> list[DocumentComparisonPage]:
    """Use reviewed short matrices when present, otherwise compare legacy packages.

    Source tables remain complete. Missing cells are always textual, and multiple
    series are retained rather than selecting one fund or one issue implicitly.
    """
    custom = [s for s in manifest.tables if s.kind == "document_comparison"]
    if custom:
        pages = []
        for spec in custom:
            frame = load_deep_dive_table(manifest, spec)
            if frame.empty:
                continue
            notes, sources = _group_notes(manifest, spec.id)
            pages.append(DocumentComparisonPage(spec.title, presentation_comparison_frame(frame), notes, sources))
        if pages:
            return pages

    pages: list[DocumentComparisonPage] = []
    comparison = _load(manifest, "comparison_main")
    funds = _funds(manifest)
    if not comparison.empty:
        first = comparison.columns[0]
        columns = {}
        for _, label, fund in funds:
            candidates = [fund.get("short_name"), fund.get("name"), fund.get("cnpj")]
            match = next((c for c in comparison.columns[1:] if c in candidates), None)
            if match:
                columns[match] = label
        if columns:
            frame = comparison[[first, *columns]].rename(columns={first: "Critério", **columns})
            # These rows describe measured IME data, inventory or processing.
            skip = r"^(?:grupo|paginas locais|ultima competencia|pl \(|direitos creditorios / pl|vencidos over|pdd /|cotas .+ / pl|series/classes documentadas|escopo da leitura|data emissao|emissoes detectadas|remuneracao-alvo por|amortizacao/vencimento por)"
            frame = frame[~frame["Critério"].map(_fold).str.contains(skip, regex=True)]
            for start in range(0, len(frame), 7):
                part = frame.iloc[start:start + 7].map(_text)
                pages.append(DocumentComparisonPage("Critérios e estrutura", part, sources=_sources(_load(manifest, "thresholds"))))

    emissions = _load(manifest, "emissions")
    if not emissions.empty and "CNPJ" in emissions:
        sections = (
            ("Remuneração das cotas", ("Remuneração-alvo", "Remuneração", "Custo / remuneração")),
            ("Amortização e pagamentos", ("Amortização/vencimento", "Amortização principal", "Prazo / amortização")),
            ("Volume documentado", ("Volume", "Volume identificado (R$ mm)")),
        )
        for title, candidates in sections:
            column = next((c for c in candidates if c in emissions), None)
            if column is None:
                continue
            rows = []
            for quota in ("Sênior", "Mezanino", "Júnior", "Outras cotas"):
                result = {"Critério": quota}
                found = False
                for cnpj, label, _ in funds:
                    group = emissions[emissions["CNPJ"].map(_digits).eq(cnpj)]
                    values = []
                    for _, row in group.iterrows():
                        kind = _quota_type(row.get("Tipo", row.get("Tipo de cota", "")))
                        if kind != quota:
                            continue
                        found = True
                        series = _text(row.get("Classe/Série", row.get("Cota/Classe", quota)))
                        values.append(f"{series}: {_text(row[column])}")
                    result[label] = "\n".join(dict.fromkeys(values)) or "Não localizado"
                if found:
                    rows.append(result)
            if rows:
                pages.append(DocumentComparisonPage(title, pd.DataFrame(rows), sources=_sources(emissions)))

    costs = _load(manifest, "structural_costs")
    if not costs.empty and {"CNPJ", "Item"}.issubset(costs.columns):
        rows = []
        for item in dict.fromkeys(["Administração", "Gestão", *costs["Item"]]):
            row = {"Critério": item}
            for cnpj, label, _ in funds:
                group = costs[costs["CNPJ"].map(_digits).eq(cnpj) & costs["Item"].map(_fold).eq(_fold(item))]
                values = []
                for _, record in group.iterrows():
                    parts = [f"{field}: {_text(record[field])}" for field in ("Percentual a.a.", "Mínimo mensal", "Base de cálculo") if field in costs]
                    values.append("\n".join(parts))
                row[label] = "\n".join(dict.fromkeys(values)) or "Não localizado"
            rows.append(row)
        for start in range(0, len(rows), 5):
            pages.append(DocumentComparisonPage("Custos estruturais", pd.DataFrame(rows[start:start + 5]), sources=_sources(costs)))
    return [DocumentComparisonPage(page.title, presentation_comparison_frame(page.frame), page.notes, page.sources) for page in pages]


def _quota_type(value: object) -> str:
    folded = _fold(value)
    if "senior" in folded:
        return "Sênior"
    if "mezan" in folded:
        return "Mezanino"
    if "junior" in folded or "subordinad" in folded:
        return "Júnior"
    return "Outras cotas"


def comparison_column_chunks(frame: pd.DataFrame, max_funds: int = 4) -> list[pd.DataFrame]:
    """Repeat the criterion for every group of funds; retain all columns."""
    first, *funds = frame.columns
    return [frame[[first, *funds[start:start + max_funds]]].copy() for start in range(0, max(len(funds), 1), max_funds)]
