"""Tests for backend/data/ — data layer module.

The session-scoped aapl_chain fixture makes one live sync of AAPL call options
from Yahoo Finance.  All subsequent tests read from the database that sync
populated, so the network is touched only once per test run.
"""

import datetime

import pymysql
import pytest

import backend.data.database as db_module
from backend.data.database import get_connection, init_db
from backend.data.market_data import (
    PricingInputs,
    _trading_days_until,
    _validate_expiration,
    get_option_chain,
    get_pricing_inputs,
)
from backend.data.mock_data import MOCK_CHAIN, MOCK_PRICING_INPUTS
from backend.data.save_closing import save_closing_snapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def test_db(monkeypatch):
    """Create a temporary MySQL test database, patch DB_CONFIG, and clean up."""
    base = db_module.DB_CONFIG
    test_db_name = "test_pff_ii_temp"

    admin = pymysql.connect(
        host=base["host"],
        user=base["user"],
        password=base["password"],
        charset="utf8mb4",
    )
    with admin.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{test_db_name}`")
    admin.commit()
    admin.close()

    test_cfg = {**base, "database": test_db_name}
    monkeypatch.setattr(db_module, "DB_CONFIG", test_cfg)

    yield test_cfg

    admin = pymysql.connect(
        host=base["host"],
        user=base["user"],
        password=base["password"],
        charset="utf8mb4",
    )
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{test_db_name}`")
    admin.commit()
    admin.close()


@pytest.fixture(scope="session")
def aapl_chain() -> dict:
    """Sync AAPL call options from Yahoo Finance once per test session."""
    return get_option_chain("AAPL", "call")


@pytest.fixture(scope="session")
def sample_inputs(aapl_chain: dict) -> PricingInputs:
    """PricingInputs for the first available AAPL call contract."""
    exp = aapl_chain["expirations"][0]
    strike = aapl_chain["strikes"][exp][0]
    return get_pricing_inputs("AAPL", exp, "call", strike)


# ── Schema tests ───────────────────────────────────────────────────────────────


def test_init_db_creates_all_tables(test_db) -> None:
    """init_db must create spot_price, option_chain and closing_snapshot."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES"
            " WHERE TABLE_SCHEMA = DATABASE()"
        )
        tables = {r["TABLE_NAME"] for r in cursor.fetchall()}
    assert {"spot_price", "option_chain", "closing_snapshot"}.issubset(tables)


def test_option_chain_schema_columns(test_db) -> None:
    """option_chain must have all required columns."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"
            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'option_chain'"
        )
        cols = {r["COLUMN_NAME"] for r in cursor.fetchall()}
    required = {
        "id", "ticker", "expiration", "strike", "option_type",
        "implied_vol", "bid", "ask", "last_price", "fetched_at",
    }
    assert required.issubset(cols)


