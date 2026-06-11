# Implementation Plan: Dashboard Simplification

## Overview

Replace the multi-page Streamlit dashboard with a single-page application backed by pure-function modules. Implementation proceeds bottom-up: shared utilities and data models first, then core calculation/resolution modules, cache layer, data fetcher, scraper, and finally the Streamlit UI wiring. The existing `pages/` directory is retired and `app.py` is rewritten.

## Tasks

- [x] 1. Set up project structure and core data models
  - [x] 1.1 Create `lib/market_day.py` with module skeleton and US market holiday list
    - Create the file with imports (`datetime`, `zoneinfo`)
    - Define `US_HOLIDAYS` set containing 2024-2025 NYSE holidays
    - Add `is_us_market_holiday(d: date) -> bool` function
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 1.2 Create `lib/cache.py` with cache directory setup and data models
    - Create the file with `CACHE_DIR = Path(".cache")`
    - Implement `CacheEntry` dataclass
    - Add `ensure_cache_dir()` helper that creates `.cache/` if missing
    - Define `read_cache(key, max_age_hours)` and `write_cache(key, data)` function signatures with docstrings
    - _Requirements: 7.1, 7.2_

  - [x] 1.3 Update `lib/calculations.py` with new dataclasses and instrument configuration
    - Replace existing content with `InstrumentData` and `DominantVariable` dataclasses
    - Add `INSTRUMENT_ORDER` list and `INSTRUMENT_CONFIG` dict
    - Add `get_color_for_change(value: float | None) -> str` utility function
    - _Requirements: 2.1, 2.2, 3.1-3.6_

  - [x] 1.4 Create `lib/scraper.py` module skeleton with `MarketReport` dataclass
    - Create the file with imports (`requests`, `bs4`, `dataclasses`)
    - Define `MarketReport` dataclass with `title`, `publication_date`, `body`, `fetched_at`, `available`, `error_message`
    - Define URL constants for daily and weekly report pages
    - _Requirements: 6.1, 6.2_

- [x] 2. Implement market day resolution logic
  - [x] 2.1 Implement `get_latest_market_day()` in `lib/market_day.py`
    - Convert current UTC+4 time to US Eastern Time
    - Check if current day is a weekday and not a holiday
    - Check if market has closed (16:00 ET has passed)
    - Walk backwards through calendar days until a valid completed trading day is found
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 2.2 Implement `get_current_trading_week(reference_date)` in `lib/market_day.py`
    - Find Monday of the most recently completed trading week
    - Adjust week_start to first trading day if Monday is a holiday
    - Adjust week_end to last trading day if Friday is a holiday
    - Return `(week_start, week_end)` tuple
    - _Requirements: 4.5, 4.6, 4.7_

  - [x]* 2.3 Write property test for market day resolution (Property 4)
    - **Property 4: Market day resolution returns a valid completed trading day**
    - Generate arbitrary datetimes in UTC+4, verify returned date is a weekday, not a holiday, and market close has passed
    - **Validates: Requirements 4.1**

  - [x]* 2.4 Write unit tests for market day edge cases
    - Test weekend falls back to Friday (`test_weekend_falls_back_to_friday`)
    - Test before market close uses previous day (`test_before_market_close_uses_previous_day`)
    - Test Monday holiday uses Tuesday open (`test_monday_holiday_uses_tuesday_open`)
    - Test Friday holiday uses Thursday close (`test_friday_holiday_uses_thursday_close`)
    - _Requirements: 4.2, 4.3, 4.6, 4.7_

- [x] 3. Implement calculations module
  - [x] 3.1 Implement `compute_daily_change` and `compute_weekly_change` in `lib/calculations.py`
    - Daily: `round(((close - open) / open) * 100, 2)`
    - Weekly: `round(((friday_close - monday_open) / monday_open) * 100, 2)`
    - _Requirements: 4.4, 4.5_

  - [x] 3.2 Implement `identify_dominant_variable` in `lib/calculations.py`
    - Filter instruments with non-None daily_change_pct
    - Find max absolute daily change
    - On tie, use INSTRUMENT_ORDER for tiebreaker (first in list wins)
    - Return `DominantVariable` with commentary string
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

  - [x] 3.3 Implement `get_color_for_change` in `lib/calculations.py`
    - Return "green" for positive, "red" for negative, "default" for zero, "default" for None
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x]* 3.4 Write property tests for calculations (Properties 1, 2, 3, 5)
    - **Property 1: Daily change formula correctness** — generate positive open/close floats, verify formula and 2dp rounding
    - **Property 2: Weekly change formula correctness** — generate positive monday_open/friday_close floats, verify formula and 2dp rounding
    - **Property 3: Color coding is determined by sign** — generate arbitrary floats, verify green/red/default mapping
    - **Property 5: Dominant variable is the instrument with maximum absolute daily change** — generate lists of InstrumentData, verify max absolute selection with tiebreaker
    - **Validates: Requirements 2.3, 2.4, 3.1-3.4, 4.4, 4.5, 5.2, 5.4**

  - [x]* 3.5 Write unit tests for calculations edge cases
    - Test `compute_daily_change` with known values
    - Test `compute_weekly_change` with known values
    - Test `identify_dominant_variable` with tied absolute values (tiebreaker)
    - Test `get_color_for_change` with zero and None inputs
    - Test instrument config has exactly 7 entries and correct significance labels
    - _Requirements: 2.1, 2.2, 3.5, 3.6, 5.4_

