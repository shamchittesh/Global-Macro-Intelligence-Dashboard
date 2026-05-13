"""Unit tests for the MacroDB class."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from lib.db import MacroDB, ValidationError, ConnectionError as DBConnectionError
from lib.models import (
    AssetSource,
    CustomAsset,
    DominantVariableRecord,
    EventCategory,
    ExpectationRecord,
    MacroEvent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    with patch("lib.db.create_client") as mock_create:
        client = MagicMock()
        mock_create.return_value = client
        yield client


@pytest.fixture
def db(mock_supabase_client):
    """Create a MacroDB instance with a mocked client."""
    return MacroDB(url="https://test.supabase.co", key="test-key")


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestMacroDBInit:
    def test_init_with_valid_credentials(self, mock_supabase_client):
        db = MacroDB(url="https://test.supabase.co", key="test-key")
        assert db.connected is True

    def test_init_with_empty_url_raises(self):
        with pytest.raises(ValidationError, match="URL must be a non-empty string"):
            MacroDB(url="", key="test-key")

    def test_init_with_empty_key_raises(self):
        with pytest.raises(ValidationError, match="key must be a non-empty string"):
            MacroDB(url="https://test.supabase.co", key="")

    def test_init_with_none_url_raises(self):
        with pytest.raises(ValidationError):
            MacroDB(url=None, key="test-key")

    def test_init_connection_failure(self):
        with patch("lib.db.create_client", side_effect=Exception("Connection refused")):
            with pytest.raises(DBConnectionError, match="Failed to connect"):
                MacroDB(url="https://test.supabase.co", key="test-key")


# ---------------------------------------------------------------------------
# Dominant Variable tests
# ---------------------------------------------------------------------------


class TestDominantVariable:
    def test_save_dominant_variable_valid(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        db.save_dominant_variable(date(2024, 1, 15), "rates", "Fed hawkish")

        mock_supabase_client.table.assert_called_with("dominant_variables")
        table_mock.insert.assert_called_once_with({
            "record_date": "2024-01-15",
            "variable": "rates",
            "notes": "Fed hawkish",
            "is_manual": True,
        })

    def test_save_dominant_variable_empty_variable_raises(self, db):
        with pytest.raises(ValidationError, match="variable must be a non-empty string"):
            db.save_dominant_variable(date(2024, 1, 15), "", "notes")

    def test_save_dominant_variable_invalid_date_raises(self, db):
        with pytest.raises(ValidationError, match="Date must be a valid date"):
            db.save_dominant_variable("2024-01-15", "rates", "notes")

    def test_get_dominant_variable_history(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[
            {
                "id": "uuid-1",
                "record_date": "2024-01-15",
                "variable": "rates",
                "influence_score": 0.85,
                "notes": "Fed hawkish",
                "is_manual": True,
            }
        ])

        result = db.get_dominant_variable_history(days=30)

        assert len(result) == 1
        assert isinstance(result[0], DominantVariableRecord)
        assert result[0].variable == "rates"
        assert result[0].date == date(2024, 1, 15)
        assert result[0].influence_score == 0.85

    def test_get_dominant_variable_history_invalid_days(self, db):
        with pytest.raises(ValidationError, match="Days must be a positive integer"):
            db.get_dominant_variable_history(days=0)

    def test_get_dominant_variable_history_negative_days(self, db):
        with pytest.raises(ValidationError, match="Days must be a positive integer"):
            db.get_dominant_variable_history(days=-5)


# ---------------------------------------------------------------------------
# Macro Events tests
# ---------------------------------------------------------------------------


class TestMacroEvents:
    def test_save_macro_event_valid(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        event = MacroEvent(
            id=None,
            date=date(2024, 3, 20),
            description="Fed holds rates steady",
            category=EventCategory.MONETARY_POLICY,
            is_custom=True,
        )
        db.save_macro_event(event)

        table_mock.insert.assert_called_once_with({
            "event_date": "2024-03-20",
            "description": "Fed holds rates steady",
            "category": "monetary_policy",
            "is_custom": True,
        })

    def test_save_macro_event_empty_description_raises(self, db):
        event = MacroEvent(
            id=None,
            date=date(2024, 3, 20),
            description="",
            category=EventCategory.MONETARY_POLICY,
        )
        with pytest.raises(ValidationError, match="description must be a non-empty string"):
            db.save_macro_event(event)

    def test_save_macro_event_description_too_long_raises(self, db):
        event = MacroEvent(
            id=None,
            date=date(2024, 3, 20),
            description="x" * 501,
            category=EventCategory.MONETARY_POLICY,
        )
        with pytest.raises(ValidationError, match="500 characters or fewer"):
            db.save_macro_event(event)

    def test_save_macro_event_invalid_category_raises(self, db):
        event = MacroEvent(
            id=None,
            date=date(2024, 3, 20),
            description="Test event",
            category="invalid",
        )
        with pytest.raises(ValidationError, match="Category must be an EventCategory"):
            db.save_macro_event(event)

    def test_get_macro_events_with_category_filter(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[
            {
                "id": "uuid-1",
                "event_date": "2024-03-20",
                "description": "Fed holds rates",
                "category": "monetary_policy",
                "is_custom": False,
            }
        ])

        result = db.get_macro_events(category="monetary_policy")

        assert len(result) == 1
        assert result[0].category == EventCategory.MONETARY_POLICY

    def test_get_macro_events_invalid_category_raises(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock

        with pytest.raises(ValidationError, match="Invalid category"):
            db.get_macro_events(category="invalid_category")

    def test_get_macro_events_with_date_range(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.lte.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        result = db.get_macro_events(start=date(2024, 1, 1), end=date(2024, 3, 31))

        assert result == []
        table_mock.gte.assert_called_once_with("event_date", "2024-01-01")
        table_mock.lte.assert_called_once_with("event_date", "2024-03-31")


# ---------------------------------------------------------------------------
# Expectations tests
# ---------------------------------------------------------------------------


class TestExpectations:
    def test_save_expectation_valid(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        expectation = ExpectationRecord(
            id=None,
            release_date=date(2024, 2, 13),
            indicator="CPI",
            expected_value=3.1,
            actual_value=3.2,
            surprise_magnitude=0.5,
            asset_reactions={"^GSPC": {"5min": -0.3, "1hr": -0.5}},
        )
        db.save_expectation(expectation)

        table_mock.insert.assert_called_once_with({
            "release_date": "2024-02-13",
            "indicator": "CPI",
            "expected_value": 3.1,
            "actual_value": 3.2,
            "surprise_magnitude": 0.5,
            "asset_reactions": {"^GSPC": {"5min": -0.3, "1hr": -0.5}},
        })

    def test_save_expectation_empty_indicator_raises(self, db):
        expectation = ExpectationRecord(
            id=None,
            release_date=date(2024, 2, 13),
            indicator="",
            expected_value=3.1,
            actual_value=None,
            surprise_magnitude=None,
        )
        with pytest.raises(ValidationError, match="indicator must be a non-empty string"):
            db.save_expectation(expectation)

    def test_save_expectation_non_numeric_expected_raises(self, db):
        expectation = ExpectationRecord(
            id=None,
            release_date=date(2024, 2, 13),
            indicator="CPI",
            expected_value="not a number",
            actual_value=None,
            surprise_magnitude=None,
        )
        with pytest.raises(ValidationError, match="expected_value must be a numeric"):
            db.save_expectation(expectation)

    def test_get_expectations_history_with_indicator(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[
            {
                "id": "uuid-1",
                "release_date": "2024-02-13",
                "indicator": "CPI",
                "expected_value": 3.1,
                "actual_value": 3.2,
                "surprise_magnitude": 0.5,
                "asset_reactions": None,
            }
        ])

        result = db.get_expectations_history(indicator="CPI")

        assert len(result) == 1
        assert isinstance(result[0], ExpectationRecord)
        assert result[0].indicator == "CPI"
        assert result[0].expected_value == 3.1

    def test_get_expectations_history_empty_indicator_raises(self, db):
        with pytest.raises(ValidationError, match="Indicator filter must be a non-empty"):
            db.get_expectations_history(indicator="  ")


# ---------------------------------------------------------------------------
# Custom Assets tests
# ---------------------------------------------------------------------------


class TestCustomAssets:
    def test_save_custom_asset_valid(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        db.save_custom_asset("AAPL", "Apple Inc")

        table_mock.insert.assert_called_once()
        call_data = table_mock.insert.call_args[0][0]
        assert call_data["symbol"] == "AAPL"
        assert call_data["display_name"] == "Apple Inc"
        assert call_data["source"] == "yfinance"

    def test_save_custom_asset_empty_symbol_raises(self, db):
        with pytest.raises(ValidationError, match="symbol must be a non-empty string"):
            db.save_custom_asset("", "Apple")

    def test_save_custom_asset_empty_name_raises(self, db):
        with pytest.raises(ValidationError, match="name must be a non-empty string"):
            db.save_custom_asset("AAPL", "")

    def test_save_custom_asset_invalid_symbol_raises(self, db):
        with pytest.raises(ValidationError, match="Invalid ticker symbol"):
            db.save_custom_asset("AAPL@#$", "Apple")

    def test_save_custom_asset_valid_special_chars(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])

        # These should all be valid ticker formats
        db.save_custom_asset("^GSPC", "S&P 500")
        db.save_custom_asset("DX-Y.NYB", "DXY")
        db.save_custom_asset("GC=F", "Gold Futures")

    def test_get_custom_assets(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[
            {
                "symbol": "AAPL",
                "display_name": "Apple Inc",
                "source": "yfinance",
                "added_date": "2024-01-10",
            }
        ])

        result = db.get_custom_assets()

        assert len(result) == 1
        assert isinstance(result[0], CustomAsset)
        assert result[0].symbol == "AAPL"
        assert result[0].source == AssetSource.YFINANCE


# ---------------------------------------------------------------------------
# Connection failure / graceful degradation tests
# ---------------------------------------------------------------------------


class TestConnectionFailure:
    def test_insert_failure_caches_data(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.execute.side_effect = Exception("Network error")

        with patch("lib.db.st.session_state", {}) as mock_state:
            with pytest.raises(DBConnectionError, match="Failed to save"):
                db.save_dominant_variable(date(2024, 1, 15), "rates", "notes")

            # Verify data was cached
            assert "_macrodb_pending_dominant_variables" in mock_state
            assert len(mock_state["_macrodb_pending_dominant_variables"]) == 1

    def test_read_failure_returns_empty_list(self, db, mock_supabase_client):
        table_mock = MagicMock()
        mock_supabase_client.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.side_effect = Exception("Network error")

        with patch("lib.db.st.session_state", {}):
            result = db.get_dominant_variable_history(days=30)
            assert result == []