def test_closing_snapshot_schema_columns(test_db) -> None:
    """closing_snapshot must have all required columns."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"
            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'closing_snapshot'"
        )
        cols = {r["COLUMN_NAME"] for r in cursor.fetchall()}
    required = {
        "id", "ticker", "snapshot_date", "expiration", "strike",
        "option_type", "implied_vol", "saved_at",
    }
    assert required.issubset(cols)


# ── get_option_chain tests ─────────────────────────────────────────────────────


def test_get_option_chain_returns_dict(aapl_chain: dict) -> None:
    assert isinstance(aapl_chain, dict)


def test_get_option_chain_has_expirations_key(aapl_chain: dict) -> None:
    assert "expirations" in aapl_chain


def test_get_option_chain_has_strikes_key(aapl_chain: dict) -> None:
    assert "strikes" in aapl_chain


def test_get_option_chain_expirations_nonempty(aapl_chain: dict) -> None:
    assert len(aapl_chain["expirations"]) > 0


def test_get_option_chain_expirations_sorted(aapl_chain: dict) -> None:
    exps = aapl_chain["expirations"]
    assert exps == sorted(exps)


def test_get_option_chain_expirations_yyyy_mm_dd(aapl_chain: dict) -> None:
    for exp in aapl_chain["expirations"]:
        # raises ValueError if format is wrong
        datetime.date.fromisoformat(exp)


def test_get_option_chain_all_expirations_in_future(aapl_chain: dict) -> None:
    today = datetime.date.today()
    for exp in aapl_chain["expirations"]:
        assert datetime.date.fromisoformat(exp) > today


def test_get_option_chain_strikes_nonempty(aapl_chain: dict) -> None:
    for exp in aapl_chain["expirations"]:
        assert len(aapl_chain["strikes"][exp]) > 0


def test_get_option_chain_strikes_are_floats(aapl_chain: dict) -> None:
    first_exp = aapl_chain["expirations"][0]
    for s in aapl_chain["strikes"][first_exp]:
        assert isinstance(s, float)


def test_get_option_chain_strikes_are_positive(aapl_chain: dict) -> None:
    first_exp = aapl_chain["expirations"][0]
    for s in aapl_chain["strikes"][first_exp]:
        assert s > 0


def test_get_option_chain_strikes_sorted(aapl_chain: dict) -> None:
    for exp, strikes in aapl_chain["strikes"].items():
        assert strikes == sorted(strikes), f"Strikes not sorted for {exp}"


def test_get_option_chain_invalid_type_raises() -> None:
    with pytest.raises(ValueError):
        get_option_chain("AAPL", "CALL")


def test_get_option_chain_invalid_type_wrong_value_raises() -> None:
    with pytest.raises(ValueError):
        get_option_chain("AAPL", "option")


# ── get_pricing_inputs tests ───────────────────────────────────────────────────


def test_pricing_inputs_is_namedtuple(sample_inputs: PricingInputs) -> None:
    assert isinstance(sample_inputs, PricingInputs)


def test_pricing_inputs_has_seven_fields(sample_inputs: PricingInputs) -> None:
    assert len(sample_inputs) == 7


def test_pricing_inputs_S_positive(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.S > 0


def test_pricing_inputs_K_positive(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.K > 0


def test_pricing_inputs_T_positive(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.T > 0


def test_pricing_inputs_T_at_most_30_years(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.T <= 30


def test_pricing_inputs_T_is_trading_days_over_252(
    sample_inputs: PricingInputs, aapl_chain: dict
) -> None:
    """T must equal trading_days / 252 for the selected expiration."""
    exp = aapl_chain["expirations"][0]
    exp_date = datetime.date.fromisoformat(exp)
    expected_T = _trading_days_until(exp_date) / 252.0
    assert abs(sample_inputs.T - expected_T) < 1e-9


def test_pricing_inputs_r_is_decimal(sample_inputs: PricingInputs) -> None:
    """r must be a decimal between 0 and 1, not a percentage."""
    assert 0.0 < sample_inputs.r < 1.0


def test_pricing_inputs_sigma_nonneg(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.sigma >= 0.0


def test_pricing_inputs_bid_nonneg(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.bid >= 0.0


def test_pricing_inputs_ask_nonneg(sample_inputs: PricingInputs) -> None:
    assert sample_inputs.ask >= 0.0


def test_pricing_inputs_all_floats(sample_inputs: PricingInputs) -> None:
    for field in sample_inputs:
        assert isinstance(field, float)


# ── Validation tests ───────────────────────────────────────────────────────────


def test_past_expiration_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="past"):
        get_pricing_inputs("AAPL", "2020-01-01", "call", 150.0)


def test_today_expiration_raises_valueerror() -> None:
    today = datetime.date.today().isoformat()
    with pytest.raises(ValueError):
        get_pricing_inputs("AAPL", today, "call", 150.0)


def test_invalid_option_type_raises_valueerror() -> None:
    future = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
    with pytest.raises(ValueError):
        get_pricing_inputs("AAPL", future, "CALL", 150.0)


def test_bad_expiration_format_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        _validate_expiration("01-01-2026")


def test_bad_expiration_format_dd_mm_yyyy_raises() -> None:
    with pytest.raises(ValueError):
        _validate_expiration("31/12/2026")


# ── trading days helper tests ─────────────────────────────────────────────────


def test_trading_days_until_positive() -> None:
    future = datetime.date.today() + datetime.timedelta(days=30)
    assert _trading_days_until(future) >= 1


def test_trading_days_until_weekend_skipped() -> None:
    # next Monday from a known Monday: at least 5 trading days in a week
    today = datetime.date.today()
    one_week_out = today + datetime.timedelta(days=7)
    t = _trading_days_until(one_week_out)
    assert 4 <= t <= 7


# ── Mock data tests ────────────────────────────────────────────────────────────


def test_mock_chain_has_expirations() -> None:
    assert "expirations" in MOCK_CHAIN
    assert len(MOCK_CHAIN["expirations"]) > 0


def test_mock_chain_has_strikes() -> None:
    assert "strikes" in MOCK_CHAIN
    for exp in MOCK_CHAIN["expirations"]:
        assert exp in MOCK_CHAIN["strikes"]
        assert len(MOCK_CHAIN["strikes"][exp]) > 0


def test_mock_chain_expirations_sorted() -> None:
    exps = MOCK_CHAIN["expirations"]
    assert exps == sorted(exps)


def test_mock_chain_expirations_in_future() -> None:
    today = datetime.date.today()
    for exp in MOCK_CHAIN["expirations"]:
        assert datetime.date.fromisoformat(exp) > today


def test_mock_pricing_inputs_is_namedtuple() -> None:
    assert isinstance(MOCK_PRICING_INPUTS, PricingInputs)


def test_mock_pricing_inputs_S_positive() -> None:
    assert MOCK_PRICING_INPUTS.S > 0


def test_mock_pricing_inputs_K_positive() -> None:
    assert MOCK_PRICING_INPUTS.K > 0


def test_mock_pricing_inputs_T_in_years() -> None:
    assert 0 < MOCK_PRICING_INPUTS.T <= 30


def test_mock_pricing_inputs_r_decimal() -> None:
    assert 0.0 < MOCK_PRICING_INPUTS.r < 1.0


def test_mock_pricing_inputs_sigma_positive() -> None:
    assert MOCK_PRICING_INPUTS.sigma > 0.0


# ── save_closing tests ─────────────────────────────────────────────────────────


def test_save_closing_snapshot_returns_positive_int(aapl_chain: dict) -> None:
    """After syncing AAPL, the snapshot must write at least one row."""
    count = save_closing_snapshot("AAPL", "call")
    assert isinstance(count, int)
    assert count > 0


def test_save_closing_snapshot_rows_in_db(aapl_chain: dict) -> None:
    """closing_snapshot must contain rows for AAPL after save."""
    save_closing_snapshot("AAPL", "call")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS n FROM closing_snapshot WHERE ticker = 'AAPL'"
        )
        row = cursor.fetchone()
    assert row["n"] > 0


def test_save_closing_invalid_type_raises() -> None:
    with pytest.raises(ValueError):
        save_closing_snapshot("AAPL", "CALL")
