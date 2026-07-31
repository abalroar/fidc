"""Materialize the year-by-year FIDC issuance decomposition by ANBIMA taxonomy.

Writes the analytical table the *Dados da Indústria* view reads, plus the
Excel deliverable meant to be pasted into a deck.  The rule that decides which
sector each offer belongs to lives in ``services/industry_issuance_taxonomy``,
shared with the panel so both cannot drift.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.industry_issuance_taxonomy import (
    DELTAS,
    DISPLAY_CATEGORIES,
    PERIODS,
    build_issuance_taxonomy,
    build_wide_table,
    write_issuance_taxonomy,
)

OUTPUT_BASENAME = "emissoes_fidc_por_taxonomia"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/industry_study"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/analysis"))
    return parser.parse_args(argv)


_CELL_PATTERN = re.compile(
    r'<c r="(?P<ref>[A-Z]+\d+)"(?P<attrs>[^>/]*)>(?P<body>.*?)</c>', re.DOTALL
)
_FORMULA_PATTERN = re.compile(r"<f[ >].*?</f>|<f/>", re.DOTALL)


def inject_cached_values(path: Path, cached: dict[str, dict[str, float]]) -> int:
    """Write the result of every formula next to the formula itself.

    openpyxl emits formulas with no cached value, so until the file is opened
    in a spreadsheet application every formula cell reads back as empty to
    pandas, to ``load_workbook(data_only=True)`` and to previewers.  The
    canonical fix is to recalculate with LibreOffice, which does not run in
    this runtime, so the values computed here — the same arithmetic the
    formulas express — are written into the sheet XML as ``<v>``.

    The formulas stay in the file and remain authoritative: a spreadsheet
    recalculates them on open and overwrites these values.
    """

    sheet_targets = {
        f"xl/worksheets/sheet{index}.xml": values
        for index, values in enumerate(cached.values(), start=1)
    }
    staging = path.with_suffix(".tmp.xlsx")
    filled = 0
    with ZipFile(path) as source, ZipFile(
        staging, "w", compression=ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            values = sheet_targets.get(item.filename)
            if values:
                text = payload.decode("utf-8")

                def replace(match: re.Match[str]) -> str:
                    nonlocal filled
                    body = match.group("body")
                    if "<f" not in body:
                        return match.group(0)
                    value = values.get(match.group("ref"))
                    if value is None:
                        return match.group(0)
                    formula = _FORMULA_PATTERN.search(body)
                    if formula is None:
                        return match.group(0)
                    filled += 1
                    return (
                        f'<c r="{match.group("ref")}"{match.group("attrs")}>'
                        f"{formula.group(0)}<v>{escape(repr(float(value)))}</v></c>"
                    )

                payload = _CELL_PATTERN.sub(replace, text).encode("utf-8")
            target.writestr(item, payload)
    shutil.move(staging, path)
    return filled


def _column_letter(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def write_workbook(
    table: pd.DataFrame,
    audit: pd.DataFrame,
    long_frame: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{OUTPUT_BASENAME}.csv"
    table.to_csv(csv_path, index=False)

    book = Workbook()
    sheet = book.active
    sheet.title = "Emissões por categoria"
    normal = Font(name="Arial", size=11)
    bold = Font(name="Arial", size=11, bold=True)
    small = Font(name="Arial", size=9)

    sheet["A1"] = (
        "Emissões de FIDCs por categoria ANBIMA — 2023 a jun/26 (R$ bilhões)"
    )
    sheet["A1"].font = bold

    header_row = 3
    for column, header in enumerate(table.columns, start=1):
        cell = sheet.cell(row=header_row, column=column, value=header)
        cell.font = bold

    first_data = header_row + 1
    total_row = first_data + len(table)
    value_columns = {
        index
        for index, name in enumerate(table.columns, start=1)
        if name.endswith("(R$ bi)")
    }
    share_columns = {
        index
        for index, name in enumerate(table.columns, start=1)
        if name.endswith("(%)")
    }
    # Cada coluna de participação normaliza pela coluna de valor imediatamente
    # à esquerda, que é como a tabela é lida: percentual do período.
    share_base = {index: index - 1 for index in share_columns}

    cached: dict[str, float] = {}
    for offset, record in enumerate(table.itertuples(index=False), start=0):
        row = first_data + offset
        values = dict(zip(table.columns, record))
        sheet.cell(row=row, column=1, value=values["Categoria"]).font = normal
        for column, name in enumerate(table.columns, start=1):
            if column == 1:
                continue
            letter = _column_letter(column)
            if column in share_columns:
                base_letter = _column_letter(share_base[column])
                sheet.cell(
                    row=row, column=column, value=f"={base_letter}{row}/{base_letter}${total_row}"
                )
                total_value = float(table[table.columns[share_base[column] - 1]].sum())
                cached[f"{letter}{row}"] = (
                    float(values[name]) if total_value else 0.0
                )
            else:
                sheet.cell(row=row, column=column, value=float(values[name]))

    sheet.cell(row=total_row, column=1, value="Total (quatro tipos ANBIMA)").font = bold
    for column, name in enumerate(table.columns, start=1):
        if column == 1:
            continue
        letter = _column_letter(column)
        if column in share_columns:
            base_letter = _column_letter(share_base[column])
            sheet.cell(
                row=total_row,
                column=column,
                value=f"={base_letter}{total_row}/{base_letter}${total_row}",
            )
            cached[f"{letter}{total_row}"] = 1.0
        else:
            sheet.cell(
                row=total_row,
                column=column,
                value=f"=SUM({letter}{first_data}:{letter}{total_row - 1})",
            )
            cached[f"{letter}{total_row}"] = float(table[name].sum())

    for row in range(first_data, total_row + 1):
        for column in range(2, len(table.columns) + 1):
            cell = sheet.cell(row=row, column=column)
            cell.number_format = "0.0%" if column in share_columns else "#,##0.0"
            cell.font = bold if row == total_row else normal

    # A ponte com o gráfico de emissões. Sem ela a leitora encontra um total
    # menor que o do gráfico e não tem como saber por quê.
    fic_row = total_row + 1
    emitted_row = total_row + 2
    sheet.cell(
        row=fic_row,
        column=1,
        value="FIC-FIDC (fundos de cotas — fora dos quatro tipos)",
    ).font = normal
    sheet.cell(
        row=emitted_row, column=1, value="Total emitido (bate com o gráfico)"
    ).font = bold
    audit_by_period = audit.set_index("period_label")
    for column, name in enumerate(table.columns, start=1):
        if column == 1 or column in share_columns:
            continue
        letter = _column_letter(column)
        period_label = name.rsplit(" (", 1)[0]
        if period_label not in audit_by_period.index:
            continue  # coluna de delta: a ponte não se aplica
        fic_value = float(audit_by_period.at[period_label, "fic_excluded_brl"]) / 1e9
        sheet.cell(row=fic_row, column=column, value=fic_value)
        sheet.cell(
            row=emitted_row, column=column, value=f"={letter}{total_row}+{letter}{fic_row}"
        )
        cached[f"{letter}{emitted_row}"] = float(table[name].sum()) + fic_value
    for row in (fic_row, emitted_row):
        for column in range(2, len(table.columns) + 1):
            cell = sheet.cell(row=row, column=column)
            cell.number_format = "#,##0.0"
            cell.font = bold if row == emitted_row else normal
    total_row = emitted_row

    notes = [
        "Fonte: CVM/SRE — ofertas públicas primárias encerradas (snapshot 24/jul/26), "
        "com a taxonomia ANBIMA sob a reclassificação analítica do projeto "
        "(taxonomy_review_actions.csv). Mesma regra da aba Escala e taxonomia.",
        "Aberturas pela reclassificação analítica final: fundos sem tipo ANBIMA "
        "nomeado entram em Outros, como a aba faz com N/D. FIC-FIDCs ficam fora "
        "dos quatro tipos — são fundos de cotas e contá-los somaria o mesmo "
        "dinheiro duas vezes.",
        "2023 foi o primeiro ano da Resolução CVM 160 e a base granular da CVM "
        "observa parte do ano; o não observado é distribuído com a composição do "
        "observado. O fator aplicado está na aba Cobertura.",
        "jan–jun/26 é comparado a jan–jun/25 porque 2026 ainda não fechou.",
    ]
    for offset, note in enumerate(notes):
        sheet.cell(row=total_row + 2 + offset, column=1, value=note).font = small

    sheet.column_dimensions["A"].width = 32
    for column in range(2, len(table.columns) + 1):
        sheet.column_dimensions[_column_letter(column)].width = 15

    coverage = book.create_sheet("Cobertura")
    coverage["A1"] = "Sobre o que a decomposição se apoia, por período"
    coverage["A1"].font = bold
    headers = (
        ("period_label", "Período"),
        ("observed_brl", "Observado na CVM (R$ bi)"),
        ("scale_factor", "Fator aplicado"),
        ("total_brl", "Total da tabela (R$ bi)"),
        ("fic_excluded_brl", "FIC-FIDC fora dos tipos (R$ bi)"),
        ("outros_from_fallback_brl", "Outros vindo de N/D (R$ bi)"),
        ("outros_from_fallback_share", "N/D sobre o total"),
        ("unresolved_issuers", "Emissores sem base"),
        ("unresolved_issuer_brl", "Volume sem base (R$ bi)"),
    )
    for column, (_, label) in enumerate(headers, start=1):
        coverage.cell(row=3, column=column, value=label).font = bold
    for offset, record in enumerate(audit.itertuples(index=False)):
        row = 4 + offset
        for column, (key, _) in enumerate(headers, start=1):
            value = getattr(record, key)
            if key.endswith("_brl"):
                value = float(value) / 1e9
            cell = coverage.cell(row=row, column=column, value=value)
            cell.font = normal
            if key.endswith("_brl"):
                cell.number_format = "#,##0.00"
            elif key.endswith("_share"):
                cell.number_format = "0.0%"
            elif key == "scale_factor":
                cell.number_format = "0.000"
    coverage.column_dimensions["A"].width = 14
    for column in range(2, len(headers) + 1):
        coverage.column_dimensions[_column_letter(column)].width = 22

    xlsx_path = output_dir / f"{OUTPUT_BASENAME}.xlsx"
    book.save(xlsx_path)
    filled = inject_cached_values(xlsx_path, {sheet.title: cached, coverage.title: {}})
    if filled != len(cached):
        raise SystemExit(
            f"cache de fórmulas incompleto: {filled} de {len(cached)} células; "
            "o arquivo abriria com colunas vazias fora do Excel"
        )
    return csv_path, xlsx_path


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    long_frame, coverage = build_issuance_taxonomy(args.data_dir)
    analytical_path = write_issuance_taxonomy(long_frame, args.data_dir)
    table = build_wide_table(long_frame)
    audit = coverage.frame()
    csv_path, xlsx_path = write_workbook(table, audit, long_frame, args.output_dir)

    print(f"[ok] série analítica: {analytical_path}")
    print(f"[ok] tabela: {csv_path}")
    print(f"[ok] excel: {xlsx_path}")
    for record in audit.itertuples(index=False):
        print(
            f"  {record.period_label}: total R$ {record.total_brl / 1e9:,.2f} bi "
            f"(observado {record.observed_brl / 1e9:,.2f}, fator {record.scale_factor:.3f}) | "
            f"FIC fora R$ {record.fic_excluded_brl / 1e9:,.2f} bi | "
            f"classificação positiva {record.classified_share:.1%}"
        )
    if coverage.unresolved_cnpjs:
        print(
            f"  emissores sem correspondência em base alguma: "
            f"{len(coverage.unresolved_cnpjs)}"
        )
    for start, end in DELTAS:
        labels = {period["key"]: period["label"] for period in PERIODS}
        pivot = long_frame.pivot(
            index="categoria", columns="period_key", values="volume_brl"
        ).reindex(DISPLAY_CATEGORIES)
        delta = ((pivot[end] - pivot[start]) / 1e9).sort_values(ascending=False)
        top = ", ".join(
            f"{name} {value:+.1f}" for name, value in delta.head(3).items()
        )
        print(f"  delta {labels[start]}→{labels[end]}: {top}")


if __name__ == "__main__":
    main()
