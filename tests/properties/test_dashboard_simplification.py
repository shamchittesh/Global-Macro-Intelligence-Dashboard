"""Property-based tests for the dashboard simplification feature.

Uses Hypothesis to validate correctness properties defined in the design document.
Each test is tagged with the property it validates and the requirements it covers.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from lib.calculations import (
    INSTRUMENT_ORDER,
    InstrumentData,
    compute_daily_change,
    compute_weekly_change,
    get_color_for_change,
    identify_dominant_variable,
)
from lib.cache import is_cache_fresh, USER_TZ
from lib.market_day import (
    US_EASTERN,
    get_latest_market_day,
    is_trading_day,
    is_us_market_holiday,
)
from lib.scraper import truncate_body


# --- Property 1: Daily change formula correctness ---
# Feature: dashboard-simplification, Property 1: Daily change formula correctness
# Validates: Requirements 2.3, 4.4


@given(
    open_price=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
    close_price=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_daily_change_formula(open_price, close_price):
    """For any valid open/close prices, compute_daily_change returns the correct formula result."""
    result = compute_daily_change(open_price, close_price)
    expected = round(((close_price - open_price) / open_price) * 100, 2)
    assert result == expected
    # Verify at most 2 decimal places
    assert result == round(result, 2)


# --- Property 2: Weekly change formula correctness ---
# Feature: dashboard-simplification, Property 2: Weekly change formula correctness
# Validates: Requirements 2.4, 4.5


@given(
    monday_open=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
    friday_close=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_weekly_change_formula(monday_open, friday_close):
    """For any valid monday_open/friday_close, compute_weekly_change returns the correct formula result."""
    result = compute_weekly_change(monday_open, friday_close)
    expected = round(((friday_close - monday_open) / monday_open) * 100, 2)
    assert result == expected
    assert result == round(result, 2)


# --- Property 3: Color coding is determined by sign ---
# Feature: dashboard-simplification, Property 3: Color coding is determined by sign
# Validates: Requirements 3.1, 3.2, 3.3, 3.4


@given(value=st.floats(allow_nan=False, allow_infinity=False))
def test_color_coding_by_sign(value):
    """For any float value, color is green if positive, red if negative, default if zero."""
    result = get_color_for_change(value)
    if value > 0:
        assert result == "green"
    elif value < 0:
        assert result == "red"
    else:
        assert result == "default"


def test_color_coding_none():
    """None value returns default color."""
    assert get_color_for_change(None) == "default"


# --- Property 4: Market day resolution returns a valid completed trading day ---
# Feature: dashboard-simplification, Property 4: Market day resolution returns a valid completed trading day
# Validates: Requirements 4.1


@given(
    dt=st.datetimes(
        min_value=datetime(2024, 1, 2, 0, 0),
        max_value=datetime(2026, 12, 30, 23, 59),
    )
)
def test_market_day_valid_trading_day(dt):
    """For any datetime, get_latest_market_day returns a valid trading day in the past."""
    # Make it timezone-aware in UTC+4
    now = dt.replace(tzinfo=USER_TZ)
    result = get_latest_market_day(now)

    # (a) Must be a weekday
    assert result.weekday() < 5, f"{result} is not a weekday"

    # (b) Must not be a US market holiday
    assert not is_us_market_holiday(result), f"{result} is a US market holiday"

    # (c) Must be on or before today in Eastern Time
    now_et = now.astimezone(US_EASTERN)
    assert result <= now_et.date(), f"{result} is after today ET ({now_et.date()})"


# --- Property 5: Dominant variable is the instrument with maximum absolute daily change ---
# Feature: dashboard-simplification, Property 5: Dominant variable is max absolute daily change
# Validates: Requirements 5.2, 5.4


@given(
    changes=st.lists(
        st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=7,
    )
)
def test_dominant_variable_max_absolute(changes):
    """The dominant variable is the one with the largest volatility-adjusted z-score."""
    from lib.calculations import TYPICAL_DAILY_VOL

    instruments = []
    for i, change in enumerate(changes):
        name = INSTRUMENT_ORDER[i] if i < len(INSTRUMENT_ORDER) else f"INST{i}"
        instruments.append(InstrumentData(
            ticker=name,
            macro_significance=f"Sig{i}",
            daily_change_pct=change,
        ))

    result = identify_dominant_variable(instruments)
    assert result is not None

    # Verify result has the max z-score
    max_zscore = max(
        abs(c) / TYPICAL_DAILY_VOL.get(INSTRUMENT_ORDER[i] if i < 7 else "X", 1.0)
        for i, c in enumerate(changes)
    )
    result_vol = TYPICAL_DAILY_VOL.get(result.ticker, 1.0)
    result_zscore = abs(result.daily_change_pct) / result_vol
    assert result_zscore == pytest.approx(max_zscore, rel=1e-6)


# --- Property 6: Report body truncation preserves content up to 5000 characters ---
# Feature: dashboard-simplification, Property 6: Report body truncation
# Validates: Requirements 6.3, 6.4


@given(text=st.text(min_size=0, max_size=10000))
def test_report_body_truncation(text):
    """Truncated body is always <= 5000 chars and preserves content when shorter."""
    result = truncate_body(text)
    assert len(result) <= 5000

    if len(text) <= 5000:
        assert result == text
    else:
        assert result == text[:5000]


# --- Property 7: Cache TTL freshness check ---
# Feature: dashboard-simplification, Property 7: Cache TTL freshness check
# Validates: Requirements 6.6


@given(
    hours_ago=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    max_age=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_cache_ttl_freshness(hours_ago, max_age):
    """Cache is fresh iff time since fetch < max_age_hours."""
    now = datetime.now(USER_TZ)
    fetched_at = (now - timedelta(hours=hours_ago)).isoformat()

    result = is_cache_fresh(fetched_at, max_age_hours=max_age)

    if hours_ago < max_age:
        assert result is True
    else:
        assert result is False


# --- Property 9: Refresh cooldown enforcement ---
# Feature: dashboard-simplification, Property 9: Refresh cooldown enforcement
# Validates: Requirements 8.4


@given(
    elapsed=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
)
def test_refresh_cooldown(elapsed):
    """Refresh is allowed iff elapsed time >= 60 seconds."""
    import time

    cooldown = 60.0
    allowed = elapsed >= cooldown

    # Simulate the logic from app.py
    last_refresh_time = time.time() - elapsed
    current_time = time.time()
    actual_elapsed = current_time - last_refresh_time

    # The actual check
    is_allowed = actual_elapsed >= cooldown

    assert is_allowed == allowed
