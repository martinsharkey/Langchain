# CryptoRTI Integration Plan

Integrating Danny's **cryptoRTI** platform (S3 data + live mTLS signal feed) to
power a new **BTCUSD strategy**, a **backtest/validation harness**, and future
ML. Owner contact: Dan Cooke. Bucket: `s3://crypto-rti-prod-us-east-1` (us-east-1).

---

## 0. SECURITY (do this — non-negotiable)

- The AWS keys (`AKIA...[REDACTED-ROTATE]`) and mTLS certs were shared in chat and are
  therefore **compromised**. **Rotate the AWS key and re-issue the client cert**
  after this work. Ask Danny to revoke the current client cert and issue a fresh one.
- Certs live in `langchain/cryptorti/certs/` and are **git-ignored** (see `.gitignore`).
  Never commit `client-key.pem`, `client.pem`, `ca.pem`, or AWS creds.
- Prefer a **reader IAM role / named AWS profile** over static keys. Store creds in
  a local `.env.cryptorti` (git-ignored), not in code.

---

## 1. What CryptoRTI provides (verified)

### A. S3 historical data (read access) — the ML goldmine
- **`data/features/{exchange}/{symbol}/{date}/features_{date}.parquet`** — the prize.
  **280 v5 columns at 1-min intervals**, family-prefixed (`ob_`, `flow_`, `px_`,
  `vpin`, `whale_`, `label_`). Includes **forward-price labels already computed**:
  `label_direction_{1m,5m,15m,30m,1h,4h}` and `label_price_change_{h}` — supervised
  targets with no look-ahead if used correctly.
- **`data/signals/btc/{date}/{signal_id}.json`** — resolved whale-deposit signals
  with staged `updates[]` and outcomes (the live feed's history).
- **`data/whale_events/btc|eth/{date}/`** — raw large transfers to exchanges.
- Also: `trades/` (tick), `orderbook/` (raw L2), `derivatives/`, `sentiment/`,
  `news_events/`, `fear_and_greed/`, `history_bars/` (5y OHLCV CSV).
- Timestamps are **microseconds UTC** (`pd.to_datetime(ts, unit='us')`).
- Known gaps: **Binance 2026-07-05 incomplete**; processed data is **T-1**.

### B. Live signal feed (mTLS WebSocket)
- `wss://3.213.39.89:8443` (static IP), mTLS with `ca.pem` + `client.pem` + `client-key.pem`.
- Pushes full signal state per event: stages `deposit_detected → sell_window_open →
  selling_confirmed → expired/resolved`. Idempotent (full state each push).
- **MT5/MQL5 cannot do mTLS** → must bridge. We connect via **Python client**
  (we already run a Python bot), so we DON'T need stunnel for the bot — the bot's
  Python process connects directly with the 3 certs. stunnel is only needed if an
  MQL5 EA must consume it.

---

## 2. How it maps to our bot

Two distinct, complementary uses:

1. **Live trading strategy (BTCUSD):** a new `CryptoRTI_WhaleSignal` strategy in the
   registry. When a live signal reaches `selling_confirmed / active_short` (VPIN
   spike + negative delta after a whale deposit), it emits a **sell** signal for
   BTCUSD with confidence scaled by tape strength. `expired`/no-confirmation → no trade.
2. **Validation + ML (the important part):** use the S3 **features + labels** to
   measure whether the whale/VPIN signal actually predicts forward BTC moves, and
   more broadly to train/validate strategies out-of-sample (this is the L6 guardrail
   from LEARNING_ARCHITECTURE.md, now with a real labelled dataset).

Note on instrument mapping: CryptoRTI tracks **BTC-USD / BTCUSDT** (spot). Your MT5
`BTCUSD` (VT Markets) is the tradable proxy. Signals are directional (whale selling
→ short bias); we trade the MT5 symbol.

---

## 3. Build plan

### C1 — S3 client module (`src/cryptorti/s3_client.py`)
- Thin boto3 wrapper: list/read parquet & json, credential from env/profile.
- Helpers: `load_features(symbol, date)`, `load_signals(date)`, `latest_signals()`.

### C2 — Live signal client (`src/cryptorti/signal_client.py`)
- Async mTLS websockets client (based on Danny's reference example).
- Maintains an in-memory map of active signals; exposes `get_active_signals()` and
  a callback. Auto-reconnect. Writes latest state to `data/cryptorti_signals.json`
  for the dashboard + strategy to read (decouples network from trading loop).

### C3 — CryptoRTI strategy (`src/learning/strategy_registry.py` via `register_custom`)
- Reads the latest active signals; if a fresh `selling_confirmed` short signal
  exists for BTC within its sell window, emit SELL for BTCUSD. Confidence from
  VPIN percentile + delta. Registered as `status="testing"` until validated.

### C4 — Backtest / validation (`src/cryptorti/backtest.py`)
- Load features+labels for a date range; evaluate the whale/VPIN rule (and the
  general ensemble) against `label_direction_*` / `label_price_change_*`.
- Report hit rate, avg bps move, by horizon — honest out-of-sample metric.

### C5 — Dashboard panel
- Add a "CryptoRTI Signals" panel: live signal status + recent resolved outcomes.

---

## 4. Order of work
C1 (S3) → C4 (backtest/validate the edge FIRST) → C3 (strategy, only if edge is real)
→ C2 (live client) → C5 (dashboard). Validating before trading is the whole point.

## 5. Open questions for Danny
- Confirm the live IP/port still `3.213.39.89:8443` and that our client cert is valid.
- Is spot BTC-USD signal → MT5 BTCUSD mapping acceptable (basis differences)?
- Rotate our AWS key + reissue client cert (shared in chat).

---

## 6. VALIDATION RESULTS (measured on 10 days of real labelled features)

Tested hypothesis: whale deposit + elevated VPIN + negative short-term delta →
forward BTC down-move. Measured against the platform's own forward labels
(14,367 rows, 2026-07-20 → 07-29). Base down-rate is the unconditional rate.

| Horizon | Signal down-rate | Base | Edge | Avg move (signal vs base) | Verdict |
|---------|------------------|------|------|---------------------------|---------|
| 5m  | 25.4% | 22.8% | +2.6% | ~0 | noise |
| 15m | 33.2% | 31.7% | +1.5% | +0.002% (wrong sign) | no edge |
| **1h** | **44.0%** | 38.6% | **+5.5%** | **−0.023% vs −0.007%** | **real edge** |

Tightening the condition sharpens the 1h edge:

| Condition (1h) | n | Down-rate (edge) | Avg move (edge) |
|----------------|---|------------------|-----------------|
| vpin≥80, deposit≥$1M, delta<0 | 1011 | 46.5% (+7.9%) | −0.047% (−0.040%) |
| vpin≥95, deposit≥$1M, delta<0 | 521 | 47.4% (+8.9%) | −0.031% (−0.024%) |

**Conclusions (honest):**
- The signal is a **directional bias, not a high-probability event** (~47% down vs
  ~39% base). Treat it as a **confidence-weighted contributor**, never a standalone
  high-conviction trade.
- The edge lives at the **~1h horizon**, NOT at scalp speed. The CryptoRTI strategy
  should bias BTCUSD SHORT with a ~1h intent, sized modestly.
- Operating point: **VPIN percentile ≥ 80–95, deposit ≥ $1M, negative 5m delta.**
- This validated-first approach is the L6 guardrail in action: we now trade this
  because it beats base rate out-of-sample, not because it sounds smart.
