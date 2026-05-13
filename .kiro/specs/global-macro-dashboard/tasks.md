# Implementation Plan: Global Macro Intelligence Dashboard

## Overview

This plan builds the Global Macro Intelligence Dashboard incrementally, starting with project scaffolding and data models, then the data fetching layer, calculations engine, database persistence, and finally the five Streamlit pages. Each step builds on the previous, ensuring no orphaned code. Property-based tests validate correctness properties from the design, and unit tests cover edge cases and integration points.

## Tasks

- [x] 1. Set up project structure, dependencies, and data models
  - [x] 1.1 Create project directory structure and configuration files
    - Create `app.py`, `pages/`, `lib/`, `tests/`, `.streamlit/` directories
    - Create `requirements.txt` with all dependencies (streamlit, streamlit-lightweight-charts, plotly, yfinance, fredapi, twelvedata, supabase, pandas, numpy, scipy, pytest, hypothesis, pytest-mock)
    - Create `.streamlit/secrets.toml.example` with placeholder keys for FRED, Twelve Data, and Supabase
    - Create `pytest.ini` or `pyproject.toml` with test configuration
    - _Requirements: 1.1, 1.4_

  - [x] 1.2 Implement data models and enums in `lib/models.py`
    - Define `AssetSource`, `ChartType`, `EventCategory` enums
    - Define `TrackedAsset`, `AssetPrice`, `MacroEvent`, `DominantVariableRecord`, `ExpectationRecord`, `CustomAsset` dataclasses
    - Define `DominantFactor`, `CorrelationShift`, `EconomicEvent` dataclasses
    - Define `DEFAULT_ASSETS` list and `INTERVALS` configuration dict
    - _Requirements: 1.1, 1.5, 1.7, 4.1, 5.1_

  - [ ]* 1.3 Write unit tests for data models
    - Test enum membership and value validation
    - Test dataclass instantiation with valid and invalid data
    - Test DEFAULT_ASSETS contains all required symbols
    - _Requirements: 1.1, 4.1_

- [x] 2. Implement data fetcher module
  - [x] 2.1 Implement `DataFetcher` class in `lib/data_fetcher.py`
    - Implement `get_asset_data()` with source routing based on `AssetSource` (yfinance, FRED, Twelve Data)
    - Implement `get_yield_data()` for FRED series retrieval
    - Implement `get_current_prices()` for latest price snapshots with change calculations
    - Implement `get_economic_calendar()` stub for upcoming releases
    - Add `@st.cache_data` decorators with appropriate TTLs
    - Implement interval resampling logic for intervals not natively supported by data sources
    - Handle error cases: API timeouts, invalid symbols, rate limits, fallback between sources
    - _Requirements: 1.1, 1.2, 1.4, 1.7, 5.1_

  - [ ]* 2.2 Write property test for price change computation
    - **Property 1: Price Change Computation**
    - For any positive current price and previous close, verify absolute change = current - previous and pct_change = (current - previous) / previous * 100
    - **Validates: Requirements 1.2**

  - [ ]* 2.3 Write property test for OHLCV resampling invariants
    - **Property 2: OHLCV Resampling Invariants**
    - For any sequence of OHLCV candles resampled to a coarser interval, verify open = first open, high = max high, low = min low, close = last close, volume = sum of volumes
    - **Validates: Requirements 1.7**

  - [ ]* 2.4 Write unit tests for data fetcher
    - Mock yfinance, FRED, and Twelve Data API responses
    - Test correct source routing based on AssetSource
    - Test error handling (timeout, invalid symbol, rate limit)
    - Test fallback behavior when primary source fails
    - Test cache decorator behavior
    - _Requirements: 1.1, 1.4, 1.7_

