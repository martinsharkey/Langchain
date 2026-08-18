"""Tick-level offline replay of BTCUSD PYRAMID_TRAIL exits.

Replays the actual 30-day Dukascopy tick stream for every H1 OsMA-cross entry,
resolves the multi-leg trailing stop tick-by-tick, and sweeps BE/trail/SL/add
so we can pick a config that raises median winner capture above the current 50%.

Inputs: data/qmmp/BTCUSD/ticks_30d.parquet + H1.parquet (for OsMA cross entries)
Outputs: stdout summary + optional JSON for dashboard.
"""
import sys, os, json, statistics
from pathlib import Path
import numpy as np, pandas as pd, polars as pl

ROOT = Path(r'C:\Users\MartinSharkey\Documents\Langchain\langchain')
D = ROOT / 'data' / 'qmmp' / 'BTCUSD'
sys.path.insert(0, str(ROOT))

from src.strategies.indicators import osma as osma_fn

PT = 0.01
FAST, SLOW, SIG = 12, 26, 9


def load():
    tks = pl.read_parquet(D / 'ticks_30d.parquet')
    # tick epoch is real UTC seconds; trim H1 bars to the same window
    tk_epoch = tks['epoch'].to_numpy()
    tk_mid = ((tks['bid'] + tks['ask']) / 2).to_numpy()

    bars = pl.read_parquet(D / 'H1.parquet').to_pandas()
    bars = bars.sort_values('time').reset_index(drop=True)
    # use last 30 days of bars (tick file spans ~30d ending at its last tick)
    tick_end = pd.to_datetime(tk_epoch[-1], unit='s', utc=True)
    tick_start = (tick_end - pd.Timedelta(days=30)).ceil('h')
    bars = bars[bars['time'] >= tick_start].reset_index(drop=True)
    bars['_epoch'] = bars['time'].astype('int64').values // 10**6
    close = bars['close'].astype(float).reset_index(drop=True)
    bar_time = bars['_epoch'].values
    osma = pd.Series(osma_fn(close, FAST, SLOW, SIG).values, index=close.index)
    return tk_epoch, tk_mid, bars, close, bar_time, osma.values


def entries(bar_time, close, osma):
    """Return list of (entry_epoch, entry_price, is_long, exit_epoch guess)."""
    out = []
    for i in range(2, len(osma)):
        prev = osma[i-2:i]
        cur = osma[i]
        if pd.isna(prev).any() or pd.isna(cur):
            continue
        # zero cross
        if prev[0] < 0 and prev[1] >= 0 and cur > 0:
            is_long = True
        elif prev[0] > 0 and prev[1] <= 0 and cur < 0:
            is_long = False
        else:
            continue
        out.append((bar_time[i], float(close[i]), is_long, None))
    return out


def sim_trade(entry_epoch, entry_price, is_long, tk_epoch, tk_mid,
              sl_pts, be_pts, trail_pts, add_pts, be_lock, max_legs=4):
    """Walk ticks from entry_epoch until ~24 H1 bars later or stop.
    Returns dict with mfe_points, exit_points, n_legs, pnl_points, max_adverse.
    """
    idx0 = int(np.searchsorted(tk_epoch, entry_epoch, side='left'))
    idx0 = min(idx0, len(tk_epoch) - 1)
    # 24 H1 bars ~ 86400 seconds; tick data is sparse, cap at 2M ticks
    idx1 = min(len(tk_epoch), idx0 + 2_000_000)
    prices = tk_mid[idx0:idx1]
    sgn = 1.0 if is_long else -1.0

    legs = [{
        'entry': entry_price,
        'sl': entry_price - sgn * sl_pts * PT,
        'be': False,
        'best': entry_price,
        'closed': False,
        'pnl': 0.0,
    }]
    last_add_price = entry_price
    max_adv = 0.0
    mfe = 0.0

    for px in prices:
        adv = max(0.0, sgn * (entry_price - px) / PT)
        if adv > max_adv:
            max_adv = adv
        fav = max(0.0, sgn * (px - entry_price) / PT)
        if fav > mfe:
            mfe = fav
        # update each leg
        for lg in legs:
            if lg['closed']:
                continue
            if is_long:
                if px > lg['best']:
                    lg['best'] = px
            else:
                if px < lg['best']:
                    lg['best'] = px
            prof = sgn * (lg['best'] - lg['entry']) / PT
            if not lg['be'] and prof >= be_pts:
                lg['be'] = True
                lg['sl'] = lg['entry'] + sgn * be_lock * PT
            if lg['be']:
                new_sl = lg['best'] - sgn * trail_pts * PT
                if is_long and new_sl > lg['sl']:
                    lg['sl'] = new_sl
                elif not is_long and new_sl < lg['sl']:
                    lg['sl'] = new_sl
            # stop hit?
            hit = (px <= lg['sl']) if is_long else (px >= lg['sl'])
            if hit:
                lg['closed'] = True
                lg['pnl'] = sgn * (lg['sl'] - lg['entry']) / PT
        # add leg
        any_open = not all(lg['closed'] for lg in legs)
        adv_last = sgn * (px - last_add_price) / PT
        if any_open and len(legs) < max_legs and adv_last >= add_pts:
            prev_entry = legs[-1]['entry']
            legs.append({
                'entry': px,
                'sl': prev_entry,  # prior leg entry = BE
                'be': False,
                'best': px,
                'closed': False,
                'pnl': 0.0,
            })
            last_add_price = px

    last_px = prices[-1] if len(prices) else entry_price
    net = 0.0
    for lg in legs:
        if not lg['closed']:
            lg['pnl'] = sgn * (last_px - lg['entry']) / PT
        net += lg['pnl']

    return {
        'mfe_points': mfe,
        'exit_points': net,
        'n_legs': len(legs),
        'max_adverse': max_adv,
    }


