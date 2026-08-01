"""
Tests for the ONNX outcome predictor (#42) — per-symbol, chronological, scale-free.
Skips gracefully if optional deps missing.
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


def _make_db(path, symbol="BTCUSD", n=200):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
                    outcome TEXT, exit_reason TEXT, indicators_snapshot TEXT)""")
    random.seed(1)
    for i in range(n):
        win = i % 2 == 0
        # separable in SCALE-FREE space: strong macd/osma relative to ATR -> win.
        # different atr scale to prove normalization works.
        atr = 50.0 if symbol == "BTCUSD" else 2.0
        snap = {"macd_line": (atr * 1.5 if win else -atr * 1.5) + random.uniform(-atr*0.2, atr*0.2),
                "osma": (atr * 0.8 if win else -atr * 0.8),
                "osma_prev": -atr * 0.1, "ema_fast": 1000, "ema_prev": 999, "atr": atr,
                "bulls_power": (atr * 1.2 if win else -atr * 0.4), "bears_power": atr * 0.05,
                "rsi": (58 if win else 42), "close": 1000}
        conn.execute("INSERT INTO trades (symbol, outcome, exit_reason, indicators_snapshot) VALUES (?,?,?,?)",
                     (symbol, "win" if win else "loss", "tp" if win else "sl", json.dumps(snap)))
    conn.commit(); conn.close()


@pytest.mark.skipif(not HAVE, reason="skl2onnx/onnxruntime/sklearn not installed")
def test_per_symbol_train_chronological_and_predict():
    from src import config
    d = tempfile.mkdtemp(); orig = config.DATA_DIR
    try:
        config.DATA_DIR = d
        dbp = os.path.join(d, "e.db"); _make_db(dbp, "BTCUSD", 200)
        from src.learning.onnx_predictor import OnnxOutcomePredictor
        p = OnnxOutcomePredictor(_DB(dbp), min_trades=50, min_auc=0.58)
        res = p.train_symbol("BTCUSD")
        assert res["trained"] and res["kept"], res
        assert res["auc"] >= 0.58, res
        assert p._meta["BTCUSD"]["split"] == "chronological"
        # winning fingerprint (ATR-relative) scores higher than losing
        pw = p.predict_win_prob({"symbol": "BTCUSD", "macd_line": 75, "osma": 40, "osma_prev": -5,
                                 "ema_fast": 1000, "ema_prev": 999, "atr": 50,
                                 "bulls_power": 60, "bears_power": 2.5, "rsi": 58, "close": 1000})
        pl = p.predict_win_prob({"symbol": "BTCUSD", "macd_line": -75, "osma": -40, "osma_prev": 5,
                                 "ema_fast": 1000, "ema_prev": 1001, "atr": 50,
                                 "bulls_power": -20, "bears_power": 2.5, "rsi": 42, "close": 1000})
        assert pw is not None and pl is not None and pw > pl, (pw, pl)
        # a DIFFERENT symbol has no model -> None (per-symbol isolation)
        assert p.predict_win_prob({"symbol": "XAUUSD", "atr": 2, "macd_line": 3}) is None
    finally:
        config.DATA_DIR = orig
        shutil.rmtree(d, ignore_errors=True)


def test_no_model_returns_none():
    from src import config
    d = tempfile.mkdtemp(); orig = config.DATA_DIR
    try:
        config.DATA_DIR = d
        dbp = os.path.join(d, "e.db"); _make_db(dbp, "BTCUSD", 5)
        from src.learning.onnx_predictor import OnnxOutcomePredictor
        p = OnnxOutcomePredictor(_DB(dbp), min_trades=50)
        assert p.predict_win_prob({"symbol": "BTCUSD", "atr": 1}) is None
    finally:
        config.DATA_DIR = orig
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(not HAVE, reason="deps")
def test_thin_holdout_not_kept():
    from src import config
    d = tempfile.mkdtemp(); orig = config.DATA_DIR
    try:
        config.DATA_DIR = d
        dbp = os.path.join(d, "e.db"); _make_db(dbp, "BTCUSD", 90)
        from src.learning.onnx_predictor import OnnxOutcomePredictor
        # require 40 per class in holdout -> impossible with 90*0.3 rows -> not kept
        p = OnnxOutcomePredictor(_DB(dbp), min_trades=50, min_holdout_per_class=40)
        res = p.train_symbol("BTCUSD")
        assert res.get("kept") is not True
    finally:
        config.DATA_DIR = orig
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if HAVE:
        test_per_symbol_train_chronological_and_predict()
        test_thin_holdout_not_kept()
    test_no_model_returns_none()
    print("onnx predictor tests passed")
