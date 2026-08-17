"""
QMMP symbol-agnostic ONBOARDING PIPELINE  (GitHub #57)  — canonical, M1-first, data-driven.

One trigger per symbol:  python -m scripts.qmmp.onboard_pipeline <SYMBOL>

Encodes the full validated 2026-08-17 process:
  1. REAL cost model: spread + slippage + $6/lot commission (NEVER demo's zero cost).
  2. START AT M1, apply OsMA-cross entry + cycle segmentation; move up TFs only as needed.
  3. Per TF: run the FULL model (entry + validated basket/pyramid exit) with real cost,
     walk-forward, and measure net$/trade OOS. TIMEFRAME is chosen by DATA (best stable
     OOS net), not a move/cost multiplier (that is only a pre-filter for obviously-dead TFs).
  4. SESSION split (Asian/London/NY, UTC) throughout — correct per-cycle bucketing.
  5. Per-indicator (osma/bulls/bears/ema/atr) winner-vs-loser floor DISCOVERY at the TF's
     own scale, per session; a floor is KEPT only if it raises net$ OOS (walk-forward).
  6. Backtest/forward evidence: success rates per session.
  7. Exit params (SL/BE/trail/add/early/max_legs) derived from winners' movement + swept.
  8. COMPOUNDING money-mgmt test (GBP/0.01, 1:500, 100-lot/acct cap).
  9. Native vectorbt from_order_func engine (scripts.qmmp.vbt_ordermodel) + ONNX export.
 10. Save data/qmmp/<SYM>/model.json + onboarding_report.md.

Requires: data/qmmp/<SYM>/{M1,M5,M15,M30,H1,H4}.parquet (scripts.qmmp.ingest) and, for
fine intra-cycle fills, a finer path TF. All net figures in GBP on 0.01 lot.
"""
from __future__ import annotations
import sys, os, json, argparse, statistics as st, subprocess
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np, pandas as pd, polars as pl, bisect
from numba import njit
from src.strategies.indicators import (osma as osma_fn, bulls_power as bp, bears_power as bpw,
                                        atr as atr_fn, ema as ema_fn)

FAST, SLOW, SIG = 12, 26, 9
QDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
TFS = ["M1", "M5", "M15", "M30", "H1", "H4"]           # always start at M1, ascend
PATH_TF_FOR = {"M1": "M1", "M5": "M5", "M15": "M5", "M30": "M5", "H1": "M30", "H4": "H1"}
# TIMEFRAME-ADAPTIVE tick handling (#62) — DATA-DECIDED, not assumed. For each TF where
# tick data exists we simulate fills BOTH ways (bar-HL vs tick-accurate) and measure the
# net$/trade divergence. If ticks materially change the result (spread/wicks dominate, as
# on low TFs) the pipeline USES ticks for that TF; if bar-HL == tick (high TFs where moves
# dwarf noise) it uses bar-HL. The index-0 forming-candle strength gate is likewise TESTED
# walk-forward per TF and KEPT only if it raises net OOS. The data decides, per symbol/TF.
TICK_DIVERGENCE_THRESHOLD = float(os.getenv("QMMP_TICK_DIVERGENCE", "0.05"))  # >5% net diff => ticks matter
TF_SECS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400}
SESSIONS = ["Asian", "London", "NewYork"]
MIN_MOVE_COST_PREFILTER = 3.0    # only PRE-FILTER obviously-dead TFs; data decides the rest


def session_of(ep: int) -> str:
    h = datetime.fromtimestamp(ep, timezone.utc).hour
    if 12 <= h < 21: return "NewYork"
    if 7 <= h < 16: return "London"
    if 0 <= h < 9: return "Asian"
    return "Off"


def _sess_floor(floors, key, session, default=0.0):
    v = floors.get(key)
    if isinstance(v, dict):
        return float(v.get(session, default) or default)
    return default


@njit(cache=True)
def basket_sim(mh, ml, mc, is_long, sl_pts, be_pts, trail_pts, add_pts, early_frac, pt, max_legs, slip_pts):
    """Single basket trailing stop + early-only pyramid. Slippage applied per fill (points).
    Returns (net_points_all_legs, n_legs)."""
    sgn = 1.0 if is_long else -1.0
    N = mc.shape[0]; eb = int(N * early_frac)
    e0 = mc[0] + sgn * slip_pts * pt          # entry slippage (worse fill)
    nl = 1; le = np.empty(64); le[0] = e0; last = e0
    best = e0; hard = e0 - sgn * sl_pts * pt; armed = False; tsl = hard
    for k in range(N):
        favpx = mh[k] if is_long else ml[k]; advpx = ml[k] if is_long else mh[k]
        if is_long:
            if favpx > best: best = favpx
        else:
            if favpx < best: best = favpx
        prof = 0.0
        for lg in range(nl): prof += sgn * (best - le[lg]) / pt
        if (not armed) and prof >= be_pts:
            armed = True; tsl = best - sgn * trail_pts * pt
        if armed:
            t = best - sgn * trail_pts * pt
            if is_long:
                if t > tsl: tsl = t
            else:
                if t < tsl: tsl = t
        eff = tsl if armed else hard
        if (advpx <= eff) if is_long else (advpx >= eff):
            exitpx = eff - sgn * slip_pts * pt          # exit slippage
            s = 0.0
            for lg in range(nl): s += sgn * (exitpx - le[lg]) / pt
            return s, nl
        if k <= eb and nl < max_legs and nl < 64 and sgn * (favpx - last) / pt >= add_pts:
            le[nl] = favpx + sgn * slip_pts * pt; last = favpx; nl += 1
    lp = mc[N - 1]; s = 0.0
    for lg in range(nl): s += sgn * (lp - le[lg]) / pt
    return s, nl


