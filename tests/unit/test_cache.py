"""Unit tests for the cache module."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from lib.cache import (
    CACHE_DIR,
    USER_TZ,
    invalidate_cache,
    invalidate_stale_instrument_data,
    is_cache_fresh,
    read_cache,
    write_cache,
)


@pytest.fixture(autouse=True)
def temp_cache_dir(tmp_path, monkeypatch):
    """Use a temporary directory for cache in all tests."""
    monkeypatch.setattr("lib.cache.CACHE_DIR", tmp_path)
    return tmp_path


class TestIsCacheFresh:
    """Tests for is_cache_fresh()."""

    def test_within_ttl_is_fresh(self):
        now = datetime.now(USER_TZ)
        fetched = (now - timedelta(hours=1)).isoformat()
        assert is_cache_fresh(fetched, max_age_hours=4.0) is True

    def test_expired_ttl_is_stale(self):
        now = datetime.now(USER_TZ)
        fetched = (now - timedelta(hours=5)).isoformat()
        assert is_cache_fresh(fetched, max_age_hours=4.0) is False

    def test_same_day_no_ttl_is_fresh(self):
        now = datetime.now(USER_TZ)
        fetched = now.replace(hour=1, minute=0).isoformat()
        with patch("lib.cache._now_utc4", return_value=now):
            assert is_cache_fresh(fetched, max_age_hours=None) is True

    def test_different_day_no_ttl_is_stale(self):
        now = datetime.now(USER_TZ)
        yesterday = (now - timedelta(days=1)).isoformat()
        with patch("lib.cache._now_utc4", return_value=now):
            assert is_cache_fresh(yesterday, max_age_hours=None) is False


class TestWriteAndReadCache:
    """Tests for write_cache() and read_cache()."""

    def test_write_then_read_returns_data(self, temp_cache_dir):
        data = {"instruments": {"SPY": {"daily_change_pct": 1.5}}}
        assert write_cache("test_key", data) is True

        result = read_cache("test_key", max_age_hours=1.0)
        assert result == data

    def test_read_missing_key_returns_none(self, temp_cache_dir):
        assert read_cache("nonexistent") is None

    def test_read_corrupted_file_returns_none(self, temp_cache_dir):
        # Write invalid JSON
        cache_file = temp_cache_dir / "bad_key.json"
        cache_file.write_text("not valid json{{{")

        assert read_cache("bad_key") is None
        # File should be deleted
        assert not cache_file.exists()

    def test_write_failure_returns_false(self, tmp_path, monkeypatch):
        # Point to a non-writable path
        import lib.cache
        monkeypatch.setattr(lib.cache, "CACHE_DIR", Path("/nonexistent/path"))
        assert write_cache("key", {"data": 1}) is False


class TestInvalidateCache:
    """Tests for invalidate_cache()."""

    def test_removes_existing_cache(self, temp_cache_dir):
        write_cache("to_remove", {"data": "value"})
        assert (temp_cache_dir / "to_remove.json").exists()

        invalidate_cache("to_remove")
        assert not (temp_cache_dir / "to_remove.json").exists()

    def test_nonexistent_key_no_error(self, temp_cache_dir):
        # Should not raise
        invalidate_cache("does_not_exist")


class TestInvalidateStaleInstrumentData:
    """Tests for invalidate_stale_instrument_data()."""

    def test_removes_old_instrument_files(self, temp_cache_dir):
        # Create files for different dates
        old_file = temp_cache_dir / "instruments_2024-01-10.json"
        old_file.write_text(json.dumps({"fetched_at": "2024-01-10T10:00:00+04:00", "data": {}}))

        today = datetime.now(USER_TZ).date().isoformat()
        today_file = temp_cache_dir / f"instruments_{today}.json"
        today_file.write_text(json.dumps({"fetched_at": datetime.now(USER_TZ).isoformat(), "data": {}}))

        invalidate_stale_instrument_data()

        assert not old_file.exists()
        assert today_file.exists()
