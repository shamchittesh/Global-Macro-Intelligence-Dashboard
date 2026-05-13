"""Cross-Asset Relationship page - Correlation analysis and multi-asset overlays."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.figure_factory as ff
from datetime import datetime, timedelta

from lib.models import DEFAULT_ASSETS, TrackedAsset
from lib.data_fetcher import (
    fetch_asset_data_cached,
    DataFetchError,
    InvalidSymbolError,
)
from lib.calculations import (
    compute_correlation_matrix,
    normalize_prices,
    compute_correlation_changes,
)

st.set_page_config(page_title="Cross-Asset Relationships", page_icon="🔗", layout="wide")
st.title("🔗 Cross-Asset Relationships")
st.caption("Correlation analysis, normalized overlays, and regime shift detection")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIME_WINDOW_MAP = {
    "1 Week": 5,
    "1 Month": 21,
    "3 Months": 63,
    "6 Months": 126,
    "1 Year": 252,
}

# Colors for overlay chart series
SERIES_COLORS = [
    "#2962FF",  # Blue
    "#FF6D00",  # Orange
    "#00C853",  # Green
    "#AA00FF",  # Purple
    "#FF1744",  # Red
    "#00BFA5",  # Teal
    "#FFD600",  # Yellow
    "#C51162",  # Pink
]

# ---------------------------------------------------------------------------
# Helper: Fetch daily close prices for all default assets
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner="Fetching price data...")
def _fetch_all_close_prices(lookback_days: int) -> dict[str, pd.Series]:
    """Fetch daily close prices for all DEFAULT_ASSETS over the lookback period.

    Returns dict mapping display_name -> close price Series with DatetimeIndex.
    """
    end_dt = datetime.now()
    # Fetch extra days to account for weekends/holidays
    start_dt = end_dt - timedelta(days=int(lookback_days * 1.6) + 10)

    price_data: dict[str, pd.Series] = {}

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
                price_data[asset.display_name] = df["close"]
        except (DataFetchError, InvalidSymbolError, Exception):
            continue

    return price_data


def _compute_returns(price_data: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Convert price series to daily returns for correlation computation."""
    returns: dict[str, pd.Series] = {}
    for name, series in price_data.items():
        if len(series) >= 2:
            ret = series.pct_change().dropna()
            if not ret.empty:
                returns[name] = ret
    return returns


# ---------------------------------------------------------------------------
# Section 1: Correlation Matrix Heatmap
# ---------------------------------------------------------------------------

st.subheader("Correlation Matrix")

# Time window selector
selected_window_label = st.selectbox(
    "Time Window",
    list(TIME_WINDOW_MAP.keys()),
    index=1,  # Default to 1 Month
    help="Rolling correlation window in trading days",
)
window_days = TIME_WINDOW_MAP[selected_window_label]

# Fetch price data
price_data = _fetch_all_close_prices(window_days)

if len(price_data) < 2:
    st.warning("Insufficient data to compute correlations. Need at least 2 assets with data.")
else:
    # Compute returns and correlation matrix
    returns_data = _compute_returns(price_data)

    if len(returns_data) < 2:
        st.warning("Insufficient return data to compute correlations.")
    else:
        corr_matrix = compute_correlation_matrix(returns_data, window=window_days)

        if corr_matrix.empty:
            st.warning("Could not compute correlation matrix.")
        else:
            # Build the annotated heatmap
            asset_names = list(corr_matrix.columns)
            z_values = corr_matrix.values.tolist()

            # Round annotations for readability
            z_text = [[f"{val:.2f}" if not np.isnan(val) else "N/A" for val in row] for row in z_values]

            fig = ff.create_annotated_heatmap(
                z=z_values,
                x=asset_names,
                y=asset_names,
                annotation_text=z_text,
                colorscale=[
                    [0.0, "#EF5350"],   # -1: Red
                    [0.5, "#FFFFFF"],   # 0: White
                    [1.0, "#26A69A"],   # +1: Green
                ],
                zmin=-1,
                zmax=1,
                showscale=True,
            )

            fig.update_layout(
                title=f"Rolling Correlation ({selected_window_label} = {window_days} trading days)",
                height=500,
                xaxis=dict(side="bottom"),
                margin=dict(l=100, r=50, t=80, b=100),
            )

            st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Correlation Shift Detection
# ---------------------------------------------------------------------------

st.subheader("⚠️ Correlation Shift Alerts")
st.caption("Highlights asset pairs where correlation shifted by more than 0.3 over the past 5 trading days")

