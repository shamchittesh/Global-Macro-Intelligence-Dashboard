"""Data fetching module for the Global Macro Intelligence Dashboard.

Provides a unified interface for fetching market data from multiple sources:
- yfinance: equities, commodities, crypto, FX
- FRED (fredapi): Treasury yields and macro indicators
- Twelve Data: intraday fills and FX when yfinance doesn't support the interval

Includes caching via @st.cache_data, interval resampling for unsupported intervals,
and error handling with fallback between sources.
"""

from datetime import date, datetime, timedelta
import logging

import pandas as pd
import streamlit as st

from lib.models import (
    AssetPrice,
    AssetSource,
    EconomicEvent,
    INTERVALS,
    DEFAULT_ASSETS,
    TrackedAsset,
)

logger = logging.getLogger(__name__)


# --- Resampling Configuration ---

# Maps unsupported intervals to (base_interval, pandas_resample_rule)
# base_interval: the finest natively-supported interval to fetch
# resample_rule: the pandas offset alias to resample to
RESAMPLE_MAP: dict[str, tuple[str, str]] = {
    "6hour": ("1hour", "6h"),
    "12hour": ("1hour", "12h"),
    "2month": ("1month", "2ME"),
    "6month": ("1month", "6ME"),
    "1year": ("1month", "12ME"),
}


class DataFetchError(Exception):
    """Raised when data fetching fails after all retries and fallbacks."""

    pass


class InvalidSymbolError(DataFetchError):
    """Raised when a symbol is not recognized by any data source."""

    pass


