"""Big-movers service (pipelines/movers.py): scoring, stored lists, outcomes, the nightly message, the API."""

import json
import shutil
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import Instrument, Interval, ProviderInstrument
from markets.engine.movers import BIG_MOVE, FEATURE_COLUMNS, build_features
from markets.pipelines import movers as movers_mod
from markets.pipelines.movers import MODEL_VERSION, MoverModel, MoverService, message
from markets.storage.duckdb import DuckMoverRepository

STOCKS = ("RELIANCE-EQ", "TCS-EQ", "INFY-EQ", "HDFCBANK-EQ")
PROBS = {"RELIANCE-EQ": 0.5, "TCS-EQ": 0.25, "INFY-EQ": 0.1, "HDFCBANK-EQ": 0.05, "SAMPLE-BE": 0.9}
LATEST = date(2025, 3, 10)  # Monday


class FakeModel:
    version = "test_v1"
    train_end = date(2024, 12, 31)

    def __init__(self, probs):
        self.probs = probs  # instrument_id -> probability
        self.seen = []

    def predict(self, features):
        self.seen.append(features)
        return np.array([self.probs[i] for i in features.instrument_id])


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, text):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append(text)


def iid(c, sym):
    return c.instruments.find("NSE", sym).instrument_id


@pytest.fixture
def loaded(container):
    """The 4 fake stocks + a BE-series stock in the universe, daily bars 2024-01-01 .. LATEST."""
    container.instruments.upsert_many([ProviderInstrument(Instrument("NSE", "SAMPLE-BE", "SAMPLE"), "fake", "99")])
    container.watchlist_sync.sync_all()
    for sym in (*STOCKS, "Nifty 50"):
        container.ingestion.ingest(iid(container, sym), Interval.D1, datetime(2024, 1, 1), datetime(2025, 3, 10))
    be = container.candles.load(iid(container, "RELIANCE-EQ"), Interval.D1) * 0.5
    container.candles.upsert(iid(container, "SAMPLE-BE"), Interval.D1, be, "test")
    members = container.watchlists.member_ids("nifty500")
    container.watchlists.set_members("nifty500", [*members, iid(container, "SAMPLE-BE")])
    return container


def service(c, notifier=None, clock=datetime(2025, 3, 10, 18, 0), cutoff=0.2):
    model = FakeModel({iid(c, s): p for s, p in PROBS.items()})
    return MoverService(DuckMoverRepository(c.db), c.market, c.watchlists, c.instruments, notifier, cutoff,
                        model=model, universe="nifty500", clock=lambda: clock)


def drop_bar(c, sym, day):
    """A stock without a bar that day (not traded, or not downloaded)."""
    c.db.cursor().execute("DELETE FROM candles WHERE instrument_id = ? AND timeframe = '1d' AND CAST(ts AS DATE) = ?",
                          [iid(c, sym), day])


def bar(c, sym, day):
    df = c.candles.load(iid(c, sym), Interval.D1, start=datetime.combine(day, datetime.min.time()),
                        end=datetime.combine(day, datetime.max.time()))
    return df.iloc[0]


def test_score_latest_session(loaded):
    svc = service(loaded)
    r = svc.score()
    assert r["as_of"] == "2025-03-10" and not r["skipped"]
    assert r["universe"] == 5 and r["with_bar"] == 5
    assert r["stocks"] == 4 and r["listed"] == 2  # BE stock scored for nothing: never listed
    assert r["warnings"] == ["no India VIX bar on 2025-03-10"]  # the fake universe has no VIX
    feats = svc.model.seen[-1]
    assert set(feats.ts) == {pd.Timestamp("2025-03-11")}  # the next weekday
    stored = loaded.db.cursor().execute("SELECT count(*), min(as_of) FROM mover_scores").fetchone()
    assert stored == (4, date(2025, 3, 10))


def test_be_stock_still_feeds_market_features(loaded):
    i = iid(loaded, "SAMPLE-BE")
    day = (datetime.combine(LATEST, datetime.min.time()), datetime.combine(LATEST, datetime.max.time()))
    jump = loaded.candles.load(i, Interval.D1, *day)
    jump["close"] = jump["high"] = jump["open"] * 1.1  # a big move on the BE stock only
    loaded.candles.upsert(i, Interval.D1, jump, "test")
    svc = service(loaded)
    svc.score()
    big = [abs(b.close / b.open - 1) >= BIG_MOVE for b in (bar(loaded, s, LATEST) for s in STOCKS)]
    assert svc.model.seen[-1]["mkt_big_share"].unique() == pytest.approx([(sum(big) + 1) / 5])


def test_score_is_kept_unless_rebuilt(loaded):
    svc = service(loaded, notifier=FakeNotifier())
    svc.nightly()
    assert svc.score()["skipped"]
    assert not svc.score(rebuild=True)["skipped"]
    assert svc.repo.run("test_v1", LATEST)["notified"] == "sent"  # re-scoring keeps the message state


