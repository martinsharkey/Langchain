"""
Tests for SymbolGovernor — the learning-loop symbol pause/fail decisions.

Guarantees under test:
  * Never blocks a healthy symbol (>=45% WR) — so we can't block everything.
  * Pauses catastrophic win rate (e.g. ETH 5%).
  * Pauses/fails a bleeding symbol and PRODUCES A FAILURE REPORT.
  * Insufficient sample keeps a symbol active (keep learning).
  * A fleet with one healthy symbol never ends up fully blocked.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.symbol_governor import decide, SymbolStats, ACTIVE, PAUSED, FAILED

# fixed thresholds for deterministic tests (don't depend on config drift)
TH = dict(window=20, min_trades=15, healthy_wr=45.0, catastrophic_wr=25.0, bleed_pnl=-15.0)


def test_healthy_symbol_never_paused():
    s = SymbolStats("XAUUSD", n=20, win_rate=48.0, pnl=-11.99)  # negative pnl but healthy WR
    d = decide(s, **TH)
    assert d.status == ACTIVE, d.reason  # MUST keep trading a working symbol

def test_high_winrate_index_protected():
    s = SymbolStats("GER40", n=20, win_rate=60.0, pnl=-4.86)
    assert decide(s, **TH).status == ACTIVE

def test_catastrophic_winrate_paused():
    s = SymbolStats("ETHUSD", n=20, win_rate=5.0, pnl=-0.47)  # tiny pnl but WR is broken
    d = decide(s, **TH)
    assert d.status in (PAUSED, FAILED)
    assert d.report is not None
    assert d.report["trigger"].startswith("catastrophic")

def test_bleeding_pnl_paused_with_report():
    s = SymbolStats("XAGUSD", n=20, win_rate=40.0, pnl=-25.0,
                    per_strategy={"CCI_Breakout": {"n": 8, "wins": 2, "pnl": -18.0},
                                  "BB_Bounce": {"n": 12, "wins": 6, "pnl": -7.0}})
    d = decide(s, **TH)
    assert d.status in (PAUSED, FAILED)
    assert d.report is not None
    # worst strategy must be reported (the one that lost most)
    assert d.report["worst_strategies"][0]["strategy"] == "CCI_Breakout"

def test_failed_when_both_bad():
    s = SymbolStats("BADSYM", n=20, win_rate=10.0, pnl=-30.0)
    assert decide(s, **TH).status == FAILED

def test_insufficient_sample_keeps_active():
    s = SymbolStats("EURUSD", n=8, win_rate=0.0, pnl=-5.0)
    assert decide(s, **TH).status == ACTIVE

def test_acceptable_midrange_trades():
    # 40% WR, small negative pnl -> not healthy, not catastrophic, not bleeding -> ACTIVE
    s = SymbolStats("BTCUSD", n=20, win_rate=40.0, pnl=-4.74)
    assert decide(s, **TH).status == ACTIVE

def test_fleet_never_fully_blocked():
    """The core guarantee: with one healthy symbol, the fleet is never all-blocked."""
    fleet = [
        SymbolStats("XAUUSD", 20, 48.0, -11.99),  # healthy -> active
        SymbolStats("ETHUSD", 20, 5.0, -20.0),    # failed
        SymbolStats("XAGUSD", 20, 30.0, -25.0),   # bleeding -> paused
    ]
    decisions = [decide(s, **TH) for s in fleet]
    assert any(d.status == ACTIVE for d in decisions), "must keep >=1 symbol trading"


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
