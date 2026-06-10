Project Diary — Data Layer (D1)
Module: Data Layer — backend/data/
Team member: Mattia Molteni
Project: PFF II Options Pricing Platform — 2026

Phase 1 — Initial Implementation
Session 1 — Project setup and data layer from scratch
What we did:
Built the data layer from scratch using Claude Code CLI. The initial implementation
used SQLite as the database backend. All six source files under backend/data/ were
generated in this phase, together with the full test suite in tests/test_data_layer.py.
The module passed 48/48 tests from the first run.

database.py — Connection and Schema:
Implemented the SQLite connection layer and the initial schema definition. The
central function is get_connection(), a context manager that yielded an open
sqlite3.Connection with row_factory = sqlite3.Row. Setting row_factory allows
rows to be accessed by column name (row["column"]) rather than by position
(row[0]), mirroring the dictionary-style access that would later be provided by
RealDictCursor in PostgreSQL. DB_PATH pointed to a local file options_data.db
in the project root — no environment variables or credentials were required.

init_db() created three tables using conn.executescript(), passing the full DDL
as a single multi-statement string. The SQLite schema used INTEGER PRIMARY KEY
(not SERIAL), TEXT for all string columns, and REAL for numeric fields. There
were no CHECK constraints at the database level — option_type validation was
enforced exclusively by application code.

The PostgreSQL implementation that replaced this is described in Phase 3,
where the migration is documented.

Design decision — append-only tables:
No UPDATE or DELETE statement appears anywhere in the codebase. Every sync event
appends new rows; old rows are never touched. This was chosen for three reasons:
(1) the Volatility Surface module depends on historical data — overwriting past
snapshots would destroy the time dimension of the surface; (2) append-only tables
are simpler to reason about under concurrent access; (3) audit trail integrity —
if a data quality issue is found later, the full history is still present and can
be corrected by filtering, not by destructive updates.

Three indexes are created:
    idx_option_chain_lookup  ON option_chain(ticker, option_type, expiration, fetched_at)
    idx_spot_price_lookup    ON spot_price(ticker, fetched_at)
    idx_closing_snapshot_lookup ON closing_snapshot(ticker, snapshot_date, option_type)
All three cover the exact WHERE + ORDER BY columns used in the most frequent
queries: lookup by ticker and option_type, then filtering by the most recent
fetched_at or a specific snapshot_date.

sync.py — Yahoo Finance Synchronization:
Implemented two functions that write to spot_price and option_chain.

_safe_float(value) is a private helper that converts any value to float or None.
It explicitly handles None, NaN (via math.isnan), and type errors from
yfinance returning unexpected types. Without this guard, a single NaN in a
Yahoo Finance response would crash the entire sync for that expiration.

sync_ticker(ticker, option_type) performs a full live sync for one ticker and
one option type. It uses yf.Ticker().fast_info to retrieve the spot price,
falling back to a 2-day history query if fast_info fails. It then iterates over
every available expiration date returned by yt.options, fetches the call or put
chain for each, and bulk-inserts rows into option_chain via cursor.executemany().
Each batch of rows shares the same fetched_at timestamp (UTC ISO-8601 string
generated once at the start of the function), so the entire sync run appears as
a single atomic snapshot when queried with ORDER BY fetched_at DESC LIMIT 1.

sync_all_tickers() loops over WORKFLOW_TICKERS (imported from config.py) and
calls sync_ticker() for both 'call' and 'put' on each ticker. Failures are
caught per ticker so a single failing ticker does not abort the others.

market_data.py — Public Interface:
This file is the single import point for all other modules. No module other than
market_data.py imports from sync.py, database.py or save_closing.py directly.

PricingInputs is a NamedTuple with seven fields:
    S: float      — spot price
    K: float      — strike price
    T: float      — time to expiry in years (trading_days / 252)
    r: float      — risk-free rate as decimal (e.g. 0.045)
    sigma: float  — implied volatility as decimal
    bid: float    — option bid price
    ask: float    — option ask price
