# Backend map (`backend/src/markets/`)

Python >= 3.9, package `markets` (`backend/pyproject.toml`; extras `angelone`, `dev`). Line counts are approximate; Grep for the symbol, then read only that range.

## core/ (shared types and interfaces)

| File | Symbols |
|---|---|
| `core/models.py` | `CANDLE_COLUMNS`; `Interval` enum (`.duration`); dataclasses `Instrument`, `ProviderInstrument`, `DateRange` (`.chunks(max_span)` splits windows), `IngestionResult` |
| `core/ports.py` | Protocols: `MarketDataProvider` (`list_instruments`, `fetch_candles`, `last_trade_dates`, `close`), `ConstituentSource`/`Constituent`, `InstrumentRepository`, `CandleRepository`, `IngestionLog`, `CalcRepository` |

## Wiring and config

| File | Symbols |
|---|---|
| `config.py` | `Settings` (env `MARKETS_*`, `backend/.env`), `get_settings()` (cached), `BACKEND_DIR` |
| `bootstrap.py` | `Container` dataclass (db, all repos, registry, provider, services incl. `screener`, `data_quality`; `.close()`), `build_container(settings, provider, db, ...)` (runs migrations) |
| `universes.py` | `WatchlistSpec`, `WATCHLISTS` (nifty500, nifty50, niftytotalmarket, nse_traded, benchmarks, sectors), `DEFAULT_UNIVERSE = "nifty500"`, `BREADTH_UNIVERSES`, `BREADTH_PERIODS` (10, 20, 50, 200: stored daily) |
| `cli.py` | `main()`; commands `init-db`, `sync-instruments`, `search`, `ingest`, `compute`, `coverage`, `update` (nightly), `dq report|check|accept` (falls back to the API when the server holds the DB), `breadth [--backfill]`, `watchlists`, `serve`. `update` and `breadth` go through the running API when the server holds the DB (`_post_api`) |

## providers/ and sources/ (external data in)