if len(price_data) >= 2:
    returns_data = _compute_returns(price_data)

    if len(returns_data) >= 2:
        # Current 5-day window correlation
        current_corr = compute_correlation_matrix(returns_data, window=5)

        # Prior 5-day window: we need returns shifted back by 5 days
        # Use days 6-10 from the end as the prior window
        prior_returns: dict[str, pd.Series] = {}
        for name, series in returns_data.items():
            if len(series) > 10:
                # Prior window: from -10 to -5 (exclusive of last 5)
                prior_returns[name] = series.iloc[:-5]
            elif len(series) > 5:
                prior_returns[name] = series.iloc[:-5]

        if len(prior_returns) >= 2:
            prior_corr = compute_correlation_matrix(prior_returns, window=5)

            shifts = compute_correlation_changes(current_corr, prior_corr, threshold=0.3)

            if shifts:
                for shift in shifts:
                    direction = "↑" if shift.change > 0 else "↓"
                    severity = "🔴" if abs(shift.change) > 0.5 else "🟡"
                    st.warning(
                        f"{severity} **{shift.asset_a}** ↔ **{shift.asset_b}**: "
                        f"Correlation shifted {direction} by {shift.change:+.3f} "
                        f"(from {shift.previous_corr:.2f} to {shift.current_corr:.2f})"
                    )
            else:
                st.success("✅ No significant correlation shifts detected in the past 5 trading days.")
        else:
            st.info("Insufficient historical data to compute prior correlation window.")
    else:
        st.info("Insufficient return data for shift detection.")
else:
    st.info("Need at least 2 assets with data for shift detection.")

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Normalized Price Overlay Chart
# ---------------------------------------------------------------------------

st.subheader("Normalized Price Overlay")
st.caption("Compare relative performance of selected assets (base = 100)")

# Multi-asset selector
asset_display_names = [a.display_name for a in DEFAULT_ASSETS]
selected_assets = st.multiselect(
    "Select Assets to Compare",
    asset_display_names,
    default=asset_display_names[:3],  # Default to first 3 assets
    help="Select 2 or more assets to overlay their normalized price movements",
)

if len(selected_assets) < 2:
    st.info("Please select at least 2 assets to display the overlay chart.")
else:
    # Filter price data to selected assets
    selected_price_data = {
        name: series for name, series in price_data.items() if name in selected_assets
    }

    if len(selected_price_data) < 2:
        st.warning("Could not fetch data for enough selected assets.")
    else:
        # Align all series to a common index
        combined_df = pd.DataFrame(selected_price_data)
        combined_df = combined_df.dropna(how="all")

        if combined_df.empty:
            st.warning("No overlapping data for selected assets.")
        else:
            # Use the first available date as the base date for normalization
            base_date = combined_df.index[0]

            # Build price_series dict for normalization
            price_series_for_norm = {
                name: combined_df[name].dropna() for name in selected_assets if name in combined_df.columns
            }

            normalized = normalize_prices(price_series_for_norm, base_date)

            if normalized:
                from streamlit_lightweight_charts import renderLightweightCharts

                # Build multiple line series for the overlay chart
                series_list = []
                for i, (name, norm_series) in enumerate(normalized.items()):
                    if norm_series.empty:
                        continue

                    color = SERIES_COLORS[i % len(SERIES_COLORS)]

                    line_data = []
                    for idx, val in norm_series.items():
                        if pd.notna(val):
                            time_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                            line_data.append({"time": time_str, "value": float(val)})

                    if line_data:
                        series_list.append({
                            "type": "Line",
                            "data": line_data,
                            "options": {
                                "color": color,
                                "lineWidth": 2,
                                "title": name,
                            },
                        })

                if series_list:
                    chart_options = {
                        "chart": {
                            "layout": {
                                "background": {"color": "#1E1E1E"},
                                "textColor": "#DDD",
                            },
                            "height": 450,
                            "timeScale": {
                                "timeVisible": True,
                                "secondsVisible": False,
                            },
                        },
                        "series": series_list,
                    }

                    renderLightweightCharts(
                        [chart_options],
                        key=f"overlay_{'_'.join(sorted(selected_assets))}_{selected_window_label}",
                    )

                    # Legend
                    legend_cols = st.columns(len(series_list))
                    for i, series in enumerate(series_list):
                        with legend_cols[i]:
                            color = series["options"]["color"]
                            name = series["options"]["title"]
                            st.markdown(
                                f'<span style="color:{color}; font-weight:bold;">● {name}</span>',
                                unsafe_allow_html=True,
                            )
                else:
                    st.warning("No valid normalized data to display.")
            else:
                st.warning("Normalization failed for selected assets.")
