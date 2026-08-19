# Plan: Test Isolation + Safe Bot Restart

> This document captures the agreed plan before implementation begins.
> It is a planning mirror; GitHub Issues remain the authoritative tracker.

## Context

The trading bot has a live/demo pipeline that must not be corrupted by tests or
automated restart:

```
vectorbt backtest (scripts/qmmp/vbt_ordermodel.py, vbt_model.py)
    ↓
Optuna floor tuning (scripts/qmmp/optuna_floor_optimizer.py)
    ↓
model.json + onboarding_report.md (scripts/qmmp/onboard_pipeline.py)
    ↓
EA generator (scripts/qmmp/ea_generator.py) → GoldShark_<SYM>.mq5
    ↓
Bot applies to demo (app.py LIVE_MICRO / scalp_engine.py)
    ↓
Live outcomes → trading_experience.db → config_checkpointer → retune
```

The live proven-state stores are:
- `data/config_checkpoints.json` — best-known configs + failed-direction memory.
- `data/tuned_params.json` — live indicator params applied by the signal path.
- `data/graduation.json` — per-symbol graduation state.
- `data/symbol_evidence.json` — research evidence history.
- `data/trading_experience.db` — closed-trade outcomes (ground truth).
- `data/qmmp/<SYM>/model.json` — onboarded, vectorbt/Optuna-validated configs.

## Problem statement

- Running the full pytest suite currently mutates live stores:
  - `config_checkpoints.json` gains synthetic failed directions.
  - `tuned_params.json` gains synthetic/reverted entries.
  - `graduation.json` and `symbol_evidence.json` are rewritten from test data.
- A future automated restart harness could overwrite successful live state if it
  does not snapshot before and validate after.
- The bot is currently restarted manually; there is no reusable, observable,
  safe restart procedure.

## Goal

Implement a phased plan that:
1. Protects live proven state from tests and restarts.
2. Provides a reusable, validated restart script.
3. Reuses existing vectorbt/Optuna/EA pipeline scripts; no rewrites.
4. Leaves all existing learning loops intact and operational.
5. Is reviewable issue-by-issue before merge.

## Phases

### Phase 1 — Defensive baseline (no behavior change)

Add `scripts/snapshot_state.py`:
- Snapshot the critical live data stores to
  `data/snapshots/YYYY-MM-DD_HHMMSS/`.
- Include: `config_checkpoints.json`, `tuned_params.json`, `graduation.json`,
  `symbol_evidence.json`, `trading_experience.db`, `bot_status.json`,
  `data/qmmp/*/model.json`.
- Add `--restore` mode to copy a snapshot back.
- Add JSON manifest inside snapshot with hashes + timestamps.

This script will be used by the restart script and can be used manually before
any risky operation.

**Acceptance criteria:**
- `python -m scripts.snapshot_state --list` shows existing snapshots.
- `python -m scripts.snapshot_state` creates a new snapshot and prints its path.
- `python -m scripts.snapshot_state --restore data/snapshots/...` restores all
  listed files atomically (write to .tmp, then rename).

### Phase 2 — Test isolation

1. Add `tests/conftest.py` with a session-scoped fixture:
   - Copy `data/` to a temp directory.
   - Monkeypatch `src.config.DATA_DIR` to that temp directory.
   - Reload modules that cache paths at import time
     (`src.learning.graduation`, `src.learning.param_optimizer`,
     `src.learning.config_checkpointer`, etc.).
   - Cleanup temp directory on teardown.

2. Add pytest marker `@pytest.mark.live` for tests that must run against real
   data/MT5. Default test run skips these.

3. Fix existing tests that currently write to live stores:
   - `test_continual_researcher.py` — redirect `symbol_evidence.json` path.
   - `test_symbol_governor.py` — ensure it uses temp graduation/evidence paths.
   - `test_self_correcting_loop.py` — already patches `TUNED_PATH`; verify no
     other live path is used.
   - Any other test that imports `src.config.DATA_DIR` at module level and
     writes files.

**Acceptance criteria:**
- Full pytest suite passes: 200+ tests, same or fewer skips.
- Snapshot of critical live files taken before and after `pytest tests/` shows
  **no changes** to hashes/mtimes.
