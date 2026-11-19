import logging
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import LiveTick
from markets.notifiers import NotifyError
from markets.notifiers.telegram import TelegramNotifier
from markets.pipelines.alerts import AlertFiredError, AlertService, indian, is_hit, message
from markets.pipelines.live import LiveService
from markets.providers.fake import FakeLiveFeed
from markets.storage.duckdb import DuckAlertRepository

MORNING = datetime(2026, 11, 19, 10, 0)  # a Thursday


class Clock:
    def __init__(self, now=MORNING):
        self.now = now

    def __call__(self):
        return self.now


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, text):
        if self.fail:
            raise NotifyError("Telegram answered 500: down")
        self.sent.append(text)


@pytest.fixture
def setup(container, reliance_id):
    clock, feed, notifier = Clock(), FakeLiveFeed(), FakeNotifier()
    live = LiveService(feed, container.instruments, "fake", lambda: [], clock)
    service = AlertService(DuckAlertRepository(container.db), container.instruments, live, notifier, clock)
    return service, live, feed, notifier, clock


def quote(ltp, ts=MORNING, prev_close=2898.6):
    return {"ts": ts, "ltp": ltp, "open": None, "high": None, "low": None, "prev_close": prev_close, "volume": None}


# ---- rules ------------------------------------------------------------------------


def test_a_level_counts_when_reached_or_jumped_over():
    assert is_hit("above", 2980, 2980) and is_hit("above", 2980, 2995.5) and not is_hit("above", 2980, 2979.95)
    assert is_hit("below", 2880, 2880) and is_hit("below", 2880, 2850) and not is_hit("below", 2880, 2880.05)


@pytest.mark.parametrize("value, text", [
    (0.5, "0.50"), (999, "999.00"), (2980, "2,980.00"), (83021.75, "83,021.75"), (140000.5, "1,40,000.50"),
    (12345678.9, "1,23,45,678.90"), (-2500, "-2,500.00"), (999.999, "1,000.00"),
])
def test_prices_use_indian_digit_grouping_like_the_app(value, text):
    assert indian(value) == text


def test_telegram_message_reads_as_agreed():
    alert = {"symbol": "RELIANCE-EQ", "instrument_type": "EQ", "direction": "above", "price": 2980.0,
             "created_at": datetime(2026, 11, 8, 18, 0), "note": "breakout from base"}
    assert message(alert, 2981.2, datetime(2026, 11, 19, 10, 42, 15), 2898.6) == (
        "🔔 RELIANCE above ₹2,980.00\nLTP ₹2,981.20 at 10:42:15 · +2.85% today\nAlert set 8 Nov · \"breakout from base\"")
    index = {**alert, "symbol": "Nifty 50", "instrument_type": "INDEX", "direction": "below", "price": 24000.0,
             "note": None}
    assert message(index, 23990.5, datetime(2026, 11, 19, 11, 0), None) == (
        "🔔 Nifty 50 below 24,000.00\nLTP 23,990.50 at 11:00:00\nAlert set 8 Nov")


@pytest.mark.parametrize("direction, price, note, error", [
    ("sideways", 100, None, "direction"), ("above", 0, None, "above 0"), ("above", -5, None, "above 0"),
    ("above", float("nan"), None, "above 0"), ("above", float("inf"), None, "above 0"),
    ("above", 100, "x" * 201, "longer than 200"),
])
def test_bad_alerts_are_refused(setup, reliance_id, direction, price, note, error):
    service = setup[0]
    with pytest.raises(ValueError, match=error):
        service.create(reliance_id, direction, price, note)


def test_unknown_stock_is_refused_and_notes_are_trimmed(setup, reliance_id):
    service = setup[0]
    with pytest.raises(KeyError):
        service.create(99999, "above", 100)
    assert service.create(reliance_id, "above", 100, "   ")["note"] is None
    assert service.create(reliance_id, "above", 100, "  base  ")["note"] == "base"


# ---- firing -------------------------------------------------------------------------


