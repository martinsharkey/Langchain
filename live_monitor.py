"""
Live trade monitor (30-min telemetry capture).

Purpose: OBSERVE the running bot for real — record what actually happens on entry,
management (SL moves, ratchet, trail), and exit, so we can verify claims against
reality and gather training telemetry. Read-only: it does NOT touch trading.

It polls every `interval` seconds and writes:
  * data/monitor/live_monitor_<ts>.jsonl  — one JSON line per snapshot event
  * a rolling console summary

Captured per open position each poll: ticket, symbol, action, entry, live price,
profit_pts, running MFE/MAE (peak/trough since entry), current SL, distance of SL
from entry (is it protecting profit?), and mgmt variant. On close: the realised
outcome joined from the trades DB (pnl, mfe_points, mae_points, exit_points,
exit_reason) so we see peak-vs-exit for every trade.
"""
from __future__ import annotations
import os, sys, json, time, sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB = os.path.join("data", "trading_experience.db")
STATUS = os.path.join("data", "bot_status.json")
OUT_DIR = os.path.join("data", "monitor")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mt5_positions():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        pos = mt5.positions_get() or []
        out = []
        for p in pos:
            tick = mt5.symbol_info_tick(p.symbol)
            info = mt5.symbol_info(p.symbol)
            point = info.point if info else 0.0
            price = (tick.bid if p.type == 0 else tick.ask) if tick else p.price_current
            action = "buy" if p.type == 0 else "sell"
            profit_pts = ((price - p.price_open) if action == "buy" else (p.price_open - price)) / point if point else 0
            # SL distance from entry in points (>0 = SL is protecting profit)
            sl_from_entry = None
            if p.sl and point:
                sl_from_entry = ((p.sl - p.price_open) if action == "buy" else (p.price_open - p.sl)) / point
            out.append({
                "ticket": p.ticket, "symbol": p.symbol, "action": action,
                "entry": p.price_open, "price": price, "profit_pts": round(profit_pts, 1),
                "sl": p.sl, "tp": p.tp, "sl_from_entry_pts": round(sl_from_entry, 1) if sl_from_entry is not None else None,
                "profit_ccy": round(p.profit, 2), "volume": p.volume,
            })
        return out
    except Exception as e:
        return {"error": str(e)}


def run(minutes=30, interval=20):
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUT_DIR, f"live_monitor_{ts}.jsonl")
    end = time.time() + minutes * 60

    # baseline
    conn = sqlite3.connect(DB)
    base_max = conn.execute("SELECT COALESCE(MAX(id),0) FROM trades").fetchone()[0]
    conn.close()
    seen_closed = set()
    # per-ticket running peak/trough as WE observe it (independent of the engine)
    track = {}   # ticket -> {peak_pts, trough_pts, first_seen, entry, action}

    def emit(rec):
        rec["t"] = _now()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    emit({"event": "monitor_start", "baseline_max_id": base_max, "minutes": minutes})
    print(f"[MONITOR] writing {path} for {minutes} min (baseline trade id {base_max})")

    while time.time() < end:
        # 1) live open positions + our own peak/trough tracking
        pos = _mt5_positions()
        if isinstance(pos, list):
            for p in pos:
                tk = p["ticket"]
                st = track.setdefault(tk, {"peak_pts": p["profit_pts"], "trough_pts": p["profit_pts"],
                                           "entry": p["entry"], "action": p["action"], "symbol": p["symbol"],
                                           "first_seen": _now()})
                st["peak_pts"] = max(st["peak_pts"], p["profit_pts"])
                st["trough_pts"] = min(st["trough_pts"], p["profit_pts"])
                p["obs_peak_pts"] = round(st["peak_pts"], 1)
                p["obs_trough_pts"] = round(st["trough_pts"], 1)
                # is the SL protecting profit yet?
                p["sl_protecting"] = (p["sl_from_entry_pts"] or -9e9) > 0
                emit({"event": "open_position", **p})
        elif pos:
            emit({"event": "mt5_error", "detail": pos})

        # 2) newly closed trades from the DB (join realised outcome)
        try:
            conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT id,symbol,action,entry_price,exit_price,profit_loss,mfe_points,mae_points,"
                "exit_points,exit_reason,mt5_ticket FROM trades WHERE id>? AND outcome IN ('win','loss','breakeven') "
                "AND (data_source IS NULL OR data_source='LIVE_MICRO') ORDER BY id", (base_max,)).fetchall()]
            conn.close()
            for r in rows:
                if r["id"] in seen_closed:
                    continue
                seen_closed.add(r["id"])
                obs = track.get(r["mt5_ticket"], {})
                # was it a winner at peak that exited worse? the core question.
                gave_back = None
                if r["mfe_points"] and r["mfe_points"] > 0 and r["exit_points"] is not None:
                    gave_back = round((r["mfe_points"] - r["exit_points"]) / r["mfe_points"] * 100, 0)
                rec = {"event": "trade_closed", "id": r["id"], "symbol": r["symbol"], "action": r["action"],
                       "pnl": r["profit_loss"], "mfe_points": r["mfe_points"], "mae_points": r["mae_points"],
                       "exit_points": r["exit_points"], "exit_reason": r["exit_reason"],
                       "obs_peak_pts": obs.get("peak_pts"), "obs_trough_pts": obs.get("trough_pts"),
                       "gave_back_pct": gave_back,
                       "profitable_sl": (r["exit_reason"] == "sl" and (r["profit_loss"] or 0) > 0)}
                emit(rec)
                print(f"[CLOSE] #{r['id']} {r['symbol'][:6]} {r['action']} pnl={r['profit_loss']:.2f} "
                      f"MFE={r['mfe_points']} exit_pts={r['exit_points']} reason={r['exit_reason']} "
                      f"gaveback={gave_back}%")
        except Exception as e:
            emit({"event": "db_error", "detail": str(e)})

        time.sleep(interval)

    # final summary
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT profit_loss,mfe_points,exit_points,exit_reason FROM trades WHERE id>? "
        "AND outcome IN ('win','loss','breakeven') AND (data_source IS NULL OR data_source='LIVE_MICRO')",
        (base_max,)).fetchall()]
    conn.close()
    n = len(rows)
    wins = sum(1 for r in rows if (r["profit_loss"] or 0) > 0)
    net = sum(r["profit_loss"] or 0 for r in rows)
    prof_sl = sum(1 for r in rows if r["exit_reason"] == "sl" and (r["profit_loss"] or 0) > 0)
    ratchet = sum(1 for r in rows if r["exit_reason"] and "ratchet" in r["exit_reason"])
    gave = [(r["mfe_points"] - r["exit_points"]) / r["mfe_points"]
            for r in rows if r["mfe_points"] and r["mfe_points"] > 0 and r["exit_points"] is not None]
    summary = {"event": "monitor_summary", "new_trades": n, "wins": wins,
               "win_rate": round(wins / n * 100) if n else None, "net": round(net, 2),
               "profitable_sl_exits": prof_sl, "ratchet_exits": ratchet,
               "median_gaveback_frac": round(sorted(gave)[len(gave)//2], 3) if gave else None}
    emit(summary)
    print(f"[MONITOR DONE] {summary}")


if __name__ == "__main__":
    mins = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run(minutes=mins)
