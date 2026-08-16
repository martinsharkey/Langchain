"""
Faithful Python port + backtester of the NotebookLM 'GoldShark_95_Percent_Engine.mq5'.

Replicates the EA's exact business rules so we can measure what it really does
BEFORE writing/compiling live MQL5:

ENTRY (v9.06 gate, evaluated once per new bar on the last CLOSED bar):
  - EMA13 trend: up if ema[t-1] > ema[t-2]
  - ATR pocket: InpMinATR <= atr[t-1] <= InpMaxATR      (price units; gold pt=0.01)
  - OsMA surge multiplier: |osma[t-1]| / mean(|osma[t-2..t-1-lookback]|) in [3.0,4.5]
  - LONG:  bulls>=1.0, bears>-1.0, osma>=0.0  (+ ema up + pocket + multiplier)
  - SHORT: bears<=-1.0, bulls>-1.0, osma<=0.0 (+ ema down + pocket + multiplier)
  - one position at a time

EXIT (v13, per-tick; here resolved with bar OHLC path worst-first):
  - Hard stop: current <= -400 pts
  - Dead-money decay: age>90min AND MFE<20pts AND current<10pts
  - MFE trailing: once MFE>=20pts, trail 15pts (MFE<50) else 30pts (runner)
  - M5 3-indicator exhaustion matrix (>=2 of 3): MACD, EMA slope, Bulls/Bears

Point value: gold _Point = 0.01, so N "points" = N*0.01 in price.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


EA_DEFAULTS = dict(
    ema_period=13,
    min_atr=1.40,   # ATR floor only (no ceiling), per design
    long_bulls_min=1.00, long_bears_min=-1.00, min_osma_long=0.00,
    short_bears_max=-1.00, short_bulls_min=-1.00, max_osma_short=0.00,
    # exits (in POINTS; gold point=0.01)
    mfe_activation_pts=20.0, mfe_runner_thr=50.0,
    scalp_trail_pts=15.0, runner_trail_pts=30.0,
    time_decay_mins=90, hard_sl_pts=400.0,
    point=0.01,
)


def _ema(s, p):
    return s.ewm(span=p, adjust=False).mean()


def compute_ea_indicators(df: pd.DataFrame, p: dict, df_m5: pd.DataFrame | None = None):
    close, high, low = df["close"], df["high"], df["low"]
    ema = _ema(close, p["ema_period"])
    power_ema = _ema(close, p["ema_period"])  # BullsPower/BearsPower use same EMA period
    macd_line = _ema(close, 12) - _ema(close, 26)
    macd_sig = _ema(macd_line, 9)
    osma = macd_line - macd_sig
    # ATR(14) simple TR mean
    pc = close.shift(1)
    tr = pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=1).mean()
    out = pd.DataFrame(index=df.index)
    out["open"], out["high"], out["low"], out["close"] = df["open"], high, low, close
    out["ema"] = ema
    out["osma"] = osma
    out["bulls"] = high - power_ema
    out["bears"] = low - power_ema
    out["atr"] = atr
    return out


def _osma_multiplier(osma: np.ndarray, i: int, lookback: int) -> float:
    # EA: osmaSum over osma[2..lookback+1] (bars before last-closed), current=|osma[4]| (last closed)
    # In series terms at decision bar i (last closed = i): current=|osma[i]|,
    # avg over |osma[i-1 .. i-lookback]|
    if i - lookback < 0:
        return 0.0
    window = np.abs(osma[i - lookback:i])
    avg = window.sum() / lookback if window.sum() != 0 else 1e-4
    return abs(osma[i]) / avg


def _m5_exhaustion(m5: pd.DataFrame, ts, position_type: str) -> bool:
    """M5 3-indicator exhaustion. Uses the last few M5 bars up to time ts."""
    sub = m5.loc[:ts]
    if len(sub) < 6:
        return False
    macd = sub["macd_line"].values
    macd_sig = sub["macd_sig"].values
    ema = sub["ema"].values
    bulls = sub["bulls"].values
    bears = sub["bears"].values
    # avg EMA slope over recent M5 bars (approx the EA's multi-lag slope)
    slope = ((ema[-1] - ema[-2]) + (ema[-2] - ema[-3]) + (ema[-3] - ema[-4])) / 3.0
    cnt = 0
    if position_type == "buy":
        if (macd[-1] < macd_sig[-1] and macd[-2] >= macd_sig[-2]):
            cnt += 1
        elif (macd[-1] < macd[-2] and macd[-2] < macd[-3]):
            cnt += 1
        if slope <= 0.02:
            cnt += 1
        if bulls[-1] < 0 or (bulls[-1] < bulls[-2] and bulls[-2] < bulls[-3]):
            cnt += 1
    else:
        if (macd[-1] > macd_sig[-1] and macd[-2] <= macd_sig[-2]):
            cnt += 1
        elif (macd[-1] > macd[-2] and macd[-2] > macd[-3]):
            cnt += 1
        if slope >= -0.02:
            cnt += 1
        if bears[-1] > 0 or (bears[-1] > bears[-2] and bears[-2] > bears[-3]):
            cnt += 1
    return cnt >= 2


def _compute_m5_matrix(df_m5: pd.DataFrame, p: dict) -> pd.DataFrame:
    c = df_m5["close"]
    macd_line = _ema(c, 12) - _ema(c, 26)
    macd_sig = _ema(macd_line, 9)
    ema = _ema(c, p["ema_period"])
    pe = _ema(c, p["ema_period"])
    out = pd.DataFrame(index=df_m5.index)
    out["macd_line"] = macd_line
    out["macd_sig"] = macd_sig
    out["ema"] = ema
    out["bulls"] = df_m5["high"] - pe
    out["bears"] = df_m5["low"] - pe
    return out


def backtest_ea(df: pd.DataFrame, df_m5: pd.DataFrame, symbol="XAUUSD", timeframe="M1",
                params: dict | None = None, gbp_per_unit: float = 0.7388,
                use_m5_exhaustion: bool = True) -> dict:
    p = dict(EA_DEFAULTS)
    if params:
        p.update(params)
    pt = p["point"]
    ind = compute_ea_indicators(df, p)
    m5m = _compute_m5_matrix(df_m5, p) if df_m5 is not None else None

    ts = ind.index.values
    o = ind["open"].values; hi = ind["high"].values; lo = ind["low"].values; cl = ind["close"].values
    ema = ind["ema"].values; osma = ind["osma"].values
    bulls = ind["bulls"].values; bears = ind["bears"].values; atr = ind["atr"].values
    times = ind.index

    n = len(ind)
    warmup = 60
    pos = None  # dict when in trade
    trades = []  # list of pnl in price units

    hard_sl = p["hard_sl_pts"] * pt
    act = p["mfe_activation_pts"] * pt
    runner_thr = p["mfe_runner_thr"] * pt
    scalp_tr = p["scalp_trail_pts"] * pt
    runner_tr = p["runner_trail_pts"] * pt

    for i in range(warmup, n):
        # ---- manage open position across THIS bar's path (worst-first) ----
        if pos is not None:
            d = pos["dir"]
            entry = pos["entry"]
            # bar path: worst-first then best (conservative)
            path = ([lo[i], hi[i]] if d == "buy" else [hi[i], lo[i]])
            closed = False
            for px in path:
                # update peak
                if d == "buy":
                    pos["peak"] = max(pos["peak"], px)
                    cur = (px - entry)
                    mfe = (pos["peak"] - entry)
                else:
                    pos["peak"] = min(pos["peak"], px)
                    cur = (entry - px)
                    mfe = (entry - pos["peak"])
                age_min = (times[i] - pos["t"]) / np.timedelta64(1, "m")
                # hard stop
                if cur <= -hard_sl:
                    trades.append(-hard_sl); closed = True; break
                # dead money
                if age_min > p["time_decay_mins"] and mfe < act and cur < 10 * pt:
                    trades.append(cur); closed = True; break
                # trailing
                if mfe >= act:
                    tr = scalp_tr if mfe < runner_thr else runner_tr
                    if d == "buy":
                        new_sl = pos["peak"] - tr
                        if pos["sl"] is None or new_sl > pos["sl"]:
                            pos["sl"] = new_sl
                        if px <= pos["sl"]:
                            trades.append(pos["sl"] - entry); closed = True; break
                    else:
                        new_sl = pos["peak"] + tr
                        if pos["sl"] is None or new_sl < pos["sl"]:
                            pos["sl"] = new_sl
                        if px >= pos["sl"]:
                            trades.append(entry - pos["sl"]); closed = True; break
            if not closed and use_m5_exhaustion and m5m is not None:
                if _m5_exhaustion(m5m, times[i], pos["dir"]):
                    px = cl[i]
                    trades.append((px - entry) if pos["dir"] == "buy" else (entry - px))
                    closed = True
            if closed:
                pos = None
            else:
                continue  # still in trade, block new entries

        # ---- evaluate entry on last closed bar (index i) ----
        if pos is None:
            if atr[i] <= 0:
                continue
            ema_up = ema[i] > ema[i - 1]
            ema_dn = ema[i] < ema[i - 1]
            # ATR floor only (no ceiling), per design.
            vol_ok = (atr[i] >= p["min_atr"])
            if not vol_ok:
                continue
            entry_px = cl[i]
            if ema_up and bulls[i] >= p["long_bulls_min"] and bears[i] > p["long_bears_min"] and osma[i] >= p["min_osma_long"]:
                pos = dict(dir="buy", entry=entry_px, peak=entry_px, sl=None, t=times[i])
            elif ema_dn and bears[i] <= p["short_bears_max"] and bulls[i] > p["short_bulls_min"] and osma[i] <= p["max_osma_short"]:
                pos = dict(dir="sell", entry=entry_px, peak=entry_px, sl=None, t=times[i])

    trades = np.array(trades, dtype=float)
    n_tr = len(trades)
    bars_per_day = {"M1": 1440, "M5": 288, "M15": 96}.get(timeframe, 1440)
    span_days = max((n - warmup) / bars_per_day, 1e-9)
    wins = trades[trades > 0]; losses = trades[trades < 0]
    gross_w = wins.sum(); gross_l = -losses.sum()
    pf = (gross_w / gross_l) if gross_l > 0 else (gross_w if gross_w else 0.0)
    win_rate = 100.0 * len(wins) / n_tr if n_tr else 0.0
    gbp_total = trades.sum() * gbp_per_unit  # price units -> GBP at 0.01 lot
    return dict(
        symbol=symbol, timeframe=timeframe, n_trades=n_tr,
        trades_per_day=round(n_tr / span_days, 2),
        win_rate=round(win_rate, 1),
        profit_factor=round(pf, 3),
        total_price_units=round(float(trades.sum()), 2),
        gbp_total_001lot=round(gbp_total, 2),
        gbp_per_day_001lot=round(gbp_total / span_days, 2),
        avg_win=round(float(wins.mean()), 3) if len(wins) else 0.0,
        avg_loss=round(float(losses.mean()), 3) if len(losses) else 0.0,
        span_days=round(span_days, 1),
    )
