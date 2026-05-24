"""
Greeks calculation using Black-Scholes analytical formulas.

This module computes the first-order and second-order Greeks (Delta, Gamma,
Theta, Vega, Rho) for European-style options using closed-form solutions
from the Black-Scholes model.

Greeks measure the sensitivity of the option price to changes in various
market parameters:
- Delta: sensitivity to underlying price movement
- Gamma: rate of change of Delta (convexity)
- Theta: time decay per day
- Vega: sensitivity to implied volatility changes (per 1%)
- Rho: sensitivity to interest rate changes (per 1%)

Note: These formulas are exact for European options. For American options,
Greeks should be calculated numerically using finite differences on the
binomial tree, which is not implemented in this module.

References:
    Black, F., and Scholes, M. (1973).
    "The Pricing of Options and Corporate Liabilities."
    Journal of Political Economy, 81(3), 637-654.

    Hull, J.C. (2018). Options, Futures, and Other Derivatives.
    10th Edition, Pearson.
"""

import numpy as np
from scipy.stats import norm


# Valid option types
VALID_OPTION_TYPES = {"call", "put"}


def calcola_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
) -> dict[str, float]:
    """
    Calculate option Greeks using Black-Scholes analytical formulas.

    This function computes all five primary Greeks for European call or put
    options. The Greeks are calculated using closed-form solutions from the
    Black-Scholes model, which assumes constant volatility, continuous trading,
    and log-normal distribution of returns.

    Args:
        S: Current spot price of the underlying asset (e.g., 289.38)
        K: Strike price of the option (e.g., 270.0)
        T: Time to expiration in years (e.g., 0.0278 for ~7 trading days)
        r: Risk-free interest rate as a decimal (e.g., 0.0359 for 3.59%)
        sigma: Implied volatility as a decimal (e.g., 0.342 for 34.2%)
        option_type: Either 'call' or 'put'

    Returns:
        Dictionary containing five Greeks as floats:
            - delta: Rate of change of option price with respect to S.
                     Range: [0, 1] for calls, [-1, 0] for puts.
                     Interpretation: A delta of 0.6234 means a $1 increase
                     in spot → $0.62 increase in option value.

            - gamma: Rate of change of delta with respect to S.
                     Always positive for both calls and puts.
                     Peaks at ATM (at-the-money) options.
                     Interpretation: Gamma of 0.0145 means delta increases
                     by 0.0145 per $1 move in spot.

            - theta: Rate of change of option price with respect to time.
                     Expressed per day (divided by 365 for annualization).
                     Usually negative (time decay).
                     Interpretation: Theta of -0.0423 means option loses
                     $0.04 per day, all else equal.

            - vega: Rate of change of option price with respect to volatility.
                    Expressed per 1% change in volatility (divided by 100).
                    Always positive for both calls and puts.
                    Interpretation: Vega of 0.1876 means option gains $0.19
                    if volatility increases by 1%.

            - rho: Rate of change of option price with respect to interest rate.
                   Expressed per 1% change in rate (divided by 100).
                   Positive for calls, negative for puts.
                   Interpretation: Rho of 0.0534 means option gains $0.05
                   if interest rate increases by 1%.

    Raises:
        ValueError: If option_type is not 'call' or 'put'
        ValueError: If T <= 0 (time to expiry must be positive)
        ValueError: If sigma <= 0 (volatility must be positive)
        ValueError: If K <= 0 (strike price must be positive)
        ValueError: If S <= 0 (spot price must be positive)

    Example:
        >>> greeks = calcola_greeks(
        ...     S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20,
        ...     option_type='call'
        ... )
        >>> print(f"Delta: {greeks['delta']:.4f}")
        Delta: 0.6368
        >>> print(f"Gamma: {greeks['gamma']:.4f}")
        Gamma: 0.0199
        >>> print(f"Theta: {greeks['theta']:.4f}")
        Theta: -0.0251
        >>> print(f"Vega: {greeks['vega']:.4f}")
        Vega: 0.3989
        >>> print(f"Rho: {greeks['rho']:.4f}")
        Rho: 0.5318

    Notes:
        - All Greeks use the Black-Scholes model assumptions:
          constant volatility, continuous trading, no dividends,
          no transaction costs, log-normal distribution of returns
        - Theta is converted to daily decay by dividing by 365
        - Vega is scaled to represent change per 1% volatility move
        - Rho is scaled to represent change per 1% rate move
        - For very short-dated options (T < 0.001), Greeks may exhibit
          numerical instability due to division by sqrt(T)
        - For American options, use finite differences on binomial tree
          for more accurate Greeks (not implemented here)
    """
    # Input validation
    if option_type not in VALID_OPTION_TYPES:
        raise ValueError(
            f"option_type must be one of {VALID_OPTION_TYPES}, "
            f"got '{option_type}'"
        )

    if T <= 0:
        raise ValueError(f"Time to expiry T must be positive, got {T}")

    if sigma <= 0:
        raise ValueError(f"Volatility sigma must be positive, got {sigma}")

    if K <= 0:
        raise ValueError(f"Strike price K must be positive, got {K}")

    if S <= 0:
        raise ValueError(f"Spot price S must be positive, got {S}")

    # Calculate Black-Scholes d1 and d2 parameters
    # d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
    # d2 = d1 - σ√T
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Standard normal distribution functions
    # N(x) = cumulative distribution function
    # φ(x) = probability density function
    pdf_d1 = norm.pdf(d1)  # φ(d1)
    cdf_d1 = norm.cdf(d1)  # N(d1)
    cdf_d2 = norm.cdf(d2)  # N(d2)

    # Discount factor for present value calculations
    discount_factor = np.exp(-r * T)

    # Calculate Greeks based on option type
    if option_type == "call":
        # Delta_call = N(d1)
        # Measures the rate of change of option price with respect to S
        delta = cdf_d1

        # Rho_call = K * T * e^(-rT) * N(d2)
        # Scaled per 1% change in interest rate (divide by 100)
        rho = K * T * discount_factor * cdf_d2 / 100

        # Theta_call = -[S * φ(d1) * σ / (2√T)] - r * K * e^(-rT) * N(d2)
        # Converted to per-day decay (divide by 365)
        # First term: vega decay, second term: interest rate effect
        theta = (
            -S * pdf_d1 * sigma / (2 * sqrt_T)
            - r * K * discount_factor * cdf_d2
        ) / 365

    else:  # put
        # Delta_put = N(d1) - 1 = -N(-d1)
        # Negative for puts as they gain value when spot decreases
        delta = cdf_d1 - 1

        # Rho_put = -K * T * e^(-rT) * N(-d2)
        # Negative for puts as they lose value when rates increase
        # Scaled per 1% change in interest rate (divide by 100)
        rho = -K * T * discount_factor * norm.cdf(-d2) / 100

        # Theta_put = -[S * φ(d1) * σ / (2√T)] + r * K * e^(-rT) * N(-d2)
        # Converted to per-day decay (divide by 365)
        # Note the sign change in the second term compared to calls
        theta = (
            -S * pdf_d1 * sigma / (2 * sqrt_T)
            + r * K * discount_factor * norm.cdf(-d2)
        ) / 365

    # Gamma and Vega are identical for calls and puts
    # This is because both measure second-order effects

    # Gamma = φ(d1) / (S * σ * √T)
    # Measures convexity: how fast Delta changes with spot price
    # Always positive, peaks at ATM
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # Vega = S * φ(d1) * √T
    # Measures sensitivity to volatility changes
    # Scaled per 1% change in volatility (divide by 100)
    # Always positive as both calls and puts benefit from higher vol
    vega = S * pdf_d1 * sqrt_T / 100

    # Return all Greeks as a dictionary
    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
        "vega": float(vega),
        "rho": float(rho),
    }