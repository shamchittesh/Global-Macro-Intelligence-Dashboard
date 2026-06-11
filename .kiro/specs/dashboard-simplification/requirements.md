# Requirements Document

## Introduction

This specification defines the simplified Global Macro Intelligence Dashboard — a single-page Streamlit application that replaces the current multi-page dashboard. The simplified dashboard tracks 7 key macro instruments with daily and weekly percentage changes, displays color-coded performance indicators, provides a "dominant variable" commentary section, and scrapes market reports from Edward Jones. Data is cached to avoid API rate limits and reflects the most recent US market close (adjusted for the user's Mauritius timezone).

## Glossary

- **Dashboard**: The single-page Streamlit web application displaying macro instrument data and market commentary
- **Instrument**: A financial ticker tracked by the Dashboard (one of: US10Y, US2Y, DXY, Oil, SPY, QQQ, VIX)
- **Macro_Significance**: A label describing what macro factor an Instrument represents (e.g., "Growth/Rates", "Fed Expectations", "Global Liquidity", "Fear/Real yields", "Risk Appetite", "Growth/Liquidity", "Fear")
- **Daily_Change**: The percentage change between the most recent trading day's open and close prices
- **Weekly_Change**: The percentage change between the Monday open and the most recent Friday close for the current or previous trading week
- **Data_Cache**: A local caching layer that stores fetched market data to avoid repeated API calls
- **Market_Day**: A day when the US stock and bond markets are open for trading (a weekday that is not a US market holiday)
- **Scraper**: The module responsible for fetching and parsing market report content from Edward Jones web pages
- **Dominant_Variable_Section**: The area of the Dashboard displaying commentary about the core macro factor driving market movements today
- **User_Timezone**: The Mauritius timezone (UTC+4), used to determine which US market day qualifies as "latest"

## Requirements

### Requirement 1: Single-Page Layout

**User Story:** As a macro analyst, I want all information on a single page, so that I can assess the market state at a glance without navigating between pages.

#### Acceptance Criteria

1. THE Dashboard SHALL render all instrument panels, the Dominant_Variable_Section, and the market report sections on a single vertically-scrollable page without requiring multi-page navigation or route changes
2. THE Dashboard SHALL display a title header containing the text "Global Macro Intelligence Dashboard" as the first visible element on the page
3. THE Dashboard SHALL organize content into distinct visual sections displayed in the following order from top to bottom: title header, instrument panel grid, Dominant_Variable_Section, daily market report, and weekly market report

### Requirement 2: Instrument Tracking

**User Story:** As a macro analyst, I want to see 7 key macro instruments with their significance labels, so that I can monitor the most important market drivers.

#### Acceptance Criteria

1. THE Dashboard SHALL display a panel for exactly 7 instruments: US10Y, US2Y, DXY, Oil, SPY, QQQ, and VIX, showing for each instrument its ticker name, Macro_Significance label, Daily_Change percentage, and Weekly_Change percentage
2. THE Dashboard SHALL display the Macro_Significance label for each Instrument as follows: US10Y ("Growth/Rates"), US2Y ("Fed Expectations"), DXY ("Global Liquidity"), Oil ("Fear/Real yields"), SPY ("Risk Appetite"), QQQ ("Growth/Liquidity"), VIX ("Fear")
3. THE Dashboard SHALL display the Daily_Change for each Instrument as a percentage value rounded to 2 decimal places
4. THE Dashboard SHALL display the Weekly_Change for each Instrument as a percentage value rounded to 2 decimal places
5. IF price data for an instrument is unavailable, THEN THE Dashboard SHALL display that instrument's panel with a "Data unavailable" indicator in place of the Daily_Change and Weekly_Change values while continuing to show the remaining instruments

### Requirement 3: Color-Coded Change Indicators

**User Story:** As a macro analyst, I want positive and negative changes to be visually distinct, so that I can quickly identify market direction.

#### Acceptance Criteria

1. WHEN the Daily_Change for an Instrument is greater than zero, THE Dashboard SHALL display that Daily_Change value text in green
2. WHEN the Daily_Change for an Instrument is less than zero, THE Dashboard SHALL display that Daily_Change value text in red
3. WHEN the Weekly_Change for an Instrument is greater than zero, THE Dashboard SHALL display that Weekly_Change value text in green
4. WHEN the Weekly_Change for an Instrument is less than zero, THE Dashboard SHALL display that Weekly_Change value text in red
5. WHEN the Daily_Change or Weekly_Change for an Instrument equals zero, THE Dashboard SHALL display that value text in the default (unstyled) text color
6. IF the Daily_Change or Weekly_Change for an Instrument is unavailable due to missing or insufficient data, THEN THE Dashboard SHALL display a placeholder label indicating data is unavailable, without applying red or green color coding

### Requirement 4: Market Day Resolution

**User Story:** As a macro analyst in Mauritius, I want the dashboard to show the latest completed US market day's data, so that the displayed data reflects closed prices rather than intraday fluctuations.

#### Acceptance Criteria

1. THE Dashboard SHALL determine the latest Market_Day by converting the current time in the User_Timezone (UTC+4) to US Eastern Time and selecting the most recent day on which the US stock market was open and closed (i.e., a weekday that is not a US market holiday, with market close at 16:00 ET having already passed)
2. WHEN the current day in US Eastern Time is a weekend or a US market holiday, THE Dashboard SHALL display data from the most recent preceding trading day
3. WHEN the current day in US Eastern Time is a trading day but the US market has not yet closed (before 16:00 ET), THE Dashboard SHALL display data from the previous trading day
4. THE Dashboard SHALL calculate Daily_Change as a percentage using the formula: ((close price − open price) / open price) × 100, where open and close prices are from the resolved latest Market_Day
5. THE Dashboard SHALL calculate Weekly_Change as a percentage using the formula: ((Friday close − Monday open) / Monday open) × 100, using the most recently completed trading week (Monday through Friday)
6. IF Monday of a trading week is a US market holiday, THEN THE Dashboard SHALL use the open price from the first trading day of that week as the Monday open for the Weekly_Change calculation
7. IF Friday of a trading week is a US market holiday, THEN THE Dashboard SHALL use the close price from the last trading day of that week as the Friday close for the Weekly_Change calculation

### Requirement 5: Dominant Variable Commentary

**User Story:** As a macro analyst, I want to see an overall comment about which macro variable is dominating market movement today, so that I can focus my analysis on the most important factor.

#### Acceptance Criteria

1. THE Dashboard SHALL display a Dominant_Variable_Section containing commentary about the primary macro factor driving market movements
2. THE Dominant_Variable_Section SHALL identify which of the 7 tracked instruments is exhibiting the largest absolute Daily_Change as the dominant variable
3. THE Dominant_Variable_Section SHALL include the Macro_Significance label of the dominant instrument in the commentary
4. WHEN two or more instruments share the same largest absolute Daily_Change value, THE Dashboard SHALL select the instrument that appears first in the defined instrument order (US10Y, US2Y, DXY, Oil, SPY, QQQ, VIX) as the dominant variable
5. THE Dominant_Variable_Section SHALL display both the dominant instrument's ticker and its Daily_Change percentage alongside the commentary

### Requirement 6: Market Report Scraping

**User Story:** As a macro analyst, I want market summaries scraped from Edward Jones, so that I have professional market context alongside the instrument data.

#### Acceptance Criteria

1. THE Scraper SHALL fetch the daily market recap content from https://www.edwardjones.ca/ca-en/market-news-insights/stock-market-news/daily-market-recap and extract the report title, publication date, and body text
2. THE Scraper SHALL fetch the weekly market update content from https://www.edwardjones.com/us-en/market-news-insights/stock-market-news/stock-market-weekly-update and extract the report title, publication date, and body text
3. THE Dashboard SHALL display the scraped daily market recap in a dedicated section showing the report title, publication date, and body text limited to 5000 characters
4. THE Dashboard SHALL display the scraped weekly market update in a dedicated section showing the report title, publication date, and body text limited to 5000 characters
5. IF the Scraper fails to fetch or parse content from either source within 15 seconds, THEN THE Dashboard SHALL display a fallback message indicating the report is temporarily unavailable and the date of the last successful fetch
6. THE Scraper SHALL cache fetched report content and refresh the daily recap no more frequently than once every 4 hours and the weekly update no more frequently than once every 12 hours

### Requirement 7: Data Caching

**User Story:** As a user with limited API quota, I want fetched data to be cached, so that repeated page loads do not trigger additional API calls.

#### Acceptance Criteria

1. THE Data_Cache SHALL store fetched instrument price data (open, close, daily change, weekly change) after the first successful retrieval
2. THE Data_Cache SHALL serve cached instrument data on subsequent requests within the same calendar day (in the User_Timezone, UTC+4)
3. WHEN cached data exists for the current calendar day (in User_Timezone), THE Dashboard SHALL use cached data instead of making new API calls
4. THE Data_Cache SHALL store scraped market report content after the first successful retrieval
5. WHEN the calendar day changes (crossing midnight in User_Timezone), THE Data_Cache SHALL invalidate stale instrument data and allow fresh retrieval on the next request
6. IF a cache write fails, THEN THE Dashboard SHALL continue operating with fresh API data and log a warning without interrupting the user experience

### Requirement 8: Minimal API Usage

**User Story:** As a user concerned about rate limits, I want the dashboard to fetch only the 7 required data points per refresh cycle, so that API consumption is minimized.

#### Acceptance Criteria

1. WHEN a data refresh cycle is triggered, THE Dashboard SHALL fetch price data for no more than 7 instruments per cycle
2. WHEN a data refresh cycle is triggered, THE Dashboard SHALL make no more than 7 API calls to the market data source per cycle (one call per instrument)
3. THE Dashboard SHALL provide a manual refresh button that allows the User to trigger a new data fetch on demand
4. WHEN the User clicks the manual refresh button, THE Dashboard SHALL disable the button for a minimum of 60 seconds before allowing another manual refresh
5. IF a data refresh cycle fails for one or more instruments, THEN THE Dashboard SHALL display the last successfully fetched data for the failed instruments and indicate which instruments failed to update
