"""PostgreSQL connection and schema for the options data layer."""

import os
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG: dict = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "dbname": os.getenv("DB_NAME"),
}


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield an open PostgreSQL connection; commits on success, rolls back on error.

    Args:
        None

    Returns:
        Context manager yielding a psycopg2 connection configured with
        RealDictCursor so rows support row["column"] access.
    """
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_index(cursor: RealDictCursor, sql: str) -> None:
    """Execute a CREATE INDEX IF NOT EXISTS statement."""
    cursor.execute(sql)


def init_db() -> None:
    """Create all tables and indexes if they do not exist.

    The database is append-only: existing rows are never updated or deleted.

    Args:
        None

    Returns:
        None
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS spot_price (
                id         SERIAL           PRIMARY KEY,
                ticker     VARCHAR(20)      NOT NULL,
                price      DOUBLE PRECISION NOT NULL,
                fetched_at VARCHAR(30)      NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS option_chain (
                id          SERIAL           PRIMARY KEY,
                ticker      VARCHAR(20)      NOT NULL,
                expiration  VARCHAR(10)      NOT NULL,
                strike      DOUBLE PRECISION NOT NULL,
                option_type TEXT             NOT NULL,
                implied_vol DOUBLE PRECISION,
                bid         DOUBLE PRECISION,
                ask         DOUBLE PRECISION,
                last_price  DOUBLE PRECISION,
                fetched_at  VARCHAR(30)      NOT NULL,
                CONSTRAINT chk_option_type CHECK (option_type IN ('call', 'put'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS closing_snapshot (
                id            SERIAL           PRIMARY KEY,
                ticker        VARCHAR(20)      NOT NULL,
                snapshot_date VARCHAR(10)      NOT NULL,
                expiration    VARCHAR(10)      NOT NULL,
                strike        DOUBLE PRECISION NOT NULL,
                option_type   TEXT             NOT NULL,
                implied_vol   DOUBLE PRECISION,
                saved_at      VARCHAR(30)      NOT NULL,
                CONSTRAINT chk_cs_option_type CHECK (option_type IN ('call', 'put'))
            )
            """
        )

        _create_index(
            cursor,
            "CREATE INDEX IF NOT EXISTS idx_option_chain_lookup"
            " ON option_chain(ticker, option_type, expiration, fetched_at)",
        )
        _create_index(
            cursor,
            "CREATE INDEX IF NOT EXISTS idx_spot_price_lookup"
            " ON spot_price(ticker, fetched_at)",
        )
        _create_index(
            cursor,
            "CREATE INDEX IF NOT EXISTS idx_closing_snapshot_lookup"
            " ON closing_snapshot(ticker, snapshot_date, option_type)",
        )
