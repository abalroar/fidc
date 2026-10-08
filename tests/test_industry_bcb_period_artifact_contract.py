"""BCB source labels preserve the actual common month in native artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from services.industry_comparative_period import ComparisonCut

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or (
    "/Users/matheusjprates/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)


def _function(source: str, name: str) -> str:
    body = source.split(f"function {name}", 1)[1].split("\n}\n", 1)[0]
    return f"function {name}{body}\n}}\n"


def _source_labels(primary: str, bcb: str | None) -> dict[str, str]:
    source = (ROOT / "scripts/build_fidc_revision_artifacts.mjs").read_text()
    cut = ComparisonCut.from_competence(primary)
    payload = {
        "latest_complete": primary,
        "offers_as_of": cut.period_end.isoformat(),
        "offers_comparison_meta": cut.to_meta(),
        "bcb_expanded_credit": [{"competencia": bcb}] if bcb else [],
        "provider_concentration_history": [{"competencia": f"{cut.year - 1}-12"}],
        "anbima_market_offers_manifest": {
            "comparison_meta": cut.to_meta(),
            "cvm_latest_complete_meta": cut.to_meta(),
            "source_reference_competence": primary,
        },
    }
    code = "const MONTHS_SHORT_PT = " + json.dumps(
        ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    ) + ";\nconst editorialPayload = " + json.dumps(payload) + ";\n"
    for name in (
        "parseIsoDate", "parseCompetence", "dateShortPt", "competenceShortPt",
        "comparativePeriod", "secondaryComparativePeriod", "historicalFrameCompetences",
        "editorialFooterCopy",
    ):
        code += _function(source, name)
    header = re.search(
        r"`Fontes: CVM, Informe Mensal de FIDC \(\$\{stockShortLower\}\); "
        r"BCB, SGS 28183–28192 \(último mês comum: \$\{[^}]+\}\)\.`",
        source,
    )
    assert header is not None
    code += (
        "const stockShortLower = competenceShortPt(editorialPayload.latest_complete).toLowerCase();"
        "const expandedCredit = editorialPayload.bcb_expanded_credit || [];"
        "const bcbStockShortLower = competenceShortPt(expandedCredit.at(-1)?.competencia).toLowerCase();"
        "process.stdout.write(JSON.stringify({"
        'footer: editorialFooterCopy("ESCALA DA INDÚSTRIA", "fallback"), '
        "header: " + header.group(0) + "}));"
    )
    result = subprocess.run(
        [NODE, "-e", code], check=True, text=True, capture_output=True, timeout=20
    )
    return json.loads(result.stdout)


def test_august_source_labels_are_byte_identical_to_published_copy() -> None:
    assert _source_labels("2026-08", "2026-08") == {
        "footer": "Fontes: CVM e BCB, ago/26. PL ex-FIC; crédito privado ampliado. Séries e perímetros no XLSX.",
        "header": "Fontes: CVM, Informe Mensal de FIDC (ago/26); BCB, SGS 28183–28192 (último mês comum: ago/26).",
    }


@pytest.mark.parametrize(
    ("primary", "bcb", "primary_label", "bcb_label"),
    [("2026-08", "2026-06", "ago/26", "jun/26"),
     ("2027-03", "2026-12", "mar/27", "dez/26")],
)
def test_bcb_lag_is_identified_in_both_source_labels(
    primary: str, bcb: str, primary_label: str, bcb_label: str
) -> None:
    result = _source_labels(primary, bcb)
    assert f"CVM, {primary_label}; BCB, {bcb_label}" in result["footer"]
    assert f"último mês comum: {bcb_label}" in result["header"]


def test_missing_bcb_source_date_keeps_nd() -> None:
    result = _source_labels("2026-08", None)
    assert "BCB, n/d" in result["footer"]
    assert "último mês comum: n/d" in result["header"]
