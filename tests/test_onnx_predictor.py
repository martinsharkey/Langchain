"""
Tests for the ONNX outcome predictor (#42). Trains on a synthetic separable
dataset, exports to ONNX, and scores. Skips gracefully if optional deps missing.
"""
import sys, os, json, sqlite3, tempfile, shutil, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

try:
    import skl2onnx, onnxruntime, sklearn  # noqa
    HAVE = True
except Exception:
    HAVE = False


class _DB:
    def __init__(self, path): self.db_path = path
    def _account_clause(self): return "", []


def _make_db(path, n=200):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY, outcome TEXT,
                    exit_reason TEXT, indicators_snapshot TEXT)""")
    random.seed(1)
    for i in range(n):
        # separable: high macd+osma+bulls -> win
        win = i % 2 == 0
        snap = {"macd_line": (2.0 if win else -2.0) + random.uniform(-0.5, 0.5),
                "osma": (1.0 if win else -1.0) + random.uniform(-0.3, 0.3),
                "osma_prev": -0.2, "ema_fast": 100, "ema_prev": 99.5, "atr": 1.0,
                "bulls_power": (3.0 if win else -1.0), "bears_power": 0.1,
                "rsi": (55 if win else 45)}
        conn.execute("INSERT INTO trades (outcome, exit_reason, indicators_snapshot) VALUES (?,?,?)",
                     ("win" if win else "loss", "tp" if win else "sl", json.dumps(snap)))
    conn.commit(); conn.close()


@pytest.mark.skipif(not HAVE, reason="skl2onnx/onnxruntime/sklearn not installed")
def test_train_export_predict():
    from src.learning.onnx_predictor import OnnxOutcomePredictor
    d = tempfile.mkdtemp()
    try:
        dbp = os.path.join(d, "e.db"); _make_db(dbp, 200)
        p = OnnxOutcomePredictor(_DB(dbp), min_trades=50)
        p.model_path = os.path.join(d, "outcome.onnx")
        p.meta_path = os.path.join(d, "outcome.meta.json")
        res = p.train()
        assert res["trained"] and res["kept"], res
        assert res["auc"] >= 0.6, res  # separable data -> strong AUC
        assert p.status()["loaded"]
        # winning fingerprint scores higher than losing
        pw = p.predict_win_prob({"macd_line": 2.0, "osma": 1.0, "osma_prev": -0.2,
                                 "ema_fast": 100, "ema_prev": 99.5, "atr": 1.0,
                                 "bulls_power": 3.0, "bears_power": 0.1, "rsi": 55})
        pl = p.predict_win_prob({"macd_line": -2.0, "osma": -1.0, "osma_prev": 0.2,
                                 "ema_fast": 100, "ema_prev": 100.5, "atr": 1.0,
                                 "bulls_power": -1.0, "bears_power": 0.1, "rsi": 45})
        assert pw is not None and pl is not None
        assert pw > pl, (pw, pl)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_model_returns_none():
    d = tempfile.mkdtemp()
    try:
        dbp = os.path.join(d, "e.db"); _make_db(dbp, 5)
        from src import config
        orig = config.DATA_DIR
        config.DATA_DIR = d  # isolate model dir so no pre-existing model loads
        from src.learning.onnx_predictor import OnnxOutcomePredictor
        p = OnnxOutcomePredictor(_DB(dbp), min_trades=50)
        assert p._sess is None
        assert p.predict_win_prob({"macd_line": 1.0}) is None  # no session
        config.DATA_DIR = orig
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if HAVE:
        test_train_export_predict()
    test_no_model_returns_none()
    print("onnx predictor tests passed")
