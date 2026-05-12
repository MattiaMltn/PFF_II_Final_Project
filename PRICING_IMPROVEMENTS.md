markdown# Pricing Engine Improvement Tasks

This document contains a series of incremental improvements for the Pricing Engine module.
Each task should be executed separately, reviewed, and committed individually.

---

## Task 1: Comprehensive Input Validation

Read `backend/pricing/binomial_tree.py`

Add comprehensive input validation at the beginning of the binomial_tree function:

1. Check that `n > 0` (number of steps must be positive)
   - Raise ValueError with message: "Number of steps n must be positive, got {n}"

2. Check that `T > 0` (time to expiry must be positive)
   - Raise ValueError with message: "Time to expiry T must be positive, got {T}"

3. Check that `sigma > 0` (volatility must be positive)
   - Raise ValueError with message: "Volatility sigma must be positive, got {sigma}"

4. Check that `S > 0` (spot price must be positive)
   - Raise ValueError with message: "Spot price S must be positive, got {S}"

Add these checks right after the existing option_type validation.
Show me the diff before applying.

**Commit message:**
refactor(pricing): add comprehensive input validation to binomial tree

Validate n > 0 with clear error message
Validate T > 0 to prevent division by zero
Validate sigma > 0 for mathematical correctness
Validate S > 0 for financial validity
Improve error messages with received values


---

## Task 2: Extract CRR Parameters Helper Function

Read `backend/pricing/binomial_tree.py`

Extract the calculation of u, d, and p into a separate private helper function:

```python
def _calculate_crr_parameters(sigma: float, r: float, dt: float) -> tuple[float, float, float]:
    """
    Calculate Cox-Ross-Rubinstein model parameters.
    
    Args:
        sigma: Volatility as decimal
        r: Risk-free rate as decimal
        dt: Time step size
    
    Returns:
        Tuple of (u, d, p) where:
        - u: Up factor
        - d: Down factor
        - p: Risk-neutral probability
    """
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp(r * dt) - d) / (u - d)
    return u, d, p
```

Then use this helper in binomial_tree():
```python
u, d, p = _calculate_crr_parameters(sigma, r, dt)
```

This improves code organization and readability.
Show me the refactored code before applying.

**Commit message:**
refactor(pricing): extract CRR parameters into helper function

Create _calculate_crr_parameters() private helper
Improve code organization and modularity
Add comprehensive docstring for helper
Main binomial_tree() function is cleaner


---

## Task 3: Add Verbose Debug Mode

Read `backend/pricing/binomial_tree.py`

Add an optional `verbose: bool = False` parameter to binomial_tree().

When `verbose=True`, print the following information:
1. After calculating u, d, p:
[DEBUG] CRR Parameters: u={u:.6f}, d={d:.6f}, p={p:.6f}

2. After building the tree:
[DEBUG] Tree size: {n} steps, {n+1} terminal nodes

3. Before returning:
[DEBUG] Option price: ${price:.4f}

Add the verbose parameter to the function signature and docstring.
Document that it's useful for debugging and educational purposes.
Show me the implementation.

**Commit message:**
feat(pricing): add verbose debug mode to binomial tree

Add optional verbose parameter (default False)
Print u, d, p parameters when verbose=True
Display tree size and computational details
Show final price before returning
Useful for debugging and educational purposes


---

## Task 4: Optimize Array Operations

Read `backend/pricing/binomial_tree.py`

The current implementation recalculates asset_prices in every iteration of the backward loop:
```python
asset_prices = np.array([S * (u**j) * (d ** (i - j)) for j in range(i + 1)])
```

This is inefficient. Optimize by:

1. Pre-calculating all asset prices at maturity once
2. Use array slicing in the backward loop instead of recalculating
3. Reduce memory allocations

Show me an optimized version that improves computational efficiency.

**Commit message:**
perf(pricing): optimize binomial tree array operations

Eliminate redundant asset price calculations
Use array slicing instead of list comprehensions
Reduce memory allocations in backward loop
Improve performance for large n values


---

## Task 5: Standardize Option Type Validation

Read both `backend/pricing/binomial_tree.py` and `backend/pricing/greeks.py`

Both functions validate option_type but in slightly different ways.
Create consistency:

1. At the top of the binomial_tree.py module (after imports), add:
```python
   # Valid option types
   VALID_OPTION_TYPES = {"call", "put"}
```

2. In both functions, use this for validation:
```python
   if option_type not in VALID_OPTION_TYPES:
       raise ValueError(
           f"option_type must be one of {VALID_OPTION_TYPES}, "
           f"got '{option_type}'"
       )
```

3. Do the same in greeks.py (import the constant from binomial_tree if needed,
   or define it in both files for module independence)

Show me the refactored validation in both files.

**Commit message:**
refactor(pricing): standardize option type validation

Define VALID_OPTION_TYPES constant
Use consistent validation across both modules
Improve error messages with available options
Enhance type safety and maintainability


---

## Task 6: Enhance Docstring Documentation

Read `backend/pricing/binomial_tree.py`

Enhance the main docstring with:

