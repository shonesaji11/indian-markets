import logging

import pytest

logzero = pytest.importorskip("logzero")

import markets.providers.angelone  # noqa: F401,E402  (installs the redaction filter)


def test_sdk_error_logs_mask_secrets(tmp_path):
    # SmartConnect's constructor calls logzero.logfile(); this replays that, then the
    # error line smartConnect._request writes when a request fails.
    log_file = tmp_path / "app.log"
    logzero.logfile(str(log_file), loglevel=logging.ERROR)
    headers = {"Content-type": "application/json", "X-PrivateKey": "APIKEY123",
               "X-ClientPublicIP": "1.2.3.4", "Authorization": "Bearer eyJSECRET"}
    params = {"clientcode": "AB123", "password": "1234", "totp": "654321", "exchange": "NSE"}
    response = {"data": {"jwtToken": "Bearer eyJJWT", "refreshToken": "eyJREFRESH"}}
    logzero.logger.error(f"Error occurred. Headers: {headers}, Request: {params}, Response: {response}")
    logzero.logfile(None)

    text = log_file.read_text()
    for secret in ("APIKEY123", "1.2.3.4", "eyJSECRET", "1234", "654321", "eyJJWT", "eyJREFRESH"):
        assert secret not in text
    assert "'Authorization': '***'" in text and "'exchange': 'NSE'" in text
