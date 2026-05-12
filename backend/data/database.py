"""MySQL connection and schema for the options data layer."""

import os
from collections.abc import Generator
from contextlib import contextmanager

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG: dict = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
}


@contextmanager
def get_connection() -> Generator[pymysql.connections.Connection, None, None]:
    """Yield an open MySQL connection; commits on success, rolls back on error.

    Args:
        None

    Returns:
        Context manager yielding a pymysql Connection configured with DictCursor
        as the default cursor class.
    """
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_index(cursor: pymysql.cursors.DictCursor, sql: str) -> None:
    """Execute a CREATE INDEX statement, silently skipping if already exists."""
    try:
        cursor.execute(sql)
    except pymysql.err.OperationalError as exc:
        if exc.args[0] != 1061:  # 1061 = Duplicate key name
            raise


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
                id         INT         AUTO_INCREMENT PRIMARY KEY,
                ticker     VARCHAR(20) NOT NULL,
                price      DOUBLE      NOT NULL,
                fetched_at VARCHAR(30) NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS option_chain (
                id          INT         AUTO_INCREMENT PRIMARY KEY,
                ticker      VARCHAR(20) NOT NULL,
                expiration  VARCHAR(10) NOT NULL,
                strike      DOUBLE      NOT NULL,
                option_type VARCHAR(4)  NOT NULL,
                implied_vol DOUBLE,
                bid         DOUBLE,
                ask         DOUBLE,
                last_price  DOUBLE,
                fetched_at  VARCHAR(30) NOT NULL,
                CONSTRAINT chk_option_type CHECK (option_type IN ('call', 'put'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS closing_snapshot (
                id            INT         AUTO_INCREMENT PRIMARY KEY,
                ticker        VARCHAR(20) NOT NULL,
                snapshot_date VARCHAR(10) NOT NULL,
                expiration    VARCHAR(10) NOT NULL,
                strike        DOUBLE      NOT NULL,
                option_type   VARCHAR(4)  NOT NULL,
                implied_vol   DOUBLE,
                saved_at      VARCHAR(30) NOT NULL,
                CONSTRAINT chk_cs_option_type CHECK (option_type IN ('call', 'put'))
            )
            """
        )

        _create_index(
            cursor,
            "CREATE INDEX idx_option_chain_lookup"
            " ON option_chain(ticker, option_type, expiration, fetched_at)",
        )
        _create_index(
            cursor,
            "CREATE INDEX idx_spot_price_lookup"
            " ON spot_price(ticker, fetched_at)",
        )
        _create_index(
            cursor,
            "CREATE INDEX idx_closing_snapshot_lookup"
            " ON closing_snapshot(ticker, snapshot_date, option_type)",
        )