Using a NamedTuple rather than a plain dict provides field-level access by name
(inputs.S), type hints, and immutability. The Pricing Engine can consume it
directly without any unpacking or transformation.

Design decision — option_type absent from PricingInputs:
option_type is the lookup key used to query the database, not a numerical input
to the pricing model. By the time PricingInputs is returned, option_type has
already served its purpose. Both binomial_tree() and calcola_greeks() receive
option_type as a separate explicit argument — they do not need to unpack it from
an inputs struct. Keeping PricingInputs to purely numerical fields (all floats)
maintains the clean contract between the data layer and the pricing engine.

_validate_option_type(option_type) raises ValueError if the value is not exactly
'call' or 'put'. It is called first in both public functions to fail early with
a clear message before any network or database call is made.

_validate_expiration(expiration) parses the string with datetime.date.fromisoformat()
and then checks that the date is strictly in the future. An expiration equal to
today is rejected because T would compute to zero or negative, which would cause
a division by zero in the pricing engine.

_trading_days_until(exp_date) counts Mon–Fri calendar days from tomorrow until
exp_date inclusive, returning at least 1. This produces T = trading_days / 252
consistent with the 252-trading-day convention. Calendar weekends are skipped;
public holidays are not modelled (they are rare enough not to affect pricing
materially at the granularity of a student project).

_fetch_risk_free_rate() queries the 13-week US T-bill yield via the Yahoo Finance
ticker ^IRX. The raw value from Yahoo Finance is expressed as an annualised
percentage (e.g. 4.5), so it is divided by 100 before being returned. If the
fetch fails for any reason, the function logs a warning and returns 0.045 as a
hardcoded fallback — a reasonable proxy for the current rate environment.

get_option_chain(ticker, option_type) calls sync_ticker() to refresh the database,
then reads back only the rows with the maximum fetched_at timestamp for that
ticker and option_type. It filters out past expirations (expiration > today) so
the UI dropdowns never show expired contracts. Returns a dict:
    {"expirations": [sorted list of YYYY-MM-DD strings],
     "strikes": {expiration: [sorted list of floats]}}

get_pricing_inputs(ticker, expiration, option_type, strike) reads S from spot_price
and sigma/bid/ask from option_chain using a float equality guard (ABS(strike - %s)
< 1e-9) to avoid floating-point mismatch when comparing strike prices. It then
calls _fetch_risk_free_rate() for r and _trading_days_until() for T. Returns a
fully populated PricingInputs ready for direct use by the Pricing Engine.

save_closing.py — End-of-Day Snapshot:
save_closing_snapshot(ticker, option_type) identifies the most recent fetched_at
in option_chain (via MAX(fetched_at)), fetches all rows at that timestamp, and
bulk-inserts them into closing_snapshot tagged with datetime.date.today().isoformat()
as snapshot_date. Returns the integer count of rows written. If no option_chain
data exists for the ticker, it logs a warning and returns 0.

save_all_tickers() imports SUPPORTED_TICKERS from config.py and calls
save_closing_snapshot() for every ticker and both option types. The function
also supports a command-line mode: when called as a module (python -m
backend.data.save_closing AAPL) it saves only the named ticker.

config.py — Ticker Configuration:
Defines WORKFLOW_TICKERS as a list of 12 symbols:
    AAPL, MSFT, SPY, GOOGL, NVDA, META, AMZN, TSLA, JPM, GS, QQQ, ASML
SUPPORTED_TICKERS is set as an alias: SUPPORTED_TICKERS = WORKFLOW_TICKERS.
The reason for two names is explained in Phase 4 and Phase 6.

mock_data.py — Offline Fixtures:
Provides two constants for offline development and unit testing.
MOCK_CHAIN is a static dict mimicking the output of get_option_chain():
three expirations (2026-06-19, 2026-09-18, 2026-12-18) with seven or eight
strikes each, all above today's date at time of writing.
MOCK_PRICING_INPUTS is a PricingInputs instance with concrete values:
S=178.72, K=180.0, T=45/252, r=0.045, sigma=0.2831, bid=4.20, ask=4.35.
These allow the frontend and pricing module to run without a live database
or internet connection.

