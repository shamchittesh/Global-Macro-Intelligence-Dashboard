"""Market day resolution for the Global Macro Intelligence Dashboard.

Determines the latest completed US trading day from the user's
Mauritius timezone (UTC+4), accounting for weekends and US market holidays.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Timezones
USER_TZ = ZoneInfo("Indian/Mauritius")  # UTC+4
US_EASTERN = ZoneInfo("America/New_York")

# NYSE observed holidays for 2024-2026
# Source: https://www.nyse.com/markets/hours-calendars
US_MARKET_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 1),   # New Year's Day
    date(2024, 1, 15),  # MLK Jr. Day
    date(2024, 2, 19),  # Presidents' Day
    date(2024, 3, 29),  # Good Friday
    date(2024, 5, 27),  # Memorial Day
    date(2024, 6, 19),  # Juneteenth
    date(2024, 7, 4),   # Independence Day
    date(2024, 9, 2),   # Labor Day
    date(2024, 11, 28), # Thanksgiving
    date(2024, 12, 25), # Christmas
    # 2025
    date(2025, 1, 1),   # New Year's Day
    date(2025, 1, 20),  # MLK Jr. Day
    date(2025, 2, 17),  # Presidents' Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 26),  # Memorial Day
    date(2025, 6, 19),  # Juneteenth
    date(2025, 7, 4),   # Independence Day
    date(2025, 9, 1),   # Labor Day
    date(2025, 11, 27), # Thanksgiving
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Jr. Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}


def is_us_market_holiday(d: date) -> bool:
    """Check if a date is a US stock market holiday."""
    return d in US_MARKET_HOLIDAYS


def is_trading_day(d: date) -> bool:
    """Check if a date is a valid US trading day (weekday and not a holiday)."""
    return d.weekday() < 5 and not is_us_market_holiday(d)


def get_latest_market_day(now: datetime | None = None) -> date:
    """Determine the most recent completed US market day.

    Converts current UTC+4 time to US Eastern, checks if market
    has closed (16:00 ET), accounts for weekends and US holidays.

    Args:
        now: Override for current time (for testing). If None, uses real clock.

    Returns:
        The date of the latest completed trading day.
    """
    if now is None:
        now = datetime.now(USER_TZ)

    # Convert to US Eastern Time
    now_et = now.astimezone(US_EASTERN)
    today_et = now_et.date()

    # Market closes at 16:00 ET
    market_close_hour = 16

    # If today is a trading day and market has closed, today is valid
    if is_trading_day(today_et) and now_et.hour >= market_close_hour:
        return today_et

    # Otherwise walk backwards to find the most recent completed trading day
    candidate = today_et - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)

    return candidate


def get_current_trading_week(reference_date: date | None = None) -> tuple[date, date]:
    """Get the Monday-Friday bounds of the most recently completed trading week.

    Adjusts for holidays: uses first trading day as 'Monday open'
    and last trading day as 'Friday close'.

    Args:
        reference_date: The reference date to determine the week from.
                       If None, uses get_latest_market_day().

    Returns:
        (week_start, week_end) - dates for open/close price lookup.
    """
    if reference_date is None:
        reference_date = get_latest_market_day()

    # Find the Monday of the current week
    days_since_monday = reference_date.weekday()  # Monday=0, Sunday=6
    current_monday = reference_date - timedelta(days=days_since_monday)
    current_friday = current_monday + timedelta(days=4)

    # If we haven't completed this week's Friday yet, use last week
    if reference_date < current_friday:
        # Use previous week
        current_monday -= timedelta(days=7)
        current_friday -= timedelta(days=7)

    # Adjust week_start to first trading day if Monday is a holiday
    week_start = current_monday
    while not is_trading_day(week_start) and week_start <= current_friday:
        week_start += timedelta(days=1)

    # Adjust week_end to last trading day if Friday is a holiday
    week_end = current_friday
    while not is_trading_day(week_end) and week_end >= current_monday:
        week_end -= timedelta(days=1)

    return week_start, week_end
