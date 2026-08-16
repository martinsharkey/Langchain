"""
backfill_history.py — reconstruct the FULL account trade history into the learning DB.

WHY (issue: bot only learned from trades it personally placed since 2026-07-30, while
the VT Markets account holds ~3,600 realised closed trades back to 2026-07-04). The
learning loops were starving. This tool pulls the broker's real closed positions,
reconstructs OUR indicator snapshot at each entry (via the SAME compute_indicator_series
used by the backtester — causal, no look-ahead), measures realised tick-level MFE/MAE,
and inserts them tagged data_source='MT5_BACKFILL' so:
  * ONNX P(win) models + excursion/exit calibration + entry-frequency + post-mortem
    can train on the FULL picture (thousands of real outcomes, not ~100);
  * they are EXCLUDED from the live auto-mutation gate (R4): the learning_window_clause
    already drops non-LIVE_MICRO sources, so backfilled rows never drive live config
    mutation — they only feed offline model training + analysis reads that opt in.

Data source: MetaTrader5 (VT Markets). copy_rates_range serves M1 back to ~07-04 for
XAUUSD/BTCUSD/GER40 (verified), and copy_ticks_range gives intra-trade excursion.

Read-only against MT5; INSERTs into data/trading_experience.db (idempotent on mt5_ticket).
Run with the live bot STOPPED (single MT5 connection).

Usage:
    python -m scripts.backfill_history            # all symbols, since 2026-07-01
    python -m scripts.backfill_history BTCUSD     # one symbol
    python -m scripts.backfill_history --from 2026-07-01 --no-ticks
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

import MetaTrader5 as mt5

from src.learning.experience_db import ExperienceDatabase
from src.strategies.indicators import compute_indicator_series

TF_M1 = mt5.TIMEFRAME_M1
DEAL_ENTRY_OUT = getattr(mt5, "DEAL_ENTRY_OUT", 1)
POINT_DEFAULT = 0.01


def _bars_to_dicts(bars):
    return [
        {"time": int(b["time"]), "open": float(b["open"]), "high": float(b["high"]),
         "low": float(b["low"]), "close": float(b["close"]),
         "volume": float(b["tick_volume"])}
        for b in bars
    ]


def _infer_point(symbol_info, symbol: str) -> float:
    if symbol_info and getattr(symbol_info, "point", 0):
        return symbol_info.point
    return POINT_DEFAULT


def reconstruct_positions(frm: datetime, to: datetime):
    """Group MT5 history deals into closed positions with entry/exit/PnL."""
    deals = mt5.history_deals_get(frm, to)
    if not deals:
        return {}
    by_pos = defaultdict(list)
    for d in deals:
        by_pos[d.position_id].append(d)
    positions = {}
    for pid, ds in by_pos.items():
        ds = sorted(ds, key=lambda d: d.time)
        outs = [d for d in ds if d.entry == DEAL_ENTRY_OUT]
        ins = [d for d in ds if d.entry != DEAL_ENTRY_OUT]
        if not outs or not ins:
            continue  # not a completed round-trip
        entry_deal = ins[0]
        exit_deal = outs[-1]
        pnl = round(sum(d.profit + d.commission + d.swap for d in ds), 2)
        # deal type 0=buy 1=sell; the ENTRY deal's type is the position direction
        action = "buy" if entry_deal.type == 0 else "sell"
        positions[pid] = {
            "position_id": pid,
            "symbol": entry_deal.symbol,
            "action": action,
            "entry_time": entry_deal.time,
            "entry_price": entry_deal.price,
            "exit_time": exit_deal.time,
            "exit_price": exit_deal.price,
            "volume": entry_deal.volume,
            "pnl": pnl,
            "outcome": "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven"),
            "exit_reason": _exit_reason(exit_deal),
        }
    return positions


def _exit_reason(exit_deal) -> str:
    r = getattr(exit_deal, "reason", None)
    m = {getattr(mt5, "DEAL_REASON_SL", 4): "sl", getattr(mt5, "DEAL_REASON_TP", 5): "tp",
         getattr(mt5, "DEAL_REASON_SO", 6): "stopout"}
    return m.get(r, "closed")


def _mfe_mae_from_ticks(symbol, action, entry_price, entry_time, exit_time, point,
                        max_hours: float = 12.0):
    """Realised max-favourable / max-adverse excursion in points, from ticks.

    Caps the fetch window at max_hours to avoid pulling an enormous tick set for a
    long-held position; returns (None, None) for over-long holds so the caller can
    fall back (excursion for a 12h+ hold is dominated by noise anyway)."""
    try:
        if exit_time - entry_time > max_hours * 3600:
            return None, None
        frm = datetime.fromtimestamp(entry_time, timezone.utc)
        to = datetime.fromtimestamp(exit_time, timezone.utc) + timedelta(seconds=1)
        ticks = mt5.copy_ticks_range(symbol, frm, to, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            return None, None
        best = worst = 0.0
        for t in ticks:
            px = t["bid"] if action == "sell" else t["ask"]
            if not px:
                px = t["last"] or entry_price
            fav = ((px - entry_price) if action == "buy" else (entry_price - px)) / point
            best = max(best, fav)
            worst = min(worst, fav)
        return round(best, 1), round(worst, 1)
    except Exception:
        return None, None


def backfill_symbol(db: ExperienceDatabase, symbol: str, positions: dict,
                    account: dict, existing: set, use_ticks: bool = True) -> dict:
    info = mt5.symbol_info(symbol)
    point = _infer_point(info, symbol)
    mt5.symbol_select(symbol, True)

    syms_pos = [p for p in positions.values() if p["symbol"] == symbol]
    if not syms_pos:
        return {"symbol": symbol, "n": 0, "note": "no positions"}
    syms_pos.sort(key=lambda p: p["entry_time"])
    t0 = datetime.fromtimestamp(syms_pos[0]["entry_time"], timezone.utc) - timedelta(days=2)
    t1 = datetime.fromtimestamp(syms_pos[-1]["exit_time"], timezone.utc) + timedelta(days=1)
    bars = mt5.copy_rates_range(symbol, TF_M1, t0, t1)
    if bars is None or len(bars) < 60:
        return {"symbol": symbol, "n": 0, "note": f"insufficient bars ({0 if bars is None else len(bars)})"}
    bar_dicts = _bars_to_dicts(bars)
    bar_times = [b["time"] for b in bar_dicts]

    # vectorized, causal per-bar indicator dicts (no look-ahead)
    series = compute_indicator_series(bar_dicts)
    # align: series is per-bar aligned to bar_dicts (skips warmup <30). Build a
    # time->index map for the bars that HAVE an indicator dict.
    offset = len(bar_dicts) - len(series)  # warmup bars dropped from the front
    time_to_idx = {bar_times[offset + i]: i for i in range(len(series))}

    conn = sqlite3.connect(db.db_path)
    cur = conn.cursor()

    inserted = skipped = no_ind = 0
    for p in syms_pos:
        if p["position_id"] in existing:
            skipped += 1
            continue
        # find the last CLOSED M1 bar at/just before entry (causal): floor entry_time to minute
        et = p["entry_time"] - (p["entry_time"] % 60)
        idx = time_to_idx.get(et)
        # walk back up to 3 minutes if exact minute missing (gaps/weekend)
        probe = et
        tries = 0
        while idx is None and tries < 3:
            probe -= 60
            idx = time_to_idx.get(probe)
            tries += 1
        if idx is None:
            no_ind += 1
            ind = {}
        else:
            # CAUSAL snapshot: use the last CLOSED bar (idx-1), NOT the bar that was
            # still FORMING at entry (idx contains the entry minute). The live path uses
            # compute_full_indicators on closed bars (osma_closed=osma[-2]); using the
            # forming bar here would leak that bar's final close into the entry features
            # (look-ahead) and make backfilled rows optimistically biased vs live rows.
            base_idx = idx - 1 if idx >= 1 else idx
            ind = dict(series[base_idx])
            # compute_indicator_series omits osma_recent/_avg (needed by the entry-
            # frequency analyzer for RUNWAY). Reconstruct them from the trailing osma
            # values of the bars preceding the closed base bar (causal).
            recent = [series[j].get("osma", 0.0) for j in range(max(0, base_idx - 6), base_idx)]
            if recent:
                ind["osma_recent"] = [round(float(x), 6) for x in recent]
                mags = [abs(float(x)) for x in recent if x is not None]
                ind["osma_recent_avg"] = round(sum(mags) / len(mags), 6) if mags else 0.0
            # confluence cross fields from the two bars before the closed base bar,
            # matching the live osma_closed=osma[-2]/osma_prev=osma[-3] convention.
            if base_idx >= 2:
                ind["osma_closed"] = round(float(series[base_idx - 1].get("osma", 0.0)), 6)
                ind["osma_prev"] = round(float(series[base_idx - 2].get("osma", 0.0)), 6)

        mfe = mae = None
        if use_ticks:
            mfe, mae = _mfe_mae_from_ticks(symbol, p["action"], p["entry_price"],
                                           p["entry_time"], p["exit_time"], point)

        snap = json.dumps({k: v for k, v in ind.items()
                           if isinstance(v, (int, float, str, bool, list))}, default=str)
        ts = datetime.fromtimestamp(p["entry_time"], timezone.utc).isoformat()
        cur.execute("""
            INSERT INTO trades (
                timestamp, symbol, action, entry_price, stop_loss, take_profit,
                position_size, confidence, strategy_used, strategy_combination,
                outcome, profit_loss, exit_price, exit_reason, market_regime,
                indicators_snapshot, rsi_value, trend, atr_value, mgmt_variant,
                timeframe, mt5_ticket, account_login, account_server,
                account_trade_mode, mfe_points, mae_points, data_source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ts, symbol, p["action"], p["entry_price"], 0, 0,
            p["volume"], 0.0, "HISTORICAL", "",
            p["outcome"], p["pnl"], p["exit_price"], p["exit_reason"],
            ind.get("trend", "unknown"), snap, ind.get("rsi"), ind.get("trend"),
            ind.get("atr"), None, "M1", p["position_id"],
            account.get("login"), account.get("server"), account.get("trade_mode"),
            mfe, mae, "MT5_BACKFILL",
        ))
        inserted += 1

    conn.commit()
    conn.close()
    return {"symbol": symbol, "n_positions": len(syms_pos), "inserted": inserted,
            "skipped_existing": skipped, "no_indicator": no_ind, "bars": len(bar_dicts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="symbols to backfill (default: all traded)")
    ap.add_argument("--from", dest="frm", default="2026-07-01", help="YYYY-MM-DD start")
    ap.add_argument("--no-ticks", action="store_true", help="skip tick MFE/MAE (faster)")
    args = ap.parse_args()

    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error())
        return
    ai = mt5.account_info()
    account = {"login": ai.login, "server": ai.server,
               "trade_mode": "DEMO" if ai.trade_mode == 0 else "REAL"}
    print(f"account {ai.login} {ai.server} balance={ai.balance:.2f} {ai.currency}")

    frm = datetime.fromisoformat(args.frm).replace(tzinfo=timezone.utc)
    to = datetime.now(timezone.utc) + timedelta(days=1)
    print(f"scanning MT5 history {frm.date()} .. {to.date()} ...")
    positions = reconstruct_positions(frm, to)
    print(f"reconstructed {len(positions)} closed positions")

    symbols = args.symbols or sorted({p["symbol"] for p in positions.values()})
    db = ExperienceDatabase()
    # load the existing-ticket set ONCE (dedup) instead of rescanning per symbol
    _c = sqlite3.connect(db.db_path)
    existing = {r[0] for r in _c.execute(
        "SELECT mt5_ticket FROM trades WHERE mt5_ticket IS NOT NULL").fetchall()}
    _c.close()
    totals = {"inserted": 0, "skipped_existing": 0, "no_indicator": 0}
    for sym in symbols:
        res = backfill_symbol(db, sym, positions, account, existing,
                              use_ticks=not args.no_ticks)
        print("  ", res)
        for k in totals:
            totals[k] += res.get(k, 0)
    print(f"\nDONE: inserted={totals['inserted']} "
          f"skipped(existing)={totals['skipped_existing']} "
          f"no_indicator={totals['no_indicator']}")
    mt5.shutdown()


if __name__ == "__main__":
    main()
