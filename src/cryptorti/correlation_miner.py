"""
CryptoRTI Correlation Miner (Phase A).

Learns the historical relationship between a cryptoRTI whale event and the
large BTCUSD candles it produces shortly after — so we can predict and 'surf'
the resulting wave instead of reacting late.

For each historical event: classify it (size bucket, exchange, inferred
direction, tape) and measure the BTCUSD response in a window after the event
(number of large candles, cumulative move in bps, lag to first large candle,
whether price moved in the inferred direction). Aggregate into a correlation
table keyed by event profile, persisted for recall by the live predictor.

Direction inference: a deposit TO an exchange = distribution = likely SELL
pressure (out of the holder's wallet, onto the order book). Withdrawal/into a
wallet = accumulation = likely BUY. If the feed provides an explicit direction
field we use that; otherwise we infer from the exchange-deposit semantics.
"""

from __future__ import annotations

import os
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("correlation_miner")

TABLE_PATH = os.path.join(config.DATA_DIR, "cryptorti_correlation.json")


def _size_bucket(usd: float) -> str:
    if usd >= 10_000_000:
        return "10M+"
    if usd >= 5_000_000:
        return "5-10M"
    if usd >= 2_000_000:
        return "2-5M"
    if usd >= 1_000_000:
        return "1-2M"
    return "<1M"


def _infer_direction(signal: dict) -> str:
    """Return 'sell' (exchange deposit / distribution) or 'buy' (accumulation)."""
    wt = signal.get("whale_transfer") or {}
    explicit = (wt.get("direction") or signal.get("direction") or "").lower()
    if explicit in ("buy", "inflow", "accumulation"):
        return "buy"
    if explicit in ("sell", "outflow", "distribution", "deposit"):
        return "sell"
    # infer: a transfer TO an exchange is typically pre-sale distribution
    if wt.get("exchange"):
        return "sell"
    return "sell"


class CorrelationMiner:
    def __init__(self):
        self.table: dict = {}

    def _event_time(self, signal: dict) -> Optional[datetime]:
        for k in ("detected_at", "expected_credit_time"):
            ts = signal.get(k)
            if ts:
                try:
                    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except Exception:
                    continue
        return None

    def _measure_response(self, candles: list[dict], event_dt: datetime,
                          direction: str, window_min: int, atr: float) -> Optional[dict]:
        """
        Measure BTCUSD response in [event, event+window]. `candles` are M1 or M5
        dicts with timestamp (epoch seconds) + ohlc. `atr` is a typical bar range
        used to define a 'large' candle (range > 1.5*atr).
        """
        start = event_dt.timestamp()
        end = start + window_min * 60
        seg = [c for c in candles if start <= c.get("timestamp", 0) <= end]
        if len(seg) < 3:
            return None
        entry_price = seg[0]["open"]
        large_thresh = 1.5 * atr if atr > 0 else 0
        n_large = 0
        first_large_lag = None
        peak_move = 0.0
        for idx, c in enumerate(seg):
            rng = c["high"] - c["low"]
            if large_thresh and rng >= large_thresh:
                n_large += 1
                if first_large_lag is None:
                    first_large_lag = int((c["timestamp"] - start) / 60)
            move = (c["close"] - entry_price)
            if direction == "sell":
                move = -move
            peak_move = max(peak_move, move)
        end_move = seg[-1]["close"] - entry_price
        if direction == "sell":
            end_move = -end_move
        move_bps = (end_move / entry_price) * 10000 if entry_price else 0
        peak_bps = (peak_move / entry_price) * 10000 if entry_price else 0
        return {
            "n_large_candles": n_large,
            "first_large_lag_min": first_large_lag,
            "move_bps": round(move_bps, 1),
            "peak_bps": round(peak_bps, 1),
            "hit": move_bps > 5,   # moved in inferred direction by >0.05%
        }

    def mine(self, symbol_mt5: str = "BTCUSD", timeframe: str = "M5",
             window_min: int = 90, max_days: int = 30) -> dict:
        """
        Build the correlation table from raw whale_events x MT5 candles.

        Uses whale_events (which carry event_type = deposit|withdrawal) so we get
        BOTH directions:
          deposit  -> coins onto an exchange  -> distribution -> SELL
          withdrawal -> coins off to a wallet -> accumulation -> BUY
        """
        from src.cryptorti import s3_client
        from src.mt5.data import get_rates
        from src.strategies.indicators import ohlcv_to_dataframe, atr as atr_fn
        from datetime import datetime, timezone

        candles = get_rates(symbol_mt5, timeframe=timeframe, count=8000)
        if not candles:
            logger.warning("correlation mine: no MT5 candles")
            return {}
        df = ohlcv_to_dataframe(candles)
        atr_series = atr_fn(df, 14)
        typical_atr = float(atr_series.dropna().median()) if atr_series.notna().any() else 0.0

        dates = s3_client.list_whale_event_dates("btc")[-max_days:]
        buckets = defaultdict(list)
        total_events = 0

        for d in dates:
            events = s3_client.load_whale_events(d, "btc")
            if events is None or len(events) == 0:
                continue
            for _, ev in events.iterrows():
                usd = float(ev.get("amount_usd", 0) or 0)
                if usd < 500_000:
                    continue
                etype = str(ev.get("event_type", "")).lower()
                direction = "buy" if etype == "withdrawal" else "sell"
                # event timestamp is microseconds UTC
                try:
                    edt = datetime.fromtimestamp(int(ev["timestamp"]) / 1_000_000, tz=timezone.utc)
                except Exception:
                    continue
                resp = self._measure_response(candles, edt, direction, window_min, typical_atr)
                if not resp:
                    continue
                total_events += 1
                profile = f"{_size_bucket(usd)}|{ev.get('exchange','?')}|{direction}"
                buckets[profile].append(resp)

        table = {}
        for profile, samples in buckets.items():
            n = len(samples)
            if n < 2:
                continue
            hits = sum(1 for s in samples if s["hit"])
            table[profile] = {
                "samples": n,
                "hit_rate": round(hits / n * 100, 1),
                "avg_move_bps": round(sum(s["move_bps"] for s in samples) / n, 1),
                "avg_peak_bps": round(sum(s["peak_bps"] for s in samples) / n, 1),
                "avg_n_large": round(sum(s["n_large_candles"] for s in samples) / n, 1),
                "avg_lag_min": round(sum((s["first_large_lag_min"] or window_min)
                                         for s in samples) / n, 1),
                "direction": profile.split("|")[-1],
            }
        self.table = table
        self._persist(total_events, window_min, timeframe)
        logger.info(f"Correlation mined: {total_events} events -> {len(table)} profiles")
        return table

    def _persist(self, total_events, window_min, timeframe):
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_events": total_events, "window_min": window_min,
                "timeframe": timeframe, "profiles": self.table,
            }
            tmp = TABLE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, TABLE_PATH)
        except Exception as e:
            logger.warning(f"correlation persist failed: {e}")

    @staticmethod
    def load() -> dict:
        try:
            if os.path.exists(TABLE_PATH):
                with open(TABLE_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"profiles": {}}


if __name__ == "__main__":
    import os as _os
    _os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    m = CorrelationMiner()
    print(json.dumps(m.mine(), indent=2))
