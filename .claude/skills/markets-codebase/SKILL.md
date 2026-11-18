---
name: markets-codebase
description: Map of this repo (Indian markets dashboard; FastAPI + DuckDB backend in backend/src/markets, React + Vite frontend in frontend/src). Use BEFORE planning or making any code change, adding a feature, fixing a bug or answering "where is X / how does Y work" in this project, so you can jump to the exact file and symbol instead of reading whole files. Covers layers, data flow, where each concern lives, and recipes for adding indicators, scans, endpoints, tables, pages and components. Also the derived-data registry, which lists what stored results (sector breadth, all-time highs, indicator values, DQ issues) must be rebuilt, and how, when bars, sector mappings, watchlists or calculation logic change or turn out wrong.
---

# Markets codebase map

Use this to pick the files to open, then open only those (and only the relevant line ranges, found via Grep). The code is the source of truth: if something here disagrees with the code, trust the code and **fix this map in the same change**.

## Layers (backend `backend/src/markets/`)

```
providers/ (Angel One, Fake) ─┐                     ┌─ api/routers/* (FastAPI, /api prefix)
sources/ (NSE index CSVs) ────┼─> pipelines/* ──────┼─ cli.py (`markets ...` commands)
engine/ (indicators, scans) ──┘   (services)        └─ scripts/*.ps1 (nightly task)
storage/duckdb/ (repositories, SQL migrations) <──── all services read/write through repos
core/ (models + Protocol ports) ── shared by everything; bootstrap.py wires the Container
```

- Layers depend on `core/ports.py` Protocols, not concrete classes. `bootstrap.build_container()` builds everything once; routers get it via `api/deps.get_container`.
- Candle frames everywhere: DatetimeIndex `ts` (**naive IST**) + float `open, high, low, close, volume` (`core/models.CANDLE_COLUMNS`).
- Intervals: `core/models.Interval` (`1m 3m 5m 10m 15m 30m 1h 1d`), mirrored in `frontend/src/api/types.ts` `INTERVALS`.
- Config: `config.Settings`, env vars `MARKETS_*` or `backend/.env` (`provider` = `angelone` | `fake`, `angel_*` credentials, `db_path`, `cors_origins`).
- Versioned, immutable computations: indicators (`@indicator(name, version=...)`), scans (`@scan(name, version, ...)`), SQL (`v_daily_stats_v1`, `daily_signals_v1`). Changing logic = bump the version / add `_v2`, never edit v1 in place (the calc repo raises `CodeChangedError` on a changed code hash).

## Frontend (`frontend/src/`)

Launcher: repo-root `start-dashboard.bat` starts backend, Vite and an ngrok tunnel to :5173 (password from gitignored `ngrok-policy.yml`; Vite `server.allowedHosts` admits ngrok domains). Pages (`pages/`, routes in `App.tsx`): `/` Overview, `/chart` Chart, `/scans` Scans, `/sector` Sector, `/watchlists` Watchlists (Chart page + your list as the side pane; Performance view since a date), `/data` Data. Data access only through `api/queries.ts` (TanStack Query hooks) over `api/client.ts` (`/api`, proxied to :8000 by Vite). Types in `api/types.ts` mirror `api/schemas.py`. Page filters/sort/selections live in the URL via `hooks/useUrlState` (so Back, reload and links restore the view); never plain `useState` for them. Per-browser preferences (theme, the Chart page's remembered indicator set, used when a link has no `ind`) go through `lib/storage.ts` (`loadSetting`/`saveSetting`, localStorage with try/catch; `session` flag for per-tab sessionStorage). Anything that opens a chart from a list of stocks uses `features/charts/chartList.useOpenChart(id, list)`, so the chart page shows that list beside it in the order displayed (`DataTable`'s `onRowClick(row, shown)` gives that order). Generic UI in `components/ui` (import from `components/ui/index.ts`), chart in `components/charts`, feature pieces in `features/<area>/`, formatting in `lib/format.ts` / `lib/time.ts`.