- [x] 4. Checkpoint - Core logic verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement cache layer
  - [x] 5.1 Implement `read_cache` and `write_cache` in `lib/cache.py`
    - `read_cache`: Load JSON file from `.cache/{key}.json`, parse `fetched_at`, check TTL or same-day validity
    - `write_cache`: Serialize data with `fetched_at` timestamp, write to `.cache/{key}.json`, return False on failure
    - Handle corrupted JSON by deleting the file and returning None
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 5.2 Implement `invalidate_cache` and `invalidate_stale_instrument_data` in `lib/cache.py`
    - `invalidate_cache(key)`: Delete `.cache/{key}.json` if it exists
    - `invalidate_stale_instrument_data()`: Scan for `instruments_*.json` files, delete those with dates before today (UTC+4)
    - _Requirements: 7.5_

  - [x]* 5.3 Write property tests for cache (Properties 7, 8)
    - **Property 7: Cache TTL freshness check** — generate fetched_at, current_time, max_age_hours; verify freshness returns True iff within TTL
    - **Property 8: Cache date-based validity for instrument data** — generate write/read timestamps in UTC+4; verify same-day = valid, different-day = stale
    - **Validates: Requirements 6.6, 7.2, 7.5**

  - [x]* 5.4 Write unit tests for cache edge cases
    - Test cache write failure continues operation (`test_cache_write_failure_continues`)
    - Test corrupted JSON file is handled gracefully
    - Test cache miss returns None
    - _Requirements: 7.6_

- [x] 6. Implement data fetcher
  - [x] 6.1 Rewrite `lib/data_fetcher.py` with simplified 7-instrument fetcher
    - Define `INSTRUMENTS` dict mapping display names to yfinance tickers
    - Implement `fetch_instrument_prices(market_day, week_start, week_end)` using yfinance
    - Make one API call per instrument (max 7 calls)
    - Return dict with open, close, weekly_open, weekly_close per instrument
    - Handle individual instrument fetch failures (log warning, set None values)
    - _Requirements: 2.1, 8.1, 8.2, 8.5_

  - [ ]* 6.2 Write unit tests for data fetcher
    - Test that exactly 7 instruments are configured
    - Test that a single instrument failure doesn't crash the full fetch (mock yfinance)
    - Test that partial failure returns data for successful instruments
    - _Requirements: 2.1, 8.1, 8.5_

