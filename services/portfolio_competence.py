from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import calendar
import math
import re
import unicodedata
from typing import Mapping, Sequence

import pandas as pd


_PT_MONTH_ABBR = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


@dataclass(frozen=True)
class PortfolioCompetenceAssessment:
    reference_competence: str | None
    latest_observed_competence: str | None
    common_competences: tuple[str, ...]
    eligible_cnpjs: tuple[str, ...]
    excluded_cnpjs: tuple[str, ...]
    exclusion_reasons_by_cnpj: Mapping[str, str]
    coverage_df: pd.DataFrame
    note: str


def assess_portfolio_competence(
    funds_by_cnpj: Mapping[str, tuple[str, Sequence[object]]],
    *,
    reporting_status_by_cnpj: Mapping[str, Mapping[str, object]] | None = None,
    as_of: date | None = None,
) -> PortfolioCompetenceAssessment:
    normalized_funds = {
        _normalize_cnpj(cnpj): (str(name or cnpj), _normalize_competences(competences))
        for cnpj, (name, competences) in funds_by_cnpj.items()
        if _normalize_cnpj(cnpj)
    }
    statuses = {
        _normalize_cnpj(cnpj): dict(status or {})
        for cnpj, status in (reporting_status_by_cnpj or {}).items()
        if _normalize_cnpj(cnpj)
    }
    all_competences = sorted(
        {competence for _, competences in normalized_funds.values() for competence in competences},
        key=_competence_sort_key,
    )
    latest = all_competences[-1] if all_competences else None
    eligible_cnpjs: list[str] = []
    excluded_cnpjs: list[str] = []
    exclusion_reasons_by_cnpj: dict[str, str] = {}
    for cnpj in normalized_funds:
        exclusion_reason = (
            _reporting_ineligibility_reason(statuses.get(cnpj, {}), latest)
            if latest
            else None
        )
        if exclusion_reason:
            excluded_cnpjs.append(cnpj)
            exclusion_reasons_by_cnpj[cnpj] = exclusion_reason
        else:
            eligible_cnpjs.append(cnpj)

    common: set[str] = set()
    if eligible_cnpjs:
        common = set.intersection(
            *(set(normalized_funds[cnpj][1]) for cnpj in eligible_cnpjs)
        )
    common_competences = tuple(sorted(common, key=_competence_sort_key))
    reference = common_competences[-1] if common_competences else None

    coverage_rows: list[dict[str, object]] = []
    for competence in all_competences:
        reported = [cnpj for cnpj in eligible_cnpjs if competence in normalized_funds[cnpj][1]]
        missing = [cnpj for cnpj in eligible_cnpjs if competence not in normalized_funds[cnpj][1]]
        coverage_rows.append(
            {
                "competencia": competence,
                "fundos_selecionados": len(normalized_funds),
                "fundos_elegiveis": len(eligible_cnpjs),
                "fundos_reportantes": len(reported),
                "cobertura_pct": len(reported) / len(eligible_cnpjs) if eligible_cnpjs else math.nan,
                "status": "Completa" if eligible_cnpjs and not missing else "Incompleta",
                "fundos_ausentes": _join_fund_labels(missing, normalized_funds, statuses),
                "fundos_excluidos": _join_excluded_labels(
                    excluded_cnpjs,
                    normalized_funds,
                    exclusion_reasons_by_cnpj,
                ),
            }
        )
    coverage_df = pd.DataFrame(coverage_rows)
    note = _assessment_note(
        reference=reference,
        latest=latest,
        eligible_cnpjs=eligible_cnpjs,
        excluded_cnpjs=excluded_cnpjs,
        normalized_funds=normalized_funds,
        statuses=statuses,
        exclusion_reasons_by_cnpj=exclusion_reasons_by_cnpj,
        as_of=as_of or date.today(),
    )
    return PortfolioCompetenceAssessment(
        reference_competence=reference,
        latest_observed_competence=latest,
        common_competences=common_competences,
        eligible_cnpjs=tuple(eligible_cnpjs),
        excluded_cnpjs=tuple(excluded_cnpjs),
        exclusion_reasons_by_cnpj=exclusion_reasons_by_cnpj,
        coverage_df=coverage_df,
        note=note,
    )


