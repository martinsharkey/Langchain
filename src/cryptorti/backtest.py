"""
CryptoRTI signal validation backtest.

The disciplined step BEFORE trading a CryptoRTI-derived strategy: measure whether
the whale-deposit + VPIN/flow conditions actually predict forward BTC moves, using
the platform's own pre-computed forward labels (no look-ahead if we only use
label_* as targets, never as features).

Hypothesis under test:
    After a whale deposit (whale_deposit_flag / whale_credit_window active), when
    VPIN is elevated (high percentile) AND short-term delta is negative (selling on
    the tape), forward returns are negative more often than base rate — i.e. a
    tradeable SHORT edge.

Usage:
    from src.cryptorti.backtest import run_validation
    run_validation(dates=["2026-07-27","2026-07-28"], horizon="15m")
"""

from __future__ import annotations

from typing import Optional

from src.cryptorti import s3_client
from src.utils.logger import get_logger

logger = get_logger("cryptorti.backtest")


def run_validation(
    dates: Optional[list[str]] = None,
    horizon: str = "15m",
    vpin_pct_min: float = 80.0,
    delta_col: str = "flow_delta_5m",
    exchange: str = "coinbase",
    symbol: str = "BTC-USD",
) -> dict:
    """
    Evaluate the whale+VPIN short hypothesis against forward labels.

    Returns a dict of honest metrics: base rate vs signal hit rate, average
    forward move, and counts — per the chosen horizon.
    """
    import pandas as pd
    import numpy as np

    if dates is None:
        # default: the last few available feature dates (T-1)
        all_dates = s3_client.list_feature_dates(exchange, symbol)
        dates = all_dates[-5:] if all_dates else []
    if not dates:
        return {"error": "no feature dates available"}

    label_dir = f"label_direction_{horizon}"
    label_chg = f"label_price_change_{horizon}"

    frames = []
    for d in dates:
        df = s3_client.load_features(d, exchange, symbol)
        if df is None or label_dir not in df.columns:
            logger.warning(f"skip {d}: no data/labels")
            continue
        frames.append(df)
    if not frames:
        return {"error": "no usable feature frames", "dates": dates}

    df = pd.concat(frames, ignore_index=True)
    n_total = len(df)

    # Base rate: how often price goes DOWN over the horizon, unconditionally
    base_down = float((df[label_dir] == -1).mean())
    base_move = float(df[label_chg].mean())

    # Signal condition: whale deposit context + elevated VPIN + negative delta
    whale_active = (df.get("whale_deposit_flag", 0) == 1)
    if "whale_credit_window" in df.columns:
        whale_active = whale_active | (df["whale_credit_window"] == 1)
    vpin_hot = df.get("vpin_percentile", 0) >= vpin_pct_min
    selling = df.get(delta_col, 0) < 0

    sig = whale_active & vpin_hot & selling
    n_sig = int(sig.sum())

    result = {
        "dates": dates,
        "horizon": horizon,
        "rows_total": n_total,
        "base_rate_down": round(base_down, 4),
        "base_avg_move_pct": round(base_move, 4),
        "signal_condition": f"whale_active & vpin_pct>={vpin_pct_min} & {delta_col}<0",
        "signal_count": n_sig,
    }

    if n_sig >= 5:
        sub = df[sig]
        sig_down = float((sub[label_dir] == -1).mean())
        sig_move = float(sub[label_chg].mean())
        result.update({
            "signal_hit_rate_down": round(sig_down, 4),
            "signal_avg_move_pct": round(sig_move, 4),
            "edge_vs_base_down": round(sig_down - base_down, 4),
            "edge_vs_base_move": round(sig_move - base_move, 4),
            "verdict": (
                "PROMISING short edge" if (sig_down > base_down + 0.05 and sig_move < base_move)
                else "WEAK / no clear edge"
            ),
        })
    else:
        result["verdict"] = f"insufficient signal samples ({n_sig}) — widen dates or loosen thresholds"

    logger.info(f"CryptoRTI validation: {result.get('verdict')} "
                f"(n_sig={n_sig}, hit={result.get('signal_hit_rate_down')}, base={base_down:.2f})")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run_validation(), indent=2, default=str))
