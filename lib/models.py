"""Data models and configuration for the Global Macro Intelligence Dashboard."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


# --- Enums ---


class AssetSource(Enum):
    """Data source for fetching asset prices."""

    YFINANCE = "yfinance"
    FRED = "fred"
    TWELVE_DATA = "twelve_data"


class ChartType(Enum):
    """Supported chart display modes."""

    CANDLESTICK = "candlestick"
    LINE = "line"


class EventCategory(Enum):
    """Categories for macro events."""

    MONETARY_POLICY = "monetary_policy"
    INFLATION_DATA = "inflation_data"
    GEOPOLITICAL = "geopolitical"
    FISCAL_POLICY = "fiscal_policy"


# --- Core Dataclasses ---


@dataclass
class TrackedAsset:
    """Configuration for a tracked asset."""

    symbol: str  # e.g., "^TNX", "DX-Y.NYB", "GC=F"
    display_name: str  # e.g., "US 10Y Yield", "DXY", "Gold"
    source: AssetSource
    fred_series_id: str | None = None  # For FRED-sourced data
    category: str = "default"  # For grouping in UI


@dataclass
class AssetPrice:
    """Current price snapshot for an asset."""

    symbol: str
    price: float
    change: float
    pct_change: float
    timestamp: datetime


@dataclass
class MacroEvent:
    """A recorded macro event."""

    id: str | None
    date: date
    description: str
    category: EventCategory
    is_custom: bool = False  # User-added vs system-provided


@dataclass
class DominantVariableRecord:
    """Daily dominant variable selection."""

    id: str | None
    date: date
    variable: str  # e.g., "rates", "USD", "oil", "liquidity"
    influence_score: float | None  # System-calculated score
    notes: str = ""  # User's reasoning
    is_manual: bool = False  # User override vs system suggestion


@dataclass
class ExpectationRecord:
    """Tracks expected vs actual for economic releases."""

    id: str | None
    release_date: date
    indicator: str  # e.g., "CPI", "NFP", "Fed Funds"
    expected_value: float
    actual_value: float | None
    surprise_magnitude: float | None  # Normalized surprise
    asset_reactions: dict | None = None  # {symbol: {5min: %, 1hr: %, 1day: %}}


@dataclass
class CustomAsset:
    """User-added custom ticker."""

    symbol: str
    display_name: str
    source: AssetSource
    added_date: date


# --- Calculation Result Dataclasses ---


@dataclass
class DominantFactor:
    """A ranked factor from dominant variable identification."""

    variable: str
    influence_score: float
    description: str


@dataclass
class CorrelationShift:
    """A detected significant correlation shift between two assets."""

    asset_a: str
    asset_b: str
    previous_corr: float
    current_corr: float
    change: float


@dataclass
class EconomicEvent:
    """An economic calendar event (upcoming or past release)."""

    date: date
    name: str
    indicator: str
    expected: float | None = None
    actual: float | None = None
    category: str = ""


# --- Default Configuration ---


DEFAULT_ASSETS: list[TrackedAsset] = [
    TrackedAsset("DGS10", "US 10Y Yield", AssetSource.FRED, fred_series_id="DGS10"),
    TrackedAsset("DGS2", "US 2Y Yield", AssetSource.FRED, fred_series_id="DGS2"),
    TrackedAsset("DX-Y.NYB", "DXY", AssetSource.YFINANCE),
    TrackedAsset("CL=F", "Oil (WTI)", AssetSource.YFINANCE),
    TrackedAsset("GC=F", "Gold", AssetSource.YFINANCE),
    TrackedAsset("^GSPC", "S&P 500", AssetSource.YFINANCE),
    TrackedAsset("^VIX", "VIX", AssetSource.YFINANCE),
    TrackedAsset("BTC-USD", "Bitcoin", AssetSource.YFINANCE),
]


INTERVALS: dict[str, dict[str, str | None]] = {
    "1min": {"yfinance": "1m", "twelve_data": "1min", "label": "1 Minute"},
    "5min": {"yfinance": "5m", "twelve_data": "5min", "label": "5 Minutes"},
    "10min": {"yfinance": None, "twelve_data": "10min", "label": "10 Minutes"},
    "15min": {"yfinance": "15m", "twelve_data": "15min", "label": "15 Minutes"},
    "30min": {"yfinance": "30m", "twelve_data": "30min", "label": "30 Minutes"},
    "1hour": {"yfinance": "1h", "twelve_data": "1h", "label": "1 Hour"},
    "6hour": {"yfinance": None, "twelve_data": None, "label": "6 Hours"},
    "12hour": {"yfinance": None, "twelve_data": None, "label": "12 Hours"},
    "1day": {"yfinance": "1d", "twelve_data": "1day", "label": "1 Day"},
    "1week": {"yfinance": "1wk", "twelve_data": "1week", "label": "1 Week"},
    "1month": {"yfinance": "1mo", "twelve_data": "1month", "label": "1 Month"},
    "2month": {"yfinance": None, "twelve_data": None, "label": "2 Months"},
    "3month": {"yfinance": "3mo", "twelve_data": None, "label": "3 Months"},
    "6month": {"yfinance": None, "twelve_data": None, "label": "6 Months"},
    "1year": {"yfinance": None, "twelve_data": None, "label": "1 Year"},
}
