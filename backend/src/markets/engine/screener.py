"""Custom scans: a filter tree of AND/OR groups and conditions, evaluated across a universe.

The tree is plain JSON (it comes from the UI and is stored in saved_scans):

    group     {"type": "group", "match": "all" | "any", "items": [group | condition, ...]}
    condition {"type": "condition", "left": operand, "op": OP, "right": operand | value}
    operand   {"type": "field", "field": "close"}
              {"type": "indicator", "name": "rsi", "params": {"period": 14}, "output": "rsi"}
              either may add "ago": {"n": 1, "unit": "w"}   # value N sessions before the scan day
    value     {"type": "value", "value": 2.5}      # percent fields take percentages: 2.5 = 2.5%

Evaluation is vectorized: every operand resolves to two Series indexed by instrument_id (its value on
its session and the session before, the latter only needed for crossovers), and conditions combine
with & and |. Missing values never match: too little history, or no bar on the session asked for,
leaves the instrument out rather than computing something else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

import pandas as pd

from markets.engine.registry import IndicatorRegistry, IndicatorSpec


@dataclass(frozen=True)
class ScanField:
    name: str
    label: str
    percent: bool = False  # stored as a fraction (0.025); entered and shown as a percentage


# Columns of daily_signals_v1 a condition can use. Scans run on daily (1d) bars only.
TIMEFRAME = "1d"
FIELDS: dict[str, ScanField] = {f.name: f for f in (
    ScanField("open", "Open"),
    ScanField("high", "High"),
    ScanField("low", "Low"),
    ScanField("close", "Close"),
    ScanField("prev_close", "Prev close"),
    ScanField("change", "Change"),
    ScanField("pct_change", "Change %", percent=True),
    ScanField("gap_pct", "Gap %", percent=True),
    ScanField("volume", "Volume"),
    # Average / relative volume are indicators (volume_avg, relative_volume) so the lookback is a parameter.
    ScanField("high_52w", "52w high"),
    ScanField("low_52w", "52w low"),
    ScanField("from_high_52w", "From 52w high %", percent=True),
)}

OPERATORS = ("gt", "gte", "lt", "lte", "crosses_above", "crosses_below")
_COMPARE: dict[str, Callable[[pd.Series, pd.Series], pd.Series]] = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}

Values = tuple[pd.Series, pd.Series]  # (value, session before), both indexed by instrument_id

# "ago" offsets count trading sessions (bars on the market calendar), not calendar days.
AGO_UNITS = {"d": 1, "w": 5, "m": 21}
MAX_AGO_BARS = 252


def bars_ago(op: dict[str, Any]) -> int:
    """Sessions before the scan day an operand reads (0 = the scan day)."""
    ago = op.get("ago") or {}
    return int(ago.get("n") or 0) * AGO_UNITS.get(ago.get("unit", "d"), 1)


def _ago_suffix(op: dict[str, Any]) -> str:
    ago = op.get("ago") or {}
    return f"{ago['n']}{ago['unit']}" if bars_ago(op) else ""


def operand_key(op: dict[str, Any]) -> str:
    """Stable, readable id for an operand, also used as its result column: close, rsi(14), macd.signal(12,26,9)."""
    suffix = f"@{_ago_suffix(op)}" if bars_ago(op) else ""
    if op.get("type") == "field":
        return op["field"] + suffix
    name, output = op["name"], op.get("output") or op["name"]
    head = name if output == name else f"{name}.{output}"
    params = op.get("params") or {}
    return (f"{head}({','.join(str(v) for v in params.values())})" if params else head) + suffix


def operand_label(op: dict[str, Any]) -> str:
    """Display name: field label, or e.g. `SMA 20`, `ADR% 20`, `MACD signal 12,26,9` (text params omitted),
    plus ` · 1w ago` for an offset."""
    suffix = f" · {_ago_suffix(op)} ago" if bars_ago(op) else ""
    if op.get("type") == "field":
        return FIELDS[op["field"]].label + suffix
    name, output = op["name"], op.get("output") or op["name"]
    head = name.replace("_pct", "%").replace("_", " ").upper() + ("" if output == name else f" {output}")
    numbers = [str(v) for v in (op.get("params") or {}).values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return (f"{head} {','.join(numbers)}" if numbers else head) + suffix


def validate(node: dict[str, Any], registry: IndicatorRegistry) -> None:
    """Raise ValueError with a readable message for anything malformed."""
    kind = node.get("type")
    if kind == "group":
        if node.get("match") not in ("all", "any"):
            raise ValueError("group match must be 'all' or 'any'")
        for item in node.get("items", []):
            validate(item, registry)
    elif kind == "condition":
        if node.get("op") not in OPERATORS:
            raise ValueError(f"unknown operator {node.get('op')!r}; expected one of {OPERATORS}")
        _validate_operand(node.get("left") or {}, registry)
        right = node.get("right") or {}
        if right.get("type") == "value":
            if not isinstance(right.get("value"), (int, float)) or isinstance(right.get("value"), bool):
                raise ValueError("comparison value must be a number")
        else:
            _validate_operand(right, registry)
    else:
        raise ValueError(f"unknown node type {kind!r}")


def _validate_operand(op: dict[str, Any], registry: IndicatorRegistry) -> None:
    ago = op.get("ago")
    if ago is not None:
        n = ago.get("n") if isinstance(ago, dict) else None
        if (not isinstance(n, int) or isinstance(n, bool) or n < 0 or ago.get("unit") not in AGO_UNITS
                or n * AGO_UNITS[ago["unit"]] > MAX_AGO_BARS):
            raise ValueError(f"ago must be a whole number of d/w/m up to {MAX_AGO_BARS} sessions (12m)")
    if op.get("type") == "field":
        if op.get("field") not in FIELDS:
            raise ValueError(f"unknown field {op.get('field')!r}")
    elif op.get("type") == "indicator":
        try:
            spec = registry.get(op.get("name", ""))
        except KeyError as exc:
            raise ValueError(exc.args[0]) from None
        spec.resolve_params(op.get("params"))
        if (op.get("output") or spec.name) not in spec.outputs:
            raise ValueError(f"{spec.name} has no output {op.get('output')!r}; expected {list(spec.outputs)}")
    else:
        raise ValueError(f"unknown operand type {op.get('type')!r}")


def iter_operands(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if node["type"] == "group":
        for item in node.get("items", []):
            yield from iter_operands(item)
    else:
        yield node["left"]
        if node["right"]["type"] != "value":
            yield node["right"]


def uses_crossovers(node: dict[str, Any]) -> bool:
    if node["type"] == "group":
        return any(uses_crossovers(i) for i in node.get("items", []))
    return node["op"].startswith("crosses")


def evaluate(node: dict[str, Any], values: dict[str, Values], index: pd.Index) -> pd.Series:
    """Boolean Series over `index` (instrument ids). An empty group matches everything."""
    if node["type"] == "group":
        items = node.get("items", [])
        if not items:
            return pd.Series(True, index=index)
        masks = [evaluate(i, values, index) for i in items]
        out = masks[0]
        for m in masks[1:]:
            out = (out & m) if node["match"] == "all" else (out | m)
        return out

    left_now, left_prev = values[operand_key(node["left"])]
    right = node["right"]
    if right["type"] == "value":
        field = FIELDS.get(node["left"].get("field", ""))
        number = right["value"] / 100 if field and field.percent else right["value"]
        right_now = right_prev = pd.Series(float(number), index=index)
    else:
        right_now, right_prev = values[operand_key(right)]

    op = node["op"]
    if op == "crosses_above":
        mask = (left_now > right_now) & (left_prev <= right_prev)
    elif op == "crosses_below":
        mask = (left_now < right_now) & (left_prev >= right_prev)
    else:
        mask = _COMPARE[op](left_now, right_now)
    return mask.reindex(index).fillna(False).astype(bool)  # NaN comparisons are already False


def lookback_bars(spec: IndicatorSpec, params: dict[str, Any]) -> int:
    """Bars to load so recursive indicators (EMA, RSI) have converged: 3x the largest window."""
    windows = [v for v in spec.resolve_params(params).values() if isinstance(v, int) and not isinstance(v, bool)]
    return max([60] + [3 * w + 2 for w in windows])


def indicator_frame(spec: IndicatorSpec, params: dict[str, Any], output: str, bars: pd.DataFrame) -> pd.DataFrame:
    """One indicator output for every instrument in `bars` (long format: instrument_id, ts, open, high,
    low, close, volume), as a wide frame: rows = ts, columns = instrument_id. Instruments with too little
    history get NaN (no shorter window is substituted)."""
    resolved = spec.resolve_params(params)
    series = {iid: spec.compute(g.set_index("ts"), resolved)[output] for iid, g in bars.groupby("instrument_id", sort=False)}
    return pd.DataFrame(series).sort_index() if series else pd.DataFrame()
