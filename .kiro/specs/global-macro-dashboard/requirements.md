# Requirements Document

## Introduction

The Global Macro Intelligence Dashboard is a learning-oriented tool designed to help the user develop institutional-grade macro thinking. It provides real-time and historical market data monitoring with interactive charts, cross-asset relationship analysis, dominant variable identification, historical event analysis, and expectation tracking. The goal is to build pattern recognition and develop intuition by consistently tracking how macro variables interact, which factor dominates on any given day, and how surprise drives repricing — thinking like global macro hedge funds, rates traders, FX desks, and institutional allocators.

## Glossary

- **Dashboard**: The primary user interface of the Global Macro Intelligence Dashboard application
- **Asset_Panel**: A visual component displaying real-time price, change, trend data, and interactive chart for a single tracked asset
- **Cross_Asset_View**: A visualization showing relationships and correlations between multiple tracked assets over a configurable time period
- **Dominant_Variable**: The single macro factor (rates, USD, oil, liquidity, etc.) that most influences market pricing on a given day
- **Macro_Event**: A scheduled or unscheduled economic event (CPI release, Fed decision, geopolitical event) that may impact asset pricing
- **Correlation_Matrix**: A visual representation showing statistical relationships between tracked assets over a selected time window
- **Expectation_Tracker**: A component tracking market-implied expectations (Fed funds futures, inflation breakevens) versus actual outcomes
- **User**: The individual using the Global Macro Intelligence Dashboard for learning purposes

## Requirements

### Requirement 1: Real-Time Asset Monitoring with Interactive Charts

**User Story:** As a User, I want to monitor key macro assets in real-time with interactive charts, so that I can observe momentum, price action, and market movements to build pattern recognition across asset classes.

#### Acceptance Criteria

1. THE Dashboard SHALL display real-time price data for US 10-Year Treasury Yield, US 2-Year Treasury Yield, DXY, Oil (WTI), Gold, S&P 500, VIX, and BTC
2. WHEN a tracked asset price updates, THE Asset_Panel SHALL display the current price, absolute change, and percentage change from the previous close within 5 seconds of data availability
3. THE Dashboard SHALL display the last-updated timestamp for each Asset_Panel
4. WHEN the User opens the Dashboard, THE Dashboard SHALL load and display current data for all tracked assets within 10 seconds
5. WHERE the User configures additional assets, THE Dashboard SHALL support adding custom ticker symbols to the monitoring view
6. THE Dashboard SHALL display an interactive candlestick or line chart for each tracked asset
7. WHEN the User selects a time interval, THE Dashboard SHALL render chart data at the selected interval from the following options: 1 minute, 5 minutes, 10 minutes, 15 minutes, 30 minutes, 1 hour, 6 hours, 12 hours, 1 day, 1 week, 1 month, 2 months, 3 months, 6 months, and 1 year
8. THE Dashboard SHALL provide a date/time range slider that allows the User to pan and zoom across the chart's time axis
9. WHEN the User adjusts the date/time range slider, THE Dashboard SHALL update the chart view to display data within the selected range without requiring a page reload
10. THE Dashboard SHALL support toggling between candlestick and line chart display modes for each asset

### Requirement 2: Cross-Asset Relationship Visualization

**User Story:** As a User, I want to visualize relationships between macro assets, so that I can identify which variable is dominating markets and build cross-asset pattern recognition.

#### Acceptance Criteria

1. THE Cross_Asset_View SHALL display a Correlation_Matrix showing rolling correlations between all tracked assets over a user-selected time window (1 week, 1 month, 3 months, 6 months, 1 year)
2. WHEN the User selects two or more assets, THE Cross_Asset_View SHALL render an overlay chart showing normalized price movements for the selected assets over the chosen time period
3. THE Cross_Asset_View SHALL highlight correlation changes that exceed 0.3 in magnitude over the past 5 trading days
4. WHEN a significant correlation shift occurs, THE Dashboard SHALL flag the shift with a visual indicator on the Cross_Asset_View

### Requirement 3: Dominant Variable Identification

**User Story:** As a User, I want to identify which macro variable is dominating market pricing on any given day, so that I can focus my analysis on the most impactful factor.

#### Acceptance Criteria

1. THE Dashboard SHALL calculate and display a suggested Dominant_Variable based on relative asset moves and cross-asset correlations for the current trading session
2. WHEN the User views the daily summary, THE Dashboard SHALL present the top 3 contributing factors ranked by their estimated influence on overall market moves
3. THE Dashboard SHALL allow the User to manually select and record the Dominant_Variable for each day
4. THE Dashboard SHALL display a historical timeline of Dominant_Variable selections over the past 30, 90, and 180 days

### Requirement 4: Historical Event Analysis

**User Story:** As a User, I want to analyze how historical macro events impacted cross-asset pricing, so that I can study past patterns and improve my understanding of market reactions.

#### Acceptance Criteria

1. THE Dashboard SHALL maintain a database of significant Macro_Event records with dates, descriptions, and categories (monetary policy, inflation data, geopolitical, fiscal policy)
2. WHEN the User selects a historical Macro_Event, THE Dashboard SHALL display price movements for all tracked assets in the 1-day, 1-week, and 1-month windows surrounding the event
3. THE Dashboard SHALL allow the User to compare asset reactions across similar historical Macro_Event types (e.g., all CPI surprises, all rate decisions)
4. THE Dashboard SHALL allow the User to add custom Macro_Event entries with date, description, and category

### Requirement 5: Expectation vs Reality Tracking

**User Story:** As a User, I want to track market expectations versus actual outcomes for key economic data, so that I can understand how surprise drives repricing.

#### Acceptance Criteria

1. THE Expectation_Tracker SHALL display consensus expectations for upcoming economic releases alongside the actual reported values after release
2. WHEN an economic data release occurs, THE Expectation_Tracker SHALL calculate and display the surprise magnitude (actual minus expected, normalized by historical standard deviation)
3. THE Expectation_Tracker SHALL display the asset price reaction for each tracked asset in the 5-minute, 1-hour, and 1-day windows following a data release
4. THE Dashboard SHALL maintain a historical record of surprise magnitudes and corresponding asset reactions for pattern analysis
