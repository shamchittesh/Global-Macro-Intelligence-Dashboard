"""Asset Monitor page - Real-time macro asset monitoring with interactive charts."""

import streamlit as st
from datetime import datetime, timedelta, date

from lib.models import (
    DEFAULT_ASSETS,
    INTERVALS,
    ChartType,
    AssetSource,
    TrackedAsset,
)
from lib.data_fetcher import (
    DataFetcher,
    fetch_asset_data_cached,
    fetch_current_prices_cached,
    InvalidSymbolError,
    DataFetchError,
)
from lib.db import get_db

st.set_page_config(page_title="Asset Monitor", page_icon="📊", layout="wide")
st.title("📊 Asset Monitor")
st.caption("Real-time macro asset monitoring with interactive charts")

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if "custom_assets" not in st.session_state:
    st.session_state["custom_assets"] = []

# ---------------------------------------------------------------------------
# Load custom assets from database
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def _load_custom_assets_from_db() -> list[dict]:
    """Load custom assets from Supabase (cached for 60s)."""
    db = get_db()
    if db is None:
        return []
    try:
        custom = db.get_custom_assets()
        return [
            {"symbol": ca.symbol, "display_name": ca.display_name, "source": ca.source.value}
            for ca in custom
        ]
    except Exception:
        return []


db_custom_assets = _load_custom_assets_from_db()
if db_custom_assets and not st.session_state["custom_assets"]:
    st.session_state["custom_assets"] = db_custom_assets

# ---------------------------------------------------------------------------
# Build full asset list (defaults + custom)
# ---------------------------------------------------------------------------

all_assets: list[TrackedAsset] = list(DEFAULT_ASSETS)
for ca in st.session_state["custom_assets"]:
    all_assets.append(
        TrackedAsset(
            symbol=ca["symbol"],
            display_name=ca["display_name"],
            source=AssetSource(ca["source"]),
        )
    )

# ---------------------------------------------------------------------------
# Price Panels
# ---------------------------------------------------------------------------

st.subheader("Price Overview")

try:
    symbols_tuple = tuple(a.symbol for a in all_assets)
    prices = fetch_current_prices_cached(symbols_tuple)
except Exception as e:
    st.warning(f"Unable to fetch current prices: {e}")
    prices = {}

# Render price panels in a grid using st.columns
cols_per_row = 4
rows = [all_assets[i : i + cols_per_row] for i in range(0, len(all_assets), cols_per_row)]

for row_assets in rows:
    cols = st.columns(len(row_assets))
    for col, asset in zip(cols, row_assets):
        with col:
            price_data = prices.get(asset.symbol)
            if price_data:
                col.metric(
                    label=asset.display_name,
                    value=f"{price_data.price:.2f}",
                    delta=f"{price_data.change:+.2f} ({price_data.pct_change:+.2f}%)",
                )
                col.caption(f"Updated: {price_data.timestamp.strftime('%Y-%m-%d %H:%M')}")
            else:
                col.metric(label=asset.display_name, value="N/A", delta="—")
                col.caption("Data unavailable")

st.divider()

# ---------------------------------------------------------------------------
# Chart Controls (Sidebar)
# ---------------------------------------------------------------------------

st.subheader("Asset Charts")

# Asset selector
asset_names = [a.display_name for a in all_assets]
selected_asset_name = st.selectbox("Select Asset", asset_names, index=0)
selected_asset = next(a for a in all_assets if a.display_name == selected_asset_name)

# Interval selector
interval_labels = {key: cfg["label"] for key, cfg in INTERVALS.items()}
interval_keys = list(interval_labels.keys())
interval_display = list(interval_labels.values())
selected_interval_display = st.selectbox("Interval", interval_display, index=interval_keys.index("1day"))
selected_interval = interval_keys[interval_display.index(selected_interval_display)]

# Chart type toggle
chart_type_str = st.radio("Chart Type", ["Candlestick", "Line"], horizontal=True)
chart_type = ChartType.CANDLESTICK if chart_type_str == "Candlestick" else ChartType.LINE

# Date range controls
col_start, col_end = st.columns(2)
with col_start:
    start_date = st.date_input(
        "Start Date",
        value=date.today() - timedelta(days=90),
        max_value=date.today(),
    )
with col_end:
    end_date = st.date_input(
        "End Date",
        value=date.today(),
        max_value=date.today(),
    )

# Validate date range
if start_date >= end_date:
    st.error("Start date must be before end date.")
    st.stop()

# ---------------------------------------------------------------------------
# Fetch and render chart
# ---------------------------------------------------------------------------

start_dt = datetime.combine(start_date, datetime.min.time())
end_dt = datetime.combine(end_date, datetime.max.time())

