Project Diary — Pricing Engine (P1)
Module: Pricing Engine — backend/pricing/
Team member: Giorgio Galdiolo
Project: PFF II Options Pricing Platform — 2026

Week 1 — Initial Implementation
Session 1 — Project setup and binomial tree implementation
What we did:
Set up the branch Giorgio_Galdiolo from main and implemented the core
pricing engine from scratch. Created the module structure under backend/pricing/
with two files: binomial_tree.py and greeks.py.
binomial_tree.py — CRR Binomial Tree:
Implemented the Cox-Ross-Rubinstein model for both European and American options.
The algorithm discretizes time into n steps of length dt = T/n. At each node
the underlying moves up by u = exp(sigma * sqrt(dt)) or down by d = 1/u.
The risk-neutral probability is p = (exp(r * dt) - d) / (u - d). Payoffs are
evaluated at the terminal nodes and the price is recovered by backward induction.
For American options, the algorithm checks at each node whether immediate exercise
is optimal by comparing the intrinsic value against the continuation value.
greeks.py — Black-Scholes Greeks:
Implemented all five Greeks analytically using closed-form Black-Scholes formulas:

Delta: first derivative of price with respect to S
Gamma: second derivative of price with respect to S
Theta: time decay (expressed per day, divided by 365)
Vega: sensitivity to volatility (per 1% change, divided by 100)
Rho: sensitivity to interest rate (per 1% change, divided by 100)

Commit: feat(pricing): implement CRR binomial tree and Black-Scholes Greeks

Week 2 — Refactoring and Improvements
The team created a structured improvement roadmap (PRICING_IMPROVEMENTS.md) with
8 tasks to be executed incrementally using Claude Code CLI as an AI agent. This
approach was chosen to demonstrate iterative development and professional commit
history, as required by the project evaluation criteria.
AI tool used: Claude Code CLI (claude command in PowerShell terminal)
Workflow: For each task — Read PRICING_IMPROVEMENTS.md and execute Task N. Show me the changes before applying. — review diff — Apply these changes — run regression tests — commit.

Task 1 — Comprehensive Input Validation
What we did:
Added explicit input validation to binomial_tree() for all numeric parameters.
Before this task, invalid inputs (e.g. negative spot price, zero volatility) would
either produce a cryptic numpy error or silently return a nonsensical result.
Changes made:

Validate n > 0 (number of steps must be positive)
Validate T > 0 (time to expiry, prevents division by zero in dt = T/n)
Validate sigma > 0 (volatility, prevents mathematical invalidity in CRR parameters)
Validate S > 0 (spot price must be positive for financial validity)
All error messages include the received value for easier debugging

Commit: refactor(pricing): add comprehensive input validation to binomial tree

Task 2 — Extract CRR Parameters Helper Function
What we did:
Extracted the CRR parameter calculation (u, d, p) into a dedicated helper
function _crr_parameters(sigma, r, dt). This reduced code duplication and made
the main function easier to read.
Commit: refactor(pricing): extract CRR parameters into helper function

Task 3 — Add Verbose Debug Mode
What we did:
Added an optional verbose: bool = False parameter to binomial_tree(). When
verbose=True, the function prints three debug messages during execution:
[DEBUG] CRR Parameters: u=1.014142, d=0.986057, p=0.501760
[DEBUG] Tree size: 200 steps, 201 terminal nodes
[DEBUG] Option price: $10.4406
This is useful for educational purposes (understanding what the model is doing
internally) and for debugging unexpected pricing results. The default verbose=False
means existing code is completely unaffected.
Commit: feat(pricing): add verbose debug mode to binomial tree

Task 4 — Optimize Array Operations
What we did:
Identified a performance bottleneck in the backward induction loop. The original
implementation recalculated all asset prices at every step of the loop:
python# Before: recalculates array from scratch at every iteration (slow)
for i in range(n - 1, -1, -1):
    asset_prices = np.array([S * (u**j) * (d**(i-j)) for j in range(i+1)])
The optimization pre-calculates all asset prices at maturity once, then uses
array slicing in the backward loop instead of recomputing:
python# After: calculate once at maturity, slice in the loop (fast)
asset_prices_terminal = S * (u ** np.arange(n, -1, -1)) * (d ** np.arange(0, n+1))
for i in range(n - 1, -1, -1):
    asset_prices = asset_prices_terminal[...] # sliced, not recomputed
Regression test: Verified that numerical results are identical before and after
the optimization (difference < 1e-10 for all test cases).
Benchmark results:
MetricBeforeAfterImprovement10 calls, n=5000.490s0.044s~11x fasterCall europea (n=200)10.440591259910.4405912599Identical ✅Put americana (n=200)15.625332040315.6253320403Identical ✅
Commit: perf(pricing): optimize binomial tree array operations