- [x] 7. Implement scraper module
  - [x] 7.1 Implement `fetch_daily_recap` and `fetch_weekly_update` in `lib/scraper.py`
    - Send HTTP GET with 15-second timeout
    - Parse HTML with BeautifulSoup to extract title, publication date, and body
    - Truncate body to 5000 characters
    - Return `MarketReport` with `available=True` on success
    - On failure (timeout, parse error), return `MarketReport` with `available=False` and `error_message`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.2 Integrate scraper with cache layer
    - Before fetching, check cache with TTL (4 hours for daily, 12 hours for weekly)
    - On cache hit, return cached `MarketReport`
    - On cache miss, fetch fresh and write to cache
    - On fetch failure, serve stale cache if available with fallback message
    - _Requirements: 6.5, 6.6_

  - [x]* 7.3 Write property test for report body truncation (Property 6)
    - **Property 6: Report body truncation preserves content up to 5000 characters**
    - Generate arbitrary strings, verify `len(result) <= 5000` and content preservation
    - **Validates: Requirements 6.3, 6.4**

  - [ ]* 7.4 Write unit tests for scraper
    - Test scraper timeout shows fallback (`test_scraper_timeout_shows_fallback`) using mocked HTTP
    - Test daily report parsing with mock HTML (`test_scraper_parses_daily_report`)
    - Test weekly report parsing with mock HTML (`test_scraper_parses_weekly_report`)
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 8. Checkpoint - All modules verified independently
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Streamlit UI and wire everything together
  - [x] 9.1 Rewrite `app.py` as single-page Streamlit dashboard
    - Set page config with title "Global Macro Intelligence Dashboard"
    - Display title header as first element
    - Implement orchestration flow: resolve market day → check cache → fetch if needed → compute changes → identify dominant → render
    - Organize layout: title header, instrument grid, dominant variable section, daily report, weekly report
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 9.2 Implement instrument panel grid in `app.py`
    - Use `st.columns` to display 7 instrument panels in a grid
    - Each panel shows: ticker name, macro significance label, daily change %, weekly change %
    - Apply color coding using `get_color_for_change` (green/red/default via `st.markdown` with HTML)
    - Handle unavailable data with "Data unavailable" placeholder
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1-3.6_

  - [x] 9.3 Implement dominant variable section in `app.py`
    - Display section header
    - Show dominant instrument ticker, macro significance label, and daily change %
    - Include commentary text from `DominantVariable.commentary`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 9.4 Implement market report sections in `app.py`
    - Display daily recap section: title, publication date, body text
    - Display weekly update section: title, publication date, body text
    - Show fallback message when report is unavailable (with last successful fetch date)
    - _Requirements: 6.3, 6.4, 6.5_

  - [x] 9.5 Implement refresh button with cooldown logic in `app.py`
    - Add refresh button to the page
    - Track `last_refresh_time` in `st.session_state`
    - Disable button for 60 seconds after click
    - On click: invalidate cache, refetch instrument data and reports
    - Handle partial fetch failures (keep cached data for failed instruments, show warning)
    - _Requirements: 8.3, 8.4, 8.5_

  - [x]* 9.6 Write property test for refresh cooldown (Property 9)
    - **Property 9: Refresh cooldown enforcement**
    - Generate arbitrary last_refresh_time and current_time, verify cooldown logic returns True iff >= 60 seconds elapsed
    - **Validates: Requirements 8.4**

  - [ ]* 9.7 Write unit tests for UI logic
    - Test zero change uses default color (`test_zero_change_default_color`)
    - Test None change shows no color (`test_none_change_no_color`)
    - Test unavailable data shows placeholder (`test_unavailable_data_shows_placeholder`)
    - Test partial fetch failure uses cached data (`test_partial_fetch_failure_uses_cached`)
    - _Requirements: 2.5, 3.5, 3.6, 8.5_

- [x] 10. Retire multi-page structure
  - [x] 10.1 Remove `pages/` directory and unused modules
    - Delete all files in `pages/` directory (the 5 page files and `.gitkeep`)
    - Remove `lib/db.py` and `lib/models.py` (Supabase-related, no longer needed)
    - Remove `schema.sql` (Supabase schema, no longer needed)
    - Update `lib/__init__.py` if it imports removed modules
    - _Requirements: 1.1_

  - [x] 10.2 Update `requirements.txt` to remove unused dependencies and add new ones
    - Remove: `supabase`, `fredapi`, `twelvedata`, `streamlit-lightweight-charts`
    - Add: `beautifulsoup4`, `requests` (for scraper)
    - Keep: `streamlit`, `yfinance`, `pandas`, `numpy`, `plotly`, `pytest`, `hypothesis`, `pytest-mock`
    - _Requirements: 8.1_

- [ ] 11. Integration tests and final wiring
  - [ ]* 11.1 Write integration tests for the full dashboard
    - Test full page renders all sections (`test_full_page_renders_all_sections`) using Streamlit testing utilities
    - Test refresh button triggers fetch (`test_refresh_button_triggers_fetch`)
    - _Requirements: 1.1, 1.2, 1.3, 8.3_

- [ ] 12. Final checkpoint - All tests pass end-to-end
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (9 properties via Hypothesis)
- Unit tests validate specific examples and edge cases
- All property tests go in `tests/properties/test_dashboard_simplification.py`
- All unit tests go in `tests/unit/test_dashboard_simplification.py`
- All integration tests go in `tests/integration/test_dashboard_simplification.py`
- The project already has Hypothesis configured with 100 iterations default profile

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1", "3.3"] },
    { "id": 2, "tasks": ["2.3", "2.4", "3.2", "3.4", "3.5", "5.1", "5.2"] },
    { "id": 3, "tasks": ["5.3", "5.4", "6.1"] },
    { "id": 4, "tasks": ["6.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 6, "tasks": ["9.1", "10.1", "10.2"] },
    { "id": 7, "tasks": ["9.2", "9.3", "9.4", "9.5"] },
    { "id": 8, "tasks": ["9.6", "9.7", "11.1"] }
  ]
}
```
