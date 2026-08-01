"""
ONNX trade-outcome predictor (#42) — a LEARNED, per-symbol entry confidence.

The hand-weighted confidence was anti-calibrated. This augments it with a model
trained on real closed trades: given a SCALE-FREE entry fingerprint, predict P(win).
Exported to ONNX so onnxruntime scores each candidate entry at microsecond latency
(portable + offline for the standalone/VPS build).

Methodology hardened per review (this model has veto power, so its validation must
be at least as rigorous as the rest of the pipeline):
  1. CHRONOLOGICAL train/holdout split (no random shuffle) — financial data is
     autocorrelated; a random split leaks future info and inflates AUC.
  2. PER-SYMBOL models + SCALE-FREE features (ATR-normalized / ratios), so the
     model learns entry QUALITY, not "which symbol is this" from raw indicator
     scale (macd/osma/atr differ by orders of magnitude across symbols).
  3. A meaningful keep-bar (AUC >= 0.58) AND minimum holdout wins/losses, so a
     coin-flip model never goes live.
  4. Conservative live authority: a small confidence NUDGE (not a 50/50 blend) and
     a veto only for genuinely low P(win), both config-gated and only active once
     the model has a real sample. Trust can be raised once it proves out live.

sklearn (train) + skl2onnx (export) + onnxruntime (infer) are optional/non-fatal:
if any is missing, predict() returns None and the engine uses its normal confidence.
"""

from __future__ import annotations

import os
import json
import logging
import sqlite3

logger = logging.getLogger("onnx_predictor")


def _fingerprint(s: dict) -> list:
    """
    SCALE-FREE entry features (comparable across symbols). Raw macd/osma/ema/atr/
    power values differ by orders of magnitude per symbol, so we express them as
    ratios of ATR (or price), never raw. RSI is already 0-100.
    """
    atr = float(s.get("atr", 0) or 0) or 1e-9
    close = float(s.get("close", 0) or 0) or float(s.get("ema_fast", 0) or 0) or 1e-9
    macd = float(s.get("macd_line", 0) or 0)
    osma = float(s.get("osma", 0) or 0)
    osma_prev = float(s.get("osma_prev", 0) or 0)
    ema = float(s.get("ema_fast", 0) or 0)
    ema_prev = float(s.get("ema_prev", 0) or 0)
    bulls = float(s.get("bulls_power", 0) or 0)
    bears = float(s.get("bears_power", 0) or 0)
    rsi = float(s.get("rsi", 50) or 50)
    return [
        macd / atr,                       # MACD in ATR units
        osma / atr,                       # OsMA in ATR units
        (osma - osma_prev) / atr,         # OsMA slope in ATR units
        (ema - ema_prev) / atr,           # EMA slope in ATR units
        (close - ema) / atr,              # price stretch from EMA in ATR units
        bulls / atr,                      # buyer control in ATR units
        bears / atr,                      # seller control in ATR units
        (rsi - 50.0) / 50.0,              # RSI centered/normalized to [-1,1]
        1.0 if osma > 0 else -1.0,        # OsMA side of zero
        1.0 if macd > 0 else -1.0,        # MACD side of zero
    ]


N_FEATURES = 10


def _model_dir() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    d = os.path.join(base, "models")
    os.makedirs(d, exist_ok=True)
    return d


def _key(symbol: str) -> str:
    return (symbol or "GLOBAL").upper()[:6]


