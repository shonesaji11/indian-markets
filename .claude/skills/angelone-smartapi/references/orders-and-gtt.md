# Orders and GTT (docs: /docs/Orders, /docs/Gtt)

Orders and GTT create/modify/cancel are validated against the app's registered **static IP**. Order place+modify+cancel share a combined limit of 9/s (each also 500/min, 1000/hr).

## Order endpoints

| Method | Path | SDK | Rate |
|---|---|---|---|
| POST | `/rest/secure/angelbroking/order/v1/placeOrder` | `placeOrder(params)` → orderid; `placeOrderFullResponse(params)` → full JSON | 9/s |
| POST | `/rest/secure/angelbroking/order/v1/modifyOrder` | `modifyOrder(params)` | 9/s |
| POST | `/rest/secure/angelbroking/order/v1/cancelOrder` | `cancelOrder(order_id, variety)` | 9/s |
| GET | `/rest/secure/angelbroking/order/v1/getOrderBook` | `orderBook()` | 1/s |
| GET | `/rest/secure/angelbroking/order/v1/getTradeBook` | `tradeBook()` (today only) | 1/s |
| GET | `/rest/secure/angelbroking/order/v1/details/{uniqueorderid}` | `individual_order_details(uniqueorderid)` | 10/s |
| POST | `/rest/secure/angelbroking/order/v1/getLtpData` | `ltpData(...)` (see market-data-quote.md) | 10/s |

## Constants

| Param | Values |
|---|---|
| `variety` | `NORMAL`, `STOPLOSS`, `ROBO` (bracket) |
| `transactiontype` | `BUY`, `SELL` |
| `ordertype` | `MARKET`, `LIMIT`, `STOPLOSS_LIMIT` (SL), `STOPLOSS_MARKET` (SL-M) |
| `producttype` | `DELIVERY` (CNC), `CARRYFORWARD` (NRML, F&O), `MARGIN`, `INTRADAY` (MIS), `BO` (ROBO only) |
| `duration` | `DAY`, `IOC` (IOC not allowed for commodities) |
| `exchange` | `NSE`, `BSE`, `NFO`, `BFO`, `MCX` |

## Place order fields

`variety, tradingsymbol, symboltoken, exchange, transactiontype, ordertype, quantity, producttype, duration, price` (LIMIT), `triggerprice` (SL/SL-M), `squareoff`/`stoploss`/`trailingStopLoss` (ROBO only), `disclosedquantity`, `ordertag` (< 20 chars, else AB4008), `scripconsent: "yes"` (needed for cash orders in surveillance scrips). Values are strings.

Response `data: {script, orderid, uniqueorderid}`. Order status is unknown at placement; poll order book / details or use the order socket/postback.

- Orders after market hours become AMO.
- MARKET orders are converted to LIMIT by Angel One using MPP (market price protection) limits.

Modify: `{variety, orderid, ordertype, producttype, duration, price, quantity, tradingsymbol, symboltoken, exchange}` → `{orderid, uniqueorderid}`. Cancel: `{variety, orderid}`.

## Order book / details row

`variety, ordertype, producttype, duration, price, triggerprice, quantity, disclosedquantity, squareoff, stoploss, trailingstoploss, tradingsymbol, transactiontype, exchange, symboltoken, ordertag, instrumenttype, strikeprice, optiontype, expirydate, lotsize, cancelsize, averageprice, filledshares, unfilledshares, orderid, text` (rejection reason), `status, orderstatus` (`open`, `cancelled`, `rejected`, `complete`, ...), `updatetime, exchtime, exchorderupdatetime` (`"20-Oct-2020 13:10:59"`), `fillid, filltime, parentorderid, uniqueorderid, exchangeorderid`.

Trade book row: `exchange, producttype, tradingsymbol, instrumenttype, symbolgroup, strikeprice, optiontype, expirydate, marketlot, precision, multiplier, tradevalue, transactiontype, fillprice, fillsize, orderid, fillid, filltime`.

## GTT

NSE and BSE only; `DELIVERY` and `MARGIN` products only.

| Method | Docs path | SDK | Rate |
|---|---|---|---|
| POST | `/rest/secure/angelbroking/gtt/v1/createRule` | `gttCreateRule(params)` | 9/s |
| POST | `/rest/secure/angelbroking/gtt/v1/modifyRule` | `gttModifyRule(params)` | 9/s |
| POST | `/rest/secure/angelbroking/gtt/v1/cancelRule` | `gttCancelRule(params)` | 9/s |
| POST | `/rest/secure/angelbroking/gtt/v1/ruleDetails` | `gttDetails(id)` | 10/s |
| POST | `/rest/secure/angelbroking/gtt/v1/ruleList` | `gttLists(status: list, page, count)` | 10/s |

SDK 1.5.3 prefixes create/modify/cancel with `/gtt-service` (`/gtt-service/rest/secure/...`); docs omit it.

| Call | Request | Response `data` |
|---|---|---|
| create | `tradingsymbol, symboltoken, exchange, transactiontype, producttype, price, qty, triggerprice, disclosedqty` | `{id}` |
| modify | `id, symboltoken, exchange, price, qty, triggerprice, disclosedqty` | `{id}` |
| cancel | `id, symboltoken, exchange` | `{id}` |
| details | `id` | rule: `status, createddate, updateddate, expirydate` (ISO Z), `clientid` + create fields |
| list | `status: [NEW, CANCELLED, ACTIVE, SENTTOEXCHANGE, FORALL], page, count` | list of rules |

GTT error codes AB9000–AB9018: see error-codes.md.
