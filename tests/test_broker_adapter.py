"""
Regression tests for src.mt5.broker_adapter (#55 execution latency).

Strategy: because `broker_adapter` imports `mt5` at module-load time, we cannot
reliably patch it through `unittest.mock.patch` in a pytest context where the
module has already been imported.  Instead, each test constructs a tiny
**test double module** that exposes the same `mt5` API surface, patches that
module into `broker_adapter` by replacing `ba.mt5` directly, and pre-caches a
clean `SymbolSpec` so `resolve_symbol` does not need to interact with the mock.
"""
import sys, os, time, threading, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from src.mt5.broker_adapter import BrokerAdapter, SymbolSpec, OrderResult
from src.mt5 import broker_adapter as ba
from src.mt5 import connector as conn


class _Sentinel:
    """Thread-safe capture of order_send call count and concurrency."""
    def __init__(self):
        self.count = 0
        self.max_concurrent = 0
        self.current = 0
        self.lock = threading.Lock()
        self.delays = []

    def call(self, request):
        with self.lock:
            self.current += 1
            self.count += 1
            self.max_concurrent = max(self.max_concurrent, self.current)
        time.sleep(0.02)
        with self.lock:
            self.current -= 1
        self.delays.append(request)
        return SimpleNamespace(
            retcode=10009, price=2500.05, volume=request["volume"],
            order=123456, comment="done"
        )


def _make_fake_mt5():
    """Return a module-like object that quacks like MT5 for broker_adapter."""
    fake = SimpleNamespace()
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_SLTP = 6
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.POSITION_TYPE_BUY = 0
    fake.POSITION_TYPE_SELL = 1
    fake.ORDER_TIME_GTC = 0
    fake.ORDER_FILLING_IOC = 1
    fake.TRADE_RETCODE_DONE = 10009
    fake.SYMBOL_TRADE_MODE_FULL = 4
    fake.terminal_info = lambda: SimpleNamespace(trade_allowed=True)
    fake.account_info = lambda: SimpleNamespace(trade_allowed=True)
    fake.symbol_select = lambda name, visible: True
    info = SimpleNamespace(
        name="XAUUSD-ECN", digits=3, point=0.001,
        trade_tick_size=0.001, trade_tick_value=0.01,
        trade_contract_size=100_000,
        volume_min=0.01, volume_max=500.0, volume_step=0.01,
        trade_mode=4,
    )
    fake.symbol_info = lambda s: info
    fake.symbols_get = lambda: [info]
    fake.symbol_info_tick = lambda s: SimpleNamespace(
        ask=2500.10, bid=2500.00, time=1724000000, last=2500.05, volume=1
    )
    return fake


def _install_fake_mt5(fake):
    """Swap ba.mt5 and conn.mt5 for the fake, reset the connector singleton."""
    ba.mt5 = fake
    conn.mt5 = fake
    ba.MT5_AVAILABLE = True
    conn.MT5_AVAILABLE = True
    conn._connector_instance = None
    connector = MagicMock()
    connector.is_connected.return_value = True
    connector._connected = True
    conn._connector_instance = connector


def _make_adapter(mode="LIVE_MICRO"):
    fake = _make_fake_mt5()
    _install_fake_mt5(fake)
    ba._spec_cache.clear()
    ba._spec_cache["XAUUSD"] = SymbolSpec(
        base="XAUUSD", resolved="XAUUSD-ECN", digits=3, point=0.001,
        tick_size=0.001, tick_value=0.01, contract_size=100_000,
        min_volume=0.01, max_volume=500.0, volume_step=0.01, tradable=True,
    )
    return BrokerAdapter("XAUUSD", mode=mode), fake


def test_place_order_uses_mt5_lock():
    sentinel = _Sentinel()
    adapter, fake = _make_adapter()
    fake.order_send = sentinel.call

    result = adapter.place("buy", 0.01, sl=2490.0, tp=2520.0,
                           signal_price=2500.00)

    assert result.ok is True
    assert result.ticket == 123456
    assert sentinel.count == 1
    assert sentinel.max_concurrent <= 1, "mt5.order_send was entered concurrently"


def test_place_order_reject_logs_latency():
    adapter, fake = _make_adapter()
    fake.order_send = lambda req: SimpleNamespace(
        retcode=10027, comment="Too frequent requests", price=2500.0,
        volume=0.01, order=None
    )

    result = adapter.place("buy", 0.01, sl=2490.0, signal_price=2500.00)

    assert result.ok is False
    assert "rejected" in result.reason


def test_order_send_serialized_across_threads():
    sentinel = _Sentinel()
    adapter, fake = _make_adapter()
    fake.order_send = sentinel.call

    errors = []
    def run():
        try:
            r = adapter.place("buy", 0.01, sl=2490.0, signal_price=2500.00)
            if not r.ok:
                errors.append(r.reason)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, errors
    assert sentinel.count == 8
    assert sentinel.max_concurrent == 1, "concurrent order_send detected"