try:
    df = fetch_asset_data_cached(
        symbol=selected_asset.symbol,
        interval=selected_interval,
        start_date=start_dt,
        end_date=end_dt,
        source_value=selected_asset.source.value,
    )
except InvalidSymbolError as e:
    st.error(f"Invalid symbol: {e}")
    df = None
except DataFetchError as e:
    st.error(f"Data fetch error: {e}")
    df = None
except Exception as e:
    st.error(f"Unexpected error fetching data: {e}")
    df = None

if df is not None and not df.empty:
    from streamlit_lightweight_charts import renderLightweightCharts

    # Prepare chart data
    if chart_type == ChartType.CANDLESTICK:
        chart_data = []
        for idx, row in df.iterrows():
            time_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            chart_data.append({
                "time": time_str,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
        series_type = "Candlestick"
    else:
        chart_data = []
        for idx, row in df.iterrows():
            time_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            chart_data.append({
                "time": time_str,
                "value": float(row["close"]),
            })
        series_type = "Line"

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
        "series": [
            {
                "type": series_type,
                "data": chart_data,
                "options": {
                    "upColor": "#26a69a",
                    "downColor": "#ef5350",
                    "borderVisible": False,
                    "wickUpColor": "#26a69a",
                    "wickDownColor": "#ef5350",
                }
                if series_type == "Candlestick"
                else {"color": "#2962FF", "lineWidth": 2},
            }
        ],
    }

    renderLightweightCharts(
        [chart_options],
        key=f"chart_{selected_asset.symbol}_{selected_interval}_{chart_type.value}",
    )

    # Show data summary
    with st.expander("Data Summary"):
        st.write(f"**Symbol:** {selected_asset.symbol} ({selected_asset.display_name})")
        st.write(f"**Interval:** {interval_labels[selected_interval]}")
        st.write(f"**Data points:** {len(df)}")
        st.write(f"**Range:** {df.index[0]} to {df.index[-1]}")
elif df is not None and df.empty:
    st.info("No data available for the selected asset and date range.")

st.divider()

# ---------------------------------------------------------------------------
# Custom Asset Addition Form
# ---------------------------------------------------------------------------

st.subheader("Add Custom Asset")

with st.form("add_custom_asset", clear_on_submit=True):
    st.write("Add a custom ticker to your monitoring view.")
    form_symbol = st.text_input("Ticker Symbol", placeholder="e.g., AAPL, TSLA, ^IXIC")
    form_name = st.text_input("Display Name", placeholder="e.g., Apple Inc.")
    submitted = st.form_submit_button("Add Asset")

    if submitted:
        if not form_symbol or not form_symbol.strip():
            st.error("Please enter a ticker symbol.")
        elif not form_name or not form_name.strip():
            st.error("Please enter a display name.")
        else:
            symbol_clean = form_symbol.strip().upper()
            name_clean = form_name.strip()

            # Check for duplicates
            existing_symbols = [a.symbol for a in all_assets]
            if symbol_clean in existing_symbols:
                st.error(f"Asset '{symbol_clean}' is already being tracked.")
            else:
                # Validate that data exists for this symbol
                with st.spinner(f"Validating symbol '{symbol_clean}'..."):
                    try:
                        validation_start = datetime.now() - timedelta(days=7)
                        validation_end = datetime.now()
                        fetcher = DataFetcher()
                        test_df = fetcher.get_asset_data(
                            symbol=symbol_clean,
                            interval="1day",
                            start_date=validation_start,
                            end_date=validation_end,
                        )
                        if test_df is None or test_df.empty:
                            st.error(
                                f"No data found for symbol '{symbol_clean}'. "
                                "Please verify the ticker is correct."
                            )
                        else:
                            # Symbol is valid - save to session state
                            new_asset = {
                                "symbol": symbol_clean,
                                "display_name": name_clean,
                                "source": AssetSource.YFINANCE.value,
                            }
                            st.session_state["custom_assets"].append(new_asset)

                            # Persist to database if available
                            db = get_db()
                            if db is not None:
                                try:
                                    db.save_custom_asset(symbol_clean, name_clean)
                                except Exception as db_err:
                                    st.warning(
                                        f"Asset added locally but failed to persist: {db_err}"
                                    )

                            st.success(
                                f"✅ Added '{name_clean}' ({symbol_clean}) to your watchlist."
                            )
                            st.rerun()
                    except InvalidSymbolError:
                        st.error(
                            f"Symbol '{symbol_clean}' not found. "
                            "Please check the ticker and try again."
                        )
                    except DataFetchError as e:
                        st.error(f"Could not validate symbol: {e}")
                    except Exception as e:
                        st.error(f"Validation failed: {e}")
