"""FloorDiscovery onboarding: backtest+forward-test derives non-zero floors offline."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.floor_discovery import FloorDiscovery


def _fake_rates(sym, timeframe="M1", count=60000):
    # synthetic trending bars so some entries fire
    bars=[]; p=2000.0; t0=1_700_000_000
    for i in range(6000):
        drift = 0.6 if (i//50)%2==0 else -0.6
        o=p; c=p+drift+((i%7)-3)*0.1; h=max(o,c)+0.3; l=min(o,c)-0.3
        bars.append({"open":o,"high":h,"low":l,"close":c,"timestamp":t0+i*60,"time":str(i),"volume":100})
        p=c
    return bars

def _fake_ticks(sym, frm, to, max_ticks=5_000_000):
    # one bid/ask tick per bar-second span, mild spread
    times=[]; bids=[]; asks=[]; t0=1_700_000_000
    p=2000.0
    for i in range(6000):
        for s in range(0,60,5):
            times.append(t0+i*60+s); bids.append(p+ (s-30)*0.01); asks.append(p+(s-30)*0.01+0.05)
        p+=0.6 if (i//50)%2==0 else -0.6
    return {"time":times,"bid":bids,"ask":asks}


def test_onboard_returns_nonzero_recipe_with_forward_test():
    fd = FloorDiscovery(_fake_rates, _fake_ticks, bars=6000, min_trades_per_day=0.0)
    r = fd.onboard("TESTSYM")
    assert r is not None, "onboarding returned nothing"
    # recipe has floors + a forward-test result (BT+FT)
    assert "osma_min_long" in r and "_forward" in r and "_train" in r
    assert r["rsi_long_max"] == 100.0   # RSI off (GoldShark)
    assert r["min_confluence"] == 3


def test_onboard_handles_no_data():
    fd = FloorDiscovery(lambda *a, **k: [], lambda *a, **k: None)
    assert fd.onboard("X") is None


if __name__ == "__main__":
    test_onboard_returns_nonzero_recipe_with_forward_test()
    test_onboard_handles_no_data()
    print("floor discovery onboarding tests passed")
