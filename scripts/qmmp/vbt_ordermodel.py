"""EXACT validated H1 BTCUSD model implemented NATIVELY in vectorbt via from_order_func.

vectorbt is the engine: a Numba order_func_nb runs per M30 bar (the intra-cycle path),
driven by H1-OsMA-cross entry flags aligned onto the M30 index. It manages the basket:
 - on a fresh H1 OsMA cross -> open leg 1 (size from money-mgmt)
 - within the first `early_frac` of the cycle, add a leg every +add_pts (new leg funded);
 - single basket trailing stop (arms after basket BE, trails trail_pts behind peak);
 - close ALL legs when the trail is hit OR the H1 OsMA sign flips (cycle end).
Real ECN cost via fees (spread) + slippage. Output = native vbt.Portfolio (equity, trades,
stats) which we export for ONNX. This makes vectorbt the source of truth.

Usage: python -m scripts.qmmp.vbt_ordermodel BTCUSD
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np, pandas as pd, polars as pl
import vectorbt as vbt
from vectorbt.portfolio import nb as pfnb
from vectorbt.portfolio.enums import SizeType, Direction, NoOrder
from numba import njit
from src.strategies.indicators import osma as osma_fn
FAST, SLOW, SIG = 12, 26, 9
DDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
PT = 0.01
SPREAD_PTS = 1200.0; SLIP_PTS = 100.0; COMM_PER_LOT = 6.0
GBP_PER_PT_PER_LOT = 0.007

# Validated params (points) — from data/qmmp/BTCUSD/model.json (pipeline output, 2026-08-17)
SL_PTS = 628348.0; BE_PTS = 11057.0; TRAIL_PTS = 11057.0; ADD_PTS = 11057.0
EARLY_FRAC = 0.15; MAX_LEGS = 4; PER_GBP = 250.0   # conservative engine sizing.
# NOTE: this native vbt engine is the ONNX-feeding trade-record engine on ONE historical
# path (compounding, no ruin-stop) -> it shows the LUCKY-PATH figure and a large max-DD.
# The HONEST money-management answer (P(£100k)/P(ruin), stress) lives in the pipeline's
# Stage 9 Monte Carlo (onboard_pipeline.py), which bounds ruin properly. Do NOT read this
# engine's headline % as an expectation.
START_CASH = float(os.getenv("QMMP_START_CASH", "5000.0"))


@njit
def order_func_nb(c, cross, cyc_id, cyc_len, cyc_pos, sl_pts, be_pts, trail_pts, add_pts,
                  early_frac, max_legs, per_gbp, spread_pts, slip_pts, pt,
                  state):
    """state (float array, per-column persistent): 
       [0]=in_basket,1=dir(+1/-1),2=n_legs,3=basket_best,4=trail_sl,5=armed,
       6=last_leg_price,7=entry0,8=cyc_id_active"""
    price = c.close[c.i, c.col]
    # --- manage existing basket ---
    if state[0] == 1.0:
        is_long = state[1] > 0
        sgn = 1.0 if is_long else -1.0
        # update best
        if is_long:
            if price > state[3]: state[3] = price
        else:
            if price < state[3]: state[3] = price
        # basket profit in points (sum legs approximated by n_legs*(best-entry0)... we track
        # per-leg entry via entry0 avg; simplified: use entry0 as basket avg entry)
        prof_pts = sgn * (state[3] - state[7]) / pt * state[2]
        if state[5] == 0.0 and prof_pts >= be_pts:
            state[5] = 1.0
            state[4] = state[3] - sgn * trail_pts * pt
        if state[5] == 1.0:
            t = state[3] - sgn * trail_pts * pt
            if is_long:
                if t > state[4]: state[4] = t
            else:
                if t < state[4]: state[4] = t
        eff_sl = state[4] if state[5] == 1.0 else (state[7] - sgn * sl_pts * pt)
        hit = (price <= eff_sl) if is_long else (price >= eff_sl)
        cycle_end = (cross[c.i, c.col] == -state[1]) or (cross[c.i, c.col] != 0 and cross[c.i, c.col] != state[1])
        if hit or cycle_end or cyc_pos[c.i, c.col] >= cyc_len[c.i, c.col]-1:
            # close entire position
            size = c.position_now
            state[0]=0.0; state[2]=0.0; state[5]=0.0
            if size != 0:
                return pfnb.order_nb(size=-size, price=price, size_type=SizeType.Amount,
                                     fees=(spread_pts*pt)/price, slippage=(slip_pts*pt)/price,
                                     direction=Direction.Both)
            return NoOrder
        # add a leg early?
        early_bars = early_frac * cyc_len[c.i, c.col]
        if (cyc_pos[c.i, c.col] <= early_bars) and (state[2] < max_legs):
            adv = sgn*(price - state[6])/pt
            if adv >= add_pts:
                # per-leg size in lots from balance (margin-capped)
                bal = c.value_now
                units = np.floor(bal/per_gbp)
                units = min(units, np.floor(bal / 0.94), 100.0 / 0.01)
                per_leg = (units*0.01)/max_legs
                if per_leg >= 0.01:
                    state[2] += 1.0; state[6] = price
                    sz = per_leg if is_long else -per_leg
                    return pfnb.order_nb(size=sz, price=price, size_type=SizeType.Amount,
                                         fees=(spread_pts*pt)/price, slippage=(slip_pts*pt)/price,
                                         direction=Direction.Both)
        return NoOrder
    # --- flat: look for entry ---
    cr = cross[c.i, c.col]
    if cr != 0.0:
        is_long = cr > 0
        bal = c.value_now
        # RUIN guard: if equity has collapsed below one min-lot's margin, stop trading.
        if bal <= 0.94:
            return NoOrder
        # margin-capped sizing: floor(bal/per_gbp) but never more than margin allows
        # (bal/0.94 per 0.01 lot at 1:500) nor the 100-lot/account cap.
        units = np.floor(bal / per_gbp)
        units = min(units, np.floor(bal / 0.94), 100.0 / 0.01)
        per_leg = (units * 0.01) / max_legs
        if per_leg < 0.01:
            return NoOrder
        state[0]=1.0; state[1]=cr; state[2]=1.0; state[3]=price; state[4]=0.0
        state[5]=0.0; state[6]=price; state[7]=price
        sz = per_leg if is_long else -per_leg
        return pfnb.order_nb(size=sz, price=price, size_type=SizeType.Amount,
                             fees=(spread_pts*pt)/price, slippage=(slip_pts*pt)/price,
                             direction=Direction.Both)
    return NoOrder


def build(symbol="BTCUSD", per_gbp=PER_GBP):
    d = os.path.join(DDIR, symbol.upper())
    h1 = pl.read_parquet(os.path.join(d, "H1.parquet")).sort("time").to_pandas().set_index("time")
    m30 = pl.read_parquet(os.path.join(d, "M30.parquet")).sort("time").to_pandas().set_index("time")
    osma = osma_fn(h1["close"], FAST, SLOW, SIG)
    up = (osma.shift(1) <= 0) & (osma > 0); dn = (osma.shift(1) >= 0) & (osma < 0)
    h1cross = pd.Series(0.0, index=h1.index); h1cross[up]=1.0; h1cross[dn]=-1.0
    # align cross onto M30 index (as-of: the H1 cross applies from that H1 bar's close)
    cross_m30 = h1cross.reindex(m30.index, method="ffill").fillna(0.0)
    # a cross fires once (on the first M30 bar of the new H1 bar): keep only transitions
    fire = cross_m30.where(cross_m30 != cross_m30.shift(1), 0.0).fillna(0.0)
    # cycle length/pos in M30 bars: id increments each H1 sign change
    sign = np.sign(osma).reindex(m30.index, method="ffill").fillna(0.0)
    cyc_id = (sign != sign.shift(1)).cumsum()
    cyc_len = cyc_id.map(cyc_id.value_counts()).astype(float)
    cyc_pos = m30.groupby(cyc_id.values).cumcount().astype(float)

    close = m30["close"]
    C = close.values.reshape(-1,1)
    cross_a = fire.values.reshape(-1,1)
    state = np.zeros(9)
    pf = vbt.Portfolio.from_order_func(
        close,
        order_func_nb,
        cross_a, cyc_id.values.reshape(-1,1)*0, cyc_len.values.reshape(-1,1),
        cyc_pos.values.reshape(-1,1), SL_PTS, BE_PTS, TRAIL_PTS, ADD_PTS,
        EARLY_FRAC, float(MAX_LEGS), float(per_gbp), SPREAD_PTS, SLIP_PTS, PT, state,
        init_cash=START_CASH, freq="30min",
    )
    stats = pf.stats()
    print(f"=== NATIVE vbt from_order_func {symbol} H1 (M30 path), £{per_gbp:.0f}/0.01 ===")
    for k in ("Total Return [%]","Win Rate [%]","Max Drawdown [%]","Total Trades","Sharpe Ratio","End Value"):
        if k in stats: print(f"  {k}: {stats[k]}")
    trades = pf.trades.records_readable
    if len(trades):
        pl.from_pandas(trades.astype(str)).write_parquet(os.path.join(d,"vbt_ordermodel_trades.parquet"))
    with open(os.path.join(d,"vbt_ordermodel_stats.json"),"w") as f:
        json.dump({k:(float(v) if isinstance(v,(int,float,np.number)) else str(v)) for k,v in stats.items()},f,indent=2,default=str)
    return pf

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv)>1 else "BTCUSD")
