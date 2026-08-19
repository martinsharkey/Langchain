# Multi-Symbol Architecture Design (Issue #85)

## Current state

All symbols (XAUUSD, BTCUSD, GER40, etc.) share:
- one Python process (`app.py`);
- one MT5 terminal connection via `src.mt5.connector`;
- one `mt5_lock()` serializing data and order calls.

This creates three scaling problems:
1. **Head-of-line blocking**: a heavy `get_rates`/`get_ticks` call or backtest cache warm delays live order/modify calls for other symbols.
2. **Single point of failure**: a crashed terminal or corrupted connection stops every symbol.
3. **No side-by-side versions**: running different config versions or A/B tests for one symbol is hard.

## Decision criteria

| Criterion | Weight | Rationale |
|-----------|--------|-----------|
| Cost | high | Extra terminals/containers, memory, ops effort |
| Ops effort | high | Keeping N terminals logged in, alive, updated |
| Data fidelity | high | Must use broker-exact ticks for live fills |
| Fault isolation | high | One symbol must not kill the others |
| Scale to 5/10/20 symbols | high | Future capacity |

## Approach A: one MT5 terminal per symbol on the same host

One Python worker per symbol; each worker calls `mt5.initialize(path=...)` against its own terminal/profile.
Shared state lives in `data/qmmp/<SYM>/` (model.json, trade logs, checkpoints).

Pros:
- Uses broker-exact data per symbol.
- No shared MT5 connection; one terminal crash affects only that symbol.
- Simple to reason about; minimal new infrastructure.
- Matches the existing per-symbol model.json + generated EA pattern.

Cons:
- N terminals to keep logged in and alive.
- Higher memory (each terminal ~150-400 MB).
- Operational complexity grows with symbol count.

## Approach B: container per symbol with a central spine

One container per symbol runs Python harness + MT5 terminal + EA.
A central spine (small service or shared store) aggregates model.json, trade logs, and checkpoints.

Pros:
- True fault isolation.
- Easier horizontal scaling; can move symbols between hosts.
- Can run different versions per symbol cleanly.

Cons:
- Needs shared storage (S3 / NFS / DB) and a coordination layer.
- More infrastructure: container runtime, image builds, networking.
- Data egress/latency to shared store must be managed.

## Comparison

| | Approach A | Approach B |
|---|---|---|
| Cost | medium (N terminals on one host) | higher (N containers + shared store) |
| Ops effort | medium | higher |
| Data fidelity | broker-exact | broker-exact (each container has its own terminal) |
| Fault isolation | per symbol | per symbol + host-level separation |
| Scale to 5 symbols | fine | overkill |
| Scale to 10-20 symbols | needs bigger host or multi-host split | natural fit |
| A/B testing | possible via extra profiles | natural via different container images |

## Minimum viable first step

**Adopt Approach A for 2-3 symbols now.**

This means:
- Keep the current single-process architecture as the default.
- Document how to run a second terminal/profile for a new symbol when needed:
  - separate MT5 installation or profile directory;
  - set `MT5_PATH` env var per worker;
  - each worker gets its own `mt5_lock()` and connector instance.
- Ensure per-symbol state (`data/qmmp/<SYM>/`, tuned params, experience DB rows) is already isolated.
- Add a lightweight health/heartbeat per terminal so a dead terminal only disables one symbol.

## Trigger for moving to Approach B

Move to containers when any of these happen:
- More than ~5 symbols live, or memory/CPU on the host is saturated.
- Need to run different EA/config versions side by side for A/B validation.
- Need host-level fault isolation (e.g. live money at scale).
- Approach A operational burden becomes unacceptable.

## Recommendations / action items

1. **Do not refactor the current single-symbol path yet.** It is correct for the current 1-3 symbol focus.
2. **Add an env/config switch** that lets the engine attach to a specific MT5 terminal path per symbol worker (already partially possible via `mt5.initialize(path=...)`).
3. **Document the per-symbol worker launch pattern** in DEPLOY.md.
4. **Add per-terminal health checks** so a dead terminal disables only that symbol.
5. **Keep the generated EA and model.json per-symbol** so migration to Approach B later is just moving files to containers.

## Acceptance status

- [x] Current single-process limitations documented.
- [x] Approach A vs B comparison written (cost, ops, fidelity, fault isolation, scale).
- [x] Minimum viable first step identified (Approach A for 2-3 symbols).
- [x] Trigger for Approach B identified.
- This issue is design-only; implementation sub-issues should be created if the trigger is reached.
