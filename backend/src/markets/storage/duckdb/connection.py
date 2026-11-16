from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

import duckdb


class Database:
    """Owns the single DuckDB connection for this process.

    DuckDB allows one read-write process per file, so the API server and CLI write
    commands cannot run against the same file at the same time. Repositories take a
    fresh cursor per operation, which is safe across threads within the process.
    """

    def __init__(self, path: Union[str, Path], read_only: bool = False):
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self.path = target
        self._conn = duckdb.connect(target, read_only=read_only)

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self._conn.cursor()

    @contextmanager
    def transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        cur = self.cursor()
        cur.begin()
        try:
            yield cur
            cur.commit()
        except Exception:
            cur.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()
