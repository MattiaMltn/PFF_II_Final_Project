"""Comprehensive pytest test suite for the pricing engine.

Covers:
- binomial_tree: convergence to Black-Scholes, put-call parity,
  American vs European, boundary conditions, and input validation.
- calcola_greeks: delta/gamma/vega ranges, call/put symmetry,
  theta sign, and input validation.
"""

import math

import pytest

from backend.pricing.binomial_tree import binomial_tree
from backend.pricing.greeks import calcola_greeks


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _black_scholes(S: float, K: float, T: float, r: float, sigma: float,
                   option_type: str) -> float:
    """Closed-form Black-Scholes price for European options."""
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# Standard ATM parameters reused across tests
_S, _K, _T, _r, _sigma = 100.0, 100.0, 1.0, 0.05, 0.20


# ---------------------------------------------------------------------------
# TestBinomialTree
# ---------------------------------------------------------------------------

class TestBinomialTree:
    """Tests for backend.pricing.binomial_tree.binomial_tree."""

    def test_european_call_convergence(self):
        """BT European call converges to Black-Scholes price within 0.2%."""
        bs = _black_scholes(_S, _K, _T, _r, _sigma, "call")
        bt = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="call", american=False, n=500)
        assert bt == pytest.approx(bs, rel=2e-3)

    def test_european_put_convergence(self):
        """BT European put converges to Black-Scholes price within 0.2%."""
        bs = _black_scholes(_S, _K, _T, _r, _sigma, "put")
        bt = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="put", american=False, n=500)
        assert bt == pytest.approx(bs, rel=2e-3)

    def test_put_call_parity_european(self):
        """European put-call parity holds: C - P = S - K * exp(-rT)."""
        call = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                             option_type="call", american=False, n=500)
        put = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                            option_type="put", american=False, n=500)
        forward = _S - _K * math.exp(-_r * _T)
        assert call - put == pytest.approx(forward, abs=1e-2)

    def test_american_vs_european_put(self):
        """American put price >= European put due to early-exercise premium."""
        american = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                 option_type="put", american=True, n=500)
        european = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                 option_type="put", american=False, n=500)
        assert american >= european - 1e-10

    def test_deep_itm_call(self):
        """Deep ITM call price ≈ S - K * exp(-rT) (intrinsic forward value)."""
        bt = binomial_tree(S=200.0, K=100.0, T=_T, r=_r, sigma=_sigma,
                           option_type="call", american=False, n=500)
        intrinsic = 200.0 - 100.0 * math.exp(-_r * _T)
        assert bt == pytest.approx(intrinsic, rel=1e-2)

    def test_deep_otm_call(self):
        """Deep OTM call price ≈ 0."""
        bt = binomial_tree(S=50.0, K=200.0, T=_T, r=_r, sigma=_sigma,
                           option_type="call", american=False, n=500)
        assert bt == pytest.approx(0.0, abs=1e-4)

    def test_invalid_option_type(self):
        """ValueError raised for unrecognised option_type string."""
        with pytest.raises(ValueError, match="option_type"):
            binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                          option_type="forward", american=False)

    @pytest.mark.parametrize("overrides,match", [
        ({"n": 0},        "n must be positive"),
        ({"n": -5},       "n must be positive"),
        ({"T": 0.0},      "T must be positive"),
        ({"T": -1.0},     "T must be positive"),
        ({"sigma": 0.0},  "sigma must be positive"),
        ({"sigma": -0.1}, "sigma must be positive"),
        ({"S": 0.0},      "S must be positive"),
        ({"S": -50.0},    "S must be positive"),
    ])
    def test_invalid_parameters(self, overrides, match):
        """ValueError raised for non-positive n, T, sigma, or S."""
        kwargs = dict(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                      option_type="call", american=False)
        kwargs.update(overrides)
        with pytest.raises(ValueError, match=match):
            binomial_tree(**kwargs)


# ---------------------------------------------------------------------------
# TestGreeks
# ---------------------------------------------------------------------------

class TestGreeks:
    """Tests for backend.pricing.greeks.calcola_greeks."""

    def test_call_delta_range(self):
        """Call delta lies in [0, 1]."""
        g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="call")
        assert 0.0 <= g["delta"] <= 1.0

    def test_put_delta_range(self):
        """Put delta lies in [-1, 0]."""
        g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="put")
        assert -1.0 <= g["delta"] <= 0.0

    def test_gamma_positive(self):
        """Gamma is always positive for both calls and puts."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                               option_type=otype)
            assert g["gamma"] > 0.0

    def test_vega_positive(self):
        """Vega is always positive for both calls and puts."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                               option_type=otype)
            assert g["vega"] > 0.0

    def test_gamma_same_for_call_put(self):
        """Gamma is identical for call and put with the same parameters."""
        call_g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="call")
        put_g  = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="put")
        assert call_g["gamma"] == pytest.approx(put_g["gamma"])

    def test_vega_same_for_call_put(self):
        """Vega is identical for call and put with the same parameters."""
        call_g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="call")
        put_g  = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="put")
        assert call_g["vega"] == pytest.approx(put_g["vega"])

    def test_theta_negative_for_atm(self):
        """ATM option theta is negative (time decay hurts the holder)."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                               option_type=otype)
            assert g["theta"] < 0.0

    @pytest.mark.parametrize("overrides,match", [
        ({"T": 0.0},      "T must be positive"),
        ({"T": -0.5},     "T must be positive"),
        ({"sigma": 0.0},  "sigma must be positive"),
        ({"sigma": -0.2}, "sigma must be positive"),
        ({"K": 0.0},      "K must be positive"),
        ({"K": -10.0},    "K must be positive"),
        ({"S": 0.0},      "S must be positive"),
        ({"S": -100.0},   "S must be positive"),
    ])
    def test_greeks_invalid_parameters(self, overrides, match):
        """ValueError raised for non-positive T, sigma, K, or S."""
        kwargs = dict(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                      option_type="call")
        kwargs.update(overrides)
        with pytest.raises(ValueError, match=match):
            calcola_greeks(**kwargs)
