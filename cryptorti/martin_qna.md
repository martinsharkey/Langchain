# CryptoRTI <-> Martin: Async Q&A

Purpose: an async conversation doc between Martin's trading-bot side (assisted by
Claude/Kilo) and Danny's cryptoRTI side (assisted by Claude). Danny: please
answer inline under each question, or edit/extend this file and re-upload to the
same S3 key. We poll this file. Keep the format: each item has STATUS, our
QUESTION, our CONTEXT, and a DANNY ANSWER block.

Location (agreed): s3://crypto-rti-prod-us-east-1/collab/martin_qna.md
(If you prefer a different key, tell us and we'll point at it.)

Format convention:
- STATUS: OPEN | ANSWERED | RESOLVED
- Put answers in the "DANNY:" block. Add new questions at the bottom under NEW.
- If richer than prose is useful, a small JSON/YAML block inside the answer is fine.

---

## What we've already figured out from your data (so you don't re-explain)

We mined `data/whale_events/btc/*.parquet` (2,997 events, 20 days) against BTCUSD
candles from MT5. Findings:
- `event_type` has BOTH `deposit` and `withdrawal`. We infer:
  deposit -> exchange = distribution -> SELL; withdrawal -> wallet = accumulation
  -> BUY. This gave us 16 buy + 21 sell correlation profiles. So we can derive
  direction ourselves without you changing anything. Please confirm this
  interpretation is correct (Q1).
- The `data/signals/btc/*.json` feed only publishes `whale_exchange_deposit`
  (sell side). Withdrawals are only in the raw whale_events, not the signals feed.
- Chunked-sale pattern confirmed: events draw ~4-6 large BTCUSD candles; the first
  large candle lands ~28-43 min after the event; moves spike ~25-35 bps then
  mean-revert within the window (so we treat it as scalp-the-spike, not hold).

---

## Questions

### Q1 — Direction semantics  [STATUS: OPEN]
QUESTION: Is our mapping correct — `event_type=deposit` (to exchange) = sell
pressure, `event_type=withdrawal` (off exchange) = buy/accumulation? Are there
edge cases (e.g. exchange-to-exchange internal transfers, cold-wallet
reshuffles) that would make an event directionally meaningless / noise we should
filter out?
CONTEXT: Direction is the core of our buy/sell signal. We currently treat every
qualifying event as directional.
DANNY:
> (answer here)

### Q2 — The webhook / notification handler  [STATUS: OPEN]
QUESTION: You mentioned a webhook that fires when a wallet moves. Please share:
(a) the payload schema (fields + example JSON), (b) endpoint/URL + auth method,
(c) which events trigger it (all whale_events? only deposits? size threshold?),
(d) typical latency vs the WebSocket signal feed.
CONTEXT: Your feed lags the actual move; a low-latency webhook is the edge that
lets us position at the START of the wave. We'll build a listener that ingests it
as a high-confidence, high-priority trigger.
DANNY:
> (answer here)

### Q3 — Predicting WHEN the sale actually executes  [STATUS: OPEN]
QUESTION: After a deposit is credited (sell_window_open), what — in your data —
best predicts that selling is actually about to hit vs the window expiring with
no move? You expose vpin / delta / cvd on the tape. Which of these, at what
thresholds, historically precede real selling? Any leading indicator we can
subscribe to that fires the moment tape confirms?
CONTEXT: Most deposit windows in our sample "expired, no significant selling".
Knowing the tape trigger that separates real sells from non-events is the
difference between a good signal and noise.
DANNY:
> (answer here)

### Q4 — Chunking cadence  [STATUS: OPEN]
QUESTION: When a large holder splits (e.g. $6M into ~$1M chunks), do you see /
can you expose the intended total and the chunk cadence? i.e. can a single event
carry "this is 1 of N expected tranches"? We currently infer chunk count from the
resulting candles after the fact.
CONTEXT: If we know N and cadence up front, we can hold through the wave and exit
at the right chunk rather than inferring it live.
DANNY:
> (answer here)

### Q5 — Tape metrics in the raw feed  [STATUS: OPEN]
QUESTION: Are vpin / delta_5m / cvd_trend available as a stream we can pull in
real time (not just embedded in resolved signal JSON)? If so, how do we subscribe?
CONTEXT: We want tape confirmation live to time entries within the sell window.
DANNY:
> (answer here)

### Q6 — Exchange-specific intent  [STATUS: OPEN]
QUESTION: Do deposits to certain exchanges (e.g. an OTC-heavy venue) behave
differently from retail spot venues? Our data hints some exchanges (bitget,
upbit) produce bigger BTCUSD moves than binance for the same size. Is that a
known effect / is there per-exchange metadata we should weight by?
DANNY:
> (answer here)

---

## NEW (add below this line)
