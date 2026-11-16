---
name: angelone-smartapi
description: Compact reference for the Angel One SmartAPI (REST + WebSocket) and the smartapi-python SDK (`from SmartApi import SmartConnect`). Use for any work on Angel One / SmartAPI / the broker API in this project, including login/TOTP/session tokens, historical candles (getCandleData), Quote/LTP market data, top gainers/PCR/OI buildup, option greeks, WebSocket streaming, scrip master/instrument tokens, orders/GTT, holdings/positions/funds, margin/brokerage, rate limits and error codes, and `backend/src/markets/providers/angelone.py`. Read SKILL.md first, then only the reference file for the area at hand.
---

# Angel One SmartAPI

Source: https://smartapi.angelone.in/docs/ (JS-rendered; WebFetch returns an empty page). SDK checked against installed `smartapi-python` 1.5.3 (`backend/.venv/Lib/site-packages/SmartApi/`).

## Basics

- Base URL `https://apiconnect.angelone.in`. JSON in, JSON out. Nearly everything is POST; GETs are noted per endpoint.
- Envelope: `{"status": bool, "message": str, "errorcode": str, "data": ...}`. HTTP 200 can still be `status: false`; check `errorcode`.
- Headers on every call:

| Header | Value |
|---|---|
| `Content-Type`, `Accept` | `application/json` |
| `X-UserType` | `USER` |
| `X-SourceID` | `WEB` |
| `X-ClientLocalIP`, `X-ClientPublicIP`, `X-MACAddress` | client IPs / MAC |
| `X-PrivateKey` | API key |
| `Authorization` | `Bearer <jwtToken>` (all except loginByPassword) |

- Login: client code + **MPIN** (`password`) + **TOTP** from the base32 secret → `jwtToken`, `refreshToken`, `feedToken`. Sessions expire at **midnight IST**; the docs recommend logging out daily.

## SDK → REST map (`SmartConnect(api_key=...)`)

| SDK method | Endpoint (prefix `/rest/secure/angelbroking/` unless shown) | Ref |
|---|---|---|
| `generateSession(client, mpin, totp)` | `/rest/auth/angelbroking/user/v1/loginByPassword` | auth |
| `generateToken(refresh)`, `renewAccessToken()` | `/rest/auth/angelbroking/jwt/v1/generateTokens` | auth |
| `getProfile(refresh)` / `terminateSession(client)` | `user/v1/getProfile` (GET) / `user/v1/logout` | auth |
| `rmsLimit()` | `user/v1/getRMS` (GET) | portfolio |
| `getCandleData(p)` / `getOIData(p)` | `historical/v1/getCandleData` / `getOIData` | historical |
| `getMarketData(mode, exchangeTokens)` | `market/v1/quote` | quote |
| `ltpData(exch, symbol, token)` | `order/v1/getLtpData` | quote |
| `gainersLosers(p)` / `putCallRatio()` / `oIBuildup(p)` | `marketData/v1/gainersLosers` / `putCallRatio` (GET) / `OIBuildup` | gainers |
| `optionGreek(p)` | `marketData/v1/optionGreek` | greeks |
| `searchScrip(exch, text)` | `order/v1/searchScrip` | instruments |
| `nseIntraday()` / `bseIntraday()` | `marketData/v1/nseIntraday` / `bseIntraday` (GET) | instruments |
| `placeOrder` / `placeOrderFullResponse` / `modifyOrder` / `cancelOrder(id, variety)` | `order/v1/placeOrder` / `modifyOrder` / `cancelOrder` | orders |
| `orderBook()` / `tradeBook()` / `individual_order_details(uid)` | `order/v1/getOrderBook` / `getTradeBook` / `details/{uid}` (GET) | orders |
| `gttCreateRule` / `gttModifyRule` / `gttCancelRule` / `gttDetails(id)` / `gttLists(status, page, count)` | `gtt/v1/createRule` ... `ruleList` | orders |
| `holding()` / `allholding()` / `position()` / `convertPosition(p)` | `portfolio/v1/getHolding` / `getAllHolding` / `order/v1/getPosition` / `convertPosition` | portfolio |
| `getMarginApi(p)` / `estimateCharges(p)` | `margin/v1/batch` / `brokerage/v1/estimateCharges` | margin |
| `verifyDis` / `generateTPIN` / `getTranStatus` | `edis/v1/...` | postback-edis-cas |
| `SmartWebSocketV2(...)` / `SmartWebSocketOrderUpdate(...)` | `wss://smartapisocket.angelone.in/smart-stream` / `wss://tns.angelone.in/smart-order-update` | websocket |

