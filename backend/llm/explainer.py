"""LLM explanation layer using the Groq API."""

from __future__ import annotations

import os
import time

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only without dependency
    def load_dotenv() -> bool:
        return False

import requests


load_dotenv()

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def explain_pricing_result(
    option_params: dict,
    price: float,
    greeks: dict,
) -> str:
    """
    Generate a plain-language explanation of pricing results using Groq.

    Args:
        option_params: Option parameters with ticker, S, K, T, r, sigma,
            option_type, and american.
        price: Option fair value from the pricing engine.
        greeks: Greeks dictionary with delta, gamma, theta, vega, and rho.

    Returns:
        Compact Markdown-formatted explanation in English.
    """
    style = "American" if option_params.get("american") else "European"
    prompt = _build_prompt(option_params, price, greeks, style)
    return _request_groq(prompt, max_tokens=500)


def explain_volatility_surface(surface_summary: dict) -> str:
    """Explain pre-computed volatility-surface statistics using Groq."""
    temporal_context = ""
    if surface_summary.get("first_snapshot"):
        temporal_context = f"""
Temporal comparison:
- First snapshot: {surface_summary['first_snapshot']}
- Latest snapshot: {surface_summary['snapshot_date']}
- Median IV change: {surface_summary['median_iv_change']:+.2%}
- ATM IV change: {surface_summary['atm_iv_change']:+.2%}
"""

    prompt = f"""
You are a quantitative analyst interpreting a filtered implied-volatility
surface for a finance student. Use only the statistics supplied below.
Do not infer events, earnings, liquidity, or arbitrage unless the data
explicitly supports that claim. The chart smoothing is visual only; all
statistics below come from raw filtered observations.

Formatting rules:
- Maximum 190 words.
- Do not add a document title or introductory sentence.
- Write exactly four compact sections with these bold labels:
  **Shape**, **Term structure**, **Data quality**, **Practical insight**.
- Use short paragraphs or bullets, with no heading syntax (#, ##, ###).
- Do not use LaTeX, tables, HTML, or dollar symbols.
- Describe differences in percentage points, not relative percentages.

Surface context:
- Ticker: {surface_summary['ticker']}
- Option type: {surface_summary['option_type']}
- Snapshot: {surface_summary['snapshot_date']}
- Data source: {surface_summary['source']}
- Raw filtered observations: {surface_summary['points']}
- Unique maturities: {surface_summary['maturities']}
- Moneyness coverage: {surface_summary['moneyness_min']:.2f} to
  {surface_summary['moneyness_max']:.2f}
- DTE coverage: {surface_summary['dte_min']} to
  {surface_summary['dte_max']} days
- IV range: {surface_summary['iv_min']:.2%} to
  {surface_summary['iv_max']:.2%}
- Median IV: {surface_summary['iv_median']:.2%}
- ATM IV (K/S within 0.95-1.05): {_format_optional_pct(surface_summary['atm_iv'])}
- Left-wing IV (K/S <= 0.90): {_format_optional_pct(surface_summary['left_wing_iv'])}
- Right-wing IV (K/S >= 1.10): {_format_optional_pct(surface_summary['right_wing_iv'])}
- Short-DTE IV (<= 60 days): {_format_optional_pct(surface_summary['short_iv'])}
- Long-DTE IV (>= 180 days): {_format_optional_pct(surface_summary['long_iv'])}
- Visual smoothing sigma: {surface_summary['smoothing_sigma']:.1f}
{temporal_context}

Explain the observed smile/skew without claiming it is necessarily abnormal.
Mention sparse coverage where a statistic is unavailable. Distinguish raw
market observations from chart interpolation and visual smoothing. State
clearly that smoothing does not alter the reported statistics.
"""
    return _request_groq(prompt, max_tokens=600)