def sweep(tk_epoch, tk_mid, ens, configs):
    """Synchronous sweep. For ~50 entries and ~140 config grid it is fast enough
    and avoids multiprocessing pickling overhead / polars serialization issues."""
    results = []
    for cfg in configs:
        trades = []
        for entry_epoch, entry_price, is_long, _ in ens:
            trades.append(sim_trade(entry_epoch, entry_price, is_long, tk_epoch, tk_mid,
                                    cfg['sl'], cfg['be'], cfg['trail'], cfg['add'],
                                    cfg['be_lock'], cfg.get('max_legs', 4)))
        wins = [t for t in trades if t['exit_points'] > 0]
        losses = [t for t in trades if t['exit_points'] <= 0]
        win_mfe = [t['mfe_points'] for t in wins]
        caps = [t['exit_points'] / t['mfe_points'] for t in wins if t['mfe_points'] > 100]
        net = sum(t['exit_points'] for t in trades)
        result = {
            'cfg': cfg,
            'n': len(trades),
            'win': len(wins),
            'loss': len(losses),
            'net': net,
            'median_mfe': statistics.median(win_mfe) if win_mfe else None,
            'median_capture': statistics.median(caps) if caps else None,
            'mean_capture': statistics.mean(caps) if caps else None,
        }
        results.append(result)
    return results



def main():
    tk_epoch, tk_mid, bars, close, bar_time, osma = load()
    ens = entries(bar_time, close, osma)
    print(f'entries: {len(ens)}')

    # baseline = original pipeline config
    baseline = {'sl': 628348, 'be': 11057, 'trail': 11057, 'add': 11057, 'be_lock': 1105, 'max_legs': 4}
    # tuned = tick-replay proven values now in model.json / config
    tuned = {'sl': 5000, 'be': 5000, 'trail': 5000, 'add': 5000, 'be_lock': 500, 'max_legs': 2}
    # quick sweep around the tuned value
    cfgs = [baseline, tuned]
    for sl in [3000, 5000, 10000]:
        for be in [3000, 5000, 7000]:
            for trail in [3000, 5000, 7000]:
                cfgs.append({
                    'sl': sl, 'be': be, 'trail': trail, 'add': be,
                    'be_lock': max(100, round(be * 0.1)), 'max_legs': 2,
                })

    results = sweep(tk_epoch, tk_mid, ens, cfgs)
    results.sort(key=lambda r: (r['net'], r['median_capture'] or 0), reverse=True)
    print('\nTop by net points:')
    for r in results[:15]:
        print(f"  be={r['cfg']['be']:5d} trail={r['cfg']['trail']:5d} add={r['cfg']['add']:5d} "
              f"sl={r['cfg']['sl']:5d} -> n={r['n']:3d} win={r['win']:3d} net={r['net']:8.0f} "
              f"cap={r['median_capture']:.2%} mean={r['mean_capture']:.2%}")


if __name__ == '__main__':
    main()
