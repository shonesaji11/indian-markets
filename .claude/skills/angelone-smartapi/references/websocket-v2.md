# WebSocket streaming 2.0 and order-status socket (docs: /docs/WebSocket2, /docs/WebSocketOrderStatus)

## Market data stream

URL `wss://smartapisocket.angelone.in/smart-stream`. SDK: `from SmartApi.smartWebSocketV2 import SmartWebSocketV2`; `SmartWebSocketV2(auth_token, api_key, client_code, feed_token, max_retry_attempt=1, retry_strategy=0, retry_delay=10, retry_multiplier=2, retry_duration=60)`; methods `connect()`, `subscribe(correlation_id, mode, token_list)`, `unsubscribe(...)`, `close_connection()`; override `on_open`, `on_data`, `on_error`, `on_close`.

Auth headers: `Authorization` (jwtToken), `x-api-key`, `x-client-code`, `x-feed-token`. Browser clients: `?clientCode=&feedToken=&apiKey=` query params instead. Auth failures → HTTP 401 with `x-error-message` header.

| Limit | Value |
|---|---|
| Connections per client code | 3 |
| Subscriptions per session | 1000 (token x mode counts separately) |
| Heartbeat | send text `ping` (docs: every 30 s; SDK pings every 10 s), server replies `pong` |
| Depth-20 (mode 4, SDK only) | NSE_CM (exchangeType 1) only, max 50 tokens |

Subscribe request:

```json
{"correlationID": "abcde12345", "action": 1,
 "params": {"mode": 1, "tokenList": [{"exchangeType": 1, "tokens": ["10626", "5290"]}]}}
```

| Field | Values |
|---|---|
| `action` | 1 subscribe, 0 unsubscribe |
| `mode` | 1 LTP, 2 Quote, 3 SnapQuote (4 Depth-20 in SDK) |
| `exchangeType` | 1 nse_cm, 2 nse_fo, 3 bse_cm, 4 bse_fo, 5 mcx_fo, 7 ncx_fo, 13 cde_fo (7/13 from SDK) |
| `correlationID` | optional, 10 chars, echoed in errors |

Recommendation: one mode per token. Unsubscribing unknown tokens and duplicate subscriptions are ignored.

### Binary response (little-endian)

| Offset | Size | Field | Type |
|---|---|---|---|
| 0 | 1 | subscription mode | int8 |
| 1 | 1 | exchange type | int8 |
| 2 | 25 | token (UTF-8, null-terminated) | bytes |
| 27 | 8 | sequence number (ignore for indices) | int64 |
| 35 | 8 | exchange timestamp, epoch ms | int64 |
| 43 | 8 | LTP — **LTP packet ends here (51 bytes)** | int64 |
| 51 | 8 | last traded qty | int64 |
| 59 | 8 | average traded price | int64 |
| 67 | 8 | volume for the day | int64 |
| 75 | 8 | total buy qty | double |
| 83 | 8 | total sell qty | double |
| 91/99/107 | 8 each | open / high / low | int64 |
| 115 | 8 | close — **Quote packet ends (123 bytes)** | int64 |
| 123 | 8 | last traded timestamp | int64 |
| 131 | 8 | open interest | int64 |
| 139 | 8 | OI change % (garbage, ignore) | double |
| 147 | 200 | best five: 10 x 20-byte packets (5 buys then 5 sells) | |
| 347/355 | 8 each | upper / lower circuit | int64 |
| 363/371 | 8 each | 52w high / low — **SnapQuote ends (379 bytes)** | int64 |

Best-five packet: flag int16 @0 (1 buy, 0 sell), qty int64 @2, price int64 @10, orders int16 @18.

**All prices are in paise**: divide by 100 (currency: divide by 10,000,000). The SDK returns raw paise values. `close` is the previous close, like Quote.

Errors (JSON): `{correlationID, errorCode, errorMessage}`; `E1001` invalid payload, `E1002` subscription limit exceeded.

## Order status stream

URL `wss://tns.angelone.in/smart-order-update`, header `Authorization: Bearer <jwt>`. SDK: `from SmartApi.smartWebSocketOrderUpdate import SmartWebSocketOrderUpdate` (`auth_token, api_key, client_code, feed_token`; `connect()`). Limit 3 connections per client code; ping every 10 s.

Message: `{"user-id", "status-code": "200", "order-status": "AB01", "error-message", "orderData": {...order book fields...}}`.

| order-status | Meaning |
|---|---|
| AB00 | connected (initial message) |
| AB01 / AB02 / AB03 / AB04 / AB05 | open / cancelled / rejected / modified / complete |
| AB06 / AB07 / AB08 | AMO received / AMO cancelled / AMO modify received |
| AB09 / AB10 / AB11 | open pending / trigger pending / modify pending |

Connection errors: 401 invalid token, 403 expired token, 429 connection limit exceeded.
