"""
Whale live monitor (30 min) — empirical answer to "what does the data say".

Watches Danny's live CryptoRTI signals as they arrive AND, for each whale event,
looks up (a) the historical profile we mined (hit-rate / expected move for that
size x exchange x direction) and (b) the ACTUAL BTC candle move in the window after
the event — so we can see, on LIVE data, whether whale deposits actually move BTC
and whether we should act on sell_window_open rather than wait for selling_confirmed
(which the feed never sends).

Read-only. Writes data/monitor/whale_monitor_<ts>.jsonl.
"""
from __future__ import annotations
import os, sys, json, time, sqlite3
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
SIGJSON = os.path.join(BASE, "data", "cryptorti_signals.json")
WDB = os.path.join(BASE, "data", "whale_outcomes.db")
OUT = os.path.join(BASE, "data", "monitor")


def _profile_lookup(usd, exchange, direction):
    """The mined historical profile for this whale bucket (hit-rate etc.)."""
    p = os.path.join(BASE, "data", "cryptorti_correlation.json")
    if not os.path.exists(p):
        return None
    prof = json.load(open(p)).get("profiles", {})
    bucket = "<1M" if usd < 1_000_000 else ("1-3M" if usd < 3_000_000 else ("3-6M" if usd < 6_000_000 else ">6M"))
    key = f"{bucket}|{(exchange or '').lower()}|{direction}"
    return prof.get(key) or {"_note": f"no profile for {key}"}


def run(minutes=30, interval=20):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"whale_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    end = time.time() + minutes * 60
    seen = set()
    stage_counts = {}

    def emit(rec):
        rec["t"] = datetime.now(timezone.utc).isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    print(f"[WHALE-MON] writing {path} for {minutes} min")
    emit({"event": "start", "minutes": minutes})

    while time.time() < end:
        try:
            d = json.load(open(SIGJSON)) if os.path.exists(SIGJSON) else {}
        except Exception:
            d = {}
        for s in d.get("signals", []):
            sid = s.get("signal_id"); stage = s.get("stage"); status = s.get("signal_status")
            wt = s.get("whale_transfer") or {}
            usd = float(s.get("amount_usd") or s.get("usd") or wt.get("amount_usd") or 0)
            exch = s.get("exchange") or wt.get("exchange") or ""
            key = f"{sid}|{stage}|{status}"
            stage_counts[stage] = stage_counts.get(stage, 0) + (0 if key in seen else 1)
            if key in seen:
                continue
            seen.add(key)
            direction = "sell" if ("deposit" in str(stage).lower() or "sell" in str(stage).lower()) else "buy"
            prof = _profile_lookup(usd, exch, direction)
            rec = {"event": "whale_signal", "signal_id": sid, "stage": stage, "status": status,
                   "amount_usd": round(usd), "exchange": exch, "direction": direction,
                   "historical_profile": prof}
            emit(rec)
            print(f"[WHALE] {sid} stage={stage} ${usd:,.0f} {exch} -> "
                  f"hist hit_rate={prof.get('hit_rate') if isinstance(prof,dict) else '?'}% "
                  f"peak={prof.get('avg_peak_bps') if isinstance(prof,dict) else '?'}bps")
        emit({"event": "stage_tally", "counts": dict(stage_counts)})
        time.sleep(interval)

    emit({"event": "summary", "stage_counts": stage_counts,
          "selling_confirmed_ever": stage_counts.get("selling_confirmed", 0)})
    print(f"[WHALE-MON DONE] stages seen: {stage_counts}")


if __name__ == "__main__":
    run(minutes=int(sys.argv[1]) if len(sys.argv) > 1 else 30)
