"""
Dukascopy historical data source — tick + bar loader for the backtest / forward-test
harness.

WHY THIS EXISTS
---------------
Dukascopy publishes some of the BEST free historical FX/CFD/commodity data on the
market: true bid/ask TICK data (with volumes) going back many years, per instrument.
This module downloads it directly from the public datafeed and adapts it to the exact
schemas our harness already speaks, so it drops in wherever MT5 data is used:

  - get_rates(symbol, timeframe, count)  -> list[bar dict]   (matches src/mt5/data.get_rates)
  - get_ticks(symbol, from_epoch, to_epoch) -> {"time":[],"bid":[],"ask":[]}  (matches get_ticks)

It intentionally does NOT depend on the `duka` pip package (that tool is fragile:
it fires 24 parallel requests per day and discards the whole day if any single hour
fails). We hit the raw datafeed politely and tolerate missing hours.

THE FEED
--------
URL:  https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
  - MONTH IS 0-INDEXED (January = "00").
  - Each file is one HOUR of ticks, LZMA-compressed.
  - Record = 20 bytes, BIG-endian struct '>IIIff':
        ms_offset  uint32   milliseconds since the hour start (UTC)
        ask        int32    ask * 10**point_scale
        bid        int32    bid * 10**point_scale
        ask_vol    float32
        bid_vol    float32
  - Prices are integers scaled by the instrument's point factor (see POINT_SCALE).
  - All timestamps are UTC.

PROVENANCE / DATA-HYGIENE
-------------------------
Dukascopy is a DIFFERENT broker to our live VT Markets MT5. Prices, spreads and tick
granularity differ. Use this for STRUCTURAL / robustness validation of the OsMA
confluence logic and for synthetic forward-test data — NOT for re-deriving the
MT5-specific strength-floor MAGNITUDES (osma_min_long/bulls/bears, atr_min), which
were tuned on MT5 ticks. Anything derived from this source should be tagged
data_source="DUKASCOPY" so the learning-window filter can exclude it from live-magnitude
learning. See DATA_SOURCES.md section 5.
"""

from __future__ import annotations

import lzma
import os
import struct
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from src.utils.logger import get_logger

logger = get_logger("data_sources.dukascopy")

# ── feed config ──────────────────────────────────────────────────────────────
_BASE_URL = ("https://datafeed.dukascopy.com/datafeed/"
             "{sym}/{year:04d}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5")
_USER_AGENT = "Mozilla/5.0 (compatible; langchain-bot/1.0; +backtest)"
_RECORD = struct.Struct(">IIIff")  # ms_offset, ask, bid, ask_vol, bid_vol
_RECORD_SIZE = 20

# Map OUR symbols -> Dukascopy instrument + price point scale (10**scale divisor).
# Point scale = number of decimal places Dukascopy encodes the price to.
#   FX 5-digit -> 5 ; metals/indices/crypto vary. Verify magnitudes before trusting.
_SYMBOL_MAP = {
    "XAUUSD": ("XAUUSD", 3),      # gold, 3 decimals (e.g. 2345.678)
    "BTCUSD": ("BTCUSD", 1),      # crypto: Dukascopy encodes BTCUSD to 1 decimal (raw/10)
    "GER40":  ("DEUIDXEUR", 3),   # DAX index (Dukascopy ticker DEUIDXEUR)
    # common FX for testing the pipeline:
    "EURUSD": ("EURUSD", 5),
    "GBPUSD": ("GBPUSD", 5),
}

# Timeframe string -> seconds (matches the "M1"/"M5"/... keys used across the harness)
_TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


def resolve(symbol: str) -> tuple[str, int]:
    """Return (dukascopy_ticker, point_scale) for one of OUR symbols.

    Falls back to the raw symbol at 5-decimal FX scale if unknown (so the pipeline
    still runs, but log a warning — verify the scale before trusting magnitudes).
    """
    base = symbol.upper().split("-")[0].split(".")[0]  # strip suffixes like -ECN
    if base in _SYMBOL_MAP:
        return _SYMBOL_MAP[base]
    logger.warning("Dukascopy: unknown symbol %s, defaulting to FX 5-decimal scale", symbol)
    return base, 5


