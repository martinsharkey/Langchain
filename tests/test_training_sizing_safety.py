"""
Test the TRAINING-mode sizing safety (review finding): a symbol in TRAINING must
NEVER size up (loosened entry + full size = the opposite of the safety design).
Binds the unbound _position_lot to a light stub.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.scalp_engine import ScalpEngine
from src.learning.operating_mode import ModeParams, TRAINING, LIVE
from src import config


class _Spec:
    digits = 2


class _Adapter:
    resolved_symbol = "BTCUSD"
    base_symbol = "BTCUSD"
    spec = _Spec()


class _ModeMgr:
    def __init__(self, mode): self._m = mode
    def params_for(self, sym): return ModeParams(self._m, 0.5, 0.1, "test")


class _Grad:
    def __init__(self, grad): self._g = grad
    def is_graduated(self, s): return self._g


class _Stub:
    def __init__(self, mode, graduated):
        self._edge_cache = {"phase": 2}       # global edge proven
        self.mode_mgr = _ModeMgr(mode)
        self.graduation = _Grad(graduated)


def _lot(stub):
    return ScalpEngine._position_lot(stub, _Adapter())


def test_training_symbol_never_sizes_up():
    # even in global Phase 2 and graduated, TRAINING mode -> micro lot
    stub = _Stub(TRAINING, graduated=True)
    assert _lot(stub) == config.SCALP_LOT


def test_live_but_not_graduated_stays_micro():
    stub = _Stub(LIVE, graduated=False)
    assert _lot(stub) == config.SCALP_LOT


if __name__ == "__main__":
    test_training_symbol_never_sizes_up()
    test_live_but_not_graduated_stays_micro()
    print("training-mode sizing safety tests passed")
