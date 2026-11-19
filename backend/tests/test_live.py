import struct
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from markets.api.app import create_app
from markets.core.models import LiveTick
from markets.pipelines.live import LiveService
from markets.providers import ProviderError
from markets.providers.angelone import AngelOneProvider
from markets.providers.angelone_stream import parse_quote_packet
from markets.providers.fake import FakeLiveFeed

# Thursday 19 Nov 2026, IST
MORNING = datetime(2026, 11, 19, 10, 0)


def _packet(exchange_type=1, token="2885", ts=datetime(2026, 11, 19, 10, 0, 5), ltp=137560, quote=True,
            ohlc=(136190, 138250, 134970, 136300), volume=14486599):
    """A SmartStream binary packet (prices in paise), as Angel One sends it."""
    epoch_ms = int((ts - datetime(1970, 1, 1, 5, 30)).total_seconds() * 1000)  # naive IST -> epoch
    data = struct.pack("<BB25sqqq", 2 if quote else 1, exchange_type, token.encode(), 7, epoch_ms, ltp)
    if quote:
        data += struct.pack("<qqqdd", 100, 136800, volume, 1.0, 2.0) + struct.pack("<qqqq", *ohlc)
    return data


class Clock:
    def __init__(self, now=MORNING):
        self.now = now

    def __call__(self):
        return self.now


# ---- packet parsing ---------------------------------------------------------------


def test_quote_packet_parses_to_rupees_and_ist():
    tick = parse_quote_packet(_packet())
    assert len(_packet()) == 123
    assert tick == LiveTick(exchange="NSE", token="2885", ts=datetime(2026, 11, 19, 10, 0, 5), ltp=1375.6,
                            open=1361.9, high=1382.5, low=1349.7, prev_close=1363.0, volume=14486599.0)


def test_ltp_packet_has_only_the_price():
    tick = parse_quote_packet(_packet(exchange_type=3, token="99919000", ltp=8302175, quote=False))
    assert len(_packet(quote=False)) == 51
    assert (tick.exchange, tick.token, tick.ltp) == ("BSE", "99919000", 83021.75)
    assert tick.open is tick.prev_close is tick.volume is None


def test_zero_prices_mean_none_and_bad_packets_are_dropped():
    no_trade_yet = parse_quote_packet(_packet(ohlc=(0, 0, 0, 136300), volume=0))
    assert (no_trade_yet.open, no_trade_yet.high, no_trade_yet.low) == (None, None, None)
    assert no_trade_yet.prev_close == 1363.0 and no_trade_yet.volume == 0
    assert parse_quote_packet(_packet(ltp=0)) is None  # nothing traded: no price to show
    assert parse_quote_packet(_packet(exchange_type=99)) is None  # unknown exchange
    assert parse_quote_packet(_packet(token="")) is None
    assert parse_quote_packet(_packet()[:50]) is None  # truncated


# ---- provider login ---------------------------------------------------------------


class _StubSession:
    access_token, feed_token = "jwt", "feed"


def test_provider_logs_in_again_on_a_new_day():
    provider = AngelOneProvider("key", "C1", None, None)  # no PIN/TOTP: any real login attempt fails
    provider._api, provider._login_day = _StubSession(), date.today()
    assert provider.stream_auth() == {"Authorization": "Bearer jwt", "x-api-key": "key", "x-client-code": "C1",
                                      "x-feed-token": "feed"}
    provider._login_day = date.today() - timedelta(days=1)  # yesterday's session ended at midnight
    with pytest.raises(ProviderError, match="credentials missing"):
        provider.stream_auth()


# ---- LiveService ------------------------------------------------------------------


@pytest.fixture
def ids(container):
    container.watchlist_sync.sync_all()
    find = container.instruments.find
    return {s: find("NSE", s).instrument_id for s in ("Nifty 50", "RELIANCE-EQ", "TCS-EQ", "INFY-EQ")}


@pytest.fixture
def live(container, ids):
    """Benchmarks (Nifty 50) plus a list of yours holding RELIANCE stream from the start."""
    mine = container.watchlists.create_manual("Mine")
    container.watchlists.add_member(mine["watchlist_id"], ids["RELIANCE-EQ"])
    feed, clock = FakeLiveFeed(), Clock()
    base = lambda: [*container.watchlists.member_ids("benchmarks"),  # noqa: E731
                    *(i for wl in container.watchlists.manual_lists() for i in wl["member_ids"])]
    service = LiveService(feed, container.instruments, "fake", base, clock)
    return service, feed, clock


def _ref(container, instrument_id):
    return "NSE", container.instruments.provider_token(instrument_id, "fake")


def test_streams_benchmarks_and_your_lists_during_feed_hours(container, ids, live):
    service, feed, clock = live
    for quiet in (datetime(2026, 11, 19, 8, 59), datetime(2026, 11, 19, 16, 15), datetime(2026, 11, 21, 11, 0)):
        clock.now = quiet  # before pre-open, after the closing session, a Saturday
        service.step()
        assert not feed.connected
    clock.now = MORNING
    service.step()
    assert feed.connected
    assert sorted(feed.subscribed) == sorted([_ref(container, ids["Nifty 50"]), _ref(container, ids["RELIANCE-EQ"])])
    assert service.status() == {"connected": True, "session_open": True, "today": "2026-11-19", "last_tick": None,
                                "lost_at": None}


def test_watched_stocks_stream_once_and_unknown_ones_are_skipped(container, ids, live):
    service, feed, clock = live
    service.watch([ids["TCS-EQ"], ids["RELIANCE-EQ"], 99999])  # RELIANCE already streams; 99999 doesn't exist
    service.step()
    service.watch([ids["TCS-EQ"]])
    service.step()
    assert sorted(feed.subscribed) == sorted(_ref(container, ids[s]) for s in ("Nifty 50", "RELIANCE-EQ", "TCS-EQ"))


