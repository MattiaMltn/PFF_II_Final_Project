# PFF_II_Final_Project 

# PFF_II_Final_Project
**Programming in Finance II — Progetto 2.7 — 2026**

## Panoramica
Piattaforma per il pricing di opzioni europee e americane
tramite Binomial Tree con Implied Volatility di mercato.
Visualizza la volatility surface storica con slider temporale.
LLM spiega i risultati in linguaggio naturale.

## Team
- [Nome] — Data layer e database
- [Nome] — Pricing engine (Binomial Tree, Greeks)
- [Nome] — Volatility surface
- [Nome] — Frontend Streamlit e LLM


## Avvio
streamlit run frontend/app.py

## Struttura
backend/data/      → database SQLite, market data
backend/pricing/   → Binomial Tree, Greeks
backend/llm/       → Claude API
frontend/app.py    → Dashboard Streamlit
tests/             → Test unitari
docs/              → Documentazione LaTeX