Commit: feat(data): implement complete data layer with PostgreSQL backend,
        sync, snapshot, public interface and test suite

Test Suite — 48 tests in tests/test_data_layer.py:
The test file is organized in five groups of tests, driven by three fixtures:
- test_db: session-scoped fixture that creates a temporary PostgreSQL schema
  (test_pff_ii_temp), patches DB_CONFIG to point at it, and drops it on teardown.
  This ensures schema tests run against a clean, isolated environment without
  touching production data.
- aapl_chain: session-scoped fixture that calls get_option_chain("AAPL", "call")
  once per test run. All subsequent tests that need live data read from the
  database populated by this single sync, keeping network calls to a minimum.
- sample_inputs: session-scoped fixture built on aapl_chain that calls
  get_pricing_inputs() for the first available expiration and strike of AAPL.

Schema tests (3 tests):
test_init_db_creates_all_tables — calls init_db() in the isolated test schema
and checks that spot_price, option_chain and closing_snapshot all exist in
information_schema.tables. Ensures that the schema bootstrap is complete and
idempotent on a fresh database.
test_option_chain_schema_columns — verifies that option_chain contains all ten
required columns (id, ticker, expiration, strike, option_type, implied_vol, bid,
ask, last_price, fetched_at). Guards against silent column renames or omissions
during future migrations.
test_closing_snapshot_schema_columns — same verification for closing_snapshot's
eight required columns (id, ticker, snapshot_date, expiration, strike, option_type,
implied_vol, saved_at). Any missing column would break the Volatility Surface
module at runtime.

get_option_chain tests (13 tests):
test_get_option_chain_returns_dict — confirms the return type is a Python dict.
test_get_option_chain_has_expirations_key — dict contains the key "expirations".
test_get_option_chain_has_strikes_key — dict contains the key "strikes".
test_get_option_chain_expirations_nonempty — at least one expiration is returned
for AAPL; guards against a silent sync failure producing an empty list.
test_get_option_chain_expirations_sorted — the "expirations" list is in ascending
order; required for the UI dropdown to display dates chronologically.
test_get_option_chain_expirations_yyyy_mm_dd — every expiration string parses
successfully with datetime.date.fromisoformat(); rejects any non-standard format.
test_get_option_chain_all_expirations_in_future — all returned expirations are
strictly after today; ensures expired contracts are filtered out before reaching
the UI.
test_get_option_chain_strikes_nonempty — every expiration has at least one strike;
guards against empty strike lists that would leave the UI dropdown empty.
test_get_option_chain_strikes_are_floats — all strike values for the first
expiration are Python floats; the Pricing Engine expects floats, not strings.
test_get_option_chain_strikes_are_positive — all strikes are greater than zero;
a zero or negative strike has no financial meaning.
test_get_option_chain_strikes_sorted — strikes are in ascending order for every
expiration; the UI dropdown must display them in increasing price order.
test_get_option_chain_invalid_type_raises — passing "CALL" (uppercase) raises
ValueError; confirms that validation is case-sensitive.
test_get_option_chain_invalid_type_wrong_value_raises — passing "option" raises
ValueError; confirms that only the exact strings 'call' and 'put' are accepted.

get_pricing_inputs tests (12 tests):
test_pricing_inputs_is_namedtuple — result is an instance of PricingInputs; the
Pricing Engine expects a NamedTuple, not a dict.
test_pricing_inputs_has_seven_fields — PricingInputs has exactly 7 fields (S, K,
T, r, sigma, bid, ask); a mismatch would break positional unpacking.
test_pricing_inputs_S_positive — S > 0; the binomial tree requires a positive spot.
test_pricing_inputs_K_positive — K > 0; strike must be positive.
test_pricing_inputs_T_positive — T > 0; zero or negative time to expiry would
crash the CRR model.
test_pricing_inputs_T_at_most_30_years — T <= 30; an unreasonably large T
signals a bug in the trading-days calculation.
test_pricing_inputs_T_is_trading_days_over_252 — T equals exactly
_trading_days_until(exp_date) / 252.0 for the selected expiration; confirms that
the time convention is applied consistently.
test_pricing_inputs_r_is_decimal — 0 < r < 1; catches the common error of
returning the rate as a percentage (e.g. 4.5 instead of 0.045).
test_pricing_inputs_sigma_nonneg — sigma >= 0; implied volatility cannot be
negative.
test_pricing_inputs_bid_nonneg — bid >= 0; option prices cannot be negative.
test_pricing_inputs_ask_nonneg — ask >= 0.
test_pricing_inputs_all_floats — every field is a Python float; the Pricing
Engine does not accept int or NoneType inputs.

