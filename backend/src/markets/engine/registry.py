from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

import pandas as pd

IndicatorFunc = Callable[..., Any]


@dataclass(frozen=True)
class IndicatorSpec:
    """A registered calculation.

    Identity rules that make results reproducible:
      - `calc_id` = hash(name, version, resolved params). Same inputs, same id.
      - `code_hash` = hash of the function source. Storage refuses to reuse a calc_id
        whose code changed, which forces a version bump when the logic changes.
    """

    name: str
    version: int
    func: IndicatorFunc
    outputs: tuple[str, ...]
    defaults: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def code_hash(self) -> str:
        return hashlib.sha256(inspect.getsource(self.func).encode()).hexdigest()[:16]

    def resolve_params(self, overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        overrides = overrides or {}
        unknown = set(overrides) - set(self.defaults)
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}; expected {sorted(self.defaults)}")
        resolved = dict(self.defaults)
        for key, value in overrides.items():
            default = self.defaults[key]
            resolved[key] = type(default)(value) if default is not None else value
        return resolved

    def calc_id(self, params: dict[str, Any]) -> str:
        payload = json.dumps({"name": self.name, "version": self.version, "params": params}, sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:16]

    def compute(self, candles: pd.DataFrame, params: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        resolved = self.resolve_params(params)
        result = self.func(candles, **resolved)
        if isinstance(result, pd.Series):
            result = result.to_frame(self.outputs[0])
        missing = set(self.outputs) - set(result.columns)
        if missing:
            raise ValueError(f"{self.name} did not return outputs {sorted(missing)}")
        return result[list(self.outputs)].reindex(candles.index)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "outputs": list(self.outputs),
            "params": self.defaults,
            "description": self.description,
        }


class IndicatorRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, IndicatorSpec] = {}

    def register(self, spec: IndicatorSpec) -> IndicatorSpec:
        if spec.name in self._specs:
            raise ValueError(f"indicator '{spec.name}' already registered")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> IndicatorSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError(f"unknown indicator '{name}'; known: {sorted(self._specs)}") from None

    def all(self) -> list[IndicatorSpec]:
        return sorted(self._specs.values(), key=lambda s: s.name)


_default = IndicatorRegistry()


def indicator(name: str, version: int, outputs: Sequence[str], description: str = "",
              registry: Optional[IndicatorRegistry] = None) -> Callable[[IndicatorFunc], IndicatorFunc]:
    """Register a function `f(candles, **params)` as an indicator.

    Parameters and their defaults are read from the function signature, so the
    signature is the single source of truth for what an indicator accepts.
    """

    def wrap(func: IndicatorFunc) -> IndicatorFunc:
        params = list(inspect.signature(func).parameters.values())[1:]
        defaults = {p.name: p.default for p in params}
        if any(v is inspect.Parameter.empty for v in defaults.values()):
            raise TypeError(f"{name}: every parameter needs a default")
        (registry or _default).register(
            IndicatorSpec(name=name, version=version, func=func, outputs=tuple(outputs), defaults=defaults,
                          description=description)
        )
        return func

    return wrap


def default_registry() -> IndicatorRegistry:
    import markets.engine.indicators  # noqa: F401  (registers built-ins on import)

    return _default
