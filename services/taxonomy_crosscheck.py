"""Cross-check the analytical taxonomy for internal contradictions.

Every rule here answers one question: does this decision contradict something
the project already knows?  A contradiction is not a verdict — the classifier
may be right and the rule too blunt — so nothing is rewritten automatically.
Each finding carries the evidence and a suggested action, and ambiguity is
reported as ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from services.industry_taxonomy_review import (
    ANALYTICAL_ANBIMA_FOCUS_BY_TYPE,
    load_taxonomy_review_actions,
    normalize_cnpj,
)


FINDING_COLUMNS: tuple[str, ...] = (
    "regra",
    "cnpj_fundo",
    "nome_fidc",
    "competencias_afetadas",
    "pl_max",
    "classificacao_atual",
    "classificacao_potencial",
    "motivo",
    "evidencia",
    "acao_sugerida",
)

ACTION_KEEP = "manter"
ACTION_REVIEW = "revisar manualmente"
ACTION_BACKEND = "corrigir via backend"

#: Tabela II ↔ taxonomia funcional N1, escrito com o vocabulário que o projeto
#: realmente usa (``FUNCTIONAL_TAXONOMY``), não com rótulos inventados.  Um par
#: fora desta tabela não é erro por si — é uma combinação que ninguém declarou
#: coerente e que pede olho humano.
#:
#: ``Multissetorial / Outros`` é aceito em toda parte de propósito: é o N1 de
#: quem tem carteira diversificada, e uma Tabela II específica com carteira
#: diversificada é assunto da regra de multicarteira, não desta.
_UNIVERSAL_N1 = frozenset({"Multissetorial / Outros", ""})
_TABLE_II_TO_N1: dict[str, frozenset[str]] = {
    "Factoring": frozenset({"Crédito PJ"}) | _UNIVERSAL_N1,
    "Cartão de crédito": frozenset({"Meios de Pagamento e Cartões", "Crédito PF"})
    | _UNIVERSAL_N1,
    "Adquirência": frozenset({"Meios de Pagamento e Cartões", "Crédito PJ"})
    | _UNIVERSAL_N1,
    "Setor público": frozenset({"Judicial/Precatórios/NPL", "Crédito PJ", "Infra/Energia"})
    | _UNIVERSAL_N1,
    "Ações judiciais": frozenset({"Judicial/Precatórios/NPL"}) | _UNIVERSAL_N1,
    "Agronegócio": frozenset({"Agro", "Crédito PJ"}) | _UNIVERSAL_N1,
    "Imobiliário": frozenset({"Imobiliário", "Crédito PF", "Crédito PJ"}) | _UNIVERSAL_N1,
    "Industrial": frozenset({"Crédito PJ", "Infra/Energia"}) | _UNIVERSAL_N1,
    "Comercial": frozenset({"Crédito PJ", "Crédito PF"}) | _UNIVERSAL_N1,
    "Serviços": frozenset({"Crédito PJ", "Infra/Energia", "Crédito PF"}) | _UNIVERSAL_N1,
    "Financeiro": frozenset(
        {"Crédito PJ", "Crédito PF", "Judicial/Precatórios/NPL", "Meios de Pagamento e Cartões"}
    )
    | _UNIVERSAL_N1,
    "Marcas e patentes": frozenset({"Crédito PJ"}) | _UNIVERSAL_N1,
}

#: Termos que denunciam risco de banco emissor numa evidência de adquirência, e
#: vice-versa.  A distinção decide quem é o devedor final do recebível.
_ISSUER_TERMS = (
    "banco emissor",
    "risco do emissor",
    "emissor do cartão",
    "bandeira e emissor",
)
_ACQUIRER_TERMS = (
    "credenciadora",
    "adquirente",
    "subadquirente",
    "arranjo de pagamento",
)
_BNPL_TERMS = ("bnpl", "buy now", "pague depois", "parcelado sem cartão", "crediário")

_MULTICARTEIRA_TERMS = ("multicarteira", "diversificada", "multissetorial")

#: Abaixo disto uma evidência não sustenta uma aprovação.
MIN_EVIDENCE_LENGTH = 120


@dataclass(frozen=True)
class CrosscheckSummary:
    findings: int
    by_rule: dict[str, int]
    pl_involved_brl: float


_FAMILY_TAG = re.compile(r"\[[^\]]*\]")
#: Trechos que a própria curadoria escreve nas notas: escores por família e
#: lista de documentos lidos. Casar contra eles é ler a conclusão como prova.
_SELF_REPORTED = re.compile(
    r"(?:escores documentais|documentos lidos)\s*:[^.]*\.?", re.IGNORECASE
)


def _documentary_text(text: str) -> str:
    """Return only what the document says, stripped of the classifier's own output.

    The evidence field carries the family label in brackets and the notes carry
    the family scores.  Both repeat the conclusion, so matching a rule against
    them would confirm the classification with itself.
    """

    cleaned = _FAMILY_TAG.sub(" ", str(text or ""))
    return _SELF_REPORTED.sub(" ", cleaned).casefold()


def _finding(
    rule: str,
    row: pd.Series,
    *,
    potential: str,
    reason: str,
    evidence: str,
    action: str,
) -> dict[str, object]:
    return {
        "regra": rule,
        "cnpj_fundo": str(row.get("cnpj_fundo") or ""),
        "nome_fidc": str(row.get("denominacao_referencia") or row.get("nome_fidc") or ""),
        "competencias_afetadas": str(row.get("competencias_afetadas") or ""),
        "pl_max": float(row.get("pl_max") or 0.0),
        "classificacao_atual": " | ".join(
            str(row.get(column) or "—")
            for column in (
                "tipo_analitico",
                "foco_analitico",
                "tabela_ii_analitica",
                "taxonomia_funcional_n1",
                "taxonomia_funcional_n2",
            )
        ),
        "classificacao_potencial": potential,
        "motivo": reason,
        "evidencia": str(evidence or "")[:1200],
        "acao_sugerida": action,
    }


def crosscheck_taxonomy(
    ledger: pd.DataFrame,
    *,
    published: pd.DataFrame | None = None,
    exported: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one row per contradiction found in the approved taxonomy."""

    if ledger is None or ledger.empty:
        return pd.DataFrame(columns=list(FINDING_COLUMNS))

    frame = ledger.copy()
    frame["cnpj_fundo"] = frame["cnpj_fundo"].map(normalize_cnpj)
    for column in FINDING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    approved = frame[frame["status"].astype(str).eq("aprovado")]
    findings: list[dict[str, object]] = []

    for _, row in approved.iterrows():
        tipo = str(row.get("tipo_analitico") or "").strip()
        foco = str(row.get("foco_analitico") or "").strip()
        tabela = str(row.get("tabela_ii_analitica") or "").strip()
        n1 = str(row.get("taxonomia_funcional_n1") or "").strip()
        n2 = str(row.get("taxonomia_funcional_n2") or "").strip()
        evidence = str(row.get("evidencia") or "")
        notes = str(row.get("notas") or "")
        # O texto entre colchetes é o rótulo de família que o próprio
        # classificador escreveu, e casar contra ele é ler a conclusão como se
        # fosse a prova. Só o trecho documental entra na busca.
        haystack = _documentary_text(f"{evidence} {notes}")

        # 1. Tipo incompatível com Foco.
        allowed_focus = set(ANALYTICAL_ANBIMA_FOCUS_BY_TYPE.get(tipo, ()))
        if tipo and foco and allowed_focus and foco not in allowed_focus:
            findings.append(
                _finding(
                    "tipo_incompativel_com_foco",
                    row,
                    potential=f"{tipo} com foco de sua própria lista",
                    reason=(
                        f"O foco '{foco}' não pertence ao vocabulário do tipo '{tipo}'."
                    ),
                    evidence=evidence,
                    action=ACTION_BACKEND,
                )
            )

        # 2. Tabela II incompatível com a funcional N1.
        expected_n1 = _TABLE_II_TO_N1.get(tabela)
        if expected_n1 and n1 and n1 not in expected_n1:
            findings.append(
                _finding(
                    "tabela_ii_incompativel_com_funcional",
                    row,
                    potential=f"{tabela} com N1 em {sorted(expected_n1)}",
                    reason=(
                        f"Tabela II '{tabela}' costuma acompanhar N1 "
                        f"{sorted(expected_n1)}, e a decisão traz '{n1}'."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )

        # 3 e 4. Adquirência versus risco de banco emissor.
        is_acquiring = "adquir" in f"{tabela} {foco} {n1} {n2}".casefold()
        issuer_evidence = any(term in haystack for term in _ISSUER_TERMS)
        acquirer_evidence = any(term in haystack for term in _ACQUIRER_TERMS)
        if is_acquiring and issuer_evidence and not acquirer_evidence:
            findings.append(
                _finding(
                    "adquirencia_com_evidencia_de_emissor",
                    row,
                    potential="Cartão de crédito / risco de banco emissor",
                    reason=(
                        "Classificado em adquirência, mas a evidência fala em risco "
                        "do banco emissor, que é o devedor oposto."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )
        is_issuer = "cartão de crédito" in f"{tabela} {foco}".casefold()
        if is_issuer and acquirer_evidence and not issuer_evidence:
            findings.append(
                _finding(
                    "emissor_com_evidencia_de_credenciadora",
                    row,
                    potential="Adquirência / recebíveis de arranjo de pagamento",
                    reason=(
                        "Classificado como cartão de crédito com risco de emissor, "
                        "mas a evidência descreve credenciadora ou subadquirente."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )

        # 5. BNPL / crédito PF classificado como adquirência.
        if is_acquiring and any(term in haystack for term in _BNPL_TERMS):
            findings.append(
                _finding(
                    "bnpl_classificado_como_adquirencia",
                    row,
                    potential="Financeiro / Crédito PF",
                    reason=(
                        "A evidência descreve BNPL ou crédito direto ao consumidor, "
                        "cujo devedor é a pessoa física, não o arranjo de pagamento."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )

        # 6. Multicarteira com classificação específica demais.
        specific = tabela not in {"", "N/D"} and "multicarteira" not in foco.casefold()
        if specific and any(term in haystack for term in _MULTICARTEIRA_TERMS):
            findings.append(
                _finding(
                    "multicarteira_com_classificacao_especifica",
                    row,
                    potential=f"{tipo} / Multicarteira",
                    reason=(
                        "A evidência descreve carteira diversificada, mas a decisão "
                        "fixa um segmento específico sem declarar predominância."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )

        # 7. Aprovação sem evidência suficiente.
        if len(evidence.strip()) < MIN_EVIDENCE_LENGTH:
            findings.append(
                _finding(
                    "aprovado_sem_evidencia_suficiente",
                    row,
                    potential="em revisão até haver leitura documental",
                    reason=(
                        f"Decisão aprovada com evidência de {len(evidence.strip())} "
                        f"caracteres, abaixo do mínimo de {MIN_EVIDENCE_LENGTH}."
                    ),
                    evidence=evidence,
                    action=ACTION_REVIEW,
                )
            )

    # 8. Divergência entre aprovado, publicado e exportado.
    findings.extend(_diff_against(approved, published, "publicada"))
    findings.extend(_diff_against(approved, exported, "exportada"))

    # 9. CNPJ repetido com classificações diferentes.
    duplicated = frame[frame["cnpj_fundo"].duplicated(keep=False)]
    for cnpj, group in duplicated.groupby("cnpj_fundo"):
        distinct = group[["tipo_analitico", "foco_analitico"]].drop_duplicates()
        if len(distinct) > 1:
            row = group.iloc[0]
            findings.append(
                _finding(
                    "cnpj_com_classificacoes_divergentes",
                    row,
                    potential="uma decisão única por CNPJ",
                    reason=(
                        f"O CNPJ carrega {len(distinct)} combinações Tipo/Foco "
                        "distintas no ledger, quando deveria haver uma só."
                    ),
                    evidence="; ".join(
                        f"{tipo} / {foco}"
                        for tipo, foco in distinct.itertuples(index=False)
                    ),
                    action=ACTION_BACKEND,
                )
            )

    if not findings:
        return pd.DataFrame(columns=list(FINDING_COLUMNS))
    result = pd.DataFrame(findings, columns=list(FINDING_COLUMNS))
    return result.sort_values(["pl_max", "regra"], ascending=[False, True]).reset_index(
        drop=True
    )


def _diff_against(
    approved: pd.DataFrame, other: pd.DataFrame | None, label: str
) -> list[dict[str, object]]:
    """Compare the approved decision with what a downstream product carries."""

    if other is None or other.empty or approved.empty:
        return []
    comparison = other.copy()
    if "cnpj_fundo" not in comparison.columns:
        return []
    comparison["cnpj_fundo"] = comparison["cnpj_fundo"].map(normalize_cnpj)
    columns = [
        column
        for column in ("tipo_analitico", "foco_analitico")
        if column in comparison.columns
    ]
    if not columns:
        return []
    merged = approved.merge(
        comparison[["cnpj_fundo", *columns]].drop_duplicates("cnpj_fundo"),
        on="cnpj_fundo",
        how="inner",
        suffixes=("", "_outro"),
    )
    findings: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        divergent = [
            column
            for column in columns
            if str(row[column] or "").strip() != str(row[f"{column}_outro"] or "").strip()
        ]
        if not divergent:
            continue
        findings.append(
            _finding(
                f"divergencia_aprovada_versus_{label}",
                row,
                potential=" | ".join(str(row[f"{column}_outro"]) for column in divergent),
                reason=(
                    f"A decisão aprovada difere da classificação {label} em "
                    f"{', '.join(divergent)}."
                ),
                evidence=str(row.get("evidencia") or ""),
                action=ACTION_BACKEND,
            )
        )
    return findings


def summarize(findings: pd.DataFrame) -> CrosscheckSummary:
    if findings.empty:
        return CrosscheckSummary(0, {}, 0.0)
    return CrosscheckSummary(
        findings=len(findings),
        by_rule=findings["regra"].value_counts().to_dict(),
        pl_involved_brl=float(
            findings.drop_duplicates("cnpj_fundo")["pl_max"].sum()
        ),
    )


def load_ledger_for_crosscheck(data_dir: Path) -> pd.DataFrame:
    """Read the ledger and attach the PL and competences of each CNPJ."""

    data_dir = Path(data_dir)
    ledger = load_taxonomy_review_actions(data_dir / "taxonomy_review_actions.csv")
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    ledger["cnpj_fundo"] = ledger["cnpj_fundo"].map(normalize_cnpj)
    base_path = data_dir / "generated_revision" / "base_fundo_cnpj.csv.gz"
    if not base_path.exists():
        ledger["pl_max"] = 0.0
        ledger["competencias_afetadas"] = ""
        return ledger
    base = pd.read_csv(
        base_path,
        dtype=str,
        keep_default_na=False,
        usecols=["competencia", "cnpj_fundo", "pl"],
    )
    base["pl"] = pd.to_numeric(base["pl"], errors="coerce").fillna(0.0)
    grouped = base.groupby("cnpj_fundo").agg(
        pl_max=("pl", "max"),
        competencias_afetadas=("competencia", lambda values: ", ".join(sorted(set(values))[-4:])),
    )
    return ledger.merge(grouped, on="cnpj_fundo", how="left").fillna(
        {"pl_max": 0.0, "competencias_afetadas": ""}
    )
