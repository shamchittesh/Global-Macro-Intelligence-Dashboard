"""Dominant Variable page - Identify and track the macro factor driving markets."""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta

from lib.models import DEFAULT_ASSETS, DominantFactor
from lib.data_fetcher import (
    fetch_asset_data_cached,
    fetch_current_prices_cached,
    DataFetchError,
    InvalidSymbolError,
)
from lib.calculations import compute_correlation_matrix, identify_dominant_variable
from lib.db import get_db

st.set_page_config(page_title="Dominant Variable", page_icon="🎯", layout="wide")
st.title("🎯 Dominant Variable")
st.caption("Identify which macro factor is driving markets today")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VARIABLE_OPTIONS = [
    "rates",
    "USD",
    "oil",
    "liquidity",
    "risk_appetite",
    "inflation",
    "geopolitics",
]

TIMELINE_VIEWS = {
    "30 Days": 30,
    "90 Days": 90,
    "180 Days": 180,
}

CORRELATION_WINDOW = 21  # Trading days for correlation calculation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner="Computing dominant factors...")
def _compute_dominant_factors() -> list[DominantFactor]:
    """Compute system-calculated dominant factors for the current session.

    1. Fetch current prices for all DEFAULT_ASSETS to get today's returns (pct_change)
    2. Fetch recent daily data to compute a correlation matrix (21-day window)
    3. Call identify_dominant_variable() to get top 3 factors
    """
    # Step 1: Get current prices with pct_change
    try:
        prices = fetch_current_prices_cached()
    except Exception:
        return []

    if not prices:
        return []

    # Build asset_returns dict: display_name -> pct_change
    asset_returns: dict[str, float] = {}
    symbol_to_name: dict[str, str] = {a.symbol: a.display_name for a in DEFAULT_ASSETS}

    for symbol, price_obj in prices.items():
        display_name = symbol_to_name.get(symbol, symbol)
        asset_returns[display_name] = price_obj.pct_change

    if not asset_returns:
        return []

    # Step 2: Fetch recent daily data and compute correlation matrix
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=int(CORRELATION_WINDOW * 1.6) + 10)

    returns_data: dict[str, pd.Series] = {}
    for asset in DEFAULT_ASSETS:
        try:
            df = fetch_asset_data_cached(
                symbol=asset.symbol,
                interval="1day",
                start_date=start_dt,
                end_date=end_dt,
                source_value=asset.source.value,
            )
            if df is not None and not df.empty:
                ret = df["close"].pct_change().dropna()
                if not ret.empty:
                    returns_data[asset.display_name] = ret
        except (DataFetchError, InvalidSymbolError, Exception):
            continue

    # Compute correlation matrix
    if len(returns_data) >= 2:
        corr_matrix = compute_correlation_matrix(returns_data, window=CORRELATION_WINDOW)
    else:
        corr_matrix = pd.DataFrame()

    # Step 3: Identify dominant variable
    factors = identify_dominant_variable(asset_returns, corr_matrix)
    return factors


# ---------------------------------------------------------------------------
# Section 1: System-Calculated Dominant Factors
# ---------------------------------------------------------------------------

st.subheader("📊 System-Calculated Dominant Factors")
st.caption("Top 3 factors driving markets this session, ranked by influence score")

factors = _compute_dominant_factors()

if factors:
    cols = st.columns(len(factors))
    for i, factor in enumerate(factors):
        with cols[i]:
            # Medal emoji for ranking
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
            st.metric(
                label=f"{medal} #{i + 1}: {factor.variable}",
                value=f"{factor.influence_score:.3f}",
                help=factor.description,
            )
            st.caption(factor.description)
else:
    st.info(
        "Unable to compute dominant factors. This may be due to market data "
        "being unavailable or insufficient data for the current session."
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Manual Dominant Variable Selection
# ---------------------------------------------------------------------------

st.subheader("✍️ Record Today's Dominant Variable")
st.caption("Manually select and record which variable you believe is driving markets")

db = get_db()

with st.form("dominant_variable_form", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
        selected_variable = st.selectbox(
            "Dominant Variable",
            VARIABLE_OPTIONS,
            help="Select the macro variable you believe is most influential today",
        )

    with col2:
        selected_date = st.date_input(
            "Date",
            value=date.today(),
            max_value=date.today(),
            help="Date for this dominant variable selection",
        )

    notes = st.text_area(
        "Notes / Reasoning",
        placeholder="Why do you think this variable is dominant today? What evidence supports this?",
        max_chars=500,
        help="Record your reasoning for future review",
    )

    submitted = st.form_submit_button("💾 Save Selection", use_container_width=True)

    if submitted:
        if db is not None:
            try:
                db.save_dominant_variable(
                    record_date=selected_date,
                    variable=selected_variable,
                    notes=notes,
                )
                st.success(
                    f"✅ Saved: **{selected_variable}** as dominant variable for {selected_date}"
                )
            except Exception as e:
                st.error(f"Failed to save: {e}")
        else:
            st.warning(
                "Database not connected. Configure Supabase credentials in "
                "`.streamlit/secrets.toml` to enable persistence."
            )

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Historical Timeline
# ---------------------------------------------------------------------------

st.subheader("📅 Historical Dominant Variable Timeline")

# View selector
selected_view = st.radio(
    "Time Range",
    list(TIMELINE_VIEWS.keys()),
    horizontal=True,
    index=0,
)
days = TIMELINE_VIEWS[selected_view]

if db is not None:
    try:
        history = db.get_dominant_variable_history(days=days)
    except Exception:
        history = []

    if history:
        # Convert to DataFrame for Plotly
        history_data = []
        for record in history:
            history_data.append({
                "Date": record.date,
                "Variable": record.variable,
                "Notes": record.notes or "",
                "Manual": "Manual" if record.is_manual else "System",
                "Score": record.influence_score if record.influence_score else 0.0,
            })

        df_history = pd.DataFrame(history_data)
        df_history["Date"] = pd.to_datetime(df_history["Date"])
        df_history = df_history.sort_values("Date")

        # Timeline bar chart - each day colored by dominant variable
        fig = px.bar(
            df_history,
            x="Date",
            y=[1] * len(df_history),  # Uniform height
            color="Variable",
            hover_data=["Notes", "Manual", "Score"],
            title=f"Dominant Variable Over Past {days} Days",
            labels={"y": "", "Variable": "Dominant Variable"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )

        fig.update_layout(
            height=350,
            yaxis=dict(visible=False),
            xaxis_title="Date",
            legend_title="Variable",
            margin=dict(l=50, r=50, t=60, b=50),
            bargap=0.1,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Summary table
        with st.expander("📋 Detailed History"):
            display_df = df_history[["Date", "Variable", "Notes", "Manual", "Score"]].copy()
            display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Frequency breakdown
        st.caption("**Variable Frequency:**")
        freq = df_history["Variable"].value_counts()
        freq_cols = st.columns(min(len(freq), 4))
        for i, (var, count) in enumerate(freq.items()):
            with freq_cols[i % len(freq_cols)]:
                pct = count / len(df_history) * 100
                st.metric(label=var, value=f"{count} days", delta=f"{pct:.0f}%")
    else:
        st.info(
            f"No dominant variable records found for the past {days} days. "
            "Use the form above to start recording."
        )
else:
    st.warning(
        "Database not connected. Configure Supabase credentials in "
        "`.streamlit/secrets.toml` to enable persistence and view history."
    )
