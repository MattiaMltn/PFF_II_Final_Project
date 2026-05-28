"""
Unit tests for the Volatility Surface module.

All tests mock get_connection so they run without a live database.
"""

import math
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
# Clean smile mock data for structural and no-arbitrage tests (Step 3)
# Spot ~100, two expirations, three strikes — satisfies all no-arb conditions:
#   - Smile: ATM (K=100) IV is local minimum at both expirations
#   - Calendar spread: T2 IV >= T1 IV at every strike
#   - Butterfly: convexity holds (ATM <= average of wings)
#   - Smoothness: max adjacent jump = 0.03 < 0.10
# ---------------------------------------------------------------------------

_SMILE_ROWS = [
    # T1 — shorter expiration
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 95.0,  "implied_vol": 0.28},
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 100.0, "implied_vol": 0.25},
    {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 105.0, "implied_vol": 0.27},
    # T2 — longer expiration, higher IVs (positive calendar spread)
    {"snapshot_date": "2024-01-15", "expiration": "2024-03-15", "strike": 95.0,  "implied_vol": 0.29},
    {"snapshot_date": "2024-01-15", "expiration": "2024-03-15", "strike": 100.0, "implied_vol": 0.26},
    {"snapshot_date": "2024-01-15", "expiration": "2024-03-15", "strike": 105.0, "implied_vol": 0.28},
]


# ---------------------------------------------------------------------------
# Structural tests (Step 3)
# ---------------------------------------------------------------------------


def test_no_nan_in_implied_vol():
    """Implied vol values must contain no NaN."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    for row in result["surfaces"]:
        assert not math.isnan(row["implied_vol"])


def test_no_inf_in_implied_vol():
    """Implied vol values must contain no infinity."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    for row in result["surfaces"]:
        assert not math.isinf(row["implied_vol"])


def test_implied_vol_in_valid_range():
    """All implied vols must lie in (0.01, 5.0) — no negative or absurd values."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")
    for row in result["surfaces"]:
        assert 0.01 < row["implied_vol"] < 5.0


def test_moneyness_filter_applied():
    """FAILING TEST (finding): surface module must exclude deep OTM/ITM outliers
    (moneyness outside 0.7–1.3 relative to ATM ~100). Currently NOT implemented."""
    rows_with_outliers = _SMILE_ROWS + [
        {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 10.0,  "implied_vol": 0.95},
        {"snapshot_date": "2024-01-15", "expiration": "2024-02-16", "strike": 500.0, "implied_vol": 0.95},
    ]
    with patch(_PATCH, _make_mock_get_connection(rows_with_outliers)):
        result = get_vol_surface_history("AAPL", "call")
    strikes = {row["strike"] for row in result["surfaces"]}
    # Moneyness of 10 and 500 vs ATM ~100 = 0.10 and 5.0 — both outside [0.7, 1.3]
    assert 10.0 not in strikes, "Deep OTM strike not filtered (moneyness=0.10)"
    assert 500.0 not in strikes, "Deep ITM strike not filtered (moneyness=5.00)"


# ---------------------------------------------------------------------------
# No-arbitrage condition tests (Step 3)
# ---------------------------------------------------------------------------


def test_calendar_spread_condition():
    """Calendar spread: IV(T2) >= IV(T1) for T2 > T1 at the same strike."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")

    iv_map: dict = {}
    for row in result["surfaces"]:
        iv_map[(row["strike"], row["expiration"])] = row["implied_vol"]

    expirations = sorted({row["expiration"] for row in result["surfaces"]})
    strikes = sorted({row["strike"] for row in result["surfaces"]})

    for strike in strikes:
        for i in range(len(expirations) - 1):
            iv_t1 = iv_map.get((strike, expirations[i]))
            iv_t2 = iv_map.get((strike, expirations[i + 1]))
            if iv_t1 is not None and iv_t2 is not None:
                assert iv_t2 >= iv_t1 - 1e-6, (
                    f"Calendar spread violated at K={strike}: "
                    f"IV({expirations[i+1]})={iv_t2} < IV({expirations[i]})={iv_t1}"
                )


def test_butterfly_spread_condition():
    """Butterfly convexity: IV(K2) <= 0.5*(IV(K1)+IV(K3)) for K1<K2<K3 (same expiry)."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")

    iv_by_exp: dict = {}
    for row in result["surfaces"]:
        iv_by_exp.setdefault(row["expiration"], {})[row["strike"]] = row["implied_vol"]

    for exp, strikes_iv in iv_by_exp.items():
        sorted_strikes = sorted(strikes_iv.keys())
        for i in range(1, len(sorted_strikes) - 1):
            k1, k2, k3 = sorted_strikes[i - 1], sorted_strikes[i], sorted_strikes[i + 1]
            iv1, iv2, iv3 = strikes_iv[k1], strikes_iv[k2], strikes_iv[k3]
            assert iv2 <= 0.5 * (iv1 + iv3) + 1e-6, (
                f"Butterfly violated at {exp}: IV(K={k2})={iv2} > "
                f"0.5*(IV(K={k1})={iv1} + IV(K={k3})={iv3}) = {0.5*(iv1+iv3):.4f}"
            )


def test_smile_atm_is_local_minimum():
    """Smile shape: ATM implied vol must be <= all wing IVs (no V-shape inversion)."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")

    iv_by_exp: dict = {}
    for row in result["surfaces"]:
        iv_by_exp.setdefault(row["expiration"], {})[row["strike"]] = row["implied_vol"]

    for exp, strikes_iv in iv_by_exp.items():
        sorted_strikes = sorted(strikes_iv.keys())
        ivols = [strikes_iv[k] for k in sorted_strikes]
        atm_idx = len(sorted_strikes) // 2
        for i, iv in enumerate(ivols):
            if i != atm_idx:
                assert ivols[atm_idx] <= iv + 1e-6, (
                    f"Smile inversion at {exp}: ATM IV={ivols[atm_idx]} "
                    f"> wing IV={iv} at K={sorted_strikes[i]}"
                )


def test_smoothness_no_large_jumps():
    """No discontinuous jump > 0.10 in IV between adjacent strikes or expirations."""
    with patch(_PATCH, _make_mock_get_connection(_SMILE_ROWS)):
        result = get_vol_surface_history("AAPL", "call")

    iv_by_exp: dict = {}
    for row in result["surfaces"]:
        iv_by_exp.setdefault(row["expiration"], {})[row["strike"]] = row["implied_vol"]

    # Across strikes (same expiration)
    for exp, strikes_iv in iv_by_exp.items():
        sorted_strikes = sorted(strikes_iv.keys())
        for i in range(len(sorted_strikes) - 1):
            k1, k2 = sorted_strikes[i], sorted_strikes[i + 1]
            jump = abs(strikes_iv[k1] - strikes_iv[k2])
            assert jump <= 0.10, (
                f"Strike jump > 0.10 at {exp}: |IV(K={k1}) - IV(K={k2})| = {jump:.4f}"
            )

    # Across expirations (same strike)
    expirations = sorted(iv_by_exp.keys())
    common_strikes = set.intersection(*[set(iv_by_exp[e].keys()) for e in expirations])
    for strike in common_strikes:
        for i in range(len(expirations) - 1):
            iv1 = iv_by_exp[expirations[i]].get(strike)
            iv2 = iv_by_exp[expirations[i + 1]].get(strike)
            if iv1 is not None and iv2 is not None:
                jump = abs(iv1 - iv2)
                assert jump <= 0.10, (
                    f"Term structure jump > 0.10 at K={strike}: "
                    f"|IV({expirations[i]}) - IV({expirations[i+1]})| = {jump:.4f}"
                )
