"""
CryptoRTI live signal client (mTLS WebSocket).

Connects to the cryptoRTI signal engine, maintains the current set of active
whale-deposit signals, and writes them to data/cryptorti_signals.json so the
trading strategy and dashboard can read them without touching the network.

Python does mTLS client certificates natively, so the bot connects directly —
no stunnel needed (stunnel is only required for a native MQL5 EA, which cannot
present client certs).

Config (env or .env.cryptorti):
    CRYPTORTI_HOST   (default 3.213.39.89)
    CRYPTORTI_PORT   (default 8443)
    CRYPTORTI_CA     (default cryptorti/certs/ca.pem)
    CRYPTORTI_CERT   (default cryptorti/certs/client.pem)
    CRYPTORTI_KEY    (default cryptorti/certs/client-key.pem)

Run standalone:
    python -m src.cryptorti.signal_client
"""

from __future__ import annotations

import os
import ssl
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("cryptorti.signal_client")

_CERT_DIR = os.path.join(config.BASE_DIR, "cryptorti", "certs")
HOST = os.getenv("CRYPTORTI_HOST", "3.213.39.89")
PORT = int(os.getenv("CRYPTORTI_PORT", "8443"))
CA = os.getenv("CRYPTORTI_CA", os.path.join(_CERT_DIR, "ca.pem"))
CERT = os.getenv("CRYPTORTI_CERT", os.path.join(_CERT_DIR, "client.pem"))
KEY = os.getenv("CRYPTORTI_KEY", os.path.join(_CERT_DIR, "client-key.pem"))

SIGNALS_PATH = os.path.join(config.DATA_DIR, "cryptorti_signals.json")

# Signal stages that indicate an active short opportunity
ACTIVE_SHORT_STATUSES = ("active_short", "selling_confirmed")


class SignalStore:
    """In-memory store of active signals, persisted to JSON for consumers."""

    def __init__(self):
        self.signals: dict[str, dict] = {}

    def update(self, signal: dict):
        sid = signal.get("signal_id")
        if not sid:
            return
        self.signals[sid] = signal
        # #44/#46: record every live whale signal into the bot's OWN outcome store
        # so it builds a self-sustaining labeled dataset (no reliance on Danny history).
        try:
            from src.cryptorti.whale_outcome_store import WhaleOutcomeStore
            if not hasattr(self, "_outcome_store"):
                self._outcome_store = WhaleOutcomeStore()
            self._outcome_store.record_signal(signal, source="websocket")
        except Exception:
            pass
        # drop resolved/expired after recording
        self._persist()

    def _persist(self):
        try:
            active = [s for s in self.signals.values()
                      if s.get("stage") not in ("resolved",)]
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "connected": True,
                "count": len(active),
                "signals": active[-50:],
            }
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = SIGNALS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp, SIGNALS_PATH)
        except Exception as e:
            logger.warning(f"persist signals failed: {e}")


def _ssl_context() -> Optional[ssl.SSLContext]:
    for p in (CA, CERT, KEY):
        if not os.path.exists(p):
            logger.error(f"Missing cert file: {p} — cannot connect to CryptoRTI live feed")
            return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_cert_chain(certfile=CERT, keyfile=KEY)
    ctx.load_verify_locations(cafile=CA)
    ctx.check_hostname = False  # self-signed CA
    return ctx


async def _listen(store: SignalStore):
    import websockets
    ctx = _ssl_context()
    if ctx is None:
        return
    uri = f"wss://{HOST}:{PORT}"
    logger.info(f"CryptoRTI connecting to {uri}")
    backoff = 1.0
    max_backoff = 60.0
    while True:
        try:
            async for ws in websockets.connect(uri, ssl=ctx, ping_interval=30):
                try:
                    logger.info("CryptoRTI connected")
                    backoff = 1.0  # reset on successful connection
                    async for message in ws:
                        if message == "pong":
                            continue
                        try:
                            signal = json.loads(message)
                        except Exception:
                            continue
                        store.update(signal)
                        logger.info(f"CryptoRTI signal {signal.get('signal_id')}: "
                                    f"stage={signal.get('stage')} status={signal.get('signal_status')}")
                except Exception as e:
                    logger.warning(f"CryptoRTI disconnected ({e}); reconnecting in {backoff}s…")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, max_backoff)
                    continue
        except Exception as e:
            logger.warning(f"CryptoRTI connection failed ({e}); retry in {backoff}s…")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, max_backoff)


def run():
    store = SignalStore()
    try:
        asyncio.run(_listen(store))
    except KeyboardInterrupt:
        pass


# ── consumer helper (used by the strategy + dashboard) ──────────────────────
def read_active_signals() -> dict:
    """Read the persisted signal state (safe if file missing)."""
    try:
        if os.path.exists(SIGNALS_PATH):
            with open(SIGNALS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {"connected": False, "count": 0, "signals": []}


def current_short_bias() -> Optional[dict]:
    """
    Return a dict describing an active BTC short bias if a validated-strength
    signal is currently live, else None.

    Operating point from backtest validation (CRYPTORTI_INTEGRATION.md §6):
    whale deposit >= $1M + selling confirmed / active_short.
    """
    state = read_active_signals()
    for s in state.get("signals", []):
        status = s.get("signal_status", "")
        stage = s.get("stage", "")
        usd = (s.get("whale_transfer") or {}).get("amount_usd", 0) or 0
        if (status in ACTIVE_SHORT_STATUSES or stage == "selling_confirmed") and usd >= 1_000_000:
            tape = s.get("tape") or {}
            vpin_pct = tape.get("vpin_percentile", 0) or 0
            # confidence scaled by tape strength; capped modest (it's a bias)
            conf = 0.45 + min(vpin_pct, 100) / 100 * 0.2  # 0.45–0.65
            return {
                "signal_id": s.get("signal_id"),
                "action": "sell",
                "confidence": round(conf, 3),
                "amount_usd": usd,
                "vpin_percentile": vpin_pct,
                "reason": f"CryptoRTI whale short: ${usd:,.0f} deposit, VPIN pct {vpin_pct}",
            }
    return None


if __name__ == "__main__":
    run()
