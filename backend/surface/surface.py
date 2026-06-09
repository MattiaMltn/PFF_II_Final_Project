"""
Volatility Surface module.

Reads historical implied volatility snapshots from the closing_snapshot
table and returns a structured dictionary for 3D surface visualization.
"""

import numpy as np
from scipy.interpolate import griddata
from backend.data.database import get_connection


def get_vol_surface_history(ticker: str, option_type: str) -> dict:
    """Return the full historical implied-volatility surface for a ticker.

    Queries every row in ``closing_snapshot`` for the given ticker and
    option type, then packages the results for downstream 3-D visualisation.

    Args:
        ticker (str): Equity ticker symbol, e.g. ``'AAPL'``.
            Case-insensitive — converted to upper-case internally.
        option_type (str): Option flavour, either ``'call'`` or ``'put'``.

    Returns:
        dict: A dictionary with two keys:

        - ``'dates'`` (list[str]): Sorted, deduplicated list of snapshot
          dates in ``YYYY-MM-DD`` format.
        - ``'surfaces'`` (list[dict]): One dictionary per data-point, each
          containing ``'snapshot_date'``, ``'expiration'``, ``'strike'``
          (float), and ``'implied_vol'`` (float).

        Returns ``{'dates': [], 'surfaces': []}`` when no data is found.

    Example:
        >>> result = get_vol_surface_history('AAPL', 'call')
        >>> result['dates'][:3]
        ['2024-01-02', '2024-01-03', '2024-01-04']
        >>> result['surfaces'][0]
        {'snapshot_date': '2024-01-02', 'expiration': '2024-02-16',
         'strike': 150.0, 'implied_vol': 0.28}
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
    """Return the implied-volatility surface for one specific snapshot date.

    Fetches all (expiration, strike, implied_vol) rows for a single
    closing-snapshot date and returns three parallel lists suitable for
    scatter or surface plots.

    Args:
        ticker (str): Equity ticker symbol, e.g. ``'AAPL'``.
            Case-insensitive — converted to upper-case internally.
        option_type (str): Option flavour, either ``'call'`` or ``'put'``.
        date (str): The snapshot date to query, in ``YYYY-MM-DD`` format.

    Returns:
        dict: A dictionary with three parallel lists (all the same length,
        in (expiration, strike) order):

        - ``'expiration'`` (list[str]): Expiration dates in ``YYYY-MM-DD``
          format.
        - ``'strike'`` (list[float]): Strike prices in ascending order.
        - ``'implied_vol'`` (list[float]): Corresponding implied volatilities
          as decimals (e.g. ``0.25`` represents 25 %).

        Returns ``{'expiration': [], 'strike': [], 'implied_vol': []}`` when
        no data is found for the given ticker, option type, and date.

    Example:
        >>> surface = get_surface_by_date('AAPL', 'put', '2024-03-15')
        >>> len(surface['strike'])
        42
        >>> surface['expiration'][0], surface['strike'][0]
        ('2024-04-19', 140.0)
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
    """Build a cubic-interpolated 30×30 volatility-surface grid for one date.

    Retrieves raw (expiration, strike, implied_vol) data for the given
    snapshot date, computes time-to-expiry in years, and uses
    ``scipy.interpolate.griddata`` with cubic interpolation to produce
    evenly-spaced 2-D meshgrids over the (strike, TTM) domain.

    Args:
        ticker (str): Equity ticker symbol, e.g. ``'AAPL'``.
            Case-insensitive — converted to upper-case internally.
        option_type (str): Option flavour, either ``'call'`` or ``'put'``.
        snapshot_date (str): The closing-snapshot date in ``YYYY-MM-DD``
            format.  Used both as the DB filter and as the reference date
            for computing time-to-expiry.

    Returns:
        dict | None: On success, a dictionary with four keys:

        - ``'snapshot_date'`` (str): The input date, echoed back.
        - ``'K_grid'`` (list[list[float]]): 30×30 grid of strike values
          spanning ``[min_strike, max_strike]``.
        - ``'T_grid'`` (list[list[float]]): 30×30 grid of time-to-expiry
          values in fractional years, spanning ``[min_ttm, max_ttm]``.
        - ``'IV_mesh'`` (list[list[float | None]]): 30×30 grid of
          interpolated implied volatilities; cells outside the convex hull
          of the raw data are ``NaN``.

        Returns ``None`` if no data exists for the given inputs or if
        fewer than 4 valid data-points are available (insufficient for
        cubic interpolation).

    Example:
        >>> grid = build_surface_grid('AAPL', 'call', '2024-03-15')
        >>> grid is not None
        True
        >>> len(grid['K_grid']), len(grid['K_grid'][0])
        (30, 30)
        >>> grid['snapshot_date']
        '2024-03-15'
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