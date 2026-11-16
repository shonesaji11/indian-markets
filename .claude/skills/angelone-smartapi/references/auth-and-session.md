# Auth and session (docs: /docs/User, /docs/ResponseStructure)

Base URL `https://apiconnect.angelone.in`. All bodies JSON. All "secure" endpoints need the headers listed in SKILL.md plus `Authorization: Bearer <jwtToken>`.

## Endpoints

| Method | Path | SDK (`SmartConnect`) | Notes |
|---|---|---|---|
| POST | `/rest/auth/angelbroking/user/v1/loginByPassword` | `generateSession(clientCode, password, totp)` | No Authorization header. `password` = MPIN. |
| POST | `/rest/auth/angelbroking/jwt/v1/generateTokens` | `generateToken(refresh_token)` / `renewAccessToken()` | Body `{refreshToken}`; needs Bearer header. |
| GET | `/rest/secure/angelbroking/user/v1/getProfile` | `getProfile(refreshToken)` | |
| GET | `/rest/secure/angelbroking/user/v1/getRMS` | `rmsLimit()` | Funds & margins (see portfolio-and-funds.md). |
| POST | `/rest/secure/angelbroking/user/v1/logout` | `terminateSession(clientCode)` | Body `{clientcode}`. Invalidates the JWT only (not web login). |

## Login

Request: `{clientcode, password (MPIN), totp, state?}`. `totp` = 6-digit code from the base32 TOTP secret (e.g. `pyotp.TOTP(secret).now()`). `state` is optional and echoed back.

Response `data`: `jwtToken`, `refreshToken`, `feedToken`, `state`.
- `jwtToken` → `Authorization: Bearer ...` for REST, and raw `Authorization` for WebSocket.
- `feedToken` → WebSocket `x-feed-token`.
- `refreshToken` → generateTokens / getProfile.

SDK `generateSession` also sets the tokens on the object, calls `getProfile`, and returns the profile with `jwtToken` (prefixed `"Bearer "`), `refreshToken`, `feedToken` added to `data`.

Session lives until **midnight** (IST) unless logged out. Docs recommend logging out daily.

## Generate token

Request `{refreshToken}` → `data: {jwtToken, refreshToken, feedToken}`.

## Get profile

`data`: `clientcode, name, email, mobileno, exchanges[], products[], lastlogintime, brokerid`.

## Publisher login (redirect flow, for third-party apps)

`https://smartapi.angelone.in/publisher-login?api_key=xxx&redirect_url=yyy&state=...` → redirect to the app's URL with `auth_token` and `feed_token` query params. SDK: `login_url()`. Not needed for personal TOTP login.

## Response envelope

Success: `{"status": true, "message": "SUCCESS", "errorcode": "", "data": {...}}`
Failure: `{"status": false, "message": "...", "errorcode": "AB1007", "data": null}`

Always check `status` and `errorcode`, not just HTTP 200. See error-codes.md.

## App setup (SmartAPI portal)

- Redirect URL: localhost is rejected; `https://example.com` works.
- Static IP is required at app creation (SEBI rule); orders/GTT create/modify/cancel are validated against the registered IP.
