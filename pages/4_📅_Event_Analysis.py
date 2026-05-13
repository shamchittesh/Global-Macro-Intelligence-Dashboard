"""Event Analysis page - Analyze how macro events impact cross-asset pricing."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

from lib.models import DEFAULT_ASSETS, EventCategory, MacroEvent
from lib.data_fetcher import (
    fetch_asset_data_cached,
    DataFetchError,
    InvalidSymbolError,
)
from lib.calculations import compute_asset_reaction
from lib.db import get_db

st.set_page_config(page_title="Event Analysis", page_icon="📅", layout="wide")
st.title("📅 Event Analysis")
st.caption("Analyze how historical macro events impact cross-asset pricing")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REACTION_WINDOWS = ["1day", "5day", "21day"]
WINDOW_LABELS = {"1day": "1 Day", "5day": "1 Week", "21day": "1 Month"}

# Mapping from trading-day windows to calendar days for data fetching
WINDOW_CALENDAR_DAYS = {"1day": 2, "5day": 10, "21day": 45}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_event_reactions(
    event_date: date,
) -> dict[str, dict[str, float]]:
    """Compute asset reactions for all DEFAULT_ASSETS around an event date.

    Fetches price data in a window around the event and computes percentage
    change for 1-day, 5-day (1 week), and 21-day (1 month) windows.

    Returns:
        Dict mapping asset display_name -> {window_label: pct_change}
    """
    reactions: dict[str, dict[str, float]] = {}

    # We need data from 1 month before to 1 month after the event
    start_dt = datetime.combine(event_date - timedelta(days=45), datetime.min.time())
    end_dt = datetime.combine(event_date + timedelta(days=45), datetime.min.time())
    release_ts = datetime.combine(event_date, datetime.min.time())

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
    reactions: dict[str, dict[str, float]], event_description: str
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
        title=f"Asset Reactions: {event_description}",
        xaxis_title="Asset",
        yaxis_title="Price Change (%)",
        height=450,
        margin=dict(l=50, r=50, t=60, b=80),
        legend_title="Window",
    )

    return fig


def _build_comparison_chart(
    comparison_data: list[dict],
) -> go.Figure:
    """Build a comparison chart across multiple events of the same category.

    comparison_data: list of dicts with keys 'description', 'date', 'reactions'
    """
    fig = go.Figure()

    assets = list(DEFAULT_ASSETS)
    asset_names = [a.display_name for a in assets]

    for event_info in comparison_data:
        desc = event_info["description"]
        event_date = event_info["date"]
        reactions = event_info["reactions"]
        label = f"{desc} ({event_date})"

        # Use 1-day reaction for comparison
        values = [reactions.get(name, {}).get("1day", 0.0) for name in asset_names]
        fig.add_trace(
            go.Bar(
                name=label,
                x=asset_names,
                y=values,
                text=[f"{v:+.2f}%" for v in values],
                textposition="auto",
            )
        )

    fig.update_layout(
        barmode="group",
        title="Cross-Event Comparison (1-Day Reaction)",
        xaxis_title="Asset",
        yaxis_title="Price Change (%)",
        height=500,
        margin=dict(l=50, r=50, t=60, b=80),
        legend_title="Event",
    )

    return fig


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

db = get_db()

# ---------------------------------------------------------------------------
# Section 1: Event List with Category Filtering
# ---------------------------------------------------------------------------

st.subheader("📋 Macro Events")

# Category filter
category_options = ["All"] + [cat.value for cat in EventCategory]
category_labels = {
    "All": "All Categories",
    "monetary_policy": "Monetary Policy",
    "inflation_data": "Inflation Data",
    "geopolitical": "Geopolitical",
    "fiscal_policy": "Fiscal Policy",
}

selected_category = st.selectbox(
    "Filter by Category",
    category_options,
    format_func=lambda x: category_labels.get(x, x),
)

# Fetch events
events: list[MacroEvent] = []
if db is not None:
    try:
        cat_filter = None if selected_category == "All" else selected_category
        events = db.get_macro_events(category=cat_filter)
    except Exception as e:
        st.error(f"Failed to load events: {e}")

if events:
    # Display events in a table
    event_data = []
    for ev in events:
        event_data.append({
            "Date": ev.date,
            "Description": ev.description,
            "Category": category_labels.get(ev.category.value, ev.category.value),
            "Custom": "✓" if ev.is_custom else "",
        })

    df_events = pd.DataFrame(event_data)
    st.dataframe(df_events, use_container_width=True, hide_index=True)
else:
    if db is None:
        st.warning(
            "Database not connected. Configure Supabase credentials in "
            "`.streamlit/secrets.toml` to view and manage events."
        )
    else:
        st.info(
            "No events found. Use the form below to add macro events."
        )

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Event Impact Analysis
# ---------------------------------------------------------------------------

st.subheader("📊 Event Impact Analysis")
st.caption(
    "Select an event to see how all tracked assets reacted in 1-day, 1-week, "
    "and 1-month windows"
)

if events:
    # Event selector
    event_options = {
        f"{ev.date} — {ev.description}": ev for ev in events
    }
    selected_event_key = st.selectbox(
        "Select Event",
        list(event_options.keys()),
    )

    if selected_event_key:
        selected_event = event_options[selected_event_key]

        with st.spinner("Computing asset reactions..."):
            reactions = _fetch_event_reactions(selected_event.date)

        if reactions:
            fig = _build_reaction_chart(reactions, selected_event.description)
            st.plotly_chart(fig, use_container_width=True)

            # Also show as a table
            with st.expander("📋 Reaction Details"):
                table_data = []
                for asset_name, windows in reactions.items():
                    row = {"Asset": asset_name}
                    for w in REACTION_WINDOWS:
                        label = WINDOW_LABELS.get(w, w)
                        row[label] = f"{windows.get(w, 0.0):+.2f}%"
                    table_data.append(row)
                st.dataframe(
                    pd.DataFrame(table_data),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.warning(
                "Unable to compute reactions. Price data may not be available "
                "for the selected event date."
            )
else:
    st.info("Add events using the form below to analyze their market impact.")

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Cross-Event Comparison
# ---------------------------------------------------------------------------

st.subheader("🔄 Cross-Event Comparison")
st.caption("Compare asset reactions across similar event types")

if events and len(events) >= 2:
    # Filter by category for comparison
    comparison_category = st.selectbox(
        "Compare events in category",
        [cat.value for cat in EventCategory],
        format_func=lambda x: category_labels.get(x, x),
        key="comparison_category",
    )

    # Get events for this category
    comparison_events = [
        ev for ev in events if ev.category.value == comparison_category
    ]

    if not comparison_events and db is not None:
        try:
            comparison_events = db.get_macro_events(category=comparison_category)
        except Exception:
            comparison_events = []

    if comparison_events:
        # Limit to most recent 5 events for readability
        comparison_events = comparison_events[:5]

        st.write(
            f"Comparing **{len(comparison_events)}** "
            f"{category_labels.get(comparison_category, comparison_category)} events"
        )

        if st.button("🔄 Compute Comparison", use_container_width=True):
            comparison_data = []
            progress_bar = st.progress(0)

            for i, ev in enumerate(comparison_events):
                reactions = _fetch_event_reactions(ev.date)
                if reactions:
                    comparison_data.append({
                        "description": ev.description[:30],
                        "date": str(ev.date),
                        "reactions": reactions,
                    })
                progress_bar.progress((i + 1) / len(comparison_events))

            progress_bar.empty()

            if comparison_data:
                fig = _build_comparison_chart(comparison_data)
                st.plotly_chart(fig, use_container_width=True)

                # Summary table
                with st.expander("📋 Comparison Details"):
                    for item in comparison_data:
                        st.write(f"**{item['description']}** ({item['date']})")
                        table_rows = []
                        for asset_name, windows in item["reactions"].items():
                            row = {"Asset": asset_name}
                            for w in REACTION_WINDOWS:
                                label = WINDOW_LABELS.get(w, w)
                                row[label] = f"{windows.get(w, 0.0):+.2f}%"
                            table_rows.append(row)
                        st.dataframe(
                            pd.DataFrame(table_rows),
                            use_container_width=True,
                            hide_index=True,
                        )
            else:
                st.warning("Could not compute reactions for the selected events.")
    else:
        st.info(
            f"No events found in the "
            f"{category_labels.get(comparison_category, comparison_category)} category."
        )
else:
    st.info("Add at least 2 events to enable cross-event comparison.")

st.divider()

# ---------------------------------------------------------------------------
# Section 4: Custom Event Entry Form
# ---------------------------------------------------------------------------

st.subheader("➕ Add Custom Event")
st.caption("Record a macro event for future analysis")

with st.form("add_event_form", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
        event_date = st.date_input(
            "Event Date",
            value=date.today(),
            help="Date of the macro event",
        )

    with col2:
        event_category = st.selectbox(
            "Category",
            [cat for cat in EventCategory],
            format_func=lambda x: category_labels.get(x.value, x.value),
        )

    event_description = st.text_area(
        "Description",
        placeholder="Describe the macro event (e.g., 'Fed raises rates 25bps', 'CPI comes in hot at 3.5%')",
        max_chars=500,
        help="Max 500 characters",
    )

    submitted = st.form_submit_button("💾 Save Event", use_container_width=True)

    if submitted:
        # Validation
        errors = []
        if not event_description or not event_description.strip():
            errors.append("Description is required.")
        elif len(event_description.strip()) > 500:
            errors.append("Description must be 500 characters or fewer.")

        if not isinstance(event_date, date):
            errors.append("Please select a valid date.")

        if errors:
            for err in errors:
                st.error(err)
        elif db is not None:
            try:
                new_event = MacroEvent(
                    id=None,
                    date=event_date,
                    description=event_description.strip(),
                    category=event_category,
                    is_custom=True,
                )
                db.save_macro_event(new_event)
                st.success(
                    f"✅ Event saved: **{event_description.strip()[:50]}** "
                    f"on {event_date}"
                )
            except Exception as e:
                st.error(f"Failed to save event: {e}")
        else:
            st.warning(
                "Database not connected. Configure Supabase credentials in "
                "`.streamlit/secrets.toml` to save events."
            )
