"""Comprehensive pytest test suite for the pricing engine.

Covers:
- binomial_tree: convergence to Black-Scholes, put-call parity,
  American vs European, boundary conditions, and input validation.
- calcola_greeks: delta/gamma/vega ranges, call/put symmetry,
  theta sign, and input validation.
"""

import math
from typing import Literal

import pytest

from backend.pricing.binomial_tree import binomial_tree
from backend.pricing.greeks import calcola_greeks
from backend.data.mock_data import MOCK_PRICING_INPUTS


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
    def test_invalid_parameters(self, overrides: dict[str, int] | dict[str, float], match: Literal['n must be positive'] | Literal['T must be positive'] | Literal['sigma must be positive'] | Literal['S must be positive']):
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
    def test_greeks_invalid_parameters(self, overrides: dict[str, float], match: Literal['T must be positive'] | Literal['sigma must be positive'] | Literal['K must be positive'] | Literal['S must be positive']):
        """ValueError raised for non-positive T, sigma, K, or S."""
        kwargs = dict(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                      option_type="call")
        kwargs.update(overrides)
        with pytest.raises(ValueError, match=match):
            calcola_greeks(**kwargs)


# ---------------------------------------------------------------------------
# TestBinomialTreeExtended — Step 2 additions
# ---------------------------------------------------------------------------

class TestBinomialTreeExtended:
    """Additional structural and validation tests for binomial_tree."""

    def test_european_call_absolute_value(self):
        """European call (S=K=100, T=1, r=0.05, σ=0.2) must be ≈10.45 (tol 0.05)."""
        price = binomial_tree(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
                              option_type="call", american=False, n=200)
        assert abs(price - 10.45) < 0.05

    def test_european_put_absolute_value(self):
        """European put (S=K=100, T=1, r=0.05, σ=0.2) must be ≈5.57 (tol 0.05)."""
        price = binomial_tree(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
                              option_type="put", american=False, n=200)
        assert abs(price - 5.57) < 0.05

    def test_american_vs_european_call(self):
        """American call >= European call (no dividends — early exercise never optimal)."""
        american = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                 option_type="call", american=True, n=500)
        european = binomial_tree(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                 option_type="call", american=False, n=500)
        assert american >= european - 1e-10

    def test_invalid_strike_zero(self):
        """binomial_tree must raise ValueError for K=0 (FINDING: currently missing)."""
        with pytest.raises(ValueError):
            binomial_tree(S=_S, K=0.0, T=_T, r=_r, sigma=_sigma,
                          option_type="call", american=False)

    def test_invalid_strike_negative(self):
        """binomial_tree must raise ValueError for K<0 (FINDING: currently missing)."""
        with pytest.raises(ValueError):
            binomial_tree(S=_S, K=-50.0, T=_T, r=_r, sigma=_sigma,
                          option_type="call", american=False)


# ---------------------------------------------------------------------------
# TestGreeksExtended — Step 2 additions
# ---------------------------------------------------------------------------

class TestGreeksExtended:
    """Additional Greeks tests: delta extremes, delta parity, rho sign."""

    def test_deep_itm_call_delta(self):
        """Deep ITM call delta (S=150, K=100) must be ≈1.0 within 0.05."""
        g = calcola_greeks(S=150.0, K=100.0, T=_T, r=_r, sigma=_sigma,
                           option_type="call")
        assert g["delta"] == pytest.approx(1.0, abs=0.05)

    def test_deep_otm_call_delta(self):
        """Deep OTM call delta (S=50, K=100) must be ≈0.0 within 0.05."""
        g = calcola_greeks(S=50.0, K=100.0, T=_T, r=_r, sigma=_sigma,
                           option_type="call")
        assert g["delta"] == pytest.approx(0.0, abs=0.05)

    def test_put_call_delta_parity(self):
        """Put-call delta parity: delta_put = delta_call - 1 (exact identity)."""
        call_g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="call")
        put_g  = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                                option_type="put")
        assert put_g["delta"] == pytest.approx(call_g["delta"] - 1.0, abs=1e-10)

    def test_call_rho_positive(self):
        """Rho must be positive for calls (higher rates increase call value)."""
        g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="call")
        assert g["rho"] > 0.0

    def test_put_rho_negative(self):
        """Rho must be negative for puts (higher rates reduce PV of exercise)."""
        g = calcola_greeks(S=_S, K=_K, T=_T, r=_r, sigma=_sigma,
                           option_type="put")
        assert g["rho"] < 0.0


# ---------------------------------------------------------------------------
# TestPriceMonotonicity — Step 2 additions
# ---------------------------------------------------------------------------

