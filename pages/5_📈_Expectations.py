"""Expectations page - Track expected vs actual economic data and surprise-driven repricing."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

from lib.models import DEFAULT_ASSETS, ExpectationRecord
from lib.data_fetcher import (
    fetch_asset_data_cached,
    DataFetchError,
    InvalidSymbolError,
)
from lib.calculations import compute_surprise_magnitude, compute_asset_reaction
from lib.db import get_db

st.set_page_config(page_title="Expectations", page_icon="📈", layout="wide")
st.title("📈 Expectations")
st.caption("Track market expectations vs actual outcomes and how surprise drives repricing")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REACTION_WINDOWS = ["5min", "1hr", "1day"]
WINDOW_LABELS = {"5min": "5 Minutes", "1hr": "1 Hour", "1day": "1 Day"}
DEFAULT_HISTORICAL_STD = 0.5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_release_reactions(
    release_date: date,
) -> dict[str, dict[str, float]]:
    """Compute asset reactions for all DEFAULT_ASSETS around a release date.

    Fetches intraday/daily price data around the release and computes percentage
    change for 5min, 1hr, and 1day windows.

    Returns:
        Dict mapping asset display_name -> {window_label: pct_change}
    """
    reactions: dict[str, dict[str, float]] = {}

    # Fetch data from a few days before to a few days after the release
    start_dt = datetime.combine(release_date - timedelta(days=5), datetime.min.time())
    end_dt = datetime.combine(release_date + timedelta(days=5), datetime.min.time())
    release_ts = datetime.combine(release_date, datetime.min.time())

    for asset in DEFAULT_ASSETS:
        try:
            # Use daily data for the 1day window; intraday would be ideal
            # but daily is universally available
            df = fetch_asset_data_cached(
                symbol=asset.symbol,
                interval="1day",
                start_date=start_dt,
                end_date=end_dt,
                source_value=asset.source.value,
            )
            if df is not None and not df.empty:
                price_series = df["close"]
                asset_reaction = compute_asset_reaction(
                    price_series=price_series,
                    release_timestamp=release_ts,
                    windows=REACTION_WINDOWS,
                )
                if asset_reaction:
                    reactions[asset.display_name] = asset_reaction
        except (DataFetchError, InvalidSymbolError, Exception):
            continue

    return reactions


def _build_reaction_chart(
    reactions: dict[str, dict[str, float]], title: str
) -> go.Figure:
    """Build a grouped bar chart showing asset reactions at each window."""
    assets = list(reactions.keys())
    fig = go.Figure()

    for window in REACTION_WINDOWS:
        label = WINDOW_LABELS.get(window, window)
        values = [reactions.get(asset, {}).get(window, 0.0) for asset in assets]
        fig.add_trace(
            go.Bar(
                name=label,
                x=assets,
                y=values,
                text=[f"{v:+.2f}%" for v in values],
                textposition="auto",
            )
        )

    fig.update_layout(
        barmode="group",
        title=title,
        xaxis_title="Asset",
        yaxis_title="Price Change (%)",
        height=450,
        margin=dict(l=50, r=50, t=60, b=80),
        legend_title="Window",
    )

    return fig


def _build_surprise_chart(
    records: list[ExpectationRecord], indicator: str
) -> go.Figure:
    """Build a bar chart of historical surprise magnitudes for an indicator."""
    # Filter records that have surprise_magnitude
    filtered = [
        r for r in records
        if r.surprise_magnitude is not None and r.indicator == indicator
    ]

    if not filtered:
        return None

    # Sort by date ascending for chronological display
    filtered.sort(key=lambda r: r.release_date)

    dates = [r.release_date.isoformat() for r in filtered]
    magnitudes = [r.surprise_magnitude for r in filtered]
    colors = [
        "green" if m >= 0 else "red" for m in magnitudes
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=dates,
            y=magnitudes,
            marker_color=colors,
            text=[f"{m:+.2f}" for m in magnitudes],
            textposition="auto",
        )
    )

    fig.update_layout(
        title=f"Surprise Magnitude History: {indicator}",
        xaxis_title="Release Date",
        yaxis_title="Surprise Magnitude (σ)",
        height=400,
        margin=dict(l=50, r=50, t=60, b=80),
    )

    return fig


def _compute_pattern_analysis(
    records: list[ExpectationRecord], indicator: str
) -> pd.DataFrame | None:
    """Compute average asset reactions across all historical releases for an indicator.

    Returns a DataFrame with assets as rows and windows as columns showing
    mean reaction percentages.
    """
    filtered = [
        r for r in records
        if r.indicator == indicator and r.asset_reactions is not None
    ]

    if not filtered:
        return None

    # Aggregate reactions: {asset: {window: [values]}}
    aggregated: dict[str, dict[str, list[float]]] = {}

    for record in filtered:
        for asset_name, windows in record.asset_reactions.items():
            if asset_name not in aggregated:
                aggregated[asset_name] = {w: [] for w in REACTION_WINDOWS}
            for window, value in windows.items():
                if window in aggregated[asset_name]:
                    aggregated[asset_name][window].append(value)

    if not aggregated:
        return None

    # Compute means
    rows = []
    for asset_name, windows in aggregated.items():
        row = {"Asset": asset_name}
        for window in REACTION_WINDOWS:
            values = windows.get(window, [])
            label = WINDOW_LABELS.get(window, window)
            row[label] = np.mean(values) if values else 0.0
        row["Count"] = len(filtered)
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

db = get_db()

# ---------------------------------------------------------------------------
# Section 1: Upcoming/Recent Releases
# ---------------------------------------------------------------------------

st.subheader("📋 Upcoming & Recent Releases")
st.caption("Economic releases with consensus expectations and actual outcomes")

# Fetch expectations history
expectations: list[ExpectationRecord] = []
if db is not None:
    try:
        expectations = db.get_expectations_history()
    except Exception as e:
        st.error(f"Failed to load expectations: {e}")

if expectations:
    # Display as a table
    table_data = []
    for rec in expectations:
        surprise_str = (
            f"{rec.surprise_magnitude:+.2f}σ"
            if rec.surprise_magnitude is not None
            else "—"
        )
        actual_str = (
            f"{rec.actual_value:.4g}" if rec.actual_value is not None else "Pending"
        )
        table_data.append({
            "Date": rec.release_date,
            "Indicator": rec.indicator,
            "Expected": f"{rec.expected_value:.4g}",
            "Actual": actual_str,
            "Surprise": surprise_str,
        })

    df_releases = pd.DataFrame(table_data)
    st.dataframe(df_releases, use_container_width=True, hide_index=True)
else:
    if db is None:
        st.warning(
            "Database not connected. Configure Supabase credentials in "
            "`.streamlit/secrets.toml` to view and manage expectations."
        )
    else:
        st.info(
            "No expectation records found. Use the form below to add entries."
        )

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Surprise Magnitude Chart
# ---------------------------------------------------------------------------

st.subheader("📊 Surprise Magnitude Chart")
st.caption("Historical surprise magnitudes for a selected indicator, colored by direction")

if expectations:
    # Get unique indicators
    indicators = sorted(set(r.indicator for r in expectations))

    selected_indicator = st.selectbox(
        "Select Indicator",
        indicators,
        key="surprise_indicator",
    )

    if selected_indicator:
        fig = _build_surprise_chart(expectations, selected_indicator)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(
                f"No surprise data available for **{selected_indicator}**. "
                "Surprise is computed when both expected and actual values are recorded."
            )
else:
    st.info("Add expectation records to view surprise magnitude charts.")

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Asset Reaction Panel
# ---------------------------------------------------------------------------

st.subheader("⚡ Asset Reaction Panel")
st.caption(
    "Select a specific release to see asset price reactions in 5-minute, "
    "1-hour, and 1-day windows"
)

if expectations:
    # Only show releases that have actual values (i.e., already released)
    released = [r for r in expectations if r.actual_value is not None]

    if released:
        release_options = {
            f"{r.release_date} — {r.indicator} (Actual: {r.actual_value:.4g})": r
            for r in released
        }

        selected_release_key = st.selectbox(
            "Select Release",
            list(release_options.keys()),
            key="reaction_release",
        )

        if selected_release_key:
            selected_release = release_options[selected_release_key]

            # Check if we have cached reactions in the record
            if selected_release.asset_reactions:
                reactions = selected_release.asset_reactions
            else:
                # Compute reactions on the fly
                with st.spinner("Computing asset reactions..."):
                    reactions = _compute_release_reactions(selected_release.release_date)

            if reactions:
                chart_title = (
                    f"Asset Reactions: {selected_release.indicator} "
                    f"({selected_release.release_date})"
                )
                fig = _build_reaction_chart(reactions, chart_title)
                st.plotly_chart(fig, use_container_width=True)

                # Details table
                with st.expander("📋 Reaction Details"):
                    detail_rows = []
                    for asset_name, windows in reactions.items():
                        row = {"Asset": asset_name}
                        for w in REACTION_WINDOWS:
                            label = WINDOW_LABELS.get(w, w)
                            row[label] = f"{windows.get(w, 0.0):+.2f}%"
                        detail_rows.append(row)
                    st.dataframe(
                        pd.DataFrame(detail_rows),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.warning(
                    "Unable to compute reactions. Price data may not be available "
                    "for the selected release date."
                )
    else:
        st.info(
            "No released data yet. Record actual values in existing entries "
            "to see asset reactions."
        )
else:
    st.info("Add expectation records to analyze asset reactions.")

st.divider()

# ---------------------------------------------------------------------------
# Section 4: Pattern Analysis
# ---------------------------------------------------------------------------

st.subheader("🔍 Pattern Analysis")
st.caption(
    "Average asset reactions across all historical releases for a selected indicator"
)

if expectations:
    indicators_with_reactions = sorted(set(
        r.indicator for r in expectations if r.asset_reactions is not None
    ))

    if indicators_with_reactions:
        pattern_indicator = st.selectbox(
            "Select Indicator for Pattern Analysis",
            indicators_with_reactions,
            key="pattern_indicator",
        )

        if pattern_indicator:
            pattern_df = _compute_pattern_analysis(expectations, pattern_indicator)

            if pattern_df is not None and not pattern_df.empty:
                st.write(
                    f"**Average reactions across "
                    f"{pattern_df['Count'].iloc[0]} releases** "
                    f"of {pattern_indicator}:"
                )

                # Display as a formatted table
                display_df = pattern_df.copy()
                for col in [WINDOW_LABELS[w] for w in REACTION_WINDOWS]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(
                            lambda x: f"{x:+.2f}%"
                        )
                st.dataframe(
                    display_df.drop(columns=["Count"]),
                    use_container_width=True,
                    hide_index=True,
                )

                # Also show as a grouped bar chart
                fig = go.Figure()
                assets = pattern_df["Asset"].tolist()
                for window in REACTION_WINDOWS:
                    label = WINDOW_LABELS.get(window, window)
                    values = pattern_df[label].tolist()
                    fig.add_trace(
                        go.Bar(
                            name=label,
                            x=assets,
                            y=values,
                            text=[f"{v:+.2f}%" for v in values],
                            textposition="auto",
                        )
                    )

                fig.update_layout(
                    barmode="group",
                    title=f"Average Asset Reactions: {pattern_indicator}",
                    xaxis_title="Asset",
                    yaxis_title="Mean Price Change (%)",
                    height=450,
                    margin=dict(l=50, r=50, t=60, b=80),
                    legend_title="Window",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(
                    f"No reaction data available for **{pattern_indicator}**. "
                    "Reactions are recorded when actual values are entered."
                )
    else:
        st.info(
            "No releases with recorded asset reactions yet. "
            "Reactions are computed when actual values are provided."
        )
else:
    st.info("Add expectation records to view pattern analysis.")

st.divider()

# ---------------------------------------------------------------------------
# Section 5: Expectation Entry Form
# ---------------------------------------------------------------------------

st.subheader("➕ Record Expectation")
st.caption("Enter expected and actual values for economic releases")

with st.form("add_expectation_form", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
        release_date = st.date_input(
            "Release Date",
            value=date.today(),
            help="Date of the economic data release",
        )
        indicator = st.text_input(
            "Indicator",
            placeholder="e.g., CPI, NFP, Fed Funds",
            help="Name of the economic indicator",
        )

    with col2:
        expected_value = st.number_input(
            "Expected Value",
            value=0.0,
            format="%.4f",
            help="Consensus expected value",
        )
        actual_value_input = st.number_input(
            "Actual Value (optional)",
            value=0.0,
            format="%.4f",
            help="Leave as 0 if not yet released; fill in after release",
        )

    # Advanced: allow user to specify historical std for surprise calculation
    with st.expander("⚙️ Advanced Settings"):
        historical_std = st.number_input(
            "Historical Std Dev",
            value=DEFAULT_HISTORICAL_STD,
            min_value=0.01,
            format="%.4f",
            help=(
                "Historical standard deviation of surprises for this indicator. "
                "Used to normalize the surprise magnitude. Default: 0.5"
            ),
        )
        include_actual = st.checkbox(
            "Include actual value",
            value=False,
            help="Check this if the actual value has been released",
        )

    submitted = st.form_submit_button(
        "💾 Save Expectation", use_container_width=True
    )

    if submitted:
        # Validation
        errors = []
        if not indicator or not indicator.strip():
            errors.append("Indicator name is required.")
        if not isinstance(release_date, date):
            errors.append("Please select a valid release date.")

        if errors:
            for err in errors:
                st.error(err)
        elif db is not None:
            try:
                # Determine actual value and surprise
                actual = actual_value_input if include_actual else None
                surprise = None
                asset_reactions = None

                if actual is not None:
                    surprise = compute_surprise_magnitude(
                        actual=actual,
                        expected=expected_value,
                        historical_std=historical_std,
                    )
                    # Compute asset reactions for this release
                    reactions = _compute_release_reactions(release_date)
                    if reactions:
                        asset_reactions = reactions

                record = ExpectationRecord(
                    id=None,
                    release_date=release_date,
                    indicator=indicator.strip(),
                    expected_value=expected_value,
                    actual_value=actual,
                    surprise_magnitude=surprise,
                    asset_reactions=asset_reactions,
                )
                db.save_expectation(record)

                surprise_msg = (
                    f" | Surprise: {surprise:+.2f}σ" if surprise is not None else ""
                )
                st.success(
                    f"✅ Expectation saved: **{indicator.strip()}** on "
                    f"{release_date} (Expected: {expected_value:.4g}"
                    f"{', Actual: ' + f'{actual:.4g}' if actual is not None else ''}"
                    f"{surprise_msg})"
                )
            except Exception as e:
                st.error(f"Failed to save expectation: {e}")
        else:
            st.warning(
                "Database not connected. Configure Supabase credentials in "
                "`.streamlit/secrets.toml` to save expectations."
            )
