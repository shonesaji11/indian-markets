"""Charts download what's missing on open: POST /api/candles/{id}/refresh."""

from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.api.routers.data import _plain_reason
from markets.core.models import CANDLE_COLUMNS, Interval
from markets.pipelines.ingest import DEFAULT_HISTORY
from markets.providers import ProviderError
from markets.providers.angelone import _INTERVALS


def test_first_download_of_every_interval_is_one_angel_request():
    assert set(DEFAULT_HISTORY) == set(Interval)  # no interval without a default
    for interval, (_, max_days) in _INTERVALS.items():
        if interval != Interval.D1:
            assert DEFAULT_HISTORY[interval] <= timedelta(days=max_days), interval


def _runs(container, instrument_id):
    return [r for r in container.ingestion_log.recent() if r["instrument_id"] == instrument_id]


def test_refresh_downloads_default_history_then_only_whats_missing(container, reliance_id):
    with TestClient(create_app(container)) as client:
        first = client.post(f"/api/candles/{reliance_id}/refresh", params={"interval": "5m"})
        assert first.status_code == 200 and first.json()["rows"] > 1000
        run = _runs(container, reliance_id)[0]
        assert run["window_end"] - run["window_start"] == DEFAULT_HISTORY[Interval.M5]

        last = container.candles.latest_ts(reliance_id, Interval.M5)
        again = client.post(f"/api/candles/{reliance_id}/refresh", params={"interval": "5m"})
        assert again.status_code == 200
        assert _runs(container, reliance_id)[0]["window_start"] == last  # from the last stored bar, not 100 days

        bars = client.get(f"/api/candles/{reliance_id}", params={"interval": "5m"}).json()["candles"]
        assert len(bars) == len({b["ts"] for b in bars})  # no duplicates from the overlap


def test_nothing_new_is_not_an_error(container, reliance_id, monkeypatch):
    empty = pd.DataFrame(columns=list(CANDLE_COLUMNS), index=pd.DatetimeIndex([], name="ts"), dtype=float)
    monkeypatch.setattr(container.provider, "fetch_candles", lambda *a: empty)  # e.g. a Sunday
    with TestClient(create_app(container)) as client:
        resp = client.post(f"/api/candles/{reliance_id}/refresh", params={"interval": "1m"})
        assert resp.status_code == 200 and resp.json() == {"rows": 0}


@pytest.mark.parametrize("error, reason", [
    ("getCandleData for 2885 failed: Access denied because of exceeding access rate", "download limit was hit"),
    ("Angel One login failed: Invalid totp", "login failed"),
    ("Angel One credentials missing: set MARKETS_ANGEL_* in backend/.env", "login failed"),
    ("getCandleData for 2885 failed: AB1004: Something Went Wrong", "didn't return the bars"),
])
def test_failed_downloads_say_why_in_plain_words(container, reliance_id, monkeypatch, error, reason):
    def fail(*args):
        raise ProviderError(error)

    monkeypatch.setattr(container.provider, "fetch_candles", fail)
    with TestClient(create_app(container)) as client:
        resp = client.post(f"/api/candles/{reliance_id}/refresh", params={"interval": "15m"})
        assert resp.status_code == 502 and reason in resp.json()["detail"]
    assert container.candles.latest_ts(reliance_id, Interval.M15) is None  # nothing half-stored
    assert reason in _plain_reason(error)


def test_unknown_instrument_is_404(container):
    with TestClient(create_app(container)) as client:
        resp = client.post("/api/candles/99999/refresh", params={"interval": "5m"})
        assert resp.status_code == 404 and "99999" in resp.json()["detail"]
