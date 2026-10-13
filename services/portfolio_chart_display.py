"""Present supplied portfolio series without drawing empty or all-zero axes."""
from __future__ import annotations

from collections.abc import Callable, Iterable

import pandas as pd
import streamlit as st

from services.portfolio_presentation_state import classify_component


def render_portfolio_series(
    frame: pd.DataFrame, *, columns: Iterable[str], title: str,
    chart_factory: Callable[[pd.DataFrame], object],
    comparable_frame: pd.DataFrame | None = None,
    absence_reason: str = "Sem valores informados para esta janela.",
) -> str:
    """Use the original chart's eligibility; retain zero and gaps in a table.

    ``comparable_frame`` must come from the existing visual eligibility rule.
    The chart always receives the unmodified original frame, including gaps.
    """
    visible = frame if comparable_frame is None else comparable_frame
    columns = tuple(columns)
    state = classify_component(visible, columns)
    if state.status == "observed":
        st.altair_chart(chart_factory(frame), use_container_width=True)
        if state.has_gaps:
            st.caption("Série parcial · lacunas preservadas.")
        return state.status
    if state.status == "absent":
        partial = comparable_frame is not None and visible.empty and not frame.empty
        reason = ("Sem competência com universo completo; dados parciais no detalhe." if "universe_complete" in frame else "Sem observação no recorte do gráfico; dados fora do recorte no detalhe.") if partial else absence_reason
        st.caption(f"{title}: N/D. {reason}")
        if partial:
            identity = [name for name in ("competencia", "universe_complete") if name in frame]
            with st.expander(f"Dados parciais · {title}", expanded=False):
                st.dataframe(frame.reindex(columns=list(dict.fromkeys([*identity, *columns]))).copy(), hide_index=True, width="stretch")
        return state.status

    gap_note = "; lacunas marcadas como N/D" if state.has_gaps else ""
    partial = comparable_frame is not None and len(visible) < len(frame)
    scope_note = " na base comparável" if comparable_frame is not None else ""
    partial_note = " Observações fora do recorte no detalhe." if partial else ""
    st.caption(f"{title}: zero nos {state.finite_count} valores observados{scope_note}{gap_note}.{partial_note}")
    detailed = frame if partial else visible
    identity = [name for name in ("competencia", "cohort", "mes_ciclo", "universe_complete") if name in detailed]
    shown = detailed.reindex(columns=list(dict.fromkeys([*identity, *columns]))).copy()
    with st.expander(f"Valores por competência · {title}", expanded=False):
        st.dataframe(shown, hide_index=True, width="stretch")
    return state.status