- [x] 3. Implement calculations module
  - [x] 3.1 Implement core calculation functions in `lib/calculations.py`
    - Implement `compute_correlation_matrix()` with rolling window support
    - Implement `normalize_prices()` for overlay chart normalization
    - Implement `compute_correlation_changes()` for detecting significant shifts
    - Implement `identify_dominant_variable()` using magnitude-weighted correlation scoring
    - Implement `compute_surprise_magnitude()` for expectation vs reality analysis
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 5.2_

  - [ ]* 3.2 Write property test for correlation matrix mathematical properties
    - **Property 3: Correlation Matrix Mathematical Properties**
    - For any set of N ≥ 2 asset return series with sufficient data points, verify matrix is symmetric, diagonal = 1.0, off-diagonal in [-1, 1]
    - **Validates: Requirements 2.1**

  - [ ]* 3.3 Write property test for price normalization invariant
    - **Property 4: Price Normalization Invariant**
    - For any set of price series and valid base date, verify all series = 100.0 at base date and ratios are preserved
    - **Validates: Requirements 2.2**

  - [ ]* 3.4 Write property test for correlation shift detection completeness
    - **Property 5: Correlation Shift Detection Completeness**
    - For any pair of correlation matrices and threshold 0.3, verify all pairs with |change| > threshold are included and all pairs with |change| <= threshold are excluded
    - **Validates: Requirements 2.3**

  - [ ]* 3.5 Write property test for dominant variable ranking invariant
    - **Property 6: Dominant Variable Ranking Invariant**
    - For any non-empty asset returns and valid correlation matrix, verify non-empty result sorted descending by influence score with all scores ≥ 0
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 3.6 Write property test for surprise magnitude computation
    - **Property 8: Surprise Magnitude Computation**
    - For any actual, expected, and positive historical_std, verify result = (actual - expected) / historical_std. When std ≤ 0, verify None or error.
    - **Validates: Requirements 5.2**

  - [ ]* 3.7 Write unit tests for calculations module
    - Test known-answer correlation examples (perfect correlation = 1.0, inverse = -1.0)
    - Test edge cases: empty data, single data point, insufficient data returns NaN
    - Test normalization with identical prices
    - Test dominant variable with single asset
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 5.2_

- [x] 4. Checkpoint - Core logic verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement database module
  - [x] 5.1 Implement `MacroDB` class in `lib/db.py`
    - Initialize Supabase client from Streamlit secrets
    - Implement `save_dominant_variable()` and `get_dominant_variable_history()`
    - Implement `save_macro_event()` and `get_macro_events()` with category filtering
    - Implement `save_expectation()` and `get_expectations_history()` with indicator filtering
    - Implement `save_custom_asset()` and `get_custom_assets()`
    - Add input validation for all save operations (non-empty strings, valid dates, valid categories, numeric values)
    - Handle connection failures gracefully (read-only mode, session state caching)
    - _Requirements: 3.3, 3.4, 4.1, 4.4, 5.1, 5.4_

  - [x] 5.2 Create Supabase schema migration file
    - Create `schema.sql` with CREATE TABLE statements for `macro_events`, `dominant_variables`, `expectations`, `custom_assets`
    - Include CHECK constraints, indexes, and default values as defined in design
    - _Requirements: 4.1, 5.4_

  - [ ]* 5.3 Write property test for domain object persistence round-trip
    - **Property 7: Domain Object Persistence Round-Trip**
    - For any valid MacroEvent or ExpectationRecord, verify save then retrieve produces equal object
    - **Validates: Requirements 4.1, 4.4, 5.4**

  - [ ]* 5.4 Write unit tests for database module
    - Test CRUD operations with mocked Supabase client
    - Test input validation (empty strings, invalid dates, invalid categories)
    - Test connection failure handling and read-only mode
    - _Requirements: 3.3, 4.1, 4.4, 5.4_

- [x] 6. Implement Asset Monitor page
  - [x] 6.1 Implement `pages/1_📊_Asset_Monitor.py`
    - Render price panels for all DEFAULT_ASSETS showing current price, absolute change, percentage change, and last-updated timestamp
    - Render interactive candlestick/line chart per asset using streamlit-lightweight-charts
    - Implement interval selector dropdown with all supported intervals from INTERVALS config
    - Implement chart type toggle (candlestick vs line)
    - Implement date/time range controls for pan and zoom
    - Implement custom asset addition form with symbol validation (verify data exists before saving)
    - Wire DataFetcher for data retrieval and MacroDB for custom asset persistence
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [ ]* 6.2 Write unit tests for Asset Monitor page logic
    - Test price panel rendering with mock data
    - Test interval selection triggers correct data fetch
    - Test custom asset validation (valid/invalid symbols)
    - _Requirements: 1.1, 1.2, 1.5_

