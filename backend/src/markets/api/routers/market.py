from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from markets.api.deps import get_container
from markets.bootstrap import Container
from markets.universes import DEFAULT_UNIVERSE

router = APIRouter(tags=["market"])


@router.get("/market/overview")
def overview(as_of: Optional[date] = None, universe: str = DEFAULT_UNIVERSE, limit: int = 10,
             c: Container = Depends(get_container)) -> dict:
    """Landing page data: benchmarks, sectors, breadth and every scan, as of any date."""
    cutoff = datetime.combine(as_of, time.max) if as_of else None
    return c.overview.overview(universe, cutoff, min(limit, 50))


@router.get("/market/sector-breadth")
def sector_breadth(as_of: Optional[date] = None, universe: str = DEFAULT_UNIVERSE,
                   periods: list[int] = Query([10, 20]), c: Container = Depends(get_container)) -> dict:
    """Per sector: stocks priced and how many closed above each N-day SMA, on the latest session."""
    cutoff = datetime.combine(as_of, time.max) if as_of else None
    try:
        return c.breadth.sectors(universe, cutoff, periods)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/jobs/breadth")
def breadth_job(backfill: bool = False, c: Container = Depends(get_container)) -> dict:
    """Recompute stored sector breadth: the last 10 days, or all history with `backfill`."""
    return {"rows": c.breadth.backfill() if backfill else c.breadth.update()}


@router.get("/watchlists")
def watchlists(c: Container = Depends(get_container)) -> list[dict]:
    return c.watchlists.all()


@router.get("/watchlists/{watchlist_id}/members")
def members(watchlist_id: str, c: Container = Depends(get_container)) -> list[dict]:
    return [asdict(i) for i in (c.instruments.get(n) for n in c.watchlists.member_ids(watchlist_id)) if i]


@router.post("/jobs/daily-update")
def daily_update(sync_instruments: bool = True, c: Container = Depends(get_container)) -> dict:
    """Run the nightly job inside this process (used by the CLI when the server holds the DB).
    Blocks until finished: several minutes for a full universe."""
    try:
        return c.daily_update.run(sync_instruments=sync_instruments).to_dict()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
