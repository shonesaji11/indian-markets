# Market data: Quote and LTP (docs: /docs/MarketData, LTP in /docs/Orders and /docs/Instruments)

## Endpoints

| Method | Path | SDK | Limits |
|---|---|---|---|
| POST | `/rest/secure/angelbroking/market/v1/quote` | `getMarketData(mode, exchangeTokens)` | 50 tokens/request; docs text says 1 req/s, rate-limit table says 10/s, 500/min, 5000/hr |
| POST | `/rest/secure/angelbroking/order/v1/getLtpData` | `ltpData(exchange, tradingsymbol, symboltoken)` | 10/s, 500/min, 5000/hr; one instrument per call |

Prefer Quote (batch of 50) over getLtpData for anything multi-symbol.

## Quote request

```json
{"mode": "FULL", "exchangeTokens": {"NSE": ["3045", "881"], "NFO": ["58662"]}}
```

`mode`: `LTP` | `OHLC` | `FULL`. All exchanges supported (keys: NSE, NFO, BSE, BFO, MCX, CDS, NCDEX).

## Quote response

`data = {fetched: [...], unfetched: [...]}`. Unfetched items: `{exchange, symbolToken, message, errorCode}` (e.g. `AB4018` "Symbol token cannot be empty").

| Field | Mode | Notes |
|---|---|---|
| `exchange`, `tradingSymbol`, `symbolToken`, `ltp` | all | camelCase keys (unlike other endpoints) |
| `open`, `high`, `low`, `close` | OHLC, FULL | **`close` = previous day's close** |
| `lastTradeQty`, `exchFeedTime`, `exchTradeTime` | FULL | times like `"21-Jun-2023 10:46:10"` (IST, no tz) |
| `netChange`, `percentChange` | FULL | vs previous close |
| `avgPrice`, `tradeVolume`, `opnInterest` | FULL | |
| `lowerCircuit`, `upperCircuit`, `52WeekLow`, `52WeekHigh` | FULL | |
| `totBuyQuan`, `totSellQuan` | FULL | |
| `referenceLimitPoint` / `referenceLimitPrice` | FULL | CAS reference price after 15:15 (see postback-edis-cas.md) |
| `depth.buy[]`, `depth.sell[]` | FULL | 5 levels of `{price, quantity, orders}` |

Prices here are in rupees.

## getLtpData

Request `{exchange, tradingsymbol, symboltoken}` → `data: {exchange, tradingsymbol, symboltoken, open, high, low, close, ltp}` (string values). The Instruments page lists the same call at `/order-service/rest/secure/angelbroking/order/v1/getLtpData`; the SDK uses the path without `/order-service`.
