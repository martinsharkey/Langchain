# Daily Process & Adherence Checklist

> A repeatable process to ensure the bot keeps behaving as designed: the right
> indicators, wiring, learning loops, data flow, reporting, and cleanup. Run the
> checklist at the start of each working session. Detail lives in the linked design
> docs; this is the operational adherence layer on top of them.

## The design docs this enforces
- `CONFLUENCE_STRATEGY.md` — the entry (indicators, what we measure/tune).
- `RESEARCHER.md` — how research works.
- `LEARNING_LOOPS.md` — how the bot learns + every loop.
- `ARCHITECTURE_OVERVIEW.md` — how it's all wired.
- `DATA_SOURCES.md` — where every data source is.
- `EXIT_LEAK_FINDINGS.md` — the exit-management reality.

---

## A. Core behaviours that must always hold (the non-negotiables)

**Indicators (what we use):** OsMA, MACD, Bulls/Bears Power, EMA, ATR, RSI — computed
in `src/strategies/indicators.py`. Bulls=High-EMA(13), Bears=Low-EMA(13); the
`>=0`/`<=0` sign logic is DELIBERATE (memory `bulls_bears_power_logic`). MACD checked
vs the ZERO line, not the signal line.

**Entry (how we use them) = OsMA_Confluence ONLY.** Follow GoldShark; do NOT add
creative gates or an ensemble grab-bag. The structural rule: OsMA zero-cross +
OsMA accelerating + MACD aligned + ATR expanding + Bulls/Bears sign + EMA slope.
Per-symbol strength/quality is LEARNED (never hardcoded), and every learned gate must
pass a no-choke floor (min trades/day) so it can never block trading entirely.

**Exits:** MFE retention ratchet (broker stop at the floor) + gated reversal-signature
exit + fast 2s management loop. See `EXIT_LEAK_FINDINGS.md`.

**Safety floors:** `LEARNING_ADAPTATION_ENABLED`, `LEARNING_AUTO_REVERT_ENABLED`,
walk-forward gate on applied changes, `data_source != SIMULATED_OHLC` on training,
per-account scoping, governor/checkpointer can only LOWER graduation.

---

## B. Start-of-session checklist

1. `gh issue list` — review the backlog (GitHub is the source of truth).
2. `git status` / `git log --oneline -5` — know the current state.
3. **One engine only:** confirm no stale `app.py` process
   (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`). Two engines = the
   duplicate-engine bug (contradictory telemetry).
4. **MT5 health:** terminal running + logged in. Do NOT run a side `mt5.initialize()`
   while the engine runs (it clobbers the session -> `No data`).
5. `python -m pytest tests/ -q` — full suite green before trusting behaviour.

## C. Data-flow & learning-loop integrity tests

Run these to confirm the loops are CLOSED (not silently dead):

- **Entry fires:** watch `[ENTRY-QUALITY]` recipes load at startup and `OPENED ...`
  entries appear at ~GoldShark frequency (XAUUSD ~77/day, BTC ~32/day). If zero
  entries: check `[ENTRY-HOLD]` reasons — `no focused signal` means the overlay
  blocked it (empty pockets are now ignored, but verify `data/edge_weights.json`).
- **MFE/MAE recorded:** new closed trades have non-null `mfe_points`/`mae_points`/
  `peak_indicators` (else the capture loop is broken).
- **Reversal signatures armed:** `[REVERSAL-SEED]` per symbol at startup.
- **Reconcile closes the loop:** `trades.outcome` moves pending -> win/loss and
  `update_trade_outcome` fires.
- **Researcher ran:** daily `[RESEARCH]`/edge-discovery, `[POST-MORTEM]`, KnowledgeStore
  count rising.
- **Checkpointer active:** `[CHECKPOINT]`/`[REVERT]`/`[STALE-BEST]` as configs change.

Quick data-flow probe (adjust as needed):
```
sqlite: SELECT data_source, COUNT(*), AVG(mfe_points) FROM trades
        WHERE date(timestamp)=date('now') GROUP BY data_source;
```

## D. How the bot reports failure & success

- **Live status:** `data/bot_status.json` (cycle, running, opened/closed, graduation,
  learning_health incl exit_capture).
- **Logs:** `logs/trading_bot_<date>.log` — `[ENTRY-QUALITY]`, `[ENTRY-HOLD]`,
  `[REVERSAL-SEED]`, `[EXIT-LOCK]`, `[REVERT]`, `[POST-MORTEM]`, `OPENED`, `CLOSED`.
- **Auto-issues:** the researcher files GitHub issues for negative-expectancy symbols.
- **Monitor on demand:** `python live_monitor.py <minutes>` -> `data/monitor/*.jsonl`
  (per-poll open-position state + per-close realised outcome). Use this to verify
  claims against reality (not just log lines).

## E. Cleanup (each session / weekly)

- **Stale processes:** kill orphaned `python.exe app.py` before starting one engine.
- **`__pycache__`:** clear if code changed but behaviour looks stale
  (`Get-ChildItem -Recurse __pycache__ | Remove-Item -Recurse`).
- **Old logs:** `logs/trading_bot_*.log` rotate/prune beyond ~14 days.
- **Monitor dumps:** prune `data/monitor/*.jsonl` beyond what's needed for analysis.
- **Overlay sanity:** ensure `data/edge_weights.json` has NO empty focused pockets
  (empty = ignored now, but a stale file is confusing). Regenerate via edge-discovery
  or delete to fall back to the static GoldShark rule.
- **Polluted imports:** never leave mis-ingested rows in `trades` (wrong `data_source`,
  impossible MFE). Purge by `data_source` if an import goes wrong.

## F. Golden rules (from hard lessons this project learned)

1. **Follow GoldShark. Don't be creative with gates.** Every extra hard gate risks
   choking entries to zero. Prove a gate lifts entry-success AND keeps trades/day up
   before it goes live.
2. **Verify against reality, not log lines.** A logged intent (`retention_ratchet_sl`)
   is not proof the broker accepted it. Use the monitor + DB.
3. **One engine, one MT5 session.**
4. **Provenance + sanity on all data.** Phantom MFE and per-bar dumps have bitten us.
5. **Entry success ≠ profit.** ~85-95% entry-direction success still loses if exits
   give it back. Both must work.