Task 5 — Standardize Option Type Validation
What we did:
Both binomial_tree() and calcola_greeks() validated option_type independently
with slightly different patterns and error messages. This was a maintenance risk:
if a new option type were added, both files would need to be updated separately.
Solution: Defined a shared constant at module level in binomial_tree.py:
pythonVALID_OPTION_TYPES = {"call", "put"}
Used the same constant and the same error message format in both functions.
In greeks.py, the constant is imported from binomial_tree.py to keep a
single source of truth.
Verification: Confirmed that passing option_type='banana' raises the same
ValueError in both modules with identical message format.
Commit: refactor(pricing): standardize option type validation

Task 6 — Enhance Docstring Documentation
What we did:
Significantly expanded the docstring of binomial_tree() from a minimal description
to a comprehensive reference document (3036 characters, 63 lines). Added:

Detailed CRR algorithm explanation with mathematical notation
American option usage example (deep ITM put, demonstrating early exercise)
Convergence rate documentation: error decreases as O(1/n), so doubling n halves
the error; n=200 is adequate for most uses, n=500-1000 recommended for high precision
Performance notes: memory and CPU scale as O(n²)
Edge cases section: very short-dated options (T < 0.001) where floating-point
rounding can distort CRR parameters; very high volatility (sigma > 5.0) where
risk-neutral probability may fall outside [0,1]

Commit: docs(pricing): enhance binomial tree docstring

Task 7 — Add Greeks Input Validation
What we did:
Applied the same input validation pattern from Task 1 to calcola_greeks().
Before this task, greeks.py may have caught T <= 0 and sigma <= 0 implicitly
(via mathematical errors), but did not explicitly validate S > 0 and K > 0.
Changes made:

Validate S > 0
Validate K > 0
Verify T > 0 message format matches binomial_tree.py
Verify sigma > 0 message format matches binomial_tree.py

Commit: refactor(greeks): add comprehensive input validation

Task 8 — Comprehensive pytest Test Suite (AI Agent PR)
What we did:
Created a complete test suite in tests/test_pricing.py with 30 tests organized
in two classes: TestBinomialTree (15 tests) and TestGreeks (15 tests).
This task was executed entirely by an AI agent (Claude Code CLI) as required
by the project evaluation criteria ("at least one Pull Request made by an AI agent").
Agent workflow:

Launched Claude Code CLI in the project directory (claude in PowerShell)
Gave the agent this task:

   Read PRICING_IMPROVEMENTS.md and execute Task 8.
   Create a new branch called test/pricing-engine, commit the test file,
   push to origin and open a Pull Request toward Giorgio_Galdiolo.
   Do not merge — leave it open for human review.

The agent autonomously: read the file, wrote tests/test_pricing.py,
created branch test/pricing-engine, committed, pushed, and opened PR #2
The team reviewed the code on GitHub
All 30 tests were verified locally before approving
PR #2 was approved and merged

Tests implemented:
TestBinomialTree:

test_european_call_convergence — BT converges to Black-Scholes as n increases
test_european_put_convergence — same for puts
test_put_call_parity_european — verifies C - P = S - K·exp(-rT)
test_american_vs_european_put — American put >= European put
test_deep_itm_call — deep ITM call approaches lower bound S - K·exp(-rT)
test_deep_otm_call — deep OTM call approaches zero
test_invalid_option_type — ValueError for invalid option type
test_invalid_parameters — ValueError for n<=0, T<=0, sigma<=0, S<=0
(+ 7 additional tests)

TestGreeks:

test_call_delta_range — call delta always in [0, 1]
test_put_delta_range — put delta always in [-1, 0]
test_gamma_positive — gamma always positive
test_vega_positive — vega always positive
test_gamma_same_for_call_put — gamma identical for call/put (put-call parity)
test_vega_same_for_call_put — vega identical for call/put
test_theta_negative_for_atm — ATM options have negative theta
test_greeks_invalid_parameters — ValueError for T<=0, sigma<=0
(+ 7 additional tests)

Result: 30/30 tests passing
GitHub PR: #2 — test/pricing-engine → Giorgio_Galdiolo
Commit: test(pricing): add comprehensive pytest test suite
Agent used: Claude Code CLI (Anthropic)

Summary — Pricing Engine Completion
TaskTypeDescriptionCommit prefix1refactorInput validation — binomial treerefactor2refactorCRR helper functionrefactor3featVerbose debug modefeat4perfArray optimization (~11x speedup)perf5refactorValidation standardizationrefactor6docsEnhanced docstringdocs7refactorInput validation — Greeksrefactor8testComprehensive test suite via AI agent PRtest
Total commits for Pricing Engine module: 10+
Test coverage: 30 tests, 2 classes, all passing
Performance improvement: ~11x speedup for large n values
AI agent contribution: Task 8 test suite written and committed autonomously by Claude Code CLI, PR #2 opened and merged