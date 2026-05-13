"""Unit tests for the calculations module."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from lib.calculations import (
    compute_asset_reaction,
    compute_correlation_changes,
    compute_correlation_matrix,
    compute_surprise_magnitude,
    identify_dominant_variable,
    normalize_prices,
)
from lib.models import CorrelationShift, DominantFactor


class TestComputeCorrelationMatrix:
    """Tests for compute_correlation_matrix()."""

    def test_perfect_positive_correlation(self):
        """Two identical series should have correlation 1.0."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        returns = pd.Series(np.random.randn(30), index=dates)
        price_data = {"A": returns, "B": returns.copy()}

        result = compute_correlation_matrix(price_data, window=30)

        assert result.loc["A", "B"] == pytest.approx(1.0)
        assert result.loc["B", "A"] == pytest.approx(1.0)
        assert result.loc["A", "A"] == pytest.approx(1.0)
        assert result.loc["B", "B"] == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        """A series and its negation should have correlation -1.0."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        returns = pd.Series(np.random.randn(30), index=dates)
        price_data = {"A": returns, "B": -returns}

        result = compute_correlation_matrix(price_data, window=30)

        assert result.loc["A", "B"] == pytest.approx(-1.0)

    def test_symmetric_matrix(self):
        """Correlation matrix should be symmetric."""
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        price_data = {
            "A": pd.Series(np.random.randn(50), index=dates),
            "B": pd.Series(np.random.randn(50), index=dates),
            "C": pd.Series(np.random.randn(50), index=dates),
        }

        result = compute_correlation_matrix(price_data, window=50)

        assert result.loc["A", "B"] == pytest.approx(result.loc["B", "A"])
        assert result.loc["A", "C"] == pytest.approx(result.loc["C", "A"])
        assert result.loc["B", "C"] == pytest.approx(result.loc["C", "B"])

    def test_empty_input(self):
        """Empty input should return empty DataFrame."""
        result = compute_correlation_matrix({}, window=30)
        assert result.empty

    def test_single_asset(self):
        """Single asset should return empty DataFrame (need >= 2)."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        price_data = {"A": pd.Series(np.random.randn(30), index=dates)}

        result = compute_correlation_matrix(price_data, window=30)
        assert result.empty

    def test_insufficient_data_returns_nan(self):
        """With only 1 data point, correlation should be NaN."""
        dates = pd.date_range("2024-01-01", periods=1, freq="D")
        price_data = {
            "A": pd.Series([1.0], index=dates),
            "B": pd.Series([2.0], index=dates),
        }

        result = compute_correlation_matrix(price_data, window=30)

        # With only 1 data point, off-diagonal should be NaN
        assert pd.isna(result.loc["A", "B"])

    def test_window_limits_data(self):
        """Window parameter should limit data used for correlation."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        # First 50 points: perfectly correlated
        # Last 50 points: uncorrelated
        a = np.concatenate([np.arange(50), np.random.randn(50)])
        b = np.concatenate([np.arange(50), np.random.randn(50)])
        price_data = {
            "A": pd.Series(a, index=dates),
            "B": pd.Series(b, index=dates),
        }

        # Using window=50 should only use the last 50 (uncorrelated) points
        result = compute_correlation_matrix(price_data, window=50)

        # The correlation should be much less than 1.0 (since last 50 are random)
        assert abs(result.loc["A", "B"]) < 0.9


class TestNormalizePrices:
    """Tests for normalize_prices()."""

    def test_base_date_equals_100(self):
        """All series should equal 100.0 at the base date."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        base_date = datetime(2024, 1, 5)
        price_series = {
            "A": pd.Series(range(100, 110), index=dates, dtype=float),
            "B": pd.Series(range(50, 60), index=dates, dtype=float),
        }

        result = normalize_prices(price_series, base_date)

        assert result["A"][base_date] == pytest.approx(100.0)
        assert result["B"][base_date] == pytest.approx(100.0)

    def test_ratio_preservation(self):
        """Ratios between points should be preserved after normalization."""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        base_date = datetime(2024, 1, 1)
        prices = pd.Series([100.0, 110.0, 90.0, 120.0, 105.0], index=dates)
        price_series = {"A": prices}

        result = normalize_prices(price_series, base_date)

        # Original ratio: 110/100 = 1.1
        # Normalized ratio: result[1]/result[0] should also be 1.1
        original_ratio = prices.iloc[1] / prices.iloc[0]
        normalized_ratio = result["A"].iloc[1] / result["A"].iloc[0]
        assert original_ratio == pytest.approx(normalized_ratio)

    def test_empty_series(self):
        """Empty series should return empty series."""
        price_series = {"A": pd.Series(dtype=float)}
        result = normalize_prices(price_series, datetime(2024, 1, 1))
        assert result["A"].empty

    def test_identical_prices(self):
        """Identical prices should all normalize to 100.0."""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        base_date = datetime(2024, 1, 1)
        price_series = {"A": pd.Series([50.0] * 5, index=dates)}

        result = normalize_prices(price_series, base_date)

        for val in result["A"]:
            assert val == pytest.approx(100.0)


