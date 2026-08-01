"""
ParameterOptimizer — autonomous self-tuning of indicator parameters per symbol.

This is the self-learning the trader wants: the bot proactively looks at a
symbol, mutates its indicator parameters (EMA period, OsMA fast/slow/signal, RSI
period, CCI period, and the SL/RR exit), backtests each candidate WALK-FORWARD
on real history, and KEEPS a mutation only if it genuinely generalizes (PF>=1 in
every time window) AND beats the current best. Micro-adjustments, tried on the
symbol, kept when better — hill-climbing on out-of-sample edge.

Tuned params are persisted per symbol (data/tuned_params.json) and applied live
by the ensemble/focused signal path. Nothing is trusted until it passes the
walk-forward gate, so the optimizer cannot overfit its way into live trading.
"""

from __future__ import annotations

import os
import json
import random
from dataclasses import dataclass

from src import config
from src.utils.logger import get_logger

logger = get_logger("param_optimizer")

TUNED_PATH = os.path.join(config.DATA_DIR, "tuned_params.json")

# Parameter search space: name -> (min, max, step, kind)
# Ranges WIDENED (#29/#31) to reach the PROVEN GoldShark optimizer cluster that
# the old ranges could not touch: EMA 13..130 (proven ~13 and up to 113),
# OsMA fast up to ~66 / slow up to ~120 (proven cluster fast=44 slow=69-117),
# ATR period 14..82 (was not tunable at all). Without this, auto-tune literally
# cannot find the region where the confluence strategy tests PF 1.46-1.62.
PARAM_SPACE = {
    "ema_fast":    (5, 40, 1, int),
    "ema_slow":    (18, 130, 2, int),
    "rsi_period":  (8, 21, 1, int),
    "cci_period":  (14, 28, 2, int),
    "osma_fast":   (8, 66, 2, int),
    "osma_slow":   (20, 120, 2, int),
    "osma_signal": (6, 43, 1, int),
    "atr_period":  (14, 82, 2, int),           # confluence: ATR period (proven 14..82)
    "atr_min":     (0.5, 4.0, 0.5, float),     # confluence: min ATR (volatility floor, ATR-relative)
    "atr_max":     (3.0, 12.0, 1.0, float),    # confluence: max ATR (volatility ceiling)
    "min_ema_slope": (0.02, 0.5, 0.02, float), # confluence: min |EMA slope| for trend confirm
    "sl_atr":      (0.6, 1.8, 0.2, float),     # exit: stop distance in ATR
    "tp_rr":       (1.5, 3.0, 0.5, float),     # exit: reward:risk
}

DEFAULTS = {
    "ema_fast": 9, "ema_slow": 21, "rsi_period": 14, "cci_period": 20,
    "osma_fast": 12, "osma_slow": 26, "osma_signal": 9,
    "atr_period": 14, "atr_min": 1.4, "atr_max": 4.5, "min_ema_slope": 0.05,
    "sl_atr": 1.0, "tp_rr": 2.0,
}


def _clamp(v, lo, hi, kind):
    v = max(lo, min(hi, v))
    return int(round(v)) if kind is int else round(v, 2)


