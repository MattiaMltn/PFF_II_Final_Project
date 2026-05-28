# Project Diary — Integration Testing
Module: `backend/pricing/` and `backend/surface/`
Date: 2026-05-28
Executed by: Claude Code (claude-sonnet-4-6)

---

## Step 1 — Existing tests (baseline)

Command: `pytest tests/test_pricing.py tests/test_surface.py -v`

**Prerequisite issue found**: `scipy` was not installed. Running the suite
immediately raised `ModuleNotFoundError: No module named 'scipy'` during
collection. Fixed with `pip install scipy`.

After installation:

| File | Tests | Result |
|------|-------|--------|
| `tests/test_pricing.py` | 30 | 30/30 passed |
| `tests/test_surface.py` | 12 | 12/12 passed |

**Total baseline: 42/42 passed.**

---

## Step 2 — Pricing engine: structural and financial sanity

New tests added to `tests/test_pricing.py` (classes `TestBinomialTreeExtended`,
`TestGreeksExtended`, `TestPriceMonotonicity`).

### Results

| Test | Result | Notes |
|------|--------|-------|
| `test_european_call_absolute_value` | PASS | BT call = 10.44, within 0.05 of 10.45 |
| `test_european_put_absolute_value` | PASS | BT put = 5.56, within 0.05 of 5.57 |
| `test_american_vs_european_call` | PASS | American call >= European call |
| `test_invalid_strike_zero` | **FAIL** | **FINDING #1** (see below) |
| `test_invalid_strike_negative` | **FAIL** | **FINDING #1** (see below) |
| `test_deep_itm_call_delta` | PASS | delta ≈ 0.991 for S=150, K=100 |
| `test_deep_otm_call_delta` | PASS | delta ≈ 0.001 for S=50, K=100 |
| `test_put_call_delta_parity` | PASS | delta_put = delta_call − 1 exactly |
| `test_call_rho_positive` | PASS | rho > 0 for calls |
| `test_put_rho_negative` | PASS | rho < 0 for puts |
| `test_call_increases_with_spot` | PASS | strictly monotone in S |
| `test_put_decreases_with_spot` | PASS | strictly monotone in S |
| `test_prices_increase_with_volatility` | PASS | vega property holds |
| `test_call_decreases_with_strike` | PASS | monotone in K |
| `test_put_increases_with_strike` | PASS | monotone in K |
| `test_call_approaches_intrinsic_at_expiry` | PASS | T=1/252: price ≈ 10.0 ± 0.5 |

### Finding #1 — `binomial_tree()` missing K validation

**Severity: Medium**

`binomial_tree()` validates `S`, `T`, `sigma`, `n` but does NOT validate the
strike price `K`. Passing `K=0` or `K<0` silently produces nonsensical results
(negative payoffs, numerically unstable tree) instead of raising `ValueError`.

By contrast, `calcola_greeks()` correctly validates `K > 0`.

**Recommended fix** (do not apply — report only):
Add the following check inside `binomial_tree()` after the existing `S > 0`
validation:

```python
if K <= 0:
    raise ValueError(f"Strike price K must be positive, got {K}")
```

---

## Step 3 — Volatility surface: structural and financial sanity

New tests added to `tests/test_surface.py`.

### Results

| Test | Result | Notes |
|------|--------|-------|
| `test_no_nan_in_implied_vol` | PASS | module passes through DB floats |
| `test_no_inf_in_implied_vol` | PASS | module passes through DB floats |
| `test_implied_vol_in_valid_range` | PASS | mock data in (0.01, 5.0) |
| `test_moneyness_filter_applied` | **FAIL** | **FINDING #2** (see below) |
| `test_calendar_spread_condition` | PASS | IV(T2) >= IV(T1) at same strike |
| `test_butterfly_spread_condition` | PASS | convexity holds on clean data |
| `test_smile_atm_is_local_minimum` | PASS | ATM IV is local minimum |
| `test_smoothness_no_large_jumps` | PASS | max adjacent jump = 0.03 < 0.10 |

### Finding #2 — `get_vol_surface_history()` has no moneyness filter

**Severity: Medium**

`surface.py` returns every row from the `closing_snapshot` table without any
filtering. Strikes with extreme moneyness (e.g., moneyness = K/S < 0.7 or
> 1.3) are included in the output unchanged. The SCOPE specifies that "no deep
OTM/ITM outliers" should appear in the surface output.

The module also has no access to a spot price, which is required to compute
moneyness. The filter is therefore architecturally missing: either the
downstream caller (frontend) must apply it, or `save_closing.py` must enforce
it before writing to the database.

**Recommended fix** (do not apply — report only):
Two options:

