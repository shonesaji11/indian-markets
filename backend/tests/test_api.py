from fastapi.testclient import TestClient

from markets.api.app import create_app


def test_end_to_end(container, reliance_id):
    with TestClient(create_app(container)) as client:
        found = client.get("/api/instruments", params={"q": "reli"}).json()
        assert found[0]["symbol"] == "RELIANCE-EQ"

        resp = client.post("/api/ingest", json={"instrument_ids": [reliance_id], "start": "2024-01-01T00:00:00",
                                                 "end": "2024-12-31T00:00:00"})
        assert resp.status_code == 202
        assert client.get("/api/ingest/runs").json()[0]["status"] == "ok"

        candles = client.get(f"/api/candles/{reliance_id}").json()["candles"]
        assert len(candles) > 200

        series = client.post("/api/calcs/run", json={"instrument_id": reliance_id, "name": "macd"}).json()
        assert series["outputs"] == ["macd", "signal", "histogram"]
        assert series["points"][-1]["signal"] is not None

        again = client.get(f"/api/calcs/{series['calc_id']}/series", params={"instrument_id": reliance_id}).json()
        assert again["points"] == series["points"]

        stats = client.get("/api/views/daily-stats", params={"as_of": "2024-06-28"}).json()
        assert stats[0]["ts"].startswith("2024-06-28")

        assert client.post("/api/calcs/run", json={"instrument_id": reliance_id, "name": "nope"}).status_code == 400
