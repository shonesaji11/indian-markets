# Historical candles and OI (docs: /docs/Historical)

## Endpoints

| Method | Path | SDK | Rate limit |
|---|---|---|---|
| POST | `/rest/secure/angelbroking/historical/v1/getCandleData` | `getCandleData(params)` | 2/s, 80/min, 5000/hr per client code |
| POST | `/rest/secure/angelbroking/historical/v1/getOIData` | `getOIData(params)` | not listed in the docs |

## Request (both)

| Field | Value |
|---|---|
| `exchange` | `NSE` (stocks + indices), `NFO`, `BSE` (stocks + indices), `BFO`, `MCX` |
| `symboltoken` | token from scrip master, e.g. Nifty 50 = `99926000` |
| `interval` | see table below |
| `fromdate`, `todate` | `"yyyy-MM-dd hh:mm"` (24h, IST), e.g. `"2023-09-06 11:15"` |

## Intervals and max days per request

| interval | max days |
|---|---|
| `ONE_MINUTE` | 30 |
| `THREE_MINUTE` | 60 |
| `FIVE_MINUTE` | 100 |
| `TEN_MINUTE` | 100 |
| `FIFTEEN_MINUTE` | 200 |
| `THIRTY_MINUTE` | 200 |
| `ONE_HOUR` | 400 |
| `ONE_DAY` | 2000 |

Longer ranges must be chunked into windows of at most these lengths.

## Candle response

`data` = list of `[timestamp, open, high, low, close, volume]`, timestamp ISO with `+05:30`, e.g. `["2023-09-06T11:15:00+05:30", 19571.2, 19573.35, 19534.4, 19552.05, 0]`. Prices in rupees (not paise).

## OI response

Only for live (unexpired) F&O contracts. `data` = list of `{time: "2024-08-19T12:24:00+05:30", oi: 166100}`.

## Confirmed behaviour (live use)

- Bursts spaced 0.4 s apart were rejected with a **non-JSON** body: `Access denied because of exceeding access rate`. The SDK then raises `DataException("Couldn't parse the JSON response ...")`. In practice only 40 calls a minute get through (measured 19 Nov 2026; see rate-limits.md): pace at >= 1.55 s and wait 60 s after a rejection.
- Daily history is **adjusted** for splits and bonuses.
- Index volume is always 0.
- Nifty 50 (99926000) has a gap in Angel's own data from 28 Aug 2017 to 12 Sep 2017. Not a client bug.
