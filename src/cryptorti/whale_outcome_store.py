"""
Whale outcome store + self-learning model (#44/#46).

Makes the whale edge SELF-SUSTAINING: the bot records every live WebSocket whale
signal it receives AND the realised BTCUSD candle response ~N minutes later, in its
OWN local store — so it builds its own labeled dataset going forward and stops
depending on re-querying Danny's history. A lightweight model learns size ->
direction/response from the accumulated events (Danny history seeds it, live events
grow it), and exposes a confidence for the live predictor.

Two tables in a local SQLite DB (data/whale_outcomes.db):
  * events:   signal_id, ts, exchange, direction, amount_usd, stage  (recorded on arrival)
  * outcomes: signal_id, resolved_ts, large_candles, net_move_pts, net_bps,
              moved_right, window_min  (filled once the candle window has passed)

`record_signal()` is called from the live SignalStore on arrival.
`resolve_pending()` is called on a cadence by the engine: for events whose window
has elapsed, pull the MT5 candle response and label the outcome.
`model()` learns P(move_right) + expected response by size bucket over ALL stored
events (seeded + live) — used by wave_predictor.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("whale_outcome_store")


def _db_path() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "whale_outcomes.db")


class WhaleOutcomeStore:
    def __init__(self, path: str = None, window_min: int = 15):
        self.path = path or _db_path()
        self.window_min = window_min
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.path)
        conn.execute("""CREATE TABLE IF NOT EXISTS whale_events (
            signal_id TEXT PRIMARY KEY, ts INTEGER, exchange TEXT, direction TEXT,
            amount_usd REAL, stage TEXT, source TEXT, recorded_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS whale_outcomes (
            signal_id TEXT PRIMARY KEY, resolved_ts INTEGER, large_candles INTEGER,
            net_move_pts REAL, net_bps REAL, moved_right INTEGER, window_min INTEGER,
            resolved_at TEXT)""")
        conn.commit(); conn.close()

    # ── capture (live) ──
    def record_signal(self, signal: dict, source: str = "websocket"):
        """Record a live whale signal on arrival (idempotent by signal_id)."""
        sid = signal.get("signal_id")
        if not sid:
            return
        amount = float(signal.get("amount_usd") or signal.get("usd") or 0)
        direction = "sell" if str(signal.get("action", signal.get("event_type", "")))\
            .lower().startswith(("s", "dep")) else "buy"
        ts = signal.get("timestamp")
        try:
            ts = int(ts) if ts else int(datetime.now(timezone.utc).timestamp() * 1e6)
        except Exception:
            ts = int(datetime.now(timezone.utc).timestamp() * 1e6)
        try:
            conn = sqlite3.connect(self.path)
            conn.execute("INSERT OR IGNORE INTO whale_events VALUES (?,?,?,?,?,?,?,?)",
                         (sid, ts, signal.get("exchange", ""), direction, amount,
                          signal.get("stage", signal.get("signal_status", "")), source,
                          datetime.now(timezone.utc).isoformat()))
            conn.commit(); conn.close()
        except Exception as e:
            logger.debug(f"record_signal skip: {e}")

    # ── resolve (label against realised candles) ──
    def resolve_pending(self, get_rates_fn, symbol: str = "BTCUSD") -> int:
        """For events whose window has elapsed and aren't yet resolved, pull the
        MT5 candle response and store the labeled outcome. Returns count resolved."""
        conn = sqlite3.connect(self.path); conn.row_factory = sqlite3.Row
        pend = conn.execute(
            "SELECT e.* FROM whale_events e LEFT JOIN whale_outcomes o "
            "ON e.signal_id=o.signal_id WHERE o.signal_id IS NULL").fetchall()
        conn.close()
        if not pend:
            return 0
        now = datetime.now(timezone.utc)
        resolved = 0
        for e in pend:
            event_dt = datetime.fromtimestamp(int(e["ts"]) / 1e6, tz=timezone.utc)
            if now < event_dt + timedelta(minutes=self.window_min + 1):
                continue  # window not elapsed yet
            resp = self._candle_response(get_rates_fn, symbol, event_dt)
            if resp is None:
                continue
            moved_right = (e["direction"] == "sell" and resp["net_move_pts"] < 0) or \
                          (e["direction"] == "buy" and resp["net_move_pts"] > 0)
            try:
                conn = sqlite3.connect(self.path)
                conn.execute("INSERT OR REPLACE INTO whale_outcomes VALUES (?,?,?,?,?,?,?,?)",
                             (e["signal_id"], int(event_dt.timestamp()), resp["large_candles"],
                              resp["net_move_pts"], resp["net_bps"], int(moved_right),
                              self.window_min, now.isoformat()))
                conn.commit(); conn.close()
                resolved += 1
            except Exception as ex:
                logger.debug(f"resolve store skip: {ex}")
        if resolved:
            logger.info(f"[WHALE] resolved {resolved} whale-event outcomes from live candles")
        return resolved

    def _candle_response(self, get_rates_fn, symbol, event_dt):
        import pandas as pd
        try:
            rates = get_rates_fn(symbol, timeframe="M1", count=400)
            if not rates:
                return None
            df = pd.DataFrame(rates)
            df["dt"] = df["time"].map(lambda t: datetime.fromtimestamp(int(t), tz=timezone.utc)
                                      if 1_000_000_000 <= int(t) <= 9_999_999_999
                                      else pd.to_datetime(t, utc=True).to_pydatetime())
        except Exception:
            return None
        post = df[(df["dt"] >= event_dt) & (df["dt"] <= event_dt + timedelta(minutes=self.window_min))]
        if len(post) < 3:
            return None
        ranges = (post["high"] - post["low"]).abs()
        med = float(ranges.median()) or 1e-9
        entry = float(post["open"].iloc[0]) or 1e-9
        net = float(post["close"].iloc[-1] - post["open"].iloc[0])
        return {"large_candles": int((ranges >= 1.8 * med).sum()),
                "net_move_pts": round(net, 1), "net_bps": round(net / entry * 1e4, 1)}

    # ── seed from Danny history (one-time / periodic) ──
    def seed_from_study(self, study_json: str = None) -> int:
        """Import events already catalogued by scripts/whale_candle_study.py so the
        model starts with Danny history, then grows from live events."""
        import json
        p = study_json
        if p is None:
            try:
                from src import config
                p = os.path.join(config.DATA_DIR, "whale_candle_study.json")
            except Exception:
                p = "whale_candle_study.json"
        if not os.path.exists(p):
            return 0
        data = json.load(open(p))
        n = 0
        conn = sqlite3.connect(self.path)
        for i, ev in enumerate(data.get("events", [])):
            sid = f"hist_{ev.get('date')}_{i}"
            conn.execute("INSERT OR IGNORE INTO whale_events VALUES (?,?,?,?,?,?,?,?)",
                         (sid, 0, ev.get("exchange", ""), ev.get("expected_dir", "sell"),
                          float(ev.get("amount_usd", 0)), "historical", "danny_study",
                          ev.get("time", "")))
            conn.execute("INSERT OR REPLACE INTO whale_outcomes VALUES (?,?,?,?,?,?,?,?)",
                         (sid, 0, int(ev.get("large_candles", 0)),
                          float(ev.get("net_move_pts", 0)), float(ev.get("net_bps", 0)),
                          int(bool(ev.get("moved_right"))), int(ev.get("bars", 15)), ""))
            n += 1
        conn.commit(); conn.close()
        logger.info(f"[WHALE] seeded {n} historical whale outcomes from {os.path.basename(p)}")
        return n

    # ── the learned model ──
    def model(self) -> dict:
        """Learn P(move_right) + avg response by size bucket over ALL stored
        (seeded + live) resolved outcomes. Self-updating as live events accrue."""
        conn = sqlite3.connect(self.path); conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT e.amount_usd, e.direction, o.moved_right, o.large_candles, o.net_bps "
            "FROM whale_events e JOIN whale_outcomes o ON e.signal_id=o.signal_id").fetchall()
        conn.close()
        buckets = {"1-3M": (1e6, 3e6), "3-6M": (3e6, 6e6), ">=6M": (6e6, 1e15)}
        out = {"n_total": len(rows), "buckets": {}}
        for name, (lo, hi) in buckets.items():
            b = [r for r in rows if lo <= (r["amount_usd"] or 0) < hi]
            if not b:
                continue
            right = sum(1 for r in b if r["moved_right"])
            out["buckets"][name] = {
                "n": len(b), "move_right_prob": round(right / len(b), 3),
                "avg_large_candles": round(sum(r["large_candles"] for r in b) / len(b), 1),
                "avg_net_bps": round(sum(r["net_bps"] for r in b) / len(b), 1)}
        return out

    def confidence_for(self, amount_usd: float) -> float:
        """Learned P(move_right) for this order size — the self-updating live signal.
        Falls back to 0 if the size bucket has no data yet."""
        m = self.model()
        if amount_usd >= 6e6:
            b = m["buckets"].get(">=6M")
        elif amount_usd >= 3e6:
            b = m["buckets"].get("3-6M")
        else:
            b = m["buckets"].get("1-3M")
        return float(b["move_right_prob"]) if b and b["n"] >= 5 else 0.0

    def stats(self) -> dict:
        conn = sqlite3.connect(self.path)
        ev = conn.execute("SELECT COUNT(*) FROM whale_events").fetchone()[0]
        oc = conn.execute("SELECT COUNT(*) FROM whale_outcomes").fetchone()[0]
        conn.close()
        return {"events": ev, "resolved": oc, "pending": ev - oc}
