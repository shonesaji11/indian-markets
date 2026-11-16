# Rate limits (docs: /docs/RateLimit)

Counted **per client code**. Over-limit requests fail with HTTP 403 and the plain-text (non-JSON) body `Access denied because of exceeding access rate`. Place/modify/cancel order share one combined 9/s budget.

| Endpoint (under `/rest/...`) | /s | /min | /hr |
|---|---|---|---|
| `auth/.../user/v1/loginByPassword` | 1 | – | – |
| `auth/.../jwt/v1/generateTokens` | 1 | – | 1000 |
| `secure/.../user/v1/getProfile` | 3 | – | 1000 |
| `secure/.../user/v1/logout` | 1 | – | – |
| `secure/.../user/v1/getRMS` | 2 | – | – |
| `order/v1/placeOrder`, `modifyOrder`, `cancelOrder` | 9 (combined) | 500 | 1000 |
| `order/v1/getOrderBook` | 1 | – | – |
| `order/v1/getTradeBook` | 1 | – | – |
| `order/v1/getPosition` | 1 | – | – |
| `order/v1/getLtpData` | 10 | 500 | 5000 |
| `order/v1/convertPosition` | 10 | 500 | 5000 |
| `order/v1/searchScrip` | 1 | – | – |
| `order/v1/details/{id}` | 10 | 500 | 5000 |
| `portfolio/v1/getHolding`, `getAllHolding` | 1 | – | – |
| `market/v1/quote` | 10 | 500 | 5000 |
| `margin/v1/batch` | 10 | 500 | 5000 |
| `gtt/v1/createRule`, `modifyRule`, `cancelRule` | 9 | 500 | 5000 |
| `gtt/v1/ruleDetails`, `ruleList` | 10 | 500 | 5000 |
| `historical/v1/getCandleData` | 2 | 80 | 5000 |
| `marketData/v1/optionGreek` | 1 | – | – |

Not listed: getOIData, gainersLosers, putCallRatio, OIBuildup, nse/bseIntraday, estimateCharges, EDIS. Treat them as about 1/s.

Other per-request caps: Quote 50 tokens (the Market Data page also says 1 req/s), margin batch 50 positions, WebSocket 3 connections and 1000 subscriptions per client code.

Practical pacing (confirmed): candles at 0.4 s spacing get rejected; use >= 0.5 s and a per-minute budget of < 80.