def test_paper_and_observe_never_call_order_send():
    def boom(req):
        raise RuntimeError("order_send must not be called")

    paper, fake_paper = _make_adapter(mode="PAPER")
    fake_paper.order_send = boom
    pr = paper.place("buy", 0.01, sl=2490.0)
    assert pr.ok is True
    assert pr.simulated is True

    obs, fake_obs = _make_adapter(mode="OBSERVE")
    fake_obs.order_send = boom
    or_ = obs.place("buy", 0.01, sl=2490.0)
    assert or_.ok is False
    assert "observe-only" in or_.reason


def _make_position(ptype=0, symbol="XAUUSD-ECN", volume=0.01, tp=2520.0, sl=0.0):
    return SimpleNamespace(type=ptype, symbol=symbol, volume=volume, tp=tp, sl=sl)


def test_close_and_modify_use_lock():
    sentinel = _Sentinel()
    adapter, fake = _make_adapter()
    fake.order_send = sentinel.call
    fake.positions_get = lambda **kw: [_make_position()]

    adapter.close(123)
    adapter.modify_sl(123, 2495.0)

    assert sentinel.count == 2
    assert sentinel.max_concurrent <= 1


def test_modify_sl_clamps_to_stops_level():
    """If requested SL is inside trade_stops_level, adapter must clamp outward."""
    adapter, fake = _make_adapter()
    sent = []
    fake.positions_get = lambda **kw: [_make_position(ptype=0, symbol="GER40.")]

    class Info:
        point = 0.1
        trade_stops_level = 500   # 50 pts minimum stop distance
        trade_freeze_level = 0

    fake.symbol_info = lambda s: Info()
    fake.symbol_info_tick = lambda s: SimpleNamespace(bid=26200.0, ask=26200.5)
    fake.order_send = lambda req: (sent.append(req), SimpleNamespace(
        retcode=10009, price=0.0, volume=0.0, order=123, comment="done"))[1]

    # requested SL only ~6 pts below current price for a buy; should be clamped to 50+1 pts
    adapter.modify_sl(123, 26195.0)
    assert len(sent) == 1
    assert sent[0]["sl"] == 26149.9  # 26200.0 - 51 pts (point=0.1)


def test_modify_sl_skips_inside_freeze_level():
    """If existing SL is inside trade_freeze_level of current price, skip."""
    adapter, fake = _make_adapter()
    sent = []
    # position with existing SL only 5 pts below current price -> inside 50pt freeze
    fake.positions_get = lambda **kw: [_make_position(ptype=0, symbol="GER40.", sl=26195.0)]

    class Info:
        point = 0.1
        trade_stops_level = 100
        trade_freeze_level = 500  # 50 pts freeze zone

    fake.symbol_info = lambda s: Info()
    fake.symbol_info_tick = lambda s: SimpleNamespace(bid=26200.0, ask=26200.5)
    fake.order_send = lambda req: (sent.append(req), SimpleNamespace(
        retcode=10009, price=0.0, volume=0.0, order=123, comment="done"))[1]

    result = adapter.modify_sl(123, 26180.0)
    assert not result.ok
    assert "freeze_level" in result.reason
    assert len(sent) == 0


def test_modify_sl_allows_legal_sl():
    """If requested SL is already beyond stops_level, it should pass through unchanged."""
    adapter, fake = _make_adapter()
    sent = []
    fake.positions_get = lambda **kw: [_make_position(ptype=0, symbol="GER40.")]

    class Info:
        point = 0.1
        trade_stops_level = 100   # 10 pts min distance
        trade_freeze_level = 0

    fake.symbol_info = lambda s: Info()
    fake.symbol_info_tick = lambda s: SimpleNamespace(bid=26200.0, ask=26200.5)
    fake.order_send = lambda req: (sent.append(req), SimpleNamespace(
        retcode=10009, price=0.0, volume=0.0, order=123, comment="done"))[1]

    adapter.modify_sl(123, 26180.0)  # 20 pts below price, legal
    assert len(sent) == 1
    assert sent[0]["sl"] == 26180.0


def test_modify_sl_sell_clamps_above_price():
    """For a sell position, SL must clamp upward above current price."""
    adapter, fake = _make_adapter()
    sent = []
    fake.positions_get = lambda **kw: [_make_position(ptype=1, symbol="GER40.")]

    class Info:
        point = 0.1
        trade_stops_level = 200   # 20 pts
        trade_freeze_level = 0

    fake.symbol_info = lambda s: Info()
    fake.symbol_info_tick = lambda s: SimpleNamespace(bid=26200.0, ask=26200.5)
    fake.order_send = lambda req: (sent.append(req), SimpleNamespace(
        retcode=10009, price=0.0, volume=0.0, order=123, comment="done"))[1]

    # requested SL only ~5 pts above ask for a sell; should clamp to 20+1 pts above ask
    adapter.modify_sl(123, 26205.5)
    assert len(sent) == 1
    assert sent[0]["sl"] == 26220.6  # ask 26200.5 + 21 pts (point=0.1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
