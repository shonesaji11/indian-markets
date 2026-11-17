"""Angel One SmartAPI adapter.

Docs: https://smartapi.angelone.in/docs
- Login needs API key, client code, PIN and a TOTP generated from your TOTP secret.
  Sessions last until midnight; the docs recommend logging out after each day's work.
- Historical candles: getCandleData, with a max span per request that depends on the
  interval. Rate limit (docs/RateLimit): 2/second, 80/minute, 5000/hour per client code.
- Error codes (docs/Exceptions): AG8001-AG8003 are token problems (log in again);
  AB1004 and AB2001 are transient server errors (retry).
- The instrument list (scrip master) is a public JSON file, no login needed.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Iterator, Optional

import httpx
import pandas as pd

from markets.core.models import CANDLE_COLUMNS, DateRange, Instrument, Interval, ProviderInstrument
from markets.providers import ProviderError
from markets.providers.ratelimit import RateLimiter

log = logging.getLogger(__name__)

# The SDK logs (via logzero) full request headers and params when a request fails:
# Bearer token, API key, PIN, TOTP. Mask those values before any handler writes them.
_SECRETS = re.compile(
    r"""(['"](?:Authorization|X-PrivateKey|X-ClientPublicIP|X-MACAddress|password|totp|"""
    r"""jwtToken|refreshToken|feedToken)['"]\s*:\s*)(['"])[^'"]*\2""", re.I)


class _RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = _SECRETS.sub(r"\1\2***\2", record.getMessage()), None
        return True


logging.getLogger("logzero_default").addFilter(_RedactSecrets())

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

# Our interval -> (SmartAPI interval name, max days per getCandleData request)
_INTERVALS = {
    Interval.M1: ("ONE_MINUTE", 30),
    Interval.M3: ("THREE_MINUTE", 60),
    Interval.M5: ("FIVE_MINUTE", 100),
    Interval.M10: ("TEN_MINUTE", 100),
    Interval.M15: ("FIFTEEN_MINUTE", 200),
    Interval.M30: ("THIRTY_MINUTE", 200),
    Interval.H1: ("ONE_HOUR", 400),
    Interval.D1: ("ONE_DAY", 2000),
}

_INSTRUMENT_TYPES = {"": "EQ", "AMXIDX": "INDEX"}

# Slightly under the documented 2/s, 80/min, 5000/hr so clock skew never trips them.
CANDLE_RATE_LIMITS = ((2, 1.05), (78, 60.0), (4900, 3600.0))
_TOKEN_ERRORS = ("AG8001", "AG8002", "AG8003")


class AngelOneProvider:
    name = "angelone"

    def __init__(self, api_key: Optional[str], client_code: Optional[str], pin: Optional[str],
                 totp_secret: Optional[str], max_retries: int = 4):
        self._creds = (api_key, client_code, pin, totp_secret)
        self._max_retries = max_retries
        self._api = None
        self._limiter = RateLimiter(CANDLE_RATE_LIMITS)

    # ---- instruments -------------------------------------------------------------

    def list_instruments(self) -> Iterator[ProviderInstrument]:
        resp = httpx.get(SCRIP_MASTER_URL, timeout=120)
        resp.raise_for_status()
        for row in resp.json():
            parsed = _parse_scrip(row)
            if parsed:
                yield parsed

    # ---- candles -----------------------------------------------------------------

    def fetch_candles(self, provider_token: str, exchange: str, interval: Interval, window: DateRange) -> pd.DataFrame:
        api_interval, max_days = _INTERVALS[interval]
        rows: list[list] = []
        for chunk in window.chunks(timedelta(days=max_days)):
            params = {
                "exchange": exchange,
                "symboltoken": provider_token,
                "interval": api_interval,
                "fromdate": chunk.start.strftime("%Y-%m-%d %H:%M"),
                "todate": chunk.end.strftime("%Y-%m-%d %H:%M"),
            }
            rows.extend(self._call_candles(params))
        return _candles_frame(rows)

    def _call_candles(self, params: dict) -> list[list]:
        last_error = None
        for attempt in range(self._max_retries):
            self._limiter.acquire()
            try:
                resp = self._session().getCandleData(params)
            except ProviderError:
                raise  # login problems will not fix themselves on retry
            except Exception as exc:  # SmartConnect raises plain exceptions on HTTP/rate-limit errors
                last_error = str(exc)
                log.warning("getCandleData failed (attempt %d): %s", attempt + 1, exc)
                if attempt + 1 < self._max_retries:
                    # Rate-limit rejections need the per-minute window to drain: 15s, 30s, 60s.
                    rate_limited = "exceeding access rate" in last_error
                    time.sleep(min(15.0 * 2 ** attempt, 60.0) if rate_limited else 1.5 * (attempt + 1))
                continue
            if resp and resp.get("status"):
                return resp.get("data") or []
            code = str(resp.get("errorcode", "")) if resp else ""
            last_error = f"{code}: {resp.get('message')}" if resp else "empty response"
            log.warning("getCandleData error (attempt %d): %s", attempt + 1, last_error)
            if code in _TOKEN_ERRORS:
                self._api = None
            if attempt + 1 < self._max_retries:
                time.sleep(1.5 * (attempt + 1))
        raise ProviderError(f"getCandleData failed for {params['symboltoken']}: {last_error}")

    # ---- plumbing ----------------------------------------------------------------

    def _session(self):
        if self._api is not None:
            return self._api
        api_key, client_code, pin, totp_secret = self._creds
        if not all(self._creds):
            raise ProviderError("Angel One credentials missing: set MARKETS_ANGEL_* in backend/.env")
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise ProviderError("Install the angelone extra: pip install -e .[angelone]") from exc

        api = SmartConnect(api_key=api_key)
        resp = api.generateSession(client_code, pin, pyotp.TOTP(totp_secret).now())
        if not resp or not resp.get("status"):
            raise ProviderError(f"Angel One login failed: {resp.get('message') if resp else 'no response'}")
        self._api = api
        return api

    def close(self) -> None:
        """Log out, as the docs recommend at the end of each day's activity."""
        if self._api is None:
            return
        try:
            self._api.terminateSession(self._creds[1])
        except Exception as exc:  # logging out is best-effort
            log.warning("Angel One logout failed: %s", exc)
        self._api = None


def _candles_frame(rows: list[list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(CANDLE_COLUMNS), index=pd.DatetimeIndex([], name="ts"), dtype=float)
    df = pd.DataFrame(rows, columns=["ts", *CANDLE_COLUMNS])
    # "2024-01-01T09:15:00+05:30" -> naive IST
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.drop_duplicates("ts", keep="last").set_index("ts").sort_index()
    return df.astype(float)


def _parse_scrip(row: dict) -> Optional[ProviderInstrument]:
    token, symbol, exchange = row.get("token"), row.get("symbol"), row.get("exch_seg")
    if not token or not symbol or not exchange:
        return None
    raw_type = row.get("instrumenttype") or ""
    expiry = None
    if row.get("expiry"):
        try:
            expiry = datetime.strptime(row["expiry"], "%d%b%Y").date()
        except ValueError:
            pass
    strike = _to_float(row.get("strike"))
    instrument = Instrument(
        exchange=exchange,
        symbol=symbol,
        name=row.get("name") or symbol,
        instrument_type=_INSTRUMENT_TYPES.get(raw_type, raw_type),
        lot_size=int(_to_float(row.get("lotsize")) or 1),
        tick_size=(_to_float(row.get("tick_size")) or 5) / 100,  # scrip master quotes tick size in paise
        expiry=expiry,
        strike=strike / 100 if strike and strike > 0 else None,  # strikes are in paise too
    )
    return ProviderInstrument(instrument=instrument, provider=AngelOneProvider.name, provider_token=str(token))


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
