"""Onboarding report generation using VectorBT's native reporting.

VectorBT provides native reporting via ``pf.stats()`` (28+ metrics),
``pf.trades.records_readable`` / ``pf.orders.records_readable`` (trade/order
records), and ``pf.plot()`` (comprehensive interactive plots). This module
emits those native outputs directly — no hand-rolled metric tables.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.onboarding.metrics import ScoredResult
from src.onboarding.validate import ValidationResult


def build_report_data(
    symbol: str,
    discovery: Dict[str, List[ScoredResult]],
    tuned: List[Dict],
    validated: List[ValidationResult],
    best_timeframe_per_session: Dict[str, Dict] = None,
) -> Dict:
    """Assemble a per-symbol onboarding report using native VectorBT stats.

    Each discovery entry carries the candidate's native ``pf.stats()`` dict
    (``result.stats``). No hand-rolled metric selection — the full native
    Series is preserved.
    """
    best = best_timeframe_per_session or {}
    return {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "best_timeframe_per_session": {
            session: {
                "timeframe": info["timeframe"],
                "results": [_scored_to_dict(r) for r in info["results"]],
            }
            for session, info in best.items()
        },
        "discovery": {
            key: [_scored_to_dict(r) for r in results]
            for key, results in discovery.items()
        },
        "tuned": tuned,
        "validated": [_validated_to_dict(v) for v in validated],
    }


def _scored_to_dict(r: ScoredResult) -> Dict:
    return {
        "indicator": r.indicator,
        "library": r.library,
        "category": r.category,
        "session": r.session,
        "timeframe": r.timeframe,
        "score": round(r.score, 4),
        # Native VectorBT pf.stats() output — the full 28-metric Series as a dict.
        "stats": r.result.stats,
    }


def _validated_to_dict(v: ValidationResult) -> Dict:
    return {
        "indicator": v.indicator,
        "library": v.library,
        "session": v.session,
        "timeframe": v.timeframe,
        "passed": v.passed,
        "pf_in_sample": round(v.pf_in_sample, 4),
        "pf_out_sample": round(v.pf_out_sample, 4),
        "degradation_pct": round(v.degradation_pct, 2),
        "trades_out_sample": v.trades_out_sample,
        "reason": v.reason,
    }


def write_reports(
    data: Dict,
    output_dir: Path,
    date: str,
) -> Dict[str, str]:
    """Write JSON report to output_dir. Returns path map.

    The JSON contains the full native ``pf.stats()`` dict per candidate.
    VectorBT's ``pf.plot()`` can be called on any backtest result for
    interactive visualization — no hand-rolled HTML/markdown rendering.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    symbol = data["symbol"]
    base = output_dir / f"{symbol}_onboarding_{date}"

    json_path = base.with_suffix(".json")
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    return {
        "json": str(json_path),
    }


__all__ = ["build_report_data", "write_reports"]
