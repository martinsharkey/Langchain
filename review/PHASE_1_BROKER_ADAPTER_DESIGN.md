# Phase 1 Design — `symbol_info`-Driven BrokerAdapter

**Status:** Design (Phase 0 complete). Implementation is Phase 1.
**Purpose:** A single, symbol-agnostic execution boundary that the trading loop
calls instead of asking an LLM to "execute". It resolves broker symbol
suffixes, computes correct lot sizing from live `symbol_info`, enforces mode
(OBSERVE/PAPER/LIVE_MICRO/LIVE), and is the ONLY place `order_send` is called.

This is the keystone that also makes crypto (Danny's L2) a config change later,
because nothing downstream hard-codes `XAUUSD` or gold-specific point values.

---

## 1. Why this abstraction

Today the loop "executes" via an LLM narration (`main.py`), the real
`place_order()` is orphaned, sizing math is wrong for gold (`risk_pips * 10`),
and `XAUUSD` is hard-coded everywhere (breaks on `XAUUSD-ECN`). The BrokerAdapter
fixes all four by centralizing execution behind one interface.

Existing primitives it will build on (already real):
- `src/mt5/data.py::get_symbol_info()` — returns `contract_size`, `tick_size`,
  `tick_value`, `min_volume`, `max_volume`, `volume_step`, `point`, `digits`.
- `src/mt5/data.py::get_last_price()` — live bid/ask/spread.
- `src/mt5/orders.py::place_order()/close_order()` — real `order_send` (currently orphaned).
- `src/mt5/account.py::get_account_info()/get_positions()/get_history()`.

---

## 2. Location & shape

New file: `src/mt5/broker_adapter.py`

```
@dataclass
class SymbolSpec:
    resolved: str          # broker's real symbol, e.g. "XAUUSD-ECN"
    base: str              # requested symbol, e.g. "XAUUSD"
    digits: int
    point: float
    tick_size: float
    tick_value: float      # account-currency value of one tick per 1.0 lot
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float

@dataclass
class OrderResult:
    ok: bool
    mode: str              # OBSERVE|PAPER|LIVE_MICRO|LIVE
    ticket: int | None     # real ticket (LIVE_*), synthetic id (PAPER), None (OBSERVE/reject)
    symbol: str
    action: str            # buy|sell
    requested_volume: float
    filled_volume: float
    price: float
    sl: float | None
    tp: float | None
    simulated: bool        # True for PAPER, False for LIVE_*
    reason: str            # human-readable status / rejection reason
    raw: dict | None       # underlying MT5 result for LIVE_*

class BrokerAdapter:
    def __init__(self, symbol: str, mode: str | None = None): ...
    def resolve_symbol(self) -> SymbolSpec: ...          # suffix handling + caching
    def calc_lot(self, balance, risk_percent, stop_distance_price) -> float: ...
    def place(self, action, volume, price, sl, tp, comment) -> OrderResult: ...
    def close(self, ticket, volume=0.0) -> OrderResult: ...
    def modify(self, ticket, sl=None, tp=None) -> OrderResult: ...   # fills orders.py gap
    def positions(self) -> list[dict]: ...
```

---

## 3. Symbol suffix resolution (fixes XAUUSD vs XAUUSD-ECN)

`resolve_symbol()` algorithm:
1. Try exact `get_symbol_info(base)`.
2. If not found, enumerate broker symbols (native `mt5.symbols_get()` / bridge
   equivalent) and match by prefix/regex: `^{base}([._-].*)?$` (covers
   `XAUUSD-ECN`, `XAUUSD.m`, `XAUUSD.raw`, `BTCUSD-ECN`, etc.).
3. Prefer a tradable symbol (`trade_mode` allows full trading) with the
   smallest suffix; call `symbol_select(resolved, True)` to ensure it's in
   Market Watch.
4. Cache the resolved `SymbolSpec`. Re-resolve on connection reset.
5. If nothing matches → raise; the loop treats it as "cannot trade this symbol".

Config: add optional `SYMBOL_OVERRIDE` env so a user can pin the exact broker
symbol and skip auto-resolution.

---

## 4. Correct position sizing (fixes the ~10x gold error)

Replace `main.py::_calculate_position_size` internals with:

```
risk_amount = balance * (risk_percent / 100.0)          # honors config.RISK_PERCENT
# value, in account currency, of a full 1.0-lot move over the stop distance:
ticks = stop_distance_price / spec.tick_size
loss_per_lot = ticks * spec.tick_value                  # derived from symbol_info, NOT a magic *10
raw_lots = risk_amount / loss_per_lot
# round DOWN to volume_step, clamp to [min_volume, max_volume]
lots = floor(raw_lots / spec.volume_step) * spec.volume_step
lots = clamp(lots, spec.min_volume, spec.max_volume)
lots = min(lots, config.MAX_POSITION_SIZE)              # honors config cap
if mode == "LIVE_MICRO":
    lots = min(lots, config.LIVE_MICRO_MAX_LOT)         # hard micro cap
```

This is correct for XAUUSD, FX, and crypto alike because every term comes from
`symbol_info`. No symbol-specific constants remain.

---

## 5. Mode behavior (the master safety gate)

`place()` branches on `config.TRADING_MODE`:

| Mode | place() behavior | ticket | simulated | writes to learning DB? |
|------|------------------|--------|-----------|------------------------|
| OBSERVE | Return `ok=False, reason="observe"` (loop already skips) | None | – | No |
| PAPER | Simulate fill at live ask/bid incl. spread; return synthetic ticket | `PAPER-<n>` | True | Yes, tagged `mode=PAPER` |
| LIVE_MICRO | `orders.place_order(...)` with lot capped to `LIVE_MICRO_MAX_LOT` | real | False | Yes, tagged `mode=LIVE_MICRO` |
| LIVE | `orders.place_order(...)` full sizing | real | False | Yes, tagged `mode=LIVE` |

PAPER fills use the REAL current price/spread (from `get_last_price`) so paper
results are realistic; they are clearly labelled everywhere (DB + dashboard).

---

## 6. Integration points (Phase 1 wiring)

1. `main.py::initialize_strategy` — construct `self.broker = BrokerAdapter(SYMBOL)`;
   call `resolve_symbol()` once and log the resolved symbol.
2. `main.py::_calculate_position_size` — delegate to `broker.calc_lot(...)`.
3. `main.py::execute_trade` — replace the "Phase 1 pending" stub with
   `result = self.broker.place(...)`; on `result.ok` create the tracked
   `OpenPosition` using `result.ticket`/`result.price`/`result.filled_volume`.
   (In OBSERVE, keep current behavior — no write.)
4. Use `SYMBOL` = resolved everywhere data is fetched so analysis and execution
   use the SAME broker symbol (`get_rates`, `get_last_price` calls should take the
   resolved symbol from the adapter).

Note: real outcome reconciliation (matching `result.ticket` to
`history_deals_get` on close) is **Phase 2**, not Phase 1. Phase 1 only makes
placement real and correctly sized; Phase 2 closes the learning loop on real fills.

---

## 7. Safety hooks (stubs in Phase 1, enforced in Phase 3)

`place()` will call a `RiskManager.check(order_ctx)` gate before any live send.
In Phase 1 this gate is a pass-through that logs; Phase 3 implements: max open
positions, daily-loss halt, spread ceiling, free-margin check, session check,
kill switch. Centralizing the call now means Phase 3 needs no loop changes.

---

## 8. Test plan (Phase 1 exit criteria)

- Unit: `calc_lot` returns correct lots for a known XAUUSD stop distance
  (e.g., balance 5000, risk 1%, stop $5.00 → lots derived from real tick_value),
  rounded to `volume_step`, clamped to caps.
- Unit: `resolve_symbol` maps `XAUUSD` → `XAUUSD-ECN` on this account.
- Integration (PAPER): a BUY decision yields a tracked position at the live ask,
  correct lot, `simulated=True`, DB row tagged PAPER.
- Integration (LIVE_MICRO): a 0.01 order actually appears in MT5, real ticket
  captured; then `close(ticket)` removes it.
- Regression: OBSERVE still writes nothing.

---

## 9. Crypto readiness (why this matters for Danny)

Because sizing and symbol handling are 100% `symbol_info`-driven:
- Adding `BTCUSD`/`ETHUSD` is a config/symbol change, not code.
- Danny's L2 order-book data becomes a new `data_source` feeding features; it
  does not touch the execution boundary.
- Crypto's 24/7 sessions only affect the Phase 3 session-check, not the adapter.
