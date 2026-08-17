"""QMMP features: build the multi-dimensional feature matrix on the M1 base, with all 38
MT5 indicators computed on EACH timeframe (M1..H4) and merged onto M1 by causal as-of
join (last CLOSED higher-TF bar at/before each M1 time -> no look-ahead). Adds the OsMA
4-state classifier + cycle-internal index (on M1), and carries session flags.

Input:  data/qmmp/<symbol>/{M1,M5,M15,M30,H1,H4}.parquet
Output: data/qmmp/<symbol>/features_m1.parquet
Usage:  python -m scripts.qmmp.features BTCUSD  [--base M1_deep]
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np, pandas as pd, polars as pl
from scripts.mt5_all_indicators import all_indicators

TFS = ["M1", "M5", "M15", "M30", "H1", "H4"]
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")


def _osma_states(osma: pd.Series) -> tuple[pd.Series, pd.Series]:
    """4-state classifier + cycle-internal index. S1 BullExp, S2 BullContr,
    S3 BearExp, S4 BearContr."""
    d = osma.diff()
    state = pd.Series(0, index=osma.index)
    state[(osma > 0) & (d > 0)] = 1
    state[(osma > 0) & (d <= 0)] = 2
    state[(osma < 0) & (d < 0)] = 3
    state[(osma < 0) & (d >= 0)] = 4
    changed = state != state.shift(1)
    cycle_index = changed.groupby(changed.cumsum()).cumcount()
    return state, cycle_index


def _tf_features(pdf: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """All 38 indicators for one timeframe; return df indexed by time with prefixed cols."""
    pdf = pdf.rename(columns={"volume": "tick_volume"})
    if "tick_volume" not in pdf:
        pdf["tick_volume"] = 1.0
    pdf["volume"] = pdf["tick_volume"]
    ind = all_indicators(pdf)
    out = pd.DataFrame(index=pdf.index)
    for name, s in ind.items():
        out[f"{prefix}_{name}"] = s.values
    return out


def build(symbol: str, base: str = "M1"):
    sym = symbol.upper()
    d = os.path.join(OUTDIR, sym)
    base_path = os.path.join(d, f"{base}.parquet")
    if not os.path.exists(base_path):
        raise SystemExit(f"missing {base_path} — run ingest first")
    base_df = pl.read_parquet(base_path).sort("time").to_pandas()
    base_df = base_df.set_index("time")
    # base-TF indicators + OsMA state on the base timeframe
    feat = _tf_features(base_df.reset_index(), "M1").set_index(base_df.index)
    osma = feat["M1_OSMA"]
    state, cyc_idx = _osma_states(osma)
    feat["osma_state"] = state.values
    feat["cycle_index"] = cyc_idx.values
    # carry session flags + OHLC from base
    for col in ("open", "high", "low", "close", "volume",
                "session_asia", "session_london", "session_ny", "weekday"):
        if col in base_df:
            feat[col] = base_df[col].values

    # merge higher TFs as-of (causal: last CLOSED HTF bar at/before each M1 time)
    base_reset = feat.reset_index().rename(columns={"index": "time"})
    if "time" not in base_reset.columns:
        base_reset = base_reset.rename(columns={base_reset.columns[0]: "time"})
    base_reset = base_reset.sort_values("time")
    for tf in TFS:
        if tf == base or tf == "M1":
            continue
        p = os.path.join(d, f"{tf}.parquet")
        if not os.path.exists(p):
            continue
        htf = pl.read_parquet(p).sort("time").to_pandas().set_index("time")
        hfeat = _tf_features(htf.reset_index(), tf).set_index(htf.index)
        # shift by 1 bar so we only use the LAST CLOSED htf bar (no look-ahead)
        hfeat = hfeat.shift(1).reset_index().rename(columns={"index": "time"})
        if "time" not in hfeat.columns:
            hfeat = hfeat.rename(columns={hfeat.columns[0]: "time"})
        hfeat = hfeat.sort_values("time")
        base_reset = pd.merge_asof(base_reset, hfeat, on="time", direction="backward")

    out = pl.from_pandas(base_reset)
    outpath = os.path.join(d, "features_m1.parquet")
    out.write_parquet(outpath)
    n_feat = len([c for c in base_reset.columns if any(c.startswith(f"{t}_") for t in TFS)])
    print(f"{sym}: {len(base_reset)} rows, {n_feat} indicator features across {len(TFS)} TFs "
          f"+ osma_state + cycle_index -> {outpath}")
    # quick sanity: state distribution
    vc = base_reset["osma_state"].value_counts().to_dict()
    print(f"  OsMA states (1=BullExp,2=BullContr,3=BearExp,4=BearContr): {vc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--base", default="M1")
    args = ap.parse_args()
    build(args.symbol, args.base)


if __name__ == "__main__":
    main()