- [x] 7. Implement Cross-Asset Relationship page
  - [x] 7.1 Implement `pages/2_🔗_Cross_Asset.py`
    - Render correlation matrix heatmap using Plotly with user-selectable time window (1 week, 1 month, 3 months, 6 months, 1 year)
    - Implement multi-asset selector for overlay chart
    - Render normalized price overlay chart using streamlit-lightweight-charts for selected assets
    - Highlight correlation shifts exceeding 0.3 magnitude over past 5 trading days with visual indicators
    - Wire DataFetcher for price data and Calculations module for correlation/normalization
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 7.2 Write unit tests for Cross-Asset page logic
    - Test correlation matrix rendering with mock correlation data
    - Test overlay chart with normalized mock price series
    - Test correlation shift highlighting logic
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 8. Implement Dominant Variable page
  - [x] 8.1 Implement `pages/3_🎯_Dominant_Variable.py`
    - Display system-calculated top 3 dominant factors with influence scores for current session
    - Implement manual dominant variable selection form with notes field
    - Render historical timeline of dominant variable selections (30, 90, 180 day views)
    - Wire Calculations module for factor ranking and MacroDB for persistence/retrieval
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 8.2 Write unit tests for Dominant Variable page logic
    - Test factor ranking display with mock calculation results
    - Test manual selection form submission and persistence
    - Test timeline rendering with mock history data
    - _Requirements: 3.1, 3.3, 3.4_

- [x] 9. Implement Event Analysis page
  - [x] 9.1 Implement `pages/4_📅_Event_Analysis.py`
    - Display list of macro events from database with category filtering
    - Implement event selection showing price movements for all tracked assets in 1-day, 1-week, 1-month windows around the event
    - Implement cross-event comparison view for similar event types (e.g., all CPI surprises)
    - Implement custom event entry form with date, description, and category fields (with validation)
    - Implement asset reaction computation for event windows
    - Wire MacroDB for event CRUD and DataFetcher for historical price data around events
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 9.2 Write property test for asset reaction computation
    - **Property 9: Asset Reaction Computation**
    - For any price series with a release timestamp and valid window endpoints, verify reaction = (price_at_end - price_at_release) / price_at_release * 100
    - **Validates: Requirements 5.3, 4.2**

  - [ ]* 9.3 Write unit tests for Event Analysis page logic
    - Test event list rendering and category filtering
    - Test price movement window calculations with mock data
    - Test custom event form validation
    - _Requirements: 4.1, 4.2, 4.4_

- [x] 10. Implement Expectations page
  - [x] 10.1 Implement `pages/5_📈_Expectations.py`
    - Display upcoming economic releases with consensus expectations
    - Display actual values alongside expectations after release with surprise magnitude calculation
    - Render asset price reactions in 5-minute, 1-hour, and 1-day windows following releases
    - Implement historical surprise/reaction pattern analysis view
    - Implement expectation entry form for recording expected and actual values
    - Wire DataFetcher for price data, Calculations for surprise computation, and MacroDB for persistence
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 10.2 Write unit tests for Expectations page logic
    - Test surprise magnitude display with known values
    - Test reaction window rendering with mock price data
    - Test expectation form submission and validation
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 11. Implement main app entry point and navigation
  - [x] 11.1 Implement `app.py` with navigation and shared state
    - Configure Streamlit page settings (title, icon, layout)
    - Set up multi-page navigation structure
    - Initialize shared session state (DataFetcher instance, MacroDB instance)
    - Add sidebar with global controls (refresh button, data source status indicators)
    - Display error banners for data source failures (stale data warnings, read-only mode)
    - _Requirements: 1.4, 1.1_

  - [ ]* 11.2 Write unit tests for app initialization
    - Test session state initialization
    - Test error banner display logic
    - _Requirements: 1.4_

- [x] 12. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All pages depend on the core modules (data_fetcher, calculations, db, models) being implemented first
- Supabase schema must be applied manually to the Supabase project before running persistence-dependent features
- `.streamlit/secrets.toml` must be configured with real API keys before data fetching works
