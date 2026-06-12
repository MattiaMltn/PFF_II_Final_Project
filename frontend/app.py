"""Options Pricing Platform - Streamlit dashboard."""

from __future__ import annotations

from collections import namedtuple
from datetime import date
from math import erf, exp, log, sqrt
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

try:
    from scipy.ndimage import gaussian_filter
except ImportError:  # pragma: no cover - scipy is a project dependency
    gaussian_filter = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only without dependency
    def load_dotenv() -> bool:
        return False

from backend.llm.explainer import (
    explain_pricing_result,
    explain_volatility_surface,
)

try:
    from backend.data.config import SUPPORTED_TICKERS
    from backend.data.database import get_connection
    from backend.data.market_data import get_option_chain, get_pricing_inputs
    from backend.pricing.binomial_tree import binomial_tree
    from backend.pricing.greeks import calcola_greeks
    from backend.surface.surface import (
        get_surface_by_date,
        get_vol_surface_history,
    )
except ImportError:
    SUPPORTED_TICKERS = ["AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"]
    get_connection = None
    get_option_chain = None
    get_pricing_inputs = None
    binomial_tree = None
    calcola_greeks = None
    get_surface_by_date = None
    get_vol_surface_history = None


PricingInputs = namedtuple(
    "PricingInputs",
    ["S", "K", "T", "r", "sigma", "bid", "ask"],
)


MOCK_CHAIN = [
    {
        "expiration": "2026-06-20",
        "strike": 280.0,
        "implied_vol": 0.24,
        "bid": 20.10,
        "ask": 20.55,
        "last_price": 20.35,
    },
    {
        "expiration": "2026-06-20",
        "strike": 300.0,
        "implied_vol": 0.26,
        "bid": 10.80,
        "ask": 11.15,
        "last_price": 10.95,
    },
    {
        "expiration": "2026-09-18",
        "strike": 300.0,
        "implied_vol": 0.29,
        "bid": 18.20,
        "ask": 18.70,
        "last_price": 18.45,
    },
]


def main() -> None:
    """Render the Streamlit dashboard."""
    load_dotenv()

    st.set_page_config(page_title="Options Pricing Platform", layout="wide")
    st.title("Options Pricing Platform")

    with st.sidebar:
        st.header("Parameters")
        ticker = st.selectbox("Ticker", SUPPORTED_TICKERS)
        option_type = st.selectbox("Option type", ["call", "put"])
        american = (
            st.selectbox("Exercise style", ["European", "American"])
            == "American"
        )

        chain_key = f"{ticker}:{option_type}"
        if st.session_state.get("chain_key") != chain_key:
            st.session_state.pop("option_chain", None)
            st.session_state["chain_key"] = chain_key

        if st.button("Load option chain"):
            with st.spinner("Fetching option chain..."):
                st.session_state["option_chain"] = _load_option_chain(
                    ticker,
                    option_type,
                )

        chain = st.session_state.get("option_chain")
        expiration = None
        strike = None

        if chain is None:
            st.info("Click Load option chain to fetch expirations and strikes.")
        else:
            expirations, strikes_by_expiration = _normalize_chain(chain)

            if not expirations:
                st.warning("No data available for this ticker.")
            else:
                expiration = st.selectbox("Expiration", expirations)
                strikes = strikes_by_expiration.get(expiration, [])
                strike = st.selectbox("Strike ($)", strikes)

        price_button = st.button(
            "Price Option",
            type="primary",
            disabled=expiration is None or strike is None,
        )

    tab1, tab2 = st.tabs(["Pricing & Greeks", "Volatility Surface"])

    with tab1:
        if expiration is None or strike is None:
            st.info("Load an option chain, then select expiration and strike.")
        else:
            _render_pricing_tab(
                ticker=ticker,
                expiration=expiration,
                option_type=option_type,
                strike=strike,
                american=american,
                price_button=price_button,
            )

    with tab2:
        _render_surface_tab(ticker, option_type)


