"""B3: Run clean XAUUSD optimize baseline on the trading host.

Usage (on trading host, with MT5 logged in):
    python scripts/run_xauusd_baseline.py

This will:
1. Load current XAUUSD params from tuned_params.json
2. Run walkforward_focused backtest
3. Log: generalizes, pfs (per window), score (min PF), n_total, session_scores
4. Print results to stdout for the LEARNING_LOG
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.strategy_registry import StrategyRegistry
from src.learning.backtester import Backtester
from src.learning.param_optimizer import ParameterOptimizer
from src import config
from src.mt5.connector import get_connector

def main():
    # Initialize MT5 connection first
    conn = get_connector()
    ok = conn.initialize()
    if not ok:
        print("ERROR: Cannot connect to MT5. Ensure terminal is running and logged in.")
        sys.exit(1)
    print(f"MT5 connected: account={conn.get_account_info().get('login')} "
          f"server={conn.get_account_info().get('server')}")

    reg = StrategyRegistry()
    bt = Backtester(registry=reg)
    opt = ParameterOptimizer(
        registry=reg,
        backtest_fn=lambda sym, params, sl_atr, tp_rr: bt.walkforward_focused(
            sym, params, sl_atr=sl_atr, tp_rr=tp_rr),
    )

    symbol = "XAUUSD"
    base = opt.current_params(symbol)
    print(f"=== B3: Clean XAUUSD Optimize Baseline ===")
    print(f"Symbol: {symbol}")
    print(f"Base params keys: {list(base.keys())[:10]}...")

    res = bt.walkforward_focused(symbol, base, sl_atr=base.get("sl_atr", 1.0), tp_rr=base.get("tp_rr", 2.0))
    if not res:
        print("ERROR: backtest returned None (insufficient data?)")
        sys.exit(1)

    print(f"generalizes: {res.get('generalizes')}")
    print(f"pfs: {res.get('pfs')}")
    print(f"wrs: {res.get('wrs')}")
    print(f"score (min PF): {res.get('score')}")
    print(f"n_total: {res.get('n_total')}")
    sess = res.get("session_scores")
    if sess:
        print(f"session_scores:")
        for s, d in sess.items():
            print(f"  {s}: trades={d.get('trades')} pf={d.get('pf')} wr={d.get('wr')}%")
    else:
        print("session_scores: None")

    # Also run optimize() to see if cold-start fires
    print(f"\n=== Running optimize() ===")
    result = opt.optimize(symbol, iterations=6)
    print(f"optimize result: improved={result.get('improved')} score={result.get('score')} tried={result.get('tried')}")
    if result.get("improved"):
        print(f"new params: {result.get('params')}")
        print(f"pfs: {result.get('pfs')}")

if __name__ == "__main__":
    main()
