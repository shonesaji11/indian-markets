# Indian Markets

Personal market dashboard: Angel One data → DuckDB → calculation engine → FastAPI → React.

## Layout

```
backend/src/markets/
  core/        Domain types (Instrument, Interval, DateRange) and ports (Protocol interfaces).
               Depends on nothing else in the project.
  providers/   Market data adapters: angelone.py (SmartAPI), fake.py (offline synthetic data).
  storage/     DuckDB adapter: connection, numbered SQL migrations, repositories.
  engine/      Pure calculations: candle DataFrame in, DataFrame out. Only knows pandas.
  pipelines/   Use cases wiring ports together (ingest, compute). No concrete classes.
  api/         FastAPI routers. Thin: validate input, call a pipeline/repo, shape output.
  bootstrap.py Composition root: the only file that picks concrete adapters.
  cli.py       `markets ...` commands.

frontend/src/
  api/         HTTP client, response types, React Query hooks (the only place that knows endpoints).
  components/  Generic, reusable UI: ui/ (Card, Button, DataTable, Field...), charts/ (PriceChart),
               layout/. These know nothing about markets or the API.
  features/    Domain components composed from the generic ones (InstrumentPicker, IngestPanel...).
  pages/       Route-level composition of features.
```

Dependency direction: `api / cli → pipelines → core ports ← providers, storage`, and
`pipelines → engine`. The engine never imports storage or providers; swapping Angel One or
DuckDB means writing a new adapter and changing `bootstrap.py`.

## Data model (DuckDB)

| Table | Purpose |
| --- | --- |
| `instruments` | Provider-independent instrument master, surrogate `instrument_id`. |
| `instrument_provider_map` | Provider tokens per instrument (Angel One symbol tokens live here only). |
| `candles` | OHLCV, PK `(instrument_id, timeframe, ts)`, with `source` and `ingested_at`. |
| `candle_revisions` | Old values of bars that a later fetch changed, so past states are reconstructable. |
| `ingestion_runs` | Audit log of every provider fetch. |
| `calc_definitions` | One row per `(name, version, params)`; `calc_id` is a hash of those. Stores a hash of the code. |
| `calc_runs` | Every computation run, with the data watermark it saw. |
| `calc_values` | Long-format results keyed by `calc_id`, so old versions stay queryable beside new ones. |
| `v_daily_stats_v1` | SQL view: returns, 52-week range, relative volume. Each row uses only past data. |
| `daily_signals_v1(as_of)` | Table macro: one row per instrument as of a date (change, gap, 52W range, SMA 50/200, relative volume vs the prior 20 days). Feeds the overview page and scans. |
| `watchlists`, `watchlist_members` | Named universes (Nifty 500, benchmarks, sectors). Membership keeps history (`added_at`/`removed_at`) so past index compositions are known. |
| `instrument_tags` | Classifications such as `industry` from NSE's constituent files. |

Rules that keep results reproducible:

- **Python calculations**: change the logic → bump `version` in `@indicator(...)`. If you forget,
  storage sees the code hash changed and refuses to write under the old `calc_id`.
- **SQL views**: never edit an applied migration. Add `v_<name>_v2` in a new migration file.
- **Point-in-time**: filter any view on `ts <= as_of` and you get what a scan would have seen
  that day, e.g. `SELECT * FROM v_daily_stats_v1 WHERE ts = '2024-03-15' AND close >= high_52w`.

Timestamps are naive IST everywhere.

## Quick start

Double-click `start-dashboard.bat` in the project folder (after the setup below). It opens the
backend, the frontend and, if `ngrok-policy.yml` exists, a public ngrok link, each in its own
window, then opens http://localhost:5173. Close the windows to stop. Anything already running is
skipped. The server runs without `--reload`, so it can't restart in the middle of the nightly update.

Public link: copy `ngrok-policy.example.yml` to `ngrok-policy.yml` (gitignored) and set a password.
Visitors must log in with it; without that file no public link is opened. The link is the
account's fixed ngrok dev domain, shown in the "Markets ngrok" window. The ngrok.exe path is set at
the top of the .bat file.

## Setup

Backend (Python 3.9+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[angelone,dev]"
copy .env.example .env      # fill in Angel One credentials
.venv\Scripts\markets init-db
.venv\Scripts\markets sync-instruments                    # ~168k instruments, ~15s
.venv\Scripts\markets ingest NSE:RELIANCE-EQ "NSE:Nifty 50" --start 2016-01-01
.venv\Scripts\markets compute sma NSE:RELIANCE-EQ --param period=50
.venv\Scripts\markets serve --reload                      # http://127.0.0.1:8000/docs
.venv\Scripts\pytest
```

Set `MARKETS_PROVIDER=fake` to run everything offline with synthetic data.

DuckDB allows one writing process per file: stop `markets serve` before running write
commands from the CLI, or use the equivalent API endpoints while the server runs.

## Nightly update

`markets update` refreshes the instrument master, re-syncs the watchlists in
`backend/src/markets/universes.py` from NSE's published constituent lists, then fetches new
daily bars for every watchlist member plus anything already stored. New instruments get 10
years of history. If `markets serve` is running (it holds the DuckDB lock) the command hands
the job to the server instead.

It runs on weekdays at 17:00 via Windows Task Scheduler (task "Markets nightly update",
registered by `backend/scripts/register-nightly-task.ps1`). Output goes to
`backend/logs/update-YYYY-MM-DD.log`. About 45-50 minutes for ~3,000 instruments, limited by
Angel One's 80 requests/minute; data-quality checks run as its last step, and the audit
scheduled task reviews the result at 19:00.

```bash
powershell -ExecutionPolicy Bypass -File backend\scripts
ightly-update.ps1
```

Frontend (Node 18+):

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173, proxies /api to :8000
```

Troubleshooting: if `npm run dev`/`build` exits silently (Windows exit code -1073741819),
an old native module from a parent folder is being loaded (this happened once with a stray
`C:\Users\shone\node_modules` holding bufferutil 4.0.5, since deleted). The frontend pins
its own `bufferutil` so a parent folder's copy is never picked up.

## Adding things

- **Indicator**: add a function in `engine/indicators/*.py` decorated with `@indicator`. It
  shows up in the API and the UI's indicator picker automatically.
- **SQL view**: new file `storage/duckdb/migrations/00N_<name>.sql`, applied on next start.
- **Scan** (overview lists): a function in `engine/scans.py` decorated with `@scan`; it receives
  the `daily_signals_v1` snapshot and returns ranked rows.
- **Tracked universe**: edit `universes.py`; the next `markets update` syncs it.
- **Data provider**: implement `MarketDataProvider` from `core/ports.py`, register it in
  `providers/__init__.py`.
- **UI**: generic pieces go in `components/`, anything that calls the API goes in `features/`.
