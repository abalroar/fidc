"""Import the June/2026 audited FIDC taxonomy workbook deterministically.

The source workbook is a curation hand-off, not a replacement for the official
ANBIMA/CVM fields.  This module normalizes its four audit sheets, validates the
closed 19 Type migrations plus 18 Focus-only decisions and prepares one
auditable ledger transaction.  Official values remain available through the
taxonomy overlay; only the analytical fields are changed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from services.industry_taxonomy_review import (
    CVM_TABLE_II_CATEGORIES,
    FUNCTIONAL_TAXONOMY,
    TAXONOMY_REVIEW_COLUMNS,
    load_taxonomy_review_actions,
    normalize_cnpj,
    valid_analytical_type_focus_pair,
)


DECISIONS_SHEET = "De-para reclassificação"
TOP200_SHEET = "Auditoria classificação Top200"
OUTROS_SHEET = "Outros · 3 baldes"
SUMMARY_SHEET = "Sumário da auditoria"
ACQUIRING_SHEET = "Taxonomia adquirência"

EXPECTED_DECISION_COUNTS = {"Migra de Tipo": 19, "Só Foco": 18}
EXPECTED_TYPE_MIGRATION_PL_BRL = 66_794_750_779.89
EXPECTED_FOCUS_ONLY_PL_BRL = 55_694_538_021.58
EXPECTED_TOP200_ROWS = 200
EXPECTED_OUTROS_ROWS = 76
EXPECTED_ACQUIRING_ROWS = 33
EXPECTED_F8_ROWS = 68
EXPECTED_F8_PL_BRL = 113_372_908_354.69

SELLER3_CNPJ = "63572282000111"
AETOS_CNPJ = "52610624000124"

DECISION_SOURCE_COLUMNS: tuple[str, ...] = (
    "CNPJ",
    "FIDC",
    "PL (R$)",
    "Tipo atual",
    "Foco atual",
    "Tipo proposto",
    "Foco proposto",
    "Efeito",
)

TOP200_DECISION_COLUMNS: tuple[str, ...] = (
    "CNPJ",
    "PL (R$)",
    "Tipo ANBIMA atual",
    "Foco ANBIMA atual",
    "Confiabilidade da Tabela II",
    "Veredito documental",
    "Evidência no regulamento",
    "Documento FundosNET (id)",
    "Recomendação",
)

NORMALIZED_DECISIONS_FILENAME = "industry_taxonomy_audited_decisions_202606.csv"
NORMALIZED_TOP200_FILENAME = "industry_taxonomy_audit_top200_202606.csv.gz"
NORMALIZED_OUTROS_FILENAME = "industry_taxonomy_outros_three_buckets_202606.csv"
NORMALIZED_ACQUIRING_FILENAME = "industry_taxonomy_acquiring_202606.csv"
NORMALIZED_MANIFEST_FILENAME = "industry_taxonomy_audit_manifest_202606.json"


class TaxonomyAuditImportError(RuntimeError):
    """Raised when the source-of-truth workbook violates its known contract."""


@dataclass(frozen=True)
class ImportedTaxonomyAudit:
    decisions: pd.DataFrame
    top200: pd.DataFrame
    outros: pd.DataFrame
    acquiring: pd.DataFrame
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _read_sheet(
    path: Path,
    sheet: str,
    *,
    header: int | None = 3,
) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=header, dtype=object)


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    *,
    sheet: str,
) -> None:
    missing = set(columns).difference(frame.columns)
    if missing:
        raise TaxonomyAuditImportError(
            f"{sheet} sem colunas obrigatórias: " + ", ".join(sorted(missing))
        )


def _normalize_cnpj_frame(
    frame: pd.DataFrame,
    *,
    sheet: str,
    expected_rows: int,
) -> pd.DataFrame:
    """Keep source rows with a valid fund key and enforce the closed perimeter."""

    _require_columns(frame, ("CNPJ",), sheet=sheet)
    out = frame.dropna(how="all").copy()
    out["cnpj_fundo"] = out["CNPJ"].map(normalize_cnpj)
    out = out[out["cnpj_fundo"].str.len().eq(14)].copy()
    if len(out) != expected_rows:
        raise TaxonomyAuditImportError(
            f"{sheet} deveria conter {expected_rows} CNPJs válidos; contém {len(out)}"
        )
    duplicated = out.loc[out["cnpj_fundo"].duplicated(False), "cnpj_fundo"].unique()
    if len(duplicated):
        raise TaxonomyAuditImportError(
            f"{sheet} contém CNPJ duplicado: " + ", ".join(sorted(duplicated))
        )
    return out.reset_index(drop=True)


def _normalize_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(frame, DECISION_SOURCE_COLUMNS, sheet=DECISIONS_SHEET)
    # A tuple fixes the emitted CSV order across Python hash seeds.
    out = frame.loc[:, list(DECISION_SOURCE_COLUMNS)].copy()
    out["cnpj_fundo"] = out["CNPJ"].map(normalize_cnpj)
    out = out[out["cnpj_fundo"].str.len().eq(14)].copy()
    out = out.rename(
        columns={
            "FIDC": "denominacao_referencia",
            "PL (R$)": "pl_brl",
            "Tipo atual": "tipo_atual",
            "Foco atual": "foco_atual",
            "Tipo proposto": "tipo_proposto",
            "Foco proposto": "foco_proposto",
            "Efeito": "efeito",
        }
    ).drop(columns="CNPJ")
    for column in (
        "denominacao_referencia",
        "tipo_atual",
        "foco_atual",
        "tipo_proposto",
        "foco_proposto",
        "efeito",
    ):
        out[column] = out[column].map(_slug)
    out["pl_brl"] = pd.to_numeric(out["pl_brl"], errors="coerce")
    out = out.sort_values("pl_brl", ascending=False).reset_index(drop=True)
    if out["cnpj_fundo"].duplicated().any():
        raise TaxonomyAuditImportError("de-para contém CNPJ duplicado")
    counts = out["efeito"].value_counts().to_dict()
    if counts != EXPECTED_DECISION_COUNTS:
        raise TaxonomyAuditImportError(
            f"de-para deveria conter {EXPECTED_DECISION_COUNTS}; recebeu {counts}"
        )
    if out["pl_brl"].isna().any():
        raise TaxonomyAuditImportError("de-para contém PL ausente ou não numérico")
    invalid_pairs = out[
        ~out.apply(
            lambda row: valid_analytical_type_focus_pair(
                row["tipo_proposto"], row["foco_proposto"]
            ),
            axis=1,
        )
    ]
    if not invalid_pairs.empty:
        raise TaxonomyAuditImportError(
            "de-para contém combinação Tipo/Foco inválida: "
            + ", ".join(invalid_pairs["cnpj_fundo"].tolist())
        )
    migrated_pl = float(
        out.loc[out["efeito"].eq("Migra de Tipo"), "pl_brl"].sum()
    )
    focus_pl = float(out.loc[out["efeito"].eq("Só Foco"), "pl_brl"].sum())
    if abs(migrated_pl - EXPECTED_TYPE_MIGRATION_PL_BRL) > 0.01:
        raise TaxonomyAuditImportError(
            f"PL das migrações de Tipo divergente: {migrated_pl:.2f}"
        )
    if abs(focus_pl - EXPECTED_FOCUS_ONLY_PL_BRL) > 0.01:
        raise TaxonomyAuditImportError(
            f"PL das mudanças só de Foco divergente: {focus_pl:.2f}"
        )
    return out


def _decision_join_checks(
    decisions: pd.DataFrame,
    top200: pd.DataFrame,
) -> dict[str, Any]:
    _require_columns(top200, TOP200_DECISION_COLUMNS, sheet=TOP200_SHEET)
    decision_keys = set(decisions["cnpj_fundo"])
    top200_keys = set(top200["cnpj_fundo"])
    missing = sorted(decision_keys.difference(top200_keys))
    if missing:
        raise TaxonomyAuditImportError(
            "de-para não fecha 37/37 com o Top200; ausentes: " + ", ".join(missing)
        )
    joined = decisions.merge(
        top200.loc[
            :,
            [
                "cnpj_fundo",
                "PL (R$)",
                "Tipo ANBIMA atual",
                "Foco ANBIMA atual",
                "Evidência no regulamento",
                "Documento FundosNET (id)",
                "Recomendação",
            ],
        ],
        on="cnpj_fundo",
        how="left",
        validate="one_to_one",
    )
    if len(joined) != sum(EXPECTED_DECISION_COUNTS.values()):
        raise TaxonomyAuditImportError(
            f"de-para deveria fechar 37/37 com o Top200; fechou {len(joined)}/37"
        )

    top_pl = pd.to_numeric(joined["PL (R$)"], errors="coerce")
    bad_pl = joined.loc[(top_pl - joined["pl_brl"]).abs().gt(0.01), "cnpj_fundo"]
    if top_pl.isna().any() or not bad_pl.empty:
        bad = set(bad_pl.tolist())
        bad.update(joined.loc[top_pl.isna(), "cnpj_fundo"].tolist())
        raise TaxonomyAuditImportError(
            "PL do de-para diverge do Top200: " + ", ".join(sorted(bad))
        )

    comparisons = (
        ("tipo_atual", "Tipo ANBIMA atual", "Tipo atual"),
        ("foco_atual", "Foco ANBIMA atual", "Foco atual"),
    )
    for decision_column, top_column, label in comparisons:
        left = joined[decision_column].map(_slug)
        right = joined[top_column].map(_slug)
        bad = joined.loc[left.ne(right), "cnpj_fundo"].tolist()
        if bad:
            raise TaxonomyAuditImportError(
                f"{label} do de-para diverge do Top200: "
                + ", ".join(sorted(bad))
            )

    for column in (
        "Evidência no regulamento",
        "Documento FundosNET (id)",
        "Recomendação",
    ):
        missing_documentation = joined.loc[
            joined[column].map(_slug).eq(""), "cnpj_fundo"
        ].tolist()
        if missing_documentation:
            raise TaxonomyAuditImportError(
                f"decisões sem {column} no Top200: "
                + ", ".join(sorted(missing_documentation))
            )
    return {
        "decision_top200_join_count": int(len(joined)),
        "decision_current_pl_matches": True,
        "decision_current_type_matches": True,
        "decision_current_focus_matches": True,
        "decision_documentation_complete": True,
    }


def _summary_entry(
    summary: pd.DataFrame,
    label: str,
) -> tuple[str, float | None]:
    """Return the narrative and numeric value following an exact summary label."""

    for _, row in summary.iterrows():
        values = row.tolist()
        for index, value in enumerate(values):
            if _slug(value) != label:
                continue
            trailing = values[index + 1 :]
            narrative = next(
                (
                    _slug(item)
                    for item in trailing
                    if _slug(item) and not isinstance(item, (int, float))
                ),
                "",
            )
            numerics = [
                float(item)
                for item in trailing
                if isinstance(item, (int, float)) and not pd.isna(item)
            ]
            return narrative, numerics[-1] if numerics else None
    raise TaxonomyAuditImportError(f"sumário sem a linha obrigatória: {label}")


def _summary_count(narrative: str, *, label: str) -> int:
    match = re.search(r"\b(\d+)\s+(?:fundos?|maiores)\b", narrative, flags=re.I)
    if not match:
        raise TaxonomyAuditImportError(
            f"sumário sem contagem legível na linha {label}: {narrative}"
        )
    return int(match.group(1))


def _assert_summary_money(label: str, actual: float | None, expected: float) -> None:
    if actual is None or abs(actual - expected) > 0.01:
        rendered = "N/D" if actual is None else f"{actual:.2f}"
        raise TaxonomyAuditImportError(
            f"sumário diverge em {label}: {rendered}; esperado {expected:.2f}"
        )


def _validate_summary(
    summary: pd.DataFrame,
    decisions: pd.DataFrame,
    top200: pd.DataFrame,
) -> dict[str, Any]:
    audited_text, audited_pl = _summary_entry(
        summary, "Fundos auditados nas três camadas"
    )
    if _summary_count(audited_text, label="Fundos auditados nas três camadas") != len(
        top200
    ):
        raise TaxonomyAuditImportError("sumário não reconcilia os 200 fundos auditados")
    top200_pl = float(pd.to_numeric(top200["PL (R$)"], errors="coerce").sum())
    _assert_summary_money("Fundos auditados nas três camadas", audited_pl, top200_pl)

    outros_text, outros_pl = _summary_entry(summary, "Balde Outros no Top 200")
    current_outros = top200["Tipo ANBIMA atual"].map(_slug).eq("Outros")
    if _summary_count(outros_text, label="Balde Outros no Top 200") != int(
        current_outros.sum()
    ):
        raise TaxonomyAuditImportError("sumário não reconcilia o balde Outros")
    _assert_summary_money(
        "Balde Outros no Top 200",
        outros_pl,
        float(pd.to_numeric(top200.loc[current_outros, "PL (R$)"], errors="coerce").sum()),
    )

    f8 = top200["Confiabilidade da Tabela II"].map(_slug).str.contains(
        "F8", regex=False
    )
    f8_count = int(f8.sum())
    f8_pl = float(pd.to_numeric(top200.loc[f8, "PL (R$)"], errors="coerce").sum())
    if f8_count != EXPECTED_F8_ROWS or abs(f8_pl - EXPECTED_F8_PL_BRL) > 0.01:
        raise TaxonomyAuditImportError(
            f"Top200 deveria conter {EXPECTED_F8_ROWS} fundos F8 e "
            f"R$ {EXPECTED_F8_PL_BRL:.2f}; recebeu {f8_count} e R$ {f8_pl:.2f}"
        )
    f8_text, f8_summary_pl = _summary_entry(summary, "Campo residual F8")
    if _summary_count(f8_text, label="Campo residual F8") != f8_count:
        raise TaxonomyAuditImportError("sumário não reconcilia a contagem de F8")
    _assert_summary_money("Campo residual F8", f8_summary_pl, f8_pl)

    migrations = decisions[decisions["efeito"].eq("Migra de Tipo")].copy()
    grouped = migrations.groupby(["tipo_atual", "tipo_proposto"], dropna=False)
    for (source_type, target_type), rows in grouped:
        label = f"{source_type} → {target_type}"
        narrative, value = _summary_entry(summary, label)
        if _summary_count(narrative, label=label) != len(rows):
            raise TaxonomyAuditImportError(
                f"sumário não reconcilia a contagem da rota {label}"
            )
        _assert_summary_money(label, value, float(rows["pl_brl"].sum()))

    net: dict[str, float] = {}
    for row in migrations.itertuples(index=False):
        net[row.tipo_atual] = net.get(row.tipo_atual, 0.0) - float(row.pl_brl)
        net[row.tipo_proposto] = net.get(row.tipo_proposto, 0.0) + float(row.pl_brl)
    for anbima_type, expected in net.items():
        _, value = _summary_entry(summary, anbima_type)
        _assert_summary_money(anbima_type, value, expected)

    closed_text, _ = _summary_entry(summary, 'Vereditos "Ler documento"')
    documented_count = int(top200["Veredito documental"].map(_slug).eq("Ler documento").sum())
    if _summary_count(closed_text, label='Vereditos "Ler documento"') != documented_count:
        raise TaxonomyAuditImportError(
            'sumário não reconcilia os vereditos "Ler documento"'
        )

    return {
        "summary_validated": True,
        "top200_pl_brl": top200_pl,
        "top200_outros_count": int(current_outros.sum()),
        "top200_outros_pl_brl": float(
            pd.to_numeric(top200.loc[current_outros, "PL (R$)"], errors="coerce").sum()
        ),
        "f8_count": f8_count,
        "f8_pl_brl": f8_pl,
    }


def _manifest_issues(
    decisions: pd.DataFrame,
    top200: pd.DataFrame,
) -> list[dict[str, Any]]:
    decisions_by_cnpj = decisions.set_index("cnpj_fundo")
    top200_by_cnpj = top200.set_index("cnpj_fundo")
    missing = {
        SELLER3_CNPJ,
        AETOS_CNPJ,
    }.difference(decisions_by_cnpj.index)
    if missing:
        raise TaxonomyAuditImportError(
            "de-para sem casos conhecidos do manifesto: " + ", ".join(sorted(missing))
        )

    seller_decision = decisions_by_cnpj.loc[SELLER3_CNPJ]
    seller_audit = top200_by_cnpj.loc[SELLER3_CNPJ]
    aetos_decision = decisions_by_cnpj.loc[AETOS_CNPJ]
    aetos_audit = top200_by_cnpj.loc[AETOS_CNPJ]
    return [
        {
            "code": "seller3_recommendation_text_inconsistent",
            "cnpj_fundo": SELLER3_CNPJ,
            "status": "source_workbook_note",
            "detail": (
                "A recomendação textual do Top200 menciona Financeiro/Crédito "
                "Pessoal como estado atual; o de-para e as colunas atuais registram "
                f"{seller_decision['tipo_atual']}/{seller_decision['foco_atual']}. "
                "A decisão importada segue o de-para e a evidência documental."
            ),
            "source_recommendation": _slug(seller_audit.get("Recomendação")),
        },
        {
            "code": "aetos_table_ii_misreport_focus_exception",
            "cnpj_fundo": AETOS_CNPJ,
            "status": "explicit_exception",
            "detail": (
                "AETOS tem veredito Tabela II mal reportada e permanece no Tipo "
                f"{aetos_decision['tipo_atual']}; o de-para altera apenas o Foco "
                f"para {aetos_decision['foco_proposto']} com base no regulamento."
            ),
            "source_verdict": _slug(aetos_audit.get("Veredito documental")),
        },
        {
            "code": "f8_exact_value_differs_from_rounded_brief",
            "status": "numeric_reconciliation",
            "detail": (
                "O workbook auditado registra 68 fundos e R$ 113,372908 bi com "
                "dominância F8; R$ 109 bi é uma aproximação anterior e não o valor "
                "numérico do arquivo-fonte."
            ),
            "fund_count": EXPECTED_F8_ROWS,
            "pl_brl": EXPECTED_F8_PL_BRL,
        },
    ]


def import_taxonomy_audit(workbook_path: Path) -> ImportedTaxonomyAudit:
    workbook_path = Path(workbook_path)
    if not workbook_path.is_file():
        raise TaxonomyAuditImportError(f"workbook ausente: {workbook_path}")
    excel = pd.ExcelFile(workbook_path)
    required_sheets = {
        DECISIONS_SHEET,
        TOP200_SHEET,
        OUTROS_SHEET,
        SUMMARY_SHEET,
        ACQUIRING_SHEET,
    }
    missing = required_sheets.difference(excel.sheet_names)
    if missing:
        raise TaxonomyAuditImportError(
            "workbook sem abas obrigatórias: " + ", ".join(sorted(missing))
        )
    decisions = _normalize_decisions(_read_sheet(workbook_path, DECISIONS_SHEET))
    top200 = _normalize_cnpj_frame(
        _read_sheet(workbook_path, TOP200_SHEET),
        sheet=TOP200_SHEET,
        expected_rows=EXPECTED_TOP200_ROWS,
    )
    outros = _normalize_cnpj_frame(
        _read_sheet(workbook_path, OUTROS_SHEET),
        sheet=OUTROS_SHEET,
        expected_rows=EXPECTED_OUTROS_ROWS,
    )
    acquiring = _normalize_cnpj_frame(
        _read_sheet(workbook_path, ACQUIRING_SHEET),
        sheet=ACQUIRING_SHEET,
        expected_rows=EXPECTED_ACQUIRING_ROWS,
    )
    summary = _read_sheet(workbook_path, SUMMARY_SHEET, header=None).dropna(
        how="all"
    )
    join_checks = _decision_join_checks(decisions, top200)
    summary_checks = _validate_summary(summary, decisions, top200)
    issues = _manifest_issues(decisions, top200)
    manifest = {
        "schema_version": "industry_taxonomy_audit_202606_v1",
        "source": {
            "filename": workbook_path.name,
            "sha256": _sha256(workbook_path),
        },
        "sheets": {
            DECISIONS_SHEET: int(len(decisions)),
            TOP200_SHEET: int(len(top200)),
            OUTROS_SHEET: int(len(outros)),
            ACQUIRING_SHEET: int(len(acquiring)),
            SUMMARY_SHEET: int(len(summary)),
        },
        "checks": {
            "type_migration_count": int(decisions["efeito"].eq("Migra de Tipo").sum()),
            "type_migration_pl_brl": float(
                decisions.loc[decisions["efeito"].eq("Migra de Tipo"), "pl_brl"].sum()
            ),
            "focus_only_count": int(decisions["efeito"].eq("Só Foco").sum()),
            "focus_only_pl_brl": float(
                decisions.loc[decisions["efeito"].eq("Só Foco"), "pl_brl"].sum()
            ),
            **join_checks,
            **summary_checks,
        },
        "issues": issues,
        "rules": [
            (
                "uma decisão estática por CNPJ aplicada retroativamente a todas "
                "as competências; 2026-06 é a competência de referência da auditoria"
            ),
            "campos oficiais ANBIMA/CVM permanecem preservados",
            "fundos sem informe em jun/26 permanecem no denominador",
            "F8 residual não determina classificação analítica",
            "Tabela II mal reportada é erro do informe, não mudança de classificação",
        ],
    }
    return ImportedTaxonomyAudit(decisions, top200, outros, acquiring, manifest)


def materialize_taxonomy_audit(
    imported: ImportedTaxonomyAudit,
    data_dir: Path,
) -> dict[str, Path]:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "decisions": data_dir / NORMALIZED_DECISIONS_FILENAME,
        "top200": data_dir / NORMALIZED_TOP200_FILENAME,
        "outros": data_dir / NORMALIZED_OUTROS_FILENAME,
        "acquiring": data_dir / NORMALIZED_ACQUIRING_FILENAME,
        "manifest": data_dir / NORMALIZED_MANIFEST_FILENAME,
    }
    imported.decisions.to_csv(paths["decisions"], index=False)
    imported.top200.to_csv(paths["top200"], index=False, compression="gzip")
    imported.outros.to_csv(paths["outros"], index=False)
    imported.acquiring.to_csv(paths["acquiring"], index=False)
    paths["manifest"].write_text(
        json.dumps(imported.manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


_MISSING_ACTION_DEFAULTS: dict[str, dict[str, str]] = {
    "54871427000194": {
        "tabela_ii_analitica": "N/D",
        "taxonomia_funcional_n1": "Crédito PF",
        "taxonomia_funcional_n2": "FGTS",
        "documento_id": "670689;670690",
    },
    "66929956000180": {
        "tabela_ii_analitica": "N/D",
        "taxonomia_funcional_n1": "Crédito PF",
        "taxonomia_funcional_n2": "Auto/Veículos",
        "documento_id": "FundosNET",
    },
    "60942242000126": {
        "tabela_ii_analitica": "Cartão de crédito",
        "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
        "taxonomia_funcional_n2": "Arranjos de pagamento/adquirência",
        "documento_id": "FundosNET",
    },
    "50168890000113": {
        "tabela_ii_analitica": "Cartão de crédito",
        "taxonomia_funcional_n1": "Meios de Pagamento e Cartões",
        "taxonomia_funcional_n2": "Banco emissor/cartão de crédito",
        "documento_id": "FundosNET",
    },
}


_EMPTY_DOCUMENTARY_VALUES = frozenset({"", "n/d", "nan", "none", "fundosnet"})
_TOP200_SOURCE = (
    "Industria_FIDC_202606_auditada.xlsx#Auditoria classificação Top200"
)


def _has_documentary_value(value: object) -> bool:
    return _slug(value).casefold() not in _EMPTY_DOCUMENTARY_VALUES


def _document_reference_score(value: object) -> tuple[int, int, int]:
    text = _slug(value)
    if not text:
        return (0, 0, 0)
    identifiers = re.findall(r"\b\d{5,}\b", text)
    has_url = int("http://" in text.casefold() or "https://" in text.casefold())
    specificity = 0 if text.casefold() in _EMPTY_DOCUMENTARY_VALUES else 1
    return (has_url + specificity, len(identifiers), len(text))


def _append_note_once(notes: object, addition: str) -> str:
    current = _slug(notes)
    addition = _slug(addition)
    if not addition or addition in current:
        return current
    return f"{current} {addition}".strip()


def prepare_audited_actions(
    imported: ImportedTaxonomyAudit,
    ledger_path: Path,
    *,
    updated_at_utc: str,
) -> pd.DataFrame:
    current = load_taxonomy_review_actions(Path(ledger_path))
    by_cnpj = current.set_index("cnpj_fundo", drop=False).to_dict(orient="index")
    audit = imported.top200.copy()
    if "cnpj_fundo" not in audit:
        audit["cnpj_fundo"] = audit["CNPJ"].map(normalize_cnpj)
    audit_by_cnpj = audit.set_index("cnpj_fundo", drop=False).to_dict(orient="index")
    rows: list[dict[str, str]] = []
    for decision in imported.decisions.to_dict(orient="records"):
        cnpj = str(decision["cnpj_fundo"])
        row = {column: "" for column in TAXONOMY_REVIEW_COLUMNS}
        row.update({k: str(v) for k, v in by_cnpj.get(cnpj, {}).items()})
        evidence = audit_by_cnpj.get(cnpj, {})
        row.update(
            {
                "review_id": cnpj,
                "competencia_referencia": "2026-06",
                "cnpj_fundo": cnpj,
                "denominacao_referencia": str(decision["denominacao_referencia"]),
                "status": "aprovado",
                "tipo_analitico": str(decision["tipo_proposto"]),
                "foco_analitico": str(decision["foco_proposto"]),
                "confianca": "alta",
                # The overlay contract is one static decision per CNPJ.  An
                # empty start competence makes the retroactive scope explicit;
                # competencia_referencia records when the evidence was audited.
                "competencia_inicio": "",
                "updated_at_utc": updated_at_utc,
                "responsavel": "auditoria_classificacao_top200_202606",
            }
        )
        if cnpj in _MISSING_ACTION_DEFAULTS:
            for column, default in _MISSING_ACTION_DEFAULTS[cnpj].items():
                if not _slug(row.get(column)):
                    row[column] = default
        audited_evidence = _slug(evidence.get("Evidência no regulamento"))
        audited_document = _slug(evidence.get("Documento FundosNET (id)"))
        audited_recommendation = _slug(evidence.get("Recomendação"))
        if not audited_evidence or not audited_document or not audited_recommendation:
            raise TaxonomyAuditImportError(
                f"ação {cnpj} sem trilha documental completa no Top200"
            )

        # Preserve a primary source/evidence already curated in the ledger.  The
        # Top200 hand-off remains traceable in the notes when it is not selected
        # as the strongest value for the dedicated field.
        if not _has_documentary_value(row.get("fonte_documental")):
            row["fonte_documental"] = _TOP200_SOURCE
        existing_evidence = _slug(row.get("evidencia"))
        if not _has_documentary_value(existing_evidence):
            row["evidencia"] = audited_evidence
        existing_document = _slug(row.get("documento_id"))
        if _document_reference_score(audited_document) > _document_reference_score(
            existing_document
        ):
            row["documento_id"] = audited_document

        note = (
            "De-para auditado de jun/26 aplicado retroativamente como decisão "
            "única por CNPJ; 2026-06 é apenas a competência de referência. "
            f"{decision['tipo_atual']}/{decision['foco_atual']} -> "
            f"{decision['tipo_proposto']}/{decision['foco_proposto']}."
        )
        row["notas"] = _append_note_once(row.get("notas"), note)
        row["notas"] = _append_note_once(
            row["notas"],
            f"Auditoria Top200 — documento: {audited_document}.",
        )
        if _slug(row.get("evidencia")) != audited_evidence:
            row["notas"] = _append_note_once(
                row["notas"],
                f"Auditoria Top200 — evidência: {audited_evidence}",
            )
        row["notas"] = _append_note_once(
            row["notas"],
            f"Auditoria Top200 — recomendação: {audited_recommendation}",
        )
        if row.get("tabela_ii_analitica") not in CVM_TABLE_II_CATEGORIES:
            row["tabela_ii_analitica"] = "N/D"
        if row.get("taxonomia_funcional_n1") not in FUNCTIONAL_TAXONOMY:
            raise TaxonomyAuditImportError(
                f"ação {cnpj} sem taxonomia funcional N1 válida"
            )
        if row.get("taxonomia_funcional_n2") not in FUNCTIONAL_TAXONOMY[
            row["taxonomia_funcional_n1"]
        ]:
            raise TaxonomyAuditImportError(
                f"ação {cnpj} sem taxonomia funcional N2 válida"
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=list(TAXONOMY_REVIEW_COLUMNS))


__all__ = [
    "ImportedTaxonomyAudit",
    "TaxonomyAuditImportError",
    "import_taxonomy_audit",
    "materialize_taxonomy_audit",
    "prepare_audited_actions",
]
