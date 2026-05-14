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
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT snapshot_date, expiration, strike, implied_vol
            FROM closing_snapshot
            WHERE ticker = %s AND option_type = %s
            ORDER BY snapshot_date, expiration, strike
            """,
            (ticker.upper(), option_type),
        )
        rows = cursor.fetchall()

    if not rows:
        return {"dates": [], "surfaces": []}

    surfaces = [
        {
            "snapshot_date": str(row["snapshot_date"]),
            "expiration": str(row["expiration"]),
            "strike": row["strike"],
            "implied_vol": row["implied_vol"],
        }
        for row in rows
    ]

    dates = sorted({row["snapshot_date"] for row in surfaces})

    return {"dates": dates, "surfaces": surfaces}