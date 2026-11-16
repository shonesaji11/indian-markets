"""Declarative watchlists synced by the nightly job. Edit this file to change what is tracked.

`index` lists are pulled from NSE's published constituents (and change when the index
rebalances); `members` lists are fixed EXCHANGE:SYMBOL references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class WatchlistSpec:
    watchlist_id: str
    name: str
    description: str = ""
    index: Optional[str] = None                    # NSE index slug, e.g. "nifty500"
    members: tuple[str, ...] = field(default_factory=tuple)


WATCHLISTS: tuple[WatchlistSpec, ...] = (
    WatchlistSpec("nifty500", "Nifty 500", "Broad market universe used for movers and breadth", index="nifty500"),
    WatchlistSpec("nifty50", "Nifty 50", "Large caps", index="nifty50"),
    WatchlistSpec(
        "benchmarks", "Benchmarks", "Headline indices",
        members=("NSE:Nifty 50", "BSE:SENSEX", "NSE:Nifty Bank", "NSE:NIFTY MIDCAP 100",
                 "NSE:NIFTY SMLCAP 100", "NSE:India VIX"),
    ),
    WatchlistSpec(
        "sectors", "Sector indices", "NSE sectoral indices",
        members=("NSE:Nifty Auto", "NSE:Nifty Bank", "NSE:Nifty Energy", "NSE:Nifty FMCG",
                 "NSE:Nifty Fin Service", "NSE:Nifty IT", "NSE:Nifty Media", "NSE:Nifty Metal",
                 "NSE:Nifty Pharma", "NSE:Nifty PSU Bank", "NSE:Nifty Pvt Bank", "NSE:Nifty Realty",
                 "NSE:Nifty Infra", "NSE:Nifty Consumption"),
    ),
)

DEFAULT_UNIVERSE = "nifty500"

# Sector breadth is stored daily for these universes and MA periods (others are computed on request).
BREADTH_UNIVERSES = ("nifty500", "nifty50", "all")
BREADTH_PERIODS = (10, 20, 50, 200)