@pytest.mark.parametrize("as_of, clock, error", [
    (date(2024, 12, 31), datetime(2025, 3, 10, 18), "training period"),
    (date(2025, 3, 8), datetime(2025, 3, 10, 18), "not a session"),  # Saturday
    (None, datetime(2025, 3, 10, 11), "aren't final"),
])
def test_score_refuses(loaded, as_of, clock, error):
    with pytest.raises(ValueError, match=error):
        service(loaded, clock=clock).score(as_of)


def test_score_needs_universe_members(loaded):
    svc = service(loaded)
    svc.universe = "benchmarks_missing"
    with pytest.raises(ValueError, match="no members"):
        svc.score()


def test_partial_download_is_flagged(loaded):
    for sym in ("TCS-EQ", "INFY-EQ"):
        drop_bar(loaded, sym, LATEST)
    r = service(loaded).score()
    assert "only 3 of 5 stocks have a bar on 2025-03-10" in r["warnings"]
    assert r["stocks"] == 2  # the two without today's bar aren't scored


def test_picks_latest_has_no_outcome(loaded):
    svc = service(loaded)
    svc.score()
    p = svc.picks()
    assert p["scored"] and p["as_of"] == "2025-03-10" and p["next_session"] is None
    assert p["assumed_next_session"] == "2025-03-11"
    assert [r["symbol"] for r in p["rows"]] == ["RELIANCE-EQ", "TCS-EQ"]
    rel = p["rows"][0]
    today, before = bar(loaded, "RELIANCE-EQ", LATEST), bar(loaded, "RELIANCE-EQ", date(2025, 3, 7))
    assert rel["close"] == pytest.approx(today.close)
    assert rel["change"] == pytest.approx(today.close / before.close - 1)
    assert rel["move"] is None and rel["hit"] is None
    assert p["top_probability"] == 0.5 and p["listed"] == 2 and p["hits"] == 0


def test_picks_past_day_shows_next_session(loaded):
    svc = service(loaded)
    svc.score(date(2025, 3, 7))  # Friday; the next session is Monday 10 Mar
    p = svc.picks(date(2025, 3, 7), cutoff=0.1)
    assert p["next_session"] == "2025-03-10" and p["cutoff"] == 0.1 and p["default_cutoff"] == 0.2
    assert [r["symbol"] for r in p["rows"]] == ["RELIANCE-EQ", "TCS-EQ", "INFY-EQ"]
    for r in p["rows"]:
        b = bar(loaded, r["symbol"], LATEST)
        assert r["move"] == pytest.approx(b.close / b.open - 1)
        assert r["hit"] == (abs(b.close / b.open - 1) >= BIG_MOVE)
    assert p["listed_with_bar"] == 3 and p["hits"] == sum(r["hit"] for r in p["rows"])
    assert p["all_with_bar"] == 4


def test_picks_next_session_without_a_bar(loaded):
    svc = service(loaded)
    svc.score(date(2025, 3, 7))
    drop_bar(loaded, "TCS-EQ", LATEST)
    p = svc.picks(date(2025, 3, 7))
    tcs = next(r for r in p["rows"] if r["symbol"] == "TCS-EQ")
    assert tcs["move"] is None and tcs["hit"] is None
    assert p["listed"] == 2 and p["listed_with_bar"] == 1


def test_picks_cutoffs_and_missing_days(loaded):
    svc = service(loaded)
    assert svc.picks() == {**svc.picks(), "as_of": None, "scored": False, "rows": []}  # nothing scored yet
    svc.score()
    assert len(svc.picks(cutoff=0.3)["rows"]) == 1
    empty = svc.picks(cutoff=0.6)
    assert empty["scored"] and empty["rows"] == [] and empty["top_probability"] == 0.5
    assert not svc.picks(date(2025, 3, 5))["scored"]


def test_days_count_lists_and_hits(loaded):
    svc = service(loaded)
    svc.score(date(2025, 3, 7))
    svc.score()
    days = svc.days(cutoff=0.1)
    assert [d["as_of"] for d in days] == ["2025-03-10", "2025-03-07"]
    assert days[0]["next_session"] is None and days[0]["listed"] == 3 and days[0]["hits"] == 0
    past = svc.picks(date(2025, 3, 7), cutoff=0.1)
    assert (days[1]["listed"], days[1]["with_bar"], days[1]["hits"]) == (3, 3, past["hits"])


def test_backfill_scores_sessions_after_training_only(loaded):
    note = FakeNotifier()
    svc = service(loaded, notifier=note)
    r = svc.backfill(date(2024, 12, 20))
    sessions = [d for d in loaded.market.recent_sessions([iid(loaded, "Nifty 50")], datetime(2025, 3, 10, 23), 500)
                if date(2025, 1, 1) <= d.date() <= LATEST]
    assert r == {"model_version": "test_v1", "sessions": len(sessions), "scored": len(sessions)}
    assert svc.backfill(date(2024, 12, 20))["scored"] == 0  # all kept
    assert note.sent == []