class TestPriceMonotonicity:
    """Price monotonicity in S, K, sigma, and T."""

    def test_call_increases_with_spot(self):
        """Call price must strictly increase as spot price rises (K fixed)."""
        prices = [
            binomial_tree(S=s, K=100.0, T=1.0, r=0.05, sigma=0.20,
                          option_type="call", american=False, n=200)
            for s in [80.0, 90.0, 100.0, 110.0, 120.0]
        ]
        for i in range(len(prices) - 1):
            assert prices[i] < prices[i + 1]

    def test_put_decreases_with_spot(self):
        """Put price must strictly decrease as spot price rises (K fixed)."""
        prices = [
            binomial_tree(S=s, K=100.0, T=1.0, r=0.05, sigma=0.20,
                          option_type="put", american=False, n=200)
            for s in [80.0, 90.0, 100.0, 110.0, 120.0]
        ]
        for i in range(len(prices) - 1):
            assert prices[i] > prices[i + 1]

    def test_prices_increase_with_volatility(self):
        """Both call and put prices must increase with volatility."""
        for otype in ("call", "put"):
            prices = [
                binomial_tree(S=100.0, K=100.0, T=1.0, r=0.05, sigma=s,
                              option_type=otype, american=False, n=200)
                for s in [0.10, 0.20, 0.30, 0.40]
            ]
            for i in range(len(prices) - 1):
                assert prices[i] < prices[i + 1]

    def test_call_decreases_with_strike(self):
        """Call price must strictly decrease as strike rises (S fixed)."""
        prices = [
            binomial_tree(S=100.0, K=k, T=1.0, r=0.05, sigma=0.20,
                          option_type="call", american=False, n=200)
            for k in [80.0, 90.0, 100.0, 110.0, 120.0]
        ]
        for i in range(len(prices) - 1):
            assert prices[i] > prices[i + 1]

    def test_put_increases_with_strike(self):
        """Put price must strictly increase as strike rises (S fixed)."""
        prices = [
            binomial_tree(S=100.0, K=k, T=1.0, r=0.05, sigma=0.20,
                          option_type="put", american=False, n=200)
            for k in [80.0, 90.0, 100.0, 110.0, 120.0]
        ]
        for i in range(len(prices) - 1):
            assert prices[i] < prices[i + 1]

    def test_call_approaches_intrinsic_at_expiry(self):
        """ITM call value approaches max(S-K, 0) as T → 0."""
        price = binomial_tree(S=110.0, K=100.0, T=1 / 252, r=0.05, sigma=0.20,
                              option_type="call", american=False, n=200)
        assert price == pytest.approx(10.0, abs=0.5)


# ---------------------------------------------------------------------------
# TestInterfaceCompatibility — Step 4
# ---------------------------------------------------------------------------

class TestInterfaceCompatibility:
    """Verify MOCK_PRICING_INPUTS is compatible with binomial_tree and calcola_greeks."""

    def test_mock_inputs_positive_values(self):
        """All MOCK_PRICING_INPUTS numeric fields satisfy the positivity constraints."""
        p = MOCK_PRICING_INPUTS
        assert p.S > 0
        assert p.K > 0
        assert p.T > 0
        assert p.sigma > 0

    def test_mock_inputs_float_types(self):
        """MOCK_PRICING_INPUTS S, K, T, r, sigma are all float-compatible."""
        p = MOCK_PRICING_INPUTS
        for val in (p.S, p.K, p.T, p.r, p.sigma):
            assert isinstance(float(val), float)

    def test_mock_data_binomial_tree_call(self):
        """MOCK_PRICING_INPUTS produces a valid non-negative call price."""
        p = MOCK_PRICING_INPUTS
        price = binomial_tree(S=p.S, K=p.K, T=p.T, r=p.r, sigma=p.sigma,
                              option_type="call", american=False, n=200)
        assert isinstance(price, float)
        assert price >= 0.0

    def test_mock_data_binomial_tree_put(self):
        """MOCK_PRICING_INPUTS produces a valid non-negative put price."""
        p = MOCK_PRICING_INPUTS
        price = binomial_tree(S=p.S, K=p.K, T=p.T, r=p.r, sigma=p.sigma,
                              option_type="put", american=False, n=200)
        assert isinstance(price, float)
        assert price >= 0.0

    def test_mock_data_greeks_call(self):
        """MOCK_PRICING_INPUTS produces a complete Greeks dict for calls."""
        p = MOCK_PRICING_INPUTS
        greeks = calcola_greeks(S=p.S, K=p.K, T=p.T, r=p.r, sigma=p.sigma,
                                option_type="call")
        assert set(greeks.keys()) == {"delta", "gamma", "theta", "vega", "rho"}
        assert all(isinstance(v, float) for v in greeks.values())

    def test_mock_data_greeks_put(self):
        """MOCK_PRICING_INPUTS produces a complete Greeks dict for puts."""
        p = MOCK_PRICING_INPUTS
        greeks = calcola_greeks(S=p.S, K=p.K, T=p.T, r=p.r, sigma=p.sigma,
                                option_type="put")
        assert set(greeks.keys()) == {"delta", "gamma", "theta", "vega", "rho"}
        assert all(isinstance(v, float) for v in greeks.values())

    def test_mock_bid_ask_valid(self):
        """MOCK_PRICING_INPUTS: bid and ask are positive and bid <= ask."""
        p = MOCK_PRICING_INPUTS
        assert p.bid > 0
        assert p.ask > 0
        assert p.bid <= p.ask

    def test_option_type_not_in_pricing_inputs(self):
        """PricingInputs has no option_type field — caller must supply it separately."""
        with pytest.raises(AttributeError):
            _ = MOCK_PRICING_INPUTS.option_type
