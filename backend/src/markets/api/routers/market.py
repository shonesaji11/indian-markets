from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from markets.api.deps import get_container
from markets.api.schemas import WatchlistNameIn
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
                   periods: list[int] = Query([10, 20]), near_pct: float = 10.0, near_basis: str = "52w",
                   c: Container = Depends(get_container)) -> dict:
    """Per sector: stocks priced and how many closed above each N-day SMA, and how many closed within
    `near_pct`% of their 52-week (`near_basis=52w`) or all-time (`ath`) high, on the latest session."""
    cutoff = datetime.combine(as_of, time.max) if as_of else None
    try:
        return c.breadth.sectors(universe, cutoff, periods, near_pct, near_basis)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/market/sector-rotation")
def sector_rotation(as_of: Optional[date] = None, universe: str = DEFAULT_UNIVERSE, period: int = 50,
                    ago_n: int = 1, ago_unit: str = "w", min_stocks: int = 5, rank_by: str = "ma",
                    near_pct: float = 10.0, near_basis: str = "52w",
                    c: Container = Depends(get_container)) -> dict:
    """Per sector: average rank by share of stocks above the `period` SMA (`rank_by=ma`) or within
    `near_pct`% of their high (`rank_by=near_high`) over the last 5 sessions vs the 5 sessions ending
    `ago_n` days/weeks/months earlier."""
    cutoff = datetime.combine(as_of, time.max) if as_of else None
    try:
        return c.breadth.rotation(universe, cutoff, period, {"n": ago_n, "unit": ago_unit}, min_stocks,
                                  rank_by, near_pct, near_basis)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/jobs/repair")
def repair_job(c: Container = Depends(get_container)) -> dict:
    """Run the data repair step now, then bring derived data up to date and re-check data quality
    (the nightly job's steps after downloading)."""
    try:
        return c.daily_update.repair_now()
    except RuntimeError as exc:  # the nightly update is running
        raise HTTPException(409, str(exc))


@router.post("/jobs/highs")
def highs_job(rebuild: bool = False, c: Container = Depends(get_container)) -> dict:
    """Bring the all-time-high cache (daily_ath) up to date, or recompute it all with `rebuild`."""
    return {"rows": c.ath.refresh(full=rebuild)}


@router.post("/jobs/breadth")
def breadth_job(backfill: bool = False, c: Container = Depends(get_container)) -> dict:
    """Recompute stored sector breadth: the last 10 days, or all history with `backfill`."""
    return {"rows": c.breadth.backfill() if backfill else c.breadth.update()}


@router.get("/watchlists")
def watchlists(c: Container = Depends(get_container)) -> list[dict]:
    return c.watchlists.all()


@router.get("/watchlists/mine")
def my_watchlists(c: Container = Depends(get_container)) -> list[dict]:
    """Your own lists by name, each with `member_ids` in the order added."""
    return c.watchlists.manual_lists()


@router.post("/watchlists/mine")
def create_watchlist(body: WatchlistNameIn, c: Container = Depends(get_container)) -> dict:
    try:
        return c.watchlists.create_manual(body.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.patch("/watchlists/mine/{watchlist_id}")
def rename_watchlist(watchlist_id: str, body: WatchlistNameIn, c: Container = Depends(get_container)) -> dict:
    try:
        c.watchlists.rename_manual(watchlist_id, body.name)
    except KeyError:
        raise HTTPException(404, "watchlist not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"renamed": watchlist_id}


@router.delete("/watchlists/mine/{watchlist_id}")
def delete_watchlist(watchlist_id: str, c: Container = Depends(get_container)) -> dict:
    try:
        c.watchlists.delete_manual(watchlist_id)
    except KeyError:
        raise HTTPException(404, "watchlist not found")
    return {"deleted": watchlist_id}


@router.put("/watchlists/mine/{watchlist_id}/members/{instrument_id}")
def add_to_watchlist(watchlist_id: str, instrument_id: int, c: Container = Depends(get_container)) -> dict:
    """Add a stock at the end of the list; adding one that's already there changes nothing."""
    try:
        return {"added": c.watchlists.add_member(watchlist_id, instrument_id)}
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))


@router.delete("/watchlists/mine/{watchlist_id}/members/{instrument_id}")
def remove_from_watchlist(watchlist_id: str, instrument_id: int, c: Container = Depends(get_container)) -> dict:
    try:
        return {"removed": c.watchlists.remove_member(watchlist_id, instrument_id)}
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))


@router.get("/watchlists/mine/{watchlist_id}/quotes")
def watchlist_quotes(watchlist_id: str, c: Container = Depends(get_container)) -> list[dict]:
    """The list's stocks in the order added, each with its last stored daily close and day change
    (`ts` = that bar's date; null when nothing is stored yet)."""
    wl = next((w for w in c.watchlists.manual_lists() if w["watchlist_id"] == watchlist_id), None)
    if wl is None:
        raise HTTPException(404, "watchlist not found")
    quotes = c.market.latest_quotes(wl["member_ids"])
    empty = {"ts": None, "close": None, "pct_change": None}
    return [
        {"instrument_id": i.instrument_id, "exchange": i.exchange, "symbol": i.symbol, "name": i.name,
         "instrument_type": i.instrument_type, **quotes.get(i.instrument_id, empty)}
        for i in (c.instruments.get(n) for n in wl["member_ids"]) if i
    ]


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
