"""Tests for OperatingMode self-managing TRAINING/LIVE decision (data-derived)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.operating_mode import decide_mode, _required_sample, TRAINING, LIVE
from src import config


def test_required_sample_is_derived_from_winrate():
    # near coin-flip needs many trades; skewed win rate needs fewer
    assert _required_sample(50.0) > _required_sample(70.0)
    assert _required_sample(51.0) >= 100          # barely-signal -> large sample
    assert _required_sample(75.0) <= 60           # clear signal -> smaller sample

def test_low_sample_is_training_loose():
    mp = decide_mode("XAUUSD", closed=5, pf=0.0, win_rate=40.0)
    assert mp.mode == TRAINING
    assert mp.confidence_min < config.SCALP_CONFIDENCE_MIN          # loosened
    assert mp.countertrend_penalty < config.MTF_COUNTERTREND_PENALTY

def test_enough_sample_and_edge_goes_live_tight():
    # win_rate 70 -> required sample is small; 80 closed clears it; PF beats derived bar
    mp = decide_mode("XAUUSD", closed=80, pf=1.4, win_rate=70.0, pf_stdev=0.1)
    assert mp.mode == LIVE
    assert mp.confidence_min > config.SCALP_CONFIDENCE_MIN          # tightened

def test_noisy_edge_needs_higher_bar():
    # same PF but high variability -> edge bar rises above it -> stays TRAINING
    stable = decide_mode("XAUUSD", closed=80, pf=1.12, win_rate=70.0, pf_stdev=0.05)
    noisy  = decide_mode("XAUUSD", closed=80, pf=1.12, win_rate=70.0, pf_stdev=0.30)
    assert stable.mode == LIVE
    assert noisy.mode == TRAINING

def test_enough_sample_no_edge_stays_training():
    mp = decide_mode("XAUUSD", closed=80, pf=0.8, win_rate=70.0)
    assert mp.mode == TRAINING

def test_manual_override_respected():
    assert decide_mode("XAUUSD", closed=5, pf=0.0, win_rate=40.0, override=LIVE).mode == LIVE
    assert decide_mode("XAUUSD", closed=99, pf=2.0, win_rate=80.0, override=TRAINING).mode == TRAINING

def test_loosen_scales_with_shortfall():
    # further from the sample target -> loosen more (bigger downward conf adj)
    near = decide_mode("XAUUSD", closed=50, pf=0.0, win_rate=52.0)   # required is large
    far  = decide_mode("XAUUSD", closed=2, pf=0.0, win_rate=52.0)
    assert far.confidence_min <= near.confidence_min


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
