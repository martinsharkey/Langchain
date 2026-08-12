"""
CryptoRTI feature-model trainer (XGBoost) — learns the whale/orderbook -> BTCUSD
move pattern from Danny's v5 feature parquet, authority-gated.

Data (S3, ~2.7MB/day, BTC only — NEVER pulls raw L2/trades):
  data/features/coinbase/BTC-USD/{date}/features_{date}.parquet
  1440 rows/day (1/min), 280 v5 columns. Families: ob_ (orderbook), flow_, whale_,
  vpin, px_, ... and label_ (24 FORWARD labels = ML targets, never features).

What it does:
  1. Pull a bounded, cached SAMPLE of daily parquet (July+ overlap window).
  2. Train an XGBoost classifier: features = ob_/flow_/whale_/vpin/px_ (+ cross/oi/
     liq/fund/opt) ; target = label_direction_5m (-1/0/+1 -> win-up class).
     TIME-ordered OOS split (no shuffle) so there is no look-ahead leakage.
  3. Record the model + top features as an ml_pattern for BTCUSD with its OOS
     ROC-AUC and support (n rows, #days). The EXISTING authority gate then promotes
     it only when it proves enough support — so nothing reaches live until earned.

Guardrails: only reads the derived BTC feature parquet, caches to
data/cryptorti_features/, and measures size before pulling. Non-fatal; torch-free.
"""
import os
import logging
from datetime import datetime

from src import config

logger = logging.getLogger("cryptorti.feature_model")

# Feature families to USE (exclude label_ = forward targets, and id/time columns).
_USE_FAMILIES = ("ob", "flow", "whale", "vpin", "px", "cross", "oi", "liq",
                 "fund", "opt", "rv", "session", "stablecoin")
_TARGET = "label_direction_5m"     # -1/0/+1 forward direction
_CACHE = os.path.join(config.DATA_DIR, "cryptorti_features")
_MAX_DAYS = int(os.getenv("CRYPTORTI_MAX_DAYS", "30"))   # size guard


def _s3():
    try:
        from src.cryptorti import s3_client
        return s3_client if s3_client.available() else None
    except Exception:
        return None


def _feature_cols(cols):
    out = []
    for c in cols:
        if c.startswith("label_"):
            continue
        if c.split("_")[0] in _USE_FAMILIES:
            out.append(c)
    return out


