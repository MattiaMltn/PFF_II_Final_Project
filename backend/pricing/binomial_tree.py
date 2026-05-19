"""Binomial (CRR) option pricer.

Readable implementation of the Cox-Ross-Rubinstein binomial tree for
pricing European and American options. The code builds a recombining
tree of underlying prices, computes payoffs at expiration and then
works backward to get the fair value at time 0.

This module prioritizes clarity over micro-optimizations so it's easy
to read and understand while remaining numerically equivalent to
standard CRR implementations.
"""

import numpy as np


# Valid option types
VALID_OPTION_TYPES = {"call", "put"}


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


def binomial_tree(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    american: bool,
    n: int = 200,
    verbose: bool = False,
) -> float:
    """Compute option price with the Cox-Ross-Rubinstein binomial tree.

    The CRR model discretizes time into n equal steps of length dt = T/n.
    At each node the underlying can move up by factor u = exp(sigma*sqrt(dt))
    or down by d = 1/u.  The risk-neutral probability of an up-move is
    p = (exp(r*dt) - d) / (u - d).  A recombining tree of (n+1) terminal
    nodes is built, payoffs are evaluated at expiration, and the price is
    recovered by backward induction discounting at the risk-free rate.

    Args:
        S: Current spot price of the underlying asset (must be > 0).
        K: Strike price of the option (must be > 0).
        T: Time to expiry in years (must be > 0).
        r: Continuously-compounded risk-free rate as a decimal (e.g. 0.05 for 5%).
        sigma: Annualised volatility as a decimal (e.g. 0.20 for 20%, must be > 0).
        option_type: 'call' for a call option, 'put' for a put option.
        american: True to allow early exercise (American-style),
                  False for European-style options.
        n: Number of time steps in the tree (default 200).
           Higher values increase accuracy but raise O(n^2) memory and time cost.
        verbose: If True, print debug info (CRR params, tree size, price);
                 useful for debugging and educational purposes.

    Returns:
        Option fair value as a float, in the same currency units as S and K.

    Raises:
        ValueError: If option_type is not 'call' or 'put', or if any of
                    n, T, sigma, S are non-positive.

    Algorithm:
        1. Compute CRR parameters u, d, p from sigma, r, dt.
        2. Build terminal asset prices: S * u^j * d^(n-j) for j in 0..n.
        3. Evaluate payoff at each terminal node.
        4. Backward induction: discount expected value one step at a time;
           for American options also check early-exercise value at each node.

    Examples:
        European call (Black-Scholes equivalent):
        >>> price = binomial_tree(S=100, K=100, T=1.0, r=0.05,
        ...                       sigma=0.20, option_type='call',
        ...                       american=False, n=500)

        American put with early exercise:
        >>> price = binomial_tree(S=100, K=110, T=0.5, r=0.05,
        ...                       sigma=0.25, option_type='put',
        ...                       american=True, n=500)
        # American put >= European put due to early-exercise premium.

    Performance:
        The pricing error relative to Black-Scholes decreases as O(1/n),
        so doubling n halves the error.  n=100 is adequate for most uses;
        n=500-1000 is recommended when high precision is required (e.g.
        for fitting implied volatility or calculating Greeks numerically).
        Memory and CPU scale as O(n^2), so very large n (>5000) may be slow.

    Edge cases:
        - Very short-dated options (T < 0.001): dt becomes tiny and
          floating-point rounding can distort u, d, p. Prefer analytical
          Black-Scholes for T < 0.001.
        - Very high volatility (sigma > 5.0): risk-neutral probability p may
          fall outside [0, 1], indicating the step size is too large; increase n.
        - r = 0 is valid and handled correctly.
    """
    # Input validation
    if option_type not in VALID_OPTION_TYPES:
        raise ValueError(
            f"option_type must be one of {VALID_OPTION_TYPES}, "
            f"got '{option_type}'"
        )

    if n <= 0:
        raise ValueError(f"Number of steps n must be positive, got {n}")

    if T <= 0:
        raise ValueError(f"Time to expiry T must be positive, got {T}")

    if sigma <= 0:
        raise ValueError(f"Volatility sigma must be positive, got {sigma}")

    if S <= 0:
        raise ValueError(f"Spot price S must be positive, got {S}")

    # Time step size
    dt = T / n

    u, d, p = _calculate_crr_parameters(sigma, r, dt)
    if verbose:
        print(f"[DEBUG] CRR Parameters: u={u:.6f}, d={d:.6f}, p={p:.6f}")

    # Discount factor for one time step
    discount = np.exp(-r * dt)

    # Build the asset price tree at maturity (time T)
    # Prices at expiration: for j up-moves the price is S * u**j * d**(n-j)
    asset_prices = np.array([S * (u**j) * (d ** (n - j)) for j in range(n + 1)])
    if verbose:
        print(f"[DEBUG] Tree size: {n} steps, {n + 1} terminal nodes")

    # Calculate option payoff at maturity for each final node
    if option_type == "call":
        # Call payoff: max(S - K, 0)
        option_values = np.maximum(asset_prices - K, 0.0)
    else:  # put
        # Put payoff: max(K - S, 0)
        option_values = np.maximum(K - asset_prices, 0.0)

    # Backward induction through the tree
    # Step back through the tree to compute option values at earlier times
    for i in range(n - 1, -1, -1):
        # Asset prices at step i derived from maturity prices via scaling
        asset_prices_i = asset_prices[:i + 1] * (u ** (n - i))

        # Calculate continuation value at each node
        # Risk-neutral expected value of the option one step ahead,
        # then discounted to the current node
        continuation_values = discount * (
            p * option_values[1:] + (1 - p) * option_values[:-1]
        )

        # For American options, compare continuation vs immediate exercise
        if american:
            # Calculate immediate exercise value at each node
            if option_type == "call":
                exercise_values = np.maximum(asset_prices_i - K, 0.0)
            else:  # put
                exercise_values = np.maximum(K - asset_prices_i, 0.0)

            # Choose the better of continuing or exercising now
            option_values = np.maximum(continuation_values, exercise_values)
        else:
            # For European options, continuation is the only choice
            option_values = continuation_values

    # The value at the root node (time 0) is the option price
    price = float(option_values[0])
    if verbose:
        print(f"[DEBUG] Option price: ${price:.4f}")
    return price