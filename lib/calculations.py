"""Pure calculation functions for the Global Macro Intelligence Dashboard.

Provides correlation analysis, price normalization, dominant variable identification,
and surprise magnitude computation. All functions are pure with no side effects.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from lib.models import CorrelationShift, DominantFactor


def compute_correlation_matrix(
    price_data: dict[str, pd.Series],
    window: int,
) -> pd.DataFrame:
    """Compute rolling correlation matrix between assets.

    Args:
        price_data: Dict mapping asset name to price series (returns-based).
        window: Rolling window in trading days.

    Returns:
        DataFrame with correlation values between all asset pairs.
        The matrix is symmetric with diagonal = 1.0 and off-diagonal in [-1, 1].
        Pairs with insufficient data will have NaN values.
    """
    if not price_data or len(price_data) < 2:
        return pd.DataFrame()

    # Build a DataFrame from the return series, aligning on index
    df = pd.DataFrame(price_data)

    # Use only the last `window` observations for the correlation calculation
    df_window = df.tail(window)

    # Need at least 2 data points to compute correlation
    if len(df_window) < 2:
        asset_names = list(price_data.keys())
        return pd.DataFrame(
            np.nan, index=asset_names, columns=asset_names
        )

    corr_matrix = df_window.corr()

    return corr_matrix


def normalize_prices(
    price_series: dict[str, pd.Series],
    base_date: datetime,
) -> dict[str, pd.Series]:
    """Normalize multiple price series to 100 at base_date for overlay comparison.

    Args:
        price_series: Dict mapping asset name to price series.
        base_date: The date at which all series should equal 100.0.

    Returns:
        Dict mapping asset name to normalized price series.
        All series will have value 100.0 at base_date.
        Ratios between any two points in a normalized series equal
        the ratios in the original series.
    """
    result: dict[str, pd.Series] = {}

    for name, series in price_series.items():
        if series.empty:
            result[name] = series.copy()
            continue

        # Find the base value - handle both datetime and date index types
        base_value = None
        if base_date in series.index:
            base_value = series[base_date]
        else:
            # Try matching just the date portion if index is datetime-like
            try:
                # Normalize to date for comparison
                base_date_normalized = pd.Timestamp(base_date).normalize()
                idx_normalized = pd.DatetimeIndex(series.index).normalize()
                mask = idx_normalized == base_date_normalized
                if mask.any():
                    base_value = series.iloc[mask.argmax()]
            except (TypeError, ValueError):
                pass

        if base_value is None or base_value == 0:
            # Cannot normalize if base_date not found or base value is zero
            result[name] = series.copy()
            continue

        # Normalize: value_normalized = (value / base_value) * 100
        result[name] = (series / base_value) * 100.0

    return result


def compute_correlation_changes(
    current_corr: pd.DataFrame,
    prior_corr: pd.DataFrame,
    threshold: float = 0.3,
) -> list[CorrelationShift]:
    """Detect significant correlation shifts.

    Args:
        current_corr: Current correlation matrix.
        prior_corr: Prior correlation matrix.
        threshold: Minimum absolute change to flag (default 0.3).

    Returns:
        List of CorrelationShift for asset pairs where |change| > threshold.
        Excludes pairs where |change| <= threshold.
    """
    shifts: list[CorrelationShift] = []

    if current_corr.empty or prior_corr.empty:
        return shifts

    # Get common assets between both matrices
    common_assets = sorted(
        set(current_corr.columns) & set(prior_corr.columns)
    )

    # Check each unique pair (upper triangle only to avoid duplicates)
    for i, asset_a in enumerate(common_assets):
        for asset_b in common_assets[i + 1:]:
            current_val = current_corr.loc[asset_a, asset_b]
            prior_val = prior_corr.loc[asset_a, asset_b]

            # Skip if either value is NaN
            if pd.isna(current_val) or pd.isna(prior_val):
                continue

            change = current_val - prior_val

            if abs(change) > threshold:
                shifts.append(
                    CorrelationShift(
                        asset_a=asset_a,
                        asset_b=asset_b,
                        previous_corr=float(prior_val),
                        current_corr=float(current_val),
                        change=float(change),
                    )
                )

    return shifts


def identify_dominant_variable(
    asset_returns: dict[str, float],
    correlations: pd.DataFrame,
) -> list[DominantFactor]:
    """Identify top contributing factors for current session.

    Uses magnitude of moves weighted by cross-asset correlation strength
    to rank which variable is driving markets.

    Args:
        asset_returns: Dict mapping asset name to current session return (%).
        correlations: Correlation matrix between assets.

    Returns:
        List of DominantFactor sorted by influence score (descending), top 3.
        All scores are non-negative.
    """
    if not asset_returns:
        return []

    factors: list[DominantFactor] = []

    for asset, ret in asset_returns.items():
        # Base influence is the absolute magnitude of the move
        magnitude = abs(ret)

        # Weight by average absolute correlation with other assets
        # Higher correlation with other movers = more likely to be the driver
        corr_weight = 1.0
        if not correlations.empty and asset in correlations.columns:
            # Get correlations of this asset with all others
            asset_corrs = correlations.loc[asset].drop(asset, errors="ignore")
            if not asset_corrs.empty:
                # Use mean absolute correlation as a weight
                valid_corrs = asset_corrs.dropna()
                if not valid_corrs.empty:
                    corr_weight = valid_corrs.abs().mean()

        # Influence score = magnitude * correlation weight
        # This rewards assets that moved significantly AND are highly
        # correlated with other assets (suggesting they are driving)
        influence_score = magnitude * corr_weight

        # Ensure non-negative (should always be, but be explicit)
        influence_score = max(0.0, influence_score)

        factors.append(
            DominantFactor(
                variable=asset,
                influence_score=float(influence_score),
                description=f"{asset}: {ret:+.2f}% move, corr weight {corr_weight:.2f}",
            )
        )

    # Sort descending by influence score
    factors.sort(key=lambda f: f.influence_score, reverse=True)

    # Return top 3
    return factors[:3]


def compute_surprise_magnitude(
    actual: float,
    expected: float,
    historical_std: float,
) -> float | None:
    """Calculate normalized surprise magnitude.

    Args:
        actual: The actual reported value.
        expected: The consensus expected value.
        historical_std: Historical standard deviation of surprises.

    Returns:
        (actual - expected) / historical_std when historical_std > 0.
        None when historical_std <= 0.
    """
    if historical_std <= 0:
        return None

    return (actual - expected) / historical_std


def compute_asset_reaction(
    price_series: pd.Series,
    release_timestamp: datetime,
    windows: list[str],
) -> dict[str, float]:
    """Compute price reaction as percentage change from release price at each window endpoint.

    Args:
        price_series: Time-indexed price series for an asset.
        release_timestamp: The timestamp of the economic data release.
        windows: List of window labels (e.g., ["5min", "1hr", "1day"]).
            Supported formats: Xmin, Xhr, Xday (where X is an integer).

    Returns:
        Dict mapping window label to percentage change:
        reaction = (price_at_window_end - price_at_release) / price_at_release * 100
        Windows where the endpoint price is unavailable will be omitted.
    """
    if price_series.empty:
        return {}

    # Find the release price - use the value at or just before the release timestamp
    release_price = None
    if release_timestamp in price_series.index:
        release_price = price_series[release_timestamp]
    else:
        # Find the nearest price at or before the release timestamp
        prior = price_series[price_series.index <= release_timestamp]
        if not prior.empty:
            release_price = prior.iloc[-1]

    if release_price is None or release_price == 0:
        return {}

    # Parse window strings into timedeltas
    window_deltas = _parse_windows(windows)

    reactions: dict[str, float] = {}
    for window_label, delta in window_deltas.items():
        target_time = release_timestamp + delta

        # Find the price at or just before the target time
        available = price_series[price_series.index <= target_time]
        if available.empty:
            continue

        end_price = available.iloc[-1]
        reaction = (end_price - release_price) / release_price * 100.0
        reactions[window_label] = float(reaction)

    return reactions


def _parse_windows(windows: list[str]) -> dict[str, pd.Timedelta]:
    """Parse window label strings into timedelta objects.

    Supported formats:
        - Xmin (e.g., "5min" -> 5 minutes)
        - Xhr (e.g., "1hr" -> 1 hour)
        - Xday (e.g., "1day" -> 1 day)

    Returns:
        Dict mapping original window label to pd.Timedelta.
        Invalid formats are skipped.
    """
    import re

    result: dict[str, pd.Timedelta] = {}

    for w in windows:
        match = re.match(r"^(\d+)(min|hr|day)$", w)
        if not match:
            continue

        value = int(match.group(1))
        unit = match.group(2)

        if unit == "min":
            result[w] = pd.Timedelta(minutes=value)
        elif unit == "hr":
            result[w] = pd.Timedelta(hours=value)
        elif unit == "day":
            result[w] = pd.Timedelta(days=value)

    return result
