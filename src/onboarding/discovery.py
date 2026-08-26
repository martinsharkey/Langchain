"""Phase 1: discovery — run all indicators (and combinations) across sessions
and timeframes using VectorBT's native factory.

VectorBT decides the indicator universe (via ``get_pandas_ta_indicators`` /
``get_talib_indicators`` / ``get_ta_indicators`` + built-ins). We test every
single indicator first, then combine the top singles' signals (AND/OR) up to a
configurable depth and let the backtest results decide which combination wins.
"""

from __future__ import annotations

import itertools
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.onboarding.backtest import run_backtest
from src.onboarding.data import load_ohlcv
from src.onboarding.indicators import Indicator, all_indicators, run_indicator
from src.onboarding.metrics import ScoredResult, composite_score
from src.onboarding.sessions import all_session_keys, filter_session
from src.onboarding.signals import combine_signals, generate_signals
from src.onboarding.timeframes import TIMEFRAMES, timeframe_minutes

logger = logging.getLogger(__name__)


class Discovery:
    """Run indicator discovery for a symbol across sessions and timeframes."""

    def __init__(
        self,
        symbol: str,
        init_cash: float = 10_000.0,
        top_n: int = 10,
        combo_depth: int = 10,
        combo_modes: Tuple[str, ...] = ("and", "or"),
    ):
        self.symbol = symbol
        self.init_cash = init_cash
        self.top_n = top_n
        self.combo_depth = combo_depth
        self.combo_modes = combo_modes

    def discover(
        self,
        timeframes: Optional[List[str]] = None,
        sessions: Optional[List[str]] = None,
        bars: int = 5000,
    ) -> Dict[str, List[ScoredResult]]:
        """Discover top indicators per (timeframe, session).

        Returns a dict keyed by ``f"{timeframe}:{session}"`` mapping to a list
        of ScoredResult ranked by composite score (descending), capped at top_n.
        """
        timeframes = timeframes or TIMEFRAMES
        sessions = sessions or all_session_keys()

        results: Dict[str, List[ScoredResult]] = {}

        for timeframe in timeframes:
            try:
                df = load_ohlcv(self.symbol, timeframe, count=bars)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{self.symbol} {timeframe}: data load failed: {e}")
                continue

            if len(df) < 100:
                logger.warning(f"{self.symbol} {timeframe}: only {len(df)} bars")
                continue

            freq = f"{timeframe_minutes(timeframe)}min"

            for session in sessions:
                sdf = filter_session(df, session)
                if len(sdf) < 50:
                    logger.debug(f"{timeframe}:{session}: only {len(sdf)} bars, skip")
                    continue

                scored = self._discover_session(sdf, session, timeframe, freq)
                if scored:
                    results[f"{timeframe}:{session}"] = scored

        return results

    def _discover_session(
        self, df: pd.DataFrame, session: str, timeframe: str, freq: str
    ) -> List[ScoredResult]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]
        volume = df["volume"]

        indicators = all_indicators()

        # Phase 1a: single indicators.
        singles: List[ScoredResult] = []
        for ind in indicators:
            result = self._run_single(
                ind, close, high, low, open_, volume, freq,
                session, timeframe,
            )
            if result is not None:
                singles.append(result)

        singles.sort(key=lambda r: r.score, reverse=True)

        # Phase 1b: combine the top singles' signals (AND/OR) up to combo_depth.
        combos: List[ScoredResult] = self._run_combinations(
            singles, close, high, low, open_, volume, freq,
            session, timeframe,
        )

        all_results = singles + combos
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[: self.top_n]

    def _run_single(
        self,
        ind: Indicator,
        close, high, low, open_, volume,
        freq,
        session, timeframe,
    ) -> Optional[ScoredResult]:
        try:
            run = run_indicator(ind, close, high, low, open_, volume)
            entries, exits = generate_signals(run, ind.library, ind.name)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"{ind.library}:{ind.name} run failed: {e}")
            return None

        if entries.sum() < 2:
            return None

        result = run_backtest(close, entries, exits, init_cash=self.init_cash, freq=freq)
        if result is None:
            return None

        return ScoredResult(
            indicator=ind.name,
            library=ind.library,
            category="single",
            session=session,
            timeframe=timeframe,
            result=result,
            score=composite_score(result),
            combination=((ind.library, ind.name),),
        )

    def _run_combinations(
        self,
        singles: List[ScoredResult],
        close, high, low, open_, volume,
        freq,
        session, timeframe,
    ) -> List[ScoredResult]:
        """Combine the top singles' signals (AND/OR) up to combo_depth."""
        if not singles:
            return []

        # Take the top combo_depth singles as the combination pool.
        pool = singles[: self.combo_depth]
        combos: List[ScoredResult] = []

        # Pre-compute each pool indicator's signals.
        from src.onboarding.indicators import wrap

        pool_signals = []
        for s in pool:
            ind = wrap(s.indicator, s.library)
            try:
                run = run_indicator(ind, close, high, low, open_, volume)
                entries, exits = generate_signals(run, ind.library, ind.name)
                pool_signals.append((s, entries, exits))
            except Exception as e:  # noqa: BLE001
                logger.debug(f"combo signal {s.library}:{s.indicator} failed: {e}")

        # Pairs and triples (up to depth 3 for tractability; deeper is
        # configurable but combinatorial).
        max_combo = min(3, len(pool_signals))
        for r in range(2, max_combo + 1):
            for combo in itertools.combinations(pool_signals, r):
                for mode in self.combo_modes:
                    entries_list = [c[1] for c in combo]
                    exits_list = [c[2] for c in combo]
                    entries, exits = combine_signals(entries_list, exits_list, mode)
                    if entries.sum() < 2:
                        continue
                    result = run_backtest(
                        close, entries, exits, init_cash=self.init_cash, freq=freq,
                    )
                    if result is None:
                        continue
                    names = tuple((c[0].library, c[0].indicator) for c in combo)
                    combos.append(
                        ScoredResult(
                            indicator="+".join(n[1] for n in names),
                            library="combo",
                            category=mode,
                            session=session,
                            timeframe=timeframe,
                            result=result,
                            score=composite_score(result),
                            combination=names,
                        )
                    )

        return combos


def best_timeframe_per_session(
    discovery: Dict[str, List[ScoredResult]],
) -> Dict[str, Dict]:
    """Aggregate discovery results into a per-session best-timeframe view.

    For each session, pick the timeframe whose top candidate scored highest, and
    return that timeframe plus its ranked results.

    Returns a dict keyed by session, each value:
        {"timeframe": str, "results": [ScoredResult, ...]}
    """
    # Group buckets by session.
    by_session: Dict[str, List[tuple]] = {}
    for key, results in discovery.items():
        timeframe, session = key.split(":", 1)
        by_session.setdefault(session, []).append((timeframe, results))

    out: Dict[str, Dict] = {}
    for session, buckets in by_session.items():
        # Best timeframe = the one whose top result has the highest score.
        best_timeframe = None
        best_results = None
        best_score = -1.0
        for timeframe, results in buckets:
            if not results:
                continue
            top_score = results[0].score
            if top_score > best_score:
                best_score = top_score
                best_timeframe = timeframe
                best_results = results
        if best_timeframe is not None:
            out[session] = {"timeframe": best_timeframe, "results": best_results}

    return out


__all__ = ["Discovery", "best_timeframe_per_session"]
