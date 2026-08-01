"""
ONNX trade-outcome predictor (#42) — a LEARNED entry confidence.

The hand-weighted confidence was shown to be anti-calibrated (higher confidence ->
worse outcomes). This replaces/augments it with a model TRAINED on real closed
trades: given an entry's fingerprint (the OsMA-confluence indicator state + MTF
alignment), predict P(win). Exported to ONNX so onnxruntime scores each candidate
entry at microsecond latency in the hot path — portable + offline (standalone/VPS).

Self-improving + safe: retrain on a cadence as trades accumulate; keep the new
model ONLY if it beats the incumbent on a holdout split (mirrors the #27
checkpointer verify/revert philosophy — never blindly trust a fresh model).

Dependency-light: sklearn (train) + skl2onnx (export) + onnxruntime (infer), all
optional/non-fatal. If unavailable, predict() returns None and the engine falls
back to the existing confidence.
"""

from __future__ import annotations

import os
import json
import logging
import sqlite3

logger = logging.getLogger("onnx_predictor")

# entry-fingerprint features pulled from the trade's indicators_snapshot
FEATURES = [
    "macd_line", "osma", "osma_prev", "ema_fast", "ema_prev", "atr",
    "bulls_power", "bears_power", "rsi",
]


def _model_dir() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    d = os.path.join(base, "models")
    os.makedirs(d, exist_ok=True)
    return d


class OnnxOutcomePredictor:
    def __init__(self, experience_db, min_trades: int = 60):
        self.db = experience_db
        self.min_trades = min_trades
        self.model_path = os.path.join(_model_dir(), "outcome.onnx")
        self.meta_path = os.path.join(_model_dir(), "outcome.meta.json")
        self._sess = None
        self._meta = self._load_meta()
        self._load_session()

    # ── inference ──
    def _load_meta(self) -> dict:
        try:
            if os.path.exists(self.meta_path):
                return json.load(open(self.meta_path))
        except Exception:
            pass
        return {}

    def _load_session(self):
        if not os.path.exists(self.model_path):
            return
        try:
            import onnxruntime as ort
            self._sess = ort.InferenceSession(self.model_path,
                                              providers=["CPUExecutionProvider"])
            logger.info(f"ONNX outcome model loaded (holdout AUC {self._meta.get('auc')})")
        except Exception as e:
            logger.debug(f"onnx session load skip: {e}")
            self._sess = None

    def predict_win_prob(self, indicators: dict):
        """Return P(win) in [0,1] for a candidate entry, or None if unavailable."""
        if self._sess is None:
            return None
        try:
            import numpy as np
            x = np.array([[float(indicators.get(f, 0) or 0) for f in FEATURES]], dtype="float32")
            out = self._sess.run(None, {self._sess.get_inputs()[0].name: x})
            # skl2onnx classifier: out[1] is probabilities (list of dicts or array)
            probs = out[1]
            if isinstance(probs, list) and probs and isinstance(probs[0], dict):
                return float(probs[0].get(1, probs[0].get(True, 0.5)))
            return float(probs[0][1])
        except Exception as e:
            logger.debug(f"onnx predict skip: {e}")
            return None

    # ── training (cadence) ──
    def _load_training_data(self):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        try:
            ac, ap = self.db._account_clause()
        except Exception:
            ac, ap = "", []
        rows = conn.execute(
            "SELECT outcome, indicators_snapshot FROM trades "
            "WHERE outcome IN ('win','loss') "
            "AND (exit_reason IS NULL OR exit_reason<>'pre_rebuild_synthetic') "
            "AND indicators_snapshot IS NOT NULL AND indicators_snapshot!=''" + ac,
            ap).fetchall()
        conn.close()
        X, y = [], []
        for r in rows:
            try:
                s = json.loads(r["indicators_snapshot"])
            except Exception:
                continue
            X.append([float(s.get(f, 0) or 0) for f in FEATURES])
            y.append(1 if r["outcome"] == "win" else 0)
        return X, y

    def train(self) -> dict:
        """Train, export to ONNX, and KEEP only if it beats the incumbent on holdout."""
        try:
            import numpy as np
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
        except Exception as e:
            return {"trained": False, "reason": f"deps unavailable: {e}"}

        X, y = self._load_training_data()
        if len(X) < self.min_trades or len(set(y)) < 2:
            return {"trained": False, "reason": f"insufficient/one-class data ({len(X)} trades)"}
        X = np.array(X, dtype="float32"); y = np.array(y)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
        clf = GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.08)
        clf.fit(Xtr, ytr)
        try:
            auc = round(float(roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])), 3)
        except Exception:
            auc = 0.5

        # verify/revert: only keep if it beats the incumbent holdout AUC (+ margin)
        prev_auc = self._meta.get("auc", 0.0)
        if auc < max(prev_auc, 0.55) - 0.01:
            return {"trained": True, "kept": False, "auc": auc, "prev_auc": prev_auc,
                    "reason": "did not beat incumbent / below 0.55 edge floor"}

        onx = convert_sklearn(clf, initial_types=[("input", FloatTensorType([None, len(FEATURES)]))],
                              options={id(clf): {"zipmap": False}})
        with open(self.model_path, "wb") as f:
            f.write(onx.SerializeToString())
        self._meta = {"auc": auc, "n_trades": len(X), "features": FEATURES}
        json.dump(self._meta, open(self.meta_path, "w"), indent=2)
        self._load_session()
        logger.warning(f"[ONNX] retrained outcome model: holdout AUC {auc} "
                       f"(prev {prev_auc}), n={len(X)} -> kept + live")
        return {"trained": True, "kept": True, "auc": auc, "prev_auc": prev_auc, "n": len(X)}

    def status(self) -> dict:
        return {"loaded": self._sess is not None, "auc": self._meta.get("auc"),
                "n_trades": self._meta.get("n_trades")}
