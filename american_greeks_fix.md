# American Options Greeks — Problem and Fix

## The Problem

`calcola_greeks()` in `backend/pricing/greeks.py` uses Black-Scholes
analytical formulas for all options, regardless of whether the option
is European or American.

This means that when the user selects an American option in the UI,
the system computes:

- **Price** via `binomial_tree(american=True)` — correctly accounts for
  early exercise at every node via backward induction
- **Greeks** via `calcola_greeks()` — uses Black-Scholes, which has no
  concept of early exercise and always assumes European-style payoff

The two results are produced by different models on the same parameters.

---

## Why It Matters

The Black-Scholes Greeks are exact for European options. For American
options they are an approximation that breaks down in specific situations.

The most significant case is the **American put delta** for deep ITM options.

Consider a put with S=80, K=100, T=1, r=0.05, sigma=0.20:

- European put: it is optimal to wait until expiry — the delta reflects
  the full probability distribution of future prices
- American put: early exercise is optimal now — the holder would receive
  K-S=20 immediately. The delta approaches -1 faster than the European
  case because the probability of continued holding decreases

Black-Scholes returns a delta that is less negative than the true American
delta. A trader using this delta to hedge would be under-hedged.

The same logic applies to theta: an American put that should be exercised
immediately has theta ≈ 0 (no more time value), while Black-Scholes
reports a negative theta implying ongoing time decay.

For **calls without dividends** the problem does not arise — it is never
optimal to exercise an American call early, so American call Greeks equal
European call Greeks exactly.

---

## The Solution

Compute Greeks via **finite differences on the binomial tree** when
`american=True`. This perturbs each input parameter slightly and measures
how the binomial tree price changes — the same model used for pricing.

The function signature becomes:

```python
def calcola_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    american: bool = False,   # NEW parameter
    n: int = 200,             # NEW parameter
) -> dict[str, float]:
```

When `american=False` (default): existing Black-Scholes code runs
unchanged. Full backward compatibility.

When `american=True`: finite differences on `binomial_tree()`:

```python
from backend.pricing.binomial_tree import binomial_tree

dS   = S * 0.01       # 1% of spot
dsig = 0.001          # 0.1 vol point
dr   = 0.0001         # 1 basis point
dt   = 1.0 / 252      # one trading day

def bt(S_, T_, r_, sig_):
    return binomial_tree(S_, K, T_, r_, sig_, option_type, True, n)

p0    = bt(S,    T,    r,    sigma)
p_sup = bt(S+dS, T,    r,    sigma)
p_sdn = bt(S-dS, T,    r,    sigma)
p_vup = bt(S,    T,    r,    sigma+dsig)
p_vdn = bt(S,    T,    r,    sigma-dsig)
p_rup = bt(S,    T,    r+dr, sigma)
p_rdn = bt(S,    T,    r-dr, sigma)
p_tdn = bt(S,    T-dt, r,    sigma) if T > dt else None

delta = (p_sup - p_sdn) / (2 * dS)
gamma = (p_sup - 2*p0 + p_sdn) / dS**2
vega  = (p_vup - p_vdn) / (2 * dsig) / 100
rho   = (p_rup - p_rdn) / (2 * dr)   / 100
theta = (p_tdn - p0)    / dt / 365 if p_tdn is not None else 0.0
```

This requires **9 binomial tree evaluations** instead of 1. With n=200
the total computation time remains well under one second.

---

## Impact on the Frontend

`app.py` must pass the `american` flag to `calcola_greeks()`:

```python
# before
greeks = calcola_greeks(S=inputs.S, K=inputs.K, T=inputs.T,
                        r=inputs.r, sigma=inputs.sigma,
                        option_type=option_type)

# after
greeks = calcola_greeks(S=inputs.S, K=inputs.K, T=inputs.T,
                        r=inputs.r, sigma=inputs.sigma,
                        option_type=option_type,
                        american=american)
```

No other change is needed in the frontend.

---

## Tests to Add

Add a class `TestGreeksAmerican` in `tests/test_pricing.py`:

```python
class TestGreeksAmerican:

    def test_american_put_delta_itm_more_negative_than_european(self):
        """Deep ITM American put delta must be more negative than European."""
        eur = calcola_greeks(S=80, K=100, T=1.0, r=0.05, sigma=0.20,
                             option_type="put", american=False)
        amr = calcola_greeks(S=80, K=100, T=1.0, r=0.05, sigma=0.20,
                             option_type="put", american=True)
        assert abs(amr["delta"]) > abs(eur["delta"])

    def test_american_call_delta_equals_european(self):
        """American call delta equals European call delta (no early exercise)."""
        eur = calcola_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                             option_type="call", american=False)
        amr = calcola_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                             option_type="call", american=True)
        assert amr["delta"] == pytest.approx(eur["delta"], abs=0.01)

    def test_american_gamma_positive(self):
        """American Greeks: gamma must be positive for both call and put."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                               option_type=otype, american=True)
            assert g["gamma"] > 0.0

    def test_american_vega_positive(self):
        """American Greeks: vega must be positive for both call and put."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                               option_type=otype, american=True)
            assert g["vega"] > 0.0

    def test_american_theta_negative_atm(self):
        """American Greeks: theta must be negative for ATM options."""
        for otype in ("call", "put"):
            g = calcola_greeks(S=100, K=100, T=1.0, r=0.05, sigma=0.20,
                               option_type=otype, american=True)
            assert g["theta"] < 0.0
```