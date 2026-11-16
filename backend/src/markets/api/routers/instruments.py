from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import InstrumentOut
from markets.bootstrap import Container

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentOut])
def search(q: str = "", exchange: Optional[str] = None, instrument_type: Optional[str] = None, limit: int = 25,
           c: Container = Depends(get_container)):
    return [asdict(i) for i in c.instruments.search(q, exchange, instrument_type, min(limit, 200))]


@router.get("/{instrument_id}", response_model=InstrumentOut)
def get(instrument_id: int, c: Container = Depends(get_container)):
    instrument = c.instruments.get(instrument_id)
    if instrument is None:
        raise HTTPException(404, "instrument not found")
    return asdict(instrument)


@router.post("/sync")
def sync(c: Container = Depends(get_container)) -> dict:
    """Refresh the instrument master from the provider (Angel One: ~150k rows, takes a while)."""
    return {"instruments": c.ingestion.sync_instruments()}