def _request_groq(prompt: str, max_tokens: int) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from the .env file.")
    if not api_key.startswith("gsk_"):
        raise RuntimeError(
            "GROQ_API_KEY has an invalid format; Groq keys start with 'gsk_'."
        )

    response = None
    for attempt in range(3):
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a careful quantitative finance tutor. "
                            "Answer directly, use the supplied numbers only, "
                            "and never claim that model mispricing guarantees "
                            "an arbitrage."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=60,
        )
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        if attempt < 2:
            time.sleep(attempt + 1)

    if response is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Groq request was not sent.")

    response.raise_for_status()

    try:
        explanation = response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Groq returned an unexpected response.") from exc

    if not explanation:
        raise RuntimeError("Groq returned an empty explanation.")

    return explanation


def _format_optional_pct(value: object) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.2%}"


def explain_unified(inputs: dict, price: float, greeks: dict) -> str:
    """
    Backward-compatible alias for handoff documents using explain_unified.

    Args:
        inputs: Option parameters and pricing inputs.
        price: Option fair value from the pricing engine.
        greeks: Greeks dictionary with delta, gamma, theta, vega, and rho.

    Returns:
        Markdown-formatted explanation.
    """
    return explain_pricing_result(inputs, price, greeks)


def _build_prompt(
    option_params: dict,
    price: float,
    greeks: dict,
    style: str,
) -> str:
    market_context = _build_market_context(option_params, price)
    return f"""
You are a quantitative analyst explaining option pricing results to a
finance student. Be concise (max 160 words) and use standard Markdown.
Only explain the supplied calculations. Do not recalculate the option price,
invent missing data, or describe a model-market difference as a guaranteed
arbitrage opportunity.
The displayed price always comes from the CRR binomial tree. The displayed
Greeks come from Black-Scholes formulas for European options, or from the
project's American-option Greeks implementation when explicitly supplied.

Formatting rules:
- Do not add a document title or introductory sentence.
- Write exactly four compact sections with these bold labels:
  **Price**, **Risk**, **Market comparison**, **Practical insight**.
- Use short paragraphs or bullets, with no heading syntax (#, ##, ###).
- Write currency as "USD 12.34"; never use the dollar symbol.
- Do not use LaTeX, mathematical delimiters, tables, or HTML.

Option parameters:
- Ticker: {option_params['ticker']}
- Type: {style} {option_params['option_type']}
- Spot (S): USD {option_params['S']:.2f}
- Strike (K): USD {option_params['K']:.2f}
- Maturity (T): {option_params['T']:.4f} years
- Risk-free rate (r): {option_params['r']:.2%}
- Implied volatility (sigma): {option_params['sigma']:.2%}

Results:
- **Price**: USD {price:.4f}
- **Delta**: {greeks['delta']:.4f}
- **Gamma**: {greeks['gamma']:.4f}
- **Theta**: {greeks['theta']:.4f} per day
- **Vega**: {greeks['vega']:.4f} per 1% vol
- **Rho**: {greeks['rho']:.4f} per 1% rate

Market comparison:
{market_context}

Explain: (1) what the price means relative to intrinsic value,
(2) what the Greeks tell us about this position's risk profile,
(3) how the model price compares with the available market quote,
(4) one practical insight or data-quality caveat for the trader.

Do not claim that the binomial-tree price was calculated with Black-Scholes.
"""


def _build_market_context(option_params: dict, price: float) -> str:
    bid = option_params.get("bid")
    ask = option_params.get("ask")

    if not _is_positive_number(bid) or not _is_positive_number(ask):
        return (
            "- Bid / ask: unavailable or non-positive\n"
            "- Model comparison: unreliable because there is no active "
            "two-sided quote"
        )

    bid_value = float(bid)
    ask_value = float(ask)
    market_mid = (bid_value + ask_value) / 2
    model_difference = price - market_mid
    difference_pct = (
        model_difference / market_mid * 100 if market_mid > 0 else 0.0
    )

    return (
        f"- Bid / ask: USD {bid_value:.2f} / USD {ask_value:.2f}\n"
        f"- Market mid: USD {market_mid:.4f}\n"
        f"- Model minus market mid: USD {model_difference:.4f} "
        f"({difference_pct:+.2f}%)"
    )


def _is_positive_number(value: object) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