def test_stocks_asked_for_before_the_feed_opens_stream_once_it_does(container, ids, live):
    service, feed, clock = live
    clock.now = datetime(2026, 11, 18, 11, 0)
    service.watch([ids["INFY-EQ"]])  # yesterday's request: forgotten
    clock.now = datetime(2026, 11, 19, 8, 30)
    service.watch([ids["TCS-EQ"]])  # a page open before pre-open
    service.step()
    clock.now = datetime(2026, 11, 19, 9, 0)
    service.step()
    assert _ref(container, ids["TCS-EQ"]) in feed.subscribed
    assert _ref(container, ids["INFY-EQ"]) not in feed.subscribed


def test_ticks_become_quotes(container, ids, live):
    service, feed, clock = live
    service.step()
    exchange, token = _ref(container, ids["RELIANCE-EQ"])
    feed.emit(LiveTick(exchange, token, datetime(2026, 11, 19, 9, 59, 58), 2950.0, 2900.0, 2960.0, 2890.0, 2898.6, 1e6))
    feed.emit(LiveTick(exchange, token, datetime(2026, 11, 19, 10, 0, 1), 2951.4, 2900.0, 2960.0, 2890.0, 2898.6, 2e6))
    feed.emit(LiveTick("NSE", "nope", datetime(2026, 11, 19, 10, 0, 2), 1.0))  # not ours: ignored
    assert service.quotes([ids["RELIANCE-EQ"], ids["TCS-EQ"]]) == [{
        "instrument_id": ids["RELIANCE-EQ"], "ts": datetime(2026, 11, 19, 10, 0, 1), "ltp": 2951.4, "open": 2900.0,
        "high": 2960.0, "low": 2890.0, "prev_close": 2898.6, "volume": 2e6}]
    assert service.status()["last_tick"] == datetime(2026, 11, 19, 10, 0, 1)


def test_a_dropped_feed_reconnects_and_resubscribes_everything(container, ids, live):
    service, feed, clock = live
    service.watch([ids["TCS-EQ"]])
    service.step()
    clock.now = MORNING + timedelta(minutes=5)
    feed.drop()
    status = service.status()
    assert not status["connected"] and status["lost_at"] == clock.now
    clock.now += timedelta(seconds=4)
    service.step()  # waits 5 s before retrying
    assert not feed.connected
    clock.now += timedelta(seconds=1)
    service.step()
    assert feed.connected and service.status()["lost_at"] is None
    assert len(feed.subscribed) == 3  # Nifty 50, RELIANCE and the watched TCS again


def test_failed_connects_back_off_and_show_as_lost(live):
    service, feed, clock = live
    feed.fail_connect = True
    service.step()
    assert service.status()["lost_at"] == MORNING
    for wait in (4, 1):  # first retry after 5 s
        clock.now += timedelta(seconds=wait)
        service.step()
    retried_at = clock.now
    clock.now += timedelta(seconds=9)
    feed.fail_connect = False
    service.step()  # second retry waits 10 s
    assert not feed.connected
    clock.now = retried_at + timedelta(seconds=10)
    service.step()
    assert feed.connected and service.status()["lost_at"] is None


def test_never_streams_more_than_the_feed_allows(container, ids, live):
    service, feed, clock = live
    feed.max_subscriptions = 2
    service.watch([ids["TCS-EQ"], ids["INFY-EQ"]])
    service.step()
    service.step()
    assert len(feed.subscribed) == 2


def test_closes_after_hours_keeps_quotes_and_forgets_extras_next_day(container, ids, live):
    service, feed, clock = live
    service.watch([ids["TCS-EQ"]])
    service.step()
    exchange, token = _ref(container, ids["TCS-EQ"])
    feed.emit(LiveTick(exchange, token, datetime(2026, 11, 19, 16, 8), 4100.0))
    clock.now = datetime(2026, 11, 19, 16, 15)
    service.step()
    assert not feed.connected
    assert service.quotes([ids["TCS-EQ"]])[0]["ltp"] == 4100.0  # the last price stays for the evening
    assert service.status()["session_open"] is False
    clock.now = datetime(2026, 11, 20, 9, 0)  # Friday: only benchmarks and your lists again
    service.step()
    assert len(feed.subscribed) == 2


def test_live_quotes_endpoint(container, ids, live):
    service, feed, clock = live
    container.live = service
    with TestClient(create_app(container)) as client:
        body = client.get("/api/live/quotes", params={"ids": [ids["TCS-EQ"]]}).json()
        assert body == {"status": {"connected": False, "session_open": True, "today": "2026-11-19",
                                   "last_tick": None, "lost_at": None}, "quotes": []}
        service.step()  # asking for TCS streams it
        assert _ref(container, ids["TCS-EQ"]) in feed.subscribed
        exchange, token = _ref(container, ids["TCS-EQ"])
        feed.emit(LiveTick(exchange, token, datetime(2026, 11, 19, 10, 0, 1), 4102.15, prev_close=4118.6))
        body = client.get("/api/live/quotes", params={"ids": [ids["TCS-EQ"]]}).json()
        assert body["status"]["connected"] is True and body["status"]["last_tick"] == "2026-11-19T10:00:01"
        assert body["quotes"][0]["ltp"] == 4102.15 and body["quotes"][0]["ts"] == "2026-11-19T10:00:01"
        assert client.get("/api/live/quotes", params={"ids": list(range(1001))}).status_code == 422