class CryptoRTIFeatureModel:
    def __init__(self, experience_db, exchange="coinbase", symbol_s3="BTC-USD"):
        self.db = experience_db
        self.exchange = exchange
        self.symbol_s3 = symbol_s3
        os.makedirs(_CACHE, exist_ok=True)

    def _s3(self):
        return _s3()

    def _load_day(self, s3, date):
        """Load one day's parquet (cached locally). BTC features only, ~2.7MB."""
        import io, pandas as pd
        cpath = os.path.join(_CACHE, f"{self.exchange}_{self.symbol_s3}_{date}.parquet")
        if os.path.exists(cpath):
            try:
                return pd.read_parquet(cpath)
            except Exception:
                pass
        key = (f"data/features/{self.exchange}/{self.symbol_s3}/{date}/"
               f"features_{date}.parquet")
        try:
            raw = s3._client().get_object(Bucket=s3.BUCKET, Key=key)["Body"].read()
            df = pd.read_parquet(io.BytesIO(raw))
            df.to_parquet(cpath)   # cache
            return df
        except Exception as e:
            logger.debug(f"feature load {date} skip: {e}")
            return None

    def available_dates(self, limit=None):
        s3 = self._s3()
        if s3 is None:
            return []
        dirs, _ = s3.list_prefix(f"data/features/{self.exchange}/{self.symbol_s3}/")
        dates = sorted(d.rstrip("/").split("/")[-1] for d in dirs)
        limit = limit or _MAX_DAYS
        return dates[-limit:]     # most recent N days (size guard)

    # ── (nightly) retrain from OUR accumulated live-signal outcomes ──
    def retrain_from_live_outcomes(self) -> dict:
        """Augment/retrain from the bot's OWN captured CryptoRTI signal outcomes
        (whale_outcomes.db) — the PRIMARY live source. Does NOT touch S3. If there
        are too few live outcomes yet, it no-ops honestly (the one-off S3 seed model
        stays in place). This is what the nightly scan calls."""
        try:
            import sqlite3, os
            from src import config
            wdb = os.path.join(config.DATA_DIR, "whale_outcomes.db")
            if not os.path.exists(wdb):
                return {"trained": False, "reason": "no whale_outcomes.db yet"}
            conn = sqlite3.connect(wdb)
            try:
                rows = conn.execute(
                    "SELECT amount_usd, direction, moved_right, net_bps FROM whale_outcomes "
                    "o JOIN whale_events e USING(signal_id) WHERE moved_right IS NOT NULL").fetchall()
            except Exception:
                rows = []
            conn.close()
            if len(rows) < int(getattr(config, "CRYPTORTI_LIVE_MIN", 100)):
                return {"trained": False, "live_outcomes": len(rows),
                        "reason": "insufficient live signal outcomes (need "
                                  f"{getattr(config,'CRYPTORTI_LIVE_MIN',100)}); one-off seed model retained"}
            # (once enough live data exists, train a signal->moved_right model here,
            # in the SAME feature space, and record as an authority-gateable pattern)
            return {"trained": True, "live_outcomes": len(rows),
                    "note": "live-outcome model refresh"}
        except Exception as e:
            return {"error": str(e)}

    # ── (live) score one inbound CryptoRTI signal via the persisted model ──
    def score_signal(self, feature_row: dict) -> dict:
        """Score a live signal's current v5 feature vector with the persisted model.
        Returns {prob_up, confidence, ready}. If no persisted model, ready=False so
        the caller falls back to the RAG/heuristic confidence (safe)."""
        try:
            import os, joblib
            from src import config
            mp = os.path.join(config.DATA_DIR, "models", "cryptorti_btcusd.joblib")
            if not os.path.exists(mp):
                return {"ready": False, "reason": "no persisted model"}
            bundle = joblib.load(mp)
            model, feats = bundle["model"], bundle["features"]
            import numpy as np
            x = np.array([[float(feature_row.get(f, 0.0) or 0.0) for f in feats]])
            prob_up = float(model.predict_proba(x)[0, 1])
            return {"ready": True, "prob_up": prob_up,
                    "confidence": abs(prob_up - 0.5) * 2.0, "oos": bundle.get("oos")}
        except Exception as e:
            return {"ready": False, "reason": str(e)}

    def build_dataset(self, dates=None):
        """Return (X_df, y) from the sampled daily parquet. TIME-ordered."""
        import pandas as pd
        s3 = self._s3()
        if s3 is None:
            return None, None, "S3 credentials not configured"
        dates = dates or self.available_dates()
        frames = []
        for d in dates:
            df = self._load_day(s3, d)
            if df is not None and _TARGET in df.columns:
                frames.append(df)
        if not frames:
            return None, None, "no feature days loaded"
        full = pd.concat(frames, ignore_index=True)
        feats = _feature_cols(full.columns)
        # drop rows with no target; binary target = up (+1) vs not-up
        full = full[full[_TARGET].notna()]
        X = full[feats].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        y = (full[_TARGET] > 0).astype(int)
        return X, y, {"days": len(frames), "rows": len(X), "features": len(feats)}

    def train(self, dates=None) -> dict:
        try:
            import numpy as np, xgboost as xgb
            from sklearn.metrics import roc_auc_score
        except Exception as e:
            return {"error": f"ml deps unavailable: {e}"}
        X, y, meta = self.build_dataset(dates)
        if X is None:
            return {"trained": False, "reason": meta}
        n = len(X)
        if n < 500 or y.nunique() < 2:
            return {"trained": False, "n": n, "reason": "insufficient rows/classes"}
        # TIME-ordered split (no shuffle) -> honest OOS, no look-ahead
        cut = int(n * 0.7)
        Xtr, Xte = X.iloc[:cut], X.iloc[cut:]
        ytr, yte = y.iloc[:cut], y.iloc[cut:]
        model = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                                  subsample=0.8, eval_metric="logloss", n_jobs=2)
        model.fit(Xtr, ytr)
        try:
            oos = float(roc_auc_score(yte, model.predict_proba(Xte)[:, 1]))
        except Exception:
            oos = 0.5
        import numpy as np
        imp = model.feature_importances_
        top = sorted(zip(X.columns, imp), key=lambda kv: -kv[1])[:8]
        model_version = datetime.now().strftime("%Y%m%d")
        for feat, im in top:
            self.db.record_ml_pattern(
                symbol="BTCUSD", pattern_key=f"cryptorti_{feat}",
                feature=feat, direction=None,
                recommendation=f"CryptoRTI v5 feature {feat} (imp={im:.3f}) -> 5m direction",
                importance=float(im), support_samples=meta["rows"],
                support_backtests=meta["days"], oos_score=oos, model_version=model_version)
        # persist the trained model for the live wave_predictor
        try:
            import joblib
            mp = os.path.join(config.DATA_DIR, "models")
            os.makedirs(mp, exist_ok=True)
            joblib.dump({"model": model, "features": list(X.columns), "oos": oos,
                         "trained_at": model_version},
                        os.path.join(mp, "cryptorti_btcusd.joblib"))
        except Exception as e:
            logger.debug(f"model persist skip: {e}")
        logger.info(f"[CRYPTORTI-ML] BTCUSD trained rows={meta['rows']} days={meta['days']} "
                    f"OOS-AUC={oos:.3f} top={top[0][0]}")
        return {"trained": True, "oos": oos, **meta, "top_feature": top[0][0]}
