from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from markets.api.deps import get_container
from markets.api.schemas import DqAcceptIn, DqCheckIn
from markets.bootstrap import Container

router = APIRouter(prefix="/dq", tags=["data quality"])


def _instrument_ids(c: Container, refs: Optional[list[str]]) -> Optional[list[int]]:
    """Instrument ids or EXCHANGE:SYMBOL references (e.g. NSE:TCS-EQ)."""
    if refs is None:
        return None
    ids = []
    for ref in refs:
        if ref.isdigit():
            ids.append(int(ref))
            continue
        exchange, _, symbol = ref.partition(":")
        instrument = c.instruments.find(exchange, symbol)
        if instrument is None:
            raise HTTPException(404, f"unknown instrument {ref}")
        ids.append(instrument.instrument_id)
    return ids


@router.get("/issues")
def issues(status: Optional[str] = "open", check: Optional[str] = None, instrument: Optional[str] = None,
           limit: int = 1000, c: Container = Depends(get_container)) -> dict:
    """Issue counts per check and status, plus the issues matching the filters (status=all for every status)."""
    ids = _instrument_ids(c, [instrument] if instrument else None)
    return c.data_quality.report(None if status == "all" else status, check, ids[0] if ids else None, limit)


@router.post("/check")
def check(body: DqCheckIn, c: Container = Depends(get_container)) -> dict:
    """Run checks now (all, or some checks / instruments; `full` re-checks all history)."""
    try:
        return c.data_quality.run(body.full, body.checks, _instrument_ids(c, body.instruments))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/issues/{issue_id}/accept")
def accept(issue_id: str, body: DqAcceptIn, c: Container = Depends(get_container)) -> dict:
    """Mark an issue as known and fine (with a note why), so it stops showing as open."""
    try:
        if not c.data_quality.accept(issue_id, body.note):
            raise HTTPException(404, "issue not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"accepted": issue_id}
