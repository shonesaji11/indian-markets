from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from markets.core.models import Interval
from markets.core.ports import CalcRepository, CandleRepository
from markets.engine.registry import IndicatorRegistry


@dataclass
class CalcOutcome:
    calc_id: str
    run_id: str
    name: str
    version: int
    params: dict[str, Any]
    rows: int


class CalcService:
    """Runs engine calculations over stored candles and persists versioned results."""

    def __init__(self, registry: IndicatorRegistry, candles: CandleRepository, calcs: CalcRepository):
        self.registry = registry
        self.candles = candles
        self.calcs = calcs

    def compute(self, name: str, instrument_id: int, interval: Interval,
                params: Optional[dict[str, Any]] = None) -> CalcOutcome:
        spec = self.registry.get(name)
        resolved = spec.resolve_params(params)
        calc_id = spec.calc_id(resolved)
        self.calcs.ensure_definition(calc_id, spec.name, spec.version, resolved, spec.outputs, spec.code_hash)

        watermark = self.candles.last_ingested_at(instrument_id, interval)
        run_id = self.calcs.start_run(calc_id, instrument_id, interval, watermark)
        try:
            # Full history every time: indicators need warm-up bars and this keeps runs reproducible.
            candles = self.candles.load(instrument_id, interval)
            values = spec.compute(candles, resolved)
            rows = self.calcs.write_values(run_id, calc_id, instrument_id, interval, values)
        except Exception as exc:
            self.calcs.finish_run(run_id, 0, "error", str(exc))
            raise
        self.calcs.finish_run(run_id, rows, "ok")
        return CalcOutcome(calc_id, run_id, spec.name, spec.version, resolved, rows)
