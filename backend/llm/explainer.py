"""LLM explanation layer using Claude API."""

from __future__ import annotations

from types import SimpleNamespace

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only without dependency
    def load_dotenv() -> bool:
        return False

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only without dependency
    class _MissingAnthropicClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(
                "The 'anthropic' package is required. Install dependencies "
                "with: pip install -r requirements.txt"
            )

    anthropic = SimpleNamespace(Anthropic=_MissingAnthropicClient)


load_dotenv()


def explain_pricing_result(
    option_params: dict,
    price: float,
    greeks: dict,
) -> str:
    """
    Generate a plain-language explanation of pricing results using Claude.

    Args:
        option_params: Option parameters with ticker, S, K, T, r, sigma,
            option_type, and american.
        price: Option fair value from the pricing engine.
        greeks: Greeks dictionary with delta, gamma, theta, vega, and rho.

    Returns:
        Markdown-formatted explanation in English.
    """
    client = anthropic.Anthropic()
    style = "American" if option_params.get("american") else "European"
    prompt = _build_prompt(option_params, price, greeks, style)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


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
    return f"""
You are a quantitative analyst explaining option pricing results to a
finance student. Be concise (max 200 words) and use markdown formatting.

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

Explain: (1) what the price means relative to intrinsic value,
(2) what the Greeks tell us about this position's risk profile,
(3) one practical insight for the trader.
"""
