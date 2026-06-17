"""Calculations module for the Global Macro Intelligence Dashboard.

Pure functions for computing daily/weekly percentage changes,
identifying the dominant variable, and determining color coding.
No Streamlit or network dependencies.
"""

from dataclasses import dataclass


# --- Instrument Configuration ---

INSTRUMENT_ORDER: list[str] = ["US10Y", "US2Y", "DXY", "Oil", "SPY", "QQQ", "VIX"]

INSTRUMENT_CONFIG: dict[str, dict[str, str]] = {
    "US10Y": {"ticker": "^TNX", "macro_significance": "Growth/Rates"},
    "US2Y": {"ticker": "^IRX", "macro_significance": "Fed Expectations"},
    "DXY": {"ticker": "DX-Y.NYB", "macro_significance": "Global Liquidity"},
    "Oil": {"ticker": "CL=F", "macro_significance": "Fear/Real yields"},
    "SPY": {"ticker": "SPY", "macro_significance": "Risk Appetite"},
    "QQQ": {"ticker": "QQQ", "macro_significance": "Growth/Liquidity"},
    "VIX": {"ticker": "^VIX", "macro_significance": "Fear"},
}

# Typical daily standard deviation (%) for each instrument.
# Used to normalize moves so "dominant variable" reflects significance
# relative to each instrument's own normal volatility, not raw %.
# Approximate values: annualized vol / sqrt(252)
TYPICAL_DAILY_VOL: dict[str, float] = {
    "US10Y": 0.8,   # ~12% annualized vol on yield changes
    "US2Y": 0.5,    # Lower vol, short-end more anchored
    "DXY": 0.4,     # ~6% annualized
    "Oil": 2.0,     # ~30% annualized
    "SPY": 1.0,     # ~16% annualized
    "QQQ": 1.3,     # ~20% annualized
    "VIX": 4.0,     # ~60% annualized (VIX is very volatile)
}


# --- Dataclasses ---


@dataclass
class InstrumentData:
    """Processed instrument data ready for display."""

    ticker: str
    macro_significance: str
    daily_change_pct: float | None = None
    weekly_change_pct: float | None = None
    data_available: bool = True
    actual_date: str | None = None  # The actual date the daily data is from


@dataclass
class DominantVariable:
    """The identified dominant market variable."""

    ticker: str
    macro_significance: str
    daily_change_pct: float
    commentary: str


# --- Pure Calculation Functions ---


def compute_daily_change(open_price: float, close_price: float) -> float:
    """Compute daily percentage change.

    Formula: ((close - open) / open) * 100, rounded to 2 decimal places.

    Args:
        open_price: Opening price (must be > 0).
        close_price: Closing price.

    Returns:
        Percentage change rounded to 2 decimal places.
    """
    return round(((close_price - open_price) / open_price) * 100, 2)


def compute_weekly_change(monday_open: float, friday_close: float) -> float:
    """Compute weekly percentage change.

    Formula: ((friday_close - monday_open) / monday_open) * 100, rounded to 2 decimal places.

    Args:
        monday_open: Monday opening price (must be > 0).
        friday_close: Friday closing price.

    Returns:
        Percentage change rounded to 2 decimal places.
    """
    return round(((friday_close - monday_open) / monday_open) * 100, 2)


def get_color_for_change(value: float | None) -> str:
    """Determine color for a percentage change value.

    Args:
        value: Percentage change value. None means data unavailable.

    Returns:
        "green" for positive, "red" for negative, "default" for zero or None.
    """
    if value is None:
        return "default"
    if value > 0:
        return "green"
    if value < 0:
        return "red"
    return "default"


def identify_dominant_variable(
    instruments: list[InstrumentData], use_weekly: bool = False
) -> DominantVariable | None:
    """Identify the instrument with the largest volatility-adjusted move.

    Normalizes each instrument's change by its typical daily volatility
    to produce a z-score. The instrument with the highest absolute z-score
    is the dominant variable.

    Args:
        instruments: List of InstrumentData with computed changes.
        use_weekly: If True, use weekly_change_pct. If False, use daily (with weekly fallback).

    Returns:
        DominantVariable identifying the dominant market factor, or None if
        no instruments have any change data.
    """
    if use_weekly:
        valid = [i for i in instruments if i.weekly_change_pct is not None]
        fallback_to_weekly = True
    else:
        # Try daily first, fall back to weekly
        valid = [i for i in instruments if i.daily_change_pct is not None]
        fallback_to_weekly = False
        if not valid:
            valid = [i for i in instruments if i.weekly_change_pct is not None]
            fallback_to_weekly = True

    if not valid:
        return None

    # Compute z-score for each instrument (normalized by typical vol)
    def sort_key(inst: InstrumentData) -> tuple[float, int]:
        change = inst.weekly_change_pct if fallback_to_weekly or use_weekly else inst.daily_change_pct
        typical_vol = TYPICAL_DAILY_VOL.get(inst.ticker, 1.0)
        if fallback_to_weekly or use_weekly:
            typical_vol *= 2.2  # ~sqrt(5) for weekly vs daily
        z_score = abs(change) / typical_vol  # type: ignore[operator]
        try:
            order_idx = INSTRUMENT_ORDER.index(inst.ticker)
        except ValueError:
            order_idx = len(INSTRUMENT_ORDER)
        return (-z_score, order_idx)

    valid.sort(key=sort_key)
    dominant = valid[0]

    is_weekly = fallback_to_weekly or use_weekly
    change = dominant.weekly_change_pct if is_weekly else dominant.daily_change_pct
    typical_vol = TYPICAL_DAILY_VOL.get(dominant.ticker, 1.0)
    if is_weekly:
        typical_vol *= 2.2
    z_score = abs(change) / typical_vol  # type: ignore[operator]
    direction = "up" if change > 0 else "down"  # type: ignore[operator]
    period = "this week" if is_weekly else "today"

    commentary = (
        f"The dominant variable {period} is {dominant.macro_significance} "
        f"({dominant.ticker}), moving {direction} {abs(change):.2f}% "  # type: ignore[arg-type]
        f"({z_score:.1f}σ relative to normal). "
        f"This suggests {dominant.macro_significance.lower()} is the primary "
        f"driver of market sentiment {period}."
    )

    return DominantVariable(
        ticker=dominant.ticker,
        macro_significance=dominant.macro_significance,
        daily_change_pct=change,  # type: ignore[arg-type]
        commentary=commentary,
    )