def test_nightly_sends_once(loaded):
    note = FakeNotifier()
    svc = service(loaded, notifier=note)
    first = svc.nightly()
    assert first["notified"] == "sent"
    assert note.sent == ["Big movers for the next session (after the close of Mon 10 Mar), p ≥ 0.20: 2 stocks\n"
                         "RELIANCE 50%, TCS 25%\nNote: no India VIX bar on 2025-03-10"]
    assert svc.nightly()["notified"] is None and len(note.sent) == 1


def test_nightly_telegram_off_and_failed(loaded):
    assert service(loaded).nightly()["notified"] == "off"
    loaded.db.cursor().execute("DELETE FROM mover_runs")
    failing = service(loaded, notifier=FakeNotifier(fail=True))
    assert failing.nightly()["notified"] == "failed"
    assert failing.repo.run("test_v1", LATEST)["notify_error"] == "telegram down"
    failing.notifier = FakeNotifier()
    assert failing.nightly()["notified"] == "sent"  # a failed message is tried again on the next run


def test_message_long_and_empty_lists():
    rows = [{"symbol": f"S{i}-EQ", "probability": 0.3} for i in range(45)]
    text = message({"as_of": "2025-03-10", "cutoff": 0.2, "rows": rows}, [])
    assert text.startswith("Big movers for the next session (after the close of Mon 10 Mar), p ≥ 0.20: 45 stocks")
    assert text.endswith("S39 30% and 5 more")
    empty = message({"as_of": "2025-03-10", "cutoff": 0.3, "rows": [], "top_probability": 0.27}, [])
    assert empty == "Big movers after the close of Mon 10 Mar: no stocks at p ≥ 0.30 (highest 27%)"


def test_daily_update_runs_the_step_and_reports_errors(loaded):
    svc = service(loaded, notifier=FakeNotifier())
    loaded.daily_update.movers = svc
    report = loaded.daily_update.repair_now()
    assert report["movers"]["notified"] == "sent"
    assert "big movers: no India VIX bar on 2025-03-10" in report["errors"]
    svc.universe = "missing"
    loaded.db.cursor().execute("DELETE FROM mover_runs")
    report = loaded.daily_update.repair_now()
    assert report["movers"] is None and any(e.startswith("big movers: watchlist missing") for e in report["errors"])


def test_api(loaded):
    loaded.movers = service(loaded)
    with TestClient(create_app(loaded)) as client:
        assert client.get("/api/movers").json()["as_of"] is None
        job = client.post("/api/jobs/movers", params={"since": "2025-03-07"}).json()
        assert job == {"model_version": "test_v1", "sessions": 2, "scored": 2}
        latest = client.get("/api/movers").json()
        assert latest["as_of"] == "2025-03-10" and len(latest["rows"]) == 2
        past = client.get("/api/movers", params={"as_of": "2025-03-07", "cutoff": 0.3}).json()
        assert past["next_session"] == "2025-03-10" and [r["symbol"] for r in past["rows"]] == ["RELIANCE-EQ"]
        assert [d["as_of"] for d in client.get("/api/movers/days").json()] == ["2025-03-10", "2025-03-07"]
        assert client.get("/api/movers", params={"cutoff": 1.5}).status_code == 422
        assert client.post("/api/jobs/movers", params={"rebuild": True}).json()["skipped"] is False
        assert client.post("/api/jobs/movers", params={"since": "2024-06-01"}).status_code == 200
        loaded.movers._clock = lambda: datetime(2025, 3, 10, 11)
        assert client.post("/api/jobs/movers", params={"rebuild": True}).status_code == 422


# --- the stored model ---------------------------------------------------------------------------

def test_stored_model_scores_features(loaded):
    model = MoverModel(MODEL_VERSION)
    assert model.version == MODEL_VERSION and model.train_end == date(2024, 12, 31)
    bars = loaded.market.daily_bars([iid(loaded, s) for s in (*STOCKS, "Nifty 50")], datetime(2025, 3, 10, 23), 400)
    nifty = bars.instrument_id == iid(loaded, "Nifty 50")
    feats = build_features(bars[~nifty], bars[nifty], bars.iloc[:0], pd.Timestamp("2025-03-11"))
    p = model.predict(feats)
    assert len(p) == 4 and ((p > 0) & (p < 1)).all()


def test_model_with_other_features_is_refused(tmp_path):
    for suffix in (".json", ".meta.json"):
        shutil.copy(movers_mod.MODELS_DIR / f"{MODEL_VERSION}{suffix}", tmp_path / f"{MODEL_VERSION}{suffix}")
    meta_path = tmp_path / f"{MODEL_VERSION}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert tuple(meta["features"]) == FEATURE_COLUMNS
    meta_path.write_text(json.dumps({**meta, "features_version": meta["features_version"] + 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="train a new model version"):
        MoverModel(MODEL_VERSION, tmp_path)
