"""
CryptoRTI S3 client — read historical data from the cryptoRTI bucket.

Credentials come from the standard AWS chain (env vars / named profile / IAM
role). NEVER hardcode keys here. Set them in a git-ignored .env.cryptorti or the
process environment:

    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   (or)   AWS_PROFILE
    CRYPTORTI_BUCKET (default: crypto-rti-prod-us-east-1)
    AWS_DEFAULT_REGION (default: us-east-1)

Data notes (from the platform data dictionary):
  * timestamps are microseconds UTC.
  * features/{exchange}/{symbol}/{date}/features_{date}.parquet has 280 v5 columns
    including forward labels (label_direction_{h}, label_price_change_{h}).
  * signals/btc/{date}/{signal_id}.json are resolved whale-deposit signals.
  * processed data is T-1; Binance 2026-07-05 is incomplete.
"""

from __future__ import annotations

import io
import os
import json
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("cryptorti.s3")


def _load_cryptorti_env():
    """
    Load credentials from cryptorti/.env.cryptorti if present and not already in
    the environment. Keeps secrets out of code and lets the running service pick
    them up automatically.
    """
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("CRYPTORTI_BUCKET"):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(os.path.dirname(os.path.dirname(here)), "cryptorti", ".env.cryptorti")
    if not os.path.exists(env_path):
        return
    try:
        for line in open(env_path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception as e:
        logger.debug(f"cryptorti env load skip: {e}")


_load_cryptorti_env()

BUCKET = os.getenv("CRYPTORTI_BUCKET", "crypto-rti-prod-us-east-1")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
SHARED_PREFIX = os.getenv("CRYPTORTI_SHARED_PREFIX", "martin/")


def put_shared(name: str, data: bytes, content_type: str = "text/markdown") -> bool:
    """Write a file into our shared folder (martin/) for async exchange with Danny."""
    try:
        _client().put_object(Bucket=BUCKET, Key=f"{SHARED_PREFIX}{name}",
                             Body=data, ContentType=content_type)
        logger.info(f"Wrote shared file {SHARED_PREFIX}{name}")
        return True
    except Exception as e:
        logger.warning(f"put_shared failed: {e}")
        return False


def get_shared(name: str) -> Optional[bytes]:
    """Read a file from the shared folder (e.g. Danny's answers)."""
    try:
        return _client().get_object(Bucket=BUCKET, Key=f"{SHARED_PREFIX}{name}")["Body"].read()
    except Exception as e:
        logger.debug(f"get_shared {name} failed: {e}")
        return None


def _client():
    import boto3
    return boto3.client("s3", region_name=REGION)


def available() -> bool:
    """True if boto3 + credentials appear usable."""
    try:
        import boto3  # noqa
        c = _client()
        c.list_objects_v2(Bucket=BUCKET, MaxKeys=1)
        return True
    except Exception as e:
        logger.warning(f"CryptoRTI S3 unavailable: {e}")
        return False


def list_prefix(prefix: str) -> tuple[list[str], list[str]]:
    """Return (subdirs, files) directly under a prefix."""
    c = _client()
    r = c.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/")
    dirs = [p["Prefix"] for p in r.get("CommonPrefixes", [])]
    files = [o["Key"] for o in r.get("Contents", [])]
    return dirs, files


def read_json(key: str) -> Optional[dict]:
    try:
        c = _client()
        body = c.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        return json.loads(body)
    except Exception as e:
        logger.warning(f"read_json {key} failed: {e}")
        return None


def read_parquet(key: str):
    """Return a DataFrame for a parquet key (or None)."""
    try:
        import pandas as pd
        c = _client()
        body = c.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        return pd.read_parquet(io.BytesIO(body))
    except Exception as e:
        logger.warning(f"read_parquet {key} failed: {e}")
        return None


# ── high-level helpers ──────────────────────────────────────────────────────
def features_key(exchange: str, symbol: str, date: str) -> str:
    return f"data/features/{exchange}/{symbol}/{date}/features_{date}.parquet"


def load_features(date: str, exchange: str = "coinbase", symbol: str = "BTC-USD"):
    """Load the 280-column v5 feature+label table for one day."""
    return read_parquet(features_key(exchange, symbol, date))


def load_signals(date: str, chain: str = "btc") -> list[dict]:
    """Load all resolved signal JSONs for a date (parallel fetch for speed)."""
    from concurrent.futures import ThreadPoolExecutor
    prefix = f"data/signals/{chain}/{date}/"
    _, files = list_prefix(prefix)
    keys = [k for k in files if k.endswith(".json")]
    if not keys:
        return []
    out = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for j in ex.map(read_json, keys):
            if j:
                out.append(j)
    return out


def list_signal_dates(chain: str = "btc") -> list[str]:
    dirs, _ = list_prefix(f"data/signals/{chain}/")
    return [d.rstrip("/").split("/")[-1] for d in dirs]


def list_whale_event_dates(chain: str = "btc") -> list[str]:
    dirs, _ = list_prefix(f"data/whale_events/{chain}/")
    return [d.rstrip("/").split("/")[-1] for d in dirs]


def load_whale_events(date: str, chain: str = "btc"):
    """
    Load raw whale-transfer events for a date as a DataFrame. Unlike the signals
    feed (deposits only), this includes event_type = deposit OR withdrawal, so we
    can derive BOTH sell (deposit->exchange) and buy (withdrawal->wallet) signals.
    Parquet files are fetched in parallel and concatenated.
    """
    import io
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor
    prefix = f"data/whale_events/{chain}/{date}/"
    _, files = list_prefix(prefix)
    keys = [k for k in files if k.endswith(".parquet")]
    if not keys:
        return pd.DataFrame()

    def _read(k):
        try:
            c = _client()
            return pd.read_parquet(io.BytesIO(c.get_object(Bucket=BUCKET, Key=k)["Body"].read()))
        except Exception as e:
            logger.debug(f"whale event read {k} failed: {e}")
            return None

    frames = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for df in ex.map(_read, keys):
            if df is not None and len(df):
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # de-duplicate identical tx rows that appear across snapshot files
    if "tx_hash" in out.columns:
        out = out.drop_duplicates(subset=["tx_hash", "event_type"]).reset_index(drop=True)
    return out


def _unused_list_signal_dates(chain: str = "btc") -> list[str]:
    dirs, _ = list_prefix(f"data/signals/{chain}/")
    return [d.rstrip("/").split("/")[-1] for d in dirs]


def list_feature_dates(exchange: str = "coinbase", symbol: str = "BTC-USD") -> list[str]:
    dirs, _ = list_prefix(f"data/features/{exchange}/{symbol}/")
    return [d.rstrip("/").split("/")[-1] for d in dirs]
