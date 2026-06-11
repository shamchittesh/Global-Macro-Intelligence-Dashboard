"""Unit tests for market day resolution logic."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from lib.market_day import (
    US_EASTERN,
    USER_TZ,
    get_current_trading_week,
    get_latest_market_day,
    is_trading_day,
    is_us_market_holiday,
)


class TestIsUSMarketHoliday:
    """Tests for is_us_market_holiday()."""

    def test_christmas_2025_is_holiday(self):
        assert is_us_market_holiday(date(2025, 12, 25)) is True

    def test_regular_tuesday_is_not_holiday(self):
        assert is_us_market_holiday(date(2025, 3, 4)) is False

    def test_mlk_day_2025_is_holiday(self):
        assert is_us_market_holiday(date(2025, 1, 20)) is True


class TestIsTradingDay:
    """Tests for is_trading_day()."""

    def test_regular_weekday(self):
        # Tuesday March 4, 2025
        assert is_trading_day(date(2025, 3, 4)) is True

    def test_saturday(self):
        assert is_trading_day(date(2025, 3, 1)) is False

    def test_sunday(self):
        assert is_trading_day(date(2025, 3, 2)) is False

    def test_holiday_weekday(self):
        # MLK Day 2025 - Monday
        assert is_trading_day(date(2025, 1, 20)) is False


class TestGetLatestMarketDay:
    """Tests for get_latest_market_day()."""

    def test_weekday_after_close_returns_today(self):
        # Wednesday 5pm ET = market closed for today
        now = datetime(2025, 3, 5, 17, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 3, 5)

    def test_weekday_before_close_returns_previous_day(self):
        # Wednesday 2pm ET = market still open
        now = datetime(2025, 3, 5, 14, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 3, 4)

    def test_saturday_returns_friday(self):
        # Saturday March 8, 2025
        now = datetime(2025, 3, 8, 10, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 3, 7)  # Friday

    def test_sunday_returns_friday(self):
        # Sunday March 9, 2025
        now = datetime(2025, 3, 9, 10, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 3, 7)  # Friday

    def test_monday_before_close_returns_friday(self):
        # Monday 10am ET
        now = datetime(2025, 3, 10, 10, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 3, 7)  # Previous Friday

    def test_holiday_tuesday_after_close_skips_to_monday(self):
        # Juneteenth 2025 is Thursday June 19
        # After close on Thursday June 19 (holiday), should return Wednesday June 18
        now = datetime(2025, 6, 19, 17, 0, tzinfo=US_EASTERN)
        result = get_latest_market_day(now.astimezone(USER_TZ))
        assert result == date(2025, 6, 18)  # Wednesday before Juneteenth


class TestGetCurrentTradingWeek:
    """Tests for get_current_trading_week()."""

    def test_mid_week_returns_previous_complete_week(self):
        # Wednesday March 5, 2025 (mid-week, hasn't completed this week)
        result = get_current_trading_week(date(2025, 3, 5))
        # Should return previous week: Feb 24 - Feb 28
        assert result[0] == date(2025, 2, 24)  # Monday
        assert result[1] == date(2025, 2, 28)  # Friday

    def test_friday_returns_current_week(self):
        # Friday March 7, 2025
        result = get_current_trading_week(date(2025, 3, 7))
        assert result[0] == date(2025, 3, 3)  # Monday
        assert result[1] == date(2025, 3, 7)  # Friday

    def test_monday_holiday_adjusts_start(self):
        # MLK Day 2025 is Monday Jan 20
        # If reference is Friday Jan 24
        result = get_current_trading_week(date(2025, 1, 24))
        # Week is Jan 20-24, but Monday is holiday so start is Jan 21
        assert result[0] == date(2025, 1, 21)  # Tuesday
        assert result[1] == date(2025, 1, 24)  # Friday