- `test_bot_restart.py` is marked `@pytest.mark.live` and is skipped by default.

### Phase 3 — Safe restart harness

Add `scripts/restart_bot.py`:
1. Snapshot live state via `snapshot_state.py`.
2. Discover existing `python app.py` / `scalp_engine` processes and stop them
   cleanly (terminate, wait, kill if needed).
3. Verify MT5 terminal is running with the expected demo account
   (login/server from `.env`). If not, abort and restore snapshot.
4. Start `python app.py <mode>` as a fresh subprocess (default mode from
   `.env` or CLI arg).
5. Poll dashboard `/api/status` until:
   - `running=True`,
   - `algo_trading.can_trade=True`,
   - status timestamp is fresh (within 2× cycle seconds),
   - `open_positions` from dashboard matches MT5 positions whose magic equals
     `config.magic_for_symbol(sym)`.
6. Run lightweight vectorbt/Optuna verification:
   - `python -m scripts.qmmp.ea_generator <SYM> --verify` for each configured
     symbol.
   - Optional: replay current `model.json` through a short vectorbt backtest to
     confirm it still passes its historical gate (reuse
     `scripts/qmmp/vbt_model.py` or `vbt_ordermodel.py`).
7. If any validation fails, stop the new process and restore the snapshot.
8. Log every step to `logs/restart_bot_YYYY-MM-DD.log`.

**Acceptance criteria:**
- `python -m scripts.restart_bot --dry-run` reports what it would do without
  stopping/starting anything.
- `python -m scripts.restart_bot --mode PAPER` restarts in PAPER mode and
  validates dashboard + EA verify.
- `python -m scripts.restart_bot --mode LIVE_MICRO` requires an explicit
  `--confirm-live` flag.
- Failed restart leaves the original state restored and logs the reason.

### Phase 4 — CI/nightly wiring

Add `.github/workflows/restart_ci.yml`:
- Trigger: schedule (e.g. nightly) or `workflow_dispatch`.
- Job 1: run full pytest suite with isolated `DATA_DIR`.
- Job 2: run `restart_bot.py` in `PAPER` mode against a clean test environment
  (Windows runner required for MT5). Never auto-restart `LIVE_MICRO`.
- Add a separate `workflow_dispatch` job for `LIVE_MICRO` that requires manual
  approval.
- Artifacts: test report, snapshot diff, restart log.

**Acceptance criteria:**
- CI passes on `main` with isolated tests.
- Manual live-restart workflow is documented and gated.

## Reuse map

| Existing asset | Reused in |
|---|---|
| `scripts/qmmp/vbt_ordermodel.py` | restart validation vectorbt replay |
| `scripts/qmmp/optuna_floor_optimizer.py` | future retune step (not changed) |
| `scripts/qmmp/onboard_pipeline.py` | unchanged; still produces `model.json` |
| `scripts/qmmp/ea_generator.py` | restart `--verify` step |
| `dashboard/app.py` `/api/status` | restart health polling |
| `src/config.py` `magic_for_symbol` | adopted-position validation |
| `src/learning/config_checkpointer.py` | protected by isolation, unchanged |
| `src/learning/param_optimizer.py` | protected by isolation, unchanged |
| `src/learning/graduation.py` | protected by isolation, unchanged |

## Success definition

After this plan is complete:
- `pytest tests/` never changes `data/config_checkpoints.json`,
  `data/tuned_params.json`, `data/graduation.json`, `data/symbol_evidence.json`,
  or `data/trading_experience.db`.
- A bot restart can be performed safely with a single command that snapshots,
  restarts, validates, and rolls back on failure.
- The vectorbt → Optuna → model.json → bot → experience DB feedback loop remains
  intact and is not rewritten.
- Every phase is tracked as a GitHub issue and linked from
  `review/ISSUES_LOG.md`.

## Open questions for the review agent / user

1. Should `restart_bot.py` default to PAPER mode, or should it require an
   explicit mode argument?
2. Should the CI live-restart workflow require one or two human approvals?
3. Do we want the snapshot service to keep only the last N snapshots to avoid
   disk bloat?
4. Should vectorbt replay during restart validation be a fast smoke test
   (latest 1k bars) or the full historical gate?
