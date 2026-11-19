from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import AlertCreateIn, AlertIn
from markets.bootstrap import Container
from markets.pipelines.alerts import AlertFiredError

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def alerts(c: Container = Depends(get_container)) -> dict:
    """All alerts (active first, then fired, newest first), each with its stock's last stored daily close,
    plus whether Telegram is set up and the live feed's state (alerts aren't checked while it's down)."""
    rows = c.alerts.list()
    closes = c.market.latest_quotes(sorted({r["instrument_id"] for r in rows}))
    for r in rows:
        r["close"] = (closes.get(r["instrument_id"]) or {}).get("close")
    return {"alerts": rows, "telegram": c.alerts.telegram, "live": c.live.status()}


@router.post("")
def create(body: AlertCreateIn, c: Container = Depends(get_container)) -> dict:
    try:
        return c.alerts.create(body.instrument_id, body.direction, body.price, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\""))


@router.patch("/{alert_id}")
def update(alert_id: str, body: AlertIn, c: Container = Depends(get_container)) -> dict:
    try:
        return c.alerts.update(alert_id, body.direction, body.price, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\""))
    except AlertFiredError as exc:
        raise HTTPException(409, str(exc))


@router.delete("/{alert_id}")
def delete(alert_id: str, c: Container = Depends(get_container)) -> dict:
    if not c.alerts.delete(alert_id):
        raise HTTPException(404, "alert not found")
    return {"deleted": alert_id}
