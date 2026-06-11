"""LLM explanation layer using the Gemini API."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only without dependency
    def load_dotenv() -> bool:
        return False

import requests


load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def explain_pricing_result(
    option_params: dict,
    price: float,
    greeks: dict,
) -> str:
    """
    Generate a plain-language explanation of pricing results using Gemini.

    Args:
        option_params: Option parameters with ticker, S, K, T, r, sigma,
            option_type, and american.
        price: Option fair value from the pricing engine.
        greeks: Greeks dictionary with delta, gamma, theta, vega, and rho.

    Returns:
        Markdown-formatted explanation in English.
    """
    style = "American" if option_params.get("american") else "European"
    prompt = _build_prompt(option_params, price, greeks, style)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the .env file.")

    response = requests.post(
        f"{GEMINI_API_URL}/{model}:generateContent",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 400,
                "temperature": 0.3,
            },
        },
        timeout=60,
    )
    response.raise_for_status()

    try:
        parts = response.json()["candidates"][0]["content"]["parts"]
        explanation = "".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Gemini returned an unexpected response.") from exc

    if not explanation:
        raise RuntimeError("Gemini returned an empty explanation.")

    return explanation


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
finance student. Be concise (max 200 words) and use markdown formatting.
Only explain the supplied calculations. Do not recalculate the option price,
invent missing data, or describe a model-market difference as a guaranteed
arbitrage opportunity.

## Option parameters
- Ticker: {option_params['ticker']}
- Type: {style} {option_params['option_type']}
- Spot (S): ${option_params['S']:.2f}
- Strike (K): ${option_params['K']:.2f}
- Maturity (T): {option_params['T']:.4f} years
- Risk-free rate (r): {option_params['r']:.2%}
- Implied volatility (sigma): {option_params['sigma']:.2%}

## Results
- **Price**: ${price:.4f}
- **Delta**: {greeks['delta']:.4f}
- **Gamma**: {greeks['gamma']:.4f}
- **Theta**: {greeks['theta']:.4f} per day
- **Vega**: {greeks['vega']:.4f} per 1% vol
- **Rho**: {greeks['rho']:.4f} per 1% rate

## Market comparison
{market_context}

Explain: (1) what the price means relative to intrinsic value,
(2) what the Greeks tell us about this position's risk profile,
(3) how the model price compares with the available market quote,
(4) one practical insight or data-quality caveat for the trader.

If this is an American option, mention briefly that the displayed Greeks use
European Black-Scholes formulas while the price uses an American binomial tree.
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
        f"- Bid / ask: ${bid_value:.2f} / ${ask_value:.2f}\n"
        f"- Market mid: ${market_mid:.4f}\n"
        f"- Model minus market mid: ${model_difference:.4f} "
        f"({difference_pct:+.2f}%)"
    )


def _is_positive_number(value: object) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
