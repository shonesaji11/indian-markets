---
name: audit
description: Review the nightly market-data update and its data-quality (DQ) checks for this project, investigate new issues, write the findings to a nightly audit file and propose fixes and book-of-work entries for the user to approve. Use after the nightly update (it runs as a scheduled task at 19:00 Mon-Fri, after the 17:00 update) or whenever the user asks about data quality, missing/bad bars, gaps, stale stocks, split-like jumps or failed downloads. Read-only on data and code.
---

# Audit: nightly data-quality review

You are bound by `CLAUDE.md` in the project root (read it first). Above all: **you never change data, code or any file except your own audit file** (step 4), and never `BOOK_OF_WORK.md`. You report, record in the audit file and propose; the user approves every fix (often from their phone), and fixes then go through the normal plan → approval → build flow.

Project root: `C:\Users\shone\OneDrive\Documents\Coding\Python\Indian Markets`. Run commands from `backend\` with `.venv\Scripts\markets.exe`.

## 1. Did the nightly update finish?

The update runs at 17:00 on weekdays (`backend\scripts\nightly-update.ps1`, about 80 minutes for ~3,000 stocks) and logs to `backend\logs\update-YYYY-MM-DD.log` (one file per day; each run starts with `==== <time> nightly update starting`).

- Open the log for the latest weekday run: today's date when you run in the evening as scheduled (if run on a weekend or before 17:00, the previous weekday's).
- It must end with `==== <time> finished with exit code N`. If the starting line has no matching finished line, the update is still running or died: report that, with the last lines of the log, and stop. If the log file is missing, say the update didn't run.
- Note the summary lines: `daily update: X/Y instruments ok, N failed`, errors (`error: ...`), the repair line (`repair: N tried, N bars re-downloaded, N bad bars removed, N resolved, N accepted as provider holes, N rate-limited`) and the data-quality lines (`data quality (incremental|full): ...` then one line per check with found/new/resolved).
- Read the last few blocks of `backend\logs\nightly-summary.log` (one short block per run, kept indefinitely) and compare tonight with previous nights: failures, run time, bar counts, new stocks backfilled. Mention a trend (e.g. failures or run time creeping up) even when tonight looks fine.

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

**What the nightly job already fixes by itself** (`backend\src\markets\pipelines\repair.py`, runs after the downloads): bad prices (missing/zero/negative price, high below low) on any stock are re-downloaded, and removed if still bad (kept in `candle_revisions`; the issue is resolved with a note); gaps on Nifty 500 / Total Market / benchmark stocks are re-downloaded at most once a week, and accepted as "provider hole" after 3 tries. At most 50 re-downloads a night; rate-limited tries don't count. Don't propose re-downloads for these: report what the repair did and only flag what it can't fix (splits, zero volume, gaps on other stocks, anything failing repeatedly). Manual run: `markets repair`.

**Known, left open by choice (don't report):** 22 `gap` issues of NSE's dummy test symbols (`011NSETEST-EQ` … `V1NSETEST`, 2023-04-27 → 2024-10-31). They're no longer synced into `nse_traded`; the user chose to leave the issues as they are (2026-11-19).

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

Write the full findings to `backend\logs\audit-YYYY-MM-DD.md` (the date of the update you audited; overwrite it if you re-run that day). The folder is gitignored and the file is kept: it is the nightly record (update status, what the repair did, the groups found with numbers and causes). It is the only file you may write; never commit.

Never edit `BOOK_OF_WORK.md`: it holds only items the user chooses to work on. When a group needs action and isn't already in it, draft an entry (dated, for **Bugs**, in the book's format: check, affected stocks/dates, likely cause, options and your recommendation) for the report's "Proposed for the book of work" section; the user decides whether it goes in. Also say there if an existing entry looks resolved or out of date. Don't propose entries for expected short history or for issues already accepted.

## 5. Report to the user

Keep it short and phone-readable:

1. Update status: finished at <time>, X/Y ok, N failed (and why).
2. DQ summary: open issues per check; new tonight; resolved tonight.
3. New groups needing attention, each with likely cause and the proposed fix (e.g. "re-download TCS 1–31 Mar: `markets ingest NSE:TCS-EQ --start 2024-03-01 --end 2024-03-31`"). Any fix that changes bars, mappings or watchlists also lists the rebuilds it needs from `markets-codebase/references/derived-data.md` (e.g. "then `markets breadth --backfill`, since the bars are older than 10 days").
4. Issues that look fine to accept, each with the exact command for the user to run or approve: `markets dq accept <issue_id> --note "<why>"`.
5. Anything that needs the user's decision.
6. Proposed for the book of work: each drafted entry, and any existing entry that looks resolved (leave this out when there is none).

End with the path of tonight's audit file. If there is nothing new: one line saying the update finished cleanly and no new DQ issues, plus the audit file's path.
