# CryptoRTI Wave-Prediction — Design

Goal: use Danny's cryptoRTI whale-event triggers to PREDICT imminent BTCUSD moves
and "surf the wave", by learning the correlation between a captured whale event
and the large candles it produces on the BTCUSD chart shortly after.

This upgrades our current use of the feed from "a modest directional bias" to a
timed, event-driven predictive signal — because the whale event tells us a large
flow is ABOUT to hit the market, and the historical correlation tells us WHEN and
HOW BIG the resulting candles tend to be.

## The trader's key insight (the pattern to learn)

A whale moving crypto rarely dumps it in one trade. A $6M sale is commonly split
into ~$1M chunks to balance liquidity — which draws ~6 large candles on BTCUSD in
sequence within a specific window after the cryptoRTI event is captured.

So a single cryptoRTI trigger is the LEADING EDGE of a multi-candle move. If we
can recognise "this event type historically produced N large candles of direction
D within T minutes", we can position at the start of the wave rather than react
late (the current feed lags).

Also critical: DIRECTION. Danny's data infers whether flow is moving INTO crypto
(accumulation -> buy pressure) or OUT OF crypto / into an exchange (distribution
-> sell pressure). That inflow/outflow inference is the buy/sell signal; the whale
event timing is the WHEN.

## Data we have to learn this correlation

1. cryptoRTI signals (live WebSocket + S3 history):
   - staged lifecycle: deposit_detected -> sell_window_open -> selling_confirmed
   - whale_transfer: amount_usd, exchange, direction (exchange deposit = likely sell)
   - tape metrics: vpin, delta, cvd at each stage
   - S3 whale_events/ + signals/ give historical events with timestamps + outcomes
2. BTCUSD candle history from MT5 (get_rates, months available).
3. Danny's WEBHOOK trigger (pending spec) — a lower-latency confidence signal that
   an event is happening NOW; drops in as a higher-priority event source.

## How the correlation-learning works

### Phase A — Historical correlation mining (offline, backtest-style)
For each historical cryptoRTI event (from S3):
  1. Take the event timestamp T and inferred direction D and size S (usd).
  2. Pull BTCUSD candles from MT5 around [T, T + window] (e.g. 1m/5m for 60-120 min).
  3. Measure the response: number of "large" candles (range > k*ATR) in direction
     D, cumulative move (bps), time-to-first-large-candle, time-to-peak.
  4. Record a labelled sample: (event features: size bucket, exchange, direction,
     vpin/delta at capture) -> (response: n_large_candles, move_bps, lag_minutes,
     hit=did price move in D by a threshold).
Aggregate into a CORRELATION TABLE: for each event profile, the empirical
distribution of response (avg move, hit rate, typical lag, typical #candles).
This is stored and recalled — the "learned patterns".

### Phase B — Live prediction (event-driven)
When a live cryptoRTI signal (or webhook trigger) arrives:
  1. Classify it into an event profile (size bucket, exchange, direction, tape).
  2. Look up the learned correlation for that profile.
  3. If the profile historically produced a strong, reliable move (hit rate +
     avg move above thresholds), emit a PREDICTIVE signal:
       - direction = inferred flow direction (buy if inflow, sell if exchange-deposit)
       - confidence = f(historical hit rate, size, tape confirmation)
       - expected_window = typical lag..peak (so the trade manager knows the hold)
       - expected_magnitude = avg move (sets TP; SL from BTC ATR)
  4. Feed it as a high-priority strategy vote (CryptoRTI_Wave) — but still gated by
     risk + broker-side SL. Because we expect a multi-candle wave, the trade
     manager uses a wider TP / trailing profile for these (ride the chunks) rather
     than a tight scalp.

### Phase C — Continuous learning (close the loop on real fills)
Every wave trade's real outcome updates the correlation table (win/loss by event
profile), so the predictor sharpens over time — and profiles that stop working are
downweighted. This reuses the existing experience DB + reflection loop.

## Handling the "chunked sale" specifically
The correlation miner explicitly measures n_large_candles and their spacing. A
$6M event that splits into 6x$1M chunks shows up as ~6 large candles at a regular
cadence. We learn that cadence per size bucket, so the trade manager can:
  - hold through the expected number of chunks (not exit after candle 1),
  - trail the stop as each chunk completes,
  - exit when the expected chunk count / window is exhausted (wave over).