def _render_pricing_tab(
    ticker: str,
    expiration: str,
    option_type: str,
    strike: float,
    american: bool,
    price_button: bool,
) -> None:
    if not price_button:
        st.info("Select an option in the sidebar and click Price Option.")
        return

    with st.spinner("Fetching market data..."):
        inputs = _load_pricing_inputs(ticker, expiration, option_type, strike)

    n_steps = 500 if american else 200

    with st.spinner("Pricing..."):
        price = _price_option(inputs, option_type, american, n_steps)
        greeks = _calculate_greeks(inputs, option_type)

    col1, col2, col3 = st.columns(3)
    col1.metric("Option Price", f"${price:.4f}")
    col2.metric("Bid / Ask", f"${inputs.bid:.2f} / ${inputs.ask:.2f}")
    col3.metric("Spot Price", f"${inputs.S:.2f}")

    st.divider()
    st.subheader("Greeks")

    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("Delta", f"{greeks['delta']:.4f}")
    g2.metric("Gamma", f"{greeks['gamma']:.4f}")
    g3.metric("Theta", f"{greeks['theta']:.4f} /day")
    g4.metric("Vega", f"{greeks['vega']:.4f} /1%")
    g5.metric("Rho", f"{greeks['rho']:.4f} /1%")

    st.divider()
    st.subheader("AI Explanation")

    if not _has_groq_key():
        st.info("Add GROQ_API_KEY to .env to enable the AI explanation.")
        return

    try:
        with st.spinner("Generating explanation..."):
            explanation = explain_pricing_result(
                option_params={
                    "ticker": ticker,
                    "S": inputs.S,
                    "K": inputs.K,
                    "T": inputs.T,
                    "r": inputs.r,
                    "sigma": inputs.sigma,
                    "bid": inputs.bid,
                    "ask": inputs.ask,
                    "option_type": option_type,
                    "american": american,
                },
                price=price,
                greeks=greeks,
            )
        with st.container(border=True):
            st.markdown(_prepare_llm_markdown(explanation))
    except Exception as exc:
        st.warning(f"AI explanation unavailable: {exc}")


