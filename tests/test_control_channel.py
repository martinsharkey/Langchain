"""
Test the dashboard control channel apply logic (#19) in isolation — no MT5.
Binds the unbound _apply_control to a light stub with a temp control.json.
"""
import sys, os, json, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Adapter:
    def __init__(self): self.mode = "OBSERVE"


class _Stub:
    def __init__(self):
        self.adapters = {"XAUUSD": _Adapter()}
        self._paused = False
        self._scalping_enabled = True
        self._last_control_ts = None


def test_apply_control_sets_mode_pause_scalping():
    from src.trading.scalp_engine import ScalpEngine
    from src import config
    d = tempfile.mkdtemp()
    orig = config.DATA_DIR
    try:
        config.DATA_DIR = d
        config.TRADING_MODE = "OBSERVE"   # ensure the mode change is a real transition
        req = {"mode": "LIVE_MICRO", "paused": True, "scalping": False,
               "disabled_symbols": ["XAGUSD"], "requested_at": time.time()}
        with open(os.path.join(d, "control.json"), "w") as f:
            json.dump(req, f)
        stub = _Stub()
        ScalpEngine._apply_control(stub)
        assert config.TRADING_MODE == "LIVE_MICRO"
        assert stub.adapters["XAUUSD"].mode == "LIVE_MICRO"
        assert stub._paused is True
        assert stub._scalping_enabled is False
        assert config.DISABLED_SYMBOLS == ["XAGUSD"]
        # idempotent: second apply with same ts does nothing new
        stub._paused = False
        ScalpEngine._apply_control(stub)
        assert stub._paused is False  # not re-applied
    finally:
        config.DATA_DIR = orig
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_apply_control_sets_mode_pause_scalping()
    print("control channel test passed")