1. More detailed explanation of how the CRR model works
2. Additional usage example showing American put with early exercise
3. Performance notes about convergence rate (error decreases as O(1/n))
4. Notes about when to use higher n values
5. Edge cases section warning about very short-dated options (T < 0.001)

Keep the existing docstring structure but make it more comprehensive.
Show me the enhanced version.

**Commit message:**
docs(pricing): enhance binomial tree docstring

Add detailed CRR algorithm explanation
Include American option usage example
Document convergence rate characteristics
Add performance recommendations
Note edge cases and numerical considerations


---

## Task 7: Add Greeks Input Validation

Read `backend/pricing/greeks.py`

Add the same input validation as in binomial_tree.py:
- Check S > 0
- Check K > 0 (strike must be positive)
- Check T > 0 (already exists, verify message format)
- Check sigma > 0 (already exists, verify message format)

Ensure error messages are consistent with binomial_tree.py style.
Show me the additions.

**Commit message:**
refactor(greeks): add comprehensive input validation

Validate S > 0 with clear error message
Validate K > 0 for strike price
Align validation with binomial_tree.py
Ensure consistent error message format


---

## Task 8: Create Comprehensive Test Suite

Create a new file `tests/test_pricing.py` with comprehensive pytest tests.

Include the following test functions:

**For binomial_tree:**
1. `test_european_call_convergence()` - Test that BT converges to BS as n increases
2. `test_european_put_convergence()` - Same for puts
3. `test_put_call_parity_european()` - Verify C - P = S - K*exp(-rT)
4. `test_american_vs_european_put()` - American put >= European put
5. `test_deep_itm_call()` - Deep ITM call ≈ S - K*exp(-rT)
6. `test_deep_otm_call()` - Deep OTM call ≈ 0
7. `test_invalid_option_type()` - Test ValueError for invalid type
8. `test_invalid_parameters()` - Test ValueError for n<=0, T<=0, etc.

**For greeks:**
9. `test_call_delta_range()` - Delta between 0 and 1 for calls
10. `test_put_delta_range()` - Delta between -1 and 0 for puts
11. `test_gamma_positive()` - Gamma always positive
12. `test_vega_positive()` - Vega always positive
13. `test_gamma_same_for_call_put()` - Gamma identical for call/put
14. `test_vega_same_for_call_put()` - Vega identical for call/put
15. `test_theta_negative_for_atm()` - ATM options have negative theta
16. `test_greeks_invalid_parameters()` - Test ValueError for T<=0, sigma<=0

Use proper pytest structure with:
- Class organization (TestBinomialTree, TestGreeks)
- Docstrings for each test
- Appropriate assertions with tolerance for floating point
- Use pytest.raises for error tests

Create the complete test file following pytest best practices.

**Commit message:**
test(pricing): add comprehensive pytest test suite

Add 16 test functions covering all functionality
Test convergence, boundary conditions, mathematical properties
Verify input validation and error handling
Test Greeks ranges and relationships
Organize tests in classes for clarity
Achieve >90% code coverage


---

## Execution Instructions

To execute these tasks with Claude Code:

1. Start Claude Code in the project directory:
claude

2. For each task, tell Claude:
Read PRICING_IMPROVEMENTS.md and execute Task [number].
Show me the changes before applying.

3. Review the proposed changes

4. If approved, tell Claude:
Apply these changes

5. Exit Claude Code and commit:
exit
   
   Then in PowerShell:
git add .
git commit -m "[use the commit message from the task]"
git push origin feature/pricing-engine

6. Repeat for the next task

---

## Notes

- Execute tasks in order (they may depend on previous changes)
- Review each diff carefully before applying
- Test the code after each change
- Each task should result in exactly one commit
- All changes should maintain backward compatibility
- Total expected commits: 8
- Estimated time: 3-4 hours distributed over 2-3 days

📥 Come salvarlo
Metodo 1 — In VS Code:

Apri VS Code
File → New File
Incolla tutto il contenuto sopra
File → Save As → PRICING_IMPROVEMENTS.md
Salvalo nella root del progetto (stessa cartella di README.md)


Metodo 2 — Con PowerShell:
powershellcd C:\Users\galdi\OneDrive\Desktop\Project_ProgrammingII\PFF_II_Final_Project

# Copia il file (copia il contenuto sopra negli appunti, poi:)
notepad PRICING_IMPROVEMENTS.md

# In Notepad: Ctrl+V per incollare, poi Ctrl+S per salvare e chiudi

✅ Dopo averlo salvato
Committalo come meta-documentazione:
bashgit add PRICING_IMPROVEMENTS.md
git commit -m "docs: add improvement roadmap for Pricing Engine

Create structured task list for incremental improvements:
- 8 tasks covering validation, refactoring, optimization
- Each task with clear instructions and commit messages
- Designed for execution with Claude Code
- Distributed over 2-3 days for professional commit history"

git push origin feature/pricing-engine

🚀 Poi inizia con i task
powershellclaude

Read PRICING_IMPROVEMENTS.md and execute Task 1.
Show me the changes before applying.