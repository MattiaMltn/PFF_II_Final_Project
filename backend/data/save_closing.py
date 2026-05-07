"""End-of-day snapshot of implied volatility for the Volatility Surface module.

Run this script once per trading day after market close to accumulate the
historical implied-volatility surface in closing_snapshot.
"""

import datetime
import logging

from backend.data.database import get_connection, init_db

logger = logging.getLogger(__name__)


def save_closing_snapshot(ticker: str, option_type: str) -> int:
    """Snapshot the latest implied volatility across all contracts into
    closing_snapshot.

    Reads the most recent rows from option_chain and copies them into
    closing_snapshot tagged with today's date. Rows accumulate over time and
    feed the Volatility Surface module.

    Args:
        ticker: Equity ticker symbol, e.g. "AAPL".
        option_type: "call" or "put" (lowercase).

    Returns:
        Number of rows written to closing_snapshot.

    Raises:
        ValueError: If option_type is not "call" or "put".
    """
    if option_type not in ("call", "put"):
        raise ValueError(
            f"option_type must be 'call' or 'put', got {option_type!r}"
        )

    init_db()
    today = datetime.date.today().isoformat()
    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
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
            logger.warning(
                "No option_chain data for %s %s — nothing to snapshot.",
                ticker,
                option_type,
            )
            return 0

        source_rows = conn.execute(
            """
            SELECT expiration, strike, implied_vol
            FROM option_chain
            WHERE ticker = ? AND option_type = ? AND fetched_at = ?
            """,
            (upper, option_type, max_ts),
        ).fetchall()

        snapshot_rows = [
            (
                upper,
                today,
                r["expiration"],
                float(r["strike"]),
                option_type,
                float(r["implied_vol"]) if r["implied_vol"] is not None else None,
                saved_at,
            )
            for r in source_rows
        ]

        conn.executemany(
            """
            INSERT INTO closing_snapshot
                (ticker, snapshot_date, expiration, strike, option_type,
                 implied_vol, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            snapshot_rows,
        )

    logger.info(
        "Saved %d closing snapshots for %s %s on %s",
        len(snapshot_rows),
        ticker,
        option_type,
        today,
    )
    return len(snapshot_rows)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    _ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    for _otype in ("call", "put"):
        save_closing_snapshot(_ticker, _otype)
