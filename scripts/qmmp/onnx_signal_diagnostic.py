"""
Step 1 diagnostic: measure ONNX signal on real floor-filtered trades.

Read-only. Does not touch scalp_engine.py, Optuna, or any live code.
Loads closed trades from trading_experience.db, reconstructs the 10 ONNX features
from the stored indicators_snapshot, calls the existing ONNX model, and computes
AUC against actual win/loss.

Usage:
    python scripts/qmmp/onnx_signal_diagnostic.py XAUUSD-ECN
    python scripts/qmmp/onnx_signal_diagnostic.py GER40.
    python scripts/qmmp/onnx_signal_diagnostic.py BTCUSD
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(REPO_ROOT, "data", "trading_experience.db")
MODEL_DIR = os.path.join(REPO_ROOT, "data", "models")

# ---------------------------------------------------------------------------
# ONNX feature reconstruction (mirrors onnx_predictor._fingerprint)
# ---------------------------------------------------------------------------
def _fingerprint(s: dict) -> list[float]:
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
        macd / atr,
        osma / atr,
        (osma - osma_prev) / atr,
        (ema - ema_prev) / atr,
        (close - ema) / atr,
        bulls / atr,
        bears / atr,
        (rsi - 50.0) / 50.0,
        1.0 if osma > 0 else -1.0,
        1.0 if macd > 0 else -1.0,
    ]


# ---------------------------------------------------------------------------
# Trade loader
# ---------------------------------------------------------------------------
def load_trades(symbol_prefix: str, strategy_filter: str | None = "OsMA_Confluence") -> list[dict]:
    """Load closed trades with indicators_snapshot from the experience DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    ac = ""
    ap = []
    try:
        from src import config
        ac, ap = config._account_clause()
    except Exception:
        pass

    where = [
        "outcome IN ('win','loss')",
        "symbol LIKE ?",
        "indicators_snapshot IS NOT NULL",
        "indicators_snapshot != ''",
        "(exit_reason IS NULL OR exit_reason <> 'pre_rebuild_synthetic')",
        "(data_source IS NULL OR data_source NOT LIKE '%SIMULATED%')",
    ]
    params = [symbol_prefix + "%"]

    if strategy_filter:
        where.append("(strategy_used = ? OR strategy_used IS NULL)")
        params.append(strategy_filter)

    sql = f"""
        SELECT id, symbol, outcome, indicators_snapshot, timestamp, profit_loss,
               strategy_used, exit_reason
        FROM trades
        WHERE {' AND '.join(where)} {ac}
        ORDER BY datetime(timestamp) ASC
    """
    rows = conn.execute(sql, params + ap).fetchall()
    conn.close()

    trades = []
    for r in rows:
        try:
            snap = json.loads(r["indicators_snapshot"])
        except Exception:
            continue
        if not snap:
            continue
        trades.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "outcome": 1 if r["outcome"] == "win" else 0,
            "snapshot": snap,
            "timestamp": r["timestamp"],
            "pnl": r["profit_loss"],
            "strategy": r["strategy_used"],
        })
    return trades


