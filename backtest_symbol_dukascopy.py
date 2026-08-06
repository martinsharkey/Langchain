"""
Baseline a symbol through the REAL Backtester (Backtester.walkforward_focused) on
Dukascopy data — the same validated engine the live adaptive loop uses, just fed by
Dukascopy instead of MT5. This is the faithful per-symbol baseline (correct tick fills,
focused pockets, manager exits, walk-forward windows) — NOT a hand-rolled approximation.

Usage: python backtest_symbol_dukascopy.py SYMBOL [end_date] [days] [timeframe] [bars]
  e.g. python backtest_symbol_dukascopy.py BTCUSD 2026-07-25 11 M15 900
"""
import sys
from datetime import datetime, timezone

from src.data_sources.dukascopy import DukascopySource
from src.learning.backtester import Backtester
from src.learning.param_optimizer import SYMBOL_BASELINES, DEFAULTS
from src.learning.strategy_registry import StrategyRegistry


def run(symbol, end_date="2026-07-25", timeframe="M15", bars=900):
    base = symbol.upper().split("-")[0]
    until = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    src = DukascopySource(until=until, use_cache=True)

    registry = StrategyRegistry()
    bt = Backtester(registry, rates_fn=src.get_rates, ticks_fn=src.get_ticks)

    params = dict(DEFAULTS); params.update(SYMBOL_BASELINES.get(base, {}))
    print(f"[{base}] real walkforward_focused on Dukascopy — {timeframe} x{bars} bars ending {end_date}")
    res = bt.walkforward_focused(base, params, sl_atr=params.get("sl_atr", 1.0),
                                 tp_rr=params.get("tp_rr", 2.0), timeframe=timeframe,
                                 bars=bars, windows=3)
    if not res:
        print("  no result (insufficient data / no focused rules)")
        return
    print(f"  windows PF: {[round(p,2) for p in res.get('pfs',[])]}")
    print(f"  windows WR: {[round(w,1) for w in res.get('wrs',[])]}")
    print(f"  n_total={res.get('n_total')} generalizes={res.get('generalizes')} "
          f"score(minPF)={res.get('score'):.2f}")


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        print("usage: backtest_symbol_dukascopy.py SYMBOL [end] [tf] [bars]"); sys.exit(1)
    run(a[1], a[2] if len(a) > 2 else "2026-07-25",
        a[3] if len(a) > 3 else "M15", int(a[4]) if len(a) > 4 else 900)