class RateLimitError(DataFetchError):
    """Raised when a data source rate limit is exceeded."""

    pass


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV DataFrame to a coarser interval.

    Args:
        df: DataFrame with DatetimeIndex and columns: open, high, low, close, volume
        rule: Pandas offset alias for the target interval (e.g., '6h', '2ME')

    Returns:
        Resampled DataFrame preserving OHLCV semantics:
        - open: first open in group
        - high: max high in group
        - low: min low in group
        - close: last close in group
        - volume: sum of volumes in group
    """
    if df.empty:
        return df

    resampled = df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    # Drop rows where all OHLC values are NaN (incomplete periods at edges)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"], how="all")
    return resampled


def _resolve_interval(interval: str, source: AssetSource) -> tuple[str | None, str | None]:
    """Resolve a requested interval to the native source interval and resample rule.

    Returns:
        (native_interval, resample_rule) - if resample_rule is None, no resampling needed.
        native_interval is None if the source doesn't support the interval at all.
    """
    if interval in RESAMPLE_MAP:
        base_interval, resample_rule = RESAMPLE_MAP[interval]
        base_config = INTERVALS.get(base_interval, {})
        source_key = "yfinance" if source == AssetSource.YFINANCE else "twelve_data"
        native = base_config.get(source_key)
        return native, resample_rule

    config = INTERVALS.get(interval, {})
    source_key = "yfinance" if source == AssetSource.YFINANCE else "twelve_data"
    native = config.get(source_key)
    return native, None


class DataFetcher:
    """Unified interface for fetching market data from multiple sources."""

    def __init__(self):
        """Initialize the DataFetcher.

        API keys are read from Streamlit secrets when needed.
        """
        self._asset_lookup: dict[str, TrackedAsset] = {
            asset.symbol: asset for asset in DEFAULT_ASSETS
        }

    def _get_fred_client(self):
        """Lazily initialize FRED client."""
        from fredapi import Fred

        try:
            api_key = st.secrets["fred"]["api_key"]
        except (KeyError, TypeError):
            api_key = st.secrets.get("FRED_API_KEY", "")
        if not api_key:
            raise DataFetchError("FRED API key not configured in secrets.")
        return Fred(api_key=api_key)

    def _get_twelve_data_client(self):
        """Lazily initialize Twelve Data client."""
        from twelvedata import TDClient

        try:
            api_key = st.secrets["twelve_data"]["api_key"]
        except (KeyError, TypeError):
            api_key = st.secrets.get("TWELVE_DATA_API_KEY", "")
        if not api_key:
            raise DataFetchError("Twelve Data API key not configured in secrets.")
        return TDClient(apikey=api_key)

    def get_asset_data(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
        source: AssetSource | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data for a given asset.

        Routes to the appropriate data source based on the asset's configured source.
        Handles interval resampling for intervals not natively supported.

        Args:
            symbol: The ticker symbol (e.g., "^GSPC", "DGS10", "BTC-USD")
            interval: Interval key from INTERVALS config (e.g., "1day", "6hour")
            start_date: Start of the data range
            end_date: End of the data range
            source: Override the default source for this symbol

        Returns:
            DataFrame with DatetimeIndex and columns: open, high, low, close, volume

        Raises:
            InvalidSymbolError: If the symbol is not recognized
            DataFetchError: If fetching fails after retries/fallbacks
        """
        if source is None:
            asset = self._asset_lookup.get(symbol)
            if asset:
                source = asset.source
            else:
                # Default to yfinance for unknown symbols
                source = AssetSource.YFINANCE

        # Route to appropriate fetcher
        if source == AssetSource.FRED:
            asset = self._asset_lookup.get(symbol)
            series_id = asset.fred_series_id if asset else symbol
            return self._fetch_fred_as_ohlcv(series_id, start_date, end_date, interval)
        elif source == AssetSource.TWELVE_DATA:
            return self._fetch_twelve_data(symbol, interval, start_date, end_date)
        else:
            # yfinance is the default
            return self._fetch_yfinance(symbol, interval, start_date, end_date)

    def _fetch_yfinance(
        self, symbol: str, interval: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """Fetch data from yfinance with resampling support and fallback."""
        import yfinance as yf

        native_interval, resample_rule = _resolve_interval(interval, AssetSource.YFINANCE)

        # If yfinance doesn't support this interval, try Twelve Data as fallback
        if native_interval is None:
            try:
                return self._fetch_twelve_data(symbol, interval, start_date, end_date)
            except (DataFetchError, Exception) as e:
                raise DataFetchError(
                    f"Interval '{interval}' not supported by yfinance and "
                    f"Twelve Data fallback failed: {e}"
                )

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=native_interval,
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "no data" in error_msg or "not found" in error_msg:
                raise InvalidSymbolError(f"Symbol '{symbol}' not found on yfinance: {e}")
            if "rate" in error_msg or "limit" in error_msg:
                raise RateLimitError(f"yfinance rate limit hit for '{symbol}': {e}")
            raise DataFetchError(f"yfinance fetch failed for '{symbol}': {e}")

        if df.empty:
            raise InvalidSymbolError(
                f"No data returned from yfinance for symbol '{symbol}' "
                f"in range {start_date} to {end_date}"
            )

        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]

        # Ensure required columns exist
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                raise DataFetchError(
                    f"Missing expected column '{col}' in yfinance response for '{symbol}'"
                )

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df[["open", "high", "low", "close", "volume"]]

        # Apply resampling if needed
        if resample_rule:
            df = _resample_ohlcv(df, resample_rule)

        return df

    def _fetch_twelve_data(
        self, symbol: str, interval: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """Fetch data from Twelve Data with resampling support."""
        native_interval, resample_rule = _resolve_interval(interval, AssetSource.TWELVE_DATA)

        if native_interval is None:
            raise DataFetchError(
                f"Interval '{interval}' not supported by Twelve Data for '{symbol}'"
            )

        try:
            td = self._get_twelve_data_client()
            ts = td.time_series(
                symbol=symbol,
                interval=native_interval,
                start_date=start_date.strftime("%Y-%m-%d %H:%M:%S"),
                end_date=end_date.strftime("%Y-%m-%d %H:%M:%S"),
                outputsize=5000,
            )
            df = ts.as_pandas()
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "invalid" in error_msg:
                raise InvalidSymbolError(
                    f"Symbol '{symbol}' not found on Twelve Data: {e}"
                )
            if "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
                raise RateLimitError(f"Twelve Data rate limit hit for '{symbol}': {e}")
            raise DataFetchError(f"Twelve Data fetch failed for '{symbol}': {e}")

        if df is None or df.empty:
            raise InvalidSymbolError(
                f"No data returned from Twelve Data for symbol '{symbol}' "
                f"in range {start_date} to {end_date}"
            )

        # Normalize column names
        df.columns = [c.lower() for c in df.columns]

        # Ensure required columns
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                raise DataFetchError(
                    f"Missing expected column '{col}' in Twelve Data response for '{symbol}'"
                )

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df[["open", "high", "low", "close", "volume"]]

        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Sort chronologically (Twelve Data returns newest first)
        df = df.sort_index()

        # Apply resampling if needed
        if resample_rule:
            df = _resample_ohlcv(df, resample_rule)

        return df

    def _fetch_fred_as_ohlcv(
        self, series_id: str, start_date: datetime, end_date: datetime, interval: str
    ) -> pd.DataFrame:
        """Fetch FRED series data and format as OHLCV-like DataFrame.

        FRED data is daily values (yields, rates), so we represent them as
        line-chart-compatible data where open=high=low=close=value, volume=0.
        """
        try:
            fred = self._get_fred_client()
            series = fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date,
            )
        except DataFetchError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "invalid" in error_msg:
                raise InvalidSymbolError(f"FRED series '{series_id}' not found: {e}")
            if "rate" in error_msg or "limit" in error_msg:
                raise RateLimitError(f"FRED rate limit hit for '{series_id}': {e}")
            raise DataFetchError(f"FRED fetch failed for '{series_id}': {e}")

        if series is None or series.empty:
            raise InvalidSymbolError(
                f"No data returned from FRED for series '{series_id}' "
                f"in range {start_date} to {end_date}"
            )

        # Drop NaN values (FRED uses '.' for missing data which becomes NaN)
        series = series.dropna()

        # Build OHLCV-like DataFrame (for yields, all OHLC = value)
        df = pd.DataFrame(
            {
                "open": series.values,
                "high": series.values,
                "low": series.values,
                "close": series.values,
                "volume": 0,
            },
            index=series.index,
        )
        df.index.name = "Date"

        # Apply resampling if interval requires it
        _, resample_rule = _resolve_interval(interval, AssetSource.FRED)
        if resample_rule:
            df = _resample_ohlcv(df, resample_rule)

        return df

    def get_yield_data(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Fetch yield/macro data from FRED.

        Args:
            series_id: FRED series identifier (e.g., "DGS10", "DGS2")
            start_date: Start of the data range
            end_date: End of the data range

        Returns:
            DataFrame with columns: date, value

        Raises:
            InvalidSymbolError: If the series ID is not found
            DataFetchError: If fetching fails
        """
        try:
            fred = self._get_fred_client()
            series = fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date,
            )
        except DataFetchError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "invalid" in error_msg:
                raise InvalidSymbolError(f"FRED series '{series_id}' not found: {e}")
            raise DataFetchError(f"FRED fetch failed for '{series_id}': {e}")

        if series is None or series.empty:
            raise InvalidSymbolError(
                f"No data returned from FRED for series '{series_id}' "
                f"in range {start_date} to {end_date}"
            )

        # Drop NaN values
        series = series.dropna()

        df = pd.DataFrame({"date": series.index, "value": series.values})
        return df

    def get_current_prices(
        self, assets: list[TrackedAsset] | None = None
    ) -> dict[str, AssetPrice]:
        """Fetch latest prices for tracked assets with change calculations.

        For each asset, fetches the most recent price and computes:
        - absolute change from previous close
        - percentage change from previous close

        Args:
            assets: List of TrackedAsset to fetch prices for.
                   Defaults to DEFAULT_ASSETS if not provided.

        Returns:
            Dict mapping symbol to AssetPrice with current price, change, pct_change.
        """
        if assets is None:
            assets = DEFAULT_ASSETS

        prices: dict[str, AssetPrice] = {}

        for asset in assets:
            try:
                price = self._fetch_current_price(asset)
                if price is not None:
                    prices[asset.symbol] = price
            except Exception as e:
                logger.warning(
                    f"Failed to fetch current price for {asset.symbol}: {e}"
                )
                continue

        return prices

    def _fetch_current_price(self, asset: TrackedAsset) -> AssetPrice | None:
        """Fetch current price for a single asset with change calculation."""
        now = datetime.now()

        if asset.source == AssetSource.FRED:
            return self._fetch_fred_current_price(asset, now)
        elif asset.source == AssetSource.TWELVE_DATA:
            return self._fetch_twelve_data_current_price(asset, now)
        else:
            return self._fetch_yfinance_current_price(asset, now)

    def _fetch_yfinance_current_price(
        self, asset: TrackedAsset, now: datetime
    ) -> AssetPrice | None:
        """Get current price from yfinance."""
        import yfinance as yf

        try:
            ticker = yf.Ticker(asset.symbol)
            hist = ticker.history(period="5d", interval="1d")

            if hist.empty:
                return None

            hist.columns = [c.lower() for c in hist.columns]
            current_price = float(hist["close"].iloc[-1])

            # Calculate change from previous close
            if len(hist) >= 2:
                prev_close = float(hist["close"].iloc[-2])
            else:
                prev_close = current_price

            change = current_price - prev_close
            pct_change = (change / prev_close * 100) if prev_close != 0 else 0.0

            return AssetPrice(
                symbol=asset.symbol,
                price=current_price,
                change=change,
                pct_change=pct_change,
                timestamp=now,
            )
        except Exception as e:
            logger.warning(f"yfinance current price failed for {asset.symbol}: {e}")
            return None

    def _fetch_fred_current_price(
        self, asset: TrackedAsset, now: datetime
    ) -> AssetPrice | None:
        """Get current value from FRED."""
        try:
            fred = self._get_fred_client()
            series_id = asset.fred_series_id or asset.symbol
            # Fetch last 10 days to ensure we get at least 2 data points
            start = now - timedelta(days=10)
            series = fred.get_series(series_id, observation_start=start)

            if series is None or series.empty:
                return None

            series = series.dropna()
            if series.empty:
                return None

            current_value = float(series.iloc[-1])

            if len(series) >= 2:
                prev_value = float(series.iloc[-2])
            else:
                prev_value = current_value

            change = current_value - prev_value
            pct_change = (change / prev_value * 100) if prev_value != 0 else 0.0

            return AssetPrice(
                symbol=asset.symbol,
                price=current_value,
                change=change,
                pct_change=pct_change,
                timestamp=now,
            )
        except Exception as e:
            logger.warning(f"FRED current price failed for {asset.symbol}: {e}")
            return None

    def _fetch_twelve_data_current_price(
        self, asset: TrackedAsset, now: datetime
    ) -> AssetPrice | None:
        """Get current price from Twelve Data."""
        try:
            td = self._get_twelve_data_client()
            ts = td.time_series(
                symbol=asset.symbol,
                interval="1day",
                outputsize=5,
            )
            df = ts.as_pandas()

            if df is None or df.empty:
                return None

            df.columns = [c.lower() for c in df.columns]
            # Twelve Data returns newest first
            df = df.sort_index()

            current_price = float(df["close"].iloc[-1])

            if len(df) >= 2:
                prev_close = float(df["close"].iloc[-2])
            else:
                prev_close = current_price

            change = current_price - prev_close
            pct_change = (change / prev_close * 100) if prev_close != 0 else 0.0

            return AssetPrice(
                symbol=asset.symbol,
                price=current_price,
                change=change,
                pct_change=pct_change,
                timestamp=now,
            )
        except Exception as e:
            logger.warning(
                f"Twelve Data current price failed for {asset.symbol}: {e}"
            )
            return None

    def get_economic_calendar(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[EconomicEvent]:
        """Fetch upcoming/past economic releases.

        This is a stub implementation that returns a curated list of
        major economic events. A full implementation would integrate with
        an economic calendar API.

        Args:
            start_date: Start of the date range
            end_date: End of the date range

        Returns:
            List of EconomicEvent objects for the date range
        """
        # Stub: return an empty list. In production, this would integrate
        # with an economic calendar API (e.g., Trading Economics, Investing.com)
        # or pull from a pre-populated database table.
        return []


# --- Cached wrapper functions ---
# These are module-level functions decorated with @st.cache_data
# to enable Streamlit's caching mechanism. They delegate to DataFetcher methods.


@st.cache_data(ttl=timedelta(minutes=5), show_spinner="Fetching asset data...")
def fetch_asset_data_cached(
    symbol: str,
    interval: str,
    start_date: datetime,
    end_date: datetime,
    source_value: str | None = None,
) -> pd.DataFrame:
    """Cached wrapper for DataFetcher.get_asset_data().

    TTL: 5 minutes for historical data (balance freshness vs API limits).
    """
    fetcher = DataFetcher()
    source = AssetSource(source_value) if source_value else None
    return fetcher.get_asset_data(symbol, interval, start_date, end_date, source=source)


@st.cache_data(ttl=timedelta(minutes=1), show_spinner="Fetching current prices...")
def fetch_current_prices_cached(
    symbols: tuple[str, ...] | None = None,
) -> dict[str, AssetPrice]:
    """Cached wrapper for DataFetcher.get_current_prices().

    TTL: 1 minute for real-time price snapshots.
    """
    fetcher = DataFetcher()
    if symbols:
        assets = [
            asset for asset in DEFAULT_ASSETS if asset.symbol in symbols
        ]
    else:
        assets = None
    return fetcher.get_current_prices(assets)


@st.cache_data(ttl=timedelta(hours=1), show_spinner="Fetching yield data...")
def fetch_yield_data_cached(
    series_id: str,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame:
    """Cached wrapper for DataFetcher.get_yield_data().

    TTL: 1 hour for FRED yield data (updates daily).
    """
    fetcher = DataFetcher()
    return fetcher.get_yield_data(series_id, start_date, end_date)


@st.cache_data(ttl=timedelta(hours=6), show_spinner="Fetching economic calendar...")
def fetch_economic_calendar_cached(
    start_date: datetime,
    end_date: datetime,
) -> list[EconomicEvent]:
    """Cached wrapper for DataFetcher.get_economic_calendar().

    TTL: 6 hours for economic calendar (events don't change frequently).
    """
    fetcher = DataFetcher()
    return fetcher.get_economic_calendar(start_date, end_date)