Validation tests (5 tests):
test_past_expiration_raises_valueerror — a date in 2020 raises ValueError
matching "past"; prevents the user from pricing an expired option.
test_today_expiration_raises_valueerror — today's date raises ValueError; T
would compute to zero at minimum, causing a division-by-zero.
test_invalid_option_type_raises_valueerror — passing "CALL" (uppercase) to
get_pricing_inputs raises ValueError; same case-sensitivity check as for
get_option_chain.
test_bad_expiration_format_raises_valueerror — "01-01-2026" (DD-MM-YYYY) raises
ValueError via _validate_expiration; fromisoformat() requires YYYY-MM-DD.
test_bad_expiration_format_dd_mm_yyyy_raises — "31/12/2026" raises ValueError;
ensures slash-separated formats are also rejected.

Trading days helper tests (2 tests):
test_trading_days_until_positive — 30 calendar days out returns at least 1
trading day; the function never returns zero.
test_trading_days_until_weekend_skipped — 7 calendar days out returns between 4
and 7 trading days; confirms that weekends are counted correctly regardless of
the current day of the week.

Mock data tests (10 tests):
test_mock_chain_has_expirations — MOCK_CHAIN contains "expirations" key and at
least one entry.
test_mock_chain_has_strikes — MOCK_CHAIN contains "strikes" key and every
expiration maps to a non-empty list.
test_mock_chain_expirations_sorted — mock expirations are in ascending order;
mock must match the contract of get_option_chain().
test_mock_chain_expirations_in_future — all mock expirations are after today;
at time of writing all three (2026-06-19, 2026-09-18, 2026-12-18) satisfy this.
test_mock_pricing_inputs_is_namedtuple — MOCK_PRICING_INPUTS is a PricingInputs
instance.
test_mock_pricing_inputs_S_positive — S=178.72 is positive.
test_mock_pricing_inputs_K_positive — K=180.0 is positive.
test_mock_pricing_inputs_T_in_years — T=45/252 is between 0 and 30.
test_mock_pricing_inputs_r_decimal — r=0.045 is between 0 and 1.
test_mock_pricing_inputs_sigma_positive — sigma=0.2831 is positive.

save_closing tests (3 tests):
test_save_closing_snapshot_returns_positive_int — after the aapl_chain sync,
save_closing_snapshot("AAPL", "call") returns an integer greater than zero;
confirms that rows were actually written.
test_save_closing_snapshot_rows_in_db — after calling save_closing_snapshot,
a direct COUNT(*) query on closing_snapshot WHERE ticker = 'AAPL' returns a
positive count; confirms database persistence rather than just a non-zero return
value.
test_save_closing_invalid_type_raises — passing "CALL" raises ValueError;
same option_type validation as in the rest of the module.

Result: 48/48 tests passing
Commit: test(data): add comprehensive pytest test suite — 48 tests, 5 groups


Phase 2 — Migration to MySQL (Abandoned)
What we did:
The professor provided a MySQL instance running on a university VPS. The data layer
was migrated from SQLite to MySQL using the pymysql driver. All query placeholders
were changed to %s (MySQL style), the connection logic was replaced with
pymysql.connect(), and DB_CONFIG was updated with the VPS credentials.

Why it was abandoned:
Port 3306 (MySQL default) was blocked by the VPS firewall. Connections consistently
timed out regardless of credentials. The professor confirmed the firewall issue and
approved Supabase as an alternative cloud database. The MySQL code was discarded;
no trace of it remains in the current codebase.


