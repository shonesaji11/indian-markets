from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import CandleSeriesOut, IngestAccepted, IngestIn
from markets.bootstrap import Container
from markets.core.models import Interval

router = APIRouter(tags=["data"])


@router.get("/candles/{instrument_id}", response_model=CandleSeriesOut)
def candles(instrument_id: int, interval: Interval = Interval.D1, start: Optional[datetime] = None,
            end: Optional[datetime] = None, c: Container = Depends(get_container)):
    instrument = c.instruments.get(instrument_id)
    if instrument is None:
        raise HTTPException(404, "instrument not found")
    frame = c.candles.load(instrument_id, interval, start, end)
    return {
        "instrument": asdict(instrument),
        "interval": interval,
        "candles": frame.reset_index().to_dict("records"),
    }


@router.get("/coverage")
def coverage(c: Container = Depends(get_container)) -> list[dict]:
    """What is stored: one row per instrument and interval."""
    return c.candles.coverage()


@router.post("/ingest", response_model=IngestAccepted, status_code=202)
def ingest(body: IngestIn, background: BackgroundTasks, c: Container = Depends(get_container)):
    """Queue candle fetches. Progress shows up in GET /api/ingest/runs."""

    def run() -> None:
        for instrument_id in body.instrument_ids:
            c.ingestion.ingest(instrument_id, body.interval, body.start, body.end)

    background.add_task(run)
    return {"queued": len(body.instrument_ids)}


@router.get("/ingest/runs")
def ingest_runs(limit: int = 50, c: Container = Depends(get_container)) -> list[dict]:
    return c.ingestion_log.recent(limit)
