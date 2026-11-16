# Option Greeks (docs: /docs/OptionGreeks)

`POST /rest/secure/angelbroking/marketData/v1/optionGreek`. SDK `optionGreek(params)`. Rate 1/s. NSE only.

Request: `{"name": "TCS", "expirydate": "25JAN2024"}`. `name` = underlying (scrip master `name`, e.g. `NIFTY`, `TCS`); `expirydate` = `DDMMMYYYY`, uppercase.

Response `data` = one row per strike and option type (all values are strings):

| Field | Example |
|---|---|
| `name` | `TCS` |
| `expiry` | `25JAN2024` |
| `strikePrice` | `"3900.000000"` (rupees) |
| `optionType` | `CE` / `PE` |
| `delta`, `gamma`, `theta`, `vega` | `"0.492400"`, ... |
| `impliedVolatility` | `"16.330000"` (percent) |
| `tradeVolume` | `"24048.00"` |
