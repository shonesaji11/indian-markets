from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from markets.api.deps import get_container
from markets.bootstrap import Container

router = APIRouter(tags=["movers"])

Cutoff = Query(None, gt=0, lt=1, description="list = probability >= cutoff (default: the movers_cutoff setting)")


@router.get("/movers")
def movers(as_of: Optional[date] = None, cutoff: Optional[float] = Cutoff, c: Container = Depends(get_container)) -> dict:
    """The big-movers list scored after the close of `as_of` (default: the latest scored day), with what each
    stock did on the next session once that bar exists. `scored` is false for a day with no list."""
    return c.movers.picks(as_of, cutoff)


@router.get("/movers/days")
def mover_days(cutoff: Optional[float] = Cutoff, c: Container = Depends(get_container)) -> list[dict]:
    """Every scored day, newest first, with its list size and hits at the cutoff."""
    return c.movers.days(cutoff)


@router.post("/jobs/movers")
def movers_job(since: Optional[date] = None, rebuild: bool = False, c: Container = Depends(get_container)) -> dict:
    """Score the latest session, or every session from `since`; days already scored are kept unless `rebuild`.
    Sends no message (the nightly update does). 422 for a day that can't be scored."""
    try:
        return c.movers.backfill(since, rebuild) if since else c.movers.score(rebuild=rebuild)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