## Webhook trigger (pending Danny's spec)
When Danny provides the webhook handler spec, add `src/cryptorti/webhook_listener.py`
(a small HTTP endpoint or poller) that receives the notification and writes it to
the same live-signal state file with a `source="webhook"` + higher priority. The
predictor treats a webhook-confirmed event as higher confidence (lower latency,
explicit "happening now"). Everything downstream (classification, correlation
lookup, predictive signal) is identical — the webhook is just a faster, stronger
trigger than the polled WebSocket state.

## Components to build
- src/cryptorti/correlation_miner.py  — Phase A: mine S3 events x MT5 candles -> table
- src/cryptorti/wave_predictor.py     — Phase B: classify live event -> predictive signal
- CryptoRTI_Wave strategy             — emits the predictive vote (BTC), high priority
- trade-manager "wave" profile        — wider TP / ride-the-chunks management
- src/cryptorti/webhook_listener.py   — (when spec ready) low-latency trigger source
- correlation table persisted + recalled; outcomes feed back via experience DB

## Open questions for Danny
- Webhook payload schema + endpoint/auth (so we can build the listener).
- Does the feed explicitly label inflow vs outflow / into-vs-out-of-crypto, or do
  we infer it from exchange-deposit vs withdrawal? Confirm the direction field.
- Typical latency of webhook vs WebSocket (to quantify the edge).
- Any per-exchange nuance (a deposit to exchange A vs B implying different intent).


## EMPIRICAL FINDINGS (correlation miner run on 932 real events x BTCUSD, 30 days)

Phase A is BUILT and RAN. Confirmed the trader insight in real data:

- Chunked-sale pattern is REAL: avg large-candles per event is consistently 4-7
  (10M+ -> 5.9 candles, <1M|bitget -> 6.9). Bigger events draw more candles --
  exactly the "6M split into ~1M chunks" behaviour described.
- Timing edge: the wave first large candle lands ~27-47 min after the event
  (avg_lag_min). Act on the trigger ahead of the visible move (solves feed lag).
- Some profiles have real edge: <1M|bitget|sell = 62.5% hit / +26bps / 6.9
  candles; <1M|upbit|sell = 75% / +70bps. Others (~35% hit) are noise.
- CRITICAL nuance -- SPIKE then REVERT: avg_move_bps (window end) is often ~0
  while avg_peak_bps is 20-47. The move spikes then mean-reverts within the
  window. So a wave trade must target the PEAK and exit near lag+peak time, NOT
  hold to window end. The trade-manager "wave" profile is ride-then-exit-at-peak.
- Direction currently all "sell" (we infer exchange-deposit = distribution).
  Buy-side waves need Danny explicit inflow/outflow field.

Predictor rule of thumb: only act on profiles with samples>=15 AND hit_rate>=55
AND avg_peak_bps above threshold; confidence from hit_rate; TP near avg_peak_bps;
time-based exit around avg_lag_min + a few candles.

## Performance note
S3 signal loading parallelised (16 threads) -- 932 files now load in ~seconds.


## DIRECTION RESOLVED (from raw whale_events, no Danny input needed)

data/whale_events/btc/*.parquet has an `event_type` column with BOTH values:
  deposit    -> coins TO an exchange   -> distribution -> SELL signal
  withdrawal -> coins OFF to a wallet  -> accumulation -> BUY signal

The signals feed (data/signals/) only publishes deposits (sell side). The miner
now sources from whale_events instead, giving BOTH directions:
16 buy + 21 sell profiles from 2,997 events (20 days).

Buy-side edge is modest & symmetric to sell (40-53% hit, peak ~24-30bps then
revert). Larger events (5-10M/10M+) show slightly stronger edge. Confirmed the
spike-then-revert behaviour applies both directions -> scalp-the-spike, exit near
avg_lag + peak, never hold to window end.

Still worth confirming with Danny (see cryptorti/martin_qna.md): exact direction
semantics/edge cases, the low-latency webhook, and the tape trigger that
separates real sells from windows that expire with no move.