1. **Upstream enforcement** (preferred): in `save_closing.py`, filter rows
   before inserting into `closing_snapshot` so that only strikes with
   `0.7 <= K/S <= 1.3` are stored. Keeps the surface module stateless.

2. **Downstream filter**: add a `moneyness_range=(0.7, 1.3)` parameter to
   `get_vol_surface_history()` and accept the spot price as an argument so the
   module can compute K/S and exclude outliers at read time.

### Additional finding — no-arbitrage conditions not validated

**Severity: Low**

`surface.py` passes raw database rows directly to the caller with no
no-arbitrage validation layer. If the database contains calendar spread
violations (IV(T2) < IV(T1)) or butterfly violations (negative convexity),
they propagate silently to the surface visualization.

**Recommended fix** (do not apply — report only):
Add a post-query sanitization step inside `get_vol_surface_history()` that
logs a warning (but does not raise) when calendar spread or butterfly
violations are detected, so the frontend can display a data-quality alert.

---

## Step 4 — Interface compatibility with data layer

New tests added to `tests/test_pricing.py` (class `TestInterfaceCompatibility`).
All tests use `MOCK_PRICING_INPUTS` from `backend/data/mock_data.py` — no
network or database calls.

### Results

| Test | Result | Notes |
|------|--------|-------|
| `test_mock_inputs_positive_values` | PASS | S, K, T, sigma all > 0 |
| `test_mock_inputs_float_types` | PASS | all fields are float-compatible |
| `test_mock_data_binomial_tree_call` | PASS | no error, returns float >= 0 |
| `test_mock_data_binomial_tree_put` | PASS | no error, returns float >= 0 |
| `test_mock_data_greeks_call` | PASS | returns dict with 5 float keys |
| `test_mock_data_greeks_put` | PASS | returns dict with 5 float keys |
| `test_mock_bid_ask_valid` | PASS | bid=4.20 <= ask=4.35, both > 0 |
| `test_option_type_not_in_pricing_inputs` | PASS | AttributeError as expected |

### Finding #3 — `PricingInputs` does not include `option_type`

**Severity: Low (design note)**

`PricingInputs` is a `NamedTuple` with fields `S, K, T, r, sigma, bid, ask`.
The SCOPE specification ("get_pricing_inputs() returns S, K, T, r, sigma,
option_type") is inaccurate: `option_type` is not part of the tuple.

This is intentional design: `option_type` is a UI selection made by the user
before calling `get_pricing_inputs()`, not a market data value fetched from the
database. The frontend must hold `option_type` in its own state and pass it
separately to `binomial_tree()` and `calcola_greeks()`.

No code change is needed. The SCOPE documentation should be updated to clarify
this.

---

## Step 5 — Summary

### Test totals after all additions

| File | Tests | Passed | Failed |
|------|-------|--------|--------|
| `tests/test_pricing.py` | 54 | 52 | 2 |
| `tests/test_surface.py` | 20 | 19 | 1 |
| **Total** | **74** | **71** | **3** |

### Findings summary

| # | Location | Description | Severity | Recommended fix |
|---|----------|-------------|----------|-----------------|
| 1 | `binomial_tree()` | No `K <= 0` validation — silently computes with invalid strike | Medium | Add `if K <= 0: raise ValueError(...)` |
| 2 | `get_vol_surface_history()` | No moneyness filter — deep OTM/ITM strikes pass through | Medium | Filter in `save_closing.py` before DB write, or add param to surface function |
| 3 | `PricingInputs` / SCOPE doc | `option_type` absent from tuple — SCOPE spec is inaccurate | Low | Update SCOPE documentation; no code change needed |
| 4 | `get_vol_surface_history()` | No no-arbitrage validation layer | Low | Add warning-level check for calendar/butterfly violations |

### Financial sanity — all pass

All financial properties of `binomial_tree()` and `calcola_greeks()` are
correctly implemented:
- Black-Scholes convergence (call 10.44, put 5.56 — within 0.05 of reference)
- Put-call parity (error < 0.01)
- American >= European for both calls and puts
- Delta: call ∈ (0,1), put ∈ (−1,0); put-call parity; deep ITM ≈ 1.0, OTM ≈ 0.0
- Gamma and Vega always positive; Theta negative for ATM; Rho correct signs
- Monotonicity: price moves in the correct direction as S, K, σ, T vary

### Interface compatibility — passes with noted design gap

`MOCK_PRICING_INPUTS` flows cleanly into both `binomial_tree()` and
`calcola_greeks()` with no type errors. The only compatibility gap is that
`option_type` must be supplied by the caller (not present in `PricingInputs`),
which is an intentional design choice, not a bug.
