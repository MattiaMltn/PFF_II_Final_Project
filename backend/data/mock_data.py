"""Static fixtures for offline development and unit testing.

Usage:
    from backend.data.mock_data import MOCK_CHAIN, MOCK_PRICING_INPUTS
"""

from backend.data.market_data import PricingInputs

MOCK_CHAIN: dict = {
    "expirations": ["2026-06-19", "2026-09-18", "2026-12-18"],
    "strikes": {
        "2026-06-19": [170.0, 175.0, 180.0, 185.0, 190.0, 195.0, 200.0],
        "2026-09-18": [165.0, 170.0, 175.0, 180.0, 185.0, 190.0, 195.0, 200.0],
        "2026-12-18": [160.0, 165.0, 170.0, 175.0, 180.0, 185.0, 190.0],
    },
}

MOCK_PRICING_INPUTS: PricingInputs = PricingInputs(
    S=178.72,
    K=180.0,
    T=45 / 252,
    r=0.045,
    sigma=0.2831,
    bid=4.20,
    ask=4.35,
)
