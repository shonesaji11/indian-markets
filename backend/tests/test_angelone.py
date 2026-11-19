import logging
from datetime import date

import pytest

logzero = pytest.importorskip("logzero")

import markets.providers.angelone  # noqa: F401,E402  (installs the redaction filter)
from markets.providers import ProviderError  # noqa: E402
from markets.providers.angelone import AngelOneProvider  # noqa: E402


class _NoLimit:
    def acquire(self):
        pass


class _FakeSession:
    """Raises the SDK's rate-limit exception `fail` times, then returns one bar."""

    def __init__(self, fail):
        self.fail = fail
        self.calls = 0

    def getCandleData(self, params):
        self.calls += 1
        if self.calls <= self.fail:
            raise Exception("Access denied because of exceeding access rate")
        return {"status": True, "data": [["2026-11-17T00:00:00+05:30", 1, 2, 0.5, 1.5, 100]]}


def _provider(monkeypatch, fail, retries=4):
    slept = []
    monkeypatch.setattr("markets.providers.angelone.time.sleep", slept.append)
    p = AngelOneProvider("k", "c", "p", "t", max_retries=retries)
    p._limiter = _NoLimit()
    p._api, p._login_day = _FakeSession(fail), date.today()  # a session logged in today
    return p, slept


def test_rate_limit_waits_for_the_minute_to_reset(monkeypatch):
    p, slept = _provider(monkeypatch, fail=3)
    assert len(p._call_candles({"symboltoken": "1"})) == 1
    assert slept == [60.0, 60.0, 60.0]


def test_rate_limit_gives_up_without_a_final_sleep(monkeypatch):
    p, slept = _provider(monkeypatch, fail=9, retries=3)
    with pytest.raises(ProviderError, match="exceeding access rate"):
        p._call_candles({"symboltoken": "1"})
    assert p._api.calls == 3 and slept == [60.0, 60.0]


def test_candle_calls_are_evenly_spaced_under_40_a_minute():
    from markets.providers.angelone import CANDLE_RATE_LIMITS
    from markets.providers.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(CANDLE_RATE_LIMITS, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    times = []
    for _ in range(200):
        limiter.acquire()
        times.append(now[0])
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert 1.55 <= min(gaps) and max(gaps) < 1.6  # even spacing (plus the limiter's 0.01 s margin), no bursts
    assert max(sum(1 for t in times if s <= t < s + 60.0) for s in times) <= 39  # Angel rejects the 41st in a minute


def test_sdk_error_logs_mask_secrets(tmp_path):
    # SmartConnect's constructor calls logzero.logfile(); this replays that, then the
    # error line smartConnect._request writes when a request fails.
    log_file = tmp_path / "app.log"
    logzero.logfile(str(log_file), loglevel=logging.ERROR)
    headers = {"Content-type": "application/json", "X-PrivateKey": "APIKEY123",
               "X-ClientPublicIP": "1.2.3.4", "Authorization": "Bearer eyJSECRET"}
    params = {"clientcode": "AB123", "password": "1234", "totp": "654321", "exchange": "NSE"}
    response = {"data": {"jwtToken": "Bearer eyJJWT", "refreshToken": "eyJREFRESH"}}
    logzero.logger.error(f"Error occurred. Headers: {headers}, Request: {params}, Response: {response}")
    logzero.logfile(None)

    text = log_file.read_text()
    for secret in ("APIKEY123", "1.2.3.4", "eyJSECRET", "1234", "654321", "eyJJWT", "eyJREFRESH"):
        assert secret not in text
    assert "'Authorization': '***'" in text and "'exchange': 'NSE'" in text


class _QuoteSession:
    """Answers getMarketData with one quote per token; token '0' has no usable trade time."""

    def __init__(self):
        self.batches = []

    def getMarketData(self, mode, exchange_tokens):
        tokens = exchange_tokens["NSE"]
        self.batches.append(len(tokens))
        fetched = [{"symbolToken": t, "exchTradeTime": "" if t == "0" else "17-Nov-2026 15:29:59"} for t in tokens]
        return {"status": True, "data": {"fetched": fetched, "unfetched": []}}


def test_last_trade_dates_batches_by_50(monkeypatch):
    p, _ = _provider(monkeypatch, fail=0)
    p._quote_limiter = _NoLimit()
    p._api = _QuoteSession()
    tokens = [str(i) for i in range(120)]
    dates = p.last_trade_dates("NSE", tokens)
    assert p._api.batches == [50, 50, 20]
    assert len(dates) == 119 and "0" not in dates  # unparseable time is left out
    assert set(dates.values()) == {date(2026, 11, 17)}
