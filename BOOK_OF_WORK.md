# Book of work

Known issues, open questions and deferred ideas: not deal breakers, but to revisit.
Newest first within each section. When an item is resolved, delete it (git history keeps the record).
Format: **title** (area, date added): the problem, options considered, current behaviour.

## Open questions (need a decision)

- **Small sectors look artificially strong** (sector breadth, 2026-11-17): a sector with 2 stocks both above the 20 MA shows 100% and tops the ranking (on 16 Nov 2026 "Diversified", 1 stock, ranked first). Options: shrink toward the market average (Bayesian / Wilson lower bound), or show a confidence marker. Current behaviour: stock counts shown, "Min stocks" filter (default 5) hides small sectors, ties broken by size.
- **Backtest survivorship bias** (backtest, 2026-11-17): index membership history only exists from when watchlist syncing started, and delisted stocks are missing from Angel's scrip master, so older backtests use today's survivors. Options: source historical index constituents (NSE archives), flag affected date ranges in reports. Not started; backtest plan awaiting go-ahead.

## Known limitations

- **Public link serves the Vite dev server** (launcher, 2026-11-17): the ngrok tunnel points at `npm run dev`, so remote loads are unbundled and slower, and the only protection is ngrok basic auth (one shared password; the app itself has no login). Options: serve the built `frontend/dist` from FastAPI on one port; ngrok Google login instead of a password. Current behaviour: works, protected by `ngrok-policy.yml`.

- **Stored breadth can lag ad-hoc fetches** (sector breadth, 2026-11-17): a day's breadth is stored on first read; bars fetched later that same day via the Data page or "Fetch latest" aren't reflected until the nightly update recomputes the last 10 days. Fix if it matters: recompute breadth after any ingest.
- **Sector labels are not point-in-time** (data, 2026-11-17): `instrument_tags.industry` holds only the latest NSE classification, so past sector breadth uses today's labels. Fix: keep tag history like `watchlist_members` does.
- **Scans run on daily bars only** (scans, 2026-11-17): `engine/screener.TIMEFRAME = "1d"`. Intraday scans would need intraday fields (no `daily_signals` equivalent) and per-interval bar loading.
- **450-day window in `daily_signals_v1`** (scans/overview, 2026-11-17): instruments whose latest bar is more than ~450 days before the as-of date drop out of snapshots.
- **One process can open the database** (infra, 2026-11-17): DuckDB locks the file, so research scripts can't read it while `markets serve` runs. Planned fix: nightly `EXPORT DATABASE` snapshot that research loads into memory.
- **Long scan URLs** (scans UI, 2026-11-17): the filter tree is stored as URL-encoded JSON. Works, but links are long and unreadable. Option: compact or base64url encoding.

## Bugs


## Ideas (later)

- **F&O stocks universe** (scans/overview, 2026-11-18): flag F&O stocks and offer "F&O stocks" in the universe dropdown on Overview and Scans. Sketch: an `fno` watchlist synced nightly from the stored scrip master (underlyings of live NFO `FUTSTK` contracts, mapped to NSE `-EQ`), so membership history and nightly price fetching come for free. Caveats: no history before the first sync (NSE publishes past changes), excluded stocks linger until their last contract expires (up to ~3 months), name mismatches skipped and logged.
- **Open-interest signals for F&O stocks** (scans, 2026-11-18): use futures OI (long/short build-up, OI change vs price change, PCR) as scan signals on the F&O universe. Angel's OI build-up and PCR APIs cover today only, so history has to be collected nightly from now on (or daily futures candles, which carry OI); nothing can be backfilled from Angel. Depends on the F&O universe being in place.
- **Sector breadth over time** (overview, 2026-11-17): which sectors are gaining share of stocks above their MA; plus other time-series charts of breadth. Data is ready: `sector_breadth` holds full daily history for nifty500 / nifty50 / all at MA 10, 20, 50, 200.
- **Chart grid on Scans results** (scans UI, 2026-11-17): reuse the sector view's Table | Charts switch.
