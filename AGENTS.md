# AGENTS.md — PFF II Options Pricing Platform

## Project Overview
Options pricing platform built with Python. Users select a ticker, option type,
expiration and strike. The system prices the option via Binomial Tree (CRR),
computes Greeks, visualizes the historical volatility surface,
and explains results via Claude API.

## Repository Structure
## Stack
- Python 3.11, PEP 8, max line length 88
- PostgreSQL via psycopg2 (Supabase cloud database)
- Streamlit for frontend
- Plotly for 3D visualization
- Claude API (Anthropic) for LLM explanations

## Rules for Agents
- Only modify files in `backend/surface/` and `tests/test_surface.py`
- NEVER modify files in `backend/data/`, `backend/pricing/`, `backend/llm/`, `frontend/`
- NEVER modify `AGENTS.md`, `README.md` directly — open a PR
- All code and comments in English
- Every public function must have type hints and a docstring
- Never store credentials in code — use `.env`
- Use `%s` placeholders for PostgreSQL queries (psycopg2), never `?`
- Always read from database via `backend.data.database.get_connection`
- Run `pytest tests/test_surface.py -v` before every commit

## Git Conventions
- Branch naming: `feature/<description>` or `fix/<description>`
- Commit messages: `type(surface): short description`
  - Types: feat, fix, test, docs, refactor
- Always create a new branch for each task
- Open a Pull Request toward `main` when done

## Database
- Host: Supabase (PostgreSQL cloud)
- Credentials in `.env` — never commit `.env`
- Table for this module: `closing_snapshot`
  - Columns: snapshot_date, expiration, strike, implied_vol, ticker, option_type
- Table is append-only — never UPDATE or DELETE rows 
## Module Interface — `backend/surface/`

### `get_vol_surface_history(ticker, option_type) -> dict`
Returns all historical snapshots for a ticker.
- Input: ticker (str, case-insensitive), option_type ('call' or 'put')
- Output: `{"dates": [...], "surfaces": [{"snapshot_date", "expiration", "strike", "implied_vol"}, ...]}`
- Returns `{"dates": [], "surfaces": []}` if no data found

### `build_surface_grid(ticker, option_type, snapshot_date) -> dict | None`
Builds an interpolated 3D grid for a single date.
- Input: ticker (str), option_type (str), snapshot_date (str, YYYY-MM-DD)
- Output: `{"snapshot_date": ..., "K_grid": [[...]], "T_grid": [[...]], "IV_mesh": [[...]]}`
- Returns `None` if fewer than 4 data points are available for that date
- Grid size: 30×30, interpolation method: cubic (scipy.interpolate.griddata)