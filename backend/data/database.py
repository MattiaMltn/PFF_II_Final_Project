"""SQLite connection and schema for the options data layer."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "options_data.db"


def get_connection() -> sqlite3.Connection:
    """Return an open connection with row_factory set to sqlite3.Row.

    Args:
        None

    Returns:
        sqlite3.Connection configured with row_factory = sqlite3.Row.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables and indexes if they do not exist.

    The database is append-only: existing rows are never updated or deleted.

    Args:
        None

    Returns:
        None
    """
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS spot_price (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT    NOT NULL,
                price      REAL    NOT NULL,
                fetched_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS option_chain (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                expiration  TEXT    NOT NULL,
                strike      REAL    NOT NULL,
                option_type TEXT    NOT NULL
                    CHECK(option_type IN ('call', 'put')),
                implied_vol REAL,
                bid         REAL,
                ask         REAL,
                last_price  REAL,
                fetched_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS closing_snapshot (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker        TEXT    NOT NULL,
                snapshot_date TEXT    NOT NULL,
                expiration    TEXT    NOT NULL,
                strike        REAL    NOT NULL,
                option_type   TEXT    NOT NULL
                    CHECK(option_type IN ('call', 'put')),
                implied_vol   REAL,
                saved_at      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_option_chain_lookup
                ON option_chain(ticker, option_type, expiration, fetched_at);

            CREATE INDEX IF NOT EXISTS idx_spot_price_lookup
                ON spot_price(ticker, fetched_at);

            CREATE INDEX IF NOT EXISTS idx_closing_snapshot_lookup
                ON closing_snapshot(ticker, snapshot_date, option_type);
            """
        )
