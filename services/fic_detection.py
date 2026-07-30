"""Auditable detection of FIC vehicles and the single exclusion gate.

A FIC holds quotas of other FIDCs instead of buying receivables.  Counted
inside the four ANBIMA types it adds the same money twice — once in the fund
it invests in, with that fund's taxonomy, and once in the vehicle that only
holds the quota.  So it has to leave the analytical universe *before* anything
is aggregated, classified or reclassified.

Three sources say whether a fund is a FIC, and they are not equally strong:

1. **Flag cadastral.**  The CVM monthly report carries ``is_fic_fidc``.  When
   it is true the matter is settled.
2. **Informe Mensal Estruturado.**  ``VL_DICRED`` at zero across the entire
   history plus FIDC quotas above half of the applications.  This is the rule
   that found the vehicles the flag misses, and it is quantitative: it reads
   what the fund holds, not what it is called.
3. **The name.**  Weakest by far, and *never* decisive on its own here.  In
   this base 257 confirmed FICs carry no form of "FIC" in the registered name,
   so a name rule would have missed most of them; and a name can say "FIC"
   while the fund buys receivables directly.  The name is kept as a
   cross-check that surfaces candidates for human review.

When the name matches "FIC" as an isolated token, the detector must not fire on
``FICÇÃO``, ``SIFIC``, ``FIC123`` or any sequence where the letters are welded
to something else.  Delimiters are the string boundaries, whitespace, hyphens,
slashes, parentheses and punctuation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import pandas as pd


#: Letter or digit, accented characters included; underscore deliberately out,
#: so ``FIC_X`` reads as delimited rather than welded.
_ALPHANUMERIC = r"[^\W_]"

#: "FIC" as a standalone token.  The lookarounds are what keep ``FICÇÃO`` and
#: ``SIFIC`` from matching: the neighbouring character must not be alphanumeric.
FIC_TOKEN_PATTERN = re.compile(
    rf"(?<!{_ALPHANUMERIC})FIC(?!{_ALPHANUMERIC})", re.IGNORECASE | re.UNICODE
)

#: The legal form spelled out.  ``FUNDO DE INVESTIMENTO EM COTAS`` and the
#: abbreviations the registry actually uses for it.
FIC_PHRASE_PATTERN = re.compile(
    r"(?<!\w)(?:FUNDO\s+DE\s+INVESTIMENTO|FI|F\.?I\.?)\s+EM\s+COTAS(?!\w)",
    re.IGNORECASE | re.UNICODE,
)

#: Detection methods, strongest first.  ``fic_detection_method`` carries one.
METHOD_REGISTRY = "flag_cadastral"
METHOD_INFORME = "informe_mensal"
METHOD_COMBINED = "combinacao"
METHOD_NAME = "nome_token_fic"
METHOD_MANUAL = "revisao_manual"
METHOD_NONE = ""

#: Methods that are strong enough to remove a fund from the universe.  The name
#: is not among them, on purpose.
DECISIVE_METHODS: frozenset[str] = frozenset(
    {METHOD_REGISTRY, METHOD_INFORME, METHOD_COMBINED, METHOD_MANUAL}
)

AUDIT_COLUMNS: tuple[str, ...] = (
    "cnpj_fundo",
    "denominacao",
    "competencia",
    "is_fic",
    "fic_detection_method",
    "fic_detection_evidence",
    "fic_exclusion_reason",
    "revisao_manual_sugerida",
    "motivo_revisao",
    "pl",
)

_TRUE_VALUES = {"true", "1", "sim", "t", "yes"}


@dataclass(frozen=True)
class ExclusionReport:
    """What the exclusion gate removed, for the manifest and the audit trail."""

    rows_in: int
    rows_out: int
    cnpj_excluded: int
    pl_excluded_last_competence_brl: float
    last_competence: str

    @property
    def rows_excluded(self) -> int:
        return self.rows_in - self.rows_out


def _truthy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.casefold().isin(_TRUE_VALUES)


def name_says_fic(name: str) -> str:
    """Return the evidence when the name carries FIC as an isolated token.

    Empty string means the name says nothing.  A non-empty return is a *lead*,
    never a verdict: the caller still needs a stronger source to exclude.
    """

    text = str(name or "")
    if not text.strip():
        return ""
    reasons: list[str] = []
    token = FIC_TOKEN_PATTERN.search(text)
    if token is not None:
        reasons.append(f"token isolado '{token.group(0)}' na denominação")
    phrase = FIC_PHRASE_PATTERN.search(text)
    if phrase is not None:
        reasons.append(f"forma legal '{phrase.group(0).strip()}' na denominação")
    return "; ".join(reasons)


def annotate_fic_detection(
    frame: pd.DataFrame,
    *,
    curated_cnpjs: Iterable[str] = (),
    curated_evidence: dict[str, str] | None = None,
    cnpj_column: str = "cnpj_fundo",
    name_column: str = "denominacao",
    flag_column: str = "is_fic_fidc",
) -> pd.DataFrame:
    """Add ``is_fic`` and the three audit columns to a monthly base.

    ``curated_cnpjs`` are the vehicles the Informe Mensal review confirmed.  The
    name is evaluated for every row, but only ever *raises a question*: a fund
    whose name says FIC while neither the flag nor the informe agrees is left in
    the universe and flagged for manual review, because the name is the weakest
    of the three sources and excluding on it would be the false positive this
    audit exists to prevent.
    """

    from services.industry_taxonomy_review import normalize_cnpj

    result = frame.copy()
    if cnpj_column not in result.columns:
        raise KeyError(f"coluna ausente para detecção de FIC: {cnpj_column}")

    keys = result[cnpj_column].map(normalize_cnpj)
    curated = {normalize_cnpj(cnpj) for cnpj in curated_cnpjs}
    curated_evidence = {
        normalize_cnpj(cnpj): text for cnpj, text in (curated_evidence or {}).items()
    }

    registry = (
        _truthy(result[flag_column])
        if flag_column in result.columns
        else pd.Series(False, index=result.index)
    )
    from_informe = keys.isin(curated)
    names = (
        result[name_column]
        if name_column in result.columns
        else pd.Series("", index=result.index)
    )
    name_evidence = names.map(name_says_fic)
    from_name = name_evidence.str.len().gt(0)

    is_fic = registry | from_informe
    method = pd.Series(METHOD_NONE, index=result.index, dtype="object")
    method[from_informe] = METHOD_INFORME
    method[registry] = METHOD_REGISTRY
    method[registry & from_informe] = METHOD_COMBINED

    evidence = pd.Series("", index=result.index, dtype="object")
    evidence[registry] = "Informe mensal CVM: campo is_fic_fidc reportado como verdadeiro."
    evidence[from_informe] = keys[from_informe].map(
        lambda cnpj: curated_evidence.get(cnpj, "")
        or (
            "Informe Mensal Estruturado: nenhum direito creditório em toda a série "
            "e cotas de FIDC acima de metade das aplicações."
        )
    )
    combined = registry & from_informe
    evidence[combined] = (
        "Flag is_fic_fidc verdadeira e confirmada pelo Informe Mensal Estruturado: "
        "sem direitos creditórios em toda a série, cotas de FIDC acima de metade "
        "das aplicações."
    )
    # O nome nunca decide, mas quando concorda vira reforço registrado.
    reinforced = is_fic & from_name
    evidence[reinforced] = evidence[reinforced].str.cat(
        name_evidence[reinforced].radd("Reforçado pelo nome: "), sep=" "
    )

    reason = pd.Series("", index=result.index, dtype="object")
    reason[is_fic] = (
        "Detém cotas de outros FIDCs em vez de adquirir direitos creditórios; o "
        "patrimônio alimenta o saldo de FIC e sai dos quatro tipos ANBIMA, "
        "evitando dupla contagem do mesmo patrimônio."
    )

    # Nome diz FIC e nenhuma fonte forte confirma: candidato a falso negativo da
    # regra quantitativa. Fica no universo e vai para revisão humana.
    ambiguous = from_name & ~is_fic
    review_reason = pd.Series("", index=result.index, dtype="object")
    review_reason[ambiguous] = (
        "Nome sugere FIC, mas o informe mensal mostra aquisição de direitos "
        "creditórios ou cotas abaixo do limiar. Possível falso negativo da regra "
        "quantitativa; permanece no universo até revisão documental."
    )
    evidence[ambiguous] = name_evidence[ambiguous]
    method[ambiguous] = METHOD_NAME

    result["is_fic"] = is_fic
    result["fic_detection_method"] = method
    result["fic_detection_evidence"] = evidence
    result["fic_exclusion_reason"] = reason
    result["revisao_manual_sugerida"] = ambiguous
    result["motivo_revisao"] = review_reason
    return result


def exclude_fics_from_fidc_universe(
    frame: pd.DataFrame,
    *,
    flag_column: str = "is_fic",
    fallback_flag_column: str = "is_fic_fidc",
    cnpj_column: str = "cnpj_fundo",
    pl_column: str = "pl",
    competence_column: str = "competencia",
) -> tuple[pd.DataFrame, ExclusionReport]:
    """Remove every FIC from the population, once, before anything else runs.

    This is the single gate.  Every derived dataset — charts, aggregations,
    rankings, taxonomy, Excel, bundle, PPTX — must come from what this returns,
    so the rule cannot drift between one screen and the next.

    ``is_fic`` is preferred; ``is_fic_fidc`` is accepted so a frame that never
    went through :func:`annotate_fic_detection` is still filtered rather than
    silently passed through unfiltered.
    """

    if frame is None or frame.empty:
        empty = frame if frame is not None else pd.DataFrame()
        return empty, ExclusionReport(0, 0, 0, 0.0, "")

    column = (
        flag_column
        if flag_column in frame.columns
        else (fallback_flag_column if fallback_flag_column in frame.columns else "")
    )
    if not column:
        raise KeyError(
            "universo sem coluna de FIC: passe o frame por annotate_fic_detection "
            "antes de agregar, sob pena de contar o mesmo patrimônio duas vezes"
        )

    excluded = _truthy(frame[column])
    kept = frame[~excluded].copy()

    last_competence = ""
    pl_excluded = 0.0
    if competence_column in frame.columns:
        competences = frame.loc[excluded, competence_column].astype(str)
        if not competences.empty:
            last_competence = str(competences.max())
            if pl_column in frame.columns:
                final = excluded & frame[competence_column].astype(str).eq(
                    last_competence
                )
                pl_excluded = float(
                    pd.to_numeric(frame.loc[final, pl_column], errors="coerce")
                    .fillna(0.0)
                    .sum()
                )
    cnpj_count = (
        int(frame.loc[excluded, cnpj_column].nunique())
        if cnpj_column in frame.columns
        else 0
    )
    return kept, ExclusionReport(
        rows_in=int(len(frame)),
        rows_out=int(len(kept)),
        cnpj_excluded=cnpj_count,
        pl_excluded_last_competence_brl=pl_excluded,
        last_competence=last_competence,
    )


def split_fidc_universe(
    frame: pd.DataFrame, **kwargs: object
) -> tuple[pd.DataFrame, pd.DataFrame, ExclusionReport]:
    """Return the eligible universe, the excluded FICs, and what moved.

    Both sides are needed.  The eligible frame feeds every analytical product;
    the excluded frame feeds the FIC net-asset balance, which is the whole point
    of taking those funds out of the types rather than deleting them.  Dropping
    the excluded rows outright would zero the balance the exclusion exists to
    build.
    """

    kept, report = exclude_fics_from_fidc_universe(frame, **kwargs)  # type: ignore[arg-type]
    if frame is None or frame.empty:
        return kept, pd.DataFrame(columns=getattr(frame, "columns", None)), report
    column = "is_fic" if "is_fic" in frame.columns else "is_fic_fidc"
    excluded = frame[_truthy(frame[column])].copy()
    return kept, excluded, report


def assert_universe_excludes_fics(
    frame: pd.DataFrame,
    excluded_cnpjs: Iterable[str],
    *,
    label: str,
    cnpj_column: str = "cnpj_fundo",
) -> None:
    """Fail loudly when a FIC reaches a product that must not contain one.

    Called on the aggregations, rankings and exports.  The rule is centralized
    upstream, but a silent regression downstream is exactly the failure this
    guard exists to make impossible.
    """

    if frame is None or frame.empty or cnpj_column not in frame.columns:
        return
    from services.industry_taxonomy_review import normalize_cnpj

    targets = {normalize_cnpj(cnpj) for cnpj in excluded_cnpjs}
    if not targets:
        return
    present = set(frame[cnpj_column].map(normalize_cnpj)) & targets
    if present:
        sample = ", ".join(sorted(present)[:5])
        raise AssertionError(
            f"{label}: {len(present)} CNPJ marcados como FIC alcançaram um produto "
            f"analítico que deve excluí-los ({sample})"
        )


def build_fic_audit(
    frame: pd.DataFrame,
    *,
    cnpj_column: str = "cnpj_fundo",
    name_column: str = "denominacao",
) -> pd.DataFrame:
    """One row per CNPJ and competence for every fund the detector touched.

    Carries both the excluded funds and the ambiguous ones, so a reviewer can
    see the false negatives the name caught and the false positives the name
    would have caused had it been allowed to decide.
    """

    required = {"is_fic", "fic_detection_method"}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"base sem anotação de FIC: {sorted(missing)}")

    touched = frame[frame["is_fic"] | frame["revisao_manual_sugerida"]].copy()
    if touched.empty:
        return pd.DataFrame(columns=list(AUDIT_COLUMNS))
    touched = touched.rename(
        columns={cnpj_column: "cnpj_fundo", name_column: "denominacao"}
    )
    for column in AUDIT_COLUMNS:
        if column not in touched.columns:
            touched[column] = ""
    audit = touched[list(AUDIT_COLUMNS)].sort_values(
        ["is_fic", "pl", "cnpj_fundo"], ascending=[False, False, True]
    )
    return audit.reset_index(drop=True)
