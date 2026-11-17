# Working rules

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

## Modularity and reuse
- Before writing anything new, search for an existing component, function, repository method or service that does it (or nearly does), and reuse or extend it. Never copy-paste logic; if two places need it, extract it.
- Build new features as reusable pieces: put general logic in the shared layer it belongs to, not inside the one page/router/pipeline that first needs it. Make the piece reusable through where it lives and how it's called, not through extra layers.
- Follow the existing structure instead of inventing a new one:
  - Classes for things with state or dependencies: providers (`providers/`), repositories (`storage/duckdb/repositories.py`), services (`pipelines/`), wired together in `bootstrap.py`'s `Container`. Layers talk through the `Protocol`s in `core/ports.py`.
  - Plain functions for stateless computation: indicators are `@indicator`-registered functions over a candle DataFrame (`engine/indicators/`), which makes them usable on the chart and in custom scans automatically; built-in Overview scans go in `engine/scans.py`; custom-scan filter logic is in `engine/screener.py`. Don't wrap pure functions in classes.
  - Frontend: generic UI in `components/ui` / `components/charts` (exported via `index.ts`), feature-specific pieces in `features/<area>/`, data access via `api/queries.ts`, shared logic in `hooks/` and `lib/`.

## Before every commit: secret checks
- Review the file list (`git status --short`): no `.env`, `ngrok-policy.yml`, logs, `*.duckdb`, or other local/secret files staged. New secret files get a `.gitignore` entry first.
- Scan the staged diff (`git diff --cached`) for credentials: API keys, passwords, PINs, TOTP secrets, tokens (`Bearer`, `eyJ...` JWTs), `authtoken`, IPs/MAC addresses, real account or client codes. Example files must hold placeholders only.
- If anything turns up, unstage it, move the value to a gitignored file, and tell me before committing.

## Project context
- Backend: `backend/src/markets` (FastAPI + DuckDB). Frontend: React in `frontend/`.
- Before planning or changing code, use the `markets-codebase` skill (`.claude/skills/markets-codebase/`) to find the exact files and symbols, then read only those ranges instead of whole files.
- For anything touching the Angel One / SmartAPI broker API, use the `angelone-smartapi` skill (`.claude/skills/angelone-smartapi/`) and read only the reference file you need.
- When a change adds, removes, renames or moves a module, public function/class, route, table, page or shared component, update the `markets-codebase` map in the same change.
