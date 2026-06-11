"""Global Macro Intelligence Dashboard - Simplified Single-Page App.

A streamlined dashboard tracking 7 key macro instruments with daily/weekly
percentage changes, dominant variable identification, and scraped market reports.
"""

import time
from datetime import datetime

import streamlit as st

from lib.cache import invalidate_cache, invalidate_stale_instrument_data
from lib.calculations import (
    INSTRUMENT_ORDER,
    DominantVariable,
    InstrumentData,
    get_color_for_change,
    identify_dominant_variable,
)
from lib.data_fetcher import fetch_all_instruments
from lib.market_day import get_latest_market_day, get_current_trading_week
from lib.scraper import MarketReport, fetch_daily_recap, fetch_weekly_update
from lib.ai_summary import generate_all_ai_content

# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Global Macro Intelligence Dashboard",
    page_icon="🌍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "last_refresh_time" not in st.session_state:
    st.session_state["last_refresh_time"] = 0.0


# ---------------------------------------------------------------------------
# Refresh Logic
# ---------------------------------------------------------------------------

REFRESH_COOLDOWN_SECONDS = 60


def is_refresh_allowed() -> bool:
    """Check if enough time has passed since last refresh."""
    elapsed = time.time() - st.session_state["last_refresh_time"]
    return elapsed >= REFRESH_COOLDOWN_SECONDS


def seconds_until_refresh() -> int:
    """Seconds remaining until refresh is allowed."""
    elapsed = time.time() - st.session_state["last_refresh_time"]
    remaining = REFRESH_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


# ---------------------------------------------------------------------------
# Helper: Color-coded metric display
# ---------------------------------------------------------------------------


def render_colored_change(value: float | None, label: str) -> str:
    """Render a percentage change value with color as HTML.

    Args:
        value: Percentage change, or None if unavailable.
        label: Label prefix (e.g., "Daily" or "Weekly").

    Returns:
        HTML string with colored value.
    """
    if value is None:
        return f"<span style='color: gray;'>{label}: N/A</span>"

    color = get_color_for_change(value)
    if color == "green":
        css_color = "#00c853"
    elif color == "red":
        css_color = "#ff1744"
    else:
        css_color = "inherit"

    sign = "+" if value > 0 else ""
    return f"<span style='color: {css_color}; font-weight: bold;'>{label}: {sign}{value:.2f}%</span>"


# ---------------------------------------------------------------------------
# Main Dashboard
# ---------------------------------------------------------------------------

# Title
st.title("🌍 Global Macro Intelligence Dashboard")

# Resolve market day
market_day = get_latest_market_day()
week_start, week_end = get_current_trading_week(market_day)

st.caption(
    f"Latest market day: **{market_day.strftime('%A, %B %d, %Y')}** · "
    f"Week: {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
)

st.divider()

# ---------------------------------------------------------------------------
# Refresh Button
# ---------------------------------------------------------------------------

col_refresh, col_status = st.columns([1, 4])

with col_refresh:
    refresh_allowed = is_refresh_allowed()
    if st.button(
        "🔄 Refresh Data",
        disabled=not refresh_allowed,
        use_container_width=True,
    ):
        # Invalidate caches and trigger refetch
        invalidate_stale_instrument_data()
        invalidate_cache(f"instruments_{market_day.isoformat()}")
        invalidate_cache("daily_report")
        invalidate_cache("weekly_report")
        invalidate_cache("ai_narrative")
        invalidate_cache("tldr_daily")
        invalidate_cache("tldr_weekly")
        st.session_state["last_refresh_time"] = time.time()
        st.rerun()

with col_status:
    if not refresh_allowed:
        remaining = seconds_until_refresh()
        st.caption(f"⏳ Refresh available in {remaining}s")

# ---------------------------------------------------------------------------
# Instrument Panel Grid
# ---------------------------------------------------------------------------

st.subheader("📊 Macro Instruments")

# Fetch data
instruments = fetch_all_instruments(market_day, week_start, week_end)

# Display in columns (4 on top row, 3 on bottom)
row1_cols = st.columns(4)
row2_cols = st.columns(4)  # Use 4 cols, last will be empty

