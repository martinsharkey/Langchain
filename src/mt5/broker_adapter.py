"""
BrokerAdapter — the single, symbol-agnostic execution boundary.

This is the ONLY place the system sends real orders. It:
  * Resolves a base symbol (e.g. "XAUUSD") to the broker's TRADABLE variant
    (e.g. "XAUUSD-ECN"), skipping disabled variants (e.g. "XAUUSD.crp").
  * Reads live symbol specs (tick_value, volume_step, min/max) for CORRECT
    position sizing — no gold-specific magic numbers.
  * Checks the MT5 "Algo Trading" terminal flag + account trade permission,
    so we can tell you exactly why an order would be blocked.
  * Places / closes real orders via order_send.
  * Honors TRADING_MODE (OBSERVE / PAPER / LIVE_MICRO / LIVE).

Because everything is driven by live symbol_info, adding BTCUSD or any other
symbol is a config change, not a code change.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict
from typing import Optional

from src.mt5.connector import get_connector, MT5_AVAILABLE, mt5, mt5_lock
from src import config
from src.utils.logger import get_logger

logger = get_logger("mt5.broker")


def _latency_log(action: str, symbol: str, signal_price: float, price: float,
                 filled_volume: float, sl: Optional[float], tp: Optional[float],
                 t0: float, t1: float, retcode: Optional[int], reason: str):
    """Emit a single [LATENCY] micro-log line for every real order path.

    Fields are chosen so the dashboard/trade log can compute ExecDelay_ms,
    SlippagePts, and reject reasons without parsing free-form text.
    """
    pt = 1.0
    if symbol and price:
        # try to resolve point size for slippage in points
        try:
            spec = resolve_symbol(symbol.upper().split("-")[0].split(".")[0])
            pt = spec.point if spec and spec.point else 1.0
        except Exception:
            pass
    delay_ms = int(round((t1 - t0) * 1000))
    slippage = round((price - signal_price) / pt, 2) if pt else 0.0
    logger.info(
        f"[LATENCY] {action} {symbol} signal={signal_price:.5f} fill={price:.5f} "
        f"vol={filled_volume} slippage_pts={slippage:.2f} delay_ms={delay_ms} "
        f"retcode={retcode} reason={reason}"
    )



@dataclass
class SymbolSpec:
    base: str
    resolved: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    tradable: bool


@dataclass
class AlgoStatus:
    terminal_trade_allowed: bool   # the Algo Trading button (green/red)
    account_trade_allowed: bool
    connected: bool

    @property
    def can_trade(self) -> bool:
        return self.terminal_trade_allowed and self.account_trade_allowed and self.connected

    @property
    def reason(self) -> str:
        if not self.connected:
            return "MT5 not connected"
        if not self.terminal_trade_allowed:
            return "Algo Trading is DISABLED in MT5 (red stop). Click the 'Algo Trading' button to enable."
        if not self.account_trade_allowed:
            return "Account trading not permitted by broker/server."
        return "OK"


@dataclass
class OrderResult:
    ok: bool
    mode: str
    ticket: Optional[int]
    symbol: str
    action: str
    requested_volume: float
    filled_volume: float
    price: float
    sl: Optional[float]
    tp: Optional[float]
    simulated: bool
    reason: str
    retcode: Optional[int] = None


# module-level cache of resolved specs {base: SymbolSpec}
_spec_cache: dict[str, SymbolSpec] = {}
_PAPER_TICKET_SEQ = 90_000_000


def get_algo_status() -> AlgoStatus:
    """Read the live Algo Trading / trade-permission state from MT5."""
    connector = get_connector()
    connected = connector.is_connected()
    term_ok = False
    acct_ok = False
    if MT5_AVAILABLE and connected:
        try:
            with mt5_lock():
                ti = mt5.terminal_info()
                ai = mt5.account_info()
            term_ok = bool(ti.trade_allowed) if ti else False
            acct_ok = bool(ai.trade_allowed) if ai else False
        except Exception as e:
            logger.warning(f"get_algo_status failed: {e}")
    return AlgoStatus(terminal_trade_allowed=term_ok,
                      account_trade_allowed=acct_ok,
                      connected=connected)


def resolve_symbol(base: str, use_cache: bool = True) -> Optional[SymbolSpec]:
    """
    Resolve a base symbol to the broker's tradable variant and return its spec.

    Strategy: gather all broker symbols whose name starts with the base
    (case-insensitive), prefer the one whose trade_mode == full (tradable),
    ensure it's selected in Market Watch, and return its live spec.
    """
    base = base.upper().strip()
    if use_cache and base in _spec_cache:
        return _spec_cache[base]

    connector = get_connector()
    if not connector.is_connected():
        connector.initialize()
    if not (MT5_AVAILABLE and connector.is_connected()):
        logger.warning("resolve_symbol: MT5 not available/connected")
        return None

    try:
        full_mode = getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4)
        with mt5_lock():
            candidates = []

            # exact match first
            exact = mt5.symbol_info(base)
            if exact is not None:
                candidates.append(exact)

            # prefix matches (XAUUSD-ECN, XAUUSD.crp, BTCUSD, etc.)
            allsyms = mt5.symbols_get() or []
            for s in allsyms:
                if s.name.upper().startswith(base) and s.name != base:
                    candidates.append(s)

            if not candidates:
                logger.warning(f"resolve_symbol: no broker symbol matches '{base}'")
                return None

            # prefer tradable (trade_mode == full), then shortest name (least suffix)
            def score(s):
                return (0 if s.trade_mode == full_mode else 1, len(s.name))
            candidates.sort(key=score)
            chosen = candidates[0]

            # make sure it's visible/selected
            mt5.symbol_select(chosen.name, True)
            info = mt5.symbol_info(chosen.name)
        if info is None:
            return None

        # Defensive: coerce any MagicMock / RPyC proxy attributes to plain Python
        # values so downstream logic and tests work with real primitives.
        def _plain(value, fallback=""):
            if value is None:
                return fallback
            if isinstance(value, (str, int, float, bool)):
                return value
            if hasattr(value, "__str__"):
                try:
                    s = str(value)
                    if not s.startswith("<"):
                        return s
                except Exception:
                    pass
            return getattr(value, "_mock_name", fallback)

        resolved_name = _plain(info.name, base)
        digits = int(_plain(info.digits, 5))
        point = float(_plain(info.point, 0.01))
        tick_size = float(_plain(info.trade_tick_size, point))
        tick_value = float(_plain(info.trade_tick_value, 0.0))
        contract_size = float(_plain(info.trade_contract_size, 1.0))
        min_volume = float(_plain(info.volume_min, 0.01))
        max_volume = float(_plain(info.volume_max, 100.0))
        volume_step = float(_plain(info.volume_step, 0.01))
        trade_mode = _plain(info.trade_mode, 0)
        spec = SymbolSpec(
            base=base,
            resolved=resolved_name,
            digits=digits,
            point=point,
            tick_size=tick_size,
            tick_value=tick_value,
            contract_size=contract_size,
            min_volume=min_volume,
            max_volume=max_volume,
            volume_step=volume_step,
            tradable=(trade_mode == full_mode),
        )
        _spec_cache[base] = spec
        logger.info(f"Resolved '{base}' -> '{spec.resolved}' (tradable={spec.tradable}, "
                    f"tick_value={spec.tick_value}, step={spec.volume_step})")
        if not spec.tradable:
            logger.warning(f"Resolved symbol '{spec.resolved}' is NOT tradable (trade_mode disabled).")
        return spec
    except Exception as e:
        logger.warning(f"resolve_symbol error for '{base}': {e}")
        return None


def _round_to_step(volume: float, step: float, vmin: float, vmax: float) -> float:
    if step <= 0:
        step = 0.01
    lots = math.floor(volume / step) * step
    lots = max(vmin, min(lots, vmax))
    # clean float noise
    return round(lots, 2)


class BrokerAdapter:
    """Per-symbol execution handle."""

    def __init__(self, base_symbol: str, mode: Optional[str] = None):
        self.base = base_symbol.upper().strip()
        self.mode = (mode or config.TRADING_MODE).upper()
        self.spec: Optional[SymbolSpec] = resolve_symbol(self.base)

    # ---- info ----
    @property
    def resolved_symbol(self) -> Optional[str]:
        return self.spec.resolved if self.spec else None

    def refresh_spec(self):
        self.spec = resolve_symbol(self.base, use_cache=False)
        return self.spec

    # ---- sizing ----
    def calc_lot(self, balance: float, risk_percent: float, stop_distance_price: float) -> float:
        """
        Correct, symbol-agnostic lot sizing derived from live tick_value.
        loss_per_lot = (stop_distance / tick_size) * tick_value
        """
        if not self.spec:
            return 0.0
        if stop_distance_price <= 0 or self.spec.tick_size <= 0 or self.spec.tick_value <= 0:
            return self.spec.min_volume
        risk_amount = balance * (risk_percent / 100.0)
        ticks = stop_distance_price / self.spec.tick_size
        loss_per_lot = ticks * self.spec.tick_value
        if loss_per_lot <= 0:
            return self.spec.min_volume
        raw = risk_amount / loss_per_lot
        lots = _round_to_step(raw, self.spec.volume_step, self.spec.min_volume, self.spec.max_volume)
        lots = min(lots, config.MAX_POSITION_SIZE)
        if self.mode == "LIVE_MICRO":
            lots = min(lots, config.LIVE_MICRO_MAX_LOT)
        return _round_to_step(lots, self.spec.volume_step, self.spec.min_volume, self.spec.max_volume)

    def live_tick(self):
        if not self.spec:
            return None
        with mt5_lock():
            t = mt5.symbol_info_tick(self.spec.resolved)
            # Defensive: unwrap MagicMock so tests and RPyC return the same shape.
            if t is None:
                return None
            return {
                "ask": float(getattr(t, "ask", 0.0) or 0.0),
                "bid": float(getattr(t, "bid", 0.0) or 0.0),
                "time": getattr(t, "time", 0),
                "last": float(getattr(t, "last", 0.0) or 0.0),
                "volume": int(getattr(t, "volume", 0) or 0),
            }

    # ---- execution ----
    def place(self, action: str, volume: float, sl: Optional[float] = None,
              tp: Optional[float] = None, comment: str = "agent",
              signal_price: Optional[float] = None) -> OrderResult:
        global _PAPER_TICKET_SEQ
        action = action.lower()
        t0 = time.time()

        if action not in ("buy", "sell"):
            return self._reject(action, volume, "invalid action")

        if not self.spec:
            return self._reject(action, volume, f"symbol '{self.base}' not resolved")

        tick = self.live_tick()
        if tick is None:
            return self._reject(action, volume, "no live price")
        price = tick["ask"] if action == "buy" else tick["bid"]
        signal_price = signal_price if signal_price is not None else price

        # OBSERVE: never place, never record
        if self.mode == "OBSERVE":
            return OrderResult(False, self.mode, None, self.spec.resolved, action,
                               volume, 0.0, price, sl, tp, False, "observe-only (no order)")

        # PAPER: simulate a fill at the live price
        if self.mode == "PAPER":
            _PAPER_TICKET_SEQ += 1
            return OrderResult(True, self.mode, _PAPER_TICKET_SEQ, self.spec.resolved, action,
                               volume, volume, price, sl, tp, True, "paper fill @ live price")

        # LIVE_MICRO / LIVE: real order — but first check Algo Trading
        algo = get_algo_status()
        if not algo.can_trade:
            _latency_log(action, self.spec.resolved, signal_price, price, 0.0,
                         sl, tp, t0, time.time(), None, f"algo-blocked:{algo.reason}")
            return self._reject(action, volume, algo.reason)

        if not self.spec.tradable:
            _latency_log(action, self.spec.resolved, signal_price, price, 0.0,
                         sl, tp, t0, time.time(), None, "symbol-not-tradable")
            return self._reject(action, volume,
                                f"symbol '{self.spec.resolved}' is not tradable (trade_mode disabled)")

        # cap volume for micro mode
        vol = volume
        if self.mode == "LIVE_MICRO":
            vol = min(vol, config.LIVE_MICRO_MAX_LOT)
        vol = _round_to_step(vol, self.spec.volume_step, self.spec.min_volume, self.spec.max_volume)

        order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.spec.resolved,
            "volume": float(vol),
            "type": order_type,
            "price": float(price),
            "deviation": 30,
            "magic": config.BOT_MAGIC,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl:
            request["sl"] = float(sl)
        if tp:
            request["tp"] = float(tp)

        try:
            with mt5_lock():
                result = mt5.order_send(request)
        except Exception as e:
            _latency_log(action, self.spec.resolved, signal_price, price, 0.0,
                         sl, tp, t0, time.time(), None, f"order_send_exception:{e}")
            return self._reject(action, vol, f"order_send exception: {e}")

        t1 = time.time()
        if result is None:
            _latency_log(action, self.spec.resolved, signal_price, price, 0.0,
                         sl, tp, t0, t1, None, f"order_send_None:{mt5.last_error()}")
            return self._reject(action, vol, f"order_send None; last_error={mt5.last_error()}")

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            _latency_log(action, self.spec.resolved, signal_price, price, 0.0,
                         sl, tp, t0, t1, result.retcode, f"rejected:{result.comment}")
            return OrderResult(False, self.mode, None, self.spec.resolved, action,
                               vol, 0.0, price, sl, tp, False,
                               f"rejected: {result.comment}", retcode=result.retcode)

        ticket = getattr(result, "order", None) or getattr(result, "deal", None)
        fill_price = getattr(result, "price", price) or price
        fill_vol = getattr(result, "volume", vol) or vol
        _latency_log(action, self.spec.resolved, signal_price, fill_price, fill_vol,
                     sl, tp, t0, t1, result.retcode, "filled")
        logger.info(f"ORDER FILLED {action.upper()} {self.spec.resolved} {fill_vol}@{fill_price} ticket={ticket}")
        return OrderResult(True, self.mode, ticket, self.spec.resolved, action,
                           vol, fill_vol, fill_price, sl, tp, False, "filled",
                           retcode=result.retcode)


    def close(self, ticket: int, volume: float = 0.0) -> OrderResult:
        """Close an open position by ticket (LIVE modes only)."""
        t0 = time.time()
        if self.mode in ("OBSERVE", "PAPER"):
            return OrderResult(True, self.mode, ticket, self.resolved_symbol or self.base,
                               "close", volume, volume, 0.0, None, None,
                               self.mode == "PAPER", f"{self.mode} close (no real order)")
        try:
            with mt5_lock():
                pos = mt5.positions_get(ticket=ticket)
                if not pos:
                    return self._reject("close", volume, f"position {ticket} not found")
                p = pos[0]
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                tick = mt5.symbol_info_tick(p.symbol)
                price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol,
                    "volume": float(volume or p.volume),
                    "type": close_type,
                    "position": ticket,
                    "price": float(price),
                    "deviation": 30,
                    "magic": config.BOT_MAGIC,
                    "comment": "agent-close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
            t1 = time.time()
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                rc = result.retcode if result else None
                cm = result.comment if result else mt5.last_error()
                _latency_log("close", p.symbol, price, price, 0.0, None, None, t0, t1, rc, f"rejected:{cm}")
                return OrderResult(False, self.mode, ticket, p.symbol, "close",
                                   volume, 0.0, price, None, None, False,
                                   f"close rejected: {cm}", retcode=rc)
            _latency_log("close", p.symbol, price, result.price, volume or p.volume,
                         None, None, t0, t1, result.retcode, "closed")
            return OrderResult(True, self.mode, ticket, p.symbol, "close",
                               volume or p.volume, volume or p.volume, result.price, None, None,
                               False, "closed", retcode=result.retcode)
        except Exception as e:
            return self._reject("close", volume, f"close exception: {e}")

    def modify_sl(self, ticket: int, sl: float, tp: Optional[float] = None) -> OrderResult:
        """
        Modify the BROKER-SIDE stop-loss (and optionally TP) of an open position.
        This is how the TradeManager moves to BE+/trails — the SL always lives on
        the broker, so the trade is never left unprotected.
        """
        t0 = time.time()
        if self.mode in ("OBSERVE", "PAPER"):
            # paper: pretend success (state tracked in-memory by the manager)
            return OrderResult(True, self.mode, ticket, self.resolved_symbol or self.base,
                               "modify", 0.0, 0.0, sl, sl, tp, self.mode == "PAPER",
                               f"{self.mode} modify (no real order)")
        try:
            with mt5_lock():
                pos = mt5.positions_get(ticket=ticket)
                if not pos:
                    return self._reject("modify", 0.0, f"position {ticket} not found")
                p = pos[0]
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": p.symbol,
                    "position": ticket,
                    "sl": float(sl),
                    "tp": float(tp if tp is not None else p.tp),
                }
                result = mt5.order_send(request)
            t1 = time.time()
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                rc = result.retcode if result else None
                cm = result.comment if result else mt5.last_error()
                _latency_log("modify", p.symbol, 0.0, 0.0, 0.0, sl, tp, t0, t1, rc, f"rejected:{cm}")
                return OrderResult(False, self.mode, ticket, p.symbol, "modify",
                                   0.0, 0.0, sl, sl, tp, False,
                                   f"modify rejected: {cm}", retcode=rc)
            _latency_log("modify", p.symbol, 0.0, 0.0, 0.0, sl, tp, t0, t1, result.retcode, "modified")
            logger.info(f"SL modified for {ticket} -> {sl}")
            return OrderResult(True, self.mode, ticket, p.symbol, "modify",
                               0.0, 0.0, sl, sl, tp, False, "modified", retcode=result.retcode)
        except Exception as e:
            return self._reject("modify", 0.0, f"modify exception: {e}")

    def _reject(self, action, volume, reason) -> OrderResult:
        logger.warning(f"Order rejected [{self.base}/{self.mode}] {action} {volume}: {reason}")
        return OrderResult(False, self.mode, None, self.resolved_symbol or self.base,
                           action, volume, 0.0, 0.0, None, None,
                           self.mode == "PAPER", reason)
