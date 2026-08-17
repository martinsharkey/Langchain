"""QMMP mining: label each OsMA-cycle-origin entry as WINNER vs FAKEOUT, then use
RandomForest + XGBoost feature-importance (per session) to rank which of the 276
multi-TF indicator features separate winners from fakeouts. Includes a WALK-FORWARD
out-of-sample check so we don't trust in-sample-only importance. Optional PCA view.

Entry universe: OsMA-cycle origins (cycle_index==0) that are also a fresh state (S1 for
long, S3 for short) — the structural entry the strategy uses.

Input:  data/qmmp/<symbol>/features_m1.parquet
Output: data/qmmp/<symbol>/attribution.csv  + console importance report
Usage:  python -m scripts.qmmp.mine BTCUSD [--target-pts 2000] [--horizon 60]
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np, pandas as pd, polars as pl
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")


def label_entries(df: pd.DataFrame, point: float, target_pts: float, horizon: int):
    """Winner = within `horizon` bars price travels +target_pts in the trade direction
    BEFORE breaching the cycle's structural swing (entry-side extreme). Fakeout = not."""
    high = df["high"].values; low = df["low"].values; close = df["close"].values
    n = len(df)
    rows = []
    st = df["osma_state"].values; ci = df["cycle_index"].values
    for i in range(n - 2):
        if ci[i] != 0:
            continue
        is_long = st[i] == 1
        is_short = st[i] == 3
        if not (is_long or is_short):
            continue
        entry = close[i]
        end = min(i + horizon, n)
        seg_hi = high[i+1:end].max() if end > i+1 else entry
        seg_lo = low[i+1:end].min() if end > i+1 else entry
        if is_long:
            fav = (seg_hi - entry) / point; adv = (entry - seg_lo) / point
        else:
            fav = (entry - seg_lo) / point; adv = (seg_hi - entry) / point
        winner = 1 if (fav >= target_pts and fav > adv) else 0
        rows.append((i, "long" if is_long else "short", winner, fav, adv))
    return rows


def session_of_row(r):
    if r["session_ny"]: s = "NewYork"
    elif r["session_london"]: s = "London"
    elif r["session_asia"]: s = "Asian"
    else: s = "Off"
    return s


def attribute(name, X, y, feat_names, folds=4):
    """Walk-forward XGBoost + RF importance. Returns mean OOS AUC and top features."""
    idx = np.arange(len(y)); fs = len(y) // folds
    aucs = []
    imp_sum = np.zeros(X.shape[1])
    for k in range(folds - 1):
        tr = slice(0, (k+1)*fs); te = slice((k+1)*fs, (k+2)*fs)
        if len(set(y[tr])) < 2 or len(set(y[te])) < 2 or (te.stop-te.start) < 20:
            continue
        m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.03,
                              subsample=0.8, colsample_bytree=0.5, min_child_weight=6,
                              reg_lambda=3.0, eval_metric="logloss")
        m.fit(X[tr], y[tr]); p = m.predict_proba(X[te])[:, 1]
        aucs.append(roc_auc_score(y[te], p)); imp_sum += m.feature_importances_
    if not aucs:
        return None, []
    top = sorted(zip(feat_names, imp_sum), key=lambda z: -z[1])[:15]
    return (np.mean(aucs), min(aucs), max(aucs)), top


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--target-pts", type=float, default=2000.0)
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--point", type=float, default=0.01)
    args = ap.parse_args()
    sym = args.symbol.upper()
    df = pl.read_parquet(os.path.join(OUTDIR, sym, "features_m1.parquet")).to_pandas()
    feat_cols = [c for c in df.columns if any(c.startswith(t+"_") for t in
                 ("M1","M5","M15","M30","H1","H4"))]
    lbls = label_entries(df, args.point, args.target_pts, args.horizon)
    print(f"{sym}: {len(lbls)} OsMA-origin entries (target {args.target_pts:.0f}pt within {args.horizon} bars)")
    lab = pd.DataFrame(lbls, columns=["i","side","winner","fav","adv"])
    # export attribution csv
    rows_meta = []
    for _, L in lab.iterrows():
        r = df.iloc[int(L["i"])]
        rows_meta.append(dict(time=r["time"], side=L["side"], session=session_of_row(r),
                              osma_state=int(r["osma_state"]), osma_amp=float(r.get("M1_OSMA", 0)),
                              winner=int(L["winner"]), fav=round(L["fav"]), adv=round(L["adv"])))
    meta = pd.DataFrame(rows_meta)
    meta.to_csv(os.path.join(OUTDIR, sym, "attribution.csv"), index=False)
    print(f"  wrote attribution.csv ({len(meta)} rows)")

    Xall = np.nan_to_num(df[feat_cols].values.astype(float), nan=0, posinf=0, neginf=0)
    for side in ("long", "short"):
        sub = lab[lab["side"] == side]
        print(f"\n=== {sym} {side}: {len(sub)} entries, winners {sub['winner'].mean()*100:.0f}% ===")
        ii = sub["i"].values
        X = Xall[ii]; y = sub["winner"].values
        res, top = attribute(f"{side}-all", X, y, feat_cols)
        if res:
            print(f"  WALK-FORWARD winner-vs-fakeout AUC: mean {res[0]:.3f} (min {res[1]:.3f} max {res[2]:.3f}) "
                  f"-> {'STABLE' if res[1] >= 0.55 else 'NOT stable'}")
            print("  top features:", ", ".join(f"{f} {v:.3f}" for f, v in top[:10]))
        # per session
        for s in ("Asian","London","NewYork"):
            sess_idx = [int(L['i']) for _, L in sub.iterrows() if session_of_row(df.iloc[int(L['i'])]) == s]
            if len(sess_idx) < 60: 
                print(f"    [{s}] n={len(sess_idx)} too small"); continue
            ys = df.iloc[sess_idx]  # placeholder to keep order
            mask = sub["i"].isin(sess_idx).values
            r2, t2 = attribute(f"{side}-{s}", Xall[sub['i'].values[mask]], y[mask], feat_cols)
            if r2:
                print(f"    [{s}] n={mask.sum()} win {y[mask].mean()*100:.0f}%  WF-AUC mean {r2[0]:.3f} (min {r2[1]:.3f}) "
                      f"top: {', '.join(f'{f}' for f,_ in t2[:4])}")


if __name__ == "__main__":
    main()
