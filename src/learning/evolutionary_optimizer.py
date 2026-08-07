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

# module-level seed-model cache (keyed by report-set signature) so we don't re-parse the
# big GoldShark XMLs + refit the GBR on every optimise() call across symbols/days.
_SEED_CACHE = {"sig": None, "model": None, "features": None}


class EvolutionaryOptimizer:
    def __init__(self, param_space: dict, backtest_fn: Callable,
                 reports_dir: str = None, experience_db=None, onnx_predictor=None):
        """param_space: {name:(lo,hi,step,type)}; backtest_fn(symbol,params,sl_atr,tp_rr)
        -> {'score':float,'generalizes':bool,...} (the real walk-forward backtester).
        experience_db: optional — pulls LIVE closed trades (ALL symbols) into the seed
        model so it learns winning combinations across every symbol, not gold-only.
        onnx_predictor: optional — its per-symbol P(win) is blended into fitness and used
        to bias seeding, integrating the two ML systems into one learning brain."""
        self.space = param_space
        self.backtest_fn = backtest_fn
        self.reports_dir = reports_dir or os.path.join(
            "data", "reprodata", "goldshark13", "optimiser_reports")
        self.db = experience_db
        self.onnx = onnx_predictor
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
    # Column map is the shared canonical GOLDSHARK_COLMAP (tools/goldshark_columns) so the
    # seed model and the researcher's verdict never drift. Features are OUR param names.

    def _train_seed_model(self, max_rows: int = 20000):
        """Fit params->PF on GoldShark passes so we can rank promising combos. Non-fatal:
        returns False if no reports/parser or too few rows."""
        try:
            from tools.parse_optimizer_report import parse_report, _f
            from tools.goldshark_columns import GOLDSHARK_COLMAP, col_for, value_for
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
        # CACHE: skip the expensive XML parse + GBR fit if the report set is unchanged.
        sig = tuple(sorted((p, int(os.path.getmtime(p)), os.path.getsize(p)) for p in bts))
        if _SEED_CACHE["sig"] == sig and _SEED_CACHE["model"] is not None:
            self._seed_model = _SEED_CACHE["model"]
            self._seed_features = _SEED_CACHE["features"]
            return True
        feats = list(GOLDSHARK_COLMAP.keys())  # OUR param names (order-stable)
        X, y = [], []
        for path in sorted(bts, key=lambda p: -os.path.getsize(p))[:6]:
            try:
                hdr, passes = parse_report(path)
            except Exception:
                continue
            present = [p for p in feats if col_for(p, hdr)]
            if len(present) < 4:
                continue
            for r in passes:
                pf = _f(r, "Profit Factor")
                if pf <= 0 or _f(r, "Trades") < 20:
                    continue
                X.append([value_for(p, r, _f) for p in feats]); y.append(min(pf, 10.0))
                if len(X) >= max_rows:
                    break
        if len(X) < 200:
            logger.info(f"seed model: only {len(X)} usable GoldShark rows — skipping seed stage")
            return False
        # ALL-SYMBOL LIVE DATA: fold in live closed trades (every symbol) so the seed model
        # learns winning param/indicator combinations across the whole book, not gold-only.
        try:
            nlive = self._add_live_rows(X, y, feats)
            if nlive:
                logger.info(f"seed model: added {nlive} live-trade rows (all symbols)")
        except Exception as e:
            logger.debug(f"seed live rows skip: {e}")
        model = GradientBoostingRegressor(n_estimators=120, max_depth=3, learning_rate=0.08)
        model.fit(np.array(X), np.array(y))
        self._seed_model = model
        self._seed_features = feats
        _SEED_CACHE.update(sig=sig, model=model, features=feats)  # cache for reuse
        # feature importance = which PARAMS most drive PF across all the evidence
        imp = sorted(zip(feats, model.feature_importances_), key=lambda x: -x[1])[:5]
        logger.warning(f"[EVO] seed model trained on {len(X)} GoldShark passes; "
                       f"top PF-driving params: {[(f, round(i,2)) for f,i in imp]}")
        return True

    def _add_live_rows(self, X: list, y: list, feats: list) -> int:
        """Fold LIVE closed trades (ALL symbols, clean/non-simulated) into the seed training
        set. Each trade's entry indicator snapshot supplies the strength columns; realised
        win/loss becomes a pseudo-PF target (win->2.0, breakeven->1.0, loss->0.3) so the
        model learns which entry-strength combinations actually won across every symbol."""
        if self.db is None:
            return 0
        import sqlite3, json as _json
        conn = sqlite3.connect(self.db.db_path); conn.row_factory = sqlite3.Row
        try:
            lw, lp = "", []
            try:
                lw, lp = self.db.learning_window_clause()
            except Exception:
                pass
            rows = conn.execute(
                "SELECT outcome, indicators_snapshot FROM trades WHERE outcome IN "
                "('win','loss','breakeven') AND indicators_snapshot IS NOT NULL" + lw
                + " ORDER BY id DESC LIMIT 5000", lp).fetchall()
        finally:
            conn.close()
        # map OUR param-name features -> the live entry snapshot keys (indicator STATE at
        # entry) so live rows populate the same columns the GoldShark passes do.
        snap_map = {"osma_min_long": "osma", "bulls_min_long": "bulls_power",
                    "bears_min_long": "bears_power", "atr_min": "atr", "atr_max": "atr"}
        added = 0
        for r in rows:
            try:
                snap = _json.loads(r["indicators_snapshot"] or "{}")
            except Exception:
                continue
            if not snap:
                continue
            row = [float(snap.get(snap_map.get(c, ""), 0.0) or 0.0) for c in feats]
            if not any(row):
                continue
            tgt = 2.0 if r["outcome"] == "win" else (1.0 if r["outcome"] == "breakeven" else 0.3)
            X.append(row); y.append(tgt); added += 1
        return added

    def _seed_score(self, cand: dict) -> float:
        if self._seed_model is None:
            return 0.0
        # features are OUR param names -> read directly from the candidate
        row = [[float(cand.get(c, 0.0) or 0.0) for c in self._seed_features]]
        try:
            return float(self._seed_model.predict(np.array(row))[0])
        except Exception:
            return 0.0

    # ── STAGE 2: genetic joint search ─────────────────────────────────────────
    def _carry(self, cand: dict, base_params: dict) -> dict:
        """Overlay base_params keys that are NOT in PARAM_SPACE onto a candidate so every
        config is scored under the SAME gating as the incumbent (critical: keeps floors_raw,
        hard_sl_points, safety_tp_points, be/trail, bal_per_lot — otherwise a raw-gated gold
        baseline would be compared against ATR-gated candidates: an invalid ranking)."""
        merged = dict(cand)
        for k, v in base_params.items():
            if k not in self.space and k not in merged:
                merged[k] = v
        return merged

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
        # initial population: base + evidence-seeded top candidates + random. Every
        # candidate carries the base's non-tunable keys (floors_raw etc.) for like-for-like.
        pop = [dict(base_params)]
        # WINNING-CLUSTER SEEDS: build candidates around the centroid(s) of ALL known
        # winning configs (GoldShark profitable passes + checkpointer bests + winning
        # baseline) so the search BUILDS ON the winning region, not just gold/random.
        try:
            from src.learning.winning_clusters import WinningClusters
            wc = WinningClusters().analyse()
            if wc:
                for cen in wc.get("centroids", [])[:3]:
                    cand = {p: self._clip(p, v) for p, v in cen["params"].items() if p in self.space}
                    pop.append(self._carry(cand, base_params))
                    # a couple of mutated variants around each winning centroid
                    for _ in range(2):
                        m = dict(cand)
                        for kk in list(m):
                            if random.random() < 0.3:
                                lo, hi, step, typ = self.space[kk]
                                m[kk] = self._clip(kk, m[kk] + random.choice([-1, 1]) * step)
                        pop.append(self._carry(m, base_params))
                logger.warning(f"[EVO] {symbol}: seeded {len(pop)-1} candidates from winning clusters")
        except Exception as e:
            logger.debug(f"winning-cluster seed skip: {e}")
        if self._seed_model is not None:
            ranked = sorted((self._sample() for _ in range(seed_pool)),
                            key=self._seed_score, reverse=True)
            pop += [self._carry(c, base_params) for c in ranked[:max(1, pop_size - len(pop))]]
        else:
            pop += [self._carry(self._sample(), base_params) for _ in range(max(1, pop_size - len(pop)))]

        def fitness(c):
            r = self.backtest_fn(symbol, c, c.get("sl_atr", 1.0), c.get("tp_rr", 2.0))
            base = (r["score"] if (r and r.get("generalizes")) else -1.0)
            # INTEGRATE ONNX: blend the win-probability the per-symbol ONNX model assigns to
            # this config's implied entry-strength profile as a small tie-break bias, so the
            # two ML systems agree on the chosen params (never overrides a failed backtest).
            if self.onnx is not None and base > 0:
                try:
                    pw = self.onnx.predict_win_prob({
                        "symbol": symbol, "osma": c.get("osma_min_long", 0),
                        "bulls_power": c.get("bulls_min_long", 0),
                        "bears_power": c.get("bears_min_long", 0),
                        "atr": c.get("atr_min", 0)})
                    if pw is not None:
                        base += 0.2 * (pw - 0.5)   # +/-0.1 nudge, backtest still dominates
                except Exception:
                    pass
            return base, r

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
