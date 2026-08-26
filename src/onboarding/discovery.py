"""Phase 1: discovery — run all indicators across sessions and timeframes using
VectorBT's native vectorized engine.

Uses VectorBT's native ``range_split`` (via ``split_sessions_native``) to split
price into per-session ranges (one column per session occurrence), then runs
indicators across ALL occurrences at once via VectorBT's vectorized ``.run()`` and
``Portfolio.from_signals()``. This replaces per-session looping with VectorBT's
native broadcasting.

Native flow:
    price_per_session = split_sessions_native(df, session, freq)
    rsi = vbt.pandas_ta('RSI').run(price_per_session, length=14)
    entries = rsi.rsi.vbt.below(30)
    exits = rsi.rsi.vbt.above(70)
    pf = vbt.Portfolio.from_signals(price_per_session, entries, exits, freq=freq)
    pf.stats()  # native stats across all session occurrences
"""

from __future__ import annotations

import itertools
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.onboarding.data import load_ohlcv
from src.onboarding.indicators import Indicator, all_indicators
from src.onboarding.metrics import ScoredResult, composite_score
from src.onboarding.sessions import all_session_keys, split_sessions_native
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
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        preloaded: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> Dict[str, List[ScoredResult]]:
        """Discover top indicators per (timeframe, session).

        Returns a dict keyed by ``f"{timeframe}:{session}"`` mapping to a list
        of ScoredResult ranked by composite score (descending), capped at top_n.

        If ``preloaded`` is provided (dict mapping timeframe -> DataFrame), uses
        that data instead of loading from MT5. This is the preferred path for
        date-range queries.
        """
        timeframes = timeframes or TIMEFRAMES
        sessions = sessions or all_session_keys()

        results: Dict[str, List[ScoredResult]] = {}

        for timeframe in timeframes:
            try:
                if preloaded is not None and timeframe in preloaded:
                    df = preloaded[timeframe]
                else:
                    df = load_ohlcv(self.symbol, timeframe, count=bars)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{self.symbol} {timeframe}: data load failed: {e}")
                continue

            if len(df) < 100:
                logger.warning(f"{self.symbol} {timeframe}: only {len(df)} bars")
                continue

            freq = f"{timeframe_minutes(timeframe)}min"

            for session in sessions:
                # Native VectorBT session splitting: dict of OHLCV DataFrames,
                # each with one column per session occurrence.
                ohlcv = split_sessions_native(df, session, freq=freq)
                if ohlcv is None or "close" not in ohlcv or ohlcv["close"].shape[1] == 0:
                    logger.debug(f"{timeframe}:{session}: no session occurrences found")
                    continue

                scored = self._discover_session(ohlcv, session, timeframe, freq)
                if scored:
                    results[f"{timeframe}:{session}"] = scored

        return results

    def _discover_session(
        self, ohlcv: Dict[str, pd.DataFrame], session: str, timeframe: str, freq: str
    ) -> List[ScoredResult]:
        """Run discovery on session bars.

        Concatenates all session-occurrence columns into a single continuous
        series (dropping NaN padding) so indicators have enough bars to generate
        signals. Runs each indicator natively on the concatenated series.
        """
        indicators = all_indicators()

        # Concatenate all occurrence columns into a single continuous series.
        close = self._concat_session_columns(ohlcv["close"])
        if len(close) < 50:
            return []
        high = self._concat_session_columns(ohlcv["high"])
        low = self._concat_session_columns(ohlcv["low"])
        open_ = self._concat_session_columns(ohlcv["open"])
        volume = self._concat_session_columns(ohlcv["volume"])

        # Phase 1a: single indicators — run natively on concatenated series.
        singles: List[ScoredResult] = []
        for ind in indicators:
            result = self._run_single(ind, close, high, low, open_, volume, freq, session, timeframe)
            if result is not None:
                singles.append(result)

        singles.sort(key=lambda r: r.score, reverse=True)

        # Phase 1b: combine the top singles' signals (AND/OR) up to combo_depth.
        combos: List[ScoredResult] = self._run_combinations(
            singles, close, high, low, open_, volume, freq, session, timeframe,
        )

        all_results = singles + combos
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[: self.top_n]

    @staticmethod
    def _concat_session_columns(df: pd.DataFrame) -> pd.Series:
        """Concatenate per-session-occurrence columns into a contiguous series.

        Each column in the input represents one session occurrence (e.g. one day's
        London session). This concatenates them end-to-end (dropping NaN padding)
        to produce a contiguous price series suitable for indicator computation.
        """
        parts = [df.iloc[:, i].dropna() for i in range(df.shape[1])]
        parts = [p for p in parts if len(p) > 0]
        if not parts:
            return pd.Series(dtype=float)
        return pd.concat(parts)

    def _run_single(
        self,
        ind: Indicator,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        open_: pd.Series,
        volume: pd.Series,
        freq: str,
        session: str,
        timeframe: str,
    ) -> Optional[ScoredResult]:
        """Run a single indicator natively on the concatenated session series."""
        try:
            inputs = {}
            for name in ind.cls.input_names:
                if name == "close":
                    inputs["close"] = close
                elif name == "high":
                    inputs["high"] = high
                elif name == "low":
                    inputs["low"] = low
                elif name == "open":
                    inputs["open"] = open_
                elif name == "volume":
                    inputs["volume"] = volume
            run = ind.cls.run(**inputs, **ind.kwargs)
            entries, exits = generate_signals(run, ind.library, ind.name)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"{ind.library}:{ind.name} run failed: {e}")
            return None

        if entries.sum() < 2:
            return None

        # Native VectorBT portfolio backtest on the concatenated series.
        try:
            import vectorbt as vbt
            pf = vbt.Portfolio.from_signals(
                close, entries, exits,
                init_cash=self.init_cash, freq=freq,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"{ind.library}:{ind.name} backtest failed: {e}")
            return None

        if pf.trades.count() < 1:
            return None

        from src.onboarding.backtest import BacktestResult
        result = BacktestResult(
            trades=int(pf.trades.count()),
            win_rate=float(pf.trades.win_rate() or 0.0),
            profit_factor=float(pf.trades.profit_factor() or 0.0),
            total_return=float(pf.total_return() or 0.0),
            max_drawdown=float(pf.max_drawdown() or 0.0),
            sharpe=float(pf.sharpe_ratio() or 0.0),
            fill_mode="bar",
            stats={},
        )

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
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        open_: pd.Series,
        volume: pd.Series,
        freq: str,
        session: str,
        timeframe: str,
    ) -> List[ScoredResult]:
        """Combine the top singles' signals (AND/OR) up to combo_depth."""
        if not singles:
            return []

        pool = singles[: self.combo_depth]
        combos: List[ScoredResult] = []

        from src.onboarding.indicators import wrap

        # Pre-compute signals for each pool indicator.
        pool_signals = []
        for s in pool:
            ind = wrap(s.indicator, s.library)
            try:
                inputs = {}
                for name in ind.cls.input_names:
                    if name == "close":
                        inputs["close"] = close
                    elif name == "high":
                        inputs["high"] = high
                    elif name == "low":
                        inputs["low"] = low
                    elif name == "open":
                        inputs["open"] = open_
                    elif name == "volume":
                        inputs["volume"] = volume
                run = ind.cls.run(**inputs, **ind.kwargs)
                e, x = generate_signals(run, ind.library, ind.name)
                pool_signals.append((s, e, x))
            except Exception as e:  # noqa: BLE001
                logger.debug(f"combo signal {s.library}:{s.indicator} failed: {e}")

        max_combo = min(3, len(pool_signals))
        for r in range(2, max_combo + 1):
            for combo in itertools.combinations(pool_signals, r):
                for mode in self.combo_modes:
                    entries_list = [c[1] for c in combo]
                    exits_list = [c[2] for c in combo]
                    entries, exits = combine_signals(entries_list, exits_list, mode)
                    if entries.sum() < 2:
                        continue
                    try:
                        import vectorbt as vbt
                        pf = vbt.Portfolio.from_signals(
                            close, entries, exits,
                            init_cash=self.init_cash, freq=freq,
                        )
                    except Exception:  # noqa: BLE001
                        continue
                    if pf.trades.count() < 1:
                        continue

                    from src.onboarding.backtest import BacktestResult
                    result = BacktestResult(
                        trades=int(pf.trades.count()),
                        win_rate=float(pf.trades.win_rate() or 0.0),
                        profit_factor=float(pf.trades.profit_factor() or 0.0),
                        total_return=float(pf.total_return() or 0.0),
                        max_drawdown=float(pf.max_drawdown() or 0.0),
                        sharpe=float(pf.sharpe_ratio() or 0.0),
                        fill_mode="bar",
                        stats={},
                    )
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
        combos: List[ScoredResult] = []

        from src.onboarding.indicators import wrap

        # Pre-compute per-occurrence signals for each pool indicator.
        pool_signals = []
        for s in pool:
            ind = wrap(s.indicator, s.library)
            occurrence_signals = []  # list of (entries, exits) per occurrence
            close_cols = ohlcv["close"]
            for col_idx in range(close_cols.shape[1]):
                col_data = {k: v.iloc[:, col_idx].dropna() for k, v in ohlcv.items()}
                if len(col_data.get("close", [])) < 50:
                    occurrence_signals.append(None)
                    continue
                try:
                    inputs = {k: col_data[k] for k in ind.cls.input_names if k in col_data}
                    run = ind.cls.run(**inputs, **ind.kwargs)
                    e, x = generate_signals(run, ind.library, ind.name)
                    occurrence_signals.append((e, x))
                except Exception:  # noqa: BLE001
                    occurrence_signals.append(None)
            pool_signals.append((s, occurrence_signals))

        max_combo = min(3, len(pool_signals))
        for r in range(2, max_combo + 1):
            for combo in itertools.combinations(pool_signals, r):
                for mode in self.combo_modes:
                    # Combine signals per occurrence.
                    close_cols = ohlcv["close"]
                    n_cols = close_cols.shape[1]
                    all_trades: List[int] = []
                    all_win_rates: List[float] = []
                    all_pf: List[float] = []
                    all_returns: List[float] = []
                    all_dd: List[float] = []
                    all_sharpe: List[float] = []

                    for col_idx in range(n_cols):
                        entries_list = []
                        exits_list = []
                        valid = True
                        for s, occ_signals in combo:
                            if occ_signals is None or occ_signals[col_idx] is None:
                                valid = False
                                break
                            e, x = occ_signals[col_idx]
                            entries_list.append(e)
                            exits_list.append(x)
                        if not valid:
                            continue

                        entries, exits = combine_signals(entries_list, exits_list, mode)
                        if entries.sum() < 2:
                            continue

                        col_data = {k: v.iloc[:, col_idx].dropna() for k, v in ohlcv.items()}
                        try:
                            import vectorbt as vbt
                            pf = vbt.Portfolio.from_signals(
                                col_data["close"], entries, exits,
                                init_cash=self.init_cash, freq=freq,
                            )
                        except Exception:  # noqa: BLE001
                            continue

                        if pf.trades.count() < 1:
                            continue

                        all_trades.append(int(pf.trades.count()))
                        all_win_rates.append(float(pf.trades.win_rate() or 0.0))
                        pf_val = pf.trades.profit_factor()
                        all_pf.append(float(pf_val) if np.isfinite(pf_val) else 0.0)
                        all_returns.append(float(pf.total_return() or 0.0))
                        all_dd.append(float(pf.max_drawdown() or 0.0))
                        all_sharpe.append(float(pf.sharpe_ratio() or 0.0))

                    if not all_trades:
                        continue

                    n = len(all_trades)
                    from src.onboarding.backtest import BacktestResult
                    result = BacktestResult(
                        trades=int(np.sum(all_trades)),
                        win_rate=float(np.mean(all_win_rates)),
                        profit_factor=float(np.mean(all_pf)),
                        total_return=float(np.mean(all_returns)),
                        max_drawdown=float(np.mean(all_dd)),
                        sharpe=float(np.mean(all_sharpe)),
                        fill_mode="bar",
                        stats={},
                    )

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


def _agg(value):
    """Aggregate a native VectorBT result (which may be a Series across columns) to a scalar."""
    if isinstance(value, pd.Series):
        # For count-like metrics, sum across columns; for ratios, use mean.
        if value.name and "count" in str(value.name).lower():
            return value.sum()
        return value.mean()
    return value


def _stats_to_dict(stats) -> Dict:
    """Convert native pf.stats() Series to a JSON-safe dict."""
    out: Dict = {}
    try:
        for k, v in stats.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[str(k)] = v if np.isfinite(v) else str(v)
            else:
                out[str(k)] = str(v)
    except Exception:
        pass
    return out


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
