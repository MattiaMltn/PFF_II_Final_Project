# AGENTS.md

**Programming in Finance II — Project 2.7 — 2026**

## Objective

Read `README.md` in full before starting. It contains the project context,
the pipeline flow and the interface contracts between modules. Then build
the module assigned to you as specified in the corresponding section of `README.md`.

## Tools

Use freely: `python`, `pip install`, `pytest`, `git status`, `git diff`, `cat`, `ls`

Always ask before: `git commit`, `git push`, any write to `options_data.db`,
any live API call to yfinance, FactSet or Anthropic.

Never: modify files outside your assigned module, run `DROP TABLE` or unfiltered
`DELETE FROM`, store credentials in code, use `git push --force`.

## Standards

All code, comments and docstrings must be written in English, follow PEP 8
and target Python 3.11 with a maximum line length of 88 characters.
Every public function must have type hints and a docstring with Args and Returns.
Credentials must be loaded from `.env` via `python-dotenv` — never hardcoded.

## Data Handling

`options_data.db` is append-only — never update or delete existing rows.
`option_type` must be `"call"` or `"put"` in lowercase.
`expiration` must follow `YYYY-MM-DD` format and raise `ValueError` if in the past.
Time to expiry `T` must be expressed in years as `trading_days / 252`.
Risk-free rate `r` must be a decimal — `0.045`, not `4.5`.

## Module Boundaries

Each module exposes a single public interface file listed in `README.md`.
Do not import from another module's internal files — only from its public interface.

## Validation

Run the test suite for your module before finishing:

```bash
pytest tests/test_<your_module>.py -v
```

All tests must pass. Do not modify a test to make it pass.

## Checkpoints

Ask for confirmation before proceeding if any of the following apply:

- Your implementation would change a public interface signature defined in `README.md`
- The database schema differs from the one specified in `README.md`
- A new dependency not listed in `requirements.txt` is needed