def _assessment_note(
    *,
    reference: str | None,
    latest: str | None,
    eligible_cnpjs: list[str],
    excluded_cnpjs: list[str],
    normalized_funds: Mapping[str, tuple[str, Sequence[str]]],
    statuses: Mapping[str, Mapping[str, object]],
    exclusion_reasons_by_cnpj: Mapping[str, str],
    as_of: date,
) -> str:
    total = len(eligible_cnpjs)
    reported_latest = [
        cnpj
        for cnpj in eligible_cnpjs
        if latest and latest in normalized_funds[cnpj][1]
    ]
    missing_latest = [cnpj for cnpj in eligible_cnpjs if cnpj not in reported_latest]
    if reference:
        opening = f"Competência utilizada: {_format_competence(reference)} ({total}/{total} fundos elegíveis)."
    else:
        opening = f"Sem competência comum entre os {total} fundos elegíveis."

    details: list[str] = [opening]
    if latest and (latest != reference or missing_latest):
        deadline = _reporting_deadline(latest)
        timing = (
            f"prazo regulatório até {deadline.strftime('%d/%m/%Y')}"
            if as_of <= deadline
            else f"prazo regulatório encerrado em {deadline.strftime('%d/%m/%Y')}"
        )
        details.append(
            f"Em {_format_competence(latest)}, {len(reported_latest)}/{total} reportaram; "
            f"ausentes ({timing}): {_join_fund_labels(missing_latest, normalized_funds, statuses) or 'nenhum'}."
        )
    if excluded_cnpjs:
        details.append(
            "Excluídos da checagem por ausência comprovada de obrigação na competência: "
            f"{_join_excluded_labels(excluded_cnpjs, normalized_funds, exclusion_reasons_by_cnpj)}."
        )
    return " ".join(details)


def _reporting_ineligibility_reason(status: Mapping[str, object], competence: str) -> str | None:
    cancellation_date = _parse_date(status.get("data_cancelamento"))
    registration_date = _parse_date(status.get("data_registro"))
    competence_month = _parse_competence(competence)
    if cancellation_date and competence_month:
        cancellation_month = date(cancellation_date.year, cancellation_date.month, 1)
        if competence_month > cancellation_month:
            return f"Cancelado em {cancellation_date.strftime('%d/%m/%Y')}"
    if registration_date and competence_month:
        registration_month = date(registration_date.year, registration_date.month, 1)
        if competence_month < registration_month:
            return f"Registro em {registration_date.strftime('%d/%m/%Y')} posterior à competência"
    # Situações textuais sem data não demonstram ausência de obrigação.
    return None


def _join_fund_labels(
    cnpjs: Sequence[str],
    funds: Mapping[str, tuple[str, Sequence[str]]],
    statuses: Mapping[str, Mapping[str, object]],
) -> str:
    labels: list[str] = []
    for cnpj in cnpjs:
        name = funds.get(cnpj, (cnpj, ()))[0]
        situation = str(statuses.get(cnpj, {}).get("situacao") or "situação cadastral N/D").strip()
        labels.append(f"{name} ({_format_cnpj(cnpj)}; {situation})")
    return "; ".join(labels)


def _join_excluded_labels(
    cnpjs: Sequence[str],
    funds: Mapping[str, tuple[str, Sequence[str]]],
    exclusion_reasons_by_cnpj: Mapping[str, str],
) -> str:
    labels: list[str] = []
    for cnpj in cnpjs:
        name = funds.get(cnpj, (cnpj, ()))[0]
        reason = exclusion_reasons_by_cnpj.get(cnpj, "ausência de obrigação comprovada")
        labels.append(f"{name} ({_format_cnpj(cnpj)}; {reason})")
    return "; ".join(labels)


def _normalize_competences(values: Sequence[object]) -> tuple[str, ...]:
    normalized = {
        str(value).strip()
        for value in values
        if _parse_competence(str(value).strip()) is not None
    }
    return tuple(sorted(normalized, key=_competence_sort_key))


def _parse_competence(value: object) -> date | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{2})/(\d{4})", text)
    if not match:
        return None
    month, year = int(match.group(1)), int(match.group(2))
    if month < 1 or month > 12:
        return None
    return date(year, month, 1)


def _competence_sort_key(value: object) -> date:
    return _parse_competence(value) or date.min


def _reporting_deadline(competence: str) -> date:
    month = _parse_competence(competence)
    if month is None:
        return date.min
    month_end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    return month_end + timedelta(days=15)


def _format_competence(value: str) -> str:
    parsed = _parse_competence(value)
    if parsed is None:
        return str(value)
    return f"{_PT_MONTH_ABBR[parsed.month]}/{str(parsed.year)[-2:]}"


def _parse_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return date(int(parsed.year), int(parsed.month), int(parsed.day))


def _fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().casefold()


def _normalize_cnpj(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _format_cnpj(value: object) -> str:
    digits = _normalize_cnpj(value)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
