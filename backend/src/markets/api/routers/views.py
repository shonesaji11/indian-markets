from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends

from markets.api.deps import get_container
from markets.bootstrap import Container

router = APIRouter(prefix="/views", tags=["views"])


@router.get("/daily-stats")
def daily_stats(as_of: Optional[date] = None, instrument_id: Optional[int] = None, limit: int = 500,
                c: Container = Depends(get_container)) -> list[dict]:
    """v_daily_stats_v1. Pass `as_of` to see every instrument as it stood on that date."""
    cutoff = datetime.combine(as_of, time.max) if as_of else None
    rows = c.views.daily_stats(cutoff, instrument_id, min(limit, 5000))
    return [{k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()} for r in rows]