all_cols = row1_cols + row2_cols[:3]

for i, instrument in enumerate(instruments):
    with all_cols[i]:
        st.markdown(
            f"**{instrument.ticker}**  \n"
            f"<small style='color: #888;'>{instrument.macro_significance}</small>",
            unsafe_allow_html=True,
        )

        if not instrument.data_available:
            st.markdown(
                "<span style='color: gray;'>Data unavailable</span>",
                unsafe_allow_html=True,
            )
        else:
            daily_html = render_colored_change(instrument.daily_change_pct, "Daily")
            weekly_html = render_colored_change(instrument.weekly_change_pct, "Weekly")
            st.markdown(f"{daily_html}<br>{weekly_html}", unsafe_allow_html=True)

        st.markdown("---")

# ---------------------------------------------------------------------------
# Fetch reports & generate all AI content in ONE Gemini call
# ---------------------------------------------------------------------------

daily_report = fetch_daily_recap()
weekly_report = fetch_weekly_update()
dominant = identify_dominant_variable(instruments)

# Single Gemini call for: narrative + daily TL;DR + weekly TL;DR
ai_content = {"narrative": None, "tldr_daily": None, "tldr_weekly": None}
if dominant:
    ai_content = generate_all_ai_content(
        instruments, dominant, daily_report, weekly_report
    )

# ---------------------------------------------------------------------------
# Dominant Variable Section
# ---------------------------------------------------------------------------

st.subheader("🎯 Dominant Variable")

if dominant:
    # Color the dominant variable's change
    dom_color = get_color_for_change(dominant.daily_change_pct)
    if dom_color == "green":
        dom_css = "#00c853"
    elif dom_color == "red":
        dom_css = "#ff1744"
    else:
        dom_css = "inherit"

    sign = "+" if dominant.daily_change_pct > 0 else ""

    st.markdown(
        f"**{dominant.ticker}** ({dominant.macro_significance}) · "
        f"<span style='color: {dom_css}; font-weight: bold;'>"
        f"{sign}{dominant.daily_change_pct:.2f}%</span>",
        unsafe_allow_html=True,
    )

    # Cross-asset narrative
    if ai_content["narrative"]:
        st.info(ai_content["narrative"])
else:
    st.warning("Unable to determine dominant variable — no instrument data available.")

st.divider()

# ---------------------------------------------------------------------------
# Market Reports
# ---------------------------------------------------------------------------

st.subheader("📰 Market Reports")

report_col1, report_col2 = st.columns(2)

# Daily Report
with report_col1:
    st.markdown("#### 📅 Daily Market Recap")

    if daily_report.available:
        # TL;DR at the top
        if ai_content["tldr_daily"]:
            st.markdown("**TL;DR**")
            st.markdown(ai_content["tldr_daily"])
            st.markdown("")

        st.markdown(f"**{daily_report.title}**")
        st.caption(f"Published: {daily_report.publication_date}")
        with st.expander("Read full report", expanded=False):
            st.markdown(daily_report.body)
        if daily_report.error_message:
            st.caption(f"⚠️ {daily_report.error_message}")
    else:
        st.warning(
            "📭 Daily market recap temporarily unavailable.\n\n"
            f"{daily_report.error_message or 'Could not fetch report.'}"
        )

# Weekly Report
with report_col2:
    st.markdown("#### 📈 Weekly Market Update")

    if weekly_report.available:
        # TL;DR at the top
        if ai_content["tldr_weekly"]:
            st.markdown("**TL;DR**")
            st.markdown(ai_content["tldr_weekly"])
            st.markdown("")

        st.markdown(f"**{weekly_report.title}**")
        st.caption(f"Published: {weekly_report.publication_date}")
        with st.expander("Read full report", expanded=False):
            st.markdown(weekly_report.body)
        if weekly_report.error_message:
            st.caption(f"⚠️ {weekly_report.error_message}")
    else:
        st.warning(
            "📭 Weekly market update temporarily unavailable.\n\n"
            f"{weekly_report.error_message or 'Could not fetch report.'}"
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    f"Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
    "Data source: yfinance · Reports: Edward Jones"
)
