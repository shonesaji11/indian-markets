---
name: audit
description: Review the nightly market-data update and its data-quality (DQ) checks for this project, investigate new issues, record them in BOOK_OF_WORK.md and propose fixes for the user to approve. Use after the nightly update (it runs as a scheduled task at 00:30 Tue-Sat) or whenever the user asks about data quality, missing/bad bars, gaps, stale stocks, split-like jumps or failed downloads. Read-only on data and code.
---

# Audit: nightly data-quality review

You are bound by `CLAUDE.md` in the project root (read it first). Above all: **you never change data or code**. You report, record and propose; the user approves every fix (often from their phone), and fixes then go through the normal plan → approval → build flow.

Project root: `C:\Users\shone\OneDrive\Documents\Coding\Python\Indian Markets`. Run commands from `backend\` with `.venv\Scripts\markets.exe`.

## 1. Did the nightly update finish?

The update runs at 23:00 on weekdays (`backend\scripts\nightly-update.ps1`) and logs to `backend\logs\update-YYYY-MM-DD.log` (one file per day; each run starts with `==== <time> nightly update starting`).

- Open the log for the latest weekday run (yesterday's date when you run after midnight).
- It must end with `==== <time> finished with exit code N`. If the starting line has no matching finished line, the update is still running or died: report that, with the last lines of the log, and stop. If the log file is missing, say the update didn't run.
- Note the summary lines: `daily update: X/Y instruments ok, N failed`, errors (`error: ...`), and the data-quality lines (`data quality (incremental|full): ...` then one line per check with found/new/resolved).

## 2. Read the issues

```
markets dq report                       # counts per check and status, then every open issue
markets dq report --status all --check gap
markets dq report --instrument NSE:TCS-EQ
markets dq check --check gap --instrument NSE:TCS-EQ   # re-run one check on one stock's full history now
markets dq check --full                 # re-check all history (slow-ish; only when needed)
```

The commands work while the API server is running (they go through `http://127.0.0.1:8000/api/dq/...`). Issue ids look like `gap:<instrument_id>:<start date>`.

| Check | Means | Usual causes |
|---|---|---|
| `gap` | Market sessions with no bar between a stock's first and last bar | Suspension, an Angel One data hole, a failed download for that window |
| `bad_bar` | Missing/zero price, high below low, or zero volume (indices exempt) | Bad tick from the provider; illiquid stock with no trades |
| `jump` | Close moved more than 35% vs the previous bar (indices exempt) | Unadjusted split/bonus in stored history, bad tick, genuine move (rare; most NSE stocks have 20% or tighter circuits) |
| `stale` | Current watchlist member with no bar for more than 3 market sessions | Suspended/delisted, symbol or token changed (EQ↔BE series), failed downloads |
| `short_history` | Fewer than 200 bars: stored as **accepted** (expected for new listings), never flagged | Only mention if something looks wrong |
| `failed_download` | Latest daily download attempt for a stock errored | Angel rate limit (`exceeding access rate`), timeouts |

Thresholds and logic: `backend\src\markets\engine\data_quality.py`. Storage: `dq_issues` / `dq_state` (`backend\src\markets\storage\duckdb\migrations\007_data_quality.sql`). Runner and incremental logic: `backend\src\markets\pipelines\data_quality.py`.

## 3. Investigate new and still-open issues

- Group issues (e.g. "212 zero-volume bars across 40 illiquid BE stocks") rather than listing hundreds of rows.
- For each group, find the likely cause. Useful context:
  - The `markets-codebase` skill: map of code, tables and migrations. Use it instead of reading whole files.
  - The `angelone-smartapi` skill when the cause looks like the provider (rate limits, adjusted history, known Angel data gaps such as Nifty 50 28 Aug–12 Sep 2017).
  - Stored bars: `GET http://127.0.0.1:8000/api/candles/<instrument_id>?interval=1d` (or open the chart page).
  - `BOOK_OF_WORK.md` for known issues and decisions (e.g. the split re-fetch idea, the ETF/series-change note on `nse_traded`).
- An issue that resolved itself (re-download filled a gap) needs no action; mention the count only.

## 4. Record

Update `BOOK_OF_WORK.md` under **Bugs** (this is the only file you may edit): one dated entry per new group that needs action, with the check, affected stocks/dates, likely cause, options and your recommendation. Update existing entries instead of duplicating them, and remove entries whose issues are now resolved. Don't add entries for expected short history or for issues already accepted. Do not commit.

## 5. Report to the user

Keep it short and phone-readable:

1. Update status: finished at <time>, X/Y ok, N failed (and why).
2. DQ summary: open issues per check; new tonight; resolved tonight.
3. New groups needing attention, each with likely cause and the proposed fix (e.g. "re-download TCS 1–31 Mar: `markets ingest NSE:TCS-EQ --start 2024-03-01 --end 2024-03-31`").
4. Issues that look fine to accept, each with the exact command for the user to run or approve: `markets dq accept <issue_id> --note "<why>"`.
5. Anything that needs the user's decision.

If there is nothing new: one line saying the update finished cleanly and no new DQ issues.