# ---------------------------------------------------------------------------
# ONNX inference
# ---------------------------------------------------------------------------
def load_onnx_session(symbol: str):
    """Load ONNX session for a symbol key (e.g. 'XAUUSD', 'GER40.', 'BTCUSD')."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("ERROR: onnxruntime not installed. pip install onnxruntime")
        sys.exit(1)

    key = symbol.upper()[:6]
    path = os.path.join(MODEL_DIR, f"outcome_{key}.onnx")
    if not os.path.exists(path):
        print(f"ERROR: No ONNX model found for {key} at {path}")
        sys.exit(1)

    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    meta_path = os.path.join(MODEL_DIR, f"outcome_{key}.meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    print(f"Loaded ONNX model for {key}: AUC={meta.get('auc')}, n_trades={meta.get('n_trades')}")
    return sess, meta


def predict_batch(sess, trades: list[dict]) -> list[float]:
    """Run ONNX inference on all trades. Returns P(win) list."""
    X = np.array([_fingerprint(t["snapshot"]) for t in trades], dtype="float32")
    input_name = sess.get_inputs()[0].name
    out = sess.run(None, {input_name: X})
    probs = out[1]
    if isinstance(probs, list) and probs and isinstance(probs[0], dict):
        return [float(p.get(1, p.get(True, 0.5))) for p in probs]
    return [float(p[1]) for p in probs]


# ---------------------------------------------------------------------------
# AUC computation
# ---------------------------------------------------------------------------
def compute_auc(y_true: list[int], y_prob: list[float]) -> float:
    """Compute AUC manually (no sklearn dependency needed for this simple metric)."""
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(y_true, y_prob))
    except ImportError:
        # Manual AUC: rank-based
        pos_scores = [p for p, y in zip(y_prob, y_true) if y == 1]
        neg_scores = [p for p, y in zip(y_prob, y_true) if y == 0]
        if not pos_scores or not neg_scores:
            return 0.5
        # Mann-Whitney U equivalent
        total = 0.0
        for ps in pos_scores:
            for ns in neg_scores:
                if ps > ns:
                    total += 1
                elif ps == ns:
                    total += 0.5
        return total / (len(pos_scores) * len(neg_scores))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_report(symbol: str, trades: list[dict], probs: list[float], meta: dict):
    y_true = [t["outcome"] for t in trades]
    auc = compute_auc(y_true, probs)

    wins = sum(y_true)
    losses = len(y_true) - wins
    avg_prob_win = np.mean([p for p, y in zip(probs, y_true) if y == 1]) if wins else 0.0
    avg_prob_loss = np.mean([p for p, y in zip(probs, y_true) if y == 0]) if losses else 0.0

    print(f"\n{'='*60}")
    print(f"ONNX Signal Diagnostic — {symbol}")
    print(f"{'='*60}")
    print(f"Trades evaluated : {len(trades)} ({wins}W / {losses}L)")
    print(f"Model AUC        : {auc:.4f}  (model's reported AUC: {meta.get('auc', 'N/A')})")
    print(f"Avg P(win) winners: {avg_prob_win:.4f}")
    print(f"Avg P(win) losers : {avg_prob_loss:.4f}")
    print(f"Separation       : {avg_prob_win - avg_prob_loss:.4f}  (higher = better discrimination)")
    print()

    if auc >= 0.58:
        print("RESULT: ONNX has REAL signal on this symbol (AUC >= 0.58).")
        print("        Wiring it into the Optuna objective is worth prototyping.")
    elif auc >= 0.55:
        print("RESULT: ONNX has WEAK signal (0.55-0.58). Borderline — may help as a"
              " nudge, not a gate.")
    else:
        print("RESULT: ONNX has NO meaningful signal (AUC < 0.55).")
        print("        Adding it to the Optuna objective would add noise, not value.")

    # Distribution of predicted probabilities
    bins = [0, 0.3, 0.5, 0.7, 0.9, 1.0]
    print(f"\nProbability distribution:")
    for i in range(len(bins) - 1):
        mask = [(p >= bins[i] and p < bins[i+1]) for p in probs]
        count = sum(mask)
        if count == 0:
            continue
        wr = sum(1 for m, y in zip(mask, y_true) if m and y == 1) / count * 100
        print(f"  [{bins[i]:.1f}-{bins[i+1]:.1f}) : {count:4d} trades, WR={wr:5.1f}%")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python onnx_signal_diagnostic.py <symbol> [--all-strategies]")
        print("  e.g. python onnx_signal_diagnostic.py XAUUSD-ECN")
        print("  e.g. python onnx_signal_diagnostic.py GER40.")
        print("  e.g. python onnx_signal_diagnostic.py BTCUSD --all-strategies")
        sys.exit(1)

    symbol = sys.argv[1]
    strategy_filter = None if "--all-strategies" in sys.argv else "OsMA_Confluence"

    print(f"Loading trades for {symbol} (strategy_filter={strategy_filter or 'ALL'})...")
    trades = load_trades(symbol, strategy_filter)
    if not trades:
        print(f"No trades found for {symbol}. Check the symbol prefix.")
        sys.exit(1)

    print(f"Loaded {len(trades)} trades. Running ONNX inference...")
    sess, meta = load_onnx_session(symbol)
    probs = predict_batch(sess, trades)

    print_report(symbol, trades, probs, meta)


if __name__ == "__main__":
    main()
