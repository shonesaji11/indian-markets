# Working rules

All rules, preferences and project knowledge live in the project: this file, `BOOK_OF_WORK.md` (local only, see below), and the skills under `.claude/skills/`. Never save them to Claude's personal memory; when I give a lasting instruction, add it here.

## Be objective (very important)
- Never agree with me to flatter me or just to sound agreeable. Judge every idea, plan or approach on its merits.
- If my thinking is inefficient, wrong or missing something, say so directly, explain why, and propose the better option. Challenge my assumptions, including in trading ideas and feature requests.
- When you agree, say why in concrete terms; when you're unsure, say that instead of hedging toward my view.

## Right first time, not fast (very important)
- There is never pressure to move fast. The only goal is to get it right the first time, without back-and-forth or fixing mistakes afterwards.
- Take as long as needed: think the task through, read the code involved, and verify each step. Never skip a read, a check or a diff review to save time or context.

## Before writing code
- For any non-trivial feature or change: decide the architecture first (where it lives, data flow, interfaces, storage), present a short plan, and wait for my go-ahead before implementing.
- Every visible UI change gets a mockup first, including small, specific tweaks I ask for directly (moving a panel, changing a layout, removing an element). Show an inline visual of the new/changed screen with its states (empty, loading, populated, error where relevant) and wait for my OK before writing code.
- Think through edge cases up front (empty/missing data, holidays and gaps, timezones, rate limits, partial failures) and discuss them with me before coding.
- UI style: for quick actions (menus, pickers, add to list, rename, confirm a delete) use a small drop-down under its button (`components/ui/Popover`), not a centred dialog over a dimmed page. Keep the screen lean: no counts or status labels unless they help a decision. In mockups, label pop-up states clearly as separate from the page.
- When requirements are ambiguous, ask me instead of guessing. Trivial fixes (typos, one-line bugs) don't need a plan; just do them.
- Ideas I mention in passing ("for the future", "maybe"): answer the direct question, add a short dated entry under Ideas in `BOOK_OF_WORK.md`, say in one line that it's logged, and move on. No investigation, plan or mockup unless I ask to build it.
- Book of work: anything left unresolved (an ambiguity we park, a known limitation, a bug outside the task, an idea for later) goes into `BOOK_OF_WORK.md` in the right section, dated, with the options considered and the current behaviour. Check it before working in an area, and delete items once they're resolved.
- The book of work holds only things still to do or decide. Before every commit, re-read the items in the areas the work touched: delete any it resolved (the work's commit and PR are the record), and cut partly resolved ones down to what's left. Never leave an entry that only describes finished work.
- `BOOK_OF_WORK.md` is local only: gitignored and never committed, kept in the main folder (backed up by OneDrive). Read and edit it there in place, also when the work itself is in a worktree; it is the one file in the main folder you may edit. It holds only items I want to work on or decide: the nightly audit proposes entries in its report but never writes them.

## Code style
- Keep code simple and concise. Prefer the smallest change that solves the problem over a larger refactor, as long as speed doesn't suffer.
- Prefer vectorized code (pandas/NumPy/DuckDB SQL) over Python loops for data work.
- No speculative abstractions, options or layers that nothing uses yet.
- Nothing in the browser console: no `console.*` calls (or `debugger`) in shipped frontend code. Use them only temporarily while building or checking edge cases, and remove them before committing. Secrets never reach the browser in any form.

## Editing code safely
- Find the code via the `markets-codebase` map and a search for its name, then read the exact lines before changing them. Never edit by cutting between two places whose position you assumed.
- Change only what you read: each edit must match exactly one spot, or stop. Check whether a file exists before writing it, and add to existing files rather than overwriting them.
- Run formatters only on new files, never over existing ones (there is no project formatter config, so it reflows untouched code).
- After each batch of edits, review `git diff` and account for every removed line before running tests.

## Modularity and reuse
- Before writing anything new, search for an existing component, function, repository method or service that does it (or nearly does), and reuse or extend it. Never copy-paste logic; if two places need it, extract it.
- Build new features as reusable pieces: put general logic in the shared layer it belongs to, not inside the one page/router/pipeline that first needs it. Make the piece reusable through where it lives and how it's called, not through extra layers.
- Follow the existing structure instead of inventing a new one:
  - Classes for things with state or dependencies: providers (`providers/`), repositories (`storage/duckdb/repositories.py`), services (`pipelines/`), wired together in `bootstrap.py`'s `Container`. Layers talk through the `Protocol`s in `core/ports.py`.
  - Plain functions for stateless computation: indicators are `@indicator`-registered functions over a candle DataFrame (`engine/indicators/`), which makes them usable on the chart and in custom scans automatically; built-in Overview scans go in `engine/scans.py`; custom-scan filter logic is in `engine/screener.py`. Don't wrap pure functions in classes.
  - Frontend: generic UI in `components/ui` / `components/charts` (exported via `index.ts`), feature-specific pieces in `features/<area>/`, data access via `api/queries.ts`, shared logic in `hooks/` and `lib/`.

## Testing new calculations and features
- Whenever a new calculation (indicator, scan, SQL column/macro, breadth or screener logic) or feature is added or changed, add tests for it: reference values for correctness, plus the data-quality edge cases (short history, gaps, zero/NaN price or volume, flat prices, unsorted/duplicate bars, stale instruments).
- Then run the full backend test suite (`pytest` in `backend/`), not just the new tests, and fix every failure before calling the work done.
- Keep command output small (it fills the context): tests print only the pass/fail count when they pass (`pytest -q` piped to `tail -2`), and on failure only the failing tests and the lines that explain them (`--tb=short`, trimmed); deeper logs only when we dig in. Same for builds, diffs and long files: review everything, print counts or the few lines that matter. Prefer page text over screenshots, and take a small screenshot only when the look itself is being checked.
- If a failure or an edge case has no obvious right answer, don't pick one silently. Explain the issue and its context, lay out a few possible solutions with their trade-offs and your recommendation, then wait for my decision and implement what I choose.

## Before calling work done (very important)
- Walk every rule in this file, one by one, as an explicit step in the task plan before the commit step: `markets-codebase` map (SKILL.md and every touched entry in references/*.md), derived-data registry, `BOOK_OF_WORK.md`, tests for every new feature or calculation (frontend too) plus a full backend `pytest` run, secret checks. If a rule seems not to apply, say so and ask; never skip one silently.
- Report every failure from the task in one clearly labelled list in the closing message, never scattered across messages: failing tests, typecheck or build errors, tool or script errors, anything that went wrong. For each: what failed, why, and what you did (fixed the code, fixed the test, reverted, worked around). Any failure resolved by changing behaviour, rather than fixing a bug, is my decision: ask instead of deciding.

## Data correctness lives in the nightly job
- Detecting and repairing wrong data (splits/bonuses, bad bars) belongs to the nightly ingestion job (`DailyUpdateService` and what it calls). Calculations, scans and UI assume stored candles are correct and don't each re-check them.
- Downstream code still handles data that is real but incomplete (holidays and gaps, short history, suspended stocks, NaN/zero volume) and is tested for it.

## Derived data and rebuilds (very important)
- Every stored computed result (sector breadth, indicator values, DQ issues, and anything added later) is listed in `.claude/skills/markets-codebase/references/derived-data.md` with its inputs and rebuild command.
- Any code that saves computed results (a new table filled from other tables, a cache, an output file, or a new writer to an existing one) must add or update its section there in the same change. Prefer a version guard and a rebuild command over relying on someone remembering.
- Whenever an input changes or turns out wrong (re-downloaded or corrected bars, split fixes, sector mapping or watchlist changes, a logic change in a calculation), or a log, error, DQ issue or my message points to one, check that file and run (or, in the audit, propose) the matching rebuild. Say which rebuilds ran.

## Before every commit: secret checks and message
- Commit message: a summary of the changes made. A short subject line naming the change, then a body listing what changed and where (features, files/areas, docs), in plain words.
- Review the file list (`git status --short`): no `.env`, `ngrok-policy.yml`, logs, `*.duckdb`, or other local/secret files staged. New secret files get a `.gitignore` entry first.
- Scan the staged diff (`git diff --cached`) for credentials: API keys, passwords, PINs, TOTP secrets, tokens (`Bearer`, `eyJ...` JWTs), `authtoken`, IPs/MAC addresses, real account or client codes. Example files must hold placeholders only.
- Search `frontend/src` for `console.` and `debugger`: remove any found (see Code style).
- If anything turns up, unstage it, move the value to a gitignored file, and tell me before committing.

## Branches and pull requests (several chats work here at once)
- The main folder stays on `main` and is never edited: no file changes (except the untracked `BOOK_OF_WORK.md`), commits, branch switches or stashes there. It runs the app and only fast-forwards (`git pull --ff-only`) after a merge. A `git checkout` there would change the branch under every other chat.
- Every change (code or docs, however small) starts in its own worktree on a new branch from the latest `origin/main`, outside OneDrive (so `node_modules` and DB files aren't synced): `git fetch origin`, then `git worktree add C:\Users\shone\worktrees\markets-<name> -b feat/<name> origin/main`. The frontend needs its own `npm install` and the backend a copy of `backend/.env`; run backend tests with the main folder's `.venv` python and `PYTHONPATH=src` so the worktree's code is the one tested. Subagents that edit files work in that same worktree, never in the main folder.
- When the work is done and checked ("Before calling work done"): commit on the branch, `git fetch origin` and rebase onto `origin/main` (re-run the tests if `main` moved), push the branch, open a PR with `gh pr create` (body = the commit message), give me the link, and stop.
- If the rebase conflicts with another chat's merged work, resolve it only when it is clearly mechanical, re-run the tests, and say so; otherwise stop and tell me.
- Merge only after I approve it in that chat. Then: `git worktree remove` the folder, and from the main folder `gh pr merge <number> --merge --delete-branch` (deletes the branch on GitHub and locally), `git fetch --prune` (drops the local record of branches deleted on GitHub) and `git pull --ff-only`. Never push to `main` directly.

## Project context
- Backend: `backend/src/markets` (FastAPI + DuckDB). Frontend: React in `frontend/`.
- Before planning or changing code, use the `markets-codebase` skill (`.claude/skills/markets-codebase/`) to find the exact files and symbols, then read only those ranges instead of whole files.
- For anything touching the Angel One / SmartAPI broker API, use the `angelone-smartapi` skill (`.claude/skills/angelone-smartapi/`) and read only the reference file you need.
- When a change adds, removes, renames or moves a module, public function/class, route, table, page or shared component, update the `markets-codebase` map in the same change.
- Broad searches and long reads go to a Sonnet subagent (Explore agent, `model: sonnet`) that brings back only the conclusion: sweeps across many files or names the map doesn't pin down, whole-codebase usage checks, and logs or command outputs too long to read in full. It locates and summarises only. Planning, design, edits and judgement calls stay in the main session, which still reads the exact lines itself before changing them. A single file or a quick grep doesn't need one.
