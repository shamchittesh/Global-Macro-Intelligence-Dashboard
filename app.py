"""Global Macro Intelligence Dashboard - Main Entry Point.

A learning-oriented tool for developing institutional-grade macro thinking.
Provides real-time asset monitoring, cross-asset analysis, dominant variable
identification, historical event analysis, and expectation tracking.
"""

import streamlit as st
from lib.data_fetcher import DataFetcher, DataFetchError
from lib.db import get_db

# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Global Macro Intelligence Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Shared Session State Initialization
# ---------------------------------------------------------------------------

if "data_fetcher" not in st.session_state:
    st.session_state["data_fetcher"] = DataFetcher()

if "db_connected" not in st.session_state:
    db = get_db()
    st.session_state["db_connected"] = db is not None and db.connected

if "custom_assets" not in st.session_state:
    st.session_state["custom_assets"] = []

# ---------------------------------------------------------------------------
# Sidebar - Global Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🌍 Macro Dashboard")
    st.caption("Global Macro Intelligence")

    st.divider()

    # Data source status indicators
    st.subheader("📡 Data Sources")

    # Check database connection
    db_status = "🟢 Connected" if st.session_state["db_connected"] else "🔴 Not Connected"
    st.write(f"**Supabase:** {db_status}")

    # API status
    try:
        fred_key = st.secrets["fred"]["api_key"]
        fred_status = "🟢 Configured" if fred_key else "🟡 Not Configured"
    except (KeyError, TypeError):
        fred_status = "🟡 Not Configured"

    try:
        td_key = st.secrets["twelve_data"]["api_key"]
        td_status = "🟢 Configured" if td_key else "🟡 Not Configured"
    except (KeyError, TypeError):
        td_status = "🟡 Not Configured"

    st.write(f"**FRED API:** {fred_status}")
    st.write(f"**Twelve Data:** {td_status}")
    st.write("**yfinance:** 🟢 No key needed")

    st.divider()

    # Refresh button
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # Navigation info
    st.subheader("📖 Pages")
    st.markdown("""
    - 📊 **Asset Monitor** — Real-time prices & charts
    - 🔗 **Cross-Asset** — Correlations & overlays
    - 🎯 **Dominant Variable** — What's driving markets
    - 📅 **Event Analysis** — Historical event impact
    - 📈 **Expectations** — Surprise & repricing
    """)

# ---------------------------------------------------------------------------
# Main Content - Landing Page
# ---------------------------------------------------------------------------

st.title("🌍 Global Macro Intelligence Dashboard")
st.markdown("---")

st.markdown("""
### Welcome

This dashboard helps you develop institutional-grade macro thinking by tracking
how macro variables interact, which factor dominates on any given day, and how
surprise drives repricing.

**Core question to ask every day:**
> *Which variable is dominating today?*
""")

# Quick status overview
st.subheader("📊 Quick Overview")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("**Navigate** using the sidebar pages to explore different analysis views.")

with col2:
    if not st.session_state["db_connected"]:
        st.warning(
            "**Database not connected.** Configure Supabase in "
            "`.streamlit/secrets.toml` to enable persistence."
        )
    else:
        st.success("**Database connected.** Your data will be persisted.")

with col3:
    st.info(
        "**Tip:** Start with the Asset Monitor to see current market state, "
        "then check Cross-Asset for correlations."
    )

# Error banners for data source failures
if not st.session_state["db_connected"]:
    st.warning(
        "⚠️ **Read-only mode:** Supabase is not connected. "
        "Journal entries, events, and expectations will not be saved. "
        "Configure credentials in `.streamlit/secrets.toml` to enable full functionality."
    )

st.markdown("---")

# Daily routine reminder
st.subheader("📝 Daily Macro Routine")
st.markdown("""
Every morning, ask yourself:

1. **What moved?** — Check the Asset Monitor
2. **Why?** — Look at Cross-Asset correlations for clues
3. **What variable dominated?** — Record it in Dominant Variable
4. **What changed in expectations?** — Track in Expectations

> *"Gold down despite war because real yields rose."*
> — This is the kind of insight you're building toward.
""")

st.markdown("---")
st.caption(
    "Built for learning. Think like macro hedge funds, rates traders, "
    "FX desks, and institutional allocators."
)