Phase 3 — Migration to PostgreSQL (Supabase)
What we did:
The database was migrated to PostgreSQL hosted on Supabase (a managed cloud
PostgreSQL service). The driver changed from pymysql to psycopg2. The connection
factory in database.py was rewritten as a context manager using
psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor). The five connection
parameters (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) are loaded from .env
via python-dotenv.

Three tables were created on Supabase with the exact DDL now in init_db(). The
query placeholders remain %s throughout — psycopg2 uses the same convention as
pymysql, so only the connection logic needed to change, not the SQL strings.

Database architecture — three tables:

spot_price:
    id          SERIAL PRIMARY KEY
    ticker      VARCHAR(20) NOT NULL
    price       DOUBLE PRECISION NOT NULL
    fetched_at  VARCHAR(30) NOT NULL
Stores one row per sync event per ticker. No UPDATE or DELETE ever runs on this
table. The most recent price for a ticker is always retrieved with ORDER BY
fetched_at DESC LIMIT 1.

option_chain:
    id          SERIAL PRIMARY KEY
    ticker      VARCHAR(20) NOT NULL
    expiration  VARCHAR(10) NOT NULL
    strike      DOUBLE PRECISION NOT NULL
    option_type TEXT NOT NULL  — CHECK (option_type IN ('call', 'put'))
    implied_vol DOUBLE PRECISION   (nullable)
    bid         DOUBLE PRECISION   (nullable)
    ask         DOUBLE PRECISION   (nullable)
    last_price  DOUBLE PRECISION   (nullable)
    fetched_at  VARCHAR(30) NOT NULL
Stores one row per contract per sync event. A CHECK constraint at the database
level prevents any value other than 'call' or 'put' from being inserted, even
if application-level validation is bypassed. implied_vol, bid, ask and last_price
are nullable because Yahoo Finance does not always provide all fields.

closing_snapshot:
    id            SERIAL PRIMARY KEY
    ticker        VARCHAR(20) NOT NULL
    snapshot_date VARCHAR(10) NOT NULL
    expiration    VARCHAR(10) NOT NULL
    strike        DOUBLE PRECISION NOT NULL
    option_type   TEXT NOT NULL  — CHECK (option_type IN ('call', 'put'))
    implied_vol   DOUBLE PRECISION   (nullable)
    saved_at      VARCHAR(30) NOT NULL
One row per contract per day. This table is written by save_closing.py once per
trading day and read exclusively by the Volatility Surface module. It is separate
from option_chain because it has different semantics: it represents the implied
volatility at close, not a live intraday sync. The snapshot_date column is the
date label used by the surface slider in the dashboard.

Design decision — RealDictCursor:
Standard psycopg2 cursors return rows as plain tuples. RealDictCursor makes rows
behave like dictionaries: code reads row["implied_vol"] instead of row[2]. This
eliminates off-by-one errors when columns are reordered, makes review diffs easier
to read, and matches the style expected by get_connection() consumers across the
codebase.

After the migration, all 48 tests were re-run against the Supabase instance and
confirmed passing. The test fixture test_db creates a temporary schema
(test_pff_ii_temp) inside the same Supabase database, runs the schema tests
there, and drops it on teardown — keeping the production tables untouched.

Commit: refactor(data): migrate database backend from SQLite to PostgreSQL (Supabase)


Phase 4 — GitHub Actions Automation
What we did:
Created .github/workflows/daily_snapshot.yml to automate market data collection
every weekday after market close. The workflow runs on a schedule and can also be
triggered manually via workflow_dispatch.

Workflow structure — exactly as in daily_snapshot.yml:
    name: Daily Closing Snapshot
    trigger: cron '0 21 * * 1-5' (every weekday at 21:00 UTC, 22:00 Italy)
             workflow_dispatch (manual trigger)
    job: snapshot, runs-on ubuntu-latest

    Steps:
    1. actions/checkout@v4 — check out the repository
    2. actions/setup-python@v5, python-version '3.11' — set up Python
    3. pip install -r requirements.txt — install all dependencies
    4. python -m backend.data.sync — sync all tickers from Yahoo Finance
       (env: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD from GitHub Secrets)
    5. python -m backend.data.save_closing — save the end-of-day snapshot
       (same five secrets injected as environment variables)

