from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from markets.core.models import Interval


class InstrumentOut(BaseModel):
    instrument_id: int
    exchange: str
    symbol: str
    name: Optional[str]
    instrument_type: Optional[str]
    lot_size: Optional[int]
    tick_size: Optional[float]
    expiry: Optional[date]
    strike: Optional[float]


class CandleOut(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleSeriesOut(BaseModel):
    instrument: InstrumentOut
    interval: Interval
    candles: list[CandleOut]


class IndicatorOut(BaseModel):
    name: str
    version: int
    outputs: list[str]
    params: dict[str, Any]
    description: str


class CalcRunIn(BaseModel):
    instrument_id: int
    interval: Interval = Interval.D1
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class CalcSeriesOut(BaseModel):
    calc_id: str
    name: str
    version: int
    params: dict[str, Any]
    outputs: list[str]
    points: list[dict[str, Any]]  # {"ts": ..., "<output>": value, ...}


class IngestIn(BaseModel):
    instrument_ids: list[int]
    interval: Interval = Interval.D1
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class IngestAccepted(BaseModel):
    queued: int


class ScanRunIn(BaseModel):
    filter: dict[str, Any] = Field(default_factory=lambda: {"type": "group", "match": "all", "items": []})
    universe: str = "nifty500"
    as_of: Optional[date] = None
    include_indices: bool = False
    industry: Optional[str] = None  # limit to one sector (NSE industry tag, or 'Unclassified')
    columns: list[dict[str, Any]] = Field(default_factory=list)  # extra operands to return, not filter on


class SavedScanIn(BaseModel):
    name: str
    definition: dict[str, Any]  # {"filter": ..., "universe": ..., "include_indices": ...}