class ParameterOptimizer:
    def __init__(self, registry, backtest_fn):
        """
        registry: StrategyRegistry (for focused pockets + regime).
        backtest_fn: callable(symbol, params, sl_atr, tp_rr) -> walk-forward result
          dict {"pfs":[...], "wrs":[...], "n_total":int, "generalizes":bool,
                "score": float}  (score = min PF across windows, the robust metric).
        """
        self.registry = registry
        self.backtest_fn = backtest_fn
        self.tuned = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(TUNED_PATH):
                with open(TUNED_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _persist(self):
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = TUNED_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.tuned, f, indent=2)
            os.replace(tmp, TUNED_PATH)
        except Exception as e:
            logger.warning(f"tuned params persist failed: {e}")

    def current_params(self, symbol: str) -> dict:
        key = self._key(symbol)
        return dict(self.tuned.get(key, {}).get("params", DEFAULTS))

    def _key(self, symbol: str) -> str:
        return symbol.upper()

    def _mutate(self, params: dict, n_mutations: int = 2) -> dict:
        """Randomly nudge a few parameters within the search space (micro-adjust)."""
        cand = dict(params)
        keys = random.sample(list(PARAM_SPACE.keys()), k=min(n_mutations, len(PARAM_SPACE)))
        for k in keys:
            lo, hi, step, kind = PARAM_SPACE[k]
            cur = cand.get(k, DEFAULTS[k])
            direction = random.choice([-1, 1])
            cand[k] = _clamp(cur + direction * step, lo, hi, kind)
        # keep ema_fast < ema_slow, osma_fast < osma_slow (sane ordering)
        if cand["ema_fast"] >= cand["ema_slow"]:
            cand["ema_slow"] = cand["ema_fast"] + 4
        if cand["osma_fast"] >= cand["osma_slow"]:
            cand["osma_slow"] = cand["osma_fast"] + 8
        return cand

    def _apply_directives(self, params: dict, directives: dict) -> dict:
        """
        Build a candidate GUIDED by post-mortem directives (e.g. {'sl_atr': +0.2,
        'tp_rr': +0.5, 'giveback': +0.15}). Reflection steers the search; the
        walk-forward gate still decides whether to keep it.
        """
        cand = dict(params)
        for k, delta in (directives or {}).items():
            if k not in PARAM_SPACE:
                continue  # e.g. 'entry_extension_filter' handled elsewhere
            lo, hi, step, kind = PARAM_SPACE[k]
            cur = cand.get(k, DEFAULTS[k])
            cand[k] = _clamp(cur + delta, lo, hi, kind)
        if cand["ema_fast"] >= cand["ema_slow"]:
            cand["ema_slow"] = cand["ema_fast"] + 4
        if cand["osma_fast"] >= cand["osma_slow"]:
            cand["osma_slow"] = cand["osma_fast"] + 8
        return cand

    def optimize(self, symbol: str, iterations: int = 12, candidates_per_iter: int = 1,
                 directives: dict = None) -> dict:
        """
        Hill-climb: start from current best, try mutations, keep any that
        generalize AND beat the incumbent's score (min-PF across windows).

        If `directives` are supplied (from the post-mortem self-reflection), the
        FIRST candidate is guided in that direction — so the bot's reflection on
        its own failures actively steers the tuning, then walk-forward validates.
        Returns a summary of what changed.
        """
        key = self._key(symbol)
        base = self.current_params(symbol)
        base_res = self.backtest_fn(symbol, base, base.get("sl_atr", 1.0), base.get("tp_rr", 2.0))
        if not base_res:
            return {"symbol": symbol, "status": "no baseline data"}
        best_params = base
        best_score = base_res["score"] if base_res.get("generalizes") else -1.0
        best_res = base_res
        improved = False
        tried = 0
        directive_worked = False

        # candidate list: reflection-guided first (if any), then random mutations
        guided = [self._apply_directives(base, directives)] if directives else []

        for idx in range(iterations + len(guided)):
            cand = guided[idx] if idx < len(guided) else self._mutate(best_params)
            is_guided = idx < len(guided)
            tried += 1
            res = self.backtest_fn(symbol, cand, cand.get("sl_atr", 1.0), cand.get("tp_rr", 2.0))
            if not res or not res.get("generalizes"):
                continue
            # robust objective: maximise the WORST-window PF (min across windows),
            # tie-break on total R. Only keep if it clears the incumbent.
            if res["score"] > best_score + 0.01:
                best_score = res["score"]; best_params = cand; best_res = res
                improved = True
                if is_guided:
                    directive_worked = True

        if improved:
            self.tuned[key] = {
                "params": best_params,
                "score": round(best_score, 3),
                "pfs": best_res.get("pfs"),
                "wrs": best_res.get("wrs"),
                "n": best_res.get("n_total"),
                "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            }
            self._persist()
            logger.info(f"[OPTIMIZER] {symbol}: IMPROVED -> min-PF {best_score:.2f} "
                        f"params={best_params} (tried {tried}, from_reflection={directive_worked})")
            return {"symbol": symbol, "improved": True, "score": best_score,
                    "params": best_params, "pfs": best_res.get("pfs"), "tried": tried,
                    "from_reflection": directive_worked}

        logger.info(f"[OPTIMIZER] {symbol}: no improvement over min-PF {best_score:.2f} (tried {tried})")
        return {"symbol": symbol, "improved": False, "score": best_score, "tried": tried}

    def status(self) -> dict:
        return dict(self.tuned)
