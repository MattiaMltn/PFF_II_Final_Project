import traceback

try:
    from backend.data.market_data import get_option_chain, get_pricing_inputs

    print("=== OPTION CHAIN ===")
    chain = get_option_chain("AAPL", "call")
    first_exp = chain['expirations'][4]  
    print(f"Expirations: {chain['expirations'][:3]}")
    print(f"Strikes for {first_exp}: {chain['strikes'][first_exp][:5]}")

    print("\n=== PRICING INPUTS ===")
    strike = chain['strikes'][first_exp][5]
    inputs = get_pricing_inputs("AAPL", first_exp, "call", strike)
    print(f"S (spot):   {inputs.S}")
    print(f"K (strike): {inputs.K}")
    print(f"T (years):  {inputs.T}")
    print(f"r (rate):   {inputs.r}")
    print(f"sigma:      {inputs.sigma}")
    print(f"bid:        {inputs.bid}")
    print(f"ask:        {inputs.ask}")

except Exception as e:
    print(f"ERRORE: {e}")
    traceback.print_exc()

input("\nPremi INVIO per chiudere...")