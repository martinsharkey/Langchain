"""
ML Pattern Engine (XGBoost) — nightly, per-symbol pattern discovery with an
AUTHORITY GATE.

What it does (owner design 2026-08-12):
  1. Pull each symbol's closed trades (features from indicators_snapshot -> win/loss).
  2. Train a per-symbol XGBoost classifier (winner vs loser) with an OUT-OF-SAMPLE
     split; record its OOS score.
  3. Extract the top feature-importance "patterns" and store them in ml_patterns
     with their SUPPORT (samples, backtests) and OOS score.
  4. Run the AUTHORITY GATE: a pattern only becomes 'authoritative' (usable live)
     once support >= configured thresholds AND OOS score clears the bar. Below that
     it stays 'provisional' and is ignored by the live system.

Design guarantees:
  * Non-fatal + torch-free (xgboost only). If xgboost missing or data too small,
    it records nothing authoritative and logs why — it NEVER fabricates authority.
  * Portable: pure DB + config, no host-specific paths.
  * The live system reads ONLY db.authoritative_patterns(), so nothing the engine
    produces affects trading until it has earned authority from the data.
"""

import os
import logging
from datetime import datetime

from src import config

logger = logging.getLogger("ml_pattern_engine")

# Feature columns pulled from indicators_snapshot (ATR-normalised where sensible).
_FEATURES = ["osma_closed", "osma_prev", "macd_line", "macd_signal",
             "bulls_power", "bears_power", "rsi", "atr", "atr_prev"]


class MLPatternEngine:
    def __init__(self, experience_db):
        self.db = experience_db
        self.min_samples = int(getattr(config, "ML_AUTHORITY_MIN_SAMPLES", 200))
        self.min_backtests = int(getattr(config, "ML_AUTHORITY_MIN_BACKTESTS", 3))
        self.min_oos = float(getattr(config, "ML_AUTHORITY_MIN_OOS", 0.55))
        self.min_train = int(getattr(config, "ML_MIN_TRAIN_SAMPLES", 80))

    def _load(self, symbol):
        import sqlite3, json
        conn = sqlite3.connect(self.db.db_path)
        rows = conn.execute(
            "SELECT outcome, indicators_snapshot FROM trades WHERE symbol=? "
            "AND outcome IN ('win','loss') AND indicators_snapshot IS NOT NULL "
            "ORDER BY id DESC LIMIT 5000", (symbol,)).fetchall()
        conn.close()
        X, y = [], []
        for outcome, snap in rows:
            try:
                d = json.loads(snap)
            except Exception:
                continue
            row = []
            ok = True
            for f in _FEATURES:
                v = d.get(f)
                try:
                    row.append(float(v))
                except (TypeError, ValueError):
                    ok = False; break
            if ok:
                X.append(row); y.append(1 if outcome == "win" else 0)
        return X, y

    def _backtest_support(self, symbol):
        """How many backtest/fwd-test adjustments back this symbol (authority input)."""
        try:
            hist = self.db.adjustment_history(symbol=symbol, limit=1000)
            return sum(1 for h in hist if h.get("fwd_pf") is not None or h.get("backtest_pf") is not None)
        except Exception:
            return 0

    def scan_symbol(self, symbol) -> dict:
        try:
            import xgboost as xgb
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score
        except Exception as e:
            logger.warning(f"ML engine deps unavailable ({e}); skipping")
            return {"symbol": symbol, "skipped": "no-xgboost"}

        X, y = self._load(symbol)
        n = len(y); pos = sum(y)
        if n < self.min_train or pos < 10 or (n - pos) < 10:
            logger.info(f"[ML] {symbol}: only {n} samples ({pos}W) — below train floor "
                        f"{self.min_train}; no patterns recorded")
            return {"symbol": symbol, "n": n, "trained": False}

        import numpy as np
        X = np.array(X); y = np.array(y)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, shuffle=False)
        model = xgb.XGBClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.1,
            subsample=0.8, eval_metric="logloss", n_jobs=2)
        model.fit(Xtr, ytr)
        try:
            oos = float(roc_auc_score(yte, model.predict_proba(Xte)[:, 1]))
        except Exception:
            oos = 0.5

        backtests = self._backtest_support(symbol)
        imp = model.feature_importances_
        model_version = datetime.now().strftime("%Y%m%d")
        # record the top features as patterns with their support + OOS
        order = sorted(range(len(_FEATURES)), key=lambda i: -imp[i])[:5]
        for i in order:
            self.db.record_ml_pattern(
                symbol=symbol, pattern_key=f"{_FEATURES[i]}_importance",
                feature=_FEATURES[i], direction=None,
                recommendation=f"{_FEATURES[i]} is a top separator (imp={imp[i]:.3f})",
                importance=float(imp[i]), support_samples=n,
                support_backtests=backtests, oos_score=oos, model_version=model_version)
        logger.info(f"[ML] {symbol}: trained n={n} OOS-AUC={oos:.3f} backtests={backtests} "
                    f"top={_FEATURES[order[0]]}")
        return {"symbol": symbol, "n": n, "oos": oos, "backtests": backtests, "trained": True}

    def run_nightly(self, symbols) -> dict:
        results = {}
        for sym in symbols:
            try:
                results[sym] = self.scan_symbol(sym)
            except Exception as e:
                logger.warning(f"[ML] {sym} scan failed: {e}")
                results[sym] = {"error": str(e)}
        promoted = self.db.promote_ml_patterns(
            self.min_samples, self.min_backtests, self.min_oos)
        logger.info(f"[ML] authority gate: {promoted} pattern(s) now AUTHORITATIVE "
                    f"(need samples>={self.min_samples}, backtests>={self.min_backtests}, "
                    f"OOS>={self.min_oos})")
        results["_promoted"] = promoted
        return results