## Where to add things

| Task | Do this |
|---|---|
| New indicator | Function in `engine/indicators/{trend,momentum,volatility}.py` with `@indicator(...)` (a new module must also be imported in `engine/indicators/__init__.py`); registered via `engine/registry.default_registry`. Instantly available to `/api/calcs/*`, CLI `compute` and the chart's IndicatorPicker. Overlay vs separate pane: `features/indicators/toChartSeries.isOverlay`. |
| New field for custom scans | Add a `ScanField` to `engine/screener.FIELDS` (must be a `daily_signals_v1` column); it appears in the Scans page pickers automatically. New indicators are scannable with no extra work. |
| New built-in overview scan | `@scan(...)` function in `engine/scans.py` taking the snapshot DataFrame; it shows up in the overview's `scans`. New snapshot columns come from `daily_signals_v1` (SQL) via `DuckMarketRepository.snapshot`. |
| New data source / broker | Implement `MarketDataProvider` (or `ConstituentSource`) from `core/ports.py`; register in `providers/build_provider`. Follow the naming/format rules in the `MarketDataProvider` docstring. Angel One API details: `angelone-smartapi` skill. |
| New table / view / SQL macro | New numbered file in `storage/duckdb/migrations/` (applied by `migrator.migrate`), plus methods on a repo in `storage/duckdb/repositories.py` (add to the Protocol in `core/ports.py` if services use it). |
| New business workflow | Service class in `pipelines/`, add it to `Container` + `build_container` in `bootstrap.py`, expose via a router and/or `cli.py`. |
| New endpoint | Router in `api/routers/` (reuse an existing one by area), Pydantic models in `api/schemas.py`, include in `api/app.py` if new. Then TS type in `api/types.ts` + hook in `api/queries.ts` (add a key to `keys`). |
| New watchlist / universe | `universes.WATCHLISTS` (`WatchlistSpec` with NSE `index` slug or explicit `EXCHANGE:SYMBOL` members). Your hand-picked lists are different: rows with `source = 'manual'` in the same tables, edited from the Watchlists tab / chart ☆ through `DuckWatchlistRepository.*_manual` and `/api/watchlists/mine`. |
| New page | `pages/XPage.tsx` + route in `App.tsx` + entry in the `NAV` array, both in `App.tsx`. Compose from `components/ui` and `features/*`. |
| New list that opens charts | Call `useOpenChart()(instrumentId, {title, context, items: toListItems(shownRows)})` from `features/charts/chartList.ts`; never `navigate('/chart?…')` directly. |
| New data-quality check | Pure `find_*` function in `engine/data_quality.py` + wire it into `DataQualityService` (`BAR_CHECKS` if it looks at bars, `GLOBAL_CHECKS` otherwise), bump `DQ_VERSION`, describe it in `.claude/skills/audit/SKILL.md`. The nightly audit (scheduled task, `audit` skill) reads `markets dq report` |
| New UI widget | Generic → `components/ui/` and export from `index.ts`; feature-specific → `features/<area>/`. Check the existing list in references/frontend.md first. |
| New stored derived data | Anything that writes computed results (a table filled from other tables, a cache, an output file): add a section to `references/derived-data.md` (writer, inputs, guards, rebuild command, which input changes need which rebuild) in the same change. Prefer a version guard and a rebuild command over relying on someone remembering. |

## References

| File | Contents |
|---|---|
| `references/backend.md` | Every backend module: classes, public methods, routes, DB tables, CLI commands, tests |
| `references/frontend.md` | Every frontend file: exported components/hooks/types and what they're for |
| `references/derived-data.md` | Every stored computed result: its inputs, what rebuilds it, and which input changes (bar fixes, mapping or watchlist changes, logic changes) need which rebuild |

## Keeping this map current

When a change adds, removes, renames or moves a module, public class/function, route, table, page or shared component, update the matching line here or in the reference file as part of the same change. Keep entries to one line.
