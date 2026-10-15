"""Gera o PPT completo de carteiras fora do Streamlit, como a página faz.

Uso (da raiz do repositório):
    python scripts/render_portfolio_decks.py OUT_DIR "Nome da carteira" [...]
    python scripts/render_portfolio_decks.py OUT_DIR --all

Variáveis de ambiente:
    CACHE=<dir>      onde guardar/ler a análise carregada (.analysis.pkl); padrão OUT_DIR
    FETCH_ONLY=1     só carrega e guarda a análise (CVM), sem gerar o PPT
    PLACEMENT=...    "inline" (padrão) ou "appendix"
    MONTHS=13        competências exibidas (janela visual)

Serve para comparar o deck antes/depois de uma mudança: carregue uma vez
(FETCH_ONLY) e gere com cada versão do código usando o mesmo CACHE.
"""
import json
import logging
import os
import pickle
import sys
import time
import traceback
import warnings
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")

from services.ime_period import build_preset_period, current_default_end_month  # noqa: E402
from services.meli_credit_monitor import _universe_warnings  # noqa: E402
from services.meli_credit_research import build_meli_research_outputs  # noqa: E402
from services.portfolio_presentation_context import build_portfolio_presentation_context  # noqa: E402
from services.portfolio_store import PortfolioFund, PortfolioRecord  # noqa: E402
from tabs import portfolio_page as pp  # noqa: E402
from tabs import tab_mercado_livre as somatorio_tab  # noqa: E402


def _analysis(record, period):
    analysis = pp._load_portfolio_analysis_data(selected_portfolio=record, period=period)
    calc = analysis.outputs
    available = somatorio_tab._available_competencia_months(calc.consolidated_monthly)
    months = available[-int(os.environ.get("MONTHS", "13")):]
    display = somatorio_tab._filter_outputs_by_competencia_months(
        calc, months=months, label=somatorio_tab._display_month_range_label(months), mode="Customizado")
    context = build_portfolio_presentation_context(analysis=replace(analysis, outputs=display), portfolio=record, period=period)
    analysis = replace(analysis, scopes=tuple(
        replace(s, position_competence=getattr(s.dashboard, "latest_competencia", "N/D"), snapshot_dashboard=s.dashboard)
        for s in analysis.scopes), reference_context=context)
    analysis = pp._filter_analysis_dashboards_to_outputs(analysis, display)
    monitor = somatorio_tab._build_credit_monitor_for_display(outputs=calc, display_outputs=display)
    return replace(analysis, outputs=display, monitor_outputs=monitor, research_outputs=build_meli_research_outputs(monitor))


def main(argv):
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(os.environ.get("CACHE", out))
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(os.environ.get("PORTFOLIOS", "portfolios.json")).read_text())
    records = {p["name"]: p for p in data["portfolios"]}
    names = list(records) if argv[2:] == ["--all"] else argv[2:]
    period = build_preset_period(end_month=current_default_end_month(), months=12)
    for name in names:
        p = records[name]
        record = PortfolioRecord(id=p["id"], name=p["name"], funds=tuple(PortfolioFund.from_dict(f) for f in p["funds"]),
                                 created_at=p.get("created_at", ""), updated_at=p.get("updated_at", ""))
        token = pp._safe_file_token(name)
        started = time.time()
        try:
            cache = cache_dir / f"{token}.analysis.pkl"
            if cache.exists():
                analysis = pickle.loads(cache.read_bytes())
                # The universe check follows the current code, not the cache.
                monitor = analysis.monitor_outputs
                if monitor is not None:
                    kept = [w for w in monitor.warnings if not str(w).startswith("Universo MELI")]
                    analysis = replace(analysis, monitor_outputs=replace(
                        monitor, warnings=[*kept, *_universe_warnings(monitor.fund_monitor)]))
            else:
                analysis = _analysis(record, period)
                cache.write_bytes(pickle.dumps(analysis))
            if os.environ.get("FETCH_ONLY"):
                print(f"OK {name} {time.time() - started:.0f}s fetched", flush=True)
                continue
            kwargs = {"table_placement": os.environ["PLACEMENT"]} if os.environ.get("PLACEMENT") else {}
            prepared = pp._prepare_complete_portfolio_pptx(analysis=analysis, selected_portfolio=record, period=period, **kwargs)
            (out / f"{token}.pptx").write_bytes(prepared.data)
            print(f"OK {name} {time.time() - started:.0f}s warnings={len(prepared.warnings)}", flush=True)
        except Exception as exc:  # noqa: BLE001 — one basket never stops the batch.
            print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc(limit=3)


if __name__ == "__main__":
    main(sys.argv)