class TestComputeCorrelationChanges:
    """Tests for compute_correlation_changes()."""

    def test_detects_large_shift(self):
        """Should detect shifts exceeding threshold."""
        assets = ["A", "B", "C"]
        current = pd.DataFrame(
            [[1.0, 0.8, 0.2], [0.8, 1.0, -0.1], [0.2, -0.1, 1.0]],
            index=assets,
            columns=assets,
        )
        prior = pd.DataFrame(
            [[1.0, 0.3, 0.2], [0.3, 1.0, -0.1], [0.2, -0.1, 1.0]],
            index=assets,
            columns=assets,
        )

        result = compute_correlation_changes(current, prior, threshold=0.3)

        # A-B changed from 0.3 to 0.8 = 0.5 change (> 0.3)
        assert len(result) == 1
        assert result[0].asset_a == "A"
        assert result[0].asset_b == "B"
        assert result[0].change == pytest.approx(0.5)

    def test_excludes_small_shift(self):
        """Should not include shifts below threshold."""
        assets = ["A", "B"]
        current = pd.DataFrame(
            [[1.0, 0.5], [0.5, 1.0]], index=assets, columns=assets
        )
        prior = pd.DataFrame(
            [[1.0, 0.4], [0.4, 1.0]], index=assets, columns=assets
        )

        result = compute_correlation_changes(current, prior, threshold=0.3)

        # Change is 0.1, below threshold
        assert len(result) == 0

    def test_empty_matrices(self):
        """Empty matrices should return empty list."""
        result = compute_correlation_changes(pd.DataFrame(), pd.DataFrame())
        assert result == []


class TestIdentifyDominantVariable:
    """Tests for identify_dominant_variable()."""

    def test_returns_top_3(self):
        """Should return at most 3 factors."""
        assets = ["A", "B", "C", "D", "E"]
        returns = {a: float(i + 1) for i, a in enumerate(assets)}
        corr = pd.DataFrame(
            np.eye(5), index=assets, columns=assets
        )

        result = identify_dominant_variable(returns, corr)

        assert len(result) <= 3

    def test_sorted_descending(self):
        """Results should be sorted by influence score descending."""
        assets = ["A", "B", "C"]
        returns = {"A": 5.0, "B": 2.0, "C": 0.5}
        corr = pd.DataFrame(
            [[1.0, 0.5, 0.3], [0.5, 1.0, 0.2], [0.3, 0.2, 1.0]],
            index=assets,
            columns=assets,
        )

        result = identify_dominant_variable(returns, corr)

        for i in range(len(result) - 1):
            assert result[i].influence_score >= result[i + 1].influence_score

    def test_non_negative_scores(self):
        """All influence scores should be non-negative."""
        assets = ["A", "B", "C"]
        returns = {"A": -3.0, "B": 1.5, "C": -0.5}
        corr = pd.DataFrame(
            [[1.0, 0.7, -0.3], [0.7, 1.0, 0.1], [-0.3, 0.1, 1.0]],
            index=assets,
            columns=assets,
        )

        result = identify_dominant_variable(returns, corr)

        for factor in result:
            assert factor.influence_score >= 0

    def test_empty_returns(self):
        """Empty returns should return empty list."""
        result = identify_dominant_variable({}, pd.DataFrame())
        assert result == []

    def test_single_asset(self):
        """Single asset should still return a result."""
        returns = {"A": 2.5}
        corr = pd.DataFrame([[1.0]], index=["A"], columns=["A"])

        result = identify_dominant_variable(returns, corr)

        assert len(result) == 1
        assert result[0].variable == "A"
        assert result[0].influence_score >= 0


