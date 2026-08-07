"""
Evolutionary + evidence-seeded JOINT parameter optimiser.

The existing tuner is greedy one-coordinate-at-a-time, so it cannot find winning parameter
COMBINATIONS or interaction effects. This module adds a true joint search over the full
PARAM_SPACE, in two stages (R10 evidence-first, VPS-portable — pure Python + sklearn/numpy
which are already dependencies; NO Optuna/genetic libs):

  STAGE 1 — SEED FROM DATA: mine the GoldShark optimiser XML passes (thousands of scored
  parameter vectors) and fit a GradientBoostingRegressor params->ProfitFactor. Use it to
  RANK a large random sample of candidate combinations and take the top-K as promising
  seeds — so we start the search where the historic evidence says good combos live.

  STAGE 2 — GENETIC JOINT SEARCH: evolve a population over the full space (tournament
  select + uniform crossover + per-gene mutation), fitness = the REAL walk-forward
  backtester score (min PF across windows). This finds jointly-optimal combinations and
  interactions the greedy tuner cannot. Every survivor is walk-forward validated, so
  nothing overfits; the winner is only returned if it beats the incumbent.
"""
from __future__ import annotations
import os, glob, random
from typing import Callable, Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("evo_optimizer")


class EvolutionaryOptimizer:
    def __init__(self, param_space: dict, backtest_fn: Callable,
                 reports_dir: str = None):
        """param_space: {name:(lo,hi,step,type)}; backtest_fn(symbol,params,sl_atr,tp_rr)
        -> {'score':float,'generalizes':bool,...} (the real walk-forward backtester)."""
        self.space = param_space
        self.backtest_fn = backtest_fn
        self.reports_dir = reports_dir or os.path.join(
            "data", "reprodata", "goldshark13", "optimiser_reports")
        self._seed_model = None
        self._seed_features = None

    # ── candidate sampling ────────────────────────────────────────────────────
    def _sample(self) -> dict:
        c = {}
        for k, (lo, hi, step, typ) in self.space.items():
            if typ is int:
                n = int((hi - lo) / step)
                c[k] = int(lo + random.randint(0, max(n, 0)) * step)
            else:
                n = int(round((hi - lo) / step))
                c[k] = round(lo + random.randint(0, max(n, 0)) * step, 4)
        return c

    def _clip(self, k, v):
        lo, hi, step, typ = self.space[k]
        v = max(lo, min(hi, v))
        return int(round(v)) if typ is int else round(v, 4)

    # ── STAGE 1: seed model from GoldShark passes ─────────────────────────────
    _COLMAP = {  # GoldShark XML Inp* column -> our param name
        "InpMinOsMALong": "osma_min_long", "InpMinBullsLong": "bulls_min_long",
        "InpMaxBearsLong": "bears_min_long", "InpMinATR": "atr_min", "InpMaxATR": "atr_max",
        "InpMinEmaSlope": "min_ema_slope", "InpMaxOsMAShort": "osma_max_short",
        "InpMaxMomentumAge": "max_momentum_age", "InpSLATR": "sl_atr", "InpTPRR": "tp_rr",
    }

    def _train_seed_model(self, max_rows: int = 20000):
        """Fit params->PF on GoldShark passes so we can rank promising combos. Non-fatal:
        returns False if no reports/parser or too few rows."""
        try:
            from tools.parse_optimizer_report import parse_report, _f
            from sklearn.ensemble import GradientBoostingRegressor
        except Exception:
            return False
        bts = []
        for d in (self.reports_dir, os.path.join(os.path.dirname(self.reports_dir.rstrip("/\\")),
                                                  "mt5_installs", "reports")):
            if d and os.path.isdir(d):
                bts += glob.glob(os.path.join(d, "*.xml"))
        if not bts:
            return False
        feats = [c for c in self._COLMAP]  # order-stable
        X, y = [], []
        for path in sorted(bts, key=lambda p: -os.path.getsize(p))[:6]:
            try:
                hdr, passes = parse_report(path)
            except Exception:
                continue
            present = [c for c in feats if c in hdr]
            if len(present) < 4:
                continue
            for r in passes:
                pf = _f(r, "Profit Factor")
                if pf <= 0 or _f(r, "Trades") < 20:
                    continue
                X.append([_f(r, c) for c in feats]); y.append(min(pf, 10.0))
                if len(X) >= max_rows:
                    break
        if len(X) < 200:
            logger.info(f"seed model: only {len(X)} usable GoldShark rows — skipping seed stage")
            return False
        model = GradientBoostingRegressor(n_estimators=120, max_depth=3, learning_rate=0.08)
        model.fit(np.array(X), np.array(y))
        self._seed_model = model
        self._seed_features = feats
        # feature importance = which PARAMS most drive PF across all the evidence
        imp = sorted(zip(feats, model.feature_importances_), key=lambda x: -x[1])[:5]
        logger.warning(f"[EVO] seed model trained on {len(X)} GoldShark passes; "
                       f"top PF-driving params: {[(f, round(i,2)) for f,i in imp]}")
        return True

    def _seed_score(self, cand: dict) -> float:
        if self._seed_model is None:
            return 0.0
        row = [[float(cand.get(self._COLMAP[c], 0.0)) for c in self._seed_features]]
        try:
            return float(self._seed_model.predict(np.array(row))[0])
        except Exception:
            return 0.0

    # ── STAGE 2: genetic joint search ─────────────────────────────────────────
    def optimise(self, symbol: str, base_params: dict, generations: int = 6,
                 pop_size: int = 16, seed_pool: int = 400) -> Optional[dict]:
        """Joint evolutionary search. Returns the best {params,score,res} found that
        BEATS the base, else None. Every fitness eval is the real walk-forward backtest."""
        base_score = -1.0
        base_res = self.backtest_fn(symbol, base_params, base_params.get("sl_atr", 1.0),
                                    base_params.get("tp_rr", 2.0))
        if base_res and base_res.get("generalizes"):
            base_score = base_res["score"]

        self._train_seed_model()
        # initial population: base + evidence-seeded top candidates + random
        pop = [dict(base_params)]
        if self._seed_model is not None:
            ranked = sorted((self._sample() for _ in range(seed_pool)),
                            key=self._seed_score, reverse=True)
            pop += ranked[:pop_size - 1]
        else:
            pop += [self._sample() for _ in range(pop_size - 1)]

        def fitness(c):
            r = self.backtest_fn(symbol, c, c.get("sl_atr", 1.0), c.get("tp_rr", 2.0))
            return (r["score"] if (r and r.get("generalizes")) else -1.0), r

        scored = [(*fitness(c), c) for c in pop]  # (score, res, cand)
        best = max(scored, key=lambda t: t[0])
        logger.warning(f"[EVO] {symbol} gen0 best score {best[0]:.2f} (base {base_score:.2f}), pop {len(pop)}")

        for g in range(1, generations + 1):
            scored.sort(key=lambda t: t[0], reverse=True)
            elite = [t[2] for t in scored[:max(2, pop_size // 4)]]
            children = []
            while len(children) < pop_size - len(elite):
                a, b = random.choice(elite), random.choice(elite)
                child = {k: (a[k] if random.random() < 0.5 else b.get(k, a[k])) for k in a}
                # per-gene mutation (one step)
                for k in child:
                    if k in self.space and random.random() < 0.2:
                        lo, hi, step, typ = self.space[k]
                        child[k] = self._clip(k, child[k] + random.choice([-1, 1]) * step)
                children.append(child)
            newpop = elite + children
            scored = [(*fitness(c), c) for c in newpop]
            gbest = max(scored, key=lambda t: t[0])
            if gbest[0] > best[0]:
                best = gbest
            logger.warning(f"[EVO] {symbol} gen{g} best {gbest[0]:.2f} (overall {best[0]:.2f})")

        if best[0] > base_score + 0.05:
            logger.warning(f"[EVO] {symbol} JOINT search improved score {base_score:.2f} -> {best[0]:.2f}")
            return {"params": best[2], "score": best[0], "res": best[1],
                    "base_score": base_score, "improved": True}
        return {"params": base_params, "score": base_score, "improved": False}