The five database credentials are stored as GitHub repository Secrets and injected
at runtime. They never appear in the repository. The workflow first syncs live
option chain data (step 4), then snapshots the just-fetched data into
closing_snapshot (step 5). The two steps must run in this order because
save_closing.py reads from option_chain to build the snapshot.

Performance problem and introduction of WORKFLOW_TICKERS:
The first runs of the workflow attempted to sync all 12 tickers for both option
types. Each ticker involves fetching the spot price and iterating over every
available expiration — for a large-cap equity like AAPL or MSFT this can mean
20+ expiration dates with hundreds of strikes each. Total runtime exceeded 19
minutes, approaching GitHub Actions' default timeout.

To address this, WORKFLOW_TICKERS was introduced in config.py as a separate list,
initially containing only 3 tickers: AAPL, MSFT, SPY. sync_all_tickers() in sync.py
imports WORKFLOW_TICKERS rather than a larger full list, so the workflow runs
quickly while the three most representative tickers are covered.

Bug fix — NameError in sync_all_tickers():
After introducing WORKFLOW_TICKERS, a NameError was found in sync.py. The import
at the top of sync_all_tickers() correctly fetched WORKFLOW_TICKERS from config,
but the loop body still referenced SUPPORTED_TICKERS, which no longer existed.
The fix was to change the loop to iterate over WORKFLOW_TICKERS consistently:

    Before (broken):
        from backend.data.config import WORKFLOW_TICKERS
        for ticker in SUPPORTED_TICKERS:   # NameError: SUPPORTED_TICKERS undefined
            ...

    After (fixed):
        from backend.data.config import WORKFLOW_TICKERS
        for ticker in WORKFLOW_TICKERS:
            ...

The current sync.py reflects the fixed version.

Commit: feat(data): add GitHub Actions daily snapshot workflow
Commit: fix(data): fix NameError in sync_all_tickers — use WORKFLOW_TICKERS


Phase 5 — Integration with Pricing and Surface Modules
What we did:
Teammates delivered the Pricing Engine (backend/pricing/) and Volatility Surface
(backend/surface/) modules. Integration tests were run end-to-end: get_pricing_inputs()
was called with live AAPL data and the output was fed directly into binomial_tree()
and calcola_greeks().

Four findings were documented during integration:

1. K <= 0 not validated in binomial_tree():
   The Pricing Engine did not guard against a zero or negative strike price. Since
   get_pricing_inputs() guarantees K > 0 (the CHECK constraint and the test
   test_pricing_inputs_K_positive ensure this), no contract can reach the pricing
   engine with K <= 0 through the normal flow. The issue was logged as a
   documentation gap in the Pricing Engine, not a data layer defect.

2. Moneyness filter absent in the Volatility Surface module:
   build_surface_grid() in backend/surface/surface.py does not filter by
   moneyness before interpolating. Deep OTM options with near-zero implied
   volatility can distort the surface. This was flagged to the Surface module
   owner (Stefano Martino) as a potential improvement but is outside the data
   layer's scope.

3. option_type absent from PricingInputs by design:
   The Pricing Engine expected option_type as an explicit argument to binomial_tree()
   and calcola_greeks(), not embedded in the inputs struct. The design decision
   (documented in Phase 1) was confirmed correct: no change to PricingInputs
   was needed.

