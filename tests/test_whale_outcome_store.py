"""
Tests for WhaleOutcomeStore (#44/#46): record live signals, resolve outcomes
against candles, learn a size-gated model. Temp DB; mock rates. No S3/MT5.
"""
import sys, os, tempfile, shutil
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cryptorti.whale_outcome_store import WhaleOutcomeStore


def _store(d):
    return WhaleOutcomeStore(path=os.path.join(d, "w.db"), window_min=15)


def test_record_signal_and_stats():
    d = tempfile.mkdtemp()
    try:
        s = _store(d)
        s.record_signal({"signal_id": "s1", "amount_usd": 7_000_000,
                         "event_type": "deposit", "exchange": "binance"})
        s.record_signal({"signal_id": "s1", "amount_usd": 7_000_000})  # idempotent
        assert s.stats()["events"] == 1
        assert s.stats()["pending"] == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_live_websocket_payload_nested_amount_parsed():
    """The LIVE payload nests amount under whale_transfer.amount_usd and has no
    top-level action/direction; record_signal must parse it (was storing 0/buy)."""
    import sqlite3, os
    d = tempfile.mkdtemp()
    try:
        s = _store(d)
        live = {"signal_id": "sig_live_1", "signal_type": "exchange_deposit",
                "stage": "sell_window_open", "signal_status": "monitoring",
                "whale_transfer": {"exchange": "binance", "amount_usd": 2_710_756.3}}
        s.record_signal(live, source="websocket")
        conn = sqlite3.connect(os.path.join(d, "w.db"))
        r = conn.execute("SELECT exchange, direction, amount_usd FROM whale_events").fetchone()
        conn.close()
        assert r[0] == "binance", r
        assert r[1] == "sell", r          # deposit -> sell pressure
        assert abs(r[2] - 2_710_756.3) < 1, r   # amount parsed, not 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _mock_rates(net_move):
    """400 M1 bars; the window right after 'now-20min' moves by net_move."""
    base = 63000.0
    now = datetime.now(timezone.utc)
    out = []
    for i in range(400):
        t = now - timedelta(minutes=400 - i)
        px = base + (net_move if i > 380 else 0)
        out.append({"time": int(t.timestamp()), "open": base, "high": max(base, px) + 5,
                    "low": min(base, px) - 5, "close": px})
    return out


def test_resolve_and_model():
    d = tempfile.mkdtemp()
    try:
        s = _store(d)
        # a >=6M deposit ~20 min ago (window elapsed) that moved DOWN (right for sell)
        ts = int((datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp() * 1e6)
        for i in range(6):
            s.record_signal({"signal_id": f"big{i}", "amount_usd": 7_000_000,
                             "event_type": "deposit", "timestamp": ts, "exchange": "binance"})
        def rates(sym, timeframe="M1", count=400):
            return _mock_rates(net_move=-150)  # fell -> deposit moved right
        n = s.resolve_pending(rates, "BTCUSD")
        assert n == 6, n
        m = s.model()
        assert m["buckets"][">=6M"]["n"] == 6
        assert m["buckets"][">=6M"]["move_right_prob"] == 1.0
        assert s.confidence_for(7_000_000) == 1.0
        # small size with no data -> 0 confidence
        assert s.confidence_for(500_000) == 0.0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_seed_from_study():
    d = tempfile.mkdtemp()
    try:
        import json
        study = {"events": [
            {"date": "2026-08-01", "time": "t", "exchange": "binance",
             "expected_dir": "sell", "amount_usd": 7e6, "moved_right": True,
             "large_candles": 4, "net_move_pts": -100, "net_bps": -15, "bars": 15}
            for _ in range(8)]}
        sp = os.path.join(d, "study.json"); json.dump(study, open(sp, "w"))
        s = _store(d)
        n = s.seed_from_study(sp)
        assert n == 8
        assert s.confidence_for(7e6) == 1.0  # all seeded moved right
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_record_signal_and_stats()
    test_live_websocket_payload_nested_amount_parsed()
    test_resolve_and_model()
    test_seed_from_study()
    print("whale outcome store tests passed")
