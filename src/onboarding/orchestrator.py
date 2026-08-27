"""Onboarding orchestrator — runs VectorBT discovery across sessions/timeframes
and writes progress markers + results for the dashboard to consume.

This is the single entry point for the onboarding wizard. It:
1. Loads OHLCV for the selected date range (native MT5 copy_rates_range).
2. For each (timeframe, session) combination, runs VectorBT discovery natively.
3. Writes a progress marker after each combination completes.
4. Accumulates results in a live results file.
5. Writes the final raw JSON + Markdown report.

All backtesting uses VectorBT's native ``vbt.Portfolio.from_signals()``.
All metrics come from ``pf.stats()``. No hand-rolled backtest loops.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.onboarding.data import load_ohlcv_range
from src.onboarding.discovery import Discovery
from src.onboarding.sessions import all_session_keys, get_session

logger = logging.getLogger(__name__)

# £100 to £100k vision: fixed start balance for every backtest.
INIT_CASH = 100.0


class OnboardingOrchestrator:
    """Run VectorBT onboarding for a symbol across sessions and timeframes."""

    def __init__(
        self,
        symbol: str,
        sessions: List[str],
        timeframes: List[str],
        start_date: datetime,
        end_date: datetime,
        output_dir: Optional[Path] = None,
        top_n: int = 10,
    ):
        self.symbol = symbol
        self.sessions = sessions
        self.timeframes = timeframes
        self.start_date = start_date
        self.end_date = end_date
        self.top_n = top_n

        self.output_dir = output_dir or Path("tests/onboarding") / symbol
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.progress_path = self.output_dir / "progress.jsonl"
        self.results_path = self.output_dir / "results_live.json"
        self.activity_path = self.output_dir / "activity.jsonl"

        # Clear stale files from previous runs.
        for p in (self.progress_path, self.results_path, self.activity_path):
            if p.exists():
                p.unlink()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _write_progress(self, marker: Dict):
        """Append a progress marker (JSON line)."""
        with open(self.progress_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(marker, default=str) + "\n")

    def _write_activity(self, activity: Dict):
        """Append a per-indicator activity marker (JSON line)."""
        with open(self.activity_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(activity, default=str) + "\n")

    def _write_results(self, results: List[Dict]):
        """Write the accumulated results file."""
        with open(self.results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

    def estimate_runtime_seconds(self) -> float:
        """Estimate total test time from the number of combinations.

        Calibrated: ~0.05s per indicator per session occurrence (VectorBT native).
        """
        n_indicators = 352  # native VectorBT enumeration
        n_sessions = len(self.sessions)
        n_timeframes = len(self.timeframes)
        # Rough: each (session, tf) tests all indicators; occurrences vary by session.
        # Use a conservative average of 5 occurrences per session.
        avg_occurrences = 5
        total_combinations = n_sessions * n_timeframes * n_indicators * avg_occurrences
        return total_combinations * 0.05  # seconds

    def run(self):
        """Run the full onboarding pipeline. Call from a background thread."""
        start_time = time.time()
        self._write_progress({
            "type": "start",
            "symbol": self.symbol,
            "sessions": self.sessions,
            "timeframes": self.timeframes,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "timestamp": datetime.now().isoformat(),
        })

        all_results: List[Dict] = []
        total_combinations = len(self.timeframes) * len(self.sessions)
        completed = 0

        for timeframe in self.timeframes:
            for session in self.sessions:
                if self._stop_event.is_set():
                    self._write_progress({"type": "cancelled", "timestamp": datetime.now().isoformat()})
                    return

                combo_start = time.time()
                self._write_progress({
                    "type": "combination_start",
                    "timeframe": timeframe,
                    "session": session,
                    "timestamp": datetime.now().isoformat(),
                })

                try:
                    # Load OHLCV for the date range natively.
                    df = load_ohlcv_range(self.symbol, timeframe, self.start_date, self.end_date)
                    preloaded = {timeframe: df}

                    # Per-indicator activity callback.
                    def on_indicator(library, name, idx, total):
                        self._write_activity({
                            "type": "indicator",
                            "library": library,
                            "name": name,
                            "index": idx,
                            "total": total,
                            "timeframe": timeframe,
                            "session": session,
                            "timestamp": datetime.now().isoformat(),
                        })

                    # Run VectorBT discovery natively for this (timeframe, session).
                    discovery = Discovery(
                        self.symbol, init_cash=INIT_CASH, top_n=self.top_n,
                        on_indicator=on_indicator,
                    )
                    session_results = discovery.discover(
                        timeframes=[timeframe],
                        sessions=[session],
                        preloaded=preloaded,
                    )

                    # Collect results.
                    key = f"{timeframe}:{session}"
                    combinations = session_results.get(key, [])
                    for r in combinations:
                        all_results.append({
                            "session": session,
                            "session_display": get_session(session).name if session in [s for s in all_session_keys()] else session,
                            "timeframe": timeframe,
                            "test_period": {
                                "start": self.start_date.strftime("%Y-%m-%d"),
                                "end": self.end_date.strftime("%Y-%m-%d"),
                            },
                            "indicator": r.indicator,
                            "library": r.library,
                            "category": r.category,
                            "score": round(r.score, 4),
                            "trades": r.result.trades,
                            "win_rate": round(r.result.win_rate, 4),
                            "profit_factor": _safe_value(r.result.profit_factor),
                            "total_return": _safe_value(r.result.total_return),
                            "max_drawdown": _safe_value(r.result.max_drawdown),
                            "sharpe": _safe_value(r.result.sharpe),
                            "start_balance": INIT_CASH,
                            "end_balance": round(INIT_CASH * (1 + (r.result.total_return or 0)), 2),
                            "stats": _safe_stats(r.result.stats),
                        })

                    self._write_results(all_results)

                    combo_elapsed = time.time() - combo_start
                    completed += 1
                    self._write_progress({
                        "type": "combination_complete",
                        "timeframe": timeframe,
                        "session": session,
                        "combinations_completed": completed,
                        "total_combinations": total_combinations,
                        "results_count": len(all_results),
                        "elapsed_seconds": round(combo_elapsed, 2),
                        "timestamp": datetime.now().isoformat(),
                    })

                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Onboarding failed for {timeframe}:{session}: {e}")
                    self._write_progress({
                        "type": "combination_error",
                        "timeframe": timeframe,
                        "session": session,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    })

        # Write final raw output.
        elapsed = time.time() - start_time
        raw_path = self.output_dir / f"{self.symbol}_onboarding_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        raw_data = {
            "symbol": self.symbol,
            "config": {
                "sessions": self.sessions,
                "timeframes": self.timeframes,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "init_cash": INIT_CASH,
            },
            "results": all_results,
            "elapsed_seconds": round(elapsed, 2),
            "completed_at": datetime.now().isoformat(),
        }
        raw_path.write_text(json.dumps(raw_data, indent=2, default=str), encoding="utf-8")

        self._write_progress({
            "type": "complete",
            "total_results": len(all_results),
            "elapsed_seconds": round(elapsed, 2),
            "raw_file": str(raw_path),
            "timestamp": datetime.now().isoformat(),
        })

    def start_background(self):
        """Start onboarding in a background thread."""
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        """Request the onboarding to stop."""
        self._stop_event.set()


def _safe_stats(stats: Dict) -> Dict:
    """Make stats JSON-safe (replace Infinity/NaN)."""
    safe = {}
    for k, v in stats.items():
        if isinstance(v, float):
            if not np.isfinite(v):
                safe[k] = str(v)
            else:
                safe[k] = round(v, 6)
        else:
            safe[k] = v
    return safe


def _safe_value(v):
    """Make a single value JSON-safe."""
    if isinstance(v, float):
        if not np.isfinite(v):
            return str(v)
        return round(v, 6)
    return v
    """Read all progress markers for a symbol."""
    progress_path = output_dir / "progress.jsonl"
    markers = []
    if progress_path.exists():
        with open(progress_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        markers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return markers


def read_progress(output_dir: Path) -> List[Dict]:
    """Read all progress markers for a symbol."""
    progress_path = output_dir / "progress.jsonl"
    markers = []
    if progress_path.exists():
        with open(progress_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        markers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return markers


def read_live_results(output_dir: Path) -> List[Dict]:
    """Read the live results file for a symbol."""
    results_path = output_dir / "results_live.json"
    if results_path.exists():
        try:
            with open(results_path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def read_activity(output_dir: Path, since: int = 0) -> List[Dict]:
    """Read per-indicator activity markers for a symbol.

    Args:
        output_dir: Symbol onboarding directory.
        since: Only return markers with index > this value (for polling).

    Returns:
        List of activity marker dicts.
    """
    activity_path = output_dir / "activity.jsonl"
    markers = []
    if activity_path.exists():
        with open(activity_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        marker = json.loads(line)
                        if marker.get("index", 0) > since:
                            markers.append(marker)
                    except json.JSONDecodeError:
                        continue
    return markers


def get_latest_activity(output_dir: Path) -> Optional[Dict]:
    """Get the most recent activity marker (what VectorBT is doing right now)."""
    markers = read_activity(output_dir)
    return markers[-1] if markers else None


__all__ = [
    "OnboardingOrchestrator",
    "INIT_CASH",
    "read_progress",
    "read_live_results",
]