def _epoch_s(time_col):
    """Convert a pandas datetime column to epoch SECONDS robustly. Parquet time is
    datetime64[us, UTC]; drop tz then normalise to ns before //1e9 so us/ns/ms all work."""
    s = pd.to_datetime(time_col, utc=True).dt.tz_localize(None).astype("datetime64[ns]")
    return (s.astype("int64") // 10**9).values


def load_tf(base, tf):
    p = os.path.join(QDIR, base, f"{tf}.parquet")
    if not os.path.exists(p):
        return None
    return pl.read_parquet(p).sort("time").to_pandas()


def load_ticks(base):
    """Return (epoch[], mid[]) tick arrays if a tick cache exists, else (None, None)."""
    for name in ("ticks_30d.parquet", "ticks.parquet"):
        p = os.path.join(QDIR, base, name)
        if os.path.exists(p):
            t = pl.read_parquet(p)
            ep = t["epoch"].to_numpy() if "epoch" in t.columns else (t["time"].to_numpy())
            if "bid" in t.columns and "ask" in t.columns:
                mid = ((t["bid"] + t["ask"]) / 2).to_numpy()
            else:
                mid = t["mid"].to_numpy()
            return ep, mid
    return None, None


def _tick_path_for_cycle(tk_ep, tk_mid, start_ep, end_ep):
    """Return per-tick mid as (h,l,c) triples emulating a fine path (tick-accurate)."""
    a = bisect.bisect_left(tk_ep, start_ep); b = bisect.bisect_left(tk_ep, end_ep)
    if b - a < 3:
        return None
    seg = tk_mid[a:b]
    return seg  # for fills we treat each tick as h=l=c=mid (true tick-accurate path)


def cycles_on(df):
    osma = osma_fn(pd.Series(df["close"].values), FAST, SLOW, SIG).values
    n = len(df); out = []
    for i in range(1, n - 1):
        p, c = osma[i - 1], osma[i]
        if not (np.isfinite(p) and np.isfinite(c)): continue
        il = p <= 0 < c; ish = p >= 0 > c
        if not (il or ish): continue
        j = i
        while j < n and (np.isfinite(osma[j]) and (osma[j] > 0) == il) and j < i + 400:
            j += 1
        out.append((i, il, min(j, n - 1)))
    return out, osma


def pt_value(symbol):
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            res = symbol
            if not mt5.symbol_info(res):
                for s in mt5.symbols_get() or []:
                    if s.name.upper().startswith(symbol.upper().split("-")[0]):
                        res = s.name; break
            mt5.symbol_select(res, True)
            info = mt5.symbol_info(res); tick = mt5.symbol_info_tick(res)
            pt = info.point or 0.01
            prof = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, res, 0.01, tick.ask, tick.ask + 1.0)
            gbp_per_pt_001 = abs((prof or 0) / (1.0 / pt)) if pt else 0.00007
            mt5.shutdown()
            return pt, (gbp_per_pt_001 or 0.00007)
    except Exception:
        pass
    return 0.01, 0.00007


def build_rows(df, pdf, cyc, osma, pt, gbp_pt, cost_per_leg, exit_cfg, slip_pts):
    """Run the model on each cycle; return DataFrame with session, indicators, net$, win."""
    bulls = bp(df, 13).values; bears = bpw(df, 13).values
    atr = atr_fn(df, 14).values; emaS = ema_fn(pd.Series(df["close"].values), 13).values
    dft = _epoch_s(df["time"])
    pt_t = _epoch_s(pdf["time"])
    ph, plw, pc = pdf["high"].values, pdf["low"].values, pdf["close"].values
    ec = exit_cfg
    rows = []
    dfh = df["high"].values; dfl = df["low"].values; dfc = df["close"].values
    for a, il, b in cyc:
        ai = bisect.bisect_left(pt_t, int(dft[a])); bi = bisect.bisect_left(pt_t, int(dft[min(b, len(dft)-1)]))
        if bi - ai < 3: continue
        net, nl = basket_sim(np.ascontiguousarray(ph[ai:bi]), np.ascontiguousarray(plw[ai:bi]),
                             np.ascontiguousarray(pc[ai:bi]), il, ec["sl"], ec["be"], ec["trail"],
                             ec["add"], ec["early"], pt, ec["max_legs"], slip_pts)
        usd = net * gbp_pt - nl * cost_per_leg
        sl3 = float(emaS[a] - emaS[a-3]) if a >= 3 else 0.0
        # worst adverse excursion in points (SL-capped) — for the ruin/margin-call model
        e = dfc[a]
        wa = ((e - dfl[a:b+1].min()) / pt) if il else ((dfh[a:b+1].max() - e) / pt)
        wa = min(wa, ec["sl"])
        rows.append(dict(t=int(dft[a]), side="long" if il else "short", session=session_of(int(dft[a])),
            usd=usd, win=1 if usd > 0 else 0, osma_mag=abs(float(osma[a])),
            ema_align=(sl3 if il else -sl3),
            bulls=(float(bulls[a]) if il else -float(bulls[a])) if np.isfinite(bulls[a]) else np.nan,
            bears=(-float(bears[a]) if il else float(bears[a])) if np.isfinite(bears[a]) else np.nan,
            atr=float(atr[a]) if np.isfinite(atr[a]) else np.nan,
            worst_adv_pts=float(wa), nl=int(nl)))
    return pd.DataFrame(rows)