def _render_surface_tab(ticker: str, option_type: str) -> None:
    surface_key = f"{ticker}:{option_type}"
    if st.session_state.get("surface_key") != surface_key:
        st.session_state.pop("surface_history", None)
        st.session_state["surface_key"] = surface_key

    if st.button("Load volatility surface"):
        with st.spinner("Fetching volatility surface..."):
            st.session_state["surface_history"] = _load_surface_history(
                ticker,
                option_type,
            )

    history = st.session_state.get("surface_history")

    if history is None:
        st.info("Click Load volatility surface to show the 3D chart.")
        return

    if not history["dates"]:
        st.warning("No historical surface data available for this ticker.")
        return

    if history.get("source") == "live_yahoo":
        st.info(
            "No historical DB snapshots found for this ticker; showing a live "
            "Yahoo Finance surface for today's option chain."
        )

    spot = _load_latest_spot(ticker)
    st.subheader("Chart filters")
    f1, f2, f3, f4 = st.columns([1.4, 1.4, 1.1, 1.1])
    with f1:
        moneyness_range = st.slider(
            "Moneyness range (K / S)",
            min_value=0.50,
            max_value=1.50,
            value=(0.60, 1.40),
            step=0.05,
        )
    with f2:
        dte_range = st.slider(
            "Days to expiry",
            min_value=1,
            max_value=1095,
            value=(14, 540),
            step=7,
        )
    with f3:
        max_iv = st.slider(
            "Max IV",
            min_value=0.25,
            max_value=2.00,
            value=1.00,
            step=0.05,
            format="%.2f",
        )
    with f4:
        trim_top_pct = st.slider(
            "Trim top outliers",
            min_value=0,
            max_value=10,
            value=2,
            step=1,
            format="%d%%",
        )

    c1, c2 = st.columns([1, 1])
    with c1:
        colorscale = st.selectbox(
            "Color scale",
            ["Viridis", "Cividis", "Plasma", "Turbo"],
        )
    with c2:
        smoothing_sigma = st.slider(
            "Visual smoothing",
            min_value=0.0,
            max_value=2.0,
            value=0.6,
            step=0.1,
            help=(
                "Applies only to the chart surface. Pricing inputs and "
                "reported raw-data statistics are not changed."
            ),
        )

    view_mode = st.radio(
        "Surface view",
        ["Single snapshot", "Temporal evolution"],
        horizontal=True,
    )

    selected_date = st.selectbox(
        "Snapshot date",
        history["dates"],
        index=len(history["dates"]) - 1,
        disabled=view_mode == "Temporal evolution",
    )

    if view_mode == "Temporal evolution":
        if len(history["dates"]) < 2:
            st.warning(
                "At least two historical snapshot dates are required for animation."
            )
            return

        max_frames = min(len(history["dates"]), 30)
        default_frames = min(len(history["dates"]), 12)
        frame_count = st.slider(
            "Snapshots in animation",
            min_value=2,
            max_value=max_frames,
            value=default_frames,
            step=1,
        )
        selected_dates = history["dates"][-frame_count:]
        _render_surface_filter_captions(
            spot=spot,
            moneyness_range=moneyness_range,
            dte_range=dte_range,
            max_iv=max_iv,
            trim_top_pct=trim_top_pct,
            smoothing_sigma=smoothing_sigma,
        )
        _render_temporal_surface(
            history=history,
            ticker=ticker,
            option_type=option_type,
            selected_dates=selected_dates,
            spot=spot,
            moneyness_range=moneyness_range,
            dte_range=dte_range,
            max_iv=max_iv,
            trim_top_pct=trim_top_pct,
            smoothing_sigma=smoothing_sigma,
            colorscale=colorscale,
        )
        return

    surface_data = _surface_data_from_history(history, selected_date)
    if not surface_data["strike"]:
        surface_data = _load_surface_by_date(ticker, option_type, selected_date)

    if not surface_data["strike"]:
        st.warning("No surface data for this date.")
        return

    df = _prepare_surface_frame(
        surface_data,
        selected_date,
        spot=spot,
        moneyness_range=moneyness_range,
        dte_range=dte_range,
        max_iv=max_iv,
        trim_top_pct=trim_top_pct,
    )

    if df.empty:
        st.warning("Surface data only contains rows outside the chart filters.")
        return

    _render_surface_filter_captions(
        spot=spot,
        moneyness_range=moneyness_range,
        dte_range=dte_range,
        max_iv=max_iv,
        trim_top_pct=trim_top_pct,
        smoothing_sigma=smoothing_sigma,
    )
    _render_surface_stats(df)

    pivot = _build_surface_pivot(df)
    display_pivot = _smooth_surface_pivot(pivot, smoothing_sigma)

    fig = _build_surface_figure(
        display_pivot,
        ticker=ticker,
        option_type=option_type,
        selected_date=selected_date,
        colorscale=colorscale,
    )
    st.plotly_chart(fig, width="stretch")
    summary = _build_surface_summary(
        df,
        ticker=ticker,
        option_type=option_type,
        snapshot_date=selected_date,
        source=history.get("source", "historical_db"),
        smoothing_sigma=smoothing_sigma,
    )
    _render_surface_explanation(summary)


def _render_surface_filter_captions(
    spot: float | None,
    moneyness_range: tuple[float, float],
    dte_range: tuple[int, int],
    max_iv: float,
    trim_top_pct: int,
    smoothing_sigma: float,
) -> None:
    if spot is not None:
        st.caption(
            f"Showing moneyness from {moneyness_range[0]:.2f} to "
            f"{moneyness_range[1]:.2f}, equivalent to strikes from "
            f"${moneyness_range[0] * spot:.2f} to "
            f"${moneyness_range[1] * spot:.2f} at latest spot ${spot:.2f}."
        )
    else:
        st.caption("Latest spot unavailable; moneyness uses the raw strike value.")
    st.caption(
        f"Showing expirations from {dte_range[0]} to {dte_range[1]} days "
        f"to expiry, implied volatility up to {max_iv:.0%}, "
        f"with top {trim_top_pct}% outliers removed."
    )
    if smoothing_sigma > 0:
        st.caption(
            f"Visual smoothing sigma: {smoothing_sigma:.1f}. "
            "This only smooths the displayed chart, not the underlying data."
        )