class OnnxOutcomePredictor:
    def __init__(self, experience_db, min_trades: int = 80, min_auc: float = 0.58,
                 min_holdout_per_class: int = 8):
        self.db = experience_db
        self.min_trades = min_trades
        self.min_auc = min_auc
        self.min_holdout_per_class = min_holdout_per_class
        self._dir = _model_dir()
        self._sess = {}    # symbol -> onnxruntime session
        self._meta = {}    # symbol -> meta dict
        self._load_all()

    def _paths(self, sym: str):
        k = _key(sym)
        return (os.path.join(self._dir, f"outcome_{k}.onnx"),
                os.path.join(self._dir, f"outcome_{k}.meta.json"))

    # ── inference ──
    def _load_all(self):
        try:
            for f in os.listdir(self._dir):
                if f.startswith("outcome_") and f.endswith(".onnx"):
                    sym = f[len("outcome_"):-len(".onnx")]
                    self._load_session(sym)
        except Exception as e:
            logger.debug(f"onnx load-all skip: {e}")

    def _load_session(self, sym: str):
        mp, meta_p = self._paths(sym)
        if not os.path.exists(mp):
            return
        try:
            import onnxruntime as ort
            self._sess[_key(sym)] = ort.InferenceSession(mp, providers=["CPUExecutionProvider"])
            if os.path.exists(meta_p):
                self._meta[_key(sym)] = json.load(open(meta_p))
            logger.info(f"ONNX model loaded for {_key(sym)} (AUC {self._meta.get(_key(sym), {}).get('auc')})")
        except Exception as e:
            logger.debug(f"onnx session load skip {sym}: {e}")

    def predict_win_prob(self, indicators: dict):
        """P(win) in [0,1] for this symbol's model, or None if no model for it."""
        sym = _key(indicators.get("symbol", ""))
        sess = self._sess.get(sym)
        if sess is None:
            return None
        try:
            import numpy as np
            x = np.array([_fingerprint(indicators)], dtype="float32")
            out = sess.run(None, {sess.get_inputs()[0].name: x})
            probs = out[1]
            if isinstance(probs, list) and probs and isinstance(probs[0], dict):
                return float(probs[0].get(1, probs[0].get(True, 0.5)))
            return float(probs[0][1])
        except Exception as e:
            logger.debug(f"onnx predict skip {sym}: {e}")
            return None

    def model_trades(self, indicators: dict) -> int:
        """Training sample size behind this symbol's model (0 if none) — lets the
        engine scale trust with maturity."""
        return int(self._meta.get(_key(indicators.get("symbol", "")), {}).get("n_trades", 0))

    # ── training (per symbol, chronological) ──
    def _load_symbol_rows(self, sym_prefix: str):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        try:
            ac, ap = self.db._account_clause()
        except Exception:
            ac, ap = "", []
        rows = conn.execute(
            "SELECT outcome, indicators_snapshot FROM trades "
            "WHERE outcome IN ('win','loss') AND symbol LIKE ? "
            "AND (exit_reason IS NULL OR exit_reason<>'pre_rebuild_synthetic') "
            "AND indicators_snapshot IS NOT NULL AND indicators_snapshot!=''" + ac +
            " ORDER BY id ASC",            # CHRONOLOGICAL order (id is insertion order)
            [sym_prefix + "%"] + ap).fetchall()
        conn.close()
        X, y = [], []
        for r in rows:
            try:
                s = json.loads(r["indicators_snapshot"])
            except Exception:
                continue
            X.append(_fingerprint(s))
            y.append(1 if r["outcome"] == "win" else 0)
        return X, y

    def train_symbol(self, symbol: str) -> dict:
        """Train a PER-SYMBOL model with a CHRONOLOGICAL holdout; keep only if it
        clears the AUC bar, has enough holdout wins/losses, and beats the incumbent."""
        try:
            import numpy as np
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.metrics import roc_auc_score
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
        except Exception as e:
            return {"trained": False, "reason": f"deps unavailable: {e}"}

        k = _key(symbol)
        X, y = self._load_symbol_rows(k)
        if len(X) < self.min_trades or len(set(y)) < 2:
            return {"trained": False, "symbol": k, "reason": f"insufficient data ({len(X)})"}
        X = np.array(X, dtype="float32"); y = np.array(y)
        # CHRONOLOGICAL split: train on the older 70%, validate on the newer 30%.
        cut = int(len(X) * 0.7)
        Xtr, Xte, ytr, yte = X[:cut], X[cut:], y[:cut], y[cut:]
        # holdout must contain enough of BOTH classes to trust the AUC
        if int((yte == 1).sum()) < self.min_holdout_per_class or \
           int((yte == 0).sum()) < self.min_holdout_per_class or len(set(ytr)) < 2:
            return {"trained": False, "symbol": k, "reason": "holdout too thin / one-class"}
        clf = GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.08)
        clf.fit(Xtr, ytr)
        try:
            auc = round(float(roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])), 3)
        except Exception:
            auc = 0.5

        prev = self._meta.get(k, {}).get("auc", 0.0)
        if auc < max(prev, self.min_auc) - 0.005:
            return {"trained": True, "kept": False, "symbol": k, "auc": auc, "prev_auc": prev,
                    "reason": f"AUC {auc} below bar {self.min_auc}/incumbent {prev}"}

        onx = convert_sklearn(clf, initial_types=[("input", FloatTensorType([None, N_FEATURES]))],
                              options={id(clf): {"zipmap": False}})
        mp, meta_p = self._paths(k)
        with open(mp, "wb") as f:
            f.write(onx.SerializeToString())
        self._meta[k] = {"auc": auc, "n_trades": len(X), "holdout": len(yte),
                         "split": "chronological", "n_features": N_FEATURES}
        json.dump(self._meta[k], open(meta_p, "w"), indent=2)
        self._load_session(k)
        logger.warning(f"[ONNX] {k}: retrained (chronological) AUC {auc} (prev {prev}) "
                       f"n={len(X)} -> kept + live")
        return {"trained": True, "kept": True, "symbol": k, "auc": auc, "prev_auc": prev, "n": len(X)}

    def train_all(self, symbols) -> dict:
        out = {}
        for s in symbols:
            try:
                out[_key(s)] = self.train_symbol(s)
            except Exception as e:
                out[_key(s)] = {"trained": False, "reason": str(e)[:80]}
        return out

    def status(self) -> dict:
        return {"models": {k: {"auc": m.get("auc"), "n": m.get("n_trades")}
                           for k, m in self._meta.items()},
                "loaded": list(self._sess.keys())}
