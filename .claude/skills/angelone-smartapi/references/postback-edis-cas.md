# Postback, EDIS, Closing Auction Session (docs: /docs/Postback, /docs/Edis, /docs/CASDoc)

## Postback / webhook

The postback URL is set when the API key is created. Angel POSTs real-time order updates for orders placed with that key. HTTPS on port 443 only. Payload = order-book row (see orders-and-gtt.md) plus `clientcode`. Statuses: open, pending, executed, cancelled, partially executed, ... AMO updates arrive at 09:00 when the order goes to the exchange. The order-status WebSocket (websocket-v2.md) is the alternative.

## EDIS (CDSL authorisation to sell holdings without POA)

Authorisation is needed once per day for selling.

| Method | Path | SDK | Body → data |
|---|---|---|---|
| POST | `/rest/secure/angelbroking/edis/v1/verifyDis` | `verifyDis(params)` | `{isin, quantity}` → `{ReqId, ReturnURL, DPId, BOID, TransDtls, version}`; already done today → `status:false, AG1000` |
| POST | `/rest/secure/angelbroking/edis/v1/generateTPIN` | `generateTPIN(params)` | `{dpId, ReqId, boid, pan}` → `data: null` |
| POST | `/rest/secure/angelbroking/edis/v1/getTranStatus` | `getTranStatus(params)` | `{ReqId}` → `TransResDtls{ReqId, ReqType, ResId, ResStatus, ResTime, ResError, Remarks, RecordResDtls[{TxnReqId, TxnId, Status, Errorcode}]}` |

TPIN entry happens in a browser: an HTML form posts `ReqId`, `DPId`, `TransDtls` (from verifyDis) to CDSL. Status `0` = not authorised to sell, `1` = authorised.

## Closing Auction Session (CAS), from 03 Aug 2026

SEBI's 20-minute closing auction for stocks that have F&O contracts (flag: scrip master `is_cas_enabled`). NFO/BFO trade until 15:40.

| Time (IST) | Phase |
|---|---|
| 15:15–15:20 | Transition; reference price computed; **SmartAPI order entry rejected** |
| 15:20–15:25 | Limit + market orders: place/modify/cancel |
| 15:25–15:30 | Limit only; market orders frozen; random close 15:28–15:30 |
| 15:30–15:35 | Matching; closing price set |
| 15:35–15:50 | Buffer |
| 15:50–16:00 | Post-close session at the equilibrium price |

- SL and iceberg orders are disallowed in CAS stocks 15:15–15:40.
- Auto square-off: Robo 15:05, equity MIS 15:10, F&O 15:20.
- Reference price = VWAP 15:00–15:15 (else LTP or previous close), with a ±3% band. Equilibrium price (volume-maximising) becomes the day's close; if there is none, the reference price is used.
- After 15:15, quote/LTP responses carry `referenceLimitPrice` (the Quote FULL sample shows `referenceLimitPoint`).

Effect for a dashboard: the official close for CAS stocks is the auction price, not the last continuous-trade price.