def _build_surface_pivot(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(
        index="days_to_expiry",
        columns="moneyness",
        values="implied_vol",
        aggfunc="mean",
    )
    pivot = pivot.sort_index().sort_index(axis=1)
    pivot = pivot.interpolate(axis=0, limit_direction="both")
    pivot = pivot.interpolate(axis=1, limit_direction="both")
    return pivot


def _render_temporal_surface(
    history: dict,
    ticker: str,
    option_type: str,
    selected_dates: list[str],
    spot: float | None,
    moneyness_range: tuple[float, float],
    dte_range: tuple[int, int],
    max_iv: float,
    trim_top_pct: int,
    smoothing_sigma: float,
    colorscale: str,
) -> None:
    frames = []
    first_df = pd.DataFrame()
    latest_df = pd.DataFrame()

    for snapshot_date in selected_dates:
        surface_data = _surface_data_from_history(history, snapshot_date)
        df = _prepare_surface_frame(
            surface_data,
            snapshot_date,
            spot=spot,
            moneyness_range=moneyness_range,
            dte_range=dte_range,
            max_iv=max_iv,
            trim_top_pct=trim_top_pct,
        )
        if df.empty:
            continue

        pivot = _build_surface_pivot(df)
        display_pivot = _smooth_surface_pivot(pivot, smoothing_sigma)
        frames.append((snapshot_date, display_pivot, len(df)))
        if first_df.empty:
            first_df = df
        latest_df = df

    if len(frames) < 2:
        st.warning("Not enough filtered surfaces to build a temporal animation.")
        return

    st.caption(
        f"Animating {len(frames)} snapshots from {frames[0][0]} to {frames[-1][0]}."
    )
    _render_surface_stats(latest_df)

    fig = _build_temporal_surface_figure(
        frames,
        ticker=ticker,
        option_type=option_type,
        colorscale=colorscale,
    )
    st.plotly_chart(fig, width="stretch")
    summary = _build_surface_summary(
        latest_df,
        ticker=ticker,
        option_type=option_type,
        snapshot_date=frames[-1][0],
        source=history.get("source", "historical_db"),
        smoothing_sigma=smoothing_sigma,
        first_df=first_df,
        first_snapshot=frames[0][0],
    )
    _render_surface_explanation(summary)


def _surface_data_from_history(history: dict, snapshot_date: str) -> dict:
    rows = [
        row
        for row in history.get("surfaces", [])
        if row["snapshot_date"] == snapshot_date
    ]

    return {
        "expiration": [row["expiration"] for row in rows],
        "strike": [row["strike"] for row in rows],
        "implied_vol": [row["implied_vol"] for row in rows],
    }


def _render_surface_stats(df: pd.DataFrame) -> None:
    stats = st.columns(4)
    stats[0].metric("Surface points", f"{len(df):,}")
    stats[1].metric(
        "IV range",
        f"{df['implied_vol'].min():.1%} - {df['implied_vol'].max():.1%}",
    )
    stats[2].metric(
        "Moneyness range",
        f"{df['moneyness'].min():.2f} - {df['moneyness'].max():.2f}",
    )
    stats[3].metric(
        "DTE range",
        f"{int(df['days_to_expiry'].min())} - "
        f"{int(df['days_to_expiry'].max())} days",
    )


def _build_surface_summary(
    df: pd.DataFrame,
    ticker: str,
    option_type: str,
    snapshot_date: str,
    source: str,
    smoothing_sigma: float,
    first_df: pd.DataFrame | None = None,
    first_snapshot: str | None = None,
) -> dict:
    def median_for(mask: pd.Series) -> float | None:
        values = df.loc[mask, "implied_vol"]
        return float(values.median()) if not values.empty else None

    atm_iv = median_for(df["moneyness"].between(0.95, 1.05))
    summary = {
        "ticker": ticker,
        "option_type": option_type,
        "snapshot_date": snapshot_date,
        "source": source,
        "points": len(df),
        "maturities": int(df["days_to_expiry"].nunique()),
        "moneyness_min": float(df["moneyness"].min()),
        "moneyness_max": float(df["moneyness"].max()),
        "dte_min": int(df["days_to_expiry"].min()),
        "dte_max": int(df["days_to_expiry"].max()),
        "iv_min": float(df["implied_vol"].min()),
        "iv_max": float(df["implied_vol"].max()),
        "iv_median": float(df["implied_vol"].median()),
        "atm_iv": atm_iv,
        "left_wing_iv": median_for(df["moneyness"] <= 0.90),
        "right_wing_iv": median_for(df["moneyness"] >= 1.10),
        "short_iv": median_for(df["days_to_expiry"] <= 60),
        "long_iv": median_for(df["days_to_expiry"] >= 180),
        "smoothing_sigma": smoothing_sigma,
        "first_snapshot": first_snapshot,
    }

    if first_df is not None and not first_df.empty:
        first_atm = first_df.loc[
            first_df["moneyness"].between(0.95, 1.05),
            "implied_vol",
        ]
        summary["median_iv_change"] = (
            summary["iv_median"] - float(first_df["implied_vol"].median())
        )
        summary["atm_iv_change"] = (
            atm_iv - float(first_atm.median())
            if atm_iv is not None and not first_atm.empty
            else 0.0
        )

    return summary


def _render_surface_explanation(summary: dict) -> None:
    st.subheader("AI Surface Commentary")
    if not _has_groq_key():
        st.info("Add GROQ_API_KEY to .env to enable the AI surface commentary.")
        return

    explanation_key = (
        f"surface_explanation:{summary['ticker']}:{summary['option_type']}:"
        f"{summary['snapshot_date']}:{summary.get('first_snapshot')}:"
        f"{summary['points']}:{summary['iv_median']:.6f}:"
        f"{summary['moneyness_min']:.3f}:{summary['moneyness_max']:.3f}:"
        f"{summary['dte_min']}:{summary['dte_max']}:"
        f"{summary['smoothing_sigma']}"
    )

    if st.button("Explain volatility surface", key=f"button:{explanation_key}"):
        try:
            with st.spinner("Interpreting volatility surface..."):
                st.session_state[explanation_key] = explain_volatility_surface(
                    summary
                )
        except Exception as exc:
            st.warning(f"AI surface commentary unavailable: {exc}")

    explanation = st.session_state.get(explanation_key)
    if explanation:
        with st.container(border=True):
            st.markdown(_prepare_llm_markdown(explanation))


def _smooth_surface_pivot(
    pivot: pd.DataFrame,
    smoothing_sigma: float,
) -> pd.DataFrame:
    if smoothing_sigma <= 0:
        return pivot

    if pivot.empty:
        return pivot

    values = pivot.to_numpy(dtype=float)
    if gaussian_filter is not None:
        smoothed = gaussian_filter(values, sigma=smoothing_sigma, mode="nearest")
    else:
        smoothed = (
            pd.DataFrame(values)
            .rolling(window=3, min_periods=1, center=True, axis=0)
            .mean()
            .rolling(window=3, min_periods=1, center=True, axis=1)
            .mean()
            .to_numpy()
        )

    lower = np.nanmin(values)
    upper = np.nanmax(values)
    smoothed = np.clip(smoothed, lower, upper)
    return pd.DataFrame(smoothed, index=pivot.index, columns=pivot.columns)


def _build_surface_figure(
    pivot: pd.DataFrame,
    ticker: str,
    option_type: str,
    selected_date: str,
    colorscale: str,
) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Surface(
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                z=pivot.values,
                colorscale=colorscale,
                colorbar=dict(title="Implied Vol"),
            )
        ]
    )
    fig.update_layout(
        title=(
            f"{ticker} {option_type.capitalize()} Volatility Surface - "
            f"{selected_date}"
        ),
        scene=dict(
            xaxis_title="Moneyness (K / S)",
            yaxis_title="Days to Expiry",
            zaxis_title="Implied Volatility",
        ),
        height=600,
    )
    return fig