class TestComputeSurpriseMagnitude:
    """Tests for compute_surprise_magnitude()."""

    def test_basic_computation(self):
        """Should compute (actual - expected) / historical_std."""
        result = compute_surprise_magnitude(actual=3.5, expected=3.0, historical_std=0.5)
        assert result == pytest.approx(1.0)

    def test_negative_surprise(self):
        """Negative surprise when actual < expected."""
        result = compute_surprise_magnitude(actual=2.0, expected=3.0, historical_std=0.5)
        assert result == pytest.approx(-2.0)

    def test_zero_std_returns_none(self):
        """Should return None when historical_std is 0."""
        result = compute_surprise_magnitude(actual=3.0, expected=2.0, historical_std=0.0)
        assert result is None

    def test_negative_std_returns_none(self):
        """Should return None when historical_std is negative."""
        result = compute_surprise_magnitude(actual=3.0, expected=2.0, historical_std=-1.0)
        assert result is None

    def test_no_surprise(self):
        """Should return 0 when actual equals expected."""
        result = compute_surprise_magnitude(actual=3.0, expected=3.0, historical_std=1.0)
        assert result == pytest.approx(0.0)


class TestComputeAssetReaction:
    """Tests for compute_asset_reaction()."""

    def test_basic_reaction(self):
        """Should compute percentage change from release price."""
        dates = pd.date_range("2024-01-01 10:00", periods=100, freq="5min")
        # Price starts at 100, goes to 105 after 5 min, 110 after 1 hr
        prices = pd.Series([100.0] + [105.0] * 11 + [110.0] * 88, index=dates)
        release = datetime(2024, 1, 1, 10, 0)

        result = compute_asset_reaction(prices, release, ["5min", "1hr"])

        assert result["5min"] == pytest.approx(5.0)  # (105-100)/100*100
        assert result["1hr"] == pytest.approx(10.0)  # (110-100)/100*100

    def test_empty_series(self):
        """Empty series should return empty dict."""
        result = compute_asset_reaction(
            pd.Series(dtype=float), datetime(2024, 1, 1), ["5min"]
        )
        assert result == {}

    def test_invalid_window_format_skipped(self):
        """Invalid window formats should be skipped."""
        dates = pd.date_range("2024-01-01 10:00", periods=20, freq="5min")
        prices = pd.Series([100.0] * 20, index=dates)
        release = datetime(2024, 1, 1, 10, 0)

        result = compute_asset_reaction(prices, release, ["invalid", "5min"])

        assert "invalid" not in result
        assert "5min" in result

    def test_day_window(self):
        """Should handle day windows."""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        prices = pd.Series([100.0, 102.0, 104.0, 103.0, 105.0], index=dates)
        release = datetime(2024, 1, 1)

        result = compute_asset_reaction(prices, release, ["1day"])

        assert result["1day"] == pytest.approx(2.0)  # (102-100)/100*100