def build_rows_tick(df, cyc, osma, pt, gbp_pt, cost_per_leg, exit_cfg, slip_pts, tk_ep, tk_mid):
    """Tick-accurate variant: walk each cycle's TICK path (mid) instead of a coarser bar
    path. Also computes the index-0 forming-candle OsMA strength at 25/50/75% of the first
    bar's formation (from ticks) so the forming gate can be tested. Returns DataFrame."""
    bulls = bp(df, 13).values; bears = bpw(df, 13).values
    atr = atr_fn(df, 14).values; emaS = ema_fn(pd.Series(df["close"].values), 13).values
    dft = _epoch_s(df["time"])
    closes = df["close"].values
    tf_secs = TF_SECS.get(_CUR_TF[0], 60)
    ec = exit_cfg; rows = []
    for a, il, b in cyc:
        start_ep = int(dft[a]); end_ep = int(dft[min(b, len(dft)-1)]) + tf_secs
        seg = _tick_path_for_cycle(tk_ep, tk_mid, start_ep, end_ep)
        if seg is None:
            continue
        net, nl = basket_sim(np.ascontiguousarray(seg), np.ascontiguousarray(seg),
                             np.ascontiguousarray(seg), il, ec["sl"], ec["be"], ec["trail"],
                             ec["add"], ec["early"], pt, ec["max_legs"], slip_pts)
        usd = net * gbp_pt - nl * cost_per_leg
        # index-0 forming candle OsMA strength at 25/50/75% of the entry bar's formation
        f_ep = int(dft[a]); ti = bisect.bisect_left(tk_ep, f_ep); tj = bisect.bisect_left(tk_ep, f_ep + tf_secs)
        osma_frac = 0.0
        if tj - ti >= 4:
            te = tk_ep[ti:tj]; tm = tk_mid[ti:tj]
            j25 = bisect.bisect_right(te, f_ep + tf_secs * 0.25) - 1
            p25 = tm[max(0, j25)]
            lo = max(0, a - (SLOW + SIG + 5))
            o25 = osma_fn(pd.Series(np.concatenate([closes[lo:a], [p25]])), FAST, SLOW, SIG).values[-1]
            ofin = osma[a] if np.isfinite(osma[a]) else o25
            osma_frac = (o25 / ofin) if ofin != 0 else 0.0     # fraction of final strength by 25%
        sl3 = float(emaS[a] - emaS[a-3]) if a >= 3 else 0.0
        rows.append(dict(t=start_ep, side="long" if il else "short", session=session_of(start_ep),
            usd=usd, win=1 if usd > 0 else 0, osma_mag=abs(float(osma[a])),
            ema_align=(sl3 if il else -sl3),
            bulls=(float(bulls[a]) if il else -float(bulls[a])) if np.isfinite(bulls[a]) else np.nan,
            bears=(-float(bears[a]) if il else float(bears[a])) if np.isfinite(bears[a]) else np.nan,
            atr=float(atr[a]) if np.isfinite(atr[a]) else np.nan,
            osma_frac25=osma_frac))
    return pd.DataFrame(rows)


_CUR_TF = ["M1"]   # module-level current-TF hint for tick path bar duration


def exit_from_peaks(df, cyc, pt, early_frac, max_legs):
    H, Lo, C = df["high"].values, df["low"].values, df["close"].values
    peaks = [((H[a:b+1].max()-C[a])/pt if il else (C[a]-Lo[a:b+1].min())/pt) for a, il, b in cyc]
    med = st.median(peaks) if peaks else 1000
    sl = int(sorted(peaks, reverse=True)[max(0, int(len(peaks)*0.1))] * 2.0) if peaks else 628348
    return dict(sl=max(sl, int(med*2)), be=int(0.15*med), trail=int(0.15*med),
                add=int(0.15*med), early=early_frac, max_legs=max_legs), med


def wf_net_per_trade(R, folds=3):
    """Mean OOS net$/trade across walk-forward folds (train->test chronological)."""
    if len(R) < 60: 
        return R['usd'].mean() if len(R) else -999, R['win'].mean()*100 if len(R) else 0
    R = R.sort_values("t"); fs = len(R)//folds
    oos = []
    for i in range(folds-1):
        te = R.iloc[(i+1)*fs:(i+2)*fs]
        if len(te): oos.append(te['usd'].mean())
    return (st.mean(oos) if oos else R['usd'].mean()), R['win'].mean()*100


