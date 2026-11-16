from datetime import datetime

import pytest

from markets.core.models import Interval
from markets.storage.duckdb.repositories import CodeChangedError


def test_find_is_case_insensitive(container):
    assert container.instruments.find("nse", "nifty 50").symbol == "Nifty 50"


def test_ingest_is_idempotent_and_incremental(container, reliance_id):
    first = container.ingestion.ingest(reliance_id, Interval.D1, datetime(2024, 1, 1), datetime(2024, 6, 30))
    assert first.status == "ok" and first.rows > 100

    again = container.ingestion.ingest(reliance_id, Interval.D1, datetime(2024, 1, 1), datetime(2024, 6, 30))
    assert again.rows == 0  # identical bars are skipped

    more = container.ingestion.ingest(reliance_id, Interval.D1, end=datetime(2024, 7, 31))
    assert more.rows > 15  # continues from the last stored bar

    stored = container.candles.load(reliance_id, Interval.D1)
    assert stored.index.is_monotonic_increasing and not stored.index.duplicated().any()


def test_orphaned_runs_are_closed_on_startup(container, reliance_id):
    from markets.core.models import DateRange

    run_id = container.ingestion_log.start("fake", reliance_id, Interval.D1,
                                           DateRange(datetime(2024, 1, 1), datetime(2024, 2, 1)))
    assert container.ingestion_log.fail_orphaned() == 1
    run = next(r for r in container.ingestion_log.recent() if r["run_id"] == run_id)
    assert run["status"] == "error" and "exited" in run["error"]


def test_changed_bars_are_archived(container, reliance_id):
    container.ingestion.ingest(reliance_id, Interval.D1, datetime(2024, 1, 1), datetime(2024, 1, 31))
    bars = container.candles.load(reliance_id, Interval.D1).head(2)
    bars["close"] += 1
    assert container.candles.upsert(reliance_id, Interval.D1, bars, source="manual") == 2

    revisions = container.db.cursor().execute("SELECT count(*) FROM candle_revisions").fetchone()[0]
    assert revisions == 2


def test_calc_results_are_versioned(container, reliance_id):
    container.ingestion.ingest(reliance_id, Interval.D1, datetime(2023, 1, 1), datetime(2024, 1, 1))
    a = container.calc_service.compute("sma", reliance_id, Interval.D1, {"period": 20})
    b = container.calc_service.compute("sma", reliance_id, Interval.D1, {"period": 50})
    assert a.calc_id != b.calc_id

    values = container.calcs.load_values(a.calc_id, reliance_id, Interval.D1)
    candles = container.candles.load(reliance_id, Interval.D1)
    expected = candles["close"].rolling(20).mean().dropna()
    assert (values["sma"] - expected).abs().max() < 1e-9

    names = {(d["name"], d["params"]["period"]) for d in container.calcs.definitions()}
    assert names == {("sma", 20), ("sma", 50)}


def test_changed_code_without_version_bump_is_refused(container):
    container.calcs.ensure_definition("abc", "sma", 1, {"period": 20}, ["sma"], code_hash="old")
    with pytest.raises(CodeChangedError):
        container.calcs.ensure_definition("abc", "sma", 1, {"period": 20}, ["sma"], code_hash="new")


def test_daily_stats_view_is_point_in_time(container, reliance_id):
    container.ingestion.ingest(reliance_id, Interval.D1, datetime(2023, 1, 1), datetime(2024, 12, 31))
    as_of = datetime(2024, 3, 15, 23, 59)
    row = container.views.daily_stats(as_of=as_of)[0]
    assert row["ts"] <= as_of

    candles = container.candles.load(reliance_id, Interval.D1, end=as_of)
    assert row["high_52w"] == pytest.approx(candles["high"].tail(252).max())
