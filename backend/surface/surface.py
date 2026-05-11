"""
Volatility Surface module.

Reads historical implied volatility snapshots from the closing_snapshot
table and returns a structured dictionary for 3D surface visualization.
"""

from backend.data.database import get_connection


def get_vol_surface_history(ticker: str, option_type: str) -> dict:
    """
    Read closing_snapshot and return the historical implied vol surface.

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g. 'AAPL'). Case-insensitive.
    option_type : str
        'call' or 'put'.

    Returns
    -------
    dict with keys:
        - 'dates': sorted list of snapshot dates as strings (YYYY-MM-DD)
        - 'surfaces': list of dicts, one per row, each with keys
            'snapshot_date', 'expiration', 'strike', 'implied_vol'

    Returns {'dates': [], 'surfaces': []} if no data is available.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT snapshot_date, expiration, strike, implied_vol
            FROM closing_snapshot
            WHERE ticker = ? AND option_type = ?
            ORDER BY snapshot_date, expiration, strike
            """,
            (ticker.upper(), option_type),
        ).fetchall()

    if not rows:
        return {"dates": [], "surfaces": []}

    surfaces = [
        {
            "snapshot_date": row[0],
            "expiration": row[1],
            "strike": row[2],
            "implied_vol": row[3],
        }
        for row in rows
    ]

    dates = sorted({row["snapshot_date"] for row in surfaces})

    return {"dates": dates, "surfaces": surfaces}
