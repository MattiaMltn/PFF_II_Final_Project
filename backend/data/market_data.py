"""Public interface for the data layer.

Other modules import only from this file:

    from backend.data.market_data import get_option_chain, get_pricing_inputs
"""

import datetime
import logging
import math
from typing import NamedTuple

import yfinance as yf

from backend.data.database import get_connection, init_db
from backend.data.sync import sync_ticker

logger = logging.getLogger(__name__)

_RISK_FREE_TICKER = "^IRX"  # 13-week US T-bill annualised yield


class PricingInputs(NamedTuple):
    """All inputs required by the Pricing Engine for a single option contract."""

    S: float      # spot price
    K: float      # strike price
    T: float      # time to expiry in years  (trading_days / 252)
    r: float      # risk-free rate as decimal (e.g. 0.045)
    sigma: float  # implied volatility as decimal
    bid: float    # option bid price
    ask: float    # option ask price


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_option_type(option_type: str) -> None:
    """Raise ValueError if option_type is not 'call' or 'put'."""
    if option_type not in ("call", "put"):
        raise ValueError(
            f"option_type must be 'call' or 'put', got {option_type!r}"
        )


def _validate_expiration(expiration: str) -> datetime.date:
    """Parse and validate an expiration string.

    Args:
        expiration: Date string in YYYY-MM-DD format.

    Returns:
        Parsed datetime.date.

    Raises:
        ValueError: If the format is wrong or the date is today or in the past.
    """
    try:
        exp_date = datetime.date.fromisoformat(expiration)
    except ValueError:
        raise ValueError(
            f"expiration must be YYYY-MM-DD, got {expiration!r}"
        )
    if exp_date <= datetime.date.today():
        raise ValueError(
            f"expiration {expiration} is in the past or today"
        )
    return exp_date


def _trading_days_until(exp_date: datetime.date) -> int:
    """Count business days (Mon–Fri) between today (exclusive) and exp_date
    (inclusive).

    Args:
        exp_date: Target date.

    Returns:
        Number of trading days; at least 1.
    """
    today = datetime.date.today()
    days = 0
    current = today + datetime.timedelta(days=1)
    while current <= exp_date:
        if current.weekday() < 5:
            days += 1
        current += datetime.timedelta(days=1)
    return max(days, 1)


def _fetch_risk_free_rate() -> float:
    """Fetch the current 13-week T-bill rate from Yahoo Finance as a decimal.

    Args:
        None

    Returns:
        Risk-free rate as a decimal (e.g. 0.045). Falls back to 0.045 if the
        fetch fails.
    """
    try:
        data = yf.Ticker(_RISK_FREE_TICKER).history(period="5d")
        if not data.empty:
            raw = float(data["Close"].iloc[-1])
            if not math.isnan(raw) and raw > 0:
                return raw / 100.0
    except Exception as exc:
        logger.warning(
            "Could not fetch risk-free rate from %s: %s. Using 0.045.",
            _RISK_FREE_TICKER,
            exc,
        )
    return 0.045


# ── Public interface ──────────────────────────────────────────────────────────

def get_option_chain(ticker: str, option_type: str) -> dict:
    """Sync and return all available expirations and strikes for a ticker.

    Triggers a live sync from Yahoo Finance, then reads the freshly written
    rows from the database. Intended to populate the UI dropdown menus.

    Args:
        ticker: Equity ticker symbol, e.g. "AAPL".
        option_type: "call" or "put" (lowercase).

    Returns:
        A dict with:
            "expirations": sorted list of expiration strings (YYYY-MM-DD).
            "strikes": dict mapping each expiration to a sorted list of floats.

    Raises:
        ValueError: If option_type is invalid.
    """
    _validate_option_type(option_type)
    init_db()
    sync_ticker(ticker, option_type)

    upper = ticker.upper()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(fetched_at) AS max_ts
            FROM option_chain
            WHERE ticker = ? AND option_type = ?
            """,
            (upper, option_type),
        ).fetchone()
        max_ts = row["max_ts"] if row else None

        if max_ts is None:
            return {"expirations": [], "strikes": {}}

        today = datetime.date.today().isoformat()
        rows = conn.execute(
            """
            SELECT expiration, strike
            FROM option_chain
            WHERE ticker = ? AND option_type = ? AND fetched_at = ?
              AND expiration > ?
            ORDER BY expiration, strike
            """,
            (upper, option_type, max_ts, today),
        ).fetchall()

    strikes_by_exp: dict[str, list[float]] = {}
    for r in rows:
        exp = r["expiration"]
        strikes_by_exp.setdefault(exp, []).append(float(r["strike"]))

    expirations = sorted(strikes_by_exp.keys())
    return {"expirations": expirations, "strikes": strikes_by_exp}


def get_pricing_inputs(
    ticker: str,
    expiration: str,
    option_type: str,
    strike: float,
) -> PricingInputs:
    """Return all inputs required by the Pricing Engine for a specific contract.

    Reads S, sigma, bid and ask from the database. Computes T = trading_days/252
    and fetches r from the 13-week T-bill rate.

    Args:
        ticker: Equity ticker symbol, e.g. "AAPL".
        expiration: Option expiration date as "YYYY-MM-DD". Must be in the future.
        option_type: "call" or "put" (lowercase).
        strike: Strike price.

    Returns:
        PricingInputs(S, K, T, r, sigma, bid, ask) — the direct input to the
        Pricing Engine with no further transformation needed.

    Raises:
        ValueError: If expiration is today or in the past, option_type is
            invalid, or the requested contract is not in the database.
    """
    _validate_option_type(option_type)
    exp_date = _validate_expiration(expiration)
    init_db()

    upper = ticker.upper()
    with get_connection() as conn:
        spot_row = conn.execute(
            """
            SELECT price FROM spot_price
            WHERE ticker = ?
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (upper,),
        ).fetchone()

        if spot_row is None:
            raise ValueError(
                f"No spot price found for {ticker}. Call get_option_chain first."
            )

        opt_row = conn.execute(
            """
            SELECT implied_vol, bid, ask
            FROM option_chain
            WHERE ticker = ? AND option_type = ? AND expiration = ?
              AND ABS(strike - ?) < 1e-9
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (upper, option_type, expiration, float(strike)),
        ).fetchone()

        if opt_row is None:
            raise ValueError(
                f"No data for {ticker} {option_type} exp={expiration} K={strike}. "
                "Call get_option_chain first."
            )

        S = float(spot_row["price"])
        sigma = float(opt_row["implied_vol"]) if opt_row["implied_vol"] is not None else 0.0
        bid = float(opt_row["bid"]) if opt_row["bid"] is not None else 0.0
        ask = float(opt_row["ask"]) if opt_row["ask"] is not None else 0.0

    r = _fetch_risk_free_rate()
    K = float(strike)
    T = _trading_days_until(exp_date) / 252.0

    return PricingInputs(S=S, K=K, T=T, r=r, sigma=sigma, bid=bid, ask=ask)
