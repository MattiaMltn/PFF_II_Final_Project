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


def binomial_tree(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    american: bool,
    n: int = 200,
) -> float:
    """Compute option price with the Cox-Ross-Rubinstein binomial tree.

    Simple, well-documented implementation. Parameters:
      - `S`, `K`, `T`, `r`, `sigma`: standard option inputs
      - `option_type`: 'call' or 'put'
      - `american`: True if early exercise is allowed
      - `n`: number of time steps

    The function returns the option price as a float. It raises
    ValueError for invalid inputs such as non-positive time or
    non-positive volatility.
    """
    # Input validation
    if option_type not in ["call", "put"]:
        raise ValueError("option_type must be 'call' or 'put'")

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

    # CRR model parameters
    # Up and down factors for the recombining tree
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u

    # Risk-neutral probability of up move
    # No-arbitrage probability under risk-neutral measure
    p = (np.exp(r * dt) - d) / (u - d)

    # Discount factor for one time step
    discount = np.exp(-r * dt)

    # Build the asset price tree at maturity (time T)
    # Prices at expiration: for j up-moves the price is S * u**j * d**(n-j)
    asset_prices = np.array([S * (u**j) * (d ** (n - j)) for j in range(n + 1)])

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
        # Asset prices at time step i
        # At step i, there are i+1 nodes
        asset_prices = np.array(
            [S * (u**j) * (d ** (i - j)) for j in range(i + 1)]
        )

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
                exercise_values = np.maximum(asset_prices - K, 0.0)
            else:  # put
                exercise_values = np.maximum(K - asset_prices, 0.0)

            # Choose the better of continuing or exercising now
            option_values = np.maximum(continuation_values, exercise_values)
        else:
            # For European options, continuation is the only choice
            option_values = continuation_values

    # The value at the root node (time 0) is the option price
    return float(option_values[0])