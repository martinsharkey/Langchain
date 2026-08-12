"""
Tests for the CryptoRTI v5 feature model: feature-column selection (must exclude
forward label_ columns to avoid look-ahead), target derivation, and that a trained
model records an authority-gate-able ml_pattern. Uses a synthetic parquet + temp
DB — no S3, no network.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.learning.experience_db import ExperienceDatabase
from src.cryptorti import feature_model as fm


def test_feature_cols_excludes_labels_and_offfamily():
    cols = ["ob_imbalance", "flow_delta_5m", "whale_deposit_usd_1h", "vpin",
            "px_close", "label_direction_5m", "label_price_change_1m",
            "timestamp", "random_other"]
    feats = fm._feature_cols(cols)
    assert "label_direction_5m" not in feats, "forward labels must NEVER be features (look-ahead)"
    assert "label_price_change_1m" not in feats
    assert "ob_imbalance" in feats and "flow_delta_5m" in feats and "vpin" in feats
    assert "timestamp" not in feats and "random_other" not in feats


def _synthetic_df(n=1200):
    import numpy as np, pandas as pd
    rng = np.random.default_rng(0)
    # a learnable signal: ob_imbalance positive -> up
    ob = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    up = (ob + 0.3 * noise > 0).astype(int)
    return pd.DataFrame({
        "ob_imbalance": ob,
        "flow_delta_5m": noise,
        "whale_deposit_usd_1h": rng.normal(0, 1, n),
        "vpin": rng.random(n),
        "px_close": 60000 + rng.normal(0, 50, n),
        "label_direction_5m": np.where(up == 1, 1.0, -1.0),  # target
        "label_price_change_5m": rng.normal(0, 0.1, n),
    })


def test_train_records_authority_gateable_pattern(monkeypatch, tmp_path):
    xgb = pytest.importorskip("xgboost")
    db = ExperienceDatabase(db_path=os.path.join(tempfile.mkdtemp(), "t.db"))
    model = fm.CryptoRTIFeatureModel(db)
    # bypass S3: feed the synthetic dataset directly
    df = _synthetic_df()
    monkeypatch.setattr(model, "build_dataset", lambda dates=None: (
        df[[c for c in df.columns if not c.startswith("label_")]].apply(
            __import__("pandas").to_numeric, errors="coerce").fillna(0.0),
        (df["label_direction_5m"] > 0).astype(int),
        {"days": 5, "rows": len(df), "features": 5},
    ))
    res = model.train(dates=["d1"])
    assert res.get("trained") is True, res
    # a learnable signal should beat random OOS
    assert res["oos"] > 0.55, f"OOS should show real edge on learnable data: {res}"
    # patterns were recorded for BTCUSD and can be authority-promoted
    db.record_ml_pattern("BTCUSD", "cryptorti_test", support_samples=1200,
                         support_backtests=5, oos_score=res["oos"])
    promoted = db.promote_ml_patterns(min_samples=500, min_backtests=3, min_oos_score=0.55)
    assert promoted >= 1
    auth = db.authoritative_patterns("BTCUSD")
    assert any(p["pattern_key"].startswith("cryptorti_") for p in auth)
