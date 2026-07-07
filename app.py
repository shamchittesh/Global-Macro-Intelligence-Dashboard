"""Global Macro Intelligence Dashboard - Simplified Single-Page App.

A streamlined dashboard tracking 7 key macro instruments with daily/weekly
percentage changes, dominant variable identification, and scraped market reports.
"""

import time
from datetime import datetime

import streamlit as st

from src.cache import invalidate_cache, invalidate_stale_instrument_data
from src.calculations import (
    INSTRUMENT_ORDER,
    DominantVariable,
    InstrumentData,
    get_color_for_change,
    identify_dominant_variable,
)
from src.data_fetcher import fetch_all_instruments
from src.market_day import get_latest_market_day, get_current_trading_week
from src.scraper import MarketReport, DailyReportDay, fetch_daily_recap, fetch_daily_recap_all_days, fetch_weekly_update
from src.ai_summary import generate_all_ai_content

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

# Auto-invalidate stale cache on every page load (handles day changes)
invalidate_stale_instrument_data()

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
        invalidate_cache("daily_report_days")
        invalidate_cache("weekly_report")
        invalidate_cache("ai_narrative")
        invalidate_cache("ai_weekly_narrative")
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

# Show actual data date (may differ from resolved market day if yfinance lags)
actual_dates = [i.actual_date for i in instruments if i.actual_date]
if actual_dates:
    from datetime import date as _date
    actual_day = _date.fromisoformat(actual_dates[0])
    st.caption(
        f"Data as of: **{actual_day.strftime('%A, %B %d, %Y')}** · "
        f"Week: {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
    )
else:
    st.caption(
        f"Latest market day: **{market_day.strftime('%A, %B %d, %Y')}** · "
        f"Week: {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
    )

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
# Fetch reports & generate all AI content
# ---------------------------------------------------------------------------

daily_report = fetch_daily_recap()
weekly_report = fetch_weekly_update()
dominant = identify_dominant_variable(instruments)
weekly_dominant = identify_dominant_variable(instruments, use_weekly=True)

# AI content (narrative, weekly narrative, TL;DRs)
ai_content = generate_all_ai_content(
    instruments, dominant, daily_report, weekly_report, weekly_dominant
)

# ---------------------------------------------------------------------------
# Dominant Variable Section
# ---------------------------------------------------------------------------

st.subheader("🎯 Dominant Variable")

dom_col1, dom_col2 = st.columns(2)

# Daily dominant
with dom_col1:
    st.markdown("**Last Trading Day**")
    if dominant:
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
        if ai_content["narrative"]:
            st.info(ai_content["narrative"])
    else:
        st.warning("No daily data available.")

# Weekly dominant
with dom_col2:
    st.markdown("**Past Week**")
    if weekly_dominant:
        w_color = get_color_for_change(weekly_dominant.daily_change_pct)
        if w_color == "green":
            w_css = "#00c853"
        elif w_color == "red":
            w_css = "#ff1744"
        else:
            w_css = "inherit"

        sign = "+" if weekly_dominant.daily_change_pct > 0 else ""
        st.markdown(
            f"**{weekly_dominant.ticker}** ({weekly_dominant.macro_significance}) · "
            f"<span style='color: {w_css}; font-weight: bold;'>"
            f"{sign}{weekly_dominant.daily_change_pct:.2f}%</span>",
            unsafe_allow_html=True,
        )
        if ai_content["weekly_narrative"]:
            st.info(ai_content["weekly_narrative"])
    else:
        st.warning("No weekly data available.")

st.divider()

# ---------------------------------------------------------------------------
# Market Reports
# ---------------------------------------------------------------------------

st.subheader("📰 Market Reports")

report_col1, report_col2 = st.columns(2)

# Daily Report
with report_col1:
    st.markdown("#### 📅 [Daily Market Update](https://www.edwardjones.com/us-en/market-news-insights/stock-market-news/daily-market-recap)")

    # Fetch all days
    all_days = fetch_daily_recap_all_days()

    if all_days:
        # Latest day shown directly
        latest = all_days[0]
        st.markdown(f"**{latest.date_label}**")
        with st.expander("Read latest recap", expanded=False):
            st.markdown(latest.body)

        # Previous days as collapsed expanders
        if len(all_days) > 1:
            for day in all_days[1:]:
                with st.expander(f"📄 {day.date_label}", expanded=False):
                    st.markdown(day.body)
    elif daily_report.available:
        st.markdown(f"**{daily_report.title}**")
        st.caption(f"Published: {daily_report.publication_date}")
        with st.expander("Read full report", expanded=False):
            st.markdown(daily_report.body)
    else:
        st.warning(
            "📭 Daily market recap temporarily unavailable.\n\n"
            f"{daily_report.error_message or 'Could not fetch report.'}"
        )

# Weekly Report
with report_col2:
    st.markdown("#### 📈 [Weekly Market Update](https://www.edwardjones.com/us-en/market-news-insights/stock-market-news/stock-market-weekly-update)")

    if weekly_report.available:
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
# AI TL;DR Section
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🤖 AI Report Summaries")

tldr_col1, tldr_col2 = st.columns(2)

with tldr_col1:
    st.markdown("**📅 Daily TL;DR**")
    if ai_content["tldr_daily"]:
        st.markdown(ai_content["tldr_daily"])
    else:
        st.caption("⏳ Generating on next refresh... (requires Gemini API)")

with tldr_col2:
    st.markdown("**📈 Weekly TL;DR**")
    if ai_content["tldr_weekly"]:
        st.markdown(ai_content["tldr_weekly"])
    else:
        st.caption("⏳ Generating on next refresh... (requires Gemini API)")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    f"Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
    "Data source: yfinance · Reports: Edward Jones"
)
