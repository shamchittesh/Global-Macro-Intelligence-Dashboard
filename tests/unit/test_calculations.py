"""Unit tests for the simplified calculations module."""

import pytest

from lib.calculations import (
    INSTRUMENT_CONFIG,
    INSTRUMENT_ORDER,
    DominantVariable,
    InstrumentData,
    compute_daily_change,
    compute_weekly_change,
    get_color_for_change,
    identify_dominant_variable,
)


class TestComputeDailyChange:
    """Tests for compute_daily_change()."""

    def test_positive_change(self):
        result = compute_daily_change(100.0, 105.0)
        assert result == 5.0

    def test_negative_change(self):
        result = compute_daily_change(100.0, 95.0)
        assert result == -5.0

    def test_zero_change(self):
        result = compute_daily_change(100.0, 100.0)
        assert result == 0.0

    def test_rounds_to_2_decimal_places(self):
        result = compute_daily_change(100.0, 103.456)
        assert result == 3.46

    def test_small_price(self):
        result = compute_daily_change(0.01, 0.02)
        assert result == 100.0


class TestComputeWeeklyChange:
    """Tests for compute_weekly_change()."""

    def test_positive_change(self):
        result = compute_weekly_change(100.0, 110.0)
        assert result == 10.0

    def test_negative_change(self):
        result = compute_weekly_change(100.0, 90.0)
        assert result == -10.0

    def test_zero_change(self):
        result = compute_weekly_change(100.0, 100.0)
        assert result == 0.0

    def test_rounds_to_2_decimal_places(self):
        result = compute_weekly_change(100.0, 107.777)
        assert result == 7.78


class TestGetColorForChange:
    """Tests for get_color_for_change()."""

    def test_positive_is_green(self):
        assert get_color_for_change(1.5) == "green"

    def test_negative_is_red(self):
        assert get_color_for_change(-2.3) == "red"

    def test_zero_is_default(self):
        assert get_color_for_change(0.0) == "default"

    def test_none_is_default(self):
        assert get_color_for_change(None) == "default"

    def test_very_small_positive_is_green(self):
        assert get_color_for_change(0.001) == "green"

    def test_very_small_negative_is_red(self):
        assert get_color_for_change(-0.001) == "red"


class TestIdentifyDominantVariable:
    """Tests for identify_dominant_variable()."""

    def test_selects_largest_absolute_change(self):
        # VIX has typical vol of 4.0, SPY 1.0
        # SPY -2.0% / 1.0 = 2.0σ, VIX +1.5% / 4.0 = 0.375σ
        # SPY should win because it's more unusual relative to its own vol
        instruments = [
            InstrumentData("US10Y", "Growth/Rates", daily_change_pct=0.5),
            InstrumentData("SPY", "Risk Appetite", daily_change_pct=-2.0),
            InstrumentData("VIX", "Fear", daily_change_pct=1.5),
        ]
        result = identify_dominant_variable(instruments)
        assert result is not None
        assert result.ticker == "SPY"
        assert result.daily_change_pct == -2.0

    def test_tiebreaker_uses_instrument_order(self):
        # US10Y vol=0.8, DXY vol=0.4
        # US10Y: 0.8/0.8=1.0σ, DXY: 0.4/0.4=1.0σ — same z-score
        # US10Y should win because it comes first in INSTRUMENT_ORDER
        instruments = [
            InstrumentData("DXY", "Global Liquidity", daily_change_pct=0.4),
            InstrumentData("US10Y", "Growth/Rates", daily_change_pct=-0.8),
        ]
        result = identify_dominant_variable(instruments)
        assert result is not None
        assert result.ticker == "US10Y"

    def test_returns_none_when_no_valid_data(self):
        instruments = [
            InstrumentData("US10Y", "Growth/Rates", daily_change_pct=None),
            InstrumentData("SPY", "Risk Appetite", daily_change_pct=None),
        ]
        result = identify_dominant_variable(instruments)
        assert result is None

    def test_returns_none_for_empty_list(self):
        result = identify_dominant_variable([])
        assert result is None

    def test_commentary_includes_significance(self):
        instruments = [
            InstrumentData("VIX", "Fear", daily_change_pct=5.0),
        ]
        result = identify_dominant_variable(instruments)
        assert result is not None
        assert "Fear" in result.commentary
        assert "VIX" in result.ticker

    def test_skips_instruments_with_none_change(self):
        instruments = [
            InstrumentData("US10Y", "Growth/Rates", daily_change_pct=None),
            InstrumentData("SPY", "Risk Appetite", daily_change_pct=1.0),
        ]
        result = identify_dominant_variable(instruments)
        assert result is not None
        assert result.ticker == "SPY"


class TestInstrumentConfig:
    """Tests for instrument configuration constants."""

    def test_exactly_7_instruments(self):
        assert len(INSTRUMENT_ORDER) == 7
        assert len(INSTRUMENT_CONFIG) == 7

    def test_all_ordered_instruments_have_config(self):
        for name in INSTRUMENT_ORDER:
            assert name in INSTRUMENT_CONFIG

    def test_significance_labels_correct(self):
        assert INSTRUMENT_CONFIG["US10Y"]["macro_significance"] == "Growth/Rates"
        assert INSTRUMENT_CONFIG["US2Y"]["macro_significance"] == "Fed Expectations"
        assert INSTRUMENT_CONFIG["DXY"]["macro_significance"] == "Global Liquidity"
        assert INSTRUMENT_CONFIG["Oil"]["macro_significance"] == "Fear/Real yields"
        assert INSTRUMENT_CONFIG["SPY"]["macro_significance"] == "Risk Appetite"
        assert INSTRUMENT_CONFIG["QQQ"]["macro_significance"] == "Growth/Liquidity"
        assert INSTRUMENT_CONFIG["VIX"]["macro_significance"] == "Fear"

    def test_all_instruments_have_ticker(self):
        for name, config in INSTRUMENT_CONFIG.items():
            assert "ticker" in config
            assert config["ticker"]  # non-empty
