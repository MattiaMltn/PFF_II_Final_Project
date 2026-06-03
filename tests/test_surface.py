"""
Unit tests for the Volatility Surface module.

All tests mock get_connection so they run without a live database.
Integration tests (marked with @pytest.mark.integration) require a live Supabase connection.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backend.surface.surface import (
    get_vol_surface_history,
    get_surface_by_date,
    build_surface_grid,
)


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


_HISTORY_ROWS = [
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 150.0, "implied_vol": 0.25},
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 155.0, "implied_vol": 0.27},
    {"snapshot_date": "2024-01-16", "expiration": "2024-03-15", "strike": 150.0, "implied_vol": 0.26},
]

_DATE_ROWS = [
    {"expiration": "2024-02-16", "strike": 150.0, "implied_vol": 0.25},
    {"expiration": "2024-02-16", "strike": 155.0, "implied_vol": 0.27},
    {"expiration": "2024-03-15", "strike": 160.0, "implied_vol": 0.30},
]

_GRID_ROWS = [
    {"expiration": "2024-04-19", "strike": 140.0, "implied_vol": 0.22},
    {"expiration": "2024-04-19", "strike": 150.0, "implied_vol": 0.25},
    {"expiration": "2024-04-19", "strike": 160.0, "implied_vol": 0.28},
    {"expiration": "2024-06-21", "strike": 140.0, "implied_vol": 0.20},
    {"expiration": "2024-06-21", "strike": 150.0, "implied_vol": 0.23},
    {"expiration": "2024-06-21", "strike": 160.0, "implied_vol": 0.26},
]

_PATCH = "backend.surface.surface.get_connection"


# ---------------------------------------------------------------------------
# Tests for get_vol_surface_history
# ---------------------------------------------------------------------------

def test_returns_correct_keys():
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert "dates" in result
    assert "surfaces" in result


def test_returns_lists():
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert isinstance(result["dates"], list)
    assert isinstance(result["surfaces"], list)


def test_empty_result_for_unknown_ticker():
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_vol_surface_history("FAKEXYZ", "call")
    assert result["dates"] == []
    assert result["surfaces"] == []


def test_surface_rows_have_correct_keys():
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    row = result["surfaces"][0]
    assert "snapshot_date" in row
    assert "expiration" in row
    assert "strike" in row
    assert "implied_vol" in row


def test_dates_are_sorted():
    with patch(_PATCH, _make_mock_get_connection(_HISTORY_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    assert result["dates"] == sorted(result["dates"])


def test_ticker_is_case_insensitive():
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
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    assert "expiration" in result
    assert "strike" in result
    assert "implied_vol" in result


def test_surface_by_date_unknown_date_returns_empty():
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("AAPL", "call", "2099-01-01")
    assert result["expiration"] == []
    assert result["strike"] == []
    assert result["implied_vol"] == []


def test_surface_by_date_unknown_ticker_returns_empty():
    with patch(_PATCH, _make_mock_get_connection([])):
        result = get_surface_by_date("FAKEXYZ", "call", "2024-01-15")
    assert result["expiration"] == []
    assert result["strike"] == []
    assert result["implied_vol"] == []


def test_surface_by_date_lists_are_parallel():
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    length = len(_DATE_ROWS)
    assert len(result["expiration"]) == length
    assert len(result["strike"]) == length
    assert len(result["implied_vol"]) == length


def test_surface_by_date_ticker_case_insensitive():
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        upper = get_surface_by_date("AAPL", "call", "2024-01-15")
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        lower = get_surface_by_date("aapl", "call", "2024-01-15")
    assert upper == lower


def test_surface_by_date_returns_correct_values():
    with patch(_PATCH, _make_mock_get_connection(_DATE_ROWS)):
        result = get_surface_by_date("AAPL", "call", "2024-01-15")
    assert result["expiration"] == ["2024-02-16", "2024-02-16", "2024-03-15"]
    assert result["strike"] == [150.0, 155.0, 160.0]
    assert result["implied_vol"] == [0.25, 0.27, 0.30]


# ---------------------------------------------------------------------------
# Tests for build_surface_grid
# ---------------------------------------------------------------------------

def test_build_surface_grid_returns_none_for_empty_data():
    with patch(_PATCH, _make_mock_get_connection([])):
        result = build_surface_grid("FAKEXYZ", "call", "2024-01-15")
    assert result is None


def test_build_surface_grid_returns_correct_keys():
    with patch(_PATCH, _make_mock_get_connection(_GRID_ROWS)):
        result = build_surface_grid("AAPL", "call", "2024-01-15")
    assert result is not None
    assert "K_grid" in result
    assert "T_grid" in result
    assert "IV_mesh" in result
    assert "snapshot_date" in result


def test_build_surface_grid_date_matches():
    with patch(_PATCH, _make_mock_get_connection(_GRID_ROWS)):
        result = build_surface_grid("AAPL", "call", "2024-01-15")
    assert result is not None
    assert result["snapshot_date"] == "2024-01-15"


def test_build_surface_grid_shapes_match():
    with patch(_PATCH, _make_mock_get_connection(_GRID_ROWS)):
        result = build_surface_grid("AAPL", "call", "2024-01-15")
    assert result is not None
    assert len(result["K_grid"]) == len(result["T_grid"]) == len(result["IV_mesh"])


# ---------------------------------------------------------------------------
# Integration tests (require live Supabase connection)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_build_surface_grid_returns_none_for_unknown_ticker_live():
    result = build_surface_grid("FAKEXYZ", "call", "2026-05-07")
    assert result is None


@pytest.mark.integration
def test_build_surface_grid_live_correct_keys():
    history = get_vol_surface_history("AAPL", "call")
    if not history["dates"]:
        pytest.skip("No data in database")
    date = history["dates"][0]
    result = build_surface_grid("AAPL", "call", date)
    if result is not None:
        assert "K_grid" in result
        assert "T_grid" in result
        assert "IV_mesh" in result
        assert "snapshot_date" in result


@pytest.mark.integration
def test_build_surface_grid_live_shapes_match():
    history = get_vol_surface_history("AAPL", "call")
    if not history["dates"]:
        pytest.skip("No data in database")
    date = history["dates"][0]
    result = build_surface_grid("AAPL", "call", date)
    if result is not None:
        assert len(result["K_grid"]) == len(result["T_grid"]) == len(result["IV_mesh"])


@pytest.mark.integration
def test_build_surface_grid_live_date_matches():
    history = get_vol_surface_history("AAPL", "call")
    if not history["dates"]:
        pytest.skip("No data in database")
    date = history["dates"][0]
    result = build_surface_grid("AAPL", "call", date)
    if result is not None:
        assert result["snapshot_date"] == date