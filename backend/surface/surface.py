"""
Volatility Surface module.

Reads historical implied volatility snapshots from the closing_snapshot
table and returns a structured dictionary for 3D surface visualization.
"""

import numpy as np
from scipy.interpolate import griddata
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


def get_surface_by_date(ticker: str, option_type: str, date: str) -> dict:
    """
    Return implied vol surface data for a single snapshot date.

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g. 'AAPL'). Case-insensitive.
    option_type : str
        'call' or 'put'.
    date : str
        Snapshot date in 'YYYY-MM-DD' format.

    Returns
    -------
    dict with keys:
        - 'expiration': list of expiration dates as strings (YYYY-MM-DD)
        - 'strike': list of strike prices (float)
        - 'implied_vol': list of implied volatilities (float)

    All three lists are parallel (same length, same ordering).
    Returns {'expiration': [], 'strike': [], 'implied_vol': []} if no data
    is found for the given ticker, option_type, and date.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT expiration, strike, implied_vol
            FROM closing_snapshot
            WHERE ticker = %s AND option_type = %s AND snapshot_date = %s
            ORDER BY expiration, strike
            """,
            (ticker.upper(), option_type, date),
        )
        rows = cursor.fetchall()

    if not rows:
        return {"expiration": [], "strike": [], "implied_vol": []}

    return {
        "expiration": [str(row["expiration"]) for row in rows],
        "strike": [row["strike"] for row in rows],
        "implied_vol": [row["implied_vol"] for row in rows],
    }


def build_surface_grid(ticker: str, option_type: str, snapshot_date: str) -> dict:
    """
    Build an interpolated 3D grid for a single snapshot date.

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g. 'AAPL'). Case-insensitive.
    option_type : str
        'call' or 'put'.
    snapshot_date : str
        Date string in YYYY-MM-DD format.

    Returns
    -------
    dict with keys:
        - 'K_grid': 2D array of strike values
        - 'T_grid': 2D array of time-to-expiry values (in years)
        - 'IV_mesh': 2D array of interpolated implied volatilities
        - 'snapshot_date': the date string

    Returns None if no data is available for that date.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT expiration, strike, implied_vol
            FROM closing_snapshot
            WHERE ticker = %s AND option_type = %s AND snapshot_date = %s
            """,
            (ticker.upper(), option_type, snapshot_date),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    from datetime import date
    snap = date.fromisoformat(snapshot_date)

    strikes = []
    ttms = []
    ivs = []

    for row in rows:
        exp = date.fromisoformat(str(row["expiration"]))
        ttm = (exp - snap).days / 365.0
        if ttm > 0 and row["implied_vol"] is not None:
            strikes.append(float(row["strike"]))
            ttms.append(ttm)
            ivs.append(float(row["implied_vol"]))

    if len(strikes) < 4:
        return None

    strikes = np.array(strikes)
    ttms = np.array(ttms)
    ivs = np.array(ivs)

    k_lin = np.linspace(strikes.min(), strikes.max(), 30)
    t_lin = np.linspace(ttms.min(), ttms.max(), 30)
    K_grid, T_grid = np.meshgrid(k_lin, t_lin)

    IV_mesh = griddata(
        points=(strikes, ttms),
        values=ivs,
        xi=(K_grid, T_grid),
        method="cubic",
        fill_value=np.nan,
    )

    return {
        "snapshot_date": snapshot_date,
        "K_grid": K_grid.tolist(),
        "T_grid": T_grid.tolist(),
        "IV_mesh": IV_mesh.tolist(),
    }