| File | Symbols |
|---|---|
| `providers/__init__.py` | `ProviderError`, `build_provider(settings)` → Angel One or Fake |
| `providers/angelone.py` | `AngelOneProvider` (login via TOTP, `list_instruments` from `SCRIP_MASTER_URL`, `fetch_candles` chunked per `_INTERVALS` max-days, rate-limited by `CANDLE_RATE_LIMITS`, re-login on `_TOKEN_ERRORS`; `last_trade_dates` via `getMarketData` FULL in batches of `QUOTE_BATCH`=50 under `QUOTE_RATE_LIMITS`; every call goes through `_call` (rate limit + retries, 15/30/60s backoff on rate-limit errors); `_INSTRUMENT_TYPES` maps `""`→EQ, `AMXIDX`→INDEX) |
| `providers/fake.py` | `FakeProvider`: deterministic synthetic universe + candles for tests/offline |
| `providers/ratelimit.py` | `RateLimiter(limits=[(max_calls, per_seconds), ...])`, sliding windows; `.acquire()` blocks until every window allows a call |
| `sources/nse_indices.py` | `NseIndexSource.constituents(index)` downloads niftyindices.com CSVs → `NseConstituent` (`_FILE_NAMES` for slugs whose file isn't `ind_<slug>list.csv`) |

## engine/ (pure computation)

| File | Symbols |
|---|---|
| `engine/registry.py` | `IndicatorSpec` (`code_hash`, `resolve_params`, `calc_id`, `compute`, `describe`), `IndicatorRegistry` (`register/get/all`), `@indicator(name, version, outputs, description)`, `default_registry()` |
| `engine/indicators/trend.py` | `sma`, `ema`, `macd` |
| `engine/indicators/momentum.py` | `rsi` |
| `engine/indicators/volatility.py` | `atr`, `bollinger`, `adr_pct(period=20)` (ADR%: 100 × (mean high/low − 1)) |
| `engine/indicators/volume.py` | `volume_avg(period)`, `relative_volume(period)` (both average the bars *before* the current one) |
| `engine/screener.py` | Custom scans: filter tree (groups `match` all/any → conditions `left op right`; daily bars only (`TIMEFRAME`); operands = `FIELDS` of daily_signals_v1 (no avg/relative volume: use the volume indicators) or any registered indicator + params + output; ops gt/gte/lt/lte/crosses_above/crosses_below; percent fields take %; any operand may carry `ago: {n, unit d/w/m}` = N × 1/5/21 sessions back, max 252 (`AGO_UNITS`, `MAX_AGO_BARS`, `bars_ago`)). `validate`, `iter_operands`, `operand_key` (`rsi(14)`, `sma(20)@1w`), `operand_label` (`RSI 14`, `SMA 20 · 1w ago`, `ADR% 20`), `uses_crossovers`, `evaluate` (vectorized masks), `indicator_frame` (wide ts × instrument; too little history = NaN, never a shorter window), `lookback_bars`. Missing values never match: no bar on the session asked for (offsets and the crossover's session before), or too little history, leaves the stock out |
| `engine/performance.py` | `basket_performance(bars, start)` → `BasketPerformance(stocks, path, counted)`: equal-weight buy-and-hold of stocks picked on the start session, bought at the next valid open (0 until bought); gaps carry the last close, stocks with no usable bar after the pick are listed but not counted; no stops/exits; end = last stored daily close (partial if "Fetch latest" ran in market hours) |
| `engine/data_quality.py` | Pure DQ checks over long-format daily bars → issues (`instrument_id, start_ts, end_ts, detail`): `trading_sessions(counts)` (market calendar: days with ≥25% of a typical day's stocks), `find_gaps`, `find_bad_bars` (zero/NaN price, high<low, zero volume except indices), `find_jumps` (>35% close move, indices exempt), `find_stale` (>3 sessions behind), `find_short_history` (<200 bars). Constants + `DQ_VERSION` (bump on any logic change → next run is full) |
| `engine/scans.py` | Built-in overview scans: `Scan` (`.run(snapshot, limit)`), `@scan(...)`, `SCANS`; scans `top_gainers`, `top_losers`, `volume_shockers`, `new_52w_highs`, `new_52w_lows`, `gap_ups`, `gap_downs`; `breadth(df)` |

## pipelines/ (services, orchestrate repos + provider + engine)

| File | Symbols |
|---|---|
| `pipelines/ingest.py` | `IngestionService`: `sync_instruments()`, `ingest(instrument_id, interval, start, end)` (incremental from last bar; `DEFAULT_HISTORY`, `DEFAULT_INTRADAY_HISTORY`) |
| `pipelines/compute.py` | `CalcService.compute(name, instrument_id, interval, params)` → `CalcOutcome`; stores values via `CalcRepository` |
| `pipelines/watchlists.py` | `WatchlistService.sync_all()` / `sync(id)`: resolves `WATCHLISTS` to instrument ids (NSE index CSV, fixed `members`, or `traded_series` = stocks whose quote shows a trade in the latest session, via `_traded_ids`), writes members + industry tags |
| `pipelines/daily_update.py` | `DailyUpdateService.run(sync_instruments, sync_watchlists)` → `DailyUpdateReport` (last step: `data_quality.run()`, summary in `report.data_quality`) (nightly: sync, daily bars for tracked ids, then `breadth.update()`) |
| `pipelines/data_quality.py` | `DataQualityService.run(full, checks, instrument_ids)` (incremental by `candles.ingested_at` watermark in `dq_state`; bar checks from the bar before the first new one; full on first run / version change / `full`; scoped runs don't move the watermark; records + resolves issues), `report(status, check, instrument_id)`, `accept(issue_id, note)`; `CHECKS`, `BAR_CHECKS`, `GLOBAL_CHECKS` |
| `pipelines/breadth.py` | `BreadthService`: `sectors(universe, as_of, periods)` (latest session; stored periods read from / written through to `sector_breadth`, others computed live), `update(days=10)`, `backfill()` |
| `pipelines/snapshots.py` | Shared by cross-sectional services: `universe_members(universe, as_of, ...)` (point-in-time watchlist, or `ALL_TRACKED`="all"), `latest_session(snap)`, `clean`, `records(df, columns)` (JSON-safe rows) |
| `pipelines/screener.py` | `ScreenerService`: `fields()`, `run(filter, universe, as_of, include_indices, industry=None, columns=())` (`industry` = one sector; `columns` = extra operands returned, not filtered on) → `{as_of, timeframe, universe, columns, rows}`, `performance(ids, start, end)` (basket vs the benchmark, default `NSE:Nifty 50` = first `benchmarks` member; ValueError if end < start), `saved_scans()`, `save(name, definition)` (upsert by name), `delete(id)` |
| `pipelines/market_overview.py` | `MarketOverviewService.overview(universe, as_of, limit)` (benchmarks, sectors, breadth, scans, sparklines), `.scan_catalog()`; `ROW_COLUMNS` |

## storage/duckdb/

| File | Symbols |
|---|---|
| `connection.py` | `Database(path)`: `.cursor()`, `.transaction()` context manager, `.close()` |
| `migrator.py` | `migrate(db)`: applies `migrations/NNN_*.sql` in order, tracked in `schema_migrations` |
| `repositories.py` | `DuckInstrumentRepository` (`upsert_many`, `get`, `find`, `search`, `provider_token`, `equity_tokens(exchange, series, provider)`); `DuckCandleRepository` (`upsert` with revisions, `load`, `latest_ts`, `last_ingested_at`, `coverage`); `DuckIngestionLog` (`start`, `finish`, `fail_orphaned`, `recent`); `DuckViewRepository.daily_stats`; `DuckCalcRepository` (`ensure_definition` raises `CodeChangedError`, `start_run`, `finish_run`, `write_values`, `load_values`, `definitions`, `fail_orphaned`); `DuckWatchlistRepository` (`upsert`, `set_members`, `member_ids(as_of)`, `all`, `set_tags`); `DuckMarketRepository` (`snapshot(as_of, ids)`, `recent_closes`, `daily_prices(ids, start, end)` (open + close) long format, `recent_sessions(ids, as_of, count)` (trading days newest first), `daily_bars(ids, as_of, bars)` long format, `tracked_daily_ids`); `DuckSavedScanRepository` (`all`, `save` upsert by name, `delete`); `DuckBreadthRepository` (`latest_session`, `compute(universe, periods, start, end)` one SQL pass with window SMAs + point-in-time membership, `store` upsert, `load`); `DuckDataQualityRepository` (`get_state`/`set_state`, `max_ingested_at`, `changed_since`, `bars_from`, `instruments_per_day`, `bar_summary`, `failed_downloads`, `record` (upsert; accepted stays accepted, resolved reopens), `resolve_missing`, `issues`, `counts`, `accept`); `UNCLASSIFIED` |

Migrations:

| File | Objects |
|---|---|
| `001_core.sql` | `instruments`, `instrument_provider_map`, `candles`, `candle_revisions`, `ingestion_runs`, `calc_definitions`, `calc_runs`, `calc_values` |
| `002_daily_stats_view.sql` | view `v_daily_stats_v1` |
| `003_watchlists.sql` | `watchlists`, `watchlist_members` (point-in-time), `instrument_tags` |
| `006_sector_breadth.sql` | `sector_breadth(ts, universe, industry, ma_period, stocks, above)` |
| `007_data_quality.sql` | `dq_issues` (issue_id = check:instrument:start, status open/resolved/accepted, first/last seen, count, note), `dq_state` (watermark, version) |
| `005_saved_scans.sql` | `saved_scans` (definition JSON = filter + universe + include_indices); seeds "At 52-week high" |
| `004_daily_signals.sql` | table macro `daily_signals_v1(as_of)`: point-in-time per-instrument signals (change, gap, rel. volume, SMA 50/200, 52w high/low); reads the last 450 calendar days, so instruments with no bar in that window drop out |

DB file: `backend/data/markets.duckdb`.

## api/ (FastAPI, everything under `/api`)

| File | Contents |
|---|---|
| `app.py` | `create_app(container)`: lifespan builds/closes the Container, CORS, routers, `GET /api/health`; `main.py` = uvicorn entry |
| `deps.py` | `get_container(request)` |
| `schemas.py` | `InstrumentOut`, `CandleOut`, `CandleSeriesOut`, `IndicatorOut`, `CalcRunIn`, `CalcSeriesOut`, `IngestIn`, `IngestAccepted`, `ScanRunIn`, `ScanPerformanceIn`, `DqCheckIn`, `DqAcceptIn`, `SavedScanIn` |
| `routers/instruments.py` | `GET /instruments?q&exchange&instrument_type&limit`, `GET /instruments/{id}`, `POST /instruments/sync` |
| `routers/data.py` | `GET /candles/{id}?interval&start&end`, `GET /coverage`, `POST /ingest` (202, background), `GET /ingest/runs` |
| `routers/calcs.py` | `GET /calcs/indicators`, `GET /calcs/definitions`, `POST /calcs/run`, `GET /calcs/{calc_id}/series` |
| `routers/market.py` | `GET /market/overview?as_of&universe&limit`, `GET /watchlists`, `GET /watchlists/{id}/members`, `POST /jobs/daily-update`, `GET /market/sector-breadth?universe&as_of&periods=10&periods=20`, `POST /jobs/breadth?backfill` |
| `routers/scans.py` | `GET /scans/fields`, `POST /scans/run` (422 on bad filter), `POST /scans/performance` (basket since a scan date, 422 if end < start), `GET/POST /scans/saved`, `DELETE /scans/saved/{id}` |
| `routers/data_quality.py` | `GET /dq/issues` (status open/resolved/accepted/all, check, instrument), `POST /dq/check` (`DqCheckIn`), `POST /dq/issues/{id}/accept` (`DqAcceptIn`, note required) |
| `routers/views.py` | `GET /views/daily-stats?as_of&instrument_id&limit` (no longer used by the UI) |

## Tests and scripts

- `backend/tests/`: `conftest.py` (fixtures: `container` = FakeProvider + in-memory DuckDB + fake index constituents, `reliance_id`, ...), `test_api.py`, `test_breadth.py`, `test_engine.py`, `test_market.py`, `test_data_quality.py`, `test_performance.py`, `test_screener.py`, `test_storage.py`. Run with `pytest` from `backend/` using `.venv`.
- `backend/scripts/nightly-update.ps1` (runs `markets update`), `register-nightly-task.ps1` (Windows Task Scheduler).
