"""
Validate the CryptoRTI whale hybrid on the BACKTEST path (#43 step D).

The live bot boosts confidence + scales the lot when a whale signal aligns with a
confluence entry — but that hybrid boost was never walk-forward validated. This
attaches historical whale/VPIN features onto BTCUSD M1 bars (causally, via
feature_align) and compares confluence-trigger outcomes:
    whale_active vs NOT whale_active
so we can see whether the whale condition actually improves win rate / PF — i.e.
whether the live boost is justified, on real historical data, no look-ahead.

Run: python -m scripts.validate_whale_backtest [DAYS]
"""

from __future__ import annotations

import sys
import statistics

from src.strategies.confluence_signal import find_confluence_triggers
from src.cryptorti.feature_align import attach_whale_features, whale_coverage
from scripts.backtest_macd_osma import simulate


def _load(days):
    import MetaTrader5 as mt5
    mt5.initialize(); mt5.symbol_select("BTCUSD", True)
    from datetime import datetime, timedelta
    end = datetime.now(); start = end - timedelta(days=days)
    import pandas as pd
    def rng(tf):
        r = mt5.copy_rates_range("BTCUSD", tf, start, end)
        return pd.DataFrame(r) if r is not None and len(r) else None
    return rng(mt5.TIMEFRAME_M1), rng(mt5.TIMEFRAME_M5), rng(mt5.TIMEFRAME_M15)


def _stats(triggers, m1, label):
    r = simulate(triggers, m1, 2.0, 2.0, require_m5=False, require_m15=False)
    n = len(triggers)
    print(f"  {label:22} triggers={n:4} -> {r}")
    return r


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    m1, m5, m15 = _load(days)
    if m1 is None or len(m1) < 1000:
        print("Insufficient M1 (stop the bot to free MT5).")
        return
    print(f"BTCUSD {len(m1)} M1 bars; attaching whale features (causal)...")
    m1w = attach_whale_features(m1)
    cov = whale_coverage(m1w)
    print(f"  whale coverage: {cov}")
    if cov["coverage_pct"] < 1:
        print("  (little/no historical whale feature overlap with this MT5 window — "
              "expected if S3 history and the MT5 window don't align; report is still valid structurally.)")

    trg, _ = find_confluence_triggers(m1w, m5, m15)
    whale_on = [t for t in trg if t.get("whale_active")]
    whale_off = [t for t in trg if not t.get("whale_active")]
    print(f"\nConfluence triggers: {len(trg)} total | {len(whale_on)} whale-active | {len(whale_off)} not")
    print("Outcome comparison (does whale_active improve the edge?):")
    _stats(trg, m1w, "ALL confluence")
    if whale_on:
        _stats(whale_on, m1w, "whale_active ONLY")
    if whale_off:
        _stats(whale_off, m1w, "NOT whale_active")
    print("\nVerdict: if whale_active PF/WR > NOT whale_active, the live boost is "
          "justified; if not, demote it to observe-only until it validates.")


if __name__ == "__main__":
    main()