def _build_temporal_surface_figure(
    frames_data: list[tuple[str, pd.DataFrame, int]],
    ticker: str,
    option_type: str,
    colorscale: str,
) -> go.Figure:
    first_date, first_pivot, _ = frames_data[0]
    all_values = np.concatenate(
        [pivot.to_numpy(dtype=float).ravel() for _, pivot, _ in frames_data]
    )
    z_min = float(np.nanmin(all_values))
    z_max = float(np.nanmax(all_values))
    x_min = min(float(pivot.columns.min()) for _, pivot, _ in frames_data)
    x_max = max(float(pivot.columns.max()) for _, pivot, _ in frames_data)
    y_min = min(float(pivot.index.min()) for _, pivot, _ in frames_data)
    y_max = max(float(pivot.index.max()) for _, pivot, _ in frames_data)

    fig = go.Figure(
        data=[
            go.Surface(
                x=first_pivot.columns.tolist(),
                y=first_pivot.index.tolist(),
                z=first_pivot.values,
                colorscale=colorscale,
                cmin=z_min,
                cmax=z_max,
                colorbar=dict(title="Implied Vol"),
            )
        ],
        frames=[
            go.Frame(
                name=snapshot_date,
                data=[
                    go.Surface(
                        x=pivot.columns.tolist(),
                        y=pivot.index.tolist(),
                        z=pivot.values,
                        colorscale=colorscale,
                        cmin=z_min,
                        cmax=z_max,
                    )
                ],
                layout=go.Layout(
                    title=(
                        f"{ticker} {option_type.capitalize()} Volatility "
                        f"Surface Evolution - {snapshot_date}"
                    )
                ),
            )
            for snapshot_date, pivot, _ in frames_data
        ],
    )

    fig.update_layout(
        title=(
            f"{ticker} {option_type.capitalize()} Volatility Surface "
            f"Evolution - {first_date}"
        ),
        scene=dict(
            xaxis=dict(title="Moneyness (K / S)", range=[x_min, x_max]),
            yaxis=dict(title="Days to Expiry", range=[y_min, y_max]),
            zaxis=dict(title="Implied Volatility", range=[z_min, z_max]),
        ),
        height=650,
        updatemenus=[
            {
                "type": "buttons",
                "showactive": False,
                "x": 0,
                "y": 1.08,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": 700, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 250},
                            },
                        ],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {
                                "frame": {"duration": 0, "redraw": False},
                                "mode": "immediate",
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                ],
            }
        ],
        sliders=[
            {
                "active": 0,
                "currentvalue": {"prefix": "Snapshot: "},
                "pad": {"t": 50},
                "steps": [
                    {
                        "label": snapshot_date,
                        "method": "animate",
                        "args": [
                            [snapshot_date],
                            {
                                "frame": {"duration": 0, "redraw": True},
                                "mode": "immediate",
                                "transition": {"duration": 0},
                            },
                        ],
                    }
                    for snapshot_date, _, _ in frames_data
                ],
            }
        ],
    )
    return fig


