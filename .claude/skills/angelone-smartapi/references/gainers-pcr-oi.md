# Top gainers/losers, PCR, OI buildup (docs: /docs/TopGainers)

All three cover **NSE F&O only, today only, no history**. Rate limits not listed in the docs.

| Method | Path | SDK |
|---|---|---|
| POST | `/rest/secure/angelbroking/marketData/v1/gainersLosers` | `gainersLosers(params)` |
| GET | `/rest/secure/angelbroking/marketData/v1/putCallRatio` | `putCallRatio()` (no body) |
| POST | `/rest/secure/angelbroking/marketData/v1/OIBuildup` | `oIBuildup(params)` |

## Gainers/Losers

Request `{"datatype": ..., "expirytype": ...}`

| Key | Values |
|---|---|
| `datatype` | `PercPriceGainers`, `PercPriceLosers`, `PercOIGainers`, `PercOILosers` |
| `expirytype` | `NEAR` (current month), `NEXT`, `FAR` |

Response list (top ~10): `{tradingSymbol, percentChange, symbolToken (int), opnInterest, netChangeOpnInterest}`. Rows are futures symbols (e.g. `HDFCBANK25JAN24FUT`), but the docs say the data is cumulative across all option strikes for that underlying/expiry; the futures token only identifies underlying + expiry.

## PCR

Response list: `{pcr: 1.04, tradingSymbol: "NIFTY25JAN24FUT"}`. Options-only PCR, cumulative across strikes, mapped to the futures symbol per underlying.

## OI Buildup

Request `{"expirytype": "NEAR", "datatype": "Long Built Up"}`

| Key | Values (exactly one space between words) |
|---|---|
| `datatype` | `Long Built Up`, `Short Built Up`, `Short Covering`, `Long Unwinding` |
| `expirytype` | `NEAR`, `NEXT`, `FAR` |

Response list (string values): `{symbolToken, ltp, netChange, percentChange, opnInterest, netChangeOpnInterest, tradingSymbol}`.
