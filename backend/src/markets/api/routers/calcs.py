from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import CalcRunIn, CalcSeriesOut, IndicatorOut
from markets.bootstrap import Container
from markets.core.models import Interval
from markets.storage.duckdb.repositories import CodeChangedError

router = APIRouter(prefix="/calcs", tags=["calculations"])


def _points(frame: pd.DataFrame) -> list[dict]:
    frame = frame.dropna(how="all").reset_index()
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


@router.get("/indicators", response_model=list[IndicatorOut])
def indicators(c: Container = Depends(get_container)):
    """Calculations the engine can run, with their default params."""
    return [spec.describe() for spec in c.registry.all()]


@router.get("/definitions")
def definitions(c: Container = Depends(get_container)) -> list[dict]:
    """Every (name, version, params) combination that has been computed and stored."""
    return c.calcs.definitions()


@router.post("/run", response_model=CalcSeriesOut)
def run(body: CalcRunIn, c: Container = Depends(get_container)):
    """Compute an indicator over stored candles, persist it, and return the series."""
    try:
        outcome = c.calc_service.compute(body.name, body.instrument_id, body.interval, body.params)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    except CodeChangedError as exc:
        raise HTTPException(409, str(exc))
    frame = c.calcs.load_values(outcome.calc_id, body.instrument_id, body.interval)
    spec = c.registry.get(body.name)
    return {
        "calc_id": outcome.calc_id,
        "name": outcome.name,
        "version": outcome.version,
        "params": outcome.params,
        "outputs": list(spec.outputs),
        "points": _points(frame),
    }


@router.get("/{calc_id}/series", response_model=CalcSeriesOut)
def series(calc_id: str, instrument_id: int, interval: Interval = Interval.D1, start: Optional[datetime] = None,
           end: Optional[datetime] = None, c: Container = Depends(get_container)):
    """Read previously stored results, including older versions of a calculation."""
    definition = next((d for d in c.calcs.definitions() if d["calc_id"] == calc_id), None)
    if definition is None:
        raise HTTPException(404, "calculation not found")
    frame = c.calcs.load_values(calc_id, instrument_id, interval, start, end)
    return {
        "calc_id": calc_id,
        "name": definition["name"],
        "version": definition["version"],
        "params": definition["params"],
        "outputs": definition["outputs"],
        "points": _points(frame),
    }
