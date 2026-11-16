# Error codes (docs: /docs/Exceptions, GTT and WebSocket pages)

Errors come in the envelope: `{"status": false, "message": "...", "errorcode": "AB1007", "data": null}`. Rate-limit errors are **not** JSON (see rate-limits.md).

## General

| Code | Meaning | Action |
|---|---|---|
| AG8001 | Invalid token | log in again |
| AG8002 | Token expired | log in again (sessions end at midnight) |
| AG8003 | Token missing | log in again / check Authorization header |
| AB8050 | Invalid refresh token | full login |
| AB8051 | Refresh token expired | full login |
| AB1000 | Invalid email or password | |
| AB1001 | Invalid email | |
| AB1002 | Invalid password length | |
| AB1003 | Client already exists | |
| AB1004 | Something went wrong, try later | **transient: retry** |
| AB1005 | User type must be USER | check `X-UserType` |
| AB1006 | Client is blocked for trading | |
| AB1007 | AMX error (also seen for bad login) | |
| AB1008 | Invalid order variety | |
| AB1009 | Symbol not found | |
| AB1010 | AMX session expired | log in again |
| AB1011 | Client not logged in | log in again |
| AB1012 | Invalid product type | |
| AB1013 / AB1014 / AB1015 / AB1016 | Order / trade / holding / position not found | |
| AB1017 | Position conversion failed | |
| AB1018 | Failed to get symbol details | |
| AB1031 | Old password mismatch | |
| AB1032 | User not found | |
| AB2000 | Error not specified | |
| AB2001 | Internal error, try later | **transient: retry** |
| AB2002 | ROBO order is blocked | |
| AB4008 | ordertag must be < 20 chars | |
| AB4018 | Symbol token cannot be empty (Quote `unfetched`) | |
| AG1000 | EDIS: already registered with CDSL today | not an error in practice |
| AG2001 | EDIS: something went wrong | retry |

## GTT

| Code | Meaning |
|---|---|
| AB9000 | Internal server error |
| AB9001 | Invalid parameters |
| AB9002 | Method not allowed |
| AB9003 | Invalid client ID |
| AB9004 | Invalid status array size |
| AB9005 | Invalid session ID |
| AB9006 / AB9007 | Invalid order qty / disclosed qty |
| AB9008 / AB9009 | Invalid price / trigger price |
| AB9010 | Invalid exchange segment |
| AB9011 / AB9012 | Invalid symbol token / trading symbol |
| AB9013 | Invalid rule ID |
| AB9014 / AB9015 | Invalid order side / product type |
| AB9016 | Invalid time period |
| AB9017 / AB9018 | Invalid page / count value |

## WebSocket

Market stream: `E1001` invalid payload, `E1002` subscription limit exceeded; HTTP 401 + `x-error-message` header on auth failure. Order stream: 401 invalid token, 403 expired token, 429 connection limit.

## SDK exceptions (`SmartApi.smartExceptions`)

`SmartAPIException` base; `GeneralException`, `TokenException`, `PermissionException`, `OrderException`, `InputException`, `DataException` (also raised for non-JSON bodies such as the rate-limit message), `NetworkException`. Raised only when the body has `error_type`; most API errors come back as a normal dict with `status: false`, so check `status`/`errorcode` yourself.
