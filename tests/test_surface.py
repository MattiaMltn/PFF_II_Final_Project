"""
Unit tests for the Volatility Surface module.

All tests mock get_connection so they run without a live database.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backend.surface.surface import get_surface_by_date, get_vol_surface_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_get_connection(rows):
    """Return a drop-in replacement for get_connection that yields mock rows."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cursor

    @contextmanager
    def mock_get_connection():
        yield conn

    return mock_get_connection


# Shared mock data for get_vol_surface_history tests
_HISTORY_ROWS = [
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 150.0, "implied_vol": 0.25},
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 155.0, "implied_vol": 0.27},
    {"snapshot_date": "2024-01-16", "expiration": "2024-03-15", "strike": 150.0, "implied_vol": 0.26},
]

# Shared mock data for get_surface_by_date tests
_DATE_ROWS = [
    {"expiration": "2024-02-16", "strike": 150.0, "implied_vol": 0.25},
    {"expiration": "2024-02-16", "strike": 155.0, "implied_vol": 0.27},
    {"expiration": "2024-03-15", "strike": 160.0, "implied_vol": 0.30},
]

_PATCH = "backend.surface.surface.get_connection"


# ---------------------------------------------------------------------------
# Tests for get_vol_surface_history
# ---------------------------------------------------------------------------


def test_returns_correct_keys():
    """Output dict must always have 'dates' and 'surfaces' keys."""
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert "dates" in result
    assert "surfaces" in result


def test_returns_lists():
    """Both values must be lists."""
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert isinstance(result["dates"], list)
    assert isinstance(result["surfaces"], list)


def test_empty_result_for_unknown_ticker():
    """Unknown ticker must return empty dates and surfaces."""
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_vol_surface_history("FAKEXYZ", "call")
    assert result["dates"] == []
    assert result["surfaces"] == []


def test_surface_rows_have_correct_keys():
    """Each surface row must contain the four expected fields."""
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert result["surfaces"]
    row = result["surfaces"][0]
    assert "snapshot_date" in row
    assert "expiration" in row
    assert "strike" in row
    assert "implied_vol" in row


def test_dates_are_sorted():
    """Dates list must be in ascending order."""
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert result["dates"] == sorted(result["dates"])


def test_ticker_is_case_insensitive():
    """'aapl' and 'AAPL' must return the same result."""
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        upper = get_vol_surface_history("AAPL", "call")
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        lower = get_vol_surface_history("aapl", "call")
    assert upper["dates"] == lower["dates"]
    assert len(upper["surfaces"]) == len(lower["surfaces"])


# ---------------------------------------------------------------------------
# Tests for get_surface_by_date
# ---------------------------------------------------------------------------


def test_surface_by_date_returns_correct_keys():
    """Output dict must always have 'expiration', 'strike', 'implied_vol' keys."""
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    assert "expiration" in result
    assert "strike" in result
    assert "implied_vol" in result


def test_surface_by_date_unknown_date_returns_empty():
    """A date with no data must return three empty lists."""
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("AAPL", "call", "2099-01-01")
    assert result["expiration"] == []
    assert result["strike"] == []
    assert result["implied_vol"] == []


def test_surface_by_date_unknown_ticker_returns_empty():
    """An unknown ticker must return three empty lists regardless of date."""
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("FAKEXYZ", "call", "2024-01-15")
    assert result["expiration"] == []
    assert result["strike"] == []
    assert result["implied_vol"] == []


def test_surface_by_date_lists_are_parallel():
    """All three returned lists must have the same length."""
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    length = len(_DATE_ROWS)
    assert len(result["expiration"]) == length
    assert len(result["strike"]) == length
    assert len(result["implied_vol"]) == length


def test_surface_by_date_ticker_case_insensitive():
    """'aapl' and 'AAPL' must return identical results for the same date."""
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        upper = get_surface_by_date("AAPL", "call", "2024-01-15")
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        lower = get_surface_by_date("aapl", "call", "2024-01-15")
    assert upper == lower


def test_surface_by_date_returns_correct_values():
    """Returned lists must contain the correct values from the data source."""
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    assert result["expiration"] == ["2024-02-16", "2024-02-16", "2024-03-15"]
    assert result["strike"] == [150.0, 155.0, 160.0]
    assert result["implied_vol"] == [0.25, 0.27, 0.30]
# ---------------------------------------------------------------------------
# Integration tests (require live Supabase connection)
# Run with: pytest -v -m integration
# Skip with: pytest -v -m "not integration"
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_get_vol_surface_history_returns_data():
    """Live DB: get_vol_surface_history must return non-empty data for AAPL."""
    result = get_vol_surface_history("AAPL", "call")
    assert "dates" in result
    assert "surfaces" in result
    assert len(result["dates"]) > 0, "Expected at least one snapshot date in Supabase"
    assert len(result["surfaces"]) > 0, "Expected at least one row in closing_snapshot"


@pytest.mark.integration
def test_integration_surface_rows_structure():
    """Live DB: every row returned must have the four required fields."""
    result = get_vol_surface_history("AAPL", "call")
    assert result["surfaces"], "No rows returned from live DB"
    for row in result["surfaces"]:
        assert "snapshot_date" in row
        assert "expiration" in row
        assert "strike" in row
        assert "implied_vol" in row


@pytest.mark.integration
def test_integration_get_surface_by_date_returns_data():
    """Live DB: get_surface_by_date must return data for the first available date."""
    history = get_vol_surface_history("AAPL", "call")
    assert history["dates"], "No dates available in live DB"
    first_date = history["dates"][0]
    result = get_surface_by_date("AAPL", "call", first_date)
    assert len(result["expiration"]) > 0
    assert len(result["strike"]) > 0
    assert len(result["implied_vol"]) > 0


@pytest.mark.integration
def test_integration_unknown_ticker_returns_empty():
    """Live DB: unknown ticker must return empty lists, not crash."""
    result = get_vol_surface_history("FAKEXYZ999", "call")
    assert result["dates"] == []
    assert result["surfaces"] == []