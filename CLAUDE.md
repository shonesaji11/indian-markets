# Working rules

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
- When requirements are ambiguous, ask me instead of guessing. Trivial fixes (typos, one-line bugs) don't need a plan; just do them.
- Book of work: anything left unresolved (an ambiguity we park, a known limitation, a bug outside the task, an idea for later) goes into `BOOK_OF_WORK.md` in the right section, dated, with the options considered and the current behaviour. Check it before working in an area, and delete items once they're resolved.

## Code style
- Keep code simple and concise. Prefer the smallest change that solves the problem over a larger refactor, as long as speed doesn't suffer.
- Prefer vectorized code (pandas/NumPy/DuckDB SQL) over Python loops for data work.
- No speculative abstractions, options or layers that nothing uses yet.

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
- If a failure or an edge case has no obvious right answer, don't pick one silently. Explain the issue and its context, lay out a few possible solutions with their trade-offs and your recommendation, then wait for my decision and implement what I choose.

## Before every commit: secret checks and message
- Commit message: a summary of the changes made. A short subject line naming the change, then a body listing what changed and where (features, files/areas, docs), in plain words.
- Review the file list (`git status --short`): no `.env`, `ngrok-policy.yml`, logs, `*.duckdb`, or other local/secret files staged. New secret files get a `.gitignore` entry first.
- Scan the staged diff (`git diff --cached`) for credentials: API keys, passwords, PINs, TOTP secrets, tokens (`Bearer`, `eyJ...` JWTs), `authtoken`, IPs/MAC addresses, real account or client codes. Example files must hold placeholders only.
- If anything turns up, unstage it, move the value to a gitignored file, and tell me before committing.

## Project context
- Backend: `backend/src/markets` (FastAPI + DuckDB). Frontend: React in `frontend/`.
- Before planning or changing code, use the `markets-codebase` skill (`.claude/skills/markets-codebase/`) to find the exact files and symbols, then read only those ranges instead of whole files.
- For anything touching the Angel One / SmartAPI broker API, use the `angelone-smartapi` skill (`.claude/skills/angelone-smartapi/`) and read only the reference file you need.
- When a change adds, removes, renames or moves a module, public function/class, route, table, page or shared component, update the `markets-codebase` map in the same change.
