"""Big-movers watchlist: after each evening's update, score every Nifty Total Market stock with a frozen model
for the chance of a >= 4% close-vs-open move on the next session, store the scores, and send the list (stocks
at or above the cutoff) to Telegram once. The list says where the action may be, not which way: the research
found big movers split 50/50 up and down (research/movers/REPORT.md).

Model files live in src/markets/models/ (<version>.json + .meta.json, made by scripts/train_movers.py).
The next session is assumed to be the next weekday (there is no holiday calendar), which only matters for the
weekday and last-week/month features on the day before a holiday.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import xgboost as xgb

from markets.core.ports import Notifier
from markets.engine.movers import BIG_MOVE, FEATURE_COLUMNS, FEATURES_VERSION, HISTORY_BARS, build_features, next_weekday
from markets.storage.duckdb.repositories import (
    DuckInstrumentRepository,
    DuckMarketRepository,
    DuckMoverRepository,
    DuckWatchlistRepository,
)

log = logging.getLogger(__name__)

MODEL_VERSION = "co4_eod_v1"  # the model the nightly job scores with
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
UNIVERSE = "niftytotalmarket"
SESSIONS = ("NSE", "Nifty 50")  # market calendar and market features
VIX = ("NSE", "India VIX")
LISTED_SERIES = "-EQ"  # other series (BE: trade-to-trade, no intraday) still feed the market features
MIN_COVERAGE = 0.9  # share of members with a bar on as_of below which the run is flagged
MARKET_CLOSE = time(15, 30)  # today's daily bar isn't final before this
MESSAGE_MAX_STOCKS = 40


class MoverModel:
    """A trained booster plus its metadata; refuses a model trained on other features than the code makes."""

    def __init__(self, version: str, directory: Path = MODELS_DIR):
        meta = json.loads((directory / f"{version}.meta.json").read_text(encoding="utf-8"))
        if meta["features_version"] != FEATURES_VERSION or tuple(meta["features"]) != FEATURE_COLUMNS:
            raise ValueError(f"model {version} was trained on features v{meta['features_version']}, "
                             f"the code makes v{FEATURES_VERSION}: train a new model version")
        self.version = version
        self.train_end = date.fromisoformat(meta["train"][1])
        self._booster = xgb.Booster()
        self._booster.load_model(directory / f"{version}.json")

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self._booster.predict(xgb.DMatrix(features[list(FEATURE_COLUMNS)]))


class MoverService:
    def __init__(self, repo: DuckMoverRepository, market: DuckMarketRepository, watchlists: DuckWatchlistRepository,
                 instruments: DuckInstrumentRepository, notifier: Optional[Notifier], cutoff: float,
                 model: Optional[Any] = None, universe: str = UNIVERSE, clock: Callable[[], datetime] = datetime.now):
        self.repo = repo
        self.market = market
        self.watchlists = watchlists
        self.instruments = instruments
        self.notifier = notifier
        self.cutoff = cutoff
        self.universe = universe
        self._model = model
        self._clock = clock

    @property
    def model(self):
        if self._model is None:
            self._model = MoverModel(MODEL_VERSION)
        return self._model

    def _index_id(self, ref: tuple[str, str]) -> Optional[int]:
        found = self.instruments.find(*ref)
        return found.instrument_id if found else None

    def _session_id(self) -> int:
        session_id = self._index_id(SESSIONS)
        if session_id is None:
            raise ValueError(f"{SESSIONS[0]}:{SESSIONS[1]} is not in the instrument list")
        return session_id

    def score(self, as_of: Optional[date] = None, rebuild: bool = False) -> dict[str, Any]:
        """Score the stocks for the session after `as_of` (default: the Nifty's latest daily bar) and store it.
        A day already scored is skipped unless `rebuild`. ValueError: not a session, no members, a day the model
        was trained on, or today before the close."""
        model, now = self.model, self._clock()
        session_id, vix_id = self._session_id(), self._index_id(VIX)
        latest = self.market.recent_sessions([session_id], datetime.combine(as_of or now.date(), time.max), 1)
        if not latest or (as_of is not None and latest[0].date() != as_of):
            raise ValueError(f"no {SESSIONS[1]} bar on {as_of or 'any day'}: not a session")
        as_of = latest[0].date()
        if as_of <= model.train_end:
            raise ValueError(f"{as_of} is inside the model's training period (to {model.train_end})")
        if as_of == now.date() and now.time() < MARKET_CLOSE:
            raise ValueError("today's bars aren't final before the close")
        summary = {"model_version": model.version, "as_of": as_of.isoformat()}
        if not rebuild and self.repo.run(model.version, as_of):
            return {**summary, "skipped": True}

        members = self.watchlists.member_ids(self.universe)
        if not members:
            raise ValueError(f"watchlist {self.universe} has no members")
        ids = [*members, session_id, *([vix_id] if vix_id else [])]
        bars = self.market.daily_bars(ids, datetime.combine(as_of, time.max), HISTORY_BARS)
        stocks = bars[bars.instrument_id.isin(members)]
        with_bar = int(stocks.loc[pd.to_datetime(stocks.ts).dt.date == as_of, "instrument_id"].nunique())
        feats = build_features(stocks, bars[bars.instrument_id == session_id], bars[bars.instrument_id == vix_id],
                               target=next_weekday(pd.Timestamp(as_of)))
        symbols = self.instruments.symbols(feats.instrument_id.tolist())
        feats = feats[feats.instrument_id.map(lambda i: symbols.get(i, "").endswith(LISTED_SERIES))]
        scores = feats[["instrument_id", "atr_pct"]].assign(probability=model.predict(feats) if len(feats) else [])
        self.repo.store(model.version, as_of, scores, now, len(members), with_bar)

        warnings = []
        if with_bar < MIN_COVERAGE * len(members):
            warnings.append(f"only {with_bar} of {len(members)} stocks have a bar on {as_of}")
        vix = bars[bars.instrument_id == vix_id]
        if vix_id is None or not (pd.to_datetime(vix.ts).dt.date == as_of).any():
            warnings.append(f"no India VIX bar on {as_of}")
        log.info("big movers %s: %d stocks scored, %d at p >= %.2f", as_of, len(scores),
                 int((scores.probability >= self.cutoff).sum()), self.cutoff)
        return {**summary, "skipped": False, "universe": len(members), "with_bar": with_bar, "stocks": len(scores),
                "listed": int((scores.probability >= self.cutoff).sum()), "warnings": warnings}

    def backfill(self, since: date, rebuild: bool = False) -> dict[str, Any]:
        """Score every session from `since` (after the training period) to the latest, as the nightly job would
        have. No messages are sent."""
        session_id = self._session_id()
        sessions = self.market.recent_sessions([session_id], datetime.combine(self._clock().date(), time.max), 10_000)
        days = sorted(d.date() for d in sessions if d.date() >= since and d.date() > self.model.train_end)
        done = sum(not self.score(d, rebuild)["skipped"] for d in days)
        return {"model_version": self.model.version, "sessions": len(days), "scored": done}

    def nightly(self) -> dict[str, Any]:
        """The evening step: score the latest session, then send its list once."""
        summary = self.score()
        summary["notified"] = self.notify(date.fromisoformat(summary["as_of"]), summary.get("warnings", []))
        return summary

    def notify(self, as_of: date, warnings: Optional[list[str]] = None) -> Optional[str]:
        """Send the day's list unless it was sent (or Telegram was off) before; returns the new state."""
        run = self.repo.run(self.model.version, as_of)
        if run is None or run["notified"] in ("sent", "off"):
            return None
        if self.notifier is None:
            status, error = "off", None
        else:
            try:
                self.notifier.send(message(self.picks(as_of), warnings or []))
                status, error = "sent", None
            except Exception as exc:
                status, error = "failed", str(exc)
                log.warning("big movers message failed: %s", exc)
        self.repo.set_notified(self.model.version, as_of, status, error)
        return status

    def picks(self, as_of: Optional[date] = None, cutoff: Optional[float] = None) -> dict[str, Any]:
        """The list for `as_of` (default: the latest scored day) at `cutoff` (default: the setting), with what each
        stock did on the next session once that bar exists."""
        version, cutoff = self.model.version, self.cutoff if cutoff is None else cutoff
        as_of = as_of or self.repo.latest_as_of(version)
        out: dict[str, Any] = {"model_version": version, "cutoff": cutoff, "default_cutoff": self.cutoff,
                               "big_move": BIG_MOVE, "as_of": as_of.isoformat() if as_of else None,
                               "scored": False, "rows": []}
        run = self.repo.run(version, as_of) if as_of else None
        if run is None:
            return out
        cols = ["instrument_id", "symbol", "name", "probability", "atr_pct", "close", "prev_close", "next_session",
                "next_open", "next_close"]
        df = pd.DataFrame(self.repo.picks(version, as_of, self._session_id()), columns=cols)
        next_session = df.next_session.iloc[0] if len(df) else None
        prices = ["close", "prev_close", "next_open", "next_close"]
        df[prices] = df[prices].astype(float)
        df["change"] = df.close / df.prev_close - 1
        df["move"] = (df.next_close / df.next_open - 1).where(df.next_open > 0)
        big = df.move.abs() >= BIG_MOVE  # False where there is no next bar
        df["hit"] = big.astype(object).where(df.move.notna(), None)
        listed = df[df.probability >= cutoff]
        out.update({
            "scored": True, "universe": run["universe"], "with_bar": run["with_bar"], "stocks": run["stocks"],
            "next_session": next_session.isoformat() if next_session else None,
            "assumed_next_session": next_weekday(pd.Timestamp(as_of)).date().isoformat(),
            "top_probability": float(df.probability.max()) if len(df) else None,
            "listed": len(listed), "listed_with_bar": int(listed.move.notna().sum()),
            "hits": int(big[listed.index].sum()),
            "all_with_bar": int(df.move.notna().sum()), "all_hits": int(big.sum()),
            "rows": _json_rows(listed[["instrument_id", "symbol", "name", "probability", "atr_pct", "close",
                                       "change", "move", "hit"]]),
        })
        return out

    def days(self, cutoff: Optional[float] = None) -> list[dict[str, Any]]:
        """Every scored day (newest first) with its list size and hits at `cutoff`."""
        cutoff = self.cutoff if cutoff is None else cutoff
        rows = self.repo.days(self.model.version, self._session_id(), cutoff, BIG_MOVE)
        return [{**r, "as_of": r["as_of"].isoformat(),
                 "next_session": r["next_session"].isoformat() if r["next_session"] else None} for r in rows]


def _json_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Records with NaN as None and numpy scalars as Python ones."""
    return [{k: (None if pd.isna(v) else v.item() if hasattr(v, "item") else v) for k, v in r.items()}
            for r in df.to_dict("records")]


def message(picks: dict[str, Any], warnings: list[str]) -> str:
    """The evening Telegram text for one day's list."""
    day = datetime.fromisoformat(picks["as_of"]).strftime("%a %d %b")
    cut = f"p ≥ {picks['cutoff']:.2f}"
    rows = picks["rows"]
    if rows:
        names = [f"{r['symbol'].removesuffix(LISTED_SERIES)} {r['probability']:.0%}" for r in rows[:MESSAGE_MAX_STOCKS]]
        more = len(rows) - MESSAGE_MAX_STOCKS
        lines = [f"Big movers for the next session (after the close of {day}), {cut}: {len(rows)} stocks",
                 ", ".join(names) + (f" and {more} more" if more > 0 else "")]
    else:
        top = picks.get("top_probability")
        lines = [f"Big movers after the close of {day}: no stocks at {cut}"
                 + (f" (highest {top:.0%})" if top is not None else "")]
    lines += [f"Note: {w}" for w in warnings]
    return "\n".join(lines)
