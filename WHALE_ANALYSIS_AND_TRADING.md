# CryptoRTI Whale Signal — Analysis, WebSocket Build & BTCUSD Trading

> How the CryptoRTI whale integration is built, what the whale data actually says
> (honestly), and exactly how BTCUSD trades when a live whale signal is present.
> Source of truth for the whale side; complements `DATA_SOURCES.md` and
> `cryptorti/martin_qna.md`.

---

## 1. The whale analysis — what the data actually says

We mined Danny's S3 history into per-bucket behaviour profiles
(`data/cryptorti_correlation.json`): **2,997 whale events → 37 profiles** keyed by
`size | exchange | direction`. Each profile carries: `samples`, `hit_rate`,
`avg_move_bps`, `avg_peak_bps`, `avg_n_large` (chunk count), `avg_lag_min`.

### The honest finding: the whale edge is THIN

Ranking the sell profiles by hit-rate (n ≥ 10):

| bucket | n | hit% | peak bps | lag min |
|---|---|---|---|---|
| `<1M \| bitget \| sell` | 36 | **58** | 42 | 33 |
| `<1M \| crypto_com \| sell` | 66 | 53 | 30 | 40 |
| `1-2M \| crypto_com \| sell` | 51 | 49 | 32 | 28 |
| `10M+ \| binance \| sell` | 109 | 49 | 35 | 28 |
| `5-10M \| binance \| sell` | 449 | 41 | 24 | 39 |
| `2-5M \| binance \| sell` | 299 | 38 | 22 | 41 |
| `1-2M \| binance \| sell` | 118 | 35 | 27 | 40 |

**Only 1 of 12 sell buckets clears a 55% tradeable bar** (`<1M|bitget`). The *big*
whales — the ones intuition says should move price — are the **worst** (binance
2-10M ≈ 38-41%, a coin-flip or below). Peak moves are small (20-42 bps = 0.2-0.4%)
with a 28-48 min lag.

### Why most signals "expire, no selling"

Danny's own feed shows (and our live capture confirms) that most deposits never
lead to selling. Live monitor sample (30 min, `whale_monitor.py`): signals seen were
`deposit_detected` / `sell_window_open` / `expired` — **zero `selling_confirmed`**.
This is not a feed bug (Q10): **it is the market reality that a whale depositing to
an exchange usually does NOT produce a tradeable BTC move.** The base rate is low.

**Conclusion:** the whale signal is a **weak, occasional edge**, not a profit driver.
That directly justifies the design: it is a small BTCUSD **confidence nudge**, never
a standalone entry.

### What we self-solved vs. what stays open

- **Self-solved from our own data (no Danny needed):** direction semantics
  (deposit→sell / withdrawal→buy), chunk pattern (~4-6 large candles), lag
  (~28-48 min), per-bucket hit-rates.
- **Still open (Danny-side, `martin_qna.md` Q3/Q7/Q9/Q10):** a live *tape* trigger
  (VPIN/CVD/delta) that separates a real sell from an expiring window, and the
  `selling_confirmed` stage embedded in the push. These would sharpen the signal but
  are **not blocking** — and the data shows the ceiling is modest regardless.

---

## 2. How the WebSocket is built

**Transport — `src/cryptorti/signal_client.py`:**
- Native Python `websockets` over **mTLS** to `wss://3.213.39.89:8443` (Q11-decided
  authoritative source; no polling, no stunnel).
- Certs: `cryptorti/certs/{ca,client,client-key}.pem` (gitignored). Env overrides:
  `CRYPTORTI_HOST/PORT/CA/CERT/KEY`.
- Auto-reconnect loop (`async for ws in websockets.connect(..., ping_interval=30)`),
  responds to `pong`, parses each JSON signal.

**On each signal (`store.update`)** — two decoupled sinks (no direct push into the
trading loop, so the engine never blocks on the feed):
1. Persists active signals to `data/cryptorti_signals.json` (the file the engine reads).
2. Records the event to `WhaleOutcomeStore` (`data/whale_outcomes.db`) for
   self-learning. The live payload nests the amount under
   `whale_transfer.amount_usd` (parsed correctly; direction derived from the
   deposit/withdrawal semantics).