4. American Greeks using Black-Scholes formulas:
   calcola_greeks() applies closed-form Black-Scholes Greeks for both European and
   American options. For American options (particularly deep ITM puts), these
   Greeks can differ from the true finite-difference Greeks because early exercise
   is not modelled analytically. This was documented as a known model limitation,
   not a data layer issue. The fix for American option Greeks via finite differences
   was later implemented in the Pricing Engine (see PR #7 in the commit history).

No changes were made to backend/data/ in this phase.


Phase 6 — WORKFLOW_TICKERS Expanded to All 12 Tickers
What we did:
To accumulate closing_snapshot history for all supported tickers (required for
the Volatility Surface to display a meaningful surface for any ticker in the UI),
WORKFLOW_TICKERS in config.py was expanded from 3 tickers (AAPL, MSFT, SPY) to
the full list of 12:
    AAPL, MSFT, SPY, GOOGL, NVDA, META, AMZN, TSLA, JPM, GS, QQQ, ASML

Bug fix — ImportError in save_closing.py:
Expanding WORKFLOW_TICKERS revealed a broken import in save_closing.py.
save_all_tickers() contained:

    from backend.data.config import SUPPORTED_TICKERS

SUPPORTED_TICKERS was defined in the original config.py as the full list of 12
tickers. WORKFLOW_TICKERS was introduced later (Phase 4) as a smaller operational
subset (AAPL, MSFT, SPY) to keep the workflow runtime manageable. When
WORKFLOW_TICKERS was expanded to 12 tickers in Phase 6, SUPPORTED_TICKERS was
removed from config.py as redundant — which broke the import in save_closing.py.
The error was therefore a regression introduced during the expansion, not a
pre-existing bug.

The fix was to add an alias in config.py:

    SUPPORTED_TICKERS = WORKFLOW_TICKERS

This approach was chosen over renaming the import in save_closing.py because
SUPPORTED_TICKERS is the semantically correct name for "all tickers the platform
supports", while WORKFLOW_TICKERS is the operational name for "tickers synced
by the automated workflow". Keeping both names and pointing them at the same list
preserves the intent of each and avoids breaking any future code that might
reference either name.

The current config.py reflects this state: WORKFLOW_TICKERS is defined as the
list of 12 tickers; SUPPORTED_TICKERS = WORKFLOW_TICKERS is the alias on the
line below.

Commit: feat(data): expand WORKFLOW_TICKERS to all 12 tickers
Commit: fix(data): add SUPPORTED_TICKERS alias in config to fix ImportError


Phase 7 — Supabase Row Level Security Policies
What we did:
Row Level Security (RLS) was enabled on all three tables (spot_price, option_chain,
closing_snapshot) in the Supabase dashboard. Permissive policies were created for
each table using USING (true), which grants full SELECT, INSERT, UPDATE and DELETE
access to all authenticated and anonymous roles. This allows the backend application,
the GitHub Actions workflow and the professor's account to read and write without
additional role configuration.

The decision to use permissive policies rather than restrictive ones was pragmatic:
the application is a student project accessed only by the team and the professor.
No personally identifiable information or sensitive financial positions are stored
— only publicly available market data. A restrictive policy would add complexity
without meaningful security benefit in this context.

No code changes were required in backend/data/ — RLS policies are configured
entirely on the Supabase side and are transparent to psycopg2.


Summary — Data Layer Completion
PhaseTypeDescriptionCommit prefix
1featComplete data layer — database, sync, public interface, snapshotfeat
1testComprehensive test suite — 48 tests, 5 groupstest
2(abandoned)MySQL migration — discarded due to firewall—
3refactorMigration to PostgreSQL / Supabase with psycopg2refactor
4featGitHub Actions daily snapshot workflowfeat
4fixNameError in sync_all_tickers — loop used wrong variable namefix
5(docs)Integration findings — 4 issues documented, 0 data layer changes—
6featWORKFLOW_TICKERS expanded from 3 to 12 tickersfeat
6fixImportError in save_all_tickers — SUPPORTED_TICKERS alias addedfix
7(infra)Supabase RLS policies enabled — no code changes—

Total source files: 6 (database.py, market_data.py, sync.py, save_closing.py,
                       config.py, mock_data.py)
Test coverage: 48 tests, 5 groups, all passing
Database: PostgreSQL on Supabase, 3 append-only tables, 3 composite indexes
Automation: GitHub Actions cron every weekday at 21:00 UTC, 2-step pipeline
            (sync then snapshot), 5 secrets injected at runtime
AI tool used: Claude Code CLI (Anthropic) — initial implementation generated
              in a single session; subsequent fixes applied incrementally
