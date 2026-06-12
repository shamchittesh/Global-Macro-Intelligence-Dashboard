"""File-based JSON cache for the Global Macro Intelligence Dashboard.

Stores fetched market data and scraped reports as JSON files in .cache/,
keyed by calendar date (UTC+4) for instrument data or by TTL for reports.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".cache")
USER_TZ = ZoneInfo("Indian/Mauritius")  # UTC+4


def _ensure_cache_dir() -> bool:
    """Create .cache/ directory if it doesn't exist. Returns False on failure."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        logger.warning(f"Failed to create cache directory: {e}")
        return False


def _get_cache_path(key: str) -> Path:
    """Get the file path for a cache key."""
    return CACHE_DIR / f"{key}.json"


def _now_utc4() -> datetime:
    """Get current time in User_Timezone (UTC+4)."""
    return datetime.now(USER_TZ)


def is_cache_fresh(fetched_at_iso: str, max_age_hours: float | None = None) -> bool:
    """Check if cached data is still fresh.

    Args:
        fetched_at_iso: ISO format timestamp of when data was cached.
        max_age_hours: Maximum age in hours. None means valid for current calendar day (UTC+4).

    Returns:
        True if cache is fresh, False if stale.
    """
    now = _now_utc4()
    fetched_at = datetime.fromisoformat(fetched_at_iso)

    if max_age_hours is not None:
        # TTL-based freshness
        return (now - fetched_at) < timedelta(hours=max_age_hours)
    else:
        # Same calendar day (UTC+4)
        return fetched_at.astimezone(USER_TZ).date() == now.date()


def read_cache(key: str, max_age_hours: float | None = None) -> Any | None:
    """Read cached data if fresh. Returns None if stale or missing.

    Args:
        key: Cache key (e.g., "instruments_2024-01-15", "daily_report")
        max_age_hours: Maximum age in hours before data is stale.
                       None means valid for current calendar day (UTC+4).

    Returns:
        Cached data dict, or None if stale/missing/corrupted.
    """
    cache_path = _get_cache_path(key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            entry = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Cache file corrupted for key '{key}', removing: {e}")
        try:
            cache_path.unlink()
        except OSError:
            pass
        return None

    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return None

    if not is_cache_fresh(fetched_at, max_age_hours):
        return None

    return entry.get("data")


def write_cache(key: str, data: Any) -> bool:
    """Write data to cache. Returns False on failure (logs warning, doesn't raise).

    Args:
        key: Cache key.
        data: JSON-serializable data to cache.

    Returns:
        True on success, False on failure.
    """
    if not _ensure_cache_dir():
        return False

    cache_path = _get_cache_path(key)
    entry = {
        "fetched_at": _now_utc4().isoformat(),
        "data": data,
    }

    try:
        with open(cache_path, "w") as f:
            json.dump(entry, f, default=str)
        return True
    except (OSError, TypeError) as e:
        logger.warning(f"Failed to write cache for key '{key}': {e}")
        return False


def invalidate_cache(key: str) -> None:
    """Remove a specific cache entry."""
    cache_path = _get_cache_path(key)
    try:
        if cache_path.exists():
            cache_path.unlink()
    except OSError as e:
        logger.warning(f"Failed to invalidate cache key '{key}': {e}")


def invalidate_stale_instrument_data() -> None:
    """Remove instrument cache entries from previous calendar days (UTC+4)."""
    if not CACHE_DIR.exists():
        return

    today = _now_utc4().date()
    today_suffix = today.isoformat()

    for cache_file in CACHE_DIR.glob("instruments_*.json"):
        # Extract date from filename: instruments_YYYY-MM-DD.json
        stem = cache_file.stem  # instruments_2024-01-15
        date_part = stem.replace("instruments_", "")
        if date_part != today_suffix:
            try:
                cache_file.unlink()
                logger.info(f"Removed stale cache: {cache_file.name}")
            except OSError as e:
                logger.warning(f"Failed to remove stale cache {cache_file.name}: {e}")
