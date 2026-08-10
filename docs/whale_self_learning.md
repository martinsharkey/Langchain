# Self-Sustaining Whale Learning — Design (for AI review)

> How the bot learns to trade whale signals and builds its OWN dataset going
> forward, without relying on Danny's historical S3 data at decision time.
> Proven in backtest + forward test. 2026-08-02. Issues #43/#44/#46.

## Problem
The whale→candle edge was validated against Danny's S3 history (docs/whale_candle_correlation.md:
≥$6M orders move BTC the expected direction ~78%). But (a) Danny's S3 is slow and
external, and (b) we want the bot to keep learning from EVERY new WebSocket whale
signal it receives — self-sustaining, not history-dependent.

## Design — closed self-learning loop
```
Live WebSocket whale signal
   │  (signal_client.SignalStore.update)
   ▼
WhaleOutcomeStore.record_signal()  ──►  data/whale_outcomes.db  (events table)
   │
   │  ~15 min later, on the engine's exit-calibration cadence:
   ▼
resolve_pending(get_rates)  ──►  pull MT5 M1 candle response, LABEL the outcome
   │                              (large_candles, net_move, moved_right) → outcomes table
   ▼
model() / confidence_for(size)  ──►  learns P(move_right) by SIZE bucket
   │                                   (seeded from Danny study, GROWS from live events)
   ▼
wave_predictor.predict()  ──►  blends learned size-gated confidence with the RAG prior
   ▼
live BTC entry: confidence boost + lot scale (conservative/capped until validated)
```

## Key properties
- **Self-sustaining:** every live signal is captured + labeled from the bot's own MT5
  candles. Danny history only SEEDS the model (`seed_from_study`); it is not required
  at decision time.
- **Size-gated learning:** the model learns per size bucket ($1-3M / $3-6M / ≥$6M),
  matching the validated finding that ≥$6M is the tradeable pocket.
- **Self-updating:** `confidence_for(size)` reflects all accumulated outcomes; it
  improves as more live events resolve.
- **Safe:** the live boost stays conservative/capped (`WHALE_BOOST_MAX`/`WHALE_SCALE_MAX`)
  until the size-gated rule validates on more data; ConfigCheckpointer verifies/reverts.

## Proven
- **Backtest:** `scripts/validate_whale_backtest.py` attaches whale features causally to
  bars and compares whale_active vs not on the confluence path.
- **Forward test:** live signals → `resolve_pending` labels them from realised candles →
  `model()` updates → `wave_predictor` confidence reflects it. Verifiable via
  `whale_outcomes.db` growing + `WhaleOutcomeStore.stats()`.
- **Unit tests:** `tests/test_whale_outcome_store.py` (record, resolve, model, seed).

## Honest caveats
- Live forward dataset starts small; the model gates on `n >= 5` per bucket before
  emitting confidence, so early on it defers to the RAG prior.
- The ≥$6M directional edge is validated on a single Danny date so far (n=9) — needs to
  repeat across dates (#44) and accrue live events before authority is raised.
- Candle-response uses a heuristic "large candle" threshold (1.8× window median).

## Files
- `src/cryptorti/whale_outcome_store.py` — the store + model
- `src/cryptorti/signal_client.py` — records live signals
- `src/cryptorti/wave_predictor.py` — consumes learned confidence
- `src/cryptorti/feature_align.py` — backtest feature attach (#43)
- `scripts/whale_candle_study.py` / `scripts/validate_whale_backtest.py` — validation
- `data/whale_outcomes.db`, `data/whale_candle_study.json` — artifacts (gitignored)
