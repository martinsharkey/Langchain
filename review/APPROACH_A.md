# Approach A: One MT5 Terminal Per Symbol (Prototype)

## Goal
Run each traded symbol (XAUUSD, BTCUSD, GER40) in its own isolated MT5 terminal
so that symbol-specific crashes, data gaps, or EA bugs cannot contaminate the fleet.

## Current state
- Single `terminal64.exe` process serves all three symbols.
- One `scalp_engine.py` loop polls all symbols sequentially.
- Shared state files: `bot_status.json`, `risk_state.json`, `trading_experience.db`.

## Proposed prototype
1. **Config-driven terminal profiles**
   - Add `data/terminals.json` mapping symbol -> terminal profile (path, port, account).
   - Each profile launches its own `terminal64.exe` with `/config=profile_name`.

2. **Per-symbol bot workers**
   - Spawn one `python app.py LIVE_MICRO --symbol XAUUSD` per terminal.
   - Each worker reads its symbol from env and only trades that symbol.
   - Shared `trading_experience.db` remains the single source of truth.

3. **Supervisor process**
   - `scripts/multi_terminal_supervisor.py` launches workers, monitors health,
     restarts crashed workers, and aggregates status for the dashboard.

4. **Rollback path**
   - Keep existing single-terminal mode as default.
   - Approach A is opt-in via `MULTI_TERMINAL=true` in `.env`.

## Risks
- Increased memory/CPU footprint (3 terminals).
- Dashboard must aggregate per-symbol status.
- MT5 demo account may not support 3 simultaneous logins from the same server.

## Milestone
- Prototype working for 2 symbols (XAUUSD + BTCUSD) on Windows.
- Issue #90 tracks this work.