@st.cache_data(ttl=300, show_spinner=False)
def _load_option_chain(ticker: str, option_type: str) -> list[dict] | dict:
    if get_option_chain is None:
        return MOCK_CHAIN
    try:
        return get_option_chain(ticker, option_type)
    except Exception as exc:
        st.warning(f"Using mock option chain: {exc}")
        return MOCK_CHAIN


def _normalize_chain(chain: list[dict] | dict) -> tuple[list[str], dict]:
    if isinstance(chain, dict):
        expirations = sorted(chain.get("expirations", []))
        strikes = chain.get("strikes", {})
        return expirations, strikes

    expirations = sorted({row["expiration"] for row in chain})
    strikes = {
        expiration: sorted(
            {
                row["strike"]
                for row in chain
                if row["expiration"] == expiration
            }
        )
        for expiration in expirations
    }
    return expirations, strikes


@st.cache_data(ttl=300, show_spinner=False)
def _load_pricing_inputs(
    ticker: str,
    expiration: str,
    option_type: str,
    strike: float,
) -> PricingInputs:
    if get_pricing_inputs is not None:
        try:
            inputs = get_pricing_inputs(ticker, expiration, option_type, strike)
            return _replace_with_latest_valid_quote(
                ticker,
                expiration,
                option_type,
                strike,
                inputs,
            )
        except Exception as exc:
            st.warning(f"Using mock pricing inputs: {exc}")

    matching_row = next(
        (
            row
            for row in MOCK_CHAIN
            if row["expiration"] == expiration and row["strike"] == strike
        ),
        MOCK_CHAIN[0],
    )
    return PricingInputs(
        S=298.87,
        K=float(strike),
        T=max((date.fromisoformat(expiration) - date.today()).days / 365, 0.01),
        r=0.0425,
        sigma=matching_row["implied_vol"],
        bid=matching_row["bid"],
        ask=matching_row["ask"],
    )