# ── low-level fetch + decode ───────────────────────────────────────────────────
def _cache_dir() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    d = os.path.join(base, "dukascopy_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(duka_sym: str, day_hour: datetime) -> str:
    fn = f"{duka_sym}_{day_hour:%Y%m%d_%H}.bi5"
    return os.path.join(_cache_dir(), fn)


def _fetch_hour_raw(duka_sym: str, dt_hour: datetime, attempts: int = 6,
                    use_cache: bool = True) -> Optional[bytes]:
    """Download ONE hour .bi5 (compressed). Returns raw bytes, or None if genuinely
    missing (404). Never raises for a missing hour — the caller skips it. Only a real
    404 is cached as an empty marker; rate-limit / transient errors are NOT cached so
    a later run retries them. dt_hour must be a UTC datetime truncated to the hour."""
    cache = _cache_path(duka_sym, dt_hour)
    if use_cache and os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read() or None

    url = _BASE_URL.format(sym=duka_sym, year=dt_hour.year,
                           month=dt_hour.month - 1,  # 0-INDEXED month
                           day=dt_hour.day, hour=dt_hour.hour)
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    raw = resp.read(16 * 1024 * 1024)  # cap network read at 16 MB
                    if use_cache:
                        with open(cache, "wb") as f:
                            f.write(raw)
                    return raw or None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # No data for this hour (weekend/holiday gap) — cache an empty marker.
                if use_cache:
                    open(cache, "wb").close()
                return None
            if e.code == 429:  # rate limited — back off harder, do NOT cache
                time.sleep(1.5 * (i + 1))
                continue
            logger.debug("dukascopy %s %s HTTP %s (try %d)", duka_sym, dt_hour, e.code, i + 1)
        except Exception as e:
            logger.debug("dukascopy %s %s fetch error: %s (try %d)", duka_sym, dt_hour, e, i + 1)
        time.sleep(0.6 * (i + 1))  # polite backoff; avoid Dukascopy rate-limiting
    logger.warning("dukascopy: gave up on %s %s after %d attempts", duka_sym, dt_hour, attempts)
    return None


def decode_hour(raw: bytes, hour_start_epoch: int, point_scale: int) -> list[tuple]:
    """Decode one hour of raw .bi5 bytes into a list of tick tuples:
        (epoch_seconds_float, bid, ask, bid_vol, ask_vol)
    hour_start_epoch = UTC epoch seconds at the start of the hour."""
    if not raw:
        return []
    # bound the compressed input and the decompressed output: a legit hour of ticks is well
    # under a few MB, so cap hard to prevent a malicious/corrupt response from being a
    # decompression-bomb / OOM against the (live) process.
    _MAX_COMPRESSED = 16 * 1024 * 1024      # 16 MB compressed ceiling
    _MAX_DECOMPRESSED = 64 * 1024 * 1024    # 64 MB decompressed ceiling
    if len(raw) > _MAX_COMPRESSED:
        logger.warning("dukascopy: compressed hour %d bytes exceeds cap — skipping", len(raw))
        return []
    try:
        dec = lzma.LZMADecompressor()
        data = dec.decompress(raw, _MAX_DECOMPRESSED)
        if not dec.eof:
            logger.warning("dukascopy: decompressed data exceeds %d-byte cap — skipping", _MAX_DECOMPRESSED)
            return []
    except (lzma.LZMAError, EOFError) as e:
        logger.debug("dukascopy: LZMA decompress failed: %s", e)
        return []
    except MemoryError:
        logger.warning("dukascopy: MemoryError decompressing hour — skipping")
        return []
    div = float(10 ** point_scale)
    out = []
    for ms, ask_i, bid_i, ask_v, bid_v in _RECORD.iter_unpack(data[: (len(data) // _RECORD_SIZE) * _RECORD_SIZE]):
        t = hour_start_epoch + ms / 1000.0
        out.append((t, bid_i / div, ask_i / div, float(bid_v), float(ask_v)))
    return out


def _hour_range(start: datetime, end: datetime):
    """Yield UTC hour-truncated datetimes from start..end inclusive."""
    cur = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    stop = end.astimezone(timezone.utc)
    while cur <= stop:
        yield cur
        cur += timedelta(hours=1)


def fetch_ticks(symbol: str, start: datetime, end: datetime,
                use_cache: bool = True, workers: int = 8, progress_cb=None) -> list[tuple]:
    """Download + decode all ticks in [start, end] (UTC). Returns a flat, time-sorted
    list of (epoch_sec, bid, ask, bid_vol, ask_vol). Missing hours are skipped.

    Hours are fetched with bounded concurrency (workers) to stay fast without tripping
    Dukascopy rate-limiting; decoded results are reassembled in time order."""
    duka_sym, scale = resolve(symbol)
    hours = list(_hour_range(start, end))
    results: dict[int, list[tuple]] = {}

    def _one(dt_hour):
        raw = _fetch_hour_raw(duka_sym, dt_hour, use_cache=use_cache)
        if not raw:
            return int(dt_hour.timestamp()), []
        hour_epoch = int(dt_hour.timestamp())
        return hour_epoch, decode_hour(raw, hour_epoch, scale)

    if workers and workers > 1 and len(hours) > 1:
        from concurrent.futures import ThreadPoolExecutor
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for hour_epoch, ticks in ex.map(_one, hours):
                results[hour_epoch] = ticks
                done += 1
                if progress_cb and (done % 24 == 0 or done == len(hours)):
                    try:
                        progress_cb(done, len(hours))
                    except Exception:
                        pass
    else:
        for idx, dt_hour in enumerate(hours, 1):
            hour_epoch, ticks = _one(dt_hour)
            results[hour_epoch] = ticks
            if progress_cb and (idx % 24 == 0 or idx == len(hours)):
                try:
                    progress_cb(idx, len(hours))
                except Exception:
                    pass

    all_ticks: list[tuple] = []
    for hour_epoch in sorted(results):
        all_ticks.extend(results[hour_epoch])
    lo, hi = start.astimezone(timezone.utc).timestamp(), end.astimezone(timezone.utc).timestamp()
    all_ticks = [t for t in all_ticks if lo <= t[0] <= hi]
    all_ticks.sort(key=lambda r: r[0])
    logger.info("dukascopy: %s -> %d ticks (%s..%s)", symbol, len(all_ticks), start, end)
    return all_ticks


# ── bar aggregation ────────────────────────────────────────────────────────────
def ticks_to_bars(ticks: list[tuple], tf_seconds: int, use_mid: bool = True) -> list[dict]:
    """Aggregate raw ticks into OHLCV bar dicts matching src/mt5/data.get_rates:
        {time(str), timestamp(int epoch), open, high, low, close, volume(tick count), spread}
    Price = mid((bid+ask)/2) if use_mid else bid. Bars are UTC-aligned."""
    bars: list[dict] = []
    if not ticks:
        return bars
    cur_bucket = None
    o = h = l = c = 0.0
    vol = 0
    spread_sum = 0.0
    for t, bid, ask, _bv, _av in ticks:
        price = (bid + ask) / 2.0 if use_mid else bid
        bucket = int(t // tf_seconds) * tf_seconds
        if cur_bucket is None:
            cur_bucket = bucket
            o = h = l = c = price
            vol = 0
            spread_sum = 0.0
        elif bucket != cur_bucket:
            bars.append(_mk_bar(cur_bucket, o, h, l, c, vol, spread_sum))
            cur_bucket = bucket
            o = h = l = c = price
            vol = 0
            spread_sum = 0.0
        h = max(h, price)
        l = min(l, price)
        c = price
        vol += 1
        spread_sum += (ask - bid)
    bars.append(_mk_bar(cur_bucket, o, h, l, c, vol, spread_sum))
    return bars


def _mk_bar(bucket_epoch: int, o, h, l, c, vol, spread_sum) -> dict:
    # avg raw price spread over the bar; kept as float (informational only, unused by
    # the confluence/reproduction logic which reads OHLC).
    avg_spread = (spread_sum / vol) if vol else 0.0
    return {
        "time": str(datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).replace(tzinfo=None)),
        "timestamp": int(bucket_epoch),
        "open": float(o), "high": float(h), "low": float(l), "close": float(c),
        "volume": int(vol),
        "spread": round(float(avg_spread), 6),  # raw price spread; informational only
    }


# ── harness-compatible adapters (drop-in for src/mt5/data) ─────────────────────
class DukascopySource:
    """A rates/ticks provider with the SAME call surface as src/mt5/data.get_rates /
    get_ticks, backed by Dukascopy history. Inject into FloorDiscovery(get_rates_fn,
    get_ticks_fn) or shim the module-level functions in a backtest harness.

    Because get_rates(symbol, timeframe, count) has no explicit date window, we
    interpret `count` as "the most recent `count` bars ending at `until`" where
    `until` defaults to now (UTC). Set `until` for reproducible offline windows.
    """

    def __init__(self, until: Optional[datetime] = None, use_cache: bool = True,
                 use_mid: bool = True, workers: int = 3, progress_cb=None):
        self.until = until or datetime.now(timezone.utc)
        self.use_cache = use_cache
        self.use_mid = use_mid
        # gentle by default (onboarding is patient — avoid rate-limit give-ups)
        self.workers = workers
        self.progress_cb = progress_cb

    def get_rates(self, symbol: str, timeframe: str = "M1", count: int = 500) -> list[dict]:
        tf = _TF_SECONDS.get(timeframe)
        if tf is None:
            raise ValueError(f"Dukascopy: unsupported timeframe {timeframe}")
        # widen the tick window a little so the first/last buckets are complete
        span_sec = tf * count
        start = self.until - timedelta(seconds=span_sec + tf)
        ticks = fetch_ticks(symbol, start, self.until, use_cache=self.use_cache,
                            workers=self.workers, progress_cb=self.progress_cb)
        bars = ticks_to_bars(ticks, tf, use_mid=self.use_mid)
        return bars[-count:] if count and len(bars) > count else bars

    def get_ticks(self, symbol: str, from_epoch: float, to_epoch: float,
                  max_ticks: int = 5_000_000):
        start = datetime.fromtimestamp(float(from_epoch), tz=timezone.utc)
        end = datetime.fromtimestamp(float(to_epoch), tz=timezone.utc)
        ticks = fetch_ticks(symbol, start, end, use_cache=self.use_cache, workers=self.workers)
        if not ticks:
            return None
        ticks = ticks[:max_ticks]
        return {
            "time": [int(t[0]) for t in ticks],
            "bid": [t[1] for t in ticks],
            "ask": [t[2] for t in ticks],
        }


# ── offline export (reproduce_*/discover_floors .npy + CSV formats) ─────────────
def save_npy(ticks: list[tuple], path: str) -> int:
    """Write ticks as a numpy structured array matching the MT5 copy_ticks dtype the
    reproduce_*/discover_floors scripts np.load(): fields time(i8),bid(f8),ask(f8),
    last(f8),volume(u8),time_msc(i8),flags(u4),volume_real(f8). Only time/bid/ask are
    populated (the only fields those readers touch)."""
    import numpy as np
    dtype = np.dtype([
        ("time", "<i8"), ("bid", "<f8"), ("ask", "<f8"), ("last", "<f8"),
        ("volume", "<u8"), ("time_msc", "<i8"), ("flags", "<u4"), ("volume_real", "<f8"),
    ])
    arr = np.zeros(len(ticks), dtype=dtype)
    for i, (t, bid, ask, _bv, _av) in enumerate(ticks):
        arr[i]["time"] = int(t)
        arr[i]["bid"] = bid
        arr[i]["ask"] = ask
        arr[i]["time_msc"] = int(t * 1000)
    np.save(path, arr)
    logger.info("dukascopy: wrote %d ticks -> %s", len(arr), path)
    return len(arr)


def save_bars_csv(bars: list[dict], path: str) -> int:
    """Write bars as a reproduce_*-style M1 CSV: columns time(epoch sec),open,high,
    low,close (utf-8-sig)."""
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close"])
        for b in bars:
            w.writerow([b["timestamp"], b["open"], b["high"], b["low"], b["close"]])
    logger.info("dukascopy: wrote %d bars -> %s", len(bars), path)
    return len(bars)


# ── smoke test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    # default: one recent-ish weekday hour we know exists
    day = sys.argv[2] if len(sys.argv) > 2 else "2024-05-03"
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = d + timedelta(hours=10)
    end = d + timedelta(hours=11)

    print(f"[dukascopy smoke] {sym} {start} .. {end}")
    ticks = fetch_ticks(sym, start, end, use_cache=True)
    print(f"  ticks: {len(ticks)}")
    if ticks:
        print(f"  first: t={ticks[0][0]:.3f} bid={ticks[0][1]} ask={ticks[0][2]}")
        print(f"  last : t={ticks[-1][0]:.3f} bid={ticks[-1][1]} ask={ticks[-1][2]}")
        bars = ticks_to_bars(ticks, _TF_SECONDS["M1"])
        print(f"  M1 bars: {len(bars)}")
        if bars:
            print(f"  bar[0]: {bars[0]}")
        src = DukascopySource(until=end)
        gt = src.get_ticks(sym, start.timestamp(), end.timestamp())
        print(f"  get_ticks keys: {list(gt.keys()) if gt else None}, n={len(gt['time']) if gt else 0}")