def test_fires_once_with_one_message(setup, reliance_id):
    service, live, feed, notifier, clock = setup
    alert = service.create(reliance_id, "above", 2980, "breakout")
    service.on_quote(reliance_id, quote(2979.0))
    service.process()
    assert service.list()[0]["triggered_at"] is None and notifier.sent == []
    service.on_quote(reliance_id, quote(2981.2, MORNING + timedelta(seconds=1)))
    service.on_quote(reliance_id, quote(2990.0, MORNING + timedelta(seconds=2)))  # still above: no second firing
    service.process()
    fired = service.list()[0]
    assert fired["alert_id"] == alert["alert_id"]
    assert (fired["triggered_at"], fired["triggered_price"], fired["notified"]) == (
        MORNING + timedelta(seconds=1), 2981.2, "sent")
    assert len(notifier.sent) == 1 and notifier.sent[0].startswith("🔔 RELIANCE above ₹2,980.00")
    assert service.instrument_ids() == []  # nothing left to stream for alerts


@pytest.mark.parametrize("ts", [
    datetime(2026, 11, 18, 16, 8),  # yesterday's last price, replayed on subscribing
    datetime(2026, 11, 19, 9, 10),  # pre-open
    datetime(2026, 11, 19, 15, 30),  # after the session
])
def test_only_todays_session_prices_count(setup, reliance_id, ts):
    service, live, feed, notifier, clock = setup
    service.create(reliance_id, "above", 2980)
    clock.now = datetime(2026, 11, 19, 15, 45)
    service.on_quote(reliance_id, quote(3100.0, ts))
    service.process()
    assert service.list()[0]["triggered_at"] is None


def test_several_alerts_on_one_stock_fire_on_their_own(setup, reliance_id):
    service, *_ = setup
    service.create(reliance_id, "above", 2980)
    low = service.create(reliance_id, "below", 2880)
    service.on_quote(reliance_id, quote(2985.0))
    service.process()
    active = [a for a in service.list() if a["triggered_at"] is None]
    assert [a["alert_id"] for a in active] == [low["alert_id"]]
    assert service.instrument_ids() == [reliance_id]  # still streamed for the remaining alert


def test_an_alert_already_met_fires_on_creation(setup, container, reliance_id):
    service, live, feed, notifier, clock = setup
    live.watch([reliance_id])
    live.step()  # connected, RELIANCE subscribed
    token = container.instruments.provider_token(reliance_id, "fake")
    feed.emit(LiveTick("NSE", token, MORNING, 2951.4, prev_close=2898.6))
    service.create(reliance_id, "above", 2900)  # already above
    service.process()
    assert service.list()[0]["triggered_price"] == 2951.4
    # and the stream itself checks alerts on every quote
    service.create(reliance_id, "below", 2940)
    feed.emit(LiveTick("NSE", token, MORNING + timedelta(seconds=5), 2939.0, prev_close=2898.6))
    service.process()
    assert all(a["triggered_at"] for a in service.list())


def test_deleted_or_edited_before_processing_does_not_fire(setup, reliance_id):
    service, live, feed, notifier, clock = setup
    alert = service.create(reliance_id, "above", 2980)
    service.on_quote(reliance_id, quote(2990.0))
    service.delete(alert["alert_id"])  # gone before the service thread got to it
    service.process()
    assert service.list() == [] and notifier.sent == []


def test_fired_alerts_cant_be_edited(setup, reliance_id):
    service, *_ = setup
    alert = service.create(reliance_id, "above", 2980)
    edited = service.update(alert["alert_id"], "below", 2900, "moved")
    assert (edited["direction"], edited["price"], edited["note"]) == ("below", 2900.0, "moved")
    service.on_quote(reliance_id, quote(2890.0))
    service.process()
    with pytest.raises(AlertFiredError):
        service.update(alert["alert_id"], "above", 3000)
    with pytest.raises(KeyError):
        service.update("nope", "above", 3000)


def test_message_failures_are_recorded_and_no_telegram_means_off(container, reliance_id):
    clock = Clock()
    live = LiveService(FakeLiveFeed(), container.instruments, "fake", lambda: [], clock)
    repo = DuckAlertRepository(container.db)
    failing = AlertService(repo, container.instruments, live, FakeNotifier(fail=True), clock)
    failing.create(reliance_id, "above", 2980)
    failing.on_quote(reliance_id, quote(2990.0))
    failing.process()
    row = repo.all()[0]
    assert row["notified"] == "failed" and "500" in row["notify_error"] and row["triggered_at"] is not None

    silent = AlertService(repo, container.instruments, live, None, clock)
    assert silent.telegram is False
    silent.create(reliance_id, "below", 2800)
    silent.on_quote(reliance_id, quote(2790.0))
    silent.process()
    assert [r["notified"] for r in repo.all() if r["direction"] == "below"] == ["off"]


