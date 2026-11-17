from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import SavedScanIn, ScanPerformanceIn, ScanRunIn
from markets.bootstrap import Container

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("/fields")
def fields(c: Container = Depends(get_container)) -> list[dict]:
    """Snapshot fields a condition can compare (indicators come from /calcs/indicators)."""
    return c.screener.fields()


@router.post("/run")
def run(body: ScanRunIn, c: Container = Depends(get_container)) -> dict:
    """Evaluate a filter tree across a universe on its latest session up to `as_of`."""
    cutoff = datetime.combine(body.as_of, time.max) if body.as_of else None
    try:
        return c.screener.run(body.filter, body.universe, cutoff, body.include_indices, body.industry, body.columns)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/performance")
def performance(body: ScanPerformanceIn, c: Container = Depends(get_container)) -> dict:
    """Equal-weight performance of scan results bought at the `start` session's close, vs the benchmark."""
    end = datetime.combine(body.end, time.max) if body.end else None
    try:
        return c.screener.performance(body.instrument_ids, datetime.combine(body.start, time.min), end)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/saved")
def saved(c: Container = Depends(get_container)) -> list[dict]:
    return c.screener.saved_scans()


@router.post("/saved")
def save(body: SavedScanIn, c: Container = Depends(get_container)) -> dict:
    """Create a saved scan, or replace the one with the same name."""
    try:
        return {"scan_id": c.screener.save(body.name, body.definition)}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/saved/{scan_id}")
def delete(scan_id: str, c: Container = Depends(get_container)) -> dict:
    if not c.screener.delete(scan_id):
        raise HTTPException(404, "saved scan not found")
    return {"deleted": scan_id}
