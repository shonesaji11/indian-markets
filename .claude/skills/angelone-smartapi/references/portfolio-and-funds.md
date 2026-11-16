# Portfolio and funds (docs: /docs/Portfolio, Funds section of /docs/User)

| Method | Path | SDK | Rate |
|---|---|---|---|
| GET | `/rest/secure/angelbroking/portfolio/v1/getHolding` | `holding()` | 1/s |
| GET | `/rest/secure/angelbroking/portfolio/v1/getAllHolding` | `allholding()` | 1/s |
| GET | `/rest/secure/angelbroking/order/v1/getPosition` | `position()` | 1/s |
| POST | `/rest/secure/angelbroking/order/v1/convertPosition` | `convertPosition(params)` | 10/s |
| GET | `/rest/secure/angelbroking/user/v1/getRMS` | `rmsLimit()` | 2/s |

## Holdings

`getHolding` `data` = list; `getAllHolding` `data = {holdings: [...], totalholding: {totalholdingvalue, totalinvvalue, totalprofitandloss, totalpnlpercentage}}`.

Holding row (numbers, not strings): `tradingsymbol, exchange, isin, t1quantity, realisedquantity, quantity, authorisedquantity, product, collateralquantity, collateraltype, haircut, averageprice, ltp, symboltoken, close, profitandloss, pnlpercentage`.

## Positions

Returns net and day positions (day = today's buy/sell activity). Row (strings): `exchange, symboltoken, producttype, tradingsymbol, symbolname, instrumenttype, priceden, pricenum, genden, gennum, precision, multiplier, boardlotsize, buyqty, sellqty, buyamount, sellamount, symbolgroup, strikeprice, optiontype, expirydate, lotsize, cfbuyqty, cfsellqty, cfbuyamount, cfsellamount, buyavgprice, sellavgprice, avgnetprice, netvalue, netqty, totalbuyvalue, totalsellvalue, cfbuyavgprice, cfsellavgprice, totalbuyavgprice, totalsellavgprice, netprice`.

## Convert position

Request: `exchange, symboltoken, oldproducttype, newproducttype, tradingsymbol, symbolname, instrumenttype, priceden, pricenum, genden, gennum, precision, multiplier, boardlotsize, buyqty, sellqty, buyamount, sellamount, transactiontype, quantity (int), type ("DAY")`. Response `data: null`.

## RMS (funds and margins)

`data` (strings): `net, availablecash, availableintradaypayin, availablelimitmargin, collateral, m2munrealized, m2mrealized, utiliseddebits, utilisedspan, utilisedoptionpremium, utilisedholdingsales, utilisedexposure, utilisedturnover, utilisedpayout`.
