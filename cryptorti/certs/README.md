# CryptoRTI Signal Engine — Client Setup

## What This Is

Real-time BTC whale deposit alerts pushed to you via WebSocket.
When a whale deposits 10+ BTC to an exchange, you get a signal within seconds of the block confirming.

## Signal Lifecycle

Each signal goes through stages, and you receive the full state at each transition:

1. **deposit_detected** — Whale deposit found in a confirmed block. Pushed immediately.
2. **sell_window_open** — Exchange has credited the deposit (~20 min after block). Selling can now begin.
3. **expired** — 1 hour after sell window opened with no tape confirmation. Signal closed.

Every push is the full signal state (idempotent). If you reconnect, you get all active signals immediately.

## Files In This Folder

- `ca.pem` — Certificate Authority cert (verifies the server is genuine)
- `client.pem` — Your client certificate (proves your identity to the server)
- `client-key.pem` — Your private key (keep this secure, do not share)
- `signal-client-example.py` — Reference Python client

## Quick Start

### Requirements

```
pip install websockets
```

### Connect

```
python signal-client-example.py \
    --host <SIGNAL_ENGINE_IP> \
    --port 8443 \
    --ca ca.pem \
    --cert client.pem \
    --key client-key.pem
```

Danny will give you the IP address.

### What You'll See

```
[deposit_detected] sig_20260716_120530_a1b2c3d4: 28.50 BTC ($1,909,500) -> binance
  2026-07-16T12:05:30Z | Whale deposit detected: 28.50 BTC ($1,909,500) to binance

[sell_window_open] sig_20260716_120530_a1b2c3d4: 28.50 BTC ($1,909,500) -> binance
  2026-07-16T12:05:30Z | Whale deposit detected: 28.50 BTC ($1,909,500) to binance
  2026-07-16T12:25:30Z | Sell window open. Exchange has credited the deposit. Watch for selling on tape.
```

## Signal JSON Format

Each push is a JSON object:

```json
{
  "signal_id": "sig_20260716_120530_a1b2c3d4",
  "signal_type": "whale_exchange_deposit",
  "chain": "BTC",
  "stage": "deposit_detected",
  "block_height": 850001,
  "detected_at": "2026-07-16T12:05:30+00:00",
  "whale_transfer": {
    "tx_hash": "9b2c...",
    "exchange": "binance",
    "to_address": "bc1q...",
    "amount_btc": 28.5,
    "btc_price_usd": 67000.0,
    "amount_usd": 1909500.0
  },
  "expected_credit_time": "2026-07-16T12:25:30+00:00",
  "sell_window_open": false,
  "signal_status": "monitoring",
  "updates": [
    {
      "time": "2026-07-16T12:05:30+00:00",
      "stage": "deposit_detected",
      "msg": "Whale deposit detected: 28.50 BTC ($1,909,500) to binance"
    }
  ]
}
```

## Building Your Own Client

The protocol is simple:
1. Connect to `wss://<host>:8443` with mTLS (provide all 3 cert files)
2. Receive JSON messages (one per signal event)
3. Optionally send `ping` to get `pong` (keepalive)
4. Auto-reconnect on disconnect — you'll get all active signals on reconnect

## S3 Signal History

Resolved signals are written to S3 for backtesting:
```
s3://crypto-rti-prod-us-east-1/data/signals/btc/{date}/{signal_id}.json
```

You can pull these with your existing S3 read access.

## Security

- **Keep `client-key.pem` secure.** Anyone with this file can connect as you.
- The connection is encrypted end-to-end (TLS 1.2+).
- The server rejects any connection without a valid client certificate.