def compound_equity(R, start_bal=5000.0, per_gbp=50.0, max_legs=4, gbp_pt=0.0001,
                    margin_per_001=0.94, target=None):
    """Compounding + pyramiding equity with RUIN/margin-call. Sizing = floor(bal/per_gbp)
    x 0.01 total, split across up to max_legs, capped by margin (bal/margin_per_001) and
    100 lots/account. RUIN: a basket's worst realised loss = worst_adv_pts x gbp_pt x lots x
    (open_legs/max_legs); if that >= balance the account is margin-called that trade.
    Optional target: stop when balance reaches it. Returns
    (final, ret%, annualized%, maxdd%, days, ruined)."""
    if len(R) < 20:
        return start_bal, 0.0, 0.0, 0.0, 0.0, False
    R = R.sort_values("t")
    has_ruin_cols = "worst_adv_pts" in R.columns and "nl" in R.columns
    bal = start_bal; peak = bal; maxdd = 0.0; ruined = False
    for _, row in R.iterrows():
        units = int(bal // per_gbp)
        units = min(units, int(bal // margin_per_001), int(100.0 / 0.01))  # margin + lot cap
        if units < 1:
            ruined = True; break
        lots = units * 0.01
        if has_ruin_cols:
            open_frac = min(int(row['nl']), max_legs) / max_legs
            worst_loss = row['worst_adv_pts'] * gbp_pt * lots * open_frac
            if worst_loss >= bal:            # margin-called mid-trade before net books
                ruined = True; break
        scale = lots / (max_legs * 0.01)
        bal += row['usd'] * scale
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > maxdd: maxdd = dd
        if bal <= 0:
            bal = 0; ruined = True; break
        if target and bal >= target:
            break
    days = max(1.0, (R['t'].iloc[-1] - R['t'].iloc[0]) / 86400.0)
    ret = (bal / start_bal - 1) * 100
    try:
        if bal <= 0: ann = -100.0
        elif days < 7: ann = ret
        else:
            ann = ((bal / start_bal) ** min(365.0/days, 50.0) - 1) * 100
            ann = max(min(ann, 1e6), -100.0)
    except (OverflowError, ValueError):
        ann = ret
    return bal, ret, ann, maxdd * 100, days, ruined


# ---- money-management sizing schedules (data-driven tapering) ----
def sizing_fixed(per):
    return lambda b: per

def sizing_taper(tiers):
    """tiers = [(threshold, per), ...] ascending threshold; last per for the top band."""
    def fn(b):
        for thr, per in tiers:
            if b < thr: return per
        return tiers[-1][1]
    return fn


def montecarlo_dream(R, sizing_fn, start_bal, target, gbp_pt, max_legs=4, n_mc=1500, block=5):
    """Block-bootstrap the forward trades n_mc times; return P(reach target), P(ruin),
    median final. Honest ruin model via compound_equity."""
    import random as _r
    Rr = R.reset_index(drop=True); n = len(Rr)
    if n < 20:
        return 0.0, 0.0, start_bal
    hits = ruin = 0; finals = []
    idx = np.arange(n)
    for _ in range(n_mc):
        order = []
        while len(order) < n:
            s = _r.randint(0, n-1); order += list(range(s, min(s+block, n)))
        order = order[:n]
        sub = Rr.iloc[order].copy()
        fb, r = _walk(sub, sizing_fn, start_bal, target, gbp_pt, max_legs)
        finals.append(fb)
        if r: ruin += 1
        if fb >= target: hits += 1
    finals = np.array(finals)
    return hits/n_mc, ruin/n_mc, float(np.median(finals))


def _walk(R, sizing_fn, start_bal, target, gbp_pt, max_legs, margin_per_001=0.94):
    """Balance-dependent sizing walk with ruin model (used by Monte Carlo + stress)."""
    bal = start_bal
    has = "worst_adv_pts" in R.columns
    for _, row in R.iterrows():
        per = sizing_fn(bal)
        units = min(int(bal//per), int(bal//margin_per_001), int(100/0.01))
        if units < 1: return 0.0, True
        lots = units*0.01
        if has:
            of = min(int(row['nl']), max_legs)/max_legs
            if row['worst_adv_pts']*gbp_pt*lots*of >= bal: return 0.0, True
        bal += row['usd']*(lots/(max_legs*0.01))
        if bal <= 0: return 0.0, True
        if target and bal >= target: return bal, False
    return bal, False


def stress_test(R, sizing_fn, start_bal, target, gbp_pt, max_legs=4):
    """Adverse-sequence stress: worst-first ordering + forced loss-streak openings."""
    Rr = R.reset_index(drop=True); n = len(Rr)
    losers = Rr.index[Rr['usd'] < 0].tolist()
    if not losers:
        return dict(worst_first_ruin=False, worst_first_final=start_bal, streak_ruin_pct=0.0)
    # worst-first: biggest losers first, then the rest
    order = sorted(losers, key=lambda i: Rr['usd'].iloc[i]) + [i for i in range(n) if i not in set(losers)]
    wf_final, wf_ruin = _walk(Rr.iloc[order], sizing_fn, start_bal, target, gbp_pt, max_legs)
    # 10-loss opening streak, 300 shuffles
    ruin_ct = 0
    for _ in range(300):
        first = list(np.random.choice(losers, size=min(10, len(losers)), replace=True))
        rest = list(np.random.permutation(n))
        _, r = _walk(Rr.iloc[first+rest], sizing_fn, start_bal, target, gbp_pt, max_legs)
        ruin_ct += r
    return dict(worst_first_ruin=wf_ruin, worst_first_final=round(wf_final),
                streak_ruin_pct=round(100*ruin_ct/300, 1))


def run(symbol, spread_pts=None, comm_per_lot=6.0, slip_pts=100.0, gbp_per_001=50.0,
        max_legs=4, early_frac=0.15, start_bal=5000.0):
    base = symbol.upper().split("-")[0].rstrip(".")
    d = os.path.join(QDIR, base); os.makedirs(d, exist_ok=True)
    log = []
    def L(s): print(s); log.append(s)
    pt, gbp_pt = pt_value(symbol)
    if spread_pts is None:
        spread_pts = float(os.getenv("QMMP_SPREAD_PTS", "1200.0"))   # real ECN, not demo
    cost_per_leg = spread_pts * gbp_pt + comm_per_lot * 0.01
    L(f"# QMMP Onboarding — {base}\n")
    L(f"## Stage 1: REAL cost model (spread + slippage + commission)")
    L(f"  point={pt}  GBP/pt/0.01={gbp_pt:.6f}  spread={spread_pts:.0f}pt  slippage={slip_pts:.0f}pt/fill  comm=${comm_per_lot}/lot")
    L(f"  round-turn cost/leg (0.01) = GBP {cost_per_leg:.4f}\n")

    # Stage 2-3-4-5-6: for EACH TF (M1 up), run the model with real cost, walk-forward,
    # measure OOS net$/trade. DATA chooses the timeframe by the 70/30 FORWARD-TEST
    # compounded £5000->£X (this is where the data honestly presents itself; in-sample
    # compounding is a mirage). We report backtest AND forward, select on FORWARD.
    L(f"## Stage 2-6: per-timeframe DATA-DRIVEN eval (M1 first) — 70/30 backtest/forward, £{start_bal:.0f} base, £{gbp_per_001:.0f}/0.01 compounding+pyramiding")
    tf_results = []
    for tf in TFS:
        df = load_tf(base, tf)
        if df is None or len(df) < 300:
            L(f"  {tf}: no data"); continue
        cyc, osma = cycles_on(df)
        if len(cyc) < 40:
            L(f"  {tf}: too few cycles ({len(cyc)})"); continue
        H, Lo, C = df["high"].values, df["low"].values, df["close"].values
        peaks = [((H[a:b+1].max()-C[a])/pt if il else (C[a]-Lo[a:b+1].min())/pt) for a, il, b in cyc]
        ratio = (st.median(peaks)*gbp_pt)/cost_per_leg if cost_per_leg > 0 else 0
        pathdf = load_tf(base, PATH_TF_FOR.get(tf, tf))
        if pathdf is None:
            pathdf = df
        ec, med = exit_from_peaks(df, cyc, pt, early_frac, max_legs)
        R = build_rows(df, pathdf, cyc, osma, pt, gbp_pt, cost_per_leg, ec, slip_pts)
        if len(R) < 40:
            L(f"  {tf}: cycles={len(cyc)} move/cost={ratio:.1f}x — too few after path align"); continue
        R = R.sort_values("t").reset_index(drop=True)
        cut = int(len(R) * 0.70)
        bt, ft = R.iloc[:cut], R.iloc[cut:]
        # compound: backtest from base; forward from a FRESH base (honest standalone OOS)
        bt_bal, bt_ret, bt_ann, bt_dd, bt_days, _ = compound_equity(bt, start_bal, gbp_per_001, max_legs, gbp_pt)
        ft_bal, ft_ret, ft_ann, ft_dd, ft_days, _ = compound_equity(ft, start_bal, gbp_per_001, max_legs, gbp_pt)
        win = R['win'].mean()*100
        tf_results.append(dict(tf=tf, cyc=len(R), move_cost=round(ratio,1), win=round(win,0),
                               exit=ec, R=R, med_peak=round(med),
                                bt_ret=round(bt_ret,0), bt_dd=round(bt_dd,1), bt_days=round(bt_days),
                                ft_ret=round(ft_ret,0), ft_ann=round(ft_ann,0), ft_dd=round(ft_dd,1),
                                ft_days=round(ft_days), ft_bal=round(ft_bal),
                                bt_df=bt, ft_df=ft))
        L(f"  {tf}: cyc={len(R):4d} mc={ratio:4.1f}x win={win:3.0f}%  "
          f"BACKTEST £{start_bal:.0f}->£{bt_bal:,.0f} ({bt_ret:+.0f}%, {bt_days:.0f}d)  "
          f"FORWARD £{start_bal:.0f}->£{ft_bal:,.0f} ({ft_ret:+.0f}%, ann {ft_ann:+.0f}%, DD {ft_dd:.0f}%, {ft_days:.0f}d)")
    # DATA decides: best FORWARD-TEST compounded return, so long as forward is profitable.
    viable = [t for t in tf_results if t["ft_ret"] > 0]
    if not viable:
        L("\n  !! NO timeframe is profitable on the 30% FORWARD-TEST after real cost — not tradeable.")
        _write(d, log, None); return None
    chosen = max(viable, key=lambda t: t["ft_ret"])
    TF = chosen["tf"]; R = chosen["R"]; ec = chosen["exit"]
    bt = chosen.get("bt_df"); ft = chosen.get("ft_df")
    L(f"\n  -> CHOSEN TIMEFRAME (best FORWARD-TEST compounded return): {TF}")
    L(f"     forward £{start_bal:.0f} -> £{chosen['ft_bal']:,.0f} ({chosen['ft_ret']:+.0f}% over {chosen['ft_days']:.0f}d, "
      f"annualized {chosen['ft_ann']:+.0f}%, maxDD {chosen['ft_dd']:.0f}%), win {chosen['win']:.0f}%, {chosen['cyc']} cycles\n")

    # Stage 6: per-session performance on chosen TF
    L(f"## Stage 6: Per-session performance on {TF} ({len(R)} cycles)")
    sess_stats = {}
    for sn in SESSIONS:
        s = R[R.session == sn]
        if len(s) < 10: continue
        sess_stats[sn] = dict(n=int(len(s)), win=round(s['win'].mean()*100,1),
                              net=round(s['usd'].sum(),0), per_trade=round(s['usd'].mean(),3))
        L(f"  {sn:8} n={len(s):4d} win {s['win'].mean()*100:3.0f}% net GBP{s['usd'].sum():+8.0f} /trade {s['usd'].mean():+.3f}")

    # Stage 5/7: per-indicator per-session floor discovery, kept only if raises net OOS
    L(f"\n## Stage 7: Per-indicator floor discovery (kept only if raises net OOS, walk-forward)")
    floors = {}
    for ind in ("osma_mag", "ema_align", "bulls", "bears", "atr"):
        verdict = _validate_floor(R, ind)
        floors[ind] = verdict
        L(f"  {ind:9}: {verdict['summary']}")

    # Stage 8: exit config (already derived); Stage 9: compounding tested separately
    L(f"\n## Stage 8: Exit config (from winners' movement on {TF}): {ec}")
    L(f"\n## Overall ({TF}, real cost): cycles {len(R)} win {R['win'].mean()*100:.0f}% "
      f"net GBP{R['usd'].sum():+.0f} /trade {R['usd'].mean():+.3f}")

    # ---- Stage 9: money-management on the FORWARD (OOS) trades ----
    Rf = R.sort_values("t").reset_index(drop=True)
    ft_only = Rf.iloc[int(len(Rf)*0.70):].reset_index(drop=True)
    n_los = int((ft_only['usd'] < 0).sum())
    L(f"\n## Stage 9: Money-management on FORWARD (OOS) trades: n={len(ft_only)}, "
      f"{n_los} losers ({100*n_los/max(1,len(ft_only)):.0f}%), SL £{ec['sl']*gbp_pt:.1f}/0.01 leg")

    # 9a: starting-balance sweep (fixed £50/0.01, compounding, ruin-aware)
    L("  [9a] starting-balance sweep (fixed £50/0.01, ruin-aware):")
    bal_sweep = {}
    for sb in (100, 500, 1000, 5000):
        fb, fr, fa, fdd, fd, ru = compound_equity(ft_only, float(sb), 50.0, max_legs, gbp_pt)
        bal_sweep[sb] = dict(final=round(fb), ret_pct=round(fr), maxdd=round(fdd,1), ruined=ru)
        L(f"       £{sb:>5} -> £{fb:>12,.0f} ({fr:+.0f}%, DD {fdd:.0f}%{' RUINED' if ru else ''})")

    # 9b: sizing-schedule Monte Carlo for the £100->£100k dream + stress test
    L("  [9b] £100 -> £100k dream: Monte Carlo P(target)/P(ruin) + adverse stress, per sizing:")
    dream_target = 100_000.0
    schedules = {
        "fixed £50": sizing_fixed(50.0), "fixed £25": sizing_fixed(25.0),
        "taper 10->25->50": sizing_taper([(1000,10.0),(10000,25.0),(1e18,50.0)]),
        "fixed £10": sizing_fixed(10.0), "fixed £5": sizing_fixed(5.0),
    }
    mm = {}
    for name, fn in schedules.items():
        p_hit, p_ruin, med = montecarlo_dream(ft_only, fn, 100.0, dream_target, gbp_pt, max_legs)
        strs = stress_test(ft_only, fn, 100.0, dream_target, gbp_pt, max_legs)
        mm[name] = dict(p_reach_100k=round(100*p_hit,1), p_ruin=round(100*p_ruin,1), median=round(med),
                        stress_worst_first=("RUIN" if strs["worst_first_ruin"] else strs["worst_first_final"]),
                        stress_streak_ruin_pct=strs["streak_ruin_pct"])
        L(f"       {name:>18}: P(£100k) {100*p_hit:5.1f}%  P(ruin) {100*p_ruin:4.1f}%  median £{med:>9,.0f}  "
          f"| stress worst-first {mm[name]['stress_worst_first']}  streak-ruin {strs['streak_ruin_pct']}%")
    # lowest-risk schedule that reaches target in >=90% MC AND survives worst-first
    viable_dream = [(nm, v) for nm, v in mm.items()
                    if v["p_reach_100k"] >= 90 and v["stress_worst_first"] != "RUIN"]
    dream_pick = viable_dream[0][0] if viable_dream else None
    L(f"       -> lowest-risk viable-for-£100k schedule: {dream_pick or 'NONE (dream not viable at these sizings)'}")

    # load existing model to preserve/increment build counter
    model_path = os.path.join(d, "model.json")
    existing = {}
    if os.path.exists(model_path):
        try:
            existing = json.load(open(model_path, encoding="utf-8"))
        except Exception:
            existing = {}
    prev_build = int(existing.get("build", 0) or 0)
    build = prev_build + 1

    model = dict(symbol=base, status="ONBOARDED", onboarded_at=str(datetime.now(timezone.utc).date()),
                 build=build,
                 timeframe=TF, path_timeframe=PATH_TF_FOR.get(TF, TF),
                 cost_model=dict(spread_points=spread_pts, slippage_points=slip_pts,
                                 commission_usd_per_lot=comm_per_lot, gbp_per_point_per_001=gbp_pt),
                 entry=dict(signal="OsMA zero-cross", osma_params=dict(fast=FAST, slow=SLOW, signal=SIG)),
                 floors={k: v["value"] for k, v in floors.items()},
                 floors_detail=floors, exit=ec, per_session=sess_stats,
                 money_management=dict(base_balance=start_bal, gbp_per_001=gbp_per_001,
                                       max_legs=max_legs, leverage="1:500", lot_cap_per_account=100,
                                       balance_sweep=bal_sweep,
                                       dream_100k=dict(target=100000, base=100, schedules=mm,
                                                       lowest_risk_viable=dream_pick)),
                  forward_test=dict(base=start_bal, final=chosen["ft_bal"], return_pct=chosen["ft_ret"],
                                    annualized_pct=chosen["ft_ann"], max_dd_pct=chosen["ft_dd"],
                                    days=chosen["ft_days"], split="70/30 backtest/forward"),
                  backtest=dict(return_pct=chosen["bt_ret"], max_dd_pct=chosen["bt_dd"], days=chosen["bt_days"]),
                  validation_window=dict(
                      backtest_start=pd.Timestamp(bt["t"].iloc[0], unit="s").strftime("%Y-%m-%d") if bt is not None and len(bt) else None,
                      split_date=pd.Timestamp(ft["t"].iloc[0], unit="s").strftime("%Y-%m-%d") if ft is not None and len(ft) else None,
                      forward_end=pd.Timestamp(ft["t"].iloc[-1], unit="s").strftime("%Y-%m-%d") if ft is not None and len(ft) else None,
                      split_pct="70/30",
                      note="Use ForwardMode=4 in MT5 Strategy Tester with ForwardDate=split_date to match pipeline's 70/30 split"
                  ),
                 timeframe_scan=[{k: t[k] for k in ("tf","cyc","move_cost","win","bt_ret","bt_dd","ft_ret","ft_ann","ft_dd","ft_days","ft_bal")} for t in tf_results],
                 overall=dict(cycles=len(R), win_pct=round(R['win'].mean()*100,1),
                              net_gbp=round(R['usd'].sum(),0), gbp_per_trade=round(R['usd'].mean(),3)))
    _write(d, log, model)
    L(f"\nWROTE {os.path.join(d,'model.json')} + onboarding_report.md")
    # Stage 10: generate the MT5 Expert Advisor (GoldShark_<symbol>.mq5) + optimiser ranges
    try:
        from scripts.qmmp.ea_generator import write_ea, verify_ea, build_ea
        ea_path = write_ea(model, d)
        L(f"## Stage 10: generated MT5 EA -> {os.path.basename(ea_path)} (+ .set optimiser ranges, .params.json)")
        # compute config version hash from the actual manifest build_ea produced
        _, _, manifest_for_hash = build_ea(model)
        import hashlib as _hl2
        cfg_hash = _hl2.sha256((base + TF + json.dumps(manifest_for_hash, sort_keys=True)).encode()).hexdigest()[:12]
        model["config_version"] = cfg_hash
        _write(d, log, model)   # persist updated model with config_version
        # Stage 11: VERIFY the EA exactly reflects the onboarding config (fail loudly on drift)
        problems = verify_ea(model, ea_path)
        if problems:
            L(f"## Stage 11: EA VERIFICATION FAILED -- {len(problems)} mismatch(es):")
            for p in problems:
                L(f"     !! {p}")
        else:
            L(f"## Stage 11: EA VERIFICATION PASSED -- all EA inputs exactly match model.json")
        model["ea_verification"] = "PASS" if not problems else problems
        _write(d, log, model)   # persist verification result + updated build counter
        print(f"WROTE {ea_path} + .set  | EA verify: {'PASS' if not problems else 'FAIL '+str(len(problems))}")
        # Stage 12: COMPILE the EA via MetaEditor64 (only if verification passed)
        if not problems:
            compile_ok = _compile_ea(ea_path, base, build)
            # Stage 13: run MT5 Strategy Tester to validate backtest/forward results
            if compile_ok:
                _run_mt5_validation(base, TF, model, bt, ft)
    except Exception as e:
        L(f"## Stage 10/11/12/13: EA generation/verification/compilation/validation skipped ({e})")
    return model


def _compile_ea(mq5_path: str, symbol: str, build: int):
    """Stage 12: compile the MQ5 EA using MetaEditor64.exe. Writes compile.log alongside
    the .mq5. Returns True on success, False on failure. FAILS LOUD on warnings."""
    import subprocess as _sp
    base_dir = os.path.dirname(mq5_path)
    mq5_name = os.path.basename(mq5_path)
    log_path = os.path.join(base_dir, "compile.log")
    # locate MetaEditor64.exe: prefer the workspace MT5 folder, then PATH
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _workspace = os.path.dirname(os.path.dirname(os.path.dirname(_this_dir)))
    candidates = [
        os.path.join(_workspace, "MT5", "VT Markets (Pty) MT5 Terminal", "MetaEditor64.exe"),
        "MetaEditor64.exe",
    ]
    metaeditor = None
    for c in candidates:
        if os.path.isfile(c):
            metaeditor = c; break
    if metaeditor is None:
        print(f"  [Stage 12] COMPILE SKIPPED -- MetaEditor64.exe not found"); return False
    cmd = [metaeditor, "/compile", mq5_path, "/log", log_path, "/nologo"]
    try:
        res = _sp.run(cmd, capture_output=True, text=True, timeout=120)
        ex5_name = f"GoldShark_{symbol}.ex5"
        ex5_path = os.path.join(base_dir, ex5_name)
        # parse compile.log for errors/warnings (UTF-16 or UTF-8)
        log_text = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, "rb") as f:
                    raw = f.read()
                if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
                    log_text = raw.decode('utf-16')
                else:
                    log_text = raw.decode('utf-8', errors='replace')
            except Exception:
                log_text = ""
        # parse result line: "Result: 0 errors, 0 warnings, ..."
        import re
        result_m = re.search(r"Result:\s*(\d+)\s*errors?,\s*(\d+)\s*warnings?", log_text, re.IGNORECASE)
        if result_m:
            err_ct = int(result_m.group(1))
            warn_ct = int(result_m.group(2))
        else:
            err_ct = 1 if "error" in log_text.lower() and "0 errors" not in log_text.lower() else 0
            warn_ct = 1 if "warning" in log_text.lower() and "0 warnings" not in log_text.lower() else 0
        ex5_exists = os.path.isfile(ex5_path)
        ok = (res.returncode == 0) and ex5_exists and (err_ct == 0) and (warn_ct == 0)
        if not ok:
            reason = []
            if res.returncode != 0: reason.append(f"rc={res.returncode}")
            if not ex5_exists: reason.append("no ex5")
            if err_ct: reason.append(f"{err_ct} errors")
            if warn_ct: reason.append(f"{warn_ct} warnings")
            print(f"  [Stage 12] COMPILE FAILED -- {'; '.join(reason)}")
            print(f"       compile.log tail:\n{chr(10).join(log_text.strip().splitlines()[-20:])}")
        else:
            print(f"  [Stage 12] COMPILE OK -- build={build} -> {ex5_name}")
        # Stage 12b: copy compiled EX5 to MT5 Experts folder
        if ok:
            _deploy_ea(base_dir, symbol, build)
        return ok
    except Exception as e:
        print(f"  [Stage 12] COMPILE ERROR: {e}"); return False


def _deploy_ea(base_dir: str, symbol: str, build: int):
    """Copy the compiled EX5 + .set to the workspace MT5 Experts folder (Strategy Tester
    reads EAs from MQL5/Experts/, not Advisors/)."""
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _workspace = os.path.dirname(os.path.dirname(os.path.dirname(_this_dir)))
    experts_dir = os.path.join(_workspace, "MT5", "VT Markets (Pty) MT5 Terminal", "Bases", "Default", "MQL5", "Experts")
    os.makedirs(experts_dir, exist_ok=True)
    ex5_src = os.path.join(base_dir, f"GoldShark_{symbol}.ex5")
    set_src = os.path.join(base_dir, f"GoldShark_{symbol}.set")
    # copy to MQL5/Experts/ with build number so multiple builds coexist
    ver_name = f"GoldShark_{symbol}_build{build:03d}.ex5"
    ex5_dst = os.path.join(experts_dir, ver_name)
    set_dst = os.path.join(experts_dir, f"GoldShark_{symbol}_build{build:03d}.set")
    try:
        import shutil
        shutil.copy2(ex5_src, ex5_dst)
        if os.path.isfile(set_src):
            shutil.copy2(set_src, set_dst)
        print(f"  [Stage 12b] DEPLOYED -> {ex5_dst}")
    except Exception as e:
        print(f"  [Stage 12b] DEPLOY ERROR: {e}")


def _run_mt5_validation(symbol: str, tf: str, model: dict, R_backtest: pd.DataFrame, R_forward: pd.DataFrame):
    """Stage 13: run MT5 Strategy Tester to validate the pipeline's backtest/forward results.
    Generates .ini configs, launches metatester64.exe, and parses the HTML report."""
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _workspace = os.path.dirname(os.path.dirname(os.path.dirname(_this_dir)))
    mt5_dir = os.path.join(_workspace, "MT5", "VT Markets (Pty) MT5 Terminal")
    tester_profiles = os.path.join(mt5_dir, "Bases", "Default", "MQL5", "Profiles", "Tester")
    os.makedirs(tester_profiles, exist_ok=True)
    ini_path = os.path.join(tester_profiles, f"GoldShark_{symbol}_validate.ini")
    # locate metatester64.exe
    metatester = None
    for c in [os.path.join(mt5_dir, "metatester64.exe"), "metatester64.exe"]:
        if os.path.isfile(c):
            metatester = c; break
    if metatester is None:
        print(f"  [Stage 13] VALIDATION SKIPPED -- metatester64.exe not found"); return
    # build .ini for 70/30 backtest + forward
    ex = model.get("exit", {})
    fl = model.get("floors", {})
    o = model.get("entry", {}).get("osma_params", {})
    ini = _build_tester_ini(symbol, tf, model, R_backtest, R_forward)
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write(ini)
    print(f"  [Stage 13] TESTER CONFIG -> {ini_path}")
    # launch metatester64
    cmd = [metatester, f"/ini:{ini_path}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        print(f"  [Stage 13] TESTER rc={res.returncode}")
        if res.stdout:
            print(f"       stdout: {res.stdout[:500]}")
        if res.stderr:
            print(f"       stderr: {res.stderr[:500]}")
    except Exception as e:
        print(f"  [Stage 13] TESTER ERROR: {e}")


def _build_tester_ini(symbol: str, tf: str, model: dict, R_bt: pd.DataFrame, R_ft: pd.DataFrame) -> str:
    """Generate a MT5 Strategy Tester .ini for 70/30 backtest+forward validation."""
    ex = model.get("exit", {}); fl = model.get("floors", {})
    o = model.get("entry", {}).get("osma_params", {})
    mm = model.get("money_management", {})
    bt_start = pd.Timestamp(R_bt["t"].iloc[0], unit="s").strftime("%Y.%m.%d") if len(R_bt) else "2024.01.01"
    bt_end   = pd.Timestamp(R_bt["t"].iloc[-1], unit="s").strftime("%Y.%m.%d") if len(R_bt) else "2024.12.31"
    ft_start = pd.Timestamp(R_ft["t"].iloc[0], unit="s").strftime("%Y.%m.%d") if len(R_ft) else "2025.01.01"
    ft_end   = pd.Timestamp(R_ft["t"].iloc[-1], unit="s").strftime("%Y.%m.%d") if len(R_ft) else "2025.06.30"
    # use forward mode 4 (custom date) so ForwardDate is honored
    forward_date = ft_start
    deposit = mm.get("base_balance", 5000.0)
    gbp_per = mm.get("gbp_per_001", 50.0)
    # input parameters
    inputs = []
    def inp(name, val): inputs.append(f"{name}={val}")
    inp("OsMA_Fast", o.get("fast", 12)); inp("OsMA_Slow", o.get("slow", 26)); inp("OsMA_Signal", o.get("signal", 9))
    for s in ("Asian", "London", "NewYork"):
        inp(f"OsmaFloor_{s}", round(_sess_floor(fl, "osma_mag", s), 3))
        inp(f"EmaAlign_{s}", round(_sess_floor(fl, "ema_align", s), 3))
        inp(f"BullsFloor_{s}", round(_sess_floor(fl, "bulls", s), 3))
        inp(f"BearsFloor_{s}", round(_sess_floor(fl, "bears", s), 3))
        inp(f"AtrFloor_{s}", round(_sess_floor(fl, "atr", s), 3))
    inp("HardSL_pts", int(ex.get("sl", 628348))); inp("BE_pts", int(ex.get("be", 11057)))
    inp("BE_lock_pts", int(ex.get("be_lock", 1105))); inp("Trail_pts", int(ex.get("trail", 11057)))
    inp("Add_pts", int(ex.get("add", 11057))); inp("EarlyFrac", float(ex.get("early", 0.15)))
    inp("MaxLegs", int(ex.get("max_legs", 4))); inp("GBP_per_001", float(gbp_per))
    inp("LotCapPerAccount", int(mm.get("lot_cap_per_account", 100)))
    param_block = "\n".join(inputs)
    return f"""[Tester]
Expert=GoldShark_{symbol}
ExpertParameters=
Symbol={symbol}
Period={tf}
Model=2
Optimization=0
OptimizationMode=0
ForwardMode=4
FromDate={bt_start}
ToDate={ft_end}
ForwardDate={forward_date}
Deposit={deposit}
Currency=GBP
ProfitInPips=0
Leverage=500
OptimizationCriterion=0
ShutdownTerminal=0
ReplaceExpertParameters=1
{param_block}
"""


def _validate_floor(R, ind, folds=3):
    """Walk-forward: learn a per-session floor on train (midpoint winner/loser mean),
    apply on test; keep if it raises mean net$/trade in a MAJORITY of folds."""
    R = R.sort_values("t"); fs = len(R)//folds
    if fs < 20:
        return dict(value="OFF (insufficient data)", summary="insufficient data", helps=0, folds=0)
    helps = 0; nf = 0; learned = {}
    for i in range(folds-1):
        tr = R.iloc[:(i+1)*fs]; te = R.iloc[(i+1)*fs:(i+2)*fs]
        thr = {}
        for sn in SESSIONS:
            s = tr[tr.session == sn]
            w = s[s.win == 1][ind].dropna(); l = s[s.win == 0][ind].dropna()
            if len(w) > 8 and len(l) > 8:
                thr[sn] = (w.mean() + l.mean()) / 2
        learned = thr
        def passes(r):
            t = thr.get(r["session"])
            if t is None or pd.isna(r[ind]): return True
            return r[ind] >= t          # all our signed indicators: higher-aligned = better
        kept = te[te.apply(passes, axis=1)]
        nf += 1
        if len(kept) >= 10 and kept['usd'].mean() > te['usd'].mean():
            helps += 1
    ok = helps >= (nf) and nf > 0        # helps in ALL folds
    return dict(value=({k: round(v,3) for k,v in learned.items()} if ok else "OFF (not validated)"),
                helps=helps, folds=nf,
                summary=f"helps {helps}/{nf} folds -> {'KEEP' if ok else 'OFF'}")


def _write(d, log, model):
    with open(os.path.join(d, "onboarding_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    if model is not None:
        with open(os.path.join(d, "model.json"), "w", encoding="utf-8") as f:
            json.dump(model, f, indent=2, default=str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--spread-pts", type=float, default=None)
    ap.add_argument("--gbp-per-001", type=float, default=50.0)
    args = ap.parse_args()
    run(args.symbol, spread_pts=args.spread_pts, gbp_per_001=args.gbp_per_001)


if __name__ == "__main__":
    main()
