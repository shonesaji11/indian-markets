from __future__ import annotations

from pathlib import Path

from markets.storage.duckdb.connection import Database

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def migrate(db: Database) -> list[str]:
    """Apply any migrations/NNN_*.sql files that have not run yet, in order."""
    cur = db.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version VARCHAR PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp)"
    )
    applied = {row[0] for row in cur.execute("SELECT version FROM schema_migrations").fetchall()}
    cur.close()

    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        with db.transaction() as tx:
            tx.execute(path.read_text(encoding="utf-8"))
            tx.execute("INSERT INTO schema_migrations (version) VALUES (?)", [version])
        newly_applied.append(version)
    return newly_applied
