from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from markets.api.deps import get_container
from markets.bootstrap import Container

router = APIRouter(prefix="/live", tags=["live"])

MAX_IDS = 1000  # one stream connection's subscriptions


@router.get("/quotes")
def quotes(ids: list[int] = Query([]), c: Container = Depends(get_container)) -> dict:
    """Latest streamed quote of each instrument that has one, plus the feed's state. Asking for an
    instrument also streams it for the rest of the day. The UI polls this about once a second."""
    if len(ids) > MAX_IDS:
        raise HTTPException(422, f"at most {MAX_IDS} instruments")
    c.live.watch(ids)
    return {"status": c.live.status(), "quotes": c.live.quotes(ids)}
