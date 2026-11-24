# Derived data registry

Every place the project **stores** something computed from other data. Stored results don't update themselves when their inputs change: whatever changed an input must also rebuild what depends on it.

**When to use this file**
- Before and after any change to an input below: re-downloaded or corrected bars, split/bonus fixes, mapping or watchlist changes, a logic change in a calculation.
- When a log, error, DQ issue or user message says an input changed or was wrong (e.g. the audit proposes a re-download): include the rebuild step in the proposed fix, and run it after the fix.
- When adding code that writes computed results to the database or to files: add a section here in the same change (rule in `CLAUDE.md`).

Commands run from `backend/` (`.venv\Scripts\markets.exe ...`). When `markets serve` holds the database lock, `markets breadth`, `markets highs`, `markets repair`, `markets update` and `markets dq` hand the job to the API (`--api`); otherwise stop the server first.

## Stored derived data

### 1. `sector_breadth` (sector breadth per day)
- **Writer:** `DuckBreadthRepository.store` (`storage/duckdb/repositories.py`; replaces every row of the range, so rows that no longer exist go too), called by `BreadthService.update` (nightly: from the earliest of 10 calendar days ago, the earliest bar (re)ingested since the last update/backfill (`derived_state.breadth_watermark`), and the earliest bar the repair step removed), `BreadthService.backfill` (all history), and on the first read of a day for a stored period by `BreadthService.sectors` and `BreadthService.rotation` (which also reads stored history for its comparison windows).
- **Scope:** universes `BREADTH_UNIVERSES` × MA periods `BREADTH_PERIODS` (`universes.py`). Other periods are computed live, never stored.
- **Inputs:** `candles` (1d close), `instruments.instrument_type` (EQ only), `instrument_tags` key `industry`, `watchlist_members` (point-in-time membership; days before a watchlist's first sync use its *current* members), the SQL in `DuckBreadthRepository._sql`.
- **Catches up by itself on:** re-downloaded or revised bars of any age (by `candles.ingested_at`) and bars removed by the repair step.
- **No version guard:** changing the SQL or the industry mapping does not invalidate stored rows. Any logic or mapping change needs a full rebuild.
- **Rebuild:** `markets breadth --backfill` (every universe, every day; `POST /api/jobs/breadth?backfill=true`). `markets breadth` alone redoes only the last 10 days.
- **What needs which rebuild:**
  - Bars re-downloaded or revised on day D, or removed by the repair step: the next `markets breadth` / nightly update recomputes from D (automatic). A bar deleted or edited by hand (no new `ingested_at`, not via repair) → `--backfill`.
  - Industry mapping changed (any stock): `--backfill` (labels are applied to all history).
  - Watchlist membership changed (index rebalance, new watchlist sync): days before that watchlist's first sync use current members, so they shift → `--backfill`. The nightly sync does this silently twice a year at rebalances (accepted; see BOOK_OF_WORK).
  - New universe or MA period added to `BREADTH_UNIVERSES` / `BREADTH_PERIODS`, or a change to `_sql`: `--backfill`.

### 2. `calc_values` + `calc_runs` + `calc_definitions` (stored indicator values)
- **Writer:** `CalcService.compute` (`pipelines/compute.py`) → `DuckCalcRepository.write_values`. Called by `POST /api/calcs/run` (the chart, on every indicator load, cached 60 s in the browser) and `markets compute NAME INSTRUMENTS`.
- **Inputs:** `candles` for that instrument and interval (full history every run), the indicator function and its params.
- **Guards:** `calc_id` = hash of (name, version, params), so new params or a version bump write a separate series. `code_hash` covers only the decorated function's own source: changing it without a version bump raises `CodeChangedError`. Changes in a helper it calls are **not** detected → bump the indicator's version by hand.
- **Self-healing:** every run recomputes full history and upserts, so changed bars are picked up the next time the chart loads that indicator. Bars removed by the repair step also have their stored values deleted (`DuckCalcRepository.delete_values_at`).
- **Not healed by a rerun:** rows are upserted, never deleted. A bar that is removed, or a value that becomes NaN after a bar fix, keeps its old stored value. Rebuild: delete that series' rows (`DELETE FROM calc_values WHERE calc_id = ? AND instrument_id = ? AND timeframe = ?`) and rerun `markets compute`.

### 3. `daily_ath` + `derived_state` (all-time high per stock and day)
- **Writer:** `DuckAthRepository.rebuild_from` (`storage/duckdb/repositories.py`), called by the repair step for stocks whose bars it removed (from the earliest removed bar), and by `AthService.refresh` (`pipelines/highs.py`): in the nightly update (after bars, before breadth), before every read of the all-time high (`BreadthService._near_high` with basis `ath`, for the Sector breadth card's near-high column and the rotation's "Near high" ranking), and by `markets highs [--rebuild]` / `POST /api/jobs/highs?rebuild=true`.
- **Inputs:** `candles` (1d `high`; zero/NaN highs skipped). History starts at each stock's first stored bar (Nov 2016 for older stocks), so "all-time" means since then.
- **Guards:** per-instrument incremental refresh: stocks with daily bars ingested after `derived_state.ath_watermark` (by `candles.ingested_at`, so re-downloads count) are recomputed from their earliest such bar. `ATH_VERSION` (`pipelines/highs.py`): bump it on any change to the calculation and the next refresh rebuilds everything. Because every read refreshes first, the table can't lag the bars.
- **Rebuild:** normally nothing to do. Full: `markets highs --rebuild`. Not caught: a bar deleted or edited by hand without a new `ingested_at` (repair removals are handled) → `--rebuild`.
- **Splits:** stored bars before a split stay unadjusted until the stock's history is re-downloaded (split re-fetch job not built yet, see BOOK_OF_WORK), so a split stock looks far below its old high; the re-download then flows through this table automatically.

### 4. `dq_issues` + `dq_state` (data-quality issues and watermark)
- **Also written by** the repair step (`pipelines/repair.py`): `repair_attempts` / `last_repair_at`, and status changes (resolved "removed bad bar", accepted "provider hole").
- **Writer:** `DataQualityService.run` (`pipelines/data_quality.py`), last step of the nightly update; `markets dq check`.
- **Inputs:** `candles` (by `ingested_at` since the stored watermark), `ingestion_runs` (failed downloads), watchlist members (stale / short-history checks), the check functions in `engine/data_quality.py`.
- **Self-healing:** re-downloaded bars get a new `ingested_at`, so the next run re-checks them and resolves fixed issues.
- **Rebuild:** check logic changed → bump `DQ_VERSION` (forces a full run next time) or run `markets dq check --full`. Bars deleted or edited without a new `ingested_at` → `markets dq check --full`.

### 5. `mover_scores` + `mover_runs` (big-movers list per day)
- **Writer:** `MoverService.score` via `DuckMoverRepository.store` (`pipelines/movers.py`; replaces that day's scores, keeps its Telegram state): the nightly update's last step (`MoverService.nightly`, then one Telegram message per day), `markets movers [--since D] [--rebuild]` / `POST /api/jobs/movers?since&rebuild` (no message).
- **Scope:** one row per eligible `-EQ` stock and scored session (`as_of`), per `model_version`. Only sessions after the model's training period (2025 on for `co4_eod_v1`).
- **Inputs:** `candles` (1d, last `HISTORY_BARS` = 500 bars up to as_of) of the current `niftytotalmarket` members (all series: they feed the market features), the Nifty 50 (sessions, market features) and India VIX; `instruments.symbol` (the `-EQ` filter); the feature code (`engine/movers.py`, `FEATURES_VERSION`) and the model file (`src/markets/models/<model_version>.json`). The next session is assumed to be the next weekday (no holiday calendar).
- **The model file** (`src/markets/models/`, trained on 2018-2024 bars by `scripts/train_movers.py`) is frozen on purpose: bar fixes never retrain it; a retrained model is a new `model_version`.
- **Not stored:** what each stock did next (close vs open, hit) is read live from `candles`, so it follows bar fixes by itself.
- **Guards:** a day already scored is skipped (not re-scored) unless `--rebuild`. The model refuses to load if its `features_version` or feature list differs from the code. A different model writes under its own `model_version`. Universe membership is today's at scoring time; a later rebalance doesn't change stored days.
- **Not caught:** bars re-downloaded, repaired or removed on or before a scored day (the scores used the old bars); a change to the feature code without a new model version (prevented by the version check only if `FEATURES_VERSION` is bumped).
- **Rebuild:** `markets movers --since D --rebuild` (every session from D; the API when the server holds the DB). One day: `markets movers --rebuild` re-scores the latest session only.
- **What needs which rebuild:**
  - Bars re-downloaded or revised on day D, or removed by the repair step, for a universe stock, the Nifty or VIX: re-score every list scored from D on: `--since D --rebuild` (each day looks back 500 bars, and the market features use the whole universe). Small fixes to one stock change other stocks' scores only through the market features.
  - A split/bonus fix (re-downloaded history): `--since <first scored day> --rebuild`.
  - A logic change in `engine/movers.py`: bump `FEATURES_VERSION`, train a new model version (`scripts/train_movers.py`), switch `MODEL_VERSION`, then `markets movers --since 2025-01-01` for that version (old versions' rows stay; delete them with `DELETE FROM mover_scores WHERE model_version = ?` and the same on `mover_runs` if unwanted).
  - Universe rebalance: nothing (stored days keep the members they were scored with).

## Computed live (nothing stored, no rebuild)
- `v_daily_stats_v1`, `daily_signals_v1(as_of)` (SQL), Overview (`MarketOverviewService`), scans and custom scans (`ScreenerService`, `engine/scans.py`), scan basket and watchlist performance, sector pages, breadth for non-stored MA periods or universes, sector near-high counts (52-week high is computed live; the all-time high is read from `daily_ath`).
- Changing their logic still follows the versioning rule (add `_v2`, bump `@scan` version); results change on the next request.
- Browser: TanStack Query caches responses in memory (indicator list and scan fields with `staleTime: Infinity`) → reload the page after a backend change. sessionStorage chart lists hold only ids and order.

## Inputs that are not derived (source data)
Note: `candles` is also changed by the nightly repair step (re-downloads, and removal of bars still bad after re-download, archived in `candle_revisions`); it brings the tables above up to date itself (see each section).
`candles`, `candle_revisions`, `instruments`, `instrument_provider_map`, `instrument_tags`, `watchlists`, `watchlist_members`, `ingestion_runs`, `saved_scans`. Changing any of these is what triggers the rebuilds above.

Your own watchlists (`watchlists.source = 'manual'`, Watchlists tab) are source data too, but they need **no rebuild**: they aren't in `BREADTH_UNIVERSES`, so they never feed `sector_breadth`. Their members are part of the nightly download targets and the DQ stale / short-history checks from the next run on; their prices in the Watchlists tab are read live from `candles`.
