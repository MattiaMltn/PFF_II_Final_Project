"""
Unit tests for the Volatility Surface module.
"""

import pytest
from backend.surface.surface import get_vol_surface_history, build_surface_grid


def test_returns_correct_keys():
    """Output dict must always have 'dates' and 'surfaces' keys."""
    result = get_vol_surface_history("AAPL", "call")
    assert "dates" in result
    assert "surfaces" in result


def test_returns_lists():
    """Both values must be lists."""
    result = get_vol_surface_history("AAPL", "call")
    assert isinstance(result["dates"], list)
    assert isinstance(result["surfaces"], list)


def test_empty_result_for_unknown_ticker():
    """Unknown ticker must return empty dates and surfaces."""
    result = get_vol_surface_history("FAKEXYZ", "call")
    assert result["dates"] == []
    assert result["surfaces"] == []


def test_surface_rows_have_correct_keys():
    """Each surface row must contain the four expected fields."""
    result = get_vol_surface_history("AAPL", "call")
    if result["surfaces"]:
        row = result["surfaces"][0]
        assert "snapshot_date" in row
        assert "expiration" in row
        assert "strike" in row
        assert "implied_vol" in row


def test_dates_are_sorted():
    """Dates list must be in ascending order."""
    result = get_vol_surface_history("AAPL", "call")
    assert result["dates"] == sorted(result["dates"])


def test_ticker_is_case_insensitive():
    """'aapl' and 'AAPL' must return the same result."""
    upper = get_vol_surface_history("AAPL", "call")
    lower = get_vol_surface_history("aapl", "call")
    assert upper["dates"] == lower["dates"]
    assert len(upper["surfaces"]) == len(lower["surfaces"])


def test_build_surface_grid_returns_none_for_unknown_ticker():
    """build_surface_grid must return None when no data exists."""
    result = build_surface_grid("FAKEXYZ", "call", "2026-05-07")
    assert result is None


def test_build_surface_grid_returns_correct_keys():
    """build_surface_grid must return dict with K_grid, T_grid, IV_mesh."""
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


def test_build_surface_grid_shapes_match():
    """K_grid, T_grid and IV_mesh must all have the same shape."""
    history = get_vol_surface_history("AAPL", "call")
    if not history["dates"]:
        pytest.skip("No data in database")
    date = history["dates"][0]
    result = build_surface_grid("AAPL", "call", date)
    if result is not None:
        assert len(result["K_grid"]) == len(result["T_grid"]) == len(result["IV_mesh"])
        assert len(result["K_grid"][0]) == len(result["T_grid"][0]) == len(result["IV_mesh"][0])


def test_build_surface_grid_date_matches():
    """snapshot_date in result must match the requested date."""
    history = get_vol_surface_history("AAPL", "call")
    if not history["dates"]:
        pytest.skip("No data in database")
    date = history["dates"][0]
    result = build_surface_grid("AAPL", "call", date)
    if result is not None:
        assert result["snapshot_date"] == date