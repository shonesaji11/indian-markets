# Margin calculator and brokerage calculator (docs: /docs/MarginCalculator, /docs/BrokerageCalculator)

## Margin calculator

`POST /rest/secure/angelbroking/margin/v1/batch`. SDK `getMarginApi(params)`. 10/s, up to 50 positions per request. Real-time margin for a basket (with hedge benefit).

Request:

```json
{"positions": [{"exchange": "NFO", "qty": 50, "price": 0, "productType": "INTRADAY",
                "token": "67300", "tradeType": "BUY", "orderType": "LIMIT"}]}
```

| Field | Values |
|---|---|
| `exchange` | `NSE`, `BSE`, `NFO`, `BFO`, `MCX` |
| `qty` | int; for NFO, number of units (lot size multiples) |
| `price` | number |
| `productType` | `DELIVERY`, `CARRYFORWARD`, `MARGIN`, `INTRADAY`, `BO` |
| `token` | symbol token |
| `tradeType` | `BUY` / `SELL` |
| `orderType` | `LIMIT` (default), `MARKET`, `STOPLOSS_LIMIT`, `STOPLOSS_MARKET` |

Response `data`: `totalMarginRequired`, `marginComponents: {netPremium, spanMargin, marginBenefit, deliveryMargin, nonNFOMargin, totOptionsPremium}`.

## Brokerage calculator

`POST /rest/secure/angelbroking/brokerage/v1/estimateCharges`. SDK `estimateCharges(params)`. Rate not listed.

Request: `{"orders": [{product_type, transaction_type, quantity, price, exchange, symbol_name, token}]}` (snake_case, string values).

Response `data`:
- `summary: {total_charges, trade_value, breakup: [...]}`
- `charges: [{total_charges, trade_value, breakup}]`, one per order

`breakup` is a tree of `{name, amount, msg, breakup: [...]}`: `Angel One Brokerage`; `External Charges` → `Exchange Transaction Charges`, `Stamp Duty`, `SEBI Fees`; `Taxes` → `Security Transaction Tax`, `GST`.
