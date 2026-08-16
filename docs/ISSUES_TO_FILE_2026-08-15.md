# GitHub Issues to file — GoldShark M1 evidence (2026-08-15)

Repo: https://github.com/martinsharkey/Langchain
`gh` CLI is not installed on this machine. Either install it
(`winget install GitHub.cli` once winget is available) or paste these into
GitHub Issues manually. Evidence source: real live trades in
`data/trading_experience.db` (XAUUSD-ECN, 904 closed trades, 2026-08-09..14)
and `data/goldshark_history/XAUUSD_Unified_TradeLog.csv`.

---

## Issue 1 — [bug] Exit capture leak: winners keep only ~50% of MFE; 306 green trades turn into losses

**Labels:** bug, learning

**Evidence (real XAUUSD-ECN trades, n=904):**
- Win rate 49.8% (450W / 454L).
- Median winner capture ratio = 50% (202/439 winners kept <50% of their MFE).
- 306 of 454 losers reached >=20pt MFE (median +58pt) before reversing to a loss.
- Live GoldShark log exit reasons are dominated by "OsMA exhausted" firing AFTER
  the peak already collapsed (e.g. peak 2.72 -> current 1.13).
- Conservative break-even model (bounded by real loser counts, not wick MFE):
  a BE lock arming at +20pt / lock +2pt rescues 306 losers => -1,914pt realised
  becomes ~+18,800pt (~+£13.9k over the sample). Optimistic on fill, but the
  direction and the 306-loser count are real.

**Fix shipped:** `mql5/GoldShark_M5_Engine.mq5` — added break-even lock
(`InpBreakEvenArmPts=20`, `InpBreakEvenLockPts=2`) in ManageExits Phase 1b, and
clamped the trail so it never regresses below the armed BE. Recompiled 0/0.

**Next:** validate in MT5 Strategy Tester (real ticks) + forward on demo; tune
arm/lock and trail via `tools/mt5_set_tuner.py`.

---

## Issue 2 — [bug] Execution latency: mean ExecDelay 3,192ms (max 77s) corrupts M1 entries

**Labels:** bug, infra

**Evidence (`XAUUSD_Unified_TradeLog.csv`, v11.10 live):**
- ExecDelay_ms: median 45ms but MEAN 3,192ms, MAX 77,398ms (77 seconds).
- SlippagePts: median 0 but mean 17.7, max 536.
- Ping_ms ~16-18 (network is fine — the delay is in the execution path, not ping).
- On M1 a multi-second fill delay means entering far from the signal price; this
  is a primary suspect for why sim win-rate (bar-fill) >> live win-rate (~50%).

**Ask:** profile the order-send path in `src/trading/scalp_engine.py` /
`trade_manager.py`; find where the 3s+ delay originates (LLM in the hot path?
synchronous S3/RAG call? MT5 order_send retclass). Add a hard latency budget +
telemetry alarm. This likely matters more than any entry tuning.

---

## Issue 3 — [learning] Entry fakeout filter: losers have higher Bulls-power / RSI (buying tops)

**Labels:** learning

**Evidence (real winners vs losers at entry, ATR-normalised):**
- bulls_atr: winners median 0.211 vs losers 0.653 (losers much stronger bull power).
- rsi: winners 48.2 vs losers 51.7.
- Candidate filter `bulls_atr <= 0.4` lifts win rate 49.8% -> 55.6% (removes 273
  losers, at the cost of 223 winners — net trade count drops ~55%).
- `bulls<=0.6 AND rsi<=52` -> 54.6%.

**Interpretation:** the strongest bull-power entries are exhaustion/tops. A
bull-power CEILING (not floor) on longs would filter fakeouts. Secondary to the
exit fix, but real and tunable. Consider adding `InpLongBullsMax` / `InpShortBearsMin`
ceiling inputs to the EA and re-test.

---

## Reconcile summary (sim vs live)
Bar-fill port said 74.6% win / PF 1.69 on M1; live is 49.8%. The gap is NOT the
timeframe — it is (a) execution latency + slippage (Issue 2) and (b) the exit
capture leak (Issue 1) that the instant-fill sim cannot see. The M1 premise is
sound; the losses are exit + execution problems.
