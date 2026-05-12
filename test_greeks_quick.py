"""Quick test for greeks.py"""

from backend.pricing.greeks import calcola_greeks

# Test 1: ATM call
print("=== Test 1: ATM Call ===")
greeks = calcola_greeks(100.0, 100.0, 1.0, 0.05, 0.20, "call")
print(f"Delta: {greeks['delta']:.4f} (expected ~0.64)")
print(f"Gamma: {greeks['gamma']:.4f} (expected ~0.02)")
print(f"Theta: {greeks['theta']:.4f} (expected negative)")
print(f"Vega:  {greeks['vega']:.4f} (expected ~0.40)")
print(f"Rho:   {greeks['rho']:.4f} (expected positive)")

# Test 2: ATM put
print("\n=== Test 2: ATM Put ===")
greeks = calcola_greeks(100.0, 100.0, 1.0, 0.05, 0.20, "put")
print(f"Delta: {greeks['delta']:.4f} (expected negative ~-0.36)")
print(f"Gamma: {greeks['gamma']:.4f} (should be same as call)")
print(f"Vega:  {greeks['vega']:.4f} (should be same as call)")
print(f"Rho:   {greeks['rho']:.4f} (expected negative)")

# Test 3: With real market data (mock)
print("\n=== Test 3: Real market data ===")
greeks = calcola_greeks(289.38, 270.0, 0.0278, 0.0359, 0.342, "call")
print(f"Delta: {greeks['delta']:.4f}")
print(f"Gamma: {greeks['gamma']:.4f}")
print(f"Theta: {greeks['theta']:.4f} (per day)")
print(f"Vega:  {greeks['vega']:.4f} (per 1% vol)")
print(f"Rho:   {greeks['rho']:.4f} (per 1% rate)")

print("\n✅ All tests completed!")