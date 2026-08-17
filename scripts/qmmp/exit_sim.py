"""Tick-accurate per-leg PYRAMID_TRAIL exit simulator for BTCUSD (Numba core).

For each OsMA-cross entry, walk the ACTUAL TICK STREAM from entry to cycle end and
resolve the multi-leg exit tick-by-tick (wick-safe — no bar-OHLC guessing):
  * broker SL at entry (leg 1 = sl_pts; new legs' SL = previous leg's break-even price);
  * BE lock at +be_pts (move SL to entry + small lock);
  * trailing: once BE armed, ratchet SL to (best - trail_pts), never loosen;
  * scale-in: add a leg every +add_pts of favourable travel beyond the last leg, while
    still open; each new leg's SL = the previous leg's entry (net risk capped); no cap.
Returns per-entry: net points (sum of all legs), n_legs, max adverse excursion (risk).

Walk-forward grid sweep over (sl, be, trail, add), optimizing BOTH net points AND a
risk-adjusted metric (net / max-adverse), picking the config strong on both and stable
across chronological folds. Uses cached Dukascopy 30d ticks.
"""
import sys, os, itertools
sys.path.insert(0, r'C:\Users\MartinSharkey\Documents\Langchain\langchain')
import numpy as np, pandas as pd, polars as pl, bisect
from numba import njit
from src.strategies.indicators import osma as osma_fn
FAST, SLOW, SIG = 12, 26, 9
D = r'C:\Users\MartinSharkey\Documents\Langchain\langchain\data\qmmp\BTCUSD'
PT = 0.01


@njit(cache=True)
def sim_ticks(prices, is_long, sl_pts, be_pts, trail_pts, add_pts, be_lock, pt, max_legs):
    """Walk a single entry's tick price path; return (net_points, n_legs, max_adverse)."""
    sgn = 1.0 if is_long else -1.0
    entry = prices[0]
    # leg arrays
    cap = 64
    leg_entry = np.empty(cap); leg_sl = np.empty(cap); leg_be = np.zeros(cap, dtype=np.bool_)
    leg_best = np.empty(cap); leg_closed = np.zeros(cap, dtype=np.bool_); leg_pnl = np.zeros(cap)
    nl = 1
    leg_entry[0] = entry
    leg_sl[0] = entry - sgn * sl_pts * pt
    leg_best[0] = entry
    last_off = entry
    max_adv = 0.0
    for idx in range(prices.shape[0]):
        px = prices[idx]
        # track max adverse (in points, vs original entry)
        adv = sgn * (entry - px) / pt
        if adv > max_adv:
            max_adv = adv
        for lg in range(nl):
            if leg_closed[lg]:
                continue
            # update best (favourable extreme) for this leg
            fav_px = px
            if is_long:
                if fav_px > leg_best[lg]:
                    leg_best[lg] = fav_px
            else:
                if fav_px < leg_best[lg]:
                    leg_best[lg] = fav_px
            leg_prof = sgn * (leg_best[lg] - leg_entry[lg]) / pt
            if (not leg_be[lg]) and leg_prof >= be_pts:
                leg_be[lg] = True
                leg_sl[lg] = leg_entry[lg] + sgn * be_lock * pt
            if leg_be[lg]:
                t = leg_best[lg] - sgn * trail_pts * pt
                if is_long:
                    if t > leg_sl[lg]:
                        leg_sl[lg] = t
                else:
                    if t < leg_sl[lg]:
                        leg_sl[lg] = t
            # stop hit?
            hit = (px <= leg_sl[lg]) if is_long else (px >= leg_sl[lg])
            if hit:
                leg_closed[lg] = True
                leg_pnl[lg] = sgn * (leg_sl[lg] - leg_entry[lg]) / pt
        # add a new leg?
        any_open = False
        for lg in range(nl):
            if not leg_closed[lg]:
                any_open = True
                break
        adv_from_last = sgn * (px - last_off) / pt
        if any_open and (max_legs == 0 or nl < max_legs) and adv_from_last >= add_pts and nl < cap:
            prev = nl - 1
            leg_entry[nl] = px
            leg_sl[nl] = leg_entry[prev]        # new leg SL = previous leg entry (BE)
            leg_be[nl] = False
            leg_best[nl] = px
            leg_closed[nl] = False
            leg_pnl[nl] = 0.0
            last_off = px
            nl += 1
    # close any still-open legs at last tick
    last_px = prices[prices.shape[0] - 1]
    net = 0.0
    for lg in range(nl):
        if not leg_closed[lg]:
            leg_pnl[lg] = sgn * (last_px - leg_entry[lg]) / pt
        net += leg_pnl[lg]
    return net, nl, max_adv


def load():
    tks = pl.read_parquet(os.path.join(D, "ticks_30d.parquet"))
    tk_epoch = tks["epoch"].to_numpy(); tk_mid = ((tks["bid"]+tks["ask"])/2).to_numpy()
    tdf = pd.DataFrame({"epoch": tk_epoch, "mid": tk_mid})
    tdf["minute"] = (tdf["epoch"]//60*60).astype(np.int64)
    g = tdf.groupby("minute")["mid"]
    bars = pd.DataFrame({"close": g.last()}).reset_index().sort_values("minute").reset_index(drop=True)
    close = pd.Series(bars["close"].values)
    osma = osma_fn(close, FAST, SLOW, SIG).values
    bar_epoch = bars["minute"].values
    return tk_epoch, tk_mid, osma, bar_epoch, close.values


def build_entries(early_frac=None):
    """Return list of (start_epoch, tick_price_path, is_long).
    If early_frac is set, keep ONLY 'early-strong' entries: OsMA at 25% of the forming
    entry candle >= early_frac * final cross magnitude (the validated entry filter)."""
    tk_epoch, tk_mid, osma, bar_epoch, close = load()
    n = len(close)
    entries = []   # (start_epoch, end_epoch, is_long, keep)
    for i in range(SLOW+SIG+5, n-2):
        prev, cur = osma[i-1], osma[i]
        if not (np.isfinite(prev) and np.isfinite(cur)): continue
        il = prev <= 0 < cur; ish = prev >= 0 > cur
        if not (il or ish): continue
        f = i+1
        if f >= n-1: continue
        j = f
        while j < n and (np.isfinite(osma[j]) and (osma[j] > 0) == il) and j < f+240:
            j += 1
        keep = True
        if early_frac is not None:
            # OsMA at 25% (15s) of the forming entry candle from ticks
            start = bar_epoch[f]
            a0 = bisect.bisect_left(tk_epoch, start); b0 = bisect.bisect_left(tk_epoch, start+60)
            if b0 - a0 < 4:
                keep = False
            else:
                te = tk_epoch[a0:b0]; tm = tk_mid[a0:b0]
                jj = bisect.bisect_right(te, start+15) - 1
                p25 = tm[max(0, jj)]
                lo = max(0, f-(SLOW+SIG+5))
                o25 = osma_fn(pd.Series(np.concatenate([close[lo:f], [p25]])), FAST, SLOW, SIG).values[-1]
                ofin = osma[f] if np.isfinite(osma[f]) else o25
                sgn = 1 if il else -1
                keep = (sgn*o25) >= (sgn*ofin*early_frac)
        entries.append((bar_epoch[f], bar_epoch[min(j, n-1)]+60, il, keep))
    out = []
    for s, e, il, keep in entries:
        if not keep: continue
        a = bisect.bisect_left(tk_epoch, s); b = bisect.bisect_left(tk_epoch, e)
        if b - a >= 5:
            out.append((s, np.ascontiguousarray(tk_mid[a:b]), il))
    return out


def evaluate(entries, sl, be, trail, add, be_lock=200.0):
    nets = np.empty(len(entries)); advs = np.empty(len(entries)); legs = np.empty(len(entries))
    for k, (s, px, il) in enumerate(entries):
        net, nl, madv = sim_ticks(px, il, sl, be, trail, add, be_lock, PT, 0)
        nets[k] = net; advs[k] = madv; legs[k] = nl
    total = nets.sum()
    win = (nets > 0).mean()*100
    pyr = (legs > 1).mean()*100
    # risk-adjusted: total net / (mean max-adverse) — reward profit per unit of risk taken
    ra = total / (advs.mean() + 1e-9)
    return dict(net=total, win=win, pyr=pyr, ra=ra, avg_adv=advs.mean(), n=len(entries))


def run_wf(entries, tag):
    entries = sorted(entries, key=lambda x: x[0])
    _ = sim_ticks(entries[0][1], entries[0][2], 6000, 400, 200, 2500, 200.0, PT, 0)
    SL=(2000,3000,4000,6000); BE=(400,600,800,1200); TRAIL=(200,300,400,600); ADD=(1000,1500,2500)
    folds=3; fs=len(entries)//folds
    F=[entries[:fs], entries[fs:2*fs], entries[2*fs:]]
    print(f"\n########## {tag}: {len(entries)} entries "
          f"(long {sum(e[2] for e in entries)} / short {sum(not e[2] for e in entries)}) ##########")
    for i in range(folds-1):
        tr, te = F[i], F[i+1]
        grid=[]
        for sl,be,trail,add in itertools.product(SL,BE,TRAIL,ADD):
            if trail>be: continue
            r=evaluate(tr,sl,be,trail,add); r["p"]=(sl,be,trail,add); grid.append(r)
        pool=[r for r in grid if r["net"]>0] or grid
        by_net={id(r):rk for rk,r in enumerate(sorted(pool,key=lambda x:-x["net"]))}
        by_ra ={id(r):rk for rk,r in enumerate(sorted(pool,key=lambda x:-x["ra"]))}
        stable=min(pool, key=lambda r: by_net[id(r)]+by_ra[id(r)])
        te_r=evaluate(te,*stable["p"])
        print(f"  FOLD {i+1}->{i+2} pick sl={stable['p'][0]} be={stable['p'][1]} trail={stable['p'][2]} add={stable['p'][3]}")
        print(f"     TRAIN net {stable['net']:+.0f} win {stable['win']:.0f}% ra {stable['ra']:+.1f}"
              f"  |  TEST net {te_r['net']:+.0f} win {te_r['win']:.0f}% ra {te_r['ra']:+.1f} "
              f"avg/trade {te_r['net']/te_r['n']:+.0f}")


def main():
    unfiltered = build_entries()
    run_wf(unfiltered, "UNFILTERED (all OsMA crosses)")
    for frac in (0.5, 0.6, 0.7):
        filt = build_entries(early_frac=frac)
        run_wf(filt, f"EARLY-STRONG FILTER frac={frac}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
