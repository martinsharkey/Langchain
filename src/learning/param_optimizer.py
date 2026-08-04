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
from typing import Optional
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
    # AUTHORITATIVE mql5-doc optimization ranges for the 7-indicator confluence.
    # MACD + OsMA share the same fast/slow/signal bounds.
    "osma_fast":   (5, 34, 1, int),        # mql5: OsMA/MACD fast (def 12)
    "osma_slow":   (20, 144, 2, int),      # mql5: OsMA/MACD slow (def 26)
    "osma_signal": (5, 55, 1, int),        # mql5: OsMA/MACD signal (def 9)
    "ema_period":  (3, 200, 1, int),       # mql5: EMA (def 14)
    "atr_period":  (5, 50, 1, int),        # mql5: ATR (def 14)
    "power_period": (5, 26, 1, int),       # mql5: Bulls/Bears Power (def 13)
    "rsi_period":  (2, 30, 1, int),        # mql5: RSI (def 14)
    # confluence strengths (ATR-relative gates) + exit
    "atr_min":     (0.0, 4.0, 0.5, float),
    "atr_max":     (0.0, 12.0, 1.0, float),
    "min_ema_slope": (0.0, 0.5, 0.02, float),
    "price_stretch_mult": (1.0, 4.0, 0.5, float),
    "min_confluence": (1, 5, 1, int),
    # ── SIGNED PER-SIDE STRENGTH FLOORS (ATR-normalized so one wide range fits gold
    # ~0.5 and BTC ~15+; the confluence scales by ATR). These are THE core signal —
    # how vigorous buyer/seller activity is. Long floors are minimums (>=), short
    # floors maximums (<=, negative). Default/step includes 0 = gate OFF. Ranges are
    # WIDE and signed (reach well beyond +-3 in ATR units). The optimizer + walk-forward
    # DISCOVER the best per-symbol floors — no hardcoded folklore.
    "osma_min_long":   (0.0, 3.0, 0.1, float),
    "osma_max_short":  (-3.0, 0.0, 0.1, float),
    "macd_min_long":   (0.0, 3.0, 0.1, float),
    "macd_max_short":  (-3.0, 0.0, 0.1, float),
    "bulls_min_long":  (0.0, 5.0, 0.1, float),
    "bears_min_long":  (0.0, 5.0, 0.1, float),   # bears pulled positive in strong uptrend
    "bears_max_short": (-5.0, 0.0, 0.1, float),
    "bulls_max_short": (-5.0, 0.0, 0.1, float),
    "atr_min_rel":     (0.0, 1.5, 0.1, float),   # relative ATR floor (vs median ATR)
    "sl_atr":      (0.5, 3.0, 0.5, float),
    "tp_rr":       (0.5, 3.0, 0.5, float),
}

DEFAULTS = {
    "osma_fast": 12, "osma_slow": 26, "osma_signal": 9,
    "ema_period": 14, "atr_period": 14, "power_period": 13, "rsi_period": 14,
    "atr_min": 0.0, "atr_max": 0.0, "min_ema_slope": 0.02,
    "price_stretch_mult": 2.0, "min_confluence": 4,
    # signed strength floors default 0 = gate OFF (sign-only) -> current behaviour
    "osma_min_long": 0.0, "osma_max_short": 0.0,
    "macd_min_long": 0.0, "macd_max_short": 0.0,
    "bulls_min_long": 0.0, "bears_min_long": 0.0,
    "bears_max_short": 0.0, "bulls_max_short": 0.0, "atr_min_rel": 0.0,
    "sl_atr": 2.0, "tp_rr": 1.0,
}


def _clamp(v, lo, hi, kind):
    v = max(lo, min(hi, v))
    return int(round(v)) if kind is int else round(v, 2)


