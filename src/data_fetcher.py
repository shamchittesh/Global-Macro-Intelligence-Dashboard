"""Simplified data fetcher for the Global Macro Intelligence Dashboard.

Fetches OHLCV data from yfinance for exactly 7 macro instruments.
Uses yf.download() to batch all tickers in a SINGLE API call,
avoiding rate limits entirely.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from src.cache import read_cache, write_cache
from src.calculations import (
    INSTRUMENT_CONFIG,
    INSTRUMENT_ORDER,
    InstrumentData,
    compute_daily_change,
    compute_weekly_change,
)
from src.market_day import get_current_trading_week, get_latest_market_day

logger = logging.getLogger(__name__)


def _process_instrument(
    name: str,
    config: dict,
    hist: pd.DataFrame,
    market_day: date,
    week_start: date,
    week_end: date,
) -> InstrumentData:
    """Process downloaded data for a single instrument.

    Args:
        name: Instrument display name (e.g., "US10Y").
        config: Dict with 'ticker' and 'macro_significance'.
        hist: DataFrame with OHLCV data for this ticker (DatetimeIndex).
        market_day: The resolved latest market day for daily change.
        week_start: First trading day of the week for weekly open.
        week_end: Last trading day of the week for weekly close.

    Returns:
        InstrumentData with computed changes, or with data_available=False on failure.
    """
    significance = config["macro_significance"]

    if hist is None or hist.empty:
        return InstrumentData(
            ticker=name,
            macro_significance=significance,
            data_available=False,
        )

    try:
        # Normalize columns to lowercase
        hist.columns = [c.lower() for c in hist.columns]

        # Build date -> row lookup
        date_index: dict[date, pd.Series] = {}
        for idx, row in hist.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            date_index[d] = row

        # Daily change: open and close for market_day
        # If exact market_day not available, use the most recent date in data
        daily_change = None
        daily_date = market_day
        if daily_date not in date_index and date_index:
            # Fallback to most recent available date
            available_dates = sorted(date_index.keys())
            # Find the latest date that's <= market_day
            candidates = [d for d in available_dates if d <= market_day]
            if candidates:
                daily_date = candidates[-1]

        if daily_date in date_index:
            row = date_index[daily_date]
            open_price = float(row["open"])
            close_price = float(row["close"])
            # Check for NaN (market still open / incomplete data)
            if (open_price > 0 and close_price > 0
                    and not pd.isna(open_price) and not pd.isna(close_price)):
                daily_change = compute_daily_change(open_price, close_price)

        # Weekly change: week_start open to week_end close
        weekly_change = None
        if week_start in date_index and week_end in date_index:
            monday_open = float(date_index[week_start]["open"])
            friday_close = float(date_index[week_end]["close"])
            if (monday_open > 0 and friday_close > 0
                    and not pd.isna(monday_open) and not pd.isna(friday_close)):
                weekly_change = compute_weekly_change(monday_open, friday_close)

        return InstrumentData(
            ticker=name,
            macro_significance=significance,
            daily_change_pct=daily_change,
            weekly_change_pct=weekly_change,
            data_available=(daily_change is not None or weekly_change is not None),
            actual_date=daily_date.isoformat() if daily_change is not None else None,
        )

    except Exception as e:
        logger.warning(f"Failed to process data for {name}: {e}")
        return InstrumentData(
            ticker=name,
            macro_significance=significance,
            data_available=False,
        )


def fetch_all_instruments(
    market_day: date | None = None,
    week_start: date | None = None,
    week_end: date | None = None,
) -> list[InstrumentData]:
    """Fetch price data for all 7 instruments in a single batch API call.

    Uses yf.download() to fetch all tickers at once, avoiding rate limits.
    Results are cached per calendar day.

    Args:
        market_day: Override latest market day (for testing).
        week_start: Override week start (for testing).
        week_end: Override week end (for testing).

    Returns:
        List of InstrumentData for all 7 instruments in INSTRUMENT_ORDER.
    """
    if market_day is None:
        market_day = get_latest_market_day()
    if week_start is None or week_end is None:
        week_start, week_end = get_current_trading_week(market_day)

    # Check cache first
    cache_key = f"instruments_{market_day.isoformat()}"
    cached = read_cache(cache_key)
    if cached is not None:
        # Reconstruct InstrumentData from cached dict
        instruments = []
        for name in INSTRUMENT_ORDER:
            if name in cached:
                d = cached[name]
                instruments.append(InstrumentData(
                    ticker=d["ticker"],
                    macro_significance=d["macro_significance"],
                    daily_change_pct=d.get("daily_change_pct"),
                    weekly_change_pct=d.get("weekly_change_pct"),
                    data_available=d.get("data_available", True),
                    actual_date=d.get("actual_date"),
                ))
            else:
                config = INSTRUMENT_CONFIG[name]
                instruments.append(InstrumentData(
                    ticker=name,
                    macro_significance=config["macro_significance"],
                    data_available=False,
                ))
        return instruments

    # Build ticker list for batch download
    ticker_list = [INSTRUMENT_CONFIG[name]["ticker"] for name in INSTRUMENT_ORDER]

    # Single API call for all 7 tickers
    fetch_start = week_start - timedelta(days=3)
    fetch_end = market_day + timedelta(days=2)  # +2 to ensure end date is inclusive

    try:
        data = yf.download(
            tickers=ticker_list,
            start=fetch_start,
            end=fetch_end,
            interval="1d",
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning(f"Batch download failed: {e}")
        # Return all unavailable
        return [
            InstrumentData(
                ticker=name,
                macro_significance=INSTRUMENT_CONFIG[name]["macro_significance"],
                data_available=False,
            )
            for name in INSTRUMENT_ORDER
        ]

    # Process each instrument from the batch result
    instruments = []
    for name in INSTRUMENT_ORDER:
        config = INSTRUMENT_CONFIG[name]
        ticker_symbol = config["ticker"]

        try:
            # yf.download returns multi-level columns: (Price, Ticker)
            # Use .xs() to extract a single ticker's data
            if data.columns.nlevels == 2:
                ticker_data = data.xs(ticker_symbol, level="Ticker", axis=1).copy()
            else:
                # Single ticker or flat columns
                ticker_data = data.copy()

            # Drop rows where all values are NaN
            ticker_data = ticker_data.dropna(how="all")

        except (KeyError, Exception) as e:
            logger.warning(f"No data for {name} ({ticker_symbol}): {e}")
            ticker_data = pd.DataFrame()

        instrument = _process_instrument(
            name, config, ticker_data, market_day, week_start, week_end
        )
        instruments.append(instrument)

    # Cache the results — only if ALL instruments have daily data
    # AND the data is from the expected market day (not stale from yfinance lag)
    all_daily_available = all(
        inst.daily_change_pct is not None
        for inst in instruments
        if inst.data_available
    )
    has_data = any(inst.data_available for inst in instruments)
    # Check if actual data matches requested market day
    actual_dates = [i.actual_date for i in instruments if i.actual_date]
    data_is_current = any(d == market_day.isoformat() for d in actual_dates)

    if has_data and all_daily_available and data_is_current:
        cache_data = {}
        for inst in instruments:
            cache_data[inst.ticker] = {
                "ticker": inst.ticker,
                "macro_significance": inst.macro_significance,
                "daily_change_pct": inst.daily_change_pct,
                "weekly_change_pct": inst.weekly_change_pct,
                "data_available": inst.data_available,
                "actual_date": inst.actual_date,
            }
        write_cache(cache_key, cache_data)

    return instruments
