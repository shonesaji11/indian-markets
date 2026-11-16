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

    p = sub.add_parser("breadth", help="recompute stored sector breadth (last 10 days, or all history)")
    p.add_argument("--backfill", action="store_true", help="recompute every day since the first candle")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API server to use when it holds the database")

    p = sub.add_parser("watchlists", help="sync watchlists from universes.py and list them")
    p.add_argument("--no-sync", action="store_true")

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
            _update_via_api(args.api, not args.skip_instrument_sync)
            return
        if args.command == "breadth" and busy:
            print(f"database is in use by the API server; running through {args.api}")
            print(f"sector breadth: {_post_api(args.api, '/api/jobs/breadth', {'backfill': args.backfill})['rows']} rows")
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
            if report.failed and not report.ok:
                raise SystemExit(1)
        elif args.command == "breadth":
            rows = c.breadth.backfill() if args.backfill else c.breadth.update()
            print(f"sector breadth: {rows} rows")
        elif args.command == "watchlists":
            if not args.no_sync:
                for r in c.watchlist_sync.sync_all():
                    print(f"synced {r['watchlist_id']}: {r['members']} members (+{r['added']} -{r['removed']})"
                          + (f", {len(r['missing'])} not found" if r["missing"] else ""))
            for w in c.watchlists.all():
                print(f"{w['watchlist_id']:<12} {w['members']:>4}  {w['name']}")
        elif args.command == "coverage":
            for row in c.candles.coverage():
                print(f"{row['exchange']}:{row['symbol']:<24} {row['timeframe']:>4}  {row['bars']:>7} bars  "
                      f"{row['first_ts']} -> {row['last_ts']}")
    finally:
        c.close()


def _print_report(r: dict) -> None:
    took = (r["finished_at"] - r["started_at"]) if not isinstance(r["finished_at"], str) else None
    print(f"daily update: {r['ok']}/{r['targets']} instruments ok, {r['failed']} failed, "
          f"{r['bars_written']} bars written, {r.get('breadth_rows', 0)} sector breadth rows"
          + (f" in {took}" if took else ""))
    for w in r["watchlists"]:
        print(f"  watchlist {w['watchlist_id']}: {w['members']} members (+{w['added']} -{w['removed']})")
    for e in r["errors"][:20]:
        print(f"  error: {e}")


def _update_via_api(base_url: str, sync_instruments: bool) -> None:
    """The API server holds the DuckDB write lock; ask it to run the job instead."""
    print(f"database is in use by the API server; running the update through {base_url}")
    _print_report(_post_api(base_url, "/api/jobs/daily-update", {"sync_instruments": sync_instruments}))


def _post_api(base_url: str, path: str, params: dict) -> dict:
    import httpx

    resp = httpx.post(f"{base_url}{path}", params=params, timeout=None)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    main()
