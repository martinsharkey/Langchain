# Distributed Service Architecture — Design (Issue #1)

Status: DESIGN ONLY. Do NOT build yet. Per STRATEGY_OBJECTIVE.md this is Phase 4
(Scale) work — it must wait until an edge is proven (PF>=1.3 over 200+ trades).
Building multi-VPS deployment for a PF~1.0 system would be premature. This doc
captures the plan so it's ready when the edge is real.

## The one hard constraint that drives everything
One MT5 terminal <-> one broker account <-> ONE authoritative writer of positions.
You cannot run two processes trading the same account (that's double-trading, not
redundancy). The BROKER is the source of truth for positions, not our local files.
Every safety property below depends on rehydrating positions from MT5 on start and
guaranteeing broker-side SL/TP so risk is bounded even if our process dies.

## Phase A — Single-box hardening (prerequisites, do first)
1. Broker-side SL/TP on every position (already in place) — risk survives a crash.
2. Startup rehydrate + reconcile from broker (already in place: adopt positions).
3. Single-writer lease: a file lock / DB row (`account_lease`: owner, heartbeat,
   expiry). Only the lease holder may send orders. Prevents two instances (or a
   stray council/daemon) from trading one account.
4. Release directories + supervised restart (NSSM on Windows) + fast rollback.
5. Windows specifics: auto-logon persistent desktop session (MT5 needs a GUI
   session), MT5 auto-start, external liveness heartbeat, safe scheduled restart
   using drain->rehydrate (never a blind kill).

## Phase B — Deploy / hot-update (single-writer handoff, NOT blue/green)
Because one account = one trader, use "quiesce -> handoff -> verify":
1. Signal old (blue) into manage-only (no new entries), flush state, release lease.
2. Start new (green); it rehydrates positions from broker as truth, reconciles
   metadata (variant/edge) from local state.
3. Readiness gate: MT5 connected + account matches + positions reconciled + risk
   state loaded. Only THEN green acquires the lease and starts trading.
4. Auto-rollback: if green fails readiness, restart blue (previous release).
Handoff window is seconds; broker-side stops cover the gap. NOT simultaneous
blue/green (that would double-trade). "Saga" is the wrong term — what we need is
idempotent order-send + an intent/outbox log + broker reconciliation, not a saga
framework.

## Phase C — Central knowledge store (the real fleet value)
Goal: instances share learning instead of relearning.
1. SQLite -> managed Postgres (experience, knowledge, hypotheses). Concurrent
   multi-writer, network access from all VPS. Keep the latency-critical trading
   loop reading a LOCAL cache; flush learning asynchronously (never block trading).
2. ChromaDB -> pgvector (same Postgres) or Qdrant. Shared RAG memory.
3. Concurrent-write safety: every learning row carries instance_id/account/symbol/
   strategy_version; idempotency keys (INSERT ... ON CONFLICT); append-only events
   with derived aggregates (no shared mutable counters -> no double-count).
4. SHARD trading by symbol/account so no two instances trade the same symbol on the
   same account (prevents duplicate trades AND double-counted learning). Learning
   is shared (read by all); write attribution is partitioned.
5. Config/model distribution: instances PULL a versioned strategy bundle (weights,
   promoted strategies, edge maps) and switch atomically at a safe point. Pull
   scales better than push across a Windows fleet.

## Phase D — Fleet ops
- Git-pull + release dirs + NSSM restart (not containers — MT5 is a Windows GUI app).
- Per-VPS secrets in local secret store (never in git; .env stays untracked).
- Canary rollout: desired-version table keyed by instance_id; roll to one VPS,
  watch its edge/health, then widen. Expand/contract DB migrations for version skew.

## Explicitly NOT recommended
- Simultaneous blue/green both trading one account.
- Containerizing MT5 on Windows.
- A full saga/orchestration framework.
- SQLite on a network share (corruption).
- Trading hot-loop synchronously behind the central DB.

## Trigger to start building
Begin Phase A only once the edge scoreboard shows PF>=1.3 over 200+ real closed
trades (Phase 1 gate, issue #2). Until then this stays a design.
