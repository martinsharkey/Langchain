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

## DECISION LOG (agreed)

- **2026-07-31 � Authoritative source = mTLS WebSocket, event-driven push only.**
  Danny's preference: the WebSocket feed. He does NOT want us polling S3 or
  dashboard.json (cost + load on his side). He will PUSH a signal only when an
  event actually happens AND it carries enough data to act on. So our bot must:
  - Treat the WebSocket signal as the single real-time source of truth.
  - NOT poll S3 / dashboard.json in the hot path (this resolves Q11; the
    dashboard REST path in CryptoRTI_Context.mqh is de-scoped for live trading).
  - Depend on Danny embedding the confidence/tape payload IN the push (see Q7),
    since a push only arrives when there is "enough data" � i.e. the push itself
    is the confirmation signal.
  - Keep S3 (`martin_qna.md`) for async collaboration only, not per-trade reads.

---I i would like
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

### Q7 � Embed a CONFIDENCE payload in the live signal (avoid us polling S3) [STATUS: OPEN, HIGH PRIORITY]
QUESTION: We do NOT want to read your S3 orderbook/L2 per trade (slow + costly).
Your live WebSocket signal already carries whale_transfer + staged lifecycle, but
it has NO tape/orderbook metrics we can act on. Please EMBED a confidence block in
each signal push (especially at the `selling_confirmed` stage), e.g.:
  "tape": { "vpin": 0.0-1.0, "vpin_percentile": 0-100, "delta_5m": <signed>,
            "cvd_trend": "rising|flat|falling", "ob_imbalance": -1..+1,
            "ask_depth_usd": .., "bid_depth_usd": .. }
  "confidence": 0.0-1.0,  "recommended_side": "sell|buy|none"
CONTEXT: With that, our bot can compute a trade-confidence rating from the signal
alone and never touch S3 in the hot path. What can you include, and at which stages?
DANNY:
> (answer here)

### Q8 � Is the signal->move WINDOW a repeatable pattern or random? [STATUS: OPEN, HIGH PRIORITY]
QUESTION: We see detected_at -> expected_credit_time (~20 min) -> sell_window_open
-> (selling_confirmed | expired ~1h). Is `expected_credit_time` a reliable, roughly
constant lag (exchange confirmations), and once `selling_confirmed` fires, is the
price reaction window tight and repeatable (e.g. move within N minutes), or does it
vary widely by exchange/size? We need to know the tradeable window precisely to set
BTC entries/exits and a wide-enough stop. Any distribution stats you have on
"time from selling_confirmed -> peak price impact" would be gold.
DANNY:
> (answer here)

### Q9 � Which stage should we trade, and hit-rate of selling_confirmed [STATUS: OPEN]
QUESTION: Many signals EXPIRE with "no significant selling". We plan to only act
on `selling_confirmed` (not `sell_window_open`). Of deposits that reach
sell_window_open, what fraction reach selling_confirmed, and of those, what
fraction actually move BTC in the expected direction? This tells us the base hit-rate.
DANNY:
> (answer here)

### Q10 � CRITICAL: 454/455 signals "expired, no selling". Is the feed right? [STATUS: OPEN, URGENT]
FINDING (our data): We mined the last 8 days of data/signals/btc. Of 455 whale
deposits >= $1M, **ZERO reached `selling_confirmed`** � 454 expired with
"Sell window expired. No significant selling detected." The BTCUSD down-move in
the window was tiny (median ~22 bps).
QUESTIONS:
- Is `selling_confirmed` actually wired/firing in the live feed, or is it rarely
  reached by design? If deposits almost never lead to confirmed selling, the raw
  deposit signal is NOT tradeable on its own � we need the tape confirmation.
- What % of deposits SHOULD reach selling_confirmed in normal conditions?
- Is there a bug where the sell window expires before your tape confirmation runs?
DANNY:
> (answer here)

### Q11 � TWO CryptoRTI data paths: which is authoritative? [STATUS: ANSWERED]
FINDING: Martin's MT5 OrderFlow engine (CryptoRTI_Context.mqh) polls
`https://cryptorti.io/api/dashboard.json` via REST and uses: overall_sentiment
(sentiment/score 0-100/confidence 0-10/risk_level/dominant_driver),
fear_and_greed, whale_movements[] (sums BTC amount_usd), stablecoin_events[].
BUT our Python bot uses the mTLS WebSocket signal feed (wss://3.213.39.89:8443)
with a DIFFERENT shape (staged whale_exchange_deposit lifecycle, no VPIN/tape).
QUESTIONS:
- Which is the authoritative real-time source going forward � the dashboard.json
  REST, or the mTLS WebSocket signals? We want ONE path for the bot.
- Does dashboard.json contain the per-event tape/VPIN/orderflow confidence, or
  only aggregate sentiment/whale sums? (We need per-signal confidence, see Q7.)
- Can the WebSocket signal carry the same whale_net_usd / sentiment / confidence
  the dashboard has, so we don't need both?
DANNY:
> Use the mTLS WebSocket feed. I'd rather push you an event only when it happens
> and it has enough data to be worth acting on, so I'm not paying to serve S3 /
> dashboard.json polls. So: WebSocket is authoritative, event-driven push only,
> and I'll work on embedding the confidence/tape payload in the push (Q7) so the
> push itself is the actionable signal. Don't poll dashboard.json for live trading.

### Q12 � Confirm the tape metrics we should rely on [STATUS: OPEN]
CONTEXT: Martin's OrderFlow engine computes CVD, per-bar delta, VPOC, tape speed
from MT5 tick flags (TICK_FLAG_BUY/SELL) � NOT true exchange volume, and NO VPIN
(despite header mentions). Real VPIN/CVD from actual Binance/Coinbase flow lives
in YOUR data.
QUESTION: Can you expose, per signal, a real-exchange CVD/VPIN/delta and bid-ask
imbalance (from your L2/trades) so our tape confirmation uses genuine exchange
order flow rather than an MT5 CFD proxy? Which of these can you commit to?
DANNY:
> (answer here)
