"""
AdaptiveLoop — orchestrates the full self-improvement cycle (L4 -> L5 -> L6).

On a cadence (called by the engine, and safe to run in the background):
  1. REFLECT (L4): for each symbol, analyze losses -> LLM hypothesis.
  2. SYNTHESIZE (L5): turn the hypothesis into a candidate strategy (status=testing).
  3. VALIDATE (L6): backtest the candidate on real MT5 history, out-of-sample.
  4. PROMOTE or REJECT: if it beats the gate, activate it (earns ensemble weight);
     otherwise disable it and mark the hypothesis rejected — with the evidence
     stored so the bot doesn't retry the same dead end.

This is the guardrail-respecting version of "the bot invents and adopts new
strategies": nothing trades real size until it proves itself on history.
"""

from __future__ import annotations

from typing import Optional

from src.utils.logger import get_logger
from src.learning.reflection_agent import ReflectionAgent, HypothesisStore
from src.learning.strategy_synthesizer import StrategySynthesizer
from src.learning.backtester import Backtester

logger = get_logger("adaptive_loop")


class AdaptiveLoop:
    def __init__(self, experience_db, registry, symbol_resolver=None,
                 rates_fn=None, ticks_fn=None):
        """
        symbol_resolver: optional callable(base_symbol)->resolved broker symbol
        (so backtests use the tradable symbol, e.g. XAUUSD -> XAUUSD-ECN).
        rates_fn / ticks_fn: optional data-source callables matching
        src.mt5.data.get_rates / get_ticks signatures. Use them to validate
        synthesized strategies on an independent historical source such as
        Dukascopy (issue #80).
        """
        self.experience_db = experience_db
        self.registry = registry
        self.store = HypothesisStore()
        self.reflection = ReflectionAgent(experience_db, registry, self.store)
        self.synth = StrategySynthesizer(registry)
        self.backtester = Backtester(registry, rates_fn=rates_fn, ticks_fn=ticks_fn)
        self.symbol_resolver = symbol_resolver or (lambda s: s)
        self.last_summary: dict = {}

    def run_once(self, symbols: list[str], timeframe: str = "M15",
                 min_sample: int = 8) -> dict:
        """One full adaptive pass across the given base symbols."""
        summary = {"reflected": [], "synthesized": [], "promoted": [], "rejected": []}

        for base in symbols:
            resolved = self.symbol_resolver(base)

            # 1) reflect on this symbol's REAL closed trades (recorded under resolved name)
            hyp = self.reflection.reflect(symbol=resolved, min_sample=min_sample)
            if not hyp:
                continue
            summary["reflected"].append({"symbol": resolved, "hypothesis": hyp.get("hypothesis")})

            # 2) synthesize a candidate strategy
            name = self.synth.synthesize(hyp)
            if not name:
                self.store.set_status(hyp["id"], "rejected", {"reason": "no synthesizable strategies"})
                continue
            summary["synthesized"].append({"symbol": resolved, "strategy": name})
            self.store.set_status(hyp["id"], "testing")

            # 3) validate on real history, out-of-sample
            try:
                res = self.backtester.evaluate_promotion(
                    resolved, [name], timeframe=timeframe, bars=8000, min_agreement=1)
            except Exception as e:
                logger.warning(f"adaptive backtest failed for {name}: {e}")
                self.store.set_status(hyp["id"], "rejected", {"reason": f"backtest error: {e}"})
                self.registry.set_status(name, "disabled")
                continue

            # 4) promote or reject
            from dataclasses import asdict
            bt = asdict(res)
            if res.passed:
                self.registry.set_status(name, "active")
                self.store.set_status(hyp["id"], "promoted", bt)
                summary["promoted"].append({"strategy": name, "win_rate": res.win_rate,
                                            "profit_factor": res.profit_factor, "R": res.total_r})
                logger.info(f"PROMOTED synthesized strategy {name}: WR {res.win_rate}% "
                            f"PF {res.profit_factor} R {res.total_r}")
            else:
                self.registry.set_status(name, "disabled")
                self.store.set_status(hyp["id"], "rejected", bt)
                summary["rejected"].append({"strategy": name, "note": res.note,
                                           "win_rate": res.win_rate})
                logger.info(f"Rejected synthesized strategy {name}: {res.note}")

        self.last_summary = summary
        return summary

    def status(self) -> dict:
        """For the dashboard: recent hypotheses + testing/active synth strategies."""
        recent = self.store.recent(15)
        testing = [s.name for s in self.registry.get_all()
                   if getattr(s, "status", "active") == "testing" and s.name.startswith("SYNTH_")]
        promoted = [s.name for s in self.registry.get_all()
                    if getattr(s, "status", "active") == "active" and s.name.startswith("SYNTH_")]
        return {"recent_hypotheses": recent, "testing": testing, "promoted": promoted,
                "last_summary": self.last_summary}
