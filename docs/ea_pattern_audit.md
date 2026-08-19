# MQL5 EA Pattern Audit (Issue #86)

Sampled EAs:
- `GoldShark3 v3.04.mq5` (cleanest unified zero-cross engine)
- `GoldShark14.mq5` (data-driven simple exit, CSV lifecycle logging)
- `GoldShark15.mq5` (SQLite lifecycle logging, MTF shadow trailing)
- `OFTradeManager.mq5` (daily stop + GMT schedule + grid/basket)

## 1. Lot sizing / balance scaling

| EA | Input | Formula | Notes |
|----|-------|---------|-------|
| GoldShark3 | `InpBalancePerLot` | `(balance / InpBalancePerLot) * 0.01` | Then `MathFloor` by `SYMBOL_VOLUME_STEP`, `minVol` fallback |
| GoldShark14 | `InpBalancePerLot` | `(balance / InpBalancePerLot) * 0.01` | Geometric decay: `baseLot * MathPow(0.5, openTrades)` |
| GoldShark15 | `InpBalancePerLot` | `(balance / InpBalancePerLot) * 0.01` | Broker max clamp (`InpBrokerMaxLots`) |
| OFTradeManager | `InpLots` | fixed `0.1` | No balance scaling; manual lot only |

**Reusable pattern**: balance-per-lot with `floor(balance / GBP_per_001) * 0.01` is the family standard.
Clamping should use `SYMBOL_VOLUME_MIN/MAX/STEP` (not just `NormalizeDouble`).

## 2. Daily stop / circuit breaker

| EA | Input | Behaviour |
|----|-------|-----------|
| GoldShark3 | `InpMaxDrawdownPct` | Equity drop % → close all + `ExpertRemove()` |
| GoldShark14 | `InpMaxDrawdownPct` + `InpMaxAccountLossPct` | DD% halts; account-loss% closes all |
| GoldShark15 | (none explicit in sampled header) | drawdown handled by shadow lifecycle |
| OFTradeManager | `InpDailyDrawdownPct` | closes trades and **locks EA** for rest of day |

**Reusable pattern**: track start-of-day balance; if `equity <= balance * (1 - pct/100)` stop new entries
and optionally flatten. OFTradeManager’s "lock until next day" is clean.

## 3. Session / time-aware trading

| EA | Inputs | Behaviour |
|----|--------|-----------|
| GoldShark3 | none | none |
| GoldShark14 | `InpEnableSessionFilter`, per-session booleans, `InpBrokerGMTOffset`, `InpAvoidRollover`, `InpRolloverBufferMins` | Convert server time to GMT; allow London/NY/Asian; block rollover window |
| GoldShark15 | hardcoded session defines (`SESSION_LONDON_START` etc) | Used only for lifecycle tag, not entry gate |
| OFTradeManager | `InpStartHourGMT`, `InpEndHourGMT`, `InpTradeMon..Fri` | Daily GMT schedule + weekday toggles |

**Reusable pattern**: server-time → GMT conversion with `InpBrokerGMTOffset`; per-session enable + rollover buffer.
This is exactly what the generated EA should expose.

## 4. Magic number / trade identification

| EA | Approach |
|----|----------|
| GoldShark3 | single `InpMagicNumber = 987654` |
| GoldShark14 | `InpMagicNumberBase = 987654` + per-symbol magic function |
| GoldShark15 | single `InpMagicNumber = 987654` |
| OFTradeManager | `sinput ulong InpMagic = 72001` |

**Reusable pattern**: single input per symbol, but deterministic per-symbol magic to avoid collisions when
running the same EA on multiple charts. Python already has `src.config.magic_for_symbol(sym)`.

## 5. UX / inputs panel

- `input group "=== ... ==="` headers are used everywhere.
- Group ordering: core/risk → indicators → entry thresholds → exit → logging.
- GoldShark14 has the most complete UX: session filtering, latency tracking, analytics endpoint, diagnostics.
- OFTradeManager uses `sinput` for magic/comment (not optimiser-exposed).

**Recommendation for generated EA**: keep `input group` blocks; add a top "Risk & protection" group,
"Session / time", "Entry / OsMA", "Per-session floors", "Exit", "Logging".

## 6. Trade logging

| EA | Format | Columns |
|----|--------|---------|
| GoldShark14 | CSV (`_Unified_TradeLog.csv`) | TradeID, Symbol, Direction, EntryTime, EntryPrice, OsMA, Bulls, Bears, EMA slope, price stretch, ATR, latency, session, etc. |
| GoldShark15 | SQLite (`_UnifiedLog.sqlite`) | Same family of fields plus per-candle snapshots (`PositionOpen`, `Status`, `PeakProfitPts`, `MaxDrawdownPts`, `ExitReason`) |
| GoldShark3 | Print only | No structured log |
| OFTradeManager | Print + objects | No lifecycle file |

**Reusable pattern**: a queued lifecycle log flushed periodically.
GoldShark15’s `LifecycleTracker` + `LogLifecycleCandle` + `FlushLifecycleLog()` is the most complete reference.
A simpler CSV equivalent (GoldShark14) is easier to ingest from Python.

## Concrete recommendations for `ea_generator.py`

1. **Add a "Risk & protection" input group**:
   - `InpMaxDrawdownPct` — equity drop halt.
   - `InpDailyDrawdownPct` — realized daily loss lock (like OFTradeManager).
   - `InpMinAccountBalance` — refuse new trades if balance below.

2. **Add a "Session / time" input group**:
   - `InpBrokerGMTOffset` (default 3 for current server).
   - `InpTradeLondon`, `InpTradeNY`, `InpTradeAsian` booleans.
   - `InpAvoidRollover`, `InpRolloverBufferMins`.
   - `InpTradeMonday..Friday` toggles.

3. **Improve lot sizing**:
   - Keep `GBP_per_001`/`InpBalancePerLot` formula.
   - Clamp with `SYMBOL_VOLUME_MIN`, `SYMBOL_VOLUME_MAX`, `SYMBOL_VOLUME_STEP`.
   - Add `InpMaxLotsPerAccount` cap.

4. **Improve magic number UX**:
   - Expose `InpMagicNumber` input, but default to the deterministic per-symbol value from `magic_for_symbol(sym)`.

5. **Add lifecycle logging group**:
   - `InpLogToCSV` / `InpLogToSQLite` toggle.
   - `InpLogFolder`.
   - Log entry snapshot + one row per closed candle + close row with exit reason.

## Files sampled

- `C:\Users\MartinSharkey\Documents\Langchain\MT5_OLD_EA's\GoldShark3_v3.04.mq5`
- `C:\Users\MartinSharkey\Documents\Langchain\MT5_OLD_EA's\Goldshark\GoldShark14.mq5`
- `C:\Users\MartinSharkey\Documents\Langchain\MT5_OLD_EA's\Goldshark\GoldShark15.mq5`
- `C:\Users\MartinSharkey\Documents\Langchain\MT5_OLD_EA's\OrderFlow\OFTradeManager.mq5`
