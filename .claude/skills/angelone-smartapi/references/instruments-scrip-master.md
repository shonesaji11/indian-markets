# Instruments and scrip master (docs: /docs/Instruments)

## Scrip master (public, no auth)

`GET https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json` (the docs table also lists the `margincalculator.angelone.in` host). One JSON array of every instrument, regenerated daily (large file: cache it, refresh once a day).

Row:

```json
{"token": "2885", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "expiry": "", "strike": "-1.000000",
 "lotsize": "1", "instrumenttype": "", "exch_seg": "NSE", "tick_size": "5.000000", "freeze_qty": "0", "is_cas_enabled": true}
```

| Field | Notes |
|---|---|
| `token` | `symboltoken` for every API and the WebSocket |
| `symbol` | trading symbol (`SBIN-EQ`, `NIFTY25JAN24FUT`, ...) |
| `name` | underlying / company name (use for option-greek `name`) |
| `expiry` | derivatives, e.g. `25JAN2024`; empty for cash |
| `strike` | **in paise** (divide by 100); `-1` for non-options |
| `tick_size` | **in paise** (5.000000 = ₹0.05) |
| `lotsize` | string |
| `instrumenttype` | `""` for equity, `AMXIDX` index, `FUTIDX`, `FUTSTK`, `OPTIDX`, `OPTSTK`, ... |
| `exch_seg` | `NSE`, `BSE`, `NFO`, `BFO`, `MCX`, `CDS`, ... (the docs' sample shows `nse_cm`; the file uses exchange names) |
| `is_cas_enabled` | Closing Auction Session eligibility |

Known index tokens: Nifty 50 = `99926000` (symbol `Nifty 50`, name `NIFTY`, `instrumenttype` `AMXIDX`, exch `NSE`).

## Search scrip

`POST /rest/secure/angelbroking/order/v1/searchScrip`, SDK `searchScrip(exchange, searchscrip)`, 1/s. Body `{exchange: "NSE", searchscrip: "SBIN"}` → list of `{exchange, tradingsymbol, symboltoken}` (all series: `SBIN-EQ`, `SBIN-BE`, ...). One scrip per request. Prefer the cached scrip master.

## Intraday-allowed scrips

| Method | Path | SDK |
|---|---|---|
| GET | `/rest/secure/angelbroking/marketData/v1/nseIntraday` | `nseIntraday()` |
| GET | `/rest/secure/angelbroking/marketData/v1/bseIntraday` | `bseIntraday()` |

Response list `{exchange, SymbolName, Multiplier}` (margin multiplier, e.g. "5.0").

## Cautionary scrips

`GET /rest/secure/angelbroking/securities/v1/cautionaryScrips` (no SDK method). Response list `{token, symbol, message}` (ASM/GSM/trade-for-trade notes). Orders in these need `scripconsent: "yes"`.

## LTP

See market-data-quote.md (`getLtpData`).