def test_messages_left_unsent_by_a_stop_go_out_on_start(setup, container, reliance_id):
    service, live, feed, notifier, clock = setup
    repo = DuckAlertRepository(container.db)
    alert_id = repo.create(reliance_id, "above", 2980.0, None, MORNING)
    repo.mark_triggered(alert_id, MORNING, 2985.0)  # fired, then the app stopped before messaging
    service.start()
    service.stop()
    assert repo.get(alert_id)["notified"] == "sent" and len(notifier.sent) == 1


def test_feed_lost_and_back_messages(setup, reliance_id):
    service, live, feed, notifier, clock = setup
    service.create(reliance_id, "above", 2980)
    live.step()  # connected
    feed.drop()
    clock.now += timedelta(seconds=29)
    service.process()
    assert notifier.sent == []  # brief drops don't message
    clock.now += timedelta(seconds=1)
    service.process()
    service.process()
    assert len(notifier.sent) == 1 and notifier.sent[0].startswith("⚠️ Live feed lost at 10:00:00")
    clock.now += timedelta(seconds=5)
    live.step()  # reconnects
    service.process()
    service.process()
    assert len(notifier.sent) == 2 and notifier.sent[1].startswith("✅ Live feed back at 10:00:35")


# ---- Telegram -----------------------------------------------------------------------


def _telegram(handler, sleeps):
    return TelegramNotifier("123456:SECRET-token", "42", retry_seconds=(5, 15, 40), sleep=sleeps.append,
                            client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_telegram_sends_to_the_chat(caplog):
    seen = []

    def ok(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    with caplog.at_level(logging.INFO, logger="httpx"):
        _telegram(ok, []).send("hello")
    assert seen[0].url.path == "/bot123456:SECRET-token/sendMessage"
    assert seen[0].read() == b'{"chat_id":"42","text":"hello"}'
    assert "SECRET" not in caplog.text and "bot***" in caplog.text  # httpx logs the URL: the token is masked


def test_telegram_retries_then_gives_up_without_leaking_the_token():
    sleeps = []
    with pytest.raises(NotifyError) as err:
        _telegram(lambda r: httpx.Response(502, json={"ok": False, "description": "Bad Gateway"}), sleeps).send("x")
    assert sleeps == [5, 15, 40] and "SECRET" not in str(err.value)

    sleeps = []
    with pytest.raises(NotifyError, match="401"):  # wrong token: retrying won't help
        _telegram(lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}), sleeps).send("x")
    assert sleeps == []

    def unreachable(request):
        raise httpx.ConnectError("no route to api.telegram.org/bot123456:SECRET-token", request=request)

    with pytest.raises(NotifyError) as err:
        _telegram(unreachable, []).send("x")
    assert "SECRET" not in str(err.value)


# ---- API ----------------------------------------------------------------------------


def test_alerts_endpoints(container, reliance_id, setup):
    container.alerts = setup[0]  # a fixed clock (Thursday 10:00) instead of the real one
    with TestClient(create_app(container)) as client:
        made = client.post("/api/alerts", json={"instrument_id": reliance_id, "direction": "above", "price": 2980,
                                                "note": "breakout"})
        assert made.status_code == 200 and made.json()["symbol"] == "RELIANCE-EQ"
        alert_id = made.json()["alert_id"]
        assert client.post("/api/alerts", json={"instrument_id": reliance_id, "direction": "up",
                                                "price": 1}).status_code == 422
        assert client.post("/api/alerts", json={"instrument_id": 99999, "direction": "above",
                                                "price": 1}).status_code == 404

        body = client.get("/api/alerts").json()
        assert body["telegram"] is True and set(body["live"]) >= {"connected", "session_open"}  # fixture's notifier
        assert [a["alert_id"] for a in body["alerts"]] == [alert_id]

        edited = client.patch(f"/api/alerts/{alert_id}", json={"direction": "below", "price": 2900, "note": None})
        assert edited.json()["direction"] == "below"
        assert client.patch("/api/alerts/nope", json={"direction": "below", "price": 1}).status_code == 404

        container.alerts.on_quote(reliance_id, quote(2890.0))
        container.alerts.process()
        assert client.get("/api/alerts").json()["alerts"][0]["triggered_price"] == 2890.0
        assert client.patch(f"/api/alerts/{alert_id}", json={"direction": "above", "price": 1}).status_code == 409

        assert client.delete(f"/api/alerts/{alert_id}").json() == {"deleted": alert_id}
        assert client.delete(f"/api/alerts/{alert_id}").status_code == 404