**Started by `app.py`** (`start_cryptorti_best_effort`): a **guarded, best-effort
daemon thread** — if the certs are missing it prints a disabled notice and the bot
runs normally. **The bot degrades gracefully: if the feed is down, BTCUSD still
trades on OsMA alone.**

**Log strings to verify it live:**
```
CryptoRTI connecting to wss://3.213.39.89:8443
CryptoRTI connected
CryptoRTI signal sig_<id>: stage=<stage> status=<status>
```

---

## 3. How BTCUSD trades when using the WebSocket

**Golden rule: the whale signal NEVER opens a trade. Entry is always OsMA_Confluence.**
The whale layer only nudges confidence on a BTC trade the OsMA engine already wants.

### The flow (`scalp_engine._evaluate_and_trade`, BTC only)

1. **OsMA_Confluence must fire first.** If the confluence says hold, there is no
   trade — the whale layer is never even reached.
2. When OsMA produces a `buy`/`sell`, the **HYBRID layer** runs:
   - `wp = _whale_predict_for_btc()` — blends the live signal's `current_short_bias`
     (from `cryptorti_signals.json`) with the mined historical profile + the bot's own
     learned `WhaleOutcomeStore` model.
   - **If the whale AGREES with the OsMA direction** and `wp.confidence >= 0.5`:
     - confidence boost: `+ WHALE_BOOST_MAX (0.06) × wp.confidence` (tiny, capped)
     - lot scale flag: `_whale_scale = 1 + min(WHALE_SCALE_MAX 0.5, 0.5 × conf)` —
       applied only to **graduated / LIVE** symbols, never a TRAINING symbol.
   - **If the whale OPPOSES the OsMA direction:** dampen confidence by `WHALE_BOOST_MAX`.
     It never reverses the direction.
3. The (possibly nudged) confidence then passes the normal gates (conf threshold, risk,
   sizing). The trade is still an **OsMA trade**, attributed to `OsMA_Confluence`.

### The live-bias gate (`current_short_bias`)

The live signal is only treated as tradeable when
`status ∈ (active_short, selling_confirmed)` OR `stage == selling_confirmed`, **and**
`amount_usd >= $1M`. Confidence = `0.45 + VPIN_percentile/100 × 0.2` (0.45-0.65).

> **Practical note:** because the live feed currently never emits `selling_confirmed`
> (see §1), this gate rarely fires, so in practice the whale boost is currently
> dormant on live — BTCUSD trades on OsMA alone. This is safe and expected; the boost
> activates only when a genuine confirmed-sell whale aligns with an OsMA entry.

### Self-learning loop

Every live whale event is stored and later labelled against the realised BTC candle
(`WhaleOutcomeStore.resolve_pending`), so the size-gated confidence model keeps
learning from real outcomes — Danny-seeded, growing from live events, no reliance on
Danny history at decision time.

---

## 4. Config knobs

| Key | Default | Meaning |
|---|---|---|
| `WHALE_BOOST_MAX` | 0.06 | max confidence boost when whale agrees |
| `WHALE_SCALE_MAX` | 0.5 | max extra lot fraction (graduated symbols only) |
| `CRYPTORTI_HOST/PORT` | 3.213.39.89:8443 | WebSocket endpoint |
| `CRYPTORTI_CA/CERT/KEY` | cryptorti/certs/*.pem | mTLS certs |

## 5. Bottom line

The whale integration is fully wired, the WebSocket flows live, and BTCUSD uses it
**correctly and conservatively** — a small, agreement-required confidence nudge, never
a standalone signal. The data says the whale edge is thin (1/12 buckets tradeable),
which is exactly why it is built as an assist, not a driver. The remaining sharpening
(live tape trigger / `selling_confirmed`) is Danny-side and non-blocking.
