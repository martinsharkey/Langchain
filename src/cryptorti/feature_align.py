"""
CryptoRTI whale/VPIN feature alignment onto MT5 bars (#43).

Attaches the platform's whale/VPIN/flow features (from S3, via s3_client) onto MT5
OHLCV bars CAUSALLY — for each bar we take the most recent CryptoRTI feature row
at-or-before the bar's timestamp (never a future row → no look-ahead). This lets
the Backtester / edge_discovery / robust_tester SEE the whale features so the live
CryptoRTI hybrid boost can be walk-forward validated the same way the technical
edge is, instead of running live-only on an unproven hypothesis.

The S3 feature table is 1-minute, microseconds-UTC `timestamp`, with columns incl.
vpin, vpin_percentile, flow_delta_5m, whale_deposit_flag, whale_credit_window,
whale_flow_active. We surface a compact, causally-safe subset per bar.

Offline / non-fatal: if S3 is unavailable or a date is missing, bars get neutral
whale features (whale_active=0, vpin=NaN) so the backtest still runs (tech-only).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger("cryptorti.feature_align")

# compact causal feature subset surfaced onto each bar
WHALE_FEATURES = ["vpin", "vpin_percentile", "flow_delta_5m",
                  "whale_deposit_flag", "whale_credit_window", "whale_flow_active"]


def _bar_dt(ts) -> datetime:
    """MT5 bar 'time' is epoch SECONDS (int/np.int64/float) or a parseable string."""
    # numpy integer types are NOT Python int -> handle numerics broadly
    try:
        v = int(ts)
        # epoch seconds (10-digit) sanity: treat plausible ranges as seconds
        if 1_000_000_000 <= v <= 9_999_999_999:
            return datetime.fromtimestamp(v, tz=timezone.utc)
    except (TypeError, ValueError):
        pass
    return pd.to_datetime(ts, utc=True).to_pydatetime()


def _dates_from_bars(bdf) -> list[str]:
    """UTC YYYY-MM-DD dates spanned by the bar set (from epoch-seconds 'time')."""
    try:
        t0 = _bar_dt(bdf["time"].iloc[0])
        t1 = _bar_dt(bdf["time"].iloc[-1])
        days = pd.date_range(t0.date(), t1.date(), freq="D")
        return [d.strftime("%Y-%m-%d") for d in days]
    except Exception as e:
        logger.debug(f"date derivation skip: {e}")
        return []


def load_whale_features(dates: list[str], exchange="coinbase", symbol="BTC-USD") -> pd.DataFrame:
    """Load + concat the S3 feature tables for the given YYYY-MM-DD dates.
    Returns a DataFrame indexed by UTC datetime with the whale/VPIN subset, or empty."""
    from src.cryptorti import s3_client
    if not s3_client.available():
        return pd.DataFrame()
    frames = []
    for d in dates:
        try:
            df = s3_client.load_features(d, exchange, symbol)
        except Exception as e:
            logger.debug(f"whale features load skip {d}: {e}")
            continue
        if df is None or "timestamp" not in df.columns:
            continue
        cols = [c for c in WHALE_FEATURES if c in df.columns]
        if not cols:
            continue
        sub = df[["timestamp"] + cols].copy()
        # timestamp is microseconds UTC
        sub["dt"] = pd.to_datetime(sub["timestamp"], unit="us", utc=True)
        frames.append(sub.set_index("dt")[cols])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


def attach_whale_features(bars, dates: list[str] = None,
                          exchange="coinbase", symbol="BTC-USD") -> pd.DataFrame:
    """
    Return `bars` (list of dicts or DataFrame) as a DataFrame with the whale/VPIN
    features attached CAUSALLY (as-of the most recent feature row at-or-before each
    bar). Missing → neutral (whale_active=0). Adds a boolean `whale_active` too.
    """
    bdf = pd.DataFrame(bars) if not isinstance(bars, pd.DataFrame) else bars.copy()
    if bdf.empty:
        return bdf
    # derive the dates to load from the bar span if not given
    if dates is None:
        dates = _dates_from_bars(bdf)
    feats = load_whale_features(dates, exchange, symbol) if dates else pd.DataFrame()
    # neutral defaults
    for c in WHALE_FEATURES:
        bdf[c] = 0.0 if c not in ("vpin", "vpin_percentile", "flow_delta_5m") else float("nan")
    bdf["whale_active"] = 0
    if feats.empty:
        return bdf
    # causal as-of merge: for each bar, the last feature row at-or-before its time
    bdf["_dt"] = bdf["time"].map(_bar_dt)
    bdf = bdf.sort_values("_dt")
    merged = pd.merge_asof(bdf, feats.reset_index().rename(columns={"index": "dt"}),
                           left_on="_dt", right_on="dt", direction="backward",
                           suffixes=("", "_w"))
    for c in WHALE_FEATURES:
        wc = c + "_w" if (c + "_w") in merged.columns else c
        if wc in merged.columns:
            bdf[c] = merged[wc].values
    # whale_active = a deposit flag or an active flow within the causal window
    active = ((pd.to_numeric(bdf["whale_deposit_flag"], errors="coerce").fillna(0) > 0) |
              (pd.to_numeric(bdf["whale_credit_window"], errors="coerce").fillna(0) > 0) |
              (pd.to_numeric(bdf["whale_flow_active"], errors="coerce").fillna(0) > 0))
    bdf["whale_active"] = active.astype(int)
    bdf.drop(columns=["_dt"], errors="ignore", inplace=True)
    return bdf


def whale_coverage(bdf: pd.DataFrame) -> dict:
    """Summary of how much of the bar set has whale features (for honest reporting)."""
    if bdf is None or bdf.empty or "whale_active" not in bdf:
        return {"bars": 0, "whale_active_bars": 0, "coverage_pct": 0.0}
    n = len(bdf); active = int(bdf["whale_active"].sum())
    has_vpin = int(pd.to_numeric(bdf.get("vpin"), errors="coerce").notna().sum()) if "vpin" in bdf else 0
    return {"bars": n, "whale_active_bars": active,
            "vpin_bars": has_vpin, "coverage_pct": round(has_vpin / n * 100, 1) if n else 0.0}
