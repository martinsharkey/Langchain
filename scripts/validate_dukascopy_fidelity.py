"""
validate_dukascopy_fidelity.py — compare Dukascopy bars/ticks against MT5 for
the same symbol + time window and report alignment/gap/divergence metrics.

Usage:
  python -m scripts.validate_dukascopy_fidelity --symbol XAUUSD --hours 24
  python -m scripts.validate_dukascopy_fidelity --symbol BTCUSD --hours 48 --tf M5
  python -m scripts.validate_dukascopy_fidelity --symbol GER40  --hours 24 --report json

Exit codes:
  0 = fidelity within thresholds
  1 = fidelity breach
  2 = unable to fetch one or both sources
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config

try:
    from src.data_sources.dukascopy import DukascopySource, fetch_ticks, ticks_to_bars, _TF_SECONDS
except Exception:  # pragma: no cover
    DukascopySource = None  # type: ignore

try:
    from src.mt5.data import get_rates as mt5_get_rates, get_ticks as mt5_get_ticks
    from src.mt5.connector import get_connector, mt5_lock
except Exception:  # pragma: no cover
    mt5_get_rates = None  # type: ignore
    mt5_get_ticks = None  # type: ignore
    get_connector = None  # type: ignore

try:
    from src.utils.logger import get_logger
except Exception:  # pragma: no cover
    def get_logger(name):  # type: ignore
        import logging
        return logging.getLogger(name)

logger = get_logger("validate_dukascopy_fidelity")

# Defaults — tune after first runs on each symbol.
_THRESHOLDS = {
    "XAUUSD": {"max_bar_gap_frac": 0.05, "max_price_divergence": 2.0, "max_spread_divergence": 1.5},
    "BTCUSD": {"max_bar_gap_frac": 0.05, "max_price_divergence": 50.0, "max_spread_divergence": 20.0},
    "GER40":  {"max_bar_gap_frac": 0.05, "max_price_divergence": 1.5, "max_spread_divergence": 1.0},
    "EURUSD": {"max_bar_gap_frac": 0.05, "max_price_divergence": 0.0003, "max_spread_divergence": 0.0001},
    "GBPUSD": {"max_bar_gap_frac": 0.05, "max_price_divergence": 0.0003, "max_spread_divergence": 0.0001},
}

_MT5_SYMBOL_MAP = {
    "XAUUSD": "XAUUSD.crp",
    "BTCUSD": "BTCUSD",
    "GER40": "GER40.",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bars_to_lookup(bars: list[dict]) -> dict[int, dict]:
    out = {}
    for b in bars:
        ts = int(b.get("timestamp", 0))
        if ts:
            out[ts] = b
    return out


def _fetch_mt5_bars(symbol: str, tf: str, hours: int) -> list[dict]:
    if mt5_get_rates is None or get_connector is None:
        return []
    connector = get_connector()
    if not connector.is_connected():
        try:
            connector.initialize()
        except Exception:
            pass
    if not connector.is_connected():
        return []
    tf_sec = _TF_SECONDS.get(tf, 3600)
    needed = max(200, math.ceil((hours * 3600) / tf_sec) + 10)
    try:
        with mt5_lock():
            bars = mt5_get_rates(symbol, tf, needed)
        if not isinstance(bars, list):
            logger.warning("MT5 get_rates returned non-list: %r", type(bars))
            return []
    except Exception as e:
        logger.warning("MT5 get_rates failed: %s", e)
        return []
    cutoff = int((_utc_now() - timedelta(hours=hours + 1)).timestamp())
    return [b for b in bars if int(b.get("timestamp", 0)) >= cutoff]


def _fetch_dukascopy_bars(symbol: str, tf: str, hours: int) -> list[dict]:
    if DukascopySource is None:
        return []
    try:
        src = DukascopySource(until=_utc_now(), use_cache=True, workers=2)
        tf_sec = _TF_SECONDS.get(tf, 3600)
        needed = max(10, math.ceil((hours * 3600) / tf_sec) + 5)
        bars = src.get_rates(symbol, tf, count=needed)
    except Exception as e:
        logger.warning("Dukascopy get_rates failed: %s", e)
        return []
    return bars


def compare(symbol: str, tf: str = "H1", hours: int = 24) -> dict[str, Any]:
    mt5_symbol = _MT5_SYMBOL_MAP.get(symbol.upper(), symbol)
    duka_bars = _fetch_dukascopy_bars(symbol, tf, hours)
    mt5_bars = _fetch_mt5_bars(mt5_symbol, tf, hours)

    if not duka_bars and not mt5_bars:
        return {"ok": False, "error": "both sources empty", "symbol": symbol, "tf": tf, "hours": hours,
                "shared_bars": 0, "dukascopy_only_bars": 0, "mt5_only_bars": 0,
                "expected_bars": 0, "gap_frac": 1.0, "price_divergence_p99": 0.0,
                "price_divergence_median": 0.0, "spread_divergence_p99": 0.0,
                "spread_divergence_median": 0.0, "top_divergences": []}
    if not duka_bars:
        return {"ok": False, "error": "dukascopy empty", "symbol": symbol, "tf": tf, "hours": hours,
                "shared_bars": 0, "dukascopy_only_bars": 0, "mt5_only_bars": 0,
                "expected_bars": 0, "gap_frac": 1.0, "price_divergence_p99": 0.0,
                "price_divergence_median": 0.0, "spread_divergence_p99": 0.0,
                "spread_divergence_median": 0.0, "top_divergences": []}
    if not mt5_bars:
        return {"ok": False, "error": "mt5 empty", "symbol": symbol, "tf": tf, "hours": hours,
                "shared_bars": 0, "dukascopy_only_bars": 0, "mt5_only_bars": 0,
                "expected_bars": 0, "gap_frac": 1.0, "price_divergence_p99": 0.0,
                "price_divergence_median": 0.0, "spread_divergence_p99": 0.0,
                "spread_divergence_median": 0.0, "top_divergences": []}

    duka_ts = sorted({int(b.get("timestamp", 0)) for b in duka_bars if b.get("timestamp")})
    mt5_ts = sorted({int(b.get("timestamp", 0)) for b in mt5_bars if b.get("timestamp")})
    if not duka_ts or not mt5_ts:
        return {"ok": False, "error": "empty timestamps", "symbol": symbol, "tf": tf, "hours": hours}

    duka_min, duka_max = duka_ts[0], duka_ts[-1]
    mt5_min, mt5_max = mt5_ts[0], mt5_ts[-1]
    overlap_start = max(duka_min, mt5_min)
    overlap_end = min(duka_max, mt5_max)
    overlap_sec = max(0, overlap_end - overlap_start)
    tf_sec = _TF_SECONDS.get(tf, 3600)
    expected_bars = max(1, math.ceil(overlap_sec / tf_sec) + 1) if overlap_sec > 0 else 1

    # Align by timestamp with 1-bar tolerance (UTC vs broker shift)
    mt5_map = _bars_to_lookup(mt5_bars)
    duka_map = _bars_to_lookup(duka_bars)
    shared = []
    for ts in duka_ts:
        if ts in mt5_map:
            shared.append((ts, duka_map[ts], mt5_map[ts]))
        elif tf_sec and (ts - tf_sec) in mt5_map:
            shared.append((ts, duka_map[ts], mt5_map[ts - tf_sec]))
        elif tf_sec and (ts + tf_sec) in mt5_map:
            shared.append((ts, duka_map[ts], mt5_map[ts + tf_sec]))

    price_errs = []
    spread_errs = []
    divergences = []
    for ts, db, mb in shared:
        do, dh, dl, dc = float(db.get("open", 0)), float(db.get("high", 0)), float(db.get("low", 0)), float(db.get("close", 0))
        mo, mh, ml, mc = float(mb.get("open", 0)), float(mb.get("high", 0)), float(mb.get("low", 0)), float(mb.get("close", 0))
        if any(v == 0 for v in [do, dh, dl, dc, mo, mh, ml, mc]):
            continue
        dp = max(abs(do - mo), abs(dh - mh), abs(dl - ml), abs(dc - mc))
        price_errs.append(dp)
        ds = abs(float(db.get("spread", 0)) - float(mb.get("spread", 0)))
        spread_errs.append(ds)
        divergences.append({"ts": ts, "price_delta": round(dp, 6), "spread_delta": round(ds, 6)})

    gap_frac = 1.0 - (len(shared) / expected_bars)
    median_price = float(sorted(price_errs)[len(price_errs) // 2]) if price_errs else 0.0
    p99_price = float(sorted(price_errs)[min(len(price_errs) - 1, max(0, int(len(price_errs) * 0.99)))]) if price_errs else 0.0
    median_spread = float(sorted(spread_errs)[len(spread_errs) // 2]) if spread_errs else 0.0
    p99_spread = float(sorted(spread_errs)[min(len(spread_errs) - 1, max(0, int(len(spread_errs) * 0.99)))]) if spread_errs else 0.0

    thresh = _THRESHOLDS.get(symbol.upper(), _THRESHOLDS.get("XAUUSD", {}))
    ok = (gap_frac <= thresh.get("max_bar_gap_frac", 0.05) and
          p99_price <= thresh.get("max_price_divergence", 999) and
          p99_spread <= thresh.get("max_spread_divergence", 999))

    return {
        "ok": ok,
        "symbol": symbol,
        "tf": tf,
        "hours": hours,
        "thresholds": thresh,
        "shared_bars": len(shared),
        "dukascopy_bars": len(duka_bars),
        "mt5_bars": len(mt5_bars),
        "dukascopy_time_range": [duka_min, duka_max],
        "mt5_time_range": [mt5_min, mt5_max],
        "overlap_sec": overlap_sec,
        "expected_bars": expected_bars,
        "gap_frac": round(gap_frac, 6),
        "price_divergence_p99": round(p99_price, 6),
        "price_divergence_median": round(median_price, 6),
        "spread_divergence_p99": round(p99_spread, 6),
        "spread_divergence_median": round(median_spread, 6),
        "top_divergences": divergences[:10],
        "error": None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate Dukascopy fidelity against MT5.")
    ap.add_argument("--symbol", default=os.getenv("TRADING_SYMBOL", "XAUUSD"))
    ap.add_argument("--tf", default="H1", choices=list(_TF_SECONDS.keys()))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--report", choices=["text", "json"], default="text")
    ap.add_argument("--fail-on-breach", action="store_true")
    args = ap.parse_args(argv)

    res = compare(args.symbol, args.tf, args.hours)
    if args.report == "json":
        print(json.dumps(res, indent=2, default=str))
    else:
        print(f"symbol={res.get('symbol')} tf={res.get('tf')} hours={res.get('hours')}")
        print(f"  shared_bars={res.get('shared_bars')} duka_only={res.get('dukascopy_only_bars')} mt5_only={res.get('mt5_only_bars')}")
        print(f"  gap_frac={res.get('gap_frac')} price_p99={res.get('price_divergence_p99')} spread_p99={res.get('spread_divergence_p99')}")
        print(f"  thresholds={res.get('thresholds')}")
        print(f"  ok={res.get('ok')} error={res.get('error')}")
        if res.get("top_divergences"):
            print("  top_divergences:")
            for d in res["top_divergences"][:5]:
                print(f"    {d}")

    if not res.get("ok") and args.fail_on_breach:
        return 1
    if res.get("error"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