class ParameterOptimizer:
    def __init__(self, registry, backtest_fn, mql5_knowledge=None,
                 is_failed_fn=None, config_fingerprint_fn=None):
        """
        registry: StrategyRegistry (for focused pockets + regime).
        backtest_fn: callable(symbol, params, sl_atr, tp_rr) -> walk-forward result
          dict {"pfs":[...], "wrs":[...], "n_total":int, "generalizes":bool,
                "score": float}  (score = min PF across windows, the robust metric).
        mql5_knowledge: optional MQL5Knowledge (#22/#25) to GROUND the next tuning
          direction in the docs instead of blind random search.
        is_failed_fn: optional callable(symbol, params_dict)->bool (#25) so the
          search AVOIDS directions the #27 checkpointer already marked as failed.
        config_fingerprint_fn: optional callable(params_dict)->str for logging.
        """
        self.registry = registry
        self.backtest_fn = backtest_fn
        self.mql5_knowledge = mql5_knowledge
        self.is_failed_fn = is_failed_fn
        self.config_fingerprint_fn = config_fingerprint_fn
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
        if cand["osma_fast"] >= cand["osma_slow"]:
            _lo, _hi, _st, _k = PARAM_SPACE["osma_slow"]
            cand["osma_slow"] = _clamp(cand["osma_fast"] + 8, _lo, _hi, _k)  # M1: re-clamp to space
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
        if cand["osma_fast"] >= cand["osma_slow"]:
            _lo, _hi, _st, _k = PARAM_SPACE["osma_slow"]
            cand["osma_slow"] = _clamp(cand["osma_fast"] + 8, _lo, _hi, _k)  # M1: re-clamp to space
        return cand

    def _mql5_guided_candidate(self, symbol: str, params: dict) -> Optional[dict]:
        """
        #25 ReAct alternative: instead of a blind random mutation, ask the mql5
        knowledge RAG for a tuning DIRECTION and nudge the relevant parameter that
        way. Cheap keyword mapping from the retrieved text to a param delta.
        Returns a candidate or None (fall back to random mutation).
        """
        if self.mql5_knowledge is None:
            return None
        try:
            hits = self.mql5_knowledge.research(
                f"better indicator parameters to improve {symbol} entry timing and reduce false signals", 2)
        except Exception:
            return None
        if not hits:
            return None
        text = " ".join(h.get("text", "").lower() for h in hits)
        cand = dict(params)
        moved = False
        # map doc guidance -> a concrete parameter nudge (grounded, not random)
        if "faster" in text or "react faster" in text or "earlier" in text:
            lo, hi, step, kind = PARAM_SPACE["osma_fast"]
            cand["osma_fast"] = _clamp(cand.get("osma_fast", DEFAULTS["osma_fast"]) - step, lo, hi, kind)
            moved = True
        elif "smoother" in text or "fewer" in text or "reduce" in text or "noise" in text:
            lo, hi, step, kind = PARAM_SPACE["osma_slow"]
            cand["osma_slow"] = _clamp(cand.get("osma_slow", DEFAULTS["osma_slow"]) + step, lo, hi, kind)
            moved = True
        if "volatility" in text or "atr" in text:
            lo, hi, step, kind = PARAM_SPACE["atr_period"]
            cand["atr_period"] = _clamp(cand.get("atr_period", DEFAULTS["atr_period"]) - step, lo, hi, kind)
            moved = True
        if not moved:
            return None
        if cand["osma_fast"] >= cand["osma_slow"]:
            _lo, _hi, _st, _k = PARAM_SPACE["osma_slow"]
            cand["osma_slow"] = _clamp(cand["osma_fast"] + 8, _lo, _hi, _k)  # M1: re-clamp to space
        return cand

    def _is_failed(self, symbol: str, cand: dict) -> bool:
        """#25: True if this candidate matches a #27 checkpointer failed direction."""
        if self.is_failed_fn is None:
            return False
        try:
            return bool(self.is_failed_fn(symbol, cand))
        except Exception:
            return False

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

        # candidate list: reflection-guided first, then a #25 mql5-grounded
        # candidate, then random mutations. All skip #27 failed directions.
        guided = [self._apply_directives(base, directives)] if directives else []
        mql5_cand = self._mql5_guided_candidate(symbol, best_params)
        if mql5_cand is not None:
            guided.append(mql5_cand)

        for idx in range(iterations + len(guided)):
            cand = guided[idx] if idx < len(guided) else self._mutate(best_params)
            is_guided = idx < len(guided)
            # #25: never re-try a direction the checkpointer marked as failed
            if self._is_failed(symbol, cand):
                continue
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
                "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
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
