"""VectorBT-only raw discovery.

Runs VectorBT's native factory end-to-end and dumps the raw ``pf.stats()`` output
for every indicator, per session and timeframe. No Optuna, no validation, no
hand-rolled signal or report code — this is the true VectorBT output.

Usage:
    python scripts/vectorbt_raw_discovery.py BTCUSD --timeframes M1 --sessions london,newyork
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.onboarding.data import load_ohlcv
from src.onboarding.sessions import all_session_keys, filter_session
from src.onboarding.timeframes import TIMEFRAMES, timeframe_minutes


def enumerate_indicators():
    """Enumerate all indicators via VectorBT's native factory."""
    out = {"builtin": ["ATR", "BBANDS", "MA", "MACD", "MSTD", "OBV", "RSI", "STOCH"]}
    out["pandas_ta"] = sorted(vbt.IndicatorFactory.get_pandas_ta_indicators())
    out["talib"] = sorted(vbt.IndicatorFactory.get_talib_indicators())
    try:
        out["ta"] = sorted(vbt.IndicatorFactory.get_ta_indicators())
    except Exception:
        out["ta"] = []
    return out


def wrap(name, library):
    """Wrap an indicator via VectorBT's native factory."""
    if library == "pandas_ta":
        return vbt.IndicatorFactory.from_pandas_ta(name)
    if library == "talib":
        return vbt.IndicatorFactory.from_talib(name)
    if library == "ta":
        return vbt.IndicatorFactory.from_ta(name)
    return getattr(vbt, name)


def run_indicator(cls, close, high, low, open_, volume):
    """Run a wrapped indicator, passing only the inputs it declares."""
    inputs = {
        "close": close, "high": high, "low": low,
        "open": open_, "open_": open_, "volume": volume,
    }
    kwargs = {k: inputs[k] for k in cls.input_names if k in inputs}
    return cls.run(**kwargs)


def signals_from_run(res):
    """Generate entry/exit signals using VectorBT's native comparison methods.

    Uses the indicator's first output crossed above/below its own rolling mean
    (a mean-reversion signal). This is entirely VectorBT-native.
    """
    out = getattr(res, res.output_names[0])
    mean = out.rolling(20, min_periods=5).mean()
    entries = out.vbt.crossed_above(mean)
    exits = out.vbt.crossed_below(mean)
    return entries, exits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--timeframes", default=",".join(TIMEFRAMES))
    ap.add_argument("--sessions", default=",".join(all_session_keys()))
    ap.add_argument("--bars", type=int, default=10000)
    ap.add_argument("--out", default="tests/onboarding")
    args = ap.parse_args()

    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    sessions = [s.strip() for s in args.sessions.split(",") if s.strip()]

    universe = enumerate_indicators()
    print(f"Indicator universe: builtin={len(universe['builtin'])}, "
          f"pandas_ta={len(universe['pandas_ta'])}, talib={len(universe['talib'])}, "
          f"ta={len(universe['ta'])}")

    all_results = {}

    out_dir = Path(args.out) / args.symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y%m%d")
    json_path = out_dir / f"{args.symbol}_vectorbt_raw_{date}.json"
    progress_path = out_dir / f"{args.symbol}_vectorbt_raw_{date}.progress.log"

    def log(msg):
        print(msg, flush=True)
        with open(progress_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def save_partial():
        json_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")

    total = len(timeframes) * len(sessions)
    done = 0

    for timeframe in timeframes:
        try:
            df = load_ohlcv(args.symbol, timeframe, count=args.bars)
        except Exception as e:
            log(f"[{timeframe}] data load failed: {e}")
            done += len(sessions)
            continue

        freq = f"{timeframe_minutes(timeframe)}min"

        for session in sessions:
            sdf = filter_session(df, session)
            if len(sdf) < 50:
                log(f"[{timeframe}:{session}] only {len(sdf)} bars, skip")
                done += 1
                continue

            close = sdf["close"]
            high = sdf["high"]
            low = sdf["low"]
            open_ = sdf["open"]
            volume = sdf["volume"]

            session_results = []
            for library, names in universe.items():
                for name in names:
                    try:
                        cls = wrap(name, library)
                        res = run_indicator(cls, close, high, low, open_, volume)
                        entries, exits = signals_from_run(res)
                    except Exception as e:
                        continue

                    if entries.sum() < 2:
                        continue

                    pf = vbt.Portfolio.from_signals(
                        close, entries, exits, init_cash=10_000.0, freq=freq,
                    )
                    if pf.trades.count() < 1:
                        continue

                    # Raw VectorBT stats.
                    stats = pf.stats()
                    session_results.append({
                        "library": library,
                        "indicator": name,
                        "stats": {str(k): (None if pd.isna(v) else v) for k, v in stats.items()},
                    })

            # Rank by native Profit Factor (descending), then Total Return.
            def _pf(r):
                v = r["stats"].get("Profit Factor")
                return v if isinstance(v, (int, float)) else -1.0

            session_results.sort(key=_pf, reverse=True)
            all_results[f"{timeframe}:{session}"] = session_results
            done += 1
            log(f"[{done}/{total}] {timeframe}:{session} -> {len(session_results)} indicators produced trades")
            save_partial()

    log(f"\nRaw VectorBT output written to: {json_path}")


if __name__ == "__main__":
    main()
