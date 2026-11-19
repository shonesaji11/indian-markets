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


@router.post("/candles/{instrument_id}/refresh")
def refresh_candles(instrument_id: int, interval: Interval = Interval.D1, c: Container = Depends(get_container)) -> dict:
    """Download what's missing for one chart, now: from the last stored bar (or the interval's default history)
    up to now. Waits for it: ~2 s, longer while the nightly update is using the download allowance."""
    try:
        result = c.ingestion.ingest(instrument_id, interval)
    except KeyError as exc:  # unknown instrument, or one the provider has no token for
        raise HTTPException(404, str(exc).strip("'\""))
    if result.status != "ok":
        raise HTTPException(502, _plain_reason(result.error or ""))
    return {"rows": result.rows}


def _plain_reason(error: str) -> str:
    """A download error in plain words (the full error is in the log and in GET /ingest/runs)."""
    lowered = error.lower()
    if "exceeding access rate" in lowered:
        return "Angel One's download limit was hit; try again in a minute"
    if "login failed" in lowered or "credentials missing" in lowered:
        return "Angel One login failed"
    return "Angel One didn't return the bars"


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
