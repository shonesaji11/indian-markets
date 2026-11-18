from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

import pandas as pd

from markets.core.models import CANDLE_COLUMNS, Instrument, Interval, ProviderInstrument
from markets.storage.duckdb.connection import Database

_INSTRUMENT_COLS = "instrument_id, exchange, symbol, name, instrument_type, lot_size, tick_size, expiry, strike"


def _new_id() -> str:
    return uuid.uuid4().hex


def _row_to_instrument(row: tuple) -> Instrument:
    instrument_id, exchange, symbol, name, itype, lot, tick, expiry, strike = row
    return Instrument(
        instrument_id=instrument_id, exchange=exchange, symbol=symbol, name=name, instrument_type=itype,
        lot_size=lot, tick_size=tick, expiry=expiry, strike=strike,
    )


def _fail_orphaned(db: Database, table: str) -> int:
    return db.cursor().execute(
        f"UPDATE {table} SET status = 'error', error = 'process exited before the run finished',"
        " finished_at = current_timestamp WHERE status = 'running'"
    ).fetchone()[0]


def _records(cur, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    result = cur.execute(sql, list(params))
    cols = [d[0] for d in result.description]
    return [dict(zip(cols, row)) for row in result.fetchall()]


class DuckInstrumentRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert_many(self, items: Sequence[ProviderInstrument]) -> int:
        if not items:
            return 0
        df = pd.DataFrame(
            [
                {
                    "exchange": p.instrument.exchange,
                    "symbol": p.instrument.symbol,
                    "name": p.instrument.name,
                    "instrument_type": p.instrument.instrument_type,
                    "lot_size": p.instrument.lot_size,
                    "tick_size": p.instrument.tick_size,
                    "expiry": p.instrument.expiry,
                    "strike": p.instrument.strike,
                    "provider": p.provider,
                    "provider_token": p.provider_token,
                }
                for p in items
            ]
        ).drop_duplicates(["exchange", "symbol"], keep="last")
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        with self._db.transaction() as cur:
            cur.register("incoming", df)
            cur.execute(
                """
                INSERT INTO instruments (exchange, symbol, name, instrument_type, lot_size, tick_size, expiry, strike)
                SELECT exchange, symbol, name, instrument_type, lot_size, tick_size, expiry, strike FROM incoming
                ON CONFLICT (exchange, symbol) DO UPDATE SET
                    name = excluded.name, instrument_type = excluded.instrument_type,
                    lot_size = excluded.lot_size, tick_size = excluded.tick_size,
                    expiry = excluded.expiry, strike = excluded.strike, updated_at = now()
                """
            )
            cur.execute(
                """
                INSERT INTO instrument_provider_map (instrument_id, provider, provider_token)
                SELECT i.instrument_id, n.provider, n.provider_token
                FROM incoming n JOIN instruments i USING (exchange, symbol)
                ON CONFLICT (instrument_id, provider) DO UPDATE SET provider_token = excluded.provider_token
                """
            )
            cur.unregister("incoming")
        return len(df)

    def get(self, instrument_id: int) -> Optional[Instrument]:
        row = self._db.cursor().execute(
            f"SELECT {_INSTRUMENT_COLS} FROM instruments WHERE instrument_id = ?", [instrument_id]
        ).fetchone()
        return _row_to_instrument(row) if row else None

    def find(self, exchange: str, symbol: str) -> Optional[Instrument]:
        row = self._db.cursor().execute(
            f"SELECT {_INSTRUMENT_COLS} FROM instruments WHERE exchange = upper(?) AND upper(symbol) = upper(?)",
            [exchange, symbol],
        ).fetchone()
        return _row_to_instrument(row) if row else None

    def search(self, query: str = "", exchange: Optional[str] = None, instrument_type: Optional[str] = None,
               limit: int = 50) -> list[Instrument]:
        clauses, params = [], []
        if query:
            clauses.append("(symbol ILIKE ? OR name ILIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if exchange:
            clauses.append("exchange = ?")
            params.append(exchange.upper())
        if instrument_type:
            clauses.append("instrument_type = ?")
            params.append(instrument_type.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # Exact and prefix matches first, then shortest symbols (RELIANCE-EQ before RELIANCE25NOVFUT).
        order = "ORDER BY (symbol ILIKE ?) DESC, (symbol ILIKE ?) DESC, length(symbol), symbol" if query else "ORDER BY symbol"
        if query:
            params += [query, f"{query}%"]
        rows = self._db.cursor().execute(
            f"SELECT {_INSTRUMENT_COLS} FROM instruments {where} {order} LIMIT ?", params + [limit]
        ).fetchall()
        return [_row_to_instrument(r) for r in rows]

    def provider_token(self, instrument_id: int, provider: str) -> Optional[str]:
        row = self._db.cursor().execute(
            "SELECT provider_token FROM instrument_provider_map WHERE instrument_id = ? AND provider = ?",
            [instrument_id, provider],
        ).fetchone()
        return row[0] if row else None

    def equity_tokens(self, exchange: str, series: Sequence[str], provider: str) -> pd.DataFrame:
        """Equities on `exchange` whose symbol ends in -<series> (e.g. RELIANCE-EQ), with provider tokens.
        Columns: instrument_id, token."""
        pattern = f"-({'|'.join(series)})$"
        return self._db.cursor().execute(
            """
            SELECT i.instrument_id, m.provider_token AS token
            FROM instruments i JOIN instrument_provider_map m USING (instrument_id)
            WHERE i.exchange = ? AND i.instrument_type = 'EQ' AND m.provider = ? AND regexp_matches(i.symbol, ?)
            ORDER BY i.instrument_id
            """,
            [exchange, provider, pattern],
        ).df()


class DuckCandleRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(self, instrument_id: int, interval: Interval, candles: pd.DataFrame, source: str) -> int:
        """Insert new bars, overwrite changed ones (archiving the old value), skip identical ones.

        Returns the number of bars inserted or changed.
        """
        if candles.empty:
            return 0
        df = candles.reset_index()[["ts", *CANDLE_COLUMNS]].copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.drop_duplicates("ts", keep="last")
        key = [instrument_id, interval.value]
        changed = " OR ".join(f"c.{col} IS DISTINCT FROM n.{col}" for col in CANDLE_COLUMNS)

        with self._db.transaction() as cur:
            cur.register("incoming", df)
            cur.execute(
                f"""
                INSERT INTO candle_revisions
                SELECT c.instrument_id, c.timeframe, c.ts, c.open, c.high, c.low, c.close, c.volume,
                       c.source, c.ingested_at, current_timestamp
                FROM candles c JOIN incoming n ON c.ts = n.ts
                WHERE c.instrument_id = ? AND c.timeframe = ? AND ({changed})
                """,
                key,
            )
            written = cur.execute(
                f"""
                INSERT INTO candles (instrument_id, timeframe, ts, open, high, low, close, volume, source, ingested_at)
                SELECT ?, ?, n.ts, n.open, n.high, n.low, n.close, n.volume, ?, current_timestamp
                FROM incoming n
                LEFT JOIN candles c ON c.instrument_id = ? AND c.timeframe = ? AND c.ts = n.ts
                WHERE c.ts IS NULL OR {changed}
                ON CONFLICT (instrument_id, timeframe, ts) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
                    volume = excluded.volume, source = excluded.source, ingested_at = excluded.ingested_at
                """,
                key + [source] + key,
            ).fetchone()[0]
            cur.unregister("incoming")
        return int(written)

    def load(self, instrument_id: int, interval: Interval, start: Optional[datetime] = None,
             end: Optional[datetime] = None) -> pd.DataFrame:
        sql = f"SELECT ts, {', '.join(CANDLE_COLUMNS)} FROM candles WHERE instrument_id = ? AND timeframe = ?"
        params: list[Any] = [instrument_id, interval.value]
        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)
        df = self._db.cursor().execute(sql + " ORDER BY ts", params).df()
        return df.set_index("ts")

    def latest_ts(self, instrument_id: int, interval: Interval) -> Optional[datetime]:
        return self._db.cursor().execute(
            "SELECT max(ts) FROM candles WHERE instrument_id = ? AND timeframe = ?", [instrument_id, interval.value]
        ).fetchone()[0]

    def last_ingested_at(self, instrument_id: int, interval: Interval) -> Optional[datetime]:
        return self._db.cursor().execute(
            "SELECT max(ingested_at) FROM candles WHERE instrument_id = ? AND timeframe = ?",
            [instrument_id, interval.value],
        ).fetchone()[0]

    def coverage(self) -> list[dict[str, Any]]:
        return _records(
            self._db.cursor(),
            """
            SELECT c.instrument_id, i.exchange, i.symbol, i.name, c.timeframe,
                   count(*) AS bars, min(c.ts) AS first_ts, max(c.ts) AS last_ts,
                   max(c.ingested_at) AS last_ingested_at
            FROM candles c JOIN instruments i USING (instrument_id)
            GROUP BY ALL ORDER BY i.symbol, c.timeframe
            """,
        )


class DuckIngestionLog:
    def __init__(self, db: Database):
        self._db = db

    def start(self, provider: str, instrument_id: int, interval: Interval, window) -> str:
        run_id = _new_id()
        self._db.cursor().execute(
            "INSERT INTO ingestion_runs (run_id, provider, instrument_id, timeframe, window_start, window_end,"
            " status, started_at) VALUES (?, ?, ?, ?, ?, ?, 'running', current_timestamp)",
            [run_id, provider, instrument_id, interval.value, window.start, window.end],
        )
        return run_id

    def finish(self, run_id: str, rows: int, status: str, error: Optional[str] = None) -> None:
        self._db.cursor().execute(
            "UPDATE ingestion_runs SET status = ?, rows_written = ?, error = ?, finished_at = current_timestamp"
            " WHERE run_id = ?",
            [status, rows, error, run_id],
        )

    def fail_orphaned(self) -> int:
        """Close runs left 'running' by a process that died. Only valid at startup: DuckDB
        allows one writer, so nothing else can be mid-run when this process opens the file."""
        return _fail_orphaned(self._db, "ingestion_runs")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return _records(
            self._db.cursor(),
            """
            SELECT r.*, i.exchange, i.symbol FROM ingestion_runs r
            LEFT JOIN instruments i USING (instrument_id)
            ORDER BY r.started_at DESC LIMIT ?
            """,
            [limit],
        )


class DuckViewRepository:
    """Read access to SQL views (computations that live in the database)."""

    def __init__(self, db: Database):
        self._db = db

    def daily_stats(self, as_of: Optional[datetime] = None, instrument_id: Optional[int] = None,
                    limit: int = 500) -> list[dict[str, Any]]:
        """Rows of v_daily_stats_v1. With `as_of`, one row per instrument for that date
        (or its last trading day before it), exactly as it would have looked then."""
        clauses, params = [], []
        if instrument_id is not None:
            clauses.append("instrument_id = ?")
            params.append(instrument_id)
        if as_of is not None:
            clauses.append("ts <= ?")
            params.append(as_of)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        if instrument_id is not None and as_of is None:
            sql = f"SELECT * FROM v_daily_stats_v1 {where} ORDER BY ts DESC LIMIT ?"
        else:
            sql = (f"SELECT * FROM v_daily_stats_v1 {where} "
                   "QUALIFY row_number() OVER (PARTITION BY instrument_id ORDER BY ts DESC) = 1 "
                   "ORDER BY symbol LIMIT ?")
        return _records(self._db.cursor(), sql, params + [limit])


class CodeChangedError(RuntimeError):
    """A calculation's source changed but its version did not."""


class DuckCalcRepository:
    def __init__(self, db: Database):
        self._db = db

    def ensure_definition(self, calc_id: str, name: str, version: int, params: dict[str, Any],
                          outputs: Sequence[str], code_hash: str) -> None:
        cur = self._db.cursor()
        row = cur.execute("SELECT code_hash FROM calc_definitions WHERE calc_id = ?", [calc_id]).fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO calc_definitions (calc_id, name, version, params, outputs, code_hash)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [calc_id, name, version, json.dumps(params, sort_keys=True), list(outputs), code_hash],
            )
        elif row[0] != code_hash:
            raise CodeChangedError(
                f"'{name}' v{version} has different code from when it was first stored. "
                f"Bump its version so old and new results are kept apart."
            )

    def start_run(self, calc_id: str, instrument_id: int, interval: Interval,
                  data_watermark: Optional[datetime]) -> str:
        run_id = _new_id()
        self._db.cursor().execute(
            "INSERT INTO calc_runs (run_id, calc_id, instrument_id, timeframe, data_watermark, status, started_at)"
            " VALUES (?, ?, ?, ?, ?, 'running', current_timestamp)",
            [run_id, calc_id, instrument_id, interval.value, data_watermark],
        )
        return run_id

    def fail_orphaned(self) -> int:
        """See DuckIngestionLog.fail_orphaned."""
        return _fail_orphaned(self._db, "calc_runs")

    def finish_run(self, run_id: str, rows: int, status: str, error: Optional[str] = None) -> None:
        self._db.cursor().execute(
            "UPDATE calc_runs SET status = ?, rows_written = ?, error = ?, finished_at = current_timestamp"
            " WHERE run_id = ?",
            [status, rows, error, run_id],
        )

    def write_values(self, run_id: str, calc_id: str, instrument_id: int, interval: Interval,
                     values: pd.DataFrame) -> int:
        long = values.rename_axis("ts").reset_index().melt(id_vars="ts", var_name="output", value_name="value")
        long = long.dropna(subset=["value"])
        if long.empty:
            return 0
        with self._db.transaction() as cur:
            cur.register("incoming", long)
            cur.execute(
                """
                INSERT INTO calc_values (calc_id, instrument_id, timeframe, ts, output, value, run_id)
                SELECT ?, ?, ?, ts, output, value, ? FROM incoming
                ON CONFLICT (calc_id, instrument_id, timeframe, ts, output) DO UPDATE SET
                    value = excluded.value, run_id = excluded.run_id
                """,
                [calc_id, instrument_id, interval.value, run_id],
            )
            cur.unregister("incoming")
        return len(long)

    def load_values(self, calc_id: str, instrument_id: int, interval: Interval,
                    start: Optional[datetime] = None, end: Optional[datetime] = None) -> pd.DataFrame:
        sql = "SELECT ts, output, value FROM calc_values WHERE calc_id = ? AND instrument_id = ? AND timeframe = ?"
        params: list[Any] = [calc_id, instrument_id, interval.value]
        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)
        long = self._db.cursor().execute(sql, params).df()
        if long.empty:
            return pd.DataFrame(index=pd.DatetimeIndex([], name="ts"))
        return long.pivot(index="ts", columns="output", values="value").sort_index()

    def definitions(self) -> list[dict[str, Any]]:
        rows = _records(
            self._db.cursor(),
            "SELECT calc_id, name, version, params, outputs, code_hash, created_at"
            " FROM calc_definitions ORDER BY name, version, created_at",
        )
        for r in rows:
            r["params"] = json.loads(r["params"])
        return rows


