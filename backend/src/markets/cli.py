"""Command line entry point: `markets <command>` (or `python -m markets.cli`).

Write commands open the DuckDB file directly, so stop the API server first, or use
the equivalent API endpoints while it is running.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Optional

from markets.core.models import Interval


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _resolve(container, refs: list[str]) -> list[int]:
    """Accept instrument ids or EXCHANGE:SYMBOL references like NSE:RELIANCE-EQ."""
    ids = []
    for ref in refs:
        if ref.isdigit():
            ids.append(int(ref))
            continue
        exchange, _, symbol = ref.partition(":")
        instrument = container.instruments.find(exchange, symbol)
        if instrument is None:
            raise SystemExit(f"unknown instrument {ref}; run `markets sync-instruments` or `markets search`")
        ids.append(instrument.instrument_id)
    return ids


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="markets")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the database and apply migrations")
    sub.add_parser("sync-instruments", help="download the provider's instrument master")

    p = sub.add_parser("search", help="find instruments")
    p.add_argument("query")
    p.add_argument("--exchange")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("ingest", help="fetch candles into the database")
    p.add_argument("instruments", nargs="+", help="ids or EXCHANGE:SYMBOL, e.g. NSE:RELIANCE-EQ")
    p.add_argument("--interval", default="1d", choices=[i.value for i in Interval])
    p.add_argument("--start", help="YYYY-MM-DD; default: incremental from last stored bar")
    p.add_argument("--end", help="YYYY-MM-DD; default: now")

    p = sub.add_parser("compute", help="run an indicator and store its values")
    p.add_argument("name")
    p.add_argument("instruments", nargs="+")
    p.add_argument("--interval", default="1d", choices=[i.value for i in Interval])
    p.add_argument("--param", action="append", default=[], help="key=value, repeatable")

    sub.add_parser("coverage", help="show what candles are stored")

    p = sub.add_parser("update", help="nightly job: sync instruments + watchlists, fetch new daily bars")
    p.add_argument("--skip-instrument-sync", action="store_true")
    p.add_argument("--api", default="http://127.0.0.1:8000",
                   help="server to hand the job to if it holds the database lock")
    p.add_argument("--scheduled", action="store_true", help="mark the summary as the scheduled nightly run")

    p = sub.add_parser("breadth", help="recompute stored sector breadth (last 10 days, or all history)")
    p.add_argument("--backfill", action="store_true", help="recompute every day since the first candle")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API server to use when it holds the database")

    p = sub.add_parser("repair", help="re-download fixable data-quality issues now; remove bars still bad")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API server to use when it holds the database")

    p = sub.add_parser("highs", help="bring the all-time-high cache up to date (changed stocks only)")
    p.add_argument("--rebuild", action="store_true", help="recompute every stock's full history")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API server to use when it holds the database")

    p = sub.add_parser("watchlists", help="sync watchlists from universes.py and list them")
    p.add_argument("--no-sync", action="store_true")

    p = sub.add_parser("dq", help="data-quality issues: report, run checks, accept known issues")
    dq = p.add_subparsers(dest="dq_command", required=True)
    q = dq.add_parser("report", help="issue counts, then the issues matching the filters")
    q.add_argument("--status", default="open", help="open (default), resolved, accepted or all")
    q.add_argument("--check", help="one check: gap, bad_bar, jump, stale, short_history, failed_download")
    q.add_argument("--instrument", help="id or EXCHANGE:SYMBOL")
    q.add_argument("--limit", type=int, default=200)
    q = dq.add_parser("check", help="run checks now (default: all, on bars ingested since the last run)")
    q.add_argument("--check", action="append", help="limit to this check; repeatable")
    q.add_argument("--instrument", action="append", help="limit to this instrument (all its history); repeatable")
    q.add_argument("--full", action="store_true", help="re-check all history")
    q = dq.add_parser("accept", help="mark an issue as known and fine")
    q.add_argument("issue_id")
    q.add_argument("--note", required=True, help="why it is fine")
    for q in dq.choices.values():
        q.add_argument("--api", default="http://127.0.0.1:8000", help="API server to use when it holds the database")

    p = sub.add_parser("serve", help="run the API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "serve":
        import uvicorn

        uvicorn.run("markets.api.main:app", host=args.host, port=args.port, reload=args.reload)
        return

    import duckdb

    from markets.bootstrap import build_container

    try:
        c = build_container()
    except duckdb.IOException as exc:
        # Linux/macOS say "Could not set lock on file"; Windows says "File is already open in ...".
        busy = any(s in str(exc).lower() for s in ("lock", "already open"))
        if args.command == "update" and busy:
            _update_via_api(args.api, not args.skip_instrument_sync, args.scheduled)
            return
        if args.command == "dq" and busy:
            print(f"database is in use by the API server; using {args.api}")
            _dq_via_api(args)
            return
        if args.command == "breadth" and busy:
            print(f"database is in use by the API server; running through {args.api}")
            print(f"sector breadth: {_post_api(args.api, '/api/jobs/breadth', {'backfill': args.backfill})['rows']} rows")
            return
        if args.command == "repair" and busy:
            print(f"database is in use by the API server; running through {args.api}")
            _print_repair(_post_api(args.api, "/api/jobs/repair", {}))
            return
        if args.command == "highs" and busy:
            print(f"database is in use by the API server; running through {args.api}")
            print(f"all-time highs: {_post_api(args.api, '/api/jobs/highs', {'rebuild': args.rebuild})['rows']} rows")
            return
        raise SystemExit(f"database is locked by another process (is `markets serve` running?): {exc}")
    try:
        if args.command == "init-db":
            print(f"database ready at {c.db.path}")
        elif args.command == "sync-instruments":
            print(f"synced {c.ingestion.sync_instruments()} instruments from {c.provider.name}")
        elif args.command == "search":
            for i in c.instruments.search(args.query, args.exchange, limit=args.limit):
                print(f"{i.instrument_id:>8}  {i.exchange}:{i.symbol:<28} {i.instrument_type or '':<8} {i.name}")
        elif args.command == "ingest":
            interval = Interval(args.interval)
            for instrument_id in _resolve(c, args.instruments):
                r = c.ingestion.ingest(instrument_id, interval, _parse_date(args.start), _parse_date(args.end))
                print(f"{instrument_id}: {r.status}, {r.rows} bars written" + (f" ({r.error})" if r.error else ""))
        elif args.command == "compute":
            params = dict(kv.split("=", 1) for kv in args.param)
            for instrument_id in _resolve(c, args.instruments):
                o = c.calc_service.compute(args.name, instrument_id, Interval(args.interval), params)
                print(f"{instrument_id}: {o.name} v{o.version} {o.params} -> calc_id {o.calc_id}, {o.rows} values")
        elif args.command == "update":
            report = c.daily_update.run(sync_instruments=not args.skip_instrument_sync)
            _print_report(report.to_dict())
            _append_summary(report.to_dict(), args.scheduled)
            if report.failed and not report.ok:
                raise SystemExit(1)
        elif args.command == "breadth":
            rows = c.breadth.backfill() if args.backfill else c.breadth.update()
            print(f"sector breadth: {rows} rows")
        elif args.command == "repair":
            _print_repair(c.daily_update.repair_now())
        elif args.command == "highs":
            print(f"all-time highs: {c.ath.refresh(full=args.rebuild)} rows")
        elif args.command == "watchlists":
            if not args.no_sync:
                for r in c.watchlist_sync.sync_all():
                    print(f"synced {r['watchlist_id']}: {r['members']} members (+{r['added']} -{r['removed']})"
                          + (f", {len(r['missing'])} not found" if r["missing"] else ""))
            for w in c.watchlists.all():
                print(f"{w['watchlist_id']:<12} {w['members']:>4}  {w['name']}")
        elif args.command == "dq":
            _dq_direct(c, args)
        elif args.command == "coverage":
            for row in c.candles.coverage():
                print(f"{row['exchange']}:{row['symbol']:<24} {row['timeframe']:>4}  {row['bars']:>7} bars  "
                      f"{row['first_ts']} -> {row['last_ts']}")
    finally:
        c.close()


def _print_report(r: dict) -> None:
    took = (r["finished_at"] - r["started_at"]) if not isinstance(r["finished_at"], str) else None
    print(f"daily update: {r['ok']}/{r['targets']} instruments ok, {r['failed']} failed "
          f"({r.get('retried', 0)} retried), "
          f"{r['bars_written']} bars written, {r.get('breadth_rows', 0)} sector breadth rows"
          + (f" in {took}" if took else ""))
    for w in r["watchlists"]:
        print(f"  watchlist {w['watchlist_id']}: {w['members']} members (+{w['added']} -{w['removed']})")
    if r.get("data_quality"):
        _print_dq_run(r["data_quality"])
    for e in r["errors"][:20]:
        print(f"  error: {e}")


def _dq_direct(c, args) -> None:
    if args.dq_command == "report":
        ids = _resolve(c, [args.instrument]) if args.instrument else [None]
        _print_dq_report(c.data_quality.report(None if args.status == "all" else args.status, args.check, ids[0], args.limit))
    elif args.dq_command == "check":
        ids = _resolve(c, args.instrument) if args.instrument else None
        _print_dq_run(c.data_quality.run(args.full, args.check, ids))
        _print_dq_report(c.data_quality.report("open", args.check[0] if args.check and len(args.check) == 1 else None,
                                               ids[0] if ids and len(ids) == 1 else None, 200))
    elif args.dq_command == "accept":
        if not c.data_quality.accept(args.issue_id, args.note):
            raise SystemExit(f"no issue {args.issue_id}")
        print(f"accepted {args.issue_id}")


def _dq_via_api(args) -> None:
    import httpx

    if args.dq_command == "report":
        params = {"status": args.status, "check": args.check, "instrument": args.instrument, "limit": args.limit}
        resp = httpx.get(f"{args.api}/api/dq/issues", params={k: v for k, v in params.items() if v is not None})
        resp.raise_for_status()
        _print_dq_report(resp.json())
    elif args.dq_command == "check":
        body = {"full": args.full, "checks": args.check, "instruments": args.instrument}
        resp = httpx.post(f"{args.api}/api/dq/check", json=body, timeout=None)
        resp.raise_for_status()
        _print_dq_run(resp.json())
    elif args.dq_command == "accept":
        resp = httpx.post(f"{args.api}/api/dq/issues/{args.issue_id}/accept", json={"note": args.note})
        resp.raise_for_status()
        print(f"accepted {args.issue_id}")


def _print_dq_run(r: dict) -> None:
    print(f"data quality ({r['mode']}): {r['instruments_rechecked']} instruments re-checked, {r['open']} open issues")
    for name, s in r["checks"].items():
        print(f"  {name:<16} {s['found']:>6} found  {s['new']:>5} new  {s['resolved']:>5} resolved")


def _print_dq_report(r: dict) -> None:
    if not r["counts"]:
        print("no data-quality issues recorded")
    for row in r["counts"]:
        print(f"{row['check_name']:<16} {row['status']:<9} {row['issues']:>6}")
    if r["issues"]:
        print()
    for i in r["issues"]:
        span = str(i["start_ts"])[:10] + ("" if str(i["end_ts"])[:10] == str(i["start_ts"])[:10] else f" -> {str(i['end_ts'])[:10]}")
        print(f"{i['check_name']:<16} {i['exchange'] or ''}:{i['symbol'] or i['instrument_id']:<22} {span:<24} "
              f"{i['detail'] or ''}  [{i['status']}, seen {i['seen_count']}x] {i['issue_id']}")


def _update_via_api(base_url: str, sync_instruments: bool, scheduled: bool) -> None:
    """The API server holds the DuckDB write lock; ask it to run the job instead."""
    print(f"database is in use by the API server; running the update through {base_url}")
    report = _post_api(base_url, "/api/jobs/daily-update", {"sync_instruments": sync_instruments})
    _print_report(report)
    _append_summary(report, scheduled)


def summary_block(r: dict, scheduled: bool) -> str:
    """A few plain lines per daily-update run for logs/nightly-summary.log. `r` is
    DailyUpdateReport.to_dict(), directly or as JSON from the API (timestamps as strings)."""
    start, end = (datetime.fromisoformat(str(r[k])) for k in ("started_at", "finished_at"))
    mins = int((end - start).total_seconds() // 60)
    took = f"{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"{mins}m"
    lines = [f"{start:%Y-%m-%d}  {start:%H:%M}-{end:%H:%M} ({took})  {'scheduled' if scheduled else 'manual'}",
             f"  stocks:   {r['ok']:,}/{r['targets']:,} ok, {r['failed']:,} failed ({r['retried']:,} retried)"]

    bars = r["bars_written"]
    if not bars:
        lines.append("  bars:     0 (no new bars: market holiday?)")
    elif r.get("new_instruments"):  # .get: a server started before these fields existed omits them
        lines.append(f"  bars:     {bars:,} (existing stocks {bars - r['new_bars']:,}; "
                     f"{r['new_instruments']:,} new stocks backfilled {r['new_bars']:,})")
    else:
        lines.append(f"  bars:     {bars:,}")
    lines.append(f"  breadth:  {r['breadth_rows']:,} rows")

    changed = [w for w in r["watchlists"] if w["added"] or w["removed"]]
    lists = "; ".join(f"{w['watchlist_id']} +{w['added']} -{w['removed']}" for w in changed) or "no changes"
    if changed and len(changed) < len(r["watchlists"]):
        lists += "; others unchanged"
    lines.append(f"  lists:    {lists}")

    dq = r.get("data_quality")
    if dq:
        new, resolved = (sum(s[k] for s in dq["checks"].values()) for k in ("new", "resolved"))
        parts = [f"{name} +{s['new']:,}" + (f" -{s['resolved']:,}" if s["resolved"] else "")
                 for name, s in dq["checks"].items()
                 if name != "short_history" and (s["new"] or s["resolved"])]
        lines.append(f"  quality:  {dq['open']:,} open; +{new:,} new, -{resolved:,} resolved ({dq['mode']})"
                     + (f": {', '.join(parts)}" if parts else ""))
    else:
        lines.append("  quality:  not run")

    failed = r.get("failed_symbols", [])
    if failed:
        lines.append("  failed:   " + ", ".join(failed[:5]) + (f" +{len(failed) - 5} more" if len(failed) > 5 else ""))
    else:
        lines.append(f"  failed:   {r['failed']} (see update-{start:%Y-%m-%d}.log)" if r["failed"] else "  failed:   -")
    other = len(r["errors"]) - r["failed"]
    if other > 0:
        lines.append(f"  errors:   {other} other (see update-{start:%Y-%m-%d}.log)")
    return "\n".join(lines) + "\n\n"


def _append_summary(r: dict, scheduled: bool) -> None:
    from markets.config import BACKEND_DIR

    path = BACKEND_DIR / "logs" / "nightly-summary.log"
    try:  # the update itself has finished; a summary problem must not fail the run
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(summary_block(r, scheduled))
    except Exception as exc:
        print(f"  warning: could not write {path.name}: {exc!r}")


def _print_repair(report: dict) -> None:
    """`report` is DailyUpdateReport.to_dict() from `repair_now` (directly or as JSON)."""
    r = report["repair"] or {}
    for e in report["errors"]:
        print(f"  error: {e}")
    if not r:
        return
    print(f"repair: {r['tried']} re-downloaded ({r['bars_written']} bars written), {r['removed']} bad bars removed, "
          f"{r['resolved']} resolved, {r['accepted']} accepted as provider holes, {r['rate_limited']} rate-limited")
    for e in r["errors"][:20]:
        print(f"  error: {e}")


def _post_api(base_url: str, path: str, params: dict) -> dict:
    import httpx

    resp = httpx.post(f"{base_url}{path}", params=params, timeout=None)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    main()