def _replace_with_latest_valid_quote(
    ticker: str,
    expiration: str,
    option_type: str,
    strike: float,
    inputs: PricingInputs,
) -> PricingInputs:
    if inputs.bid > 0 and inputs.ask > 0 and inputs.sigma > 0.01:
        return inputs

    if get_connection is None:
        return inputs

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT implied_vol, bid, ask
                FROM option_chain
                WHERE ticker = %s
                  AND option_type = %s
                  AND expiration = %s
                  AND ABS(strike - %s) < 1e-9
                  AND bid > 0
                  AND ask > 0
                  AND implied_vol > 0.01
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (ticker.upper(), option_type, expiration, float(strike)),
            )
            row = cursor.fetchone()
    except Exception:
        return inputs

    if not row:
        return inputs

    st.warning(
        "Latest quote had zero bid/ask or invalid IV; using the most recent "
        "valid quote for this contract."
    )
    return PricingInputs(
        S=inputs.S,
        K=inputs.K,
        T=inputs.T,
        r=inputs.r,
        sigma=float(row["implied_vol"]),
        bid=float(row["bid"]),
        ask=float(row["ask"]),
    )


def _price_option(
    inputs: PricingInputs,
    option_type: str,
    american: bool,
    n_steps: int,
) -> float:
    if binomial_tree is not None:
        try:
            return binomial_tree(
                S=inputs.S,
                K=inputs.K,
                T=inputs.T,
                r=inputs.r,
                sigma=inputs.sigma,
                option_type=option_type,
                american=american,
                n=n_steps,
            )
        except Exception as exc:
            st.warning(f"Using mock pricing result: {exc}")

    intrinsic = (
        max(inputs.S - inputs.K, 0)
        if option_type == "call"
        else max(inputs.K - inputs.S, 0)
    )
    time_value = inputs.S * inputs.sigma * sqrt(inputs.T) * 0.1
    return intrinsic + time_value


def _calculate_greeks(inputs: PricingInputs, option_type: str) -> dict:
    if calcola_greeks is not None:
        try:
            return calcola_greeks(
                S=inputs.S,
                K=inputs.K,
                T=inputs.T,
                r=inputs.r,
                sigma=inputs.sigma,
                option_type=option_type,
            )
        except Exception as exc:
            st.warning(f"Using mock Greeks: {exc}")

    return _black_scholes_greeks(inputs, option_type)


@st.cache_data(ttl=300, show_spinner=False)
def _load_surface_history(ticker: str, option_type: str) -> dict:
    if get_vol_surface_history is not None:
        try:
            history = get_vol_surface_history(ticker, option_type)
            if history["dates"]:
                history["source"] = "historical_db"
                return history
        except Exception as exc:
            st.warning(f"Historical surface unavailable: {exc}")

    live_history = _load_live_surface_history(ticker, option_type)
    if live_history["dates"]:
        return live_history

    return {"dates": [], "surfaces": [], "source": "none"}


def _load_live_surface_history(ticker: str, option_type: str) -> dict:
    if option_type not in ("call", "put"):
        return {"dates": [], "surfaces": [], "source": "none"}

    snapshot_date = date.today().isoformat()
    rows = []

    try:
        yt = yf.Ticker(ticker)
        expirations = list(yt.options)
    except Exception:
        return {"dates": [], "surfaces": [], "source": "none"}

    if not expirations:
        return {"dates": [], "surfaces": [], "source": "none"}

    df_name = "calls" if option_type == "call" else "puts"
    for expiration in expirations:
        try:
            chain = yt.option_chain(expiration)
            df = getattr(chain, df_name)
        except Exception:
            continue

        for _, row in df.iterrows():
            implied_vol = row.get("impliedVolatility")
            strike = row.get("strike")
            if pd.isna(implied_vol) or pd.isna(strike):
                continue
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "expiration": expiration,
                    "strike": float(strike),
                    "implied_vol": float(implied_vol),
                }
            )

    if not rows:
        return {"dates": [], "surfaces": [], "source": "none"}

    return {"dates": [snapshot_date], "surfaces": rows, "source": "live_yahoo"}


