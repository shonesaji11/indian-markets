import logging

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
    p._api = _FakeSession(fail)
    return p, slept


def test_rate_limit_backoff_grows(monkeypatch):
    p, slept = _provider(monkeypatch, fail=3)
    assert len(p._call_candles({"symboltoken": "1"})) == 1
    assert slept == [15.0, 30.0, 60.0]


def test_rate_limit_gives_up_without_a_final_sleep(monkeypatch):
    p, slept = _provider(monkeypatch, fail=9, retries=3)
    with pytest.raises(ProviderError, match="exceeding access rate"):
        p._call_candles({"symboltoken": "1"})
    assert p._api.calls == 3 and slept == [15.0, 30.0]


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
