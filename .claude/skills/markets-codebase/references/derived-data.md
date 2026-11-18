# Derived data registry

Every place the project **stores** something computed from other data. Stored results don't update themselves when their inputs change: whatever changed an input must also rebuild what depends on it.

**When to use this file**
- Before and after any change to an input below: re-downloaded or corrected bars, split/bonus fixes, mapping or watchlist changes, a logic change in a calculation.
- When a log, error, DQ issue or user message says an input changed or was wrong (e.g. the audit proposes a re-download): include the rebuild step in the proposed fix, and run it after the fix.
- When adding code that writes computed results to the database or to files: add a section here in the same change (rule in `CLAUDE.md`).

Commands run from `backend/` (`.venv\Scripts\markets.exe ...`). When `markets serve` holds the database lock, `markets breadth`, `markets update` and `markets dq` hand the job to the API (`--api`); otherwise stop the server first.

## Stored derived data

### 1. `sector_breadth` (sector breadth per day)
- **Writer:** `DuckBreadthRepository.store` (`storage/duckdb/repositories.py`), called by `BreadthService.update` (nightly, last 10 calendar days), `BreadthService.backfill` (all history) and `BreadthService.sectors` (first read of a day for a stored period).
- **Scope:** universes `BREADTH_UNIVERSES` × MA periods `BREADTH_PERIODS` (`universes.py`). Other periods are computed live, never stored.
- **Inputs:** `candles` (1d close), `instruments.instrument_type` (EQ only), `instrument_tags` key `industry`, `watchlist_members` (point-in-time membership; days before a watchlist's first sync use its *current* members), the SQL in `DuckBreadthRepository._sql`.
- **No version guard:** changing the SQL does not invalidate stored rows. Any logic change needs a full rebuild.
- **Rebuild:** `markets breadth --backfill` (every universe, every day; `POST /api/jobs/breadth?backfill=true`). `markets breadth` alone redoes only the last 10 days.
- **What needs which rebuild:**
  - Bars changed on day D (re-download, split fix, deleted/edited bar): breadth from D for as long as D sits inside the longest stored SMA window (200 sessions, ~290 calendar days). Older than the last 10 days → `--backfill`.
  - Industry mapping changed (any stock): `--backfill` (labels are applied to all history).
  - Watchlist membership changed (index rebalance, new watchlist sync): days before that watchlist's first sync use current members, so they shift → `--backfill`. The nightly sync does this silently twice a year at rebalances (accepted; see BOOK_OF_WORK).
  - New universe or MA period added to `BREADTH_UNIVERSES` / `BREADTH_PERIODS`, or a change to `_sql`: `--backfill`.

### 2. `calc_values` + `calc_runs` + `calc_definitions` (stored indicator values)
- **Writer:** `CalcService.compute` (`pipelines/compute.py`) → `DuckCalcRepository.write_values`. Called by `POST /api/calcs/run` (the chart, on every indicator load, cached 60 s in the browser) and `markets compute NAME INSTRUMENTS`.
- **Inputs:** `candles` for that instrument and interval (full history every run), the indicator function and its params.
- **Guards:** `calc_id` = hash of (name, version, params), so new params or a version bump write a separate series. `code_hash` covers only the decorated function's own source: changing it without a version bump raises `CodeChangedError`. Changes in a helper it calls are **not** detected → bump the indicator's version by hand.
- **Self-healing:** every run recomputes full history and upserts, so changed bars are picked up the next time the chart loads that indicator.
- **Not healed by a rerun:** rows are upserted, never deleted. A bar that is removed, or a value that becomes NaN after a bar fix, keeps its old stored value. Rebuild: delete that series' rows (`DELETE FROM calc_values WHERE calc_id = ? AND instrument_id = ? AND timeframe = ?`) and rerun `markets compute`.

### 3. `dq_issues` + `dq_state` (data-quality issues and watermark)
- **Writer:** `DataQualityService.run` (`pipelines/data_quality.py`), last step of the nightly update; `markets dq check`.
- **Inputs:** `candles` (by `ingested_at` since the stored watermark), `ingestion_runs` (failed downloads), watchlist members (stale / short-history checks), the check functions in `engine/data_quality.py`.
- **Self-healing:** re-downloaded bars get a new `ingested_at`, so the next run re-checks them and resolves fixed issues.
- **Rebuild:** check logic changed → bump `DQ_VERSION` (forces a full run next time) or run `markets dq check --full`. Bars deleted or edited without a new `ingested_at` → `markets dq check --full`.

## Computed live (nothing stored, no rebuild)
- `v_daily_stats_v1`, `daily_signals_v1(as_of)` (SQL), Overview (`MarketOverviewService`), scans and custom scans (`ScreenerService`, `engine/scans.py`), scan basket performance, sector pages, breadth for non-stored MA periods or universes.
- Changing their logic still follows the versioning rule (add `_v2`, bump `@scan` version); results change on the next request.
- Browser: TanStack Query caches responses in memory (indicator list and scan fields with `staleTime: Infinity`) → reload the page after a backend change. sessionStorage chart lists hold only ids and order.

## Inputs that are not derived (source data)
`candles`, `candle_revisions`, `instruments`, `instrument_provider_map`, `instrument_tags`, `watchlists`, `watchlist_members`, `ingestion_runs`, `saved_scans`. Changing any of these is what triggers the rebuilds above.