MANUAL = "manual"  # watchlists.source of the lists you make yourself
MAX_NAME = 60


class DuckWatchlistRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(self, watchlist_id: str, name: str, description: Optional[str] = None,
               source: Optional[str] = None) -> None:
        self._db.cursor().execute(
            """
            INSERT INTO watchlists (watchlist_id, name, description, source) VALUES (?, ?, ?, ?)
            ON CONFLICT (watchlist_id) DO UPDATE SET
                name = excluded.name, description = excluded.description, source = excluded.source,
                updated_at = now()
            """,
            [watchlist_id, name, description, source],
        )

    def set_members(self, watchlist_id: str, instrument_ids: Sequence[int]) -> dict[str, int]:
        """Make `instrument_ids` the current members, closing out anyone who left."""
        wanted = pd.DataFrame({"instrument_id": pd.Series(sorted(set(instrument_ids)), dtype="int64")})
        with self._db.transaction() as cur:
            cur.register("wanted", wanted)
            removed = cur.execute(
                """
                UPDATE watchlist_members SET removed_at = now()
                WHERE watchlist_id = ? AND removed_at IS NULL
                  AND instrument_id NOT IN (SELECT instrument_id FROM wanted)
                """,
                [watchlist_id],
            ).fetchone()[0]
            added = cur.execute(
                """
                INSERT INTO watchlist_members (watchlist_id, instrument_id, added_at)
                SELECT ?, w.instrument_id, now() FROM wanted w
                WHERE w.instrument_id NOT IN (
                    SELECT instrument_id FROM watchlist_members WHERE watchlist_id = ? AND removed_at IS NULL)
                """,
                [watchlist_id, watchlist_id],
            ).fetchone()[0]
            cur.execute("UPDATE watchlists SET updated_at = now() WHERE watchlist_id = ?", [watchlist_id])
            cur.unregister("wanted")
        return {"added": int(added), "removed": int(removed), "members": len(wanted)}

    def member_ids(self, watchlist_id: str, as_of: Optional[datetime] = None) -> list[int]:
        """Current members, or the members at a past moment when `as_of` is given."""
        if as_of is None:
            sql = "SELECT instrument_id FROM watchlist_members WHERE watchlist_id = ? AND removed_at IS NULL"
            params: list[Any] = [watchlist_id]
        else:
            sql = ("SELECT instrument_id FROM watchlist_members WHERE watchlist_id = ? AND added_at <= ?"
                   " AND (removed_at IS NULL OR removed_at > ?)")
            params = [watchlist_id, as_of, as_of]
        return [r[0] for r in self._db.cursor().execute(sql + " ORDER BY instrument_id", params).fetchall()]

    def all(self) -> list[dict[str, Any]]:
        return _records(
            self._db.cursor(),
            """
            SELECT w.*, count(m.instrument_id) AS members
            FROM watchlists w
            LEFT JOIN watchlist_members m ON m.watchlist_id = w.watchlist_id AND m.removed_at IS NULL
            GROUP BY ALL ORDER BY w.name
            """,
        )

    # Your own lists (source = MANUAL): created and edited by hand, never touched by the NSE sync.

    def manual_lists(self) -> list[dict[str, Any]]:
        """Your lists by name, each with its current members in the order they were added."""
        rows = _records(
            self._db.cursor(),
            """
            SELECT w.watchlist_id, w.name,
                   list(m.instrument_id ORDER BY m.added_at, m.instrument_id)
                       FILTER (WHERE m.instrument_id IS NOT NULL) AS member_ids
            FROM watchlists w
            LEFT JOIN watchlist_members m ON m.watchlist_id = w.watchlist_id AND m.removed_at IS NULL
            WHERE w.source = ?
            GROUP BY w.watchlist_id, w.name ORDER BY lower(w.name), w.watchlist_id
            """,
            [MANUAL],
        )
        return [{**r, "member_ids": r["member_ids"] or []} for r in rows]

    def create_manual(self, name: str) -> dict[str, Any]:
        name = self._check_name(name)
        watchlist_id = _new_id()
        self._db.cursor().execute(
            "INSERT INTO watchlists (watchlist_id, name, source) VALUES (?, ?, ?)", [watchlist_id, name, MANUAL])
        return {"watchlist_id": watchlist_id, "name": name, "member_ids": []}

    def rename_manual(self, watchlist_id: str, name: str) -> None:
        self._require_manual(watchlist_id)
        name = self._check_name(name, exclude=watchlist_id)
        self._db.cursor().execute(
            "UPDATE watchlists SET name = ?, updated_at = now() WHERE watchlist_id = ?", [name, watchlist_id])

    def delete_manual(self, watchlist_id: str) -> None:
        self._require_manual(watchlist_id)
        with self._db.transaction() as cur:
            cur.execute("DELETE FROM watchlist_members WHERE watchlist_id = ?", [watchlist_id])
            cur.execute("DELETE FROM watchlists WHERE watchlist_id = ?", [watchlist_id])

    def add_member(self, watchlist_id: str, instrument_id: int) -> bool:
        """Add a stock to the end of one of your lists. False (no change) if it's already in it."""
        self._require_manual(watchlist_id)
        with self._db.transaction() as cur:
            if cur.execute("SELECT 1 FROM instruments WHERE instrument_id = ?", [instrument_id]).fetchone() is None:
                raise KeyError(f"instrument {instrument_id} not found")
            added = cur.execute(
                """
                INSERT INTO watchlist_members (watchlist_id, instrument_id, added_at)
                SELECT ?, ?, now() WHERE NOT EXISTS (
                    SELECT 1 FROM watchlist_members
                    WHERE watchlist_id = ? AND instrument_id = ? AND removed_at IS NULL)
                """,
                [watchlist_id, instrument_id, watchlist_id, instrument_id],
            ).fetchone()[0]
            cur.execute("UPDATE watchlists SET updated_at = now() WHERE watchlist_id = ?", [watchlist_id])
        return added > 0

    def remove_member(self, watchlist_id: str, instrument_id: int) -> bool:
        """Take a stock out of one of your lists. False (no change) if it wasn't in it."""
        self._require_manual(watchlist_id)
        with self._db.transaction() as cur:
            removed = cur.execute(
                "UPDATE watchlist_members SET removed_at = now()"
                " WHERE watchlist_id = ? AND instrument_id = ? AND removed_at IS NULL",
                [watchlist_id, instrument_id],
            ).fetchone()[0]
            cur.execute("UPDATE watchlists SET updated_at = now() WHERE watchlist_id = ?", [watchlist_id])
        return removed > 0

    def _require_manual(self, watchlist_id: str) -> None:
        row = self._db.cursor().execute(
            "SELECT 1 FROM watchlists WHERE watchlist_id = ? AND source = ?", [watchlist_id, MANUAL]).fetchone()
        if row is None:
            raise KeyError(f"watchlist {watchlist_id} not found")

    def _check_name(self, name: str, exclude: Optional[str] = None) -> str:
        """Trimmed name; ValueError if empty, too long or already used by another of your lists."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Enter a name")
        if len(name) > MAX_NAME:
            raise ValueError(f"Keep the name to {MAX_NAME} characters or fewer")
        taken = self._db.cursor().execute(
            "SELECT 1 FROM watchlists WHERE source = ? AND lower(name) = lower(?) AND watchlist_id IS DISTINCT FROM ?",
            [MANUAL, name, exclude],
        ).fetchone()
        if taken:
            raise ValueError("You already have a list with that name")
        return name

    def set_tags(self, key: str, values: dict[int, str], source: str) -> int:
        if not values:
            return 0
        df = pd.DataFrame({"instrument_id": list(values), "value": list(values.values())})
        with self._db.transaction() as cur:
            cur.register("incoming", df)
            cur.execute(
                """
                INSERT INTO instrument_tags (instrument_id, key, value, source, updated_at)
                SELECT instrument_id, ?, value, ?, now() FROM incoming
                ON CONFLICT (instrument_id, key) DO UPDATE SET
                    value = excluded.value, source = excluded.source, updated_at = excluded.updated_at
                """,
                [key, source],
            )
            cur.unregister("incoming")
        return len(df)


class DuckMarketRepository:
    """Cross-sectional reads for dashboards and scans, backed by daily_signals_v1."""

    def __init__(self, db: Database):
        self._db = db

    def snapshot(self, as_of: datetime, instrument_ids: Sequence[int]) -> pd.DataFrame:
        """One row per instrument: its signals on its last trading day on or before `as_of`."""
        if not instrument_ids:
            return pd.DataFrame()
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        df = cur.execute(
            """
            SELECT s.*, t.value AS industry
            FROM daily_signals_v1(CAST(? AS TIMESTAMP)) s
            JOIN universe u USING (instrument_id)
            LEFT JOIN instrument_tags t ON t.instrument_id = s.instrument_id AND t.key = 'industry'
            """,
            [as_of],
        ).df()
        cur.unregister("universe")
        return df

    def recent_closes(self, instrument_ids: Sequence[int], as_of: datetime, bars: int = 60) -> dict[int, list[dict]]:
        """Last `bars` daily closes per instrument, for sparklines."""
        if not instrument_ids:
            return {}
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        df = cur.execute(
            """
            SELECT instrument_id, ts, close FROM (
                SELECT c.instrument_id, c.ts, c.close,
                       row_number() OVER (PARTITION BY c.instrument_id ORDER BY c.ts DESC) AS n
                FROM candles c JOIN universe u USING (instrument_id)
                WHERE c.timeframe = '1d' AND c.ts <= ? AND c.ts > CAST(? AS TIMESTAMP) - INTERVAL 200 DAY
            ) WHERE n <= ? ORDER BY instrument_id, ts
            """,
            [as_of, as_of, bars],
        ).df()
        cur.unregister("universe")
        return {
            int(iid): [{"ts": ts.isoformat(), "close": float(c)} for ts, c in zip(g["ts"], g["close"])]
            for iid, g in df.groupby("instrument_id")
        }

    def latest_quotes(self, instrument_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
        """Last stored daily bar per instrument: its `ts`, `close` and `pct_change` (fraction, vs the
        bar before; None with only one bar or a zero/missing previous close). No entry = no daily bars."""
        if not instrument_ids:
            return {}
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        rows = _records(
            cur,
            """
            SELECT instrument_id, ts,
                   CASE WHEN isnan(close) THEN NULL ELSE close END AS close,
                   CASE WHEN isnan(close / nullif(prev_close, 0)) THEN NULL
                        ELSE close / nullif(prev_close, 0) - 1 END AS pct_change
            FROM (
                SELECT c.instrument_id, c.ts, c.close,
                       lag(c.close) OVER (PARTITION BY c.instrument_id ORDER BY c.ts) AS prev_close
                FROM candles c JOIN universe u USING (instrument_id)
                WHERE c.timeframe = '1d'
            )
            QUALIFY row_number() OVER (PARTITION BY instrument_id ORDER BY ts DESC) = 1
            """,
        )
        cur.unregister("universe")
        return {int(r.pop("instrument_id")): r for r in rows}

    def daily_bars(self, instrument_ids: Sequence[int], as_of: datetime, bars: int) -> pd.DataFrame:
        """Last `bars` daily candles per instrument up to `as_of`, long format, oldest first."""
        cols = ["instrument_id", "ts", *CANDLE_COLUMNS]
        if not instrument_ids:
            return pd.DataFrame(columns=cols)
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        df = cur.execute(
            f"""
            SELECT {', '.join(cols)} FROM candles c JOIN universe u USING (instrument_id)
            WHERE c.timeframe = '1d' AND c.ts <= ?
            QUALIFY row_number() OVER (PARTITION BY c.instrument_id ORDER BY c.ts DESC) <= ?
            ORDER BY instrument_id, ts
            """,
            [as_of, bars],
        ).df()
        cur.unregister("universe")
        return df

    def recent_sessions(self, instrument_ids: Sequence[int], as_of: datetime, count: int) -> list[pd.Timestamp]:
        """The last `count` trading sessions on or before `as_of` (newest first): days on which any of
        `instrument_ids` has a daily bar."""
        if not instrument_ids or count < 1:
            return []
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        rows = cur.execute(
            """
            SELECT DISTINCT ts FROM candles c JOIN universe u USING (instrument_id)
            WHERE c.timeframe = '1d' AND c.ts <= ? ORDER BY ts DESC LIMIT ?
            """,
            [as_of, count],
        ).fetchall()
        cur.unregister("universe")
        return [pd.Timestamp(r[0]) for r in rows]

    def daily_prices(self, instrument_ids: Sequence[int], start: datetime, end: datetime) -> pd.DataFrame:
        """Daily opens and closes per instrument with `start <= ts <= end`, long format."""
        cols = ["instrument_id", "ts", "open", "close"]
        if not instrument_ids:
            return pd.DataFrame(columns=cols)
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("universe", ids)
        df = cur.execute(
            f"""
            SELECT {', '.join(cols)} FROM candles c JOIN universe u USING (instrument_id)
            WHERE c.timeframe = '1d' AND c.ts BETWEEN ? AND ?
            ORDER BY instrument_id, ts
            """,
            [start, end],
        ).df()
        cur.unregister("universe")
        return df

    def tracked_daily_ids(self) -> list[int]:
        """Instruments that already have daily candles stored."""
        return [r[0] for r in self._db.cursor().execute(
            "SELECT DISTINCT instrument_id FROM candles WHERE timeframe = '1d' ORDER BY 1").fetchall()]


class DuckSavedScanRepository:
    """Named custom scans. `definition` is stored as JSON text and returned as a dict."""

    def __init__(self, db: Database):
        self._db = db

    def all(self) -> list[dict[str, Any]]:
        rows = _records(self._db.cursor(), "SELECT * FROM saved_scans ORDER BY name")
        return [{**r, "definition": json.loads(r["definition"])} for r in rows]

    def save(self, name: str, definition: dict[str, Any]) -> str:
        """Create, or replace the scan with the same name. Returns its id."""
        with self._db.transaction() as cur:
            row = cur.execute("SELECT scan_id FROM saved_scans WHERE name = ?", [name]).fetchone()
            if row:
                cur.execute("UPDATE saved_scans SET definition = ?, updated_at = now() WHERE scan_id = ?",
                            [json.dumps(definition), row[0]])
                return row[0]
            scan_id = _new_id()
            cur.execute("INSERT INTO saved_scans (scan_id, name, definition) VALUES (?, ?, ?)",
                        [scan_id, name, json.dumps(definition)])
            return scan_id

    def delete(self, scan_id: str) -> bool:
        return self._db.cursor().execute(
            "DELETE FROM saved_scans WHERE scan_id = ?", [scan_id]).fetchone()[0] > 0


UNCLASSIFIED = "Unclassified"


class DuckBreadthRepository:
    """Sector breadth (share of stocks above their SMA) computed in SQL over any date range.

    The SMA averages the last N bars, or all bars a stock has when it has fewer than N (the same
    "use what's available" rule as custom scans). Stocks count on the days they have a bar.
    Universe membership is point-in-time from watchlist_members; days before the watchlist was
    first synced use its current members. Equities only.
    """

    def __init__(self, db: Database):
        self._db = db

    def latest_session(self, as_of: datetime) -> Optional[datetime]:
        row = self._db.cursor().execute(
            "SELECT max(ts) FROM candles WHERE timeframe = '1d' AND ts <= ?", [as_of]).fetchone()
        return row[0] if row else None

    def compute(self, universe: str, periods: Sequence[int], start: datetime, end: datetime) -> pd.DataFrame:
        """Columns: ts, universe, industry, ma_period, stocks, above."""
        sql, params = self._sql(universe, periods, start, end)
        return self._db.cursor().execute(sql, params).df()

    def store(self, universe: str, periods: Sequence[int], start: datetime, end: datetime) -> int:
        """Compute and upsert into sector_breadth; returns rows written."""
        sql, params = self._sql(universe, periods, start, end)
        with self._db.transaction() as cur:
            cur.execute(f"CREATE TEMP TABLE _breadth AS {sql}", params)
            n = cur.execute("SELECT count(*) FROM _breadth").fetchone()[0]
            cur.execute(
                "INSERT OR REPLACE INTO sector_breadth (ts, universe, industry, ma_period, stocks, above)"
                " SELECT ts, universe, industry, ma_period, stocks, above FROM _breadth")
            cur.execute("DROP TABLE _breadth")
        return int(n)

    def load(self, universe: str, ts: datetime, periods: Sequence[int]) -> pd.DataFrame:
        if not periods:
            return pd.DataFrame(columns=["ts", "universe", "industry", "ma_period", "stocks", "above"])
        marks = ", ".join("?" * len(periods))
        return self._db.cursor().execute(
            f"SELECT ts, universe, industry, ma_period, stocks, above FROM sector_breadth"
            f" WHERE universe = ? AND ts = ? AND ma_period IN ({marks})",
            [universe, ts, *periods],
        ).df()

    def load_range(self, universe: str, period: int, start: datetime, end: datetime) -> pd.DataFrame:
        """Stored rows of one MA period for every day in [start, end]."""
        return self._db.cursor().execute(
            "SELECT ts, universe, industry, ma_period, stocks, above FROM sector_breadth"
            " WHERE universe = ? AND ma_period = ? AND ts BETWEEN ? AND ? ORDER BY ts, industry",
            [universe, period, start, end],
        ).df()

    @staticmethod
    def _sql(universe: str, periods: Sequence[int], start: datetime, end: datetime) -> tuple[str, list[Any]]:
        periods = sorted({int(p) for p in periods if int(p) > 0})
        if not periods:
            raise ValueError("at least one positive MA period is required")
        # Enough calendar days before `start` to fill the longest window (~1.45 calendar days per bar).
        lookback = 2 * max(periods) + 20
        smas = ",\n".join(
            f"avg(close) OVER (PARTITION BY instrument_id ORDER BY ts ROWS BETWEEN {p - 1} PRECEDING"
            f" AND CURRENT ROW) AS sma_{p}" for p in periods)
        counts = "\nUNION ALL\n".join(
            f"SELECT ts, ? AS universe, industry, {p} AS ma_period, count(*) AS stocks,"
            f" count(*) FILTER (WHERE close > sma_{p}) AS above FROM scoped GROUP BY ts, industry"
            for p in periods)
        if universe == "all":
            membership, member_params = "TRUE", []
        else:
            membership = """EXISTS (
                SELECT 1 FROM watchlist_members m
                WHERE m.watchlist_id = ? AND m.instrument_id = s.instrument_id AND (
                    (s.ts >= first_sync.d AND CAST(m.added_at AS DATE) <= s.ts
                        AND (m.removed_at IS NULL OR CAST(m.removed_at AS DATE) > s.ts))
                    OR (s.ts < first_sync.d AND m.removed_at IS NULL)))"""
            member_params = [universe]
        sql = f"""
            WITH first_sync AS (
                SELECT coalesce(min(CAST(added_at AS DATE)), DATE '1900-01-01') AS d
                FROM watchlist_members WHERE watchlist_id = ?
            ),
            bars AS (
                SELECT c.instrument_id, c.ts, c.close
                FROM candles c JOIN instruments i USING (instrument_id)
                WHERE c.timeframe = '1d' AND i.instrument_type = 'EQ'
                  AND c.ts <= ? AND c.ts > CAST(? AS TIMESTAMP) - INTERVAL {lookback} DAY
            ),
            sma AS (SELECT instrument_id, ts, close, {smas} FROM bars),
            scoped AS (
                SELECT s.*, coalesce(t.value, '{UNCLASSIFIED}') AS industry
                FROM sma s CROSS JOIN first_sync
                LEFT JOIN instrument_tags t ON t.instrument_id = s.instrument_id AND t.key = 'industry'
                WHERE s.ts >= ? AND {membership}
            )
            {counts}
        """
        params: list[Any] = [universe, end, start, start, *member_params, *([universe] * len(periods))]
        return sql, params


class DuckDataQualityRepository:
    """Inputs for the data-quality checks (engine/data_quality.py), the issues they find, and run state."""

    def __init__(self, db: Database):
        self._db = db

    # --- state ---------------------------------------------------------------------------

    def get_state(self, key: str) -> Optional[str]:
        row = self._db.cursor().execute("SELECT value FROM dq_state WHERE key = ?", [key]).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self._db.cursor().execute("INSERT OR REPLACE INTO dq_state VALUES (?, ?, current_timestamp)", [key, value])

    # --- check inputs --------------------------------------------------------------------

    def max_ingested_at(self) -> Optional[datetime]:
        return self._db.cursor().execute("SELECT max(ingested_at) FROM candles WHERE timeframe = '1d'").fetchone()[0]

    def changed_since(self, watermark: Optional[datetime], instrument_ids: Optional[Sequence[int]] = None) -> pd.DataFrame:
        """instrument_id, from_ts: instruments with daily bars ingested after `watermark` and the
        earliest such bar (every instrument from its first bar when `watermark` is None)."""
        where, params = ["timeframe = '1d'"], []
        if watermark is not None:
            where.append("ingested_at > ?")
            params.append(watermark)
        if instrument_ids is not None:
            where.append(f"instrument_id IN ({','.join('?' * len(instrument_ids))})" if instrument_ids else "FALSE")
            params.extend(instrument_ids)
        return self._db.cursor().execute(
            f"SELECT instrument_id, min(ts) AS from_ts FROM candles WHERE {' AND '.join(where)} GROUP BY 1",
            params).df()

    def bars_from(self, changed: pd.DataFrame) -> pd.DataFrame:
        """Daily bars of each changed instrument from the bar before its `from_ts` (context for the gap
        and jump checks) to its latest, with instrument_type."""
        names = ["instrument_id", "ts", "open", "high", "low", "close", "volume", "instrument_type"]
        if changed.empty:
            return pd.DataFrame(columns=names)
        cur = self._db.cursor()
        cur.register("changed", changed)
        df = cur.execute(
            """
            WITH ctx AS (
                SELECT ch.instrument_id, coalesce(max(p.ts), min(ch.from_ts)) AS start_ts
                FROM changed ch
                LEFT JOIN candles p ON p.instrument_id = ch.instrument_id AND p.timeframe = '1d' AND p.ts < ch.from_ts
                GROUP BY ch.instrument_id
            )
            SELECT c.instrument_id, c.ts, c.open, c.high, c.low, c.close, c.volume, i.instrument_type
            FROM candles c JOIN ctx USING (instrument_id) JOIN instruments i USING (instrument_id)
            WHERE c.timeframe = '1d' AND c.ts >= ctx.start_ts
            ORDER BY c.instrument_id, c.ts
            """
        ).df()
        cur.unregister("changed")
        return df

    def instruments_per_day(self) -> pd.Series:
        """Distinct stocks (not indices) with a daily bar, per day: the input for the market calendar."""
        df = self._db.cursor().execute(
            """SELECT c.ts, count(DISTINCT c.instrument_id) AS n FROM candles c JOIN instruments i USING (instrument_id)
               WHERE c.timeframe = '1d' AND i.instrument_type IS DISTINCT FROM 'INDEX' GROUP BY 1 ORDER BY 1"""
        ).df()
        return df.set_index("ts")["n"] if not df.empty else pd.Series(dtype="int64")

    def bar_summary(self, instrument_ids: Sequence[int]) -> pd.DataFrame:
        """Per instrument (index): first_ts, last_ts and number of daily bars."""
        cols = ["first_ts", "last_ts", "bars"]
        if not instrument_ids:
            return pd.DataFrame(columns=cols)
        ids = pd.DataFrame({"instrument_id": pd.Series(list(instrument_ids), dtype="int64")})
        cur = self._db.cursor()
        cur.register("ids", ids)
        df = cur.execute(
            """SELECT instrument_id, min(ts) AS first_ts, max(ts) AS last_ts, count(*) AS bars
               FROM candles JOIN ids USING (instrument_id) WHERE timeframe = '1d' GROUP BY 1"""
        ).df()
        cur.unregister("ids")
        return df.set_index("instrument_id")[cols]

    def failed_downloads(self) -> pd.DataFrame:
        """Daily downloads whose latest attempt failed: instrument_id, start_ts/end_ts (the window), detail."""
        return self._db.cursor().execute(
            """
            SELECT instrument_id, window_start AS start_ts, window_end AS end_ts, error AS detail, status
            FROM ingestion_runs WHERE timeframe = '1d' AND status <> 'running'
            QUALIFY row_number() OVER (PARTITION BY instrument_id ORDER BY started_at DESC) = 1
            """
        ).df().query("status == 'error'").drop(columns="status")

    # --- issues --------------------------------------------------------------------------

    def record(self, check: str, found: pd.DataFrame, now: datetime, status: str = "open",
               note: Optional[str] = None) -> pd.DataFrame:
        """Upsert `found` (instrument_id, start_ts, end_ts, detail) as issues of `check`; returns them with
        issue_id and `new`. A resolved issue seen again reopens; an accepted one stays accepted."""
        if found.empty:
            return found.assign(issue_id=pd.Series(dtype=str), new=pd.Series(dtype=bool))
        df = found.copy()
        start = pd.to_datetime(df["start_ts"]).dt.strftime("%Y-%m-%d").fillna("-")
        df["issue_id"] = check + ":" + df["instrument_id"].astype(str) + ":" + start
        df = df.drop_duplicates("issue_id", keep="last")
        cur = self._db.cursor()
        cur.register("found", df)
        known = {r[0] for r in cur.execute("SELECT issue_id FROM dq_issues JOIN found USING (issue_id)").fetchall()}
        cur.execute(
            """
            INSERT INTO dq_issues (issue_id, check_name, instrument_id, start_ts, end_ts, detail, status, note,
                                   first_seen, last_seen, seen_count, resolved_at)
            SELECT issue_id, ?, instrument_id, start_ts, end_ts, detail, ?, ?, ?, ?, 1, NULL FROM found
            ON CONFLICT (issue_id) DO UPDATE SET
                end_ts = excluded.end_ts, detail = excluded.detail, last_seen = excluded.last_seen,
                seen_count = dq_issues.seen_count + 1,
                status = CASE WHEN dq_issues.status = 'accepted' THEN 'accepted' ELSE excluded.status END,
                resolved_at = NULL
            """,
            [check, status, note, now, now],
        )
        cur.unregister("found")
        df["new"] = ~df["issue_id"].isin(known)
        return df

    def resolve_missing(self, check: str, seen_ids: Sequence[str], now: datetime,
                        scope: Optional[pd.DataFrame] = None, statuses: Sequence[str] = ("open",)) -> int:
        """Mark open issues of `check` resolved when a re-check no longer finds them. `scope`
        (instrument_id, from_ts) limits this to the instruments and dates just re-checked; None = all."""
        cur = self._db.cursor()
        cur.register("seen", pd.DataFrame({"issue_id": pd.Series(list(seen_ids), dtype=str)}))
        where = (f"check_name = ? AND status IN ({','.join('?' * len(statuses))})"
                 " AND issue_id NOT IN (SELECT issue_id FROM seen)")
        if scope is not None:
            cur.register("scope", scope)
            where += """ AND EXISTS (SELECT 1 FROM scope s WHERE s.instrument_id = dq_issues.instrument_id
                                     AND (dq_issues.end_ts IS NULL OR dq_issues.end_ts >= s.from_ts))"""
        resolved = cur.execute(
            f"UPDATE dq_issues SET status = 'resolved', resolved_at = ? WHERE {where} RETURNING issue_id",
            [now, check, *statuses]).fetchall()
        cur.unregister("seen")
        if scope is not None:
            cur.unregister("scope")
        return len(resolved)

    def issues(self, status: Optional[str] = "open", check: Optional[str] = None,
               instrument_id: Optional[int] = None, limit: int = 1000) -> list[dict[str, Any]]:
        """Issues with exchange and symbol, by check then symbol; `None` filters are ignored."""
        where, params = [], []
        for col, val in (("q.status", status), ("q.check_name", check), ("q.instrument_id", instrument_id)):
            if val is not None:
                where.append(f"{col} = ?")
                params.append(val)
        df = self._db.cursor().execute(
            f"""SELECT q.*, i.exchange, i.symbol FROM dq_issues q LEFT JOIN instruments i USING (instrument_id)
                {'WHERE ' + ' AND '.join(where) if where else ''}
                ORDER BY q.check_name, i.symbol, q.start_ts LIMIT ?""",
            [*params, limit]).df()
        return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]

    def counts(self) -> list[dict[str, Any]]:
        """Issues per check and status."""
        return [dict(zip(("check_name", "status", "issues"), r)) for r in self._db.cursor().execute(
            "SELECT check_name, status, count(*) FROM dq_issues GROUP BY 1, 2 ORDER BY 1, 2").fetchall()]

    def accept(self, issue_id: str, note: str) -> bool:
        """Mark an issue as known and fine, so it stops being reported as open."""
        return bool(self._db.cursor().execute(
            "UPDATE dq_issues SET status = 'accepted', note = ? WHERE issue_id = ? RETURNING issue_id",
            [note, issue_id]).fetchall())