@st.cache_data(ttl=300, show_spinner=False)
def _load_surface_by_date(
    ticker: str,
    option_type: str,
    selected_date: str,
) -> dict:
    if get_surface_by_date is not None:
        try:
            return get_surface_by_date(ticker, option_type, selected_date)
        except Exception as exc:
            st.warning(f"Using mock surface data: {exc}")

    return {
        "expiration": [
            "2026-06-20",
            "2026-06-20",
            "2026-09-18",
            "2026-09-18",
        ],
        "strike": [280.0, 300.0, 280.0, 300.0],
        "implied_vol": [0.24, 0.26, 0.27, 0.29],
    }


@st.cache_data(ttl=300, show_spinner=False)
def _load_latest_spot(ticker: str) -> float | None:
    if get_connection is None:
        return None

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT price
                FROM spot_price
                WHERE ticker = %s
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (ticker.upper(),),
            )
            row = cursor.fetchone()
    except Exception:
        return None

    if not row:
        return None

    return float(row["price"])


def _prepare_surface_frame(
    surface_data: dict,
    selected_date: str,
    spot: float | None = None,
    moneyness_range: tuple[float, float] = (0.6, 1.4),
    dte_range: tuple[int, int] = (14, 540),
    max_iv: float = 1.0,
    trim_top_pct: int = 2,
) -> pd.DataFrame:
    df = pd.DataFrame(surface_data)
    df["expiration_date"] = pd.to_datetime(df["expiration"], errors="coerce")
    snapshot_date = pd.to_datetime(selected_date)
    df["days_to_expiry"] = (df["expiration_date"] - snapshot_date).dt.days
    df["implied_vol"] = pd.to_numeric(df["implied_vol"], errors="coerce")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    df = df.dropna(subset=["strike", "implied_vol", "days_to_expiry"])
    df = df[
        (df["days_to_expiry"] >= dte_range[0])
        & (df["days_to_expiry"] <= dte_range[1])
        & (df["implied_vol"] > 0.01)
        & (df["implied_vol"] <= max_iv)
    ]

    if spot is not None and spot > 0:
        df["moneyness"] = (df["strike"] / spot).round(3)
        df = df[
            (df["moneyness"] >= moneyness_range[0])
            & (df["moneyness"] <= moneyness_range[1])
        ]
    else:
        df["moneyness"] = df["strike"]

    if df.empty:
        return df

    trim_quantile = 1 - (trim_top_pct / 100)
    upper = df["implied_vol"].quantile(trim_quantile)
    return df[df["implied_vol"] <= upper]


def _black_scholes_greeks(inputs: PricingInputs, option_type: str) -> dict:
    d1 = (
        log(inputs.S / inputs.K)
        + (inputs.r + 0.5 * inputs.sigma**2) * inputs.T
    ) / (inputs.sigma * sqrt(inputs.T))
    d2 = d1 - inputs.sigma * sqrt(inputs.T)
    pdf = exp(-0.5 * d1**2) / sqrt(2 * 3.141592653589793)

    if option_type == "call":
        delta = _norm_cdf(d1)
        theta = (
            -inputs.S * pdf * inputs.sigma / (2 * sqrt(inputs.T))
            - inputs.r * inputs.K * exp(-inputs.r * inputs.T) * _norm_cdf(d2)
        ) / 365
        rho = inputs.K * inputs.T * exp(-inputs.r * inputs.T) * _norm_cdf(d2)
    else:
        delta = _norm_cdf(d1) - 1
        theta = (
            -inputs.S * pdf * inputs.sigma / (2 * sqrt(inputs.T))
            + inputs.r
            * inputs.K
            * exp(-inputs.r * inputs.T)
            * _norm_cdf(-d2)
        ) / 365
        rho = -inputs.K * inputs.T * exp(-inputs.r * inputs.T) * _norm_cdf(-d2)

    gamma = pdf / (inputs.S * inputs.sigma * sqrt(inputs.T))
    vega = inputs.S * pdf * sqrt(inputs.T) / 100

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "rho": rho / 100,
    }


def _norm_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def _has_groq_key() -> bool:
    key = os.getenv("GROQ_API_KEY", "").strip()
    return key.startswith("gsk_")


def _prepare_llm_markdown(explanation: str) -> str:
    """Keep currency symbols from being interpreted as LaTeX by Streamlit."""
    return explanation.replace("$", r"\$")


if __name__ == "__main__":
    main()
