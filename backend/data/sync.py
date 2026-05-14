"""Synchronize market data from Yahoo Finance into the PostgreSQL database."""

import datetime
import logging
import math

import pandas as pd
import yfinance as yf

from backend.data.database import get_connection, init_db

logger = logging.getLogger(__name__)


def _safe_float(value: object) -> float | None:
    """Return float or None for NaN/None values."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def sync_ticker(ticker: str, option_type: str) -> None:
    """Fetch the full option chain for ticker from Yahoo Finance and persist it.

    Appends new rows to option_chain and spot_price. Never updates or deletes
    existing rows.

    Args:
        ticker: Equity ticker symbol, e.g. "AAPL".
        option_type: "call" or "put" (lowercase).

    Returns:
        None

    Raises:
        ValueError: If option_type is not "call" or "put".
        RuntimeError: If the spot price cannot be obtained.
    """
    if option_type not in ("call", "put"):
        raise ValueError(
            f"option_type must be 'call' or 'put', got {option_type!r}"
        )

    init_db()
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    upper = ticker.upper()

    yt = yf.Ticker(ticker)

    # Spot price
    spot: float | None = None
    try:
        info = yt.fast_info
        spot = _safe_float(getattr(info, "last_price", None))
    except Exception:
        pass

    if spot is None:
        hist = yt.history(period="2d")
        if not hist.empty:
            spot = float(hist["Close"].iloc[-1])

    if spot is None:
        raise RuntimeError(f"Could not obtain spot price for {ticker}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO spot_price (ticker, price, fetched_at) VALUES (%s, %s, %s)",
            (upper, spot, fetched_at),
        )

    # Option chain
    expirations = yt.options
    if not expirations:
        logger.warning("No option expirations found for %s", ticker)
        return

    df_col = "calls" if option_type == "call" else "puts"

    with get_connection() as conn:
        cursor = conn.cursor()
        for exp in expirations:
            try:
                chain = yt.option_chain(exp)
                df = getattr(chain, df_col)
            except Exception as exc:
                logger.warning(
                    "Skipping expiration %s for %s: %s", exp, ticker, exc
                )
                continue

            rows = []
            for _, row in df.iterrows():
                rows.append(
                    (
                        upper,
                        exp,
                        float(row["strike"]),
                        option_type,
                        _safe_float(row.get("impliedVolatility")),
                        _safe_float(row.get("bid")),
                        _safe_float(row.get("ask")),
                        _safe_float(row.get("lastPrice")),
                        fetched_at,
                    )
                )

            cursor.executemany(
                """
                INSERT INTO option_chain
                    (ticker, expiration, strike, option_type,
                     implied_vol, bid, ask, last_price, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            logger.info(
                "Synced %d %s options for %s exp=%s",
                len(rows),
                option_type,
                ticker,
                exp,
            )


def sync_all_tickers() -> dict[str, int]:
    """Sync all supported tickers for both call and put from Yahoo Finance.

    Returns:
        Dict mapping ticker to total rows synced (call + put combined).
    """
    from backend.data.config import WORKFLOW_TICKERS

    results = {}
    for ticker in SUPPORTED_TICKERS:
        total = 0
        for option_type in ("call", "put"):
            try:
                sync_ticker(ticker, option_type)
                logger.info("Synced %s %s successfully.", ticker, option_type)
                total += 1
            except Exception as exc:
                logger.warning("Failed to sync %s %s: %s", ticker, option_type, exc)
        results[ticker] = total
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_all_tickers()