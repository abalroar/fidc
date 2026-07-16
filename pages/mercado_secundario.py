from __future__ import annotations

import streamlit as st

from services.dashboard_ui import dashboard_page
from tabs.tab_secondary_market import render_tab_secondary_market


st.set_page_config(page_title="Mercado Secundário FIDC", page_icon="📊", layout="wide")

with dashboard_page("secondary_market_standalone"):
    render_tab_secondary_market()
