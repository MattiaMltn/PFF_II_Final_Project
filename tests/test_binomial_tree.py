import math
import pytest
from backend.pricing.binomial_tree import binomial_tree


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(S, K, T, r, sigma, option_type: str):
    """Black-Scholes closed-form price for European calls and puts."""
    if T <= 0 or sigma <= 0:
        raise ValueError("T and sigma must be positive for Black-Scholes")

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    elif option_type == "put":
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_binomial_matches_black_scholes(option_type):
    """Compare the CRR binomial price (European) to Black-Scholes.

    The binomial approximation should converge to the Black-Scholes
    price as the number of steps increases. We use a reasonably large
    number of steps and accept a small relative tolerance.
    """
    S = 100.0
    K = 100.0
    T = 1.0
    r = 0.05
    sigma = 0.20

    # Use a relatively large number of steps for good convergence
    n = 500

    bs = black_scholes_price(S, K, T, r, sigma, option_type)
    bt = binomial_tree(S=S, K=K, T=T, r=r, sigma=sigma, option_type=option_type, american=False, n=n)

    # Allow small relative difference (0.2%)
    assert bt == pytest.approx(bs, rel=2e-3)
