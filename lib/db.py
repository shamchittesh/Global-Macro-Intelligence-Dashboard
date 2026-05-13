"""Supabase database interface for user-generated data."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import streamlit as st
from supabase import Client, create_client

from lib.models import (
    AssetSource,
    CustomAsset,
    DominantVariableRecord,
    EventCategory,
    ExpectationRecord,
    MacroEvent,
)

logger = logging.getLogger(__name__)


class MacroDBError(Exception):
    """Base exception for MacroDB operations."""


class ValidationError(MacroDBError):
    """Raised when input validation fails."""


class ConnectionError(MacroDBError):
    """Raised when Supabase connection fails."""


class MacroDB:
    """Supabase database interface for user-generated data.

    Handles all persistence operations for macro events, dominant variable
    selections, expectation records, and custom assets. Provides input
    validation and graceful degradation on connection failures.
    """

    def __init__(self, url: str, key: str) -> None:
        """Initialize Supabase client.

        Args:
            url: Supabase project URL.
            key: Supabase anonymous/service key.

        Raises:
            ConnectionError: If the Supabase client cannot be created.
        """
        if not url or not isinstance(url, str):
            raise ValidationError("Supabase URL must be a non-empty string.")
        if not key or not isinstance(key, str):
            raise ValidationError("Supabase key must be a non-empty string.")

        try:
            self._client: Client = create_client(url, key)
            self._connected = True
        except Exception as e:
            logger.error("Failed to create Supabase client: %s", e)
            self._connected = False
            raise ConnectionError(f"Failed to connect to Supabase: {e}") from e

    @property
    def connected(self) -> bool:
        """Whether the database connection is active."""
        return self._connected

    # -------------------------------------------------------------------------
    # Dominant Variable
    # -------------------------------------------------------------------------

    def save_dominant_variable(
        self, record_date: date, variable: str, notes: str = ""
    ) -> None:
        """Save a dominant variable selection for a given date.

        Args:
            record_date: The date for the selection.
            variable: The dominant variable name (e.g., "rates", "USD").
            notes: Optional user reasoning.

        Raises:
            ValidationError: If inputs are invalid.
            ConnectionError: If the database is unreachable.
        """
        self._validate_date(record_date)
        self._validate_non_empty_string(variable, "variable")
        if not isinstance(notes, str):
            raise ValidationError("Notes must be a string.")

        data = {
            "record_date": record_date.isoformat(),
            "variable": variable.strip(),
            "notes": notes.strip(),
            "is_manual": True,
        }

        self._execute_insert("dominant_variables", data)

    def get_dominant_variable_history(self, days: int = 30) -> list[DominantVariableRecord]:
        """Retrieve dominant variable history for the past N days.

        Args:
            days: Number of days of history to retrieve (default 30).

        Returns:
            List of DominantVariableRecord sorted by date descending.
        """
        if not isinstance(days, int) or days <= 0:
            raise ValidationError("Days must be a positive integer.")

        start_date = date.today() - timedelta(days=days)

        try:
            response = (
                self._client.table("dominant_variables")
                .select("*")
                .gte("record_date", start_date.isoformat())
                .order("record_date", desc=True)
                .execute()
            )
            return [self._row_to_dominant_variable(row) for row in response.data]
        except Exception as e:
            logger.error("Failed to fetch dominant variable history: %s", e)
            return self._get_cached("dominant_variables", [])

    # -------------------------------------------------------------------------
    # Macro Events
    # -------------------------------------------------------------------------

    def save_macro_event(self, event: MacroEvent) -> None:
        """Save a macro event to the database.

        Args:
            event: The MacroEvent to persist.

        Raises:
            ValidationError: If the event data is invalid.
            ConnectionError: If the database is unreachable.
        """
        if not isinstance(event, MacroEvent):
            raise ValidationError("Event must be a MacroEvent instance.")
        self._validate_date(event.date)
        self._validate_non_empty_string(event.description, "description")
        if len(event.description) > 500:
            raise ValidationError("Event description must be 500 characters or fewer.")
        self._validate_category(event.category)

        data = {
            "event_date": event.date.isoformat(),
            "description": event.description.strip(),
            "category": event.category.value,
            "is_custom": event.is_custom,
        }

        self._execute_insert("macro_events", data)

    def get_macro_events(
        self,
        category: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MacroEvent]:
        """Retrieve macro events with optional category and date filtering.

        Args:
            category: Optional EventCategory value string to filter by.
            start: Optional start date (inclusive).
            end: Optional end date (inclusive).

        Returns:
            List of MacroEvent sorted by date descending.
        """
        try:
            query = self._client.table("macro_events").select("*")

            if category is not None:
                # Validate category filter
                valid_categories = [c.value for c in EventCategory]
                if category not in valid_categories:
                    raise ValidationError(
                        f"Invalid category '{category}'. Must be one of: {valid_categories}"
                    )
                query = query.eq("category", category)

            if start is not None:
                query = query.gte("event_date", start.isoformat())
            if end is not None:
                query = query.lte("event_date", end.isoformat())

            response = query.order("event_date", desc=True).execute()
            return [self._row_to_macro_event(row) for row in response.data]
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Failed to fetch macro events: %s", e)
            return self._get_cached("macro_events", [])

    # -------------------------------------------------------------------------
    # Expectations
    # -------------------------------------------------------------------------

    def save_expectation(self, expectation: ExpectationRecord) -> None:
        """Save an expectation record to the database.

        Args:
            expectation: The ExpectationRecord to persist.

        Raises:
            ValidationError: If the expectation data is invalid.
            ConnectionError: If the database is unreachable.
        """
        if not isinstance(expectation, ExpectationRecord):
            raise ValidationError("Expectation must be an ExpectationRecord instance.")
        self._validate_date(expectation.release_date)
        self._validate_non_empty_string(expectation.indicator, "indicator")
        self._validate_numeric(expectation.expected_value, "expected_value")

        if expectation.actual_value is not None:
            self._validate_numeric(expectation.actual_value, "actual_value")
        if expectation.surprise_magnitude is not None:
            self._validate_numeric(expectation.surprise_magnitude, "surprise_magnitude")

        data = {
            "release_date": expectation.release_date.isoformat(),
            "indicator": expectation.indicator.strip(),
            "expected_value": expectation.expected_value,
            "actual_value": expectation.actual_value,
            "surprise_magnitude": expectation.surprise_magnitude,
            "asset_reactions": expectation.asset_reactions,
        }

        self._execute_insert("expectations", data)

    def get_expectations_history(
        self, indicator: str | None = None
    ) -> list[ExpectationRecord]:
        """Retrieve expectation records with optional indicator filtering.

        Args:
            indicator: Optional indicator name to filter by (e.g., "CPI", "NFP").

        Returns:
            List of ExpectationRecord sorted by release date descending.
        """
        try:
            query = self._client.table("expectations").select("*")

            if indicator is not None:
                if not isinstance(indicator, str) or not indicator.strip():
                    raise ValidationError("Indicator filter must be a non-empty string.")
                query = query.eq("indicator", indicator.strip())

            response = query.order("release_date", desc=True).execute()
            return [self._row_to_expectation(row) for row in response.data]
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Failed to fetch expectations history: %s", e)
            return self._get_cached("expectations", [])

    # -------------------------------------------------------------------------
    # Custom Assets
    # -------------------------------------------------------------------------

    def save_custom_asset(self, symbol: str, name: str) -> None:
        """Save a custom asset ticker.

        Args:
            symbol: The ticker symbol (e.g., "AAPL", "^GSPC").
            name: Display name for the asset.

        Raises:
            ValidationError: If inputs are invalid.
            ConnectionError: If the database is unreachable.
        """
        self._validate_non_empty_string(symbol, "symbol")
        self._validate_non_empty_string(name, "name")
        self._validate_ticker_symbol(symbol)

        data = {
            "symbol": symbol.strip().upper(),
            "display_name": name.strip(),
            "source": AssetSource.YFINANCE.value,
            "added_date": date.today().isoformat(),
        }

        self._execute_insert("custom_assets", data)

    def get_custom_assets(self) -> list[CustomAsset]:
        """Retrieve all custom assets.

        Returns:
            List of CustomAsset sorted by added date descending.
        """
        try:
            response = (
                self._client.table("custom_assets")
                .select("*")
                .order("added_date", desc=True)
                .execute()
            )
            return [self._row_to_custom_asset(row) for row in response.data]
        except Exception as e:
            logger.error("Failed to fetch custom assets: %s", e)
            return self._get_cached("custom_assets", [])

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _execute_insert(self, table: str, data: dict) -> None:
        """Execute an insert operation with error handling.

        On failure, caches the data in session state for later retry.
        """
        try:
            self._client.table(table).insert(data).execute()
        except Exception as e:
            logger.error("Failed to insert into %s: %s", table, e)
            self._connected = False
            self._cache_pending_write(table, data)
            raise ConnectionError(
                f"Failed to save to {table}. Data cached for retry."
            ) from e

    def _cache_pending_write(self, table: str, data: dict) -> None:
        """Cache a failed write in Streamlit session state for later retry."""
        cache_key = f"_macrodb_pending_{table}"
        if cache_key not in st.session_state:
            st.session_state[cache_key] = []
        st.session_state[cache_key].append(data)

    def _get_cached(self, table: str, default: list):
        """Return cached data from session state if available."""
        cache_key = f"_macrodb_cache_{table}"
        return st.session_state.get(cache_key, default)

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_non_empty_string(value: object, field_name: str) -> None:
        """Validate that a value is a non-empty string."""
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be a non-empty string.")

    @staticmethod
    def _validate_date(value: object) -> None:
        """Validate that a value is a valid date instance."""
        if not isinstance(value, date):
            raise ValidationError("Date must be a valid date instance.")

    @staticmethod
    def _validate_numeric(value: object, field_name: str) -> None:
        """Validate that a value is numeric (int or float)."""
        if not isinstance(value, (int, float)):
            raise ValidationError(f"{field_name} must be a numeric value.")

    @staticmethod
    def _validate_category(category: object) -> None:
        """Validate that a category is a valid EventCategory."""
        if not isinstance(category, EventCategory):
            raise ValidationError(
                f"Category must be an EventCategory enum value. Got: {type(category)}"
            )

    @staticmethod
    def _validate_ticker_symbol(symbol: str) -> None:
        """Validate ticker symbol format.

        Allows alphanumeric characters and special chars: ^ - . =
        """
        import re

        pattern = r"^[A-Za-z0-9\^\-\.=]+$"
        if not re.match(pattern, symbol.strip()):
            raise ValidationError(
                f"Invalid ticker symbol '{symbol}'. "
                "Must be alphanumeric with allowed special characters (^, -, ., =)."
            )

    # -------------------------------------------------------------------------
    # Row-to-model converters
    # -------------------------------------------------------------------------

    @staticmethod
    def _row_to_dominant_variable(row: dict) -> DominantVariableRecord:
        """Convert a database row to a DominantVariableRecord."""
        return DominantVariableRecord(
            id=row.get("id"),
            date=date.fromisoformat(row["record_date"]),
            variable=row["variable"],
            influence_score=row.get("influence_score"),
            notes=row.get("notes", ""),
            is_manual=row.get("is_manual", False),
        )

    @staticmethod
    def _row_to_macro_event(row: dict) -> MacroEvent:
        """Convert a database row to a MacroEvent."""
        return MacroEvent(
            id=row.get("id"),
            date=date.fromisoformat(row["event_date"]),
            description=row["description"],
            category=EventCategory(row["category"]),
            is_custom=row.get("is_custom", False),
        )

    @staticmethod
    def _row_to_expectation(row: dict) -> ExpectationRecord:
        """Convert a database row to an ExpectationRecord."""
        return ExpectationRecord(
            id=row.get("id"),
            release_date=date.fromisoformat(row["release_date"]),
            indicator=row["indicator"],
            expected_value=row["expected_value"],
            actual_value=row.get("actual_value"),
            surprise_magnitude=row.get("surprise_magnitude"),
            asset_reactions=row.get("asset_reactions"),
        )

    @staticmethod
    def _row_to_custom_asset(row: dict) -> CustomAsset:
        """Convert a database row to a CustomAsset."""
        return CustomAsset(
            symbol=row["symbol"],
            display_name=row["display_name"],
            source=AssetSource(row["source"]),
            added_date=date.fromisoformat(row["added_date"]),
        )


def get_db() -> MacroDB | None:
    """Get or create a MacroDB instance from Streamlit secrets.

    Returns:
        MacroDB instance, or None if connection fails (read-only mode).
    """
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return MacroDB(url=url, key=key)
    except KeyError:
        logger.warning("Supabase credentials not found in Streamlit secrets.")
        return None
    except ConnectionError as e:
        logger.error("Database connection failed: %s", e)
        return None
