# Exit-Leak Findings — Live-Proven Root Cause (2026-08-03)

> Written from a 30-minute LIVE monitor of the running bot (`live_monitor.py`,
> 160 telemetry events, 26 closes, 133 open-position snapshots). This supersedes
> earlier assertions that the retention ratchet was "working" — it was not.

## TL;DR

The profit-retention exit protection **never worked in reality**. Every
stop-loss modification was silently rejected by the broker, and even after fixing
that, the dominant losses come from **intra-cycle round-trips the 15-second poll
loop physically cannot catch**. The exit leak is a **structural latency problem**,
not a logic problem. Fix = broker-side protection set at entry + fast management
polling.

## The evidence (live monitor, 26 closes)

- **Win rate 35%, median give-back of peak = 100%.** Half the trades that reached
  a real profitable peak gave back everything.
- **9 of 26 trades peaked >100 pts then exited at a loss/scratch.**
- Examples:
  - BTCUSD #5256: MFE **16,764 pts** → exit +285 pts (gave back 98%), pnl +0.02
  - BTCUSD #5270: MFE **15,173 pts** → exit −529 pts, pnl −0.04
  - XAUUSD #5255: MFE 700 pts → exit 3 pts (gave back 100%), pnl −0.02

## Root cause #1 — the ratchet SL was rejected every time (now fixed)

The retention ratchet computed a floor stop and logged `retention_ratchet_sl`, but:

- `adapter.modify_sl(...)` was **rejected by MT5 with `retcode=10016 "Invalid
  stops"`** on essentially every attempt.
- The engine **discarded the result**, so the failure was invisible — the log line
  made it *look* like the ratchet fired when the broker SL never actually moved.

Why `10016`: by the time the 15 s poll fires, price has already fallen back through
the intended floor, so a "stop loss" placed there is on the wrong side of / too
close to market and MT5 refuses it.

**Fix applied:** the engine now checks the `modify_sl` result, logs rejections, and
— if a *profit-protecting* stop can't be placed — **closes the trade outright** to
salvage the peak. This works when the poll catches it (e.g. #5254 BTC exited
+2447 pts / +£0.19 near peak).

## Root cause #2 — intra-cycle latency (structural, the real leak)

Even the fallback-close is often too late:

- BTCUSD #5270 peaked **+15,173 pts** and still exited **−529** because the peak
  formed *and* collapsed **between two 15-second polls**.
- BTC's favourable excursions form and reverse inside a single cycle.

**No poll-rate logic — ratchet, reversal signature, or fallback-close — can catch a
move that both peaks and reverses between polls.** Everything built so far operates
at the 15 s cadence (`SCALP_CYCLE_SECONDS`), so it structurally cannot protect these.

## The fixes (both structural)

### Fix 1 — broker-side protection set AT ENTRY
Attach a stop-loss and take-profit (and, where supported, a trailing stop) to the
order at placement time so **MT5 enforces them tick-by-tick with zero polling
latency**. This is the only real cure for the intra-cycle movers: the broker will
close at the protective level even while Python is asleep between cycles.

### Fix 2 — fast management polling for open positions
Run a separate, fast (1–2 s) loop that manages *open positions only* (SL moves,
ratchet, reversal exit), decoupled from the 15 s *entry* evaluation loop. This
tightens the window in which a peak can round-trip unseen, at modest extra
CPU/API cost.

## What was already correct (keep)

- Entry indicators captured at trigger time (no hindsight).
- MFE/MAE + `data_source` provenance logging.
- Per-symbol scale-free reversal signature (armed for XAUUSD/BTCUSD/GER40 from
  seeded GoldShark data) — it just needs a faster/broker-side actuator to matter.

## Honest status

The exit leak is **not solved** by anything shipped before this document. The
ratchet-SL-rejection fix is a partial mitigation. The structural fixes above are
required for real improvement, and even then intra-cycle whipsaws (peak → deep
adverse within one tick burst) will remain the hardest case.

## Telemetry for training

`data/monitor/live_monitor_*.jsonl` — per-poll open-position state (entry, live
price, observed peak/trough, SL distance, is-SL-protecting) + per-close realised
outcome (pnl, MFE/MAE, exit_points, exit_reason, gave-back %). Use this to train/
validate exit policy against real intra-cycle behaviour.
