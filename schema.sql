-- Global Macro Intelligence Dashboard - Supabase Schema
-- Apply this SQL in your Supabase project's SQL Editor

-- ============================================================================
-- Macro Events Table
-- Stores scheduled and unscheduled economic/geopolitical events
-- ============================================================================
CREATE TABLE IF NOT EXISTS macro_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_date DATE NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('monetary_policy', 'inflation_data', 'geopolitical', 'fiscal_policy')
    ),
    is_custom BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_macro_events_date ON macro_events (event_date DESC);
CREATE INDEX idx_macro_events_category ON macro_events (category);

-- ============================================================================
-- Dominant Variables Table
-- Daily record of which macro variable dominated market pricing
-- ============================================================================
CREATE TABLE IF NOT EXISTS dominant_variables (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_date DATE NOT NULL UNIQUE,
    variable TEXT NOT NULL,
    influence_score REAL,
    notes TEXT DEFAULT '',
    is_manual BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dominant_variables_date ON dominant_variables (record_date DESC);

-- ============================================================================
-- Expectations Table
-- Tracks consensus expectations vs actual outcomes for economic releases
-- ============================================================================
CREATE TABLE IF NOT EXISTS expectations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    release_date DATE NOT NULL,
    indicator TEXT NOT NULL,
    expected_value REAL NOT NULL,
    actual_value REAL,
    surprise_magnitude REAL,
    asset_reactions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_expectations_date ON expectations (release_date DESC);
CREATE INDEX idx_expectations_indicator ON expectations (indicator);

-- ============================================================================
-- Custom Assets Table
-- User-added ticker symbols for monitoring
-- ============================================================================
CREATE TABLE IF NOT EXISTS custom_assets (
    symbol TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('yfinance', 'fred', 'twelve_data')),
    added_date DATE DEFAULT CURRENT_DATE
);

-- ============================================================================
-- Row Level Security (RLS) - Optional
-- Enable if using Supabase Auth for multi-user support in the future
-- ============================================================================
-- ALTER TABLE macro_events ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dominant_variables ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE expectations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE custom_assets ENABLE ROW LEVEL SECURITY;
