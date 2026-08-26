"""Onboarding pipeline orchestrator: discovery -> optimize -> validate -> report."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.onboarding.discovery import Discovery, best_timeframe_per_session
from src.onboarding.optimize import Optimizer
from src.onboarding.report import build_report_data, write_reports
from src.onboarding.validate import Validator

logger = logging.getLogger(__name__)


class OnboardingPipeline:
    """Run the full symbol onboarding pipeline."""

    def __init__(
        self,
        symbol: str,
        init_cash: float = 10_000.0,
        top_n: int = 10,
        n_trials: int = 50,
        n_folds: int = 5,
        output_dir: Optional[Path] = None,
    ):
        self.symbol = symbol
        self.init_cash = init_cash
        self.top_n = top_n
        self.n_trials = n_trials
        self.n_folds = n_folds
        self.output_dir = output_dir or Path("tests/onboarding") / symbol
        self.studies_dir = Path("data/studies") / symbol

    def run(
        self,
        timeframes: Optional[List[str]] = None,
        sessions: Optional[List[str]] = None,
        bars: int = 5000,
        stages: str = "discovery",
    ) -> Dict:
        """Run the pipeline and write reports.

        Args:
            timeframes: Timeframes to test (default: all).
            sessions: Sessions to test (default: all).
            bars: Number of OHLCV bars to load per timeframe.
            stages: Which stages to run, comma-separated. Supported:
                - "discovery": VectorBT discovery only (no Optuna, no validation).
                - "discovery,optimize": discovery + Optuna tuning.
                - "discovery,optimize,validate": full pipeline (default).

        Returns a summary dict.
        """
        stage_set = {s.strip() for s in stages.split(",") if s.strip()}

        logger.info(f"Onboarding {self.symbol}: discovery")
        discovery = Discovery(self.symbol, self.init_cash, self.top_n).discover(
            timeframes=timeframes, sessions=sessions, bars=bars
        )

        # Flatten top candidates across all session/timeframe buckets.
        candidates = [r for results in discovery.values() for r in results]

        tuned: List[Dict] = []
        if "optimize" in stage_set:
            logger.info(f"Onboarding {self.symbol}: optimizing {len(candidates)} candidates")
            tuned = Optimizer(self.symbol, self.init_cash, self.n_trials).optimize(
                candidates, self.studies_dir
            )

        validated: List = []
        if "validate" in stage_set:
            logger.info(f"Onboarding {self.symbol}: validating {len(tuned)} tuned")
            validated = Validator(self.symbol, self.init_cash, self.n_folds).validate(tuned)

        best = best_timeframe_per_session(discovery)

        data = build_report_data(self.symbol, discovery, tuned, validated, best)
        date = datetime.now().strftime("%Y%m%d")
        paths = write_reports(data, self.output_dir, date)

        return {
            "symbol": self.symbol,
            "stages": sorted(stage_set),
            "discovery_buckets": len(discovery),
            "candidates": len(candidates),
            "tuned": len(tuned),
            "validated": len(validated),
            "passed": sum(1 for v in validated if v.passed),
            "best_timeframe_per_session": {
                session: {"timeframe": info["timeframe"], "top": len(info["results"])}
                for session, info in best.items()
            },
            "reports": paths,
        }


def onboard(
    symbol: str,
    timeframes: Optional[List[str]] = None,
    sessions: Optional[List[str]] = None,
    top_n: int = 10,
    n_trials: int = 50,
    n_folds: int = 5,
    bars: int = 5000,
    stages: str = "discovery",
) -> Dict:
    """Convenience entry point for onboarding a symbol.

    ``stages`` controls which pipeline stages run (see ``OnboardingPipeline.run``).
    Default is "discovery" only, so VectorBT's true output is visible before any
    Optuna tuning or validation is applied.
    """
    pipeline = OnboardingPipeline(
        symbol=symbol, top_n=top_n, n_trials=n_trials, n_folds=n_folds
    )
    return pipeline.run(timeframes=timeframes, sessions=sessions, bars=bars, stages=stages)


__all__ = ["OnboardingPipeline", "onboard"]