## Confirmed gotchas

- **getCandleData: 2/s, 80/min, 5000/hr per client code.** At 0.4 s spacing, requests were rejected with the non-JSON body `Access denied because of exceeding access rate` (the SDK raises `DataException`). Pace at >= 0.5 s and back off.
- **Max days per candle request:** 1m 30, 3m 60, 5m/10m 100, 15m/30m 200, 1h 400, 1d 2000. Dates are `"yyyy-MM-dd hh:mm"`; timestamps come back with `+05:30`.
- Daily history is **split/bonus adjusted**. Index volume is **0**. Nifty 50 has a gap in Angel's own data from **28 Aug to 12 Sep 2017**.
- **Quote `close` = previous day's close** (the same holds for WebSocket close). Quote takes up to **50 tokens** per request.
- Top Gainers/Losers, PCR and OI Buildup: **NSE F&O only, today only, no history**.
- Errors AG8001–AG8003 are token problems: log in again. AB1004 and AB2001 are transient: retry.
- SmartAPI portal: app creation rejects localhost redirect URLs (`https://example.com` works) and requires a **static IP** (SEBI rule, enforced for orders and GTT).
- Scrip master: public JSON at `https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json`. `strike` and `tick_size` are in **paise**. Nifty 50 token = `99926000`.
- WebSocket binary prices are in **paise** (divide by 100); REST prices are in rupees.
- SDK quirks (1.5.3): the class attribute `clientPublicIp` is hard-coded to `106.193.147.98` and `clientLocalIp` to `127.0.0.1` (a `finally` block overwrites the detected IPs). The constructor's `clientPublicIP`/`clientLocalIP` args are ignored by `requestHeaders()`. Set `obj.clientPublicIp` / `obj.clientLocalIp` on the instance if the static IP matters. `SmartConnect()` and the WebSocket classes create `logs/<date>/app.log` in the CWD. Most API errors come back as `status: false` dicts, not exceptions. GTT create/modify/cancel in the SDK use a `/gtt-service` prefix.
- From 03 Aug 2026, the Closing Auction Session changes the official close for F&O stocks and rejects SmartAPI orders 15:15–15:20 (see postback-edis-cas.md).

## Reference files (`references/`)

| File | Covers (doc page) |
|---|---|
| `auth-and-session.md` | Login/TOTP, token refresh, profile, logout, publisher login, envelope, portal setup (User, ResponseStructure) |
| `historical.md` | getCandleData intervals, max days, response shape, OI history, data quirks (Historical) |
| `market-data-quote.md` | Quote LTP/OHLC/FULL fields and depth, getLtpData (MarketData) |
| `gainers-pcr-oi.md` | Top gainers/losers, PCR, OI buildup parameters and responses (TopGainers) |
| `option-greeks.md` | Greeks + IV by underlying and expiry (OptionGreeks) |
| `websocket-v2.md` | Stream auth, subscribe JSON, binary packet layout, limits; order-status socket codes (WebSocket2, WebSocketOrderStatus) |
| `instruments-scrip-master.md` | Scrip master fields/units, searchScrip, intraday lists, cautionary scrips (Instruments) |
| `orders-and-gtt.md` | Order constants, place/modify/cancel, order/trade book fields, GTT rules (Orders, Gtt) |
| `portfolio-and-funds.md` | Holdings, all-holdings summary, positions, convert, RMS funds (Portfolio, User/Funds) |
| `margin-brokerage.md` | Margin batch calculator, brokerage/charges estimate (MarginCalculator, BrokerageCalculator) |
| `rate-limits.md` | Full per-endpoint throttle table and other caps (RateLimit) |
| `error-codes.md` | AB/AG/GTT/WebSocket codes with actions, SDK exception classes (Exceptions) |
| `postback-edis-cas.md` | Postback webhook, EDIS/TPIN flow, Closing Auction Session timings (Postback, Edis, CASDoc) |
