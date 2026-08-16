"""
vectorbt-based backtesting engine for the OsMA-Confluence strategy.

This is a parallel engine to src/learning/backtester.py, built on vectorbt for
fast, vectorized parameter sweeps. It reimplements the same *business rules*
(indicators, confluence entry logic, ATR-based SL / RR TP, GBP-on-0.01-lot
readout) so results are comparable to the tick-accurate engine.

IMPORTANT FILL-REALISM NOTE
---------------------------
vectorbt fills on bar OHLC with a flat `fees`/`slippage` model. It does NOT use
real bid/ask ticks like src/learning/backtester.py. For high-frequency M1 gold
(hundreds of trades/day) the spread cost is the dominant term, so treat vectorbt
numbers as an *optimistic pre-filter* for breadth, and always re-validate the
top candidates in the tick-accurate engine before trusting the money figure.

Usage (from the project venv):
    from src.learning.vbt_engine import fetch_bars, run_confluence, sweep
    df = fetch_bars("XAUUSD-ECN", "M5", 12000)
    res = run_confluence(df, symbol="XAUUSD", timeframe="M5")
    print(res["stats"])
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except Exception as e:  # pragma: no cover
    raise ImportError("vectorbt is required for vbt_engine; pip install vectorbt") from e


# ---------------------------------------------------------------------------
# Business-rule defaults (mirrors param_optimizer.DEFAULTS + confluence cfg)
# ---------------------------------------------------------------------------

VBT_DEFAULTS = {
    # indicator periods
    "osma_fast": 12, "osma_slow": 26, "osma_signal": 9,
    "ema_period": 50,            # trend EMA (confluence DEFAULT_CFG uses 50)
    "atr_period": 14,
    "power_period": 13,          # bulls/bears EMA
    "rsi_period": 14,
    # soft-check thresholds
    "min_ema_slope": 0.02,       # ATR-normalized EMA slope floor (S1)
    "price_stretch_mult": 2.0,   # S3: |close-ema| <= mult*atr
    "atr_min": 0.0, "atr_max": 0.0,       # absolute ATR band (S2)
    "atr_min_rel": 0.7,          # relative ATR floor (S2): atr >= rel*median_atr
    "rsi_long_max": 72.0, "rsi_short_min": 28.0,  # S5 + hard exhaustion gate
    "min_confluence": 4,         # soft count threshold (0..5)
    # signed strength floors (ATR-scaled). 0 = OFF
    "osma_min_long": 0.0, "osma_max_short": 0.0,
    "bulls_min_long": 0.0, "bears_max_short": 0.0,
    # momentum age
    "max_momentum_age": 3,
    # exits
    "sl_atr": 0.8, "tp_rr": 2.0,
    # costs (flat vectorbt model). XAU spread ~ a few points; tune per broker.
    "fees": 0.0, "slippage": 0.0,
}

# Per-symbol proven baseline (XAUUSD pass5469) mapped to vbt keys
XAUUSD_BASELINE = {
    "osma_fast": 12, "osma_slow": 26, "osma_signal": 9, "ema_period": 13,
    "atr_period": 14, "min_ema_slope": 0.2, "atr_min": 1.4, "atr_max": 0.0,
    "osma_min_long": 0.87, "bulls_min_long": 0.3,
    "osma_max_short": -0.30, "bears_max_short": -0.04,
    "rsi_long_max": 100.0, "rsi_short_min": 0.0,
    "sl_atr": 0.8, "tp_rr": 2.0, "min_confluence": 3,
}

BARS_PER_DAY = {"M1": 1440, "M5": 288, "M15": 96, "M30": 48, "H1": 24, "H4": 6, "D1": 1}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def fetch_bars(symbol: str = "XAUUSD-ECN", timeframe: str = "M5", count: int = 12000) -> pd.DataFrame:
    """Fetch OHLCV bars from the live MT5 terminal into a DatetimeIndexed DataFrame.

    Requires the MT5 terminal running and logged in (same as the production engine).
    """
    from src.mt5.connector import get_connector
    import MetaTrader5 as mt5

    conn = get_connector()
    conn.initialize()
    tf_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map[timeframe]
    raw = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if raw is None or len(raw) == 0:
        raise ConnectionError(f"No rates for {symbol} {timeframe} (terminal running?)")
    df = pd.DataFrame(raw).rename(columns={"tick_volume": "volume"})
    df.index = pd.to_datetime(df["time"], unit="s")
    df.index.name = "time"
    return df[["open", "high", "low", "close", "volume", "spread"]]


# ---------------------------------------------------------------------------
# Indicators (mirror src/strategies/indicators.py exactly)
# ---------------------------------------------------------------------------

def _ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()


def _rsi(close: pd.Series, p: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    dn = -delta.clip(upper=0.0)
    # Wilder smoothing
    roll_up = up.ewm(alpha=1.0 / p, adjust=False).mean()
    roll_dn = dn.ewm(alpha=1.0 / p, adjust=False).mean()
    rs = roll_up / roll_dn.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(p, min_periods=1).mean()  # simple rolling mean (not Wilder), matches engine


def compute_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    close, high, low = df["close"], df["high"], df["low"]
    macd_line = _ema(close, p["osma_fast"]) - _ema(close, p["osma_slow"])
    macd_signal = _ema(macd_line, p["osma_signal"])
    osma = macd_line - macd_signal
    ema_trend = _ema(close, p["ema_period"])
    power_ema = _ema(close, p["power_period"])
    out = pd.DataFrame(index=df.index)
    out["close"] = close
    out["osma"] = osma
    out["osma_prev"] = osma.shift(1)
    out["macd_line"] = macd_line
    out["macd_signal"] = macd_signal
    out["ema"] = ema_trend
    out["ema_prev"] = ema_trend.shift(1)
    out["atr"] = _atr(df, p["atr_period"])
    out["bulls"] = high - power_ema
    out["bears"] = low - power_ema
    out["rsi"] = _rsi(close, p["rsi_period"])
    out["med_atr"] = out["atr"].rolling(200, min_periods=20).median()
    return out


# ---------------------------------------------------------------------------
# Confluence entry signals (vectorized reimplementation)
# ---------------------------------------------------------------------------

def confluence_signals(ind: pd.DataFrame, p: dict):
    """Return (long_entries, short_entries) boolean Series matching the
    OsMA-Confluence business rules (vectorized, closed-bar semantics).
    """
    osma, osma_prev = ind["osma"], ind["osma_prev"]
    atr = ind["atr"]
    ema, ema_prev = ind["ema"], ind["ema_prev"]
    close = ind["close"]
    bulls, bears, rsi = ind["bulls"], ind["bears"], ind["rsi"]
    macd_line, macd_sig = ind["macd_line"], ind["macd_signal"]

    valid = (atr > 0) & (close > 0)

    # Step 1: OsMA zero-cross trigger (cross OR fresh momentum within max age)
    cross_up = (osma_prev <= 0) & (osma > 0)
    cross_dn = (osma_prev >= 0) & (osma < 0)
    max_age = int(p.get("max_momentum_age", 3))
    pos_age = _sign_age(osma, +1)
    neg_age = _sign_age(osma, -1)
    fresh_up = (~cross_up) & (osma > 0) & (pos_age > 0) & (pos_age <= max_age)
    fresh_dn = (~cross_dn) & (osma < 0) & (neg_age > 0) & (neg_age <= max_age)
    trig_up = cross_up | fresh_up
    trig_dn = cross_dn | fresh_dn

    # Step 2: MACD alignment (line vs signal == osma sign)
    macd_up = macd_line > macd_sig
    macd_dn = macd_line < macd_sig

    # Step 4: OsMA acceleration
    accel_up = osma > osma_prev
    accel_dn = osma < osma_prev

    # Step 6: HARD RSI exhaustion gate
    rsi_ok_long = rsi < p["rsi_long_max"]
    rsi_ok_short = rsi > p["rsi_short_min"]

    # Step 9: immutable directional-alignment (sign of powers)
    dir_long = (bulls > 0) & (bears > 0) & (osma > 0)
    dir_short = (bulls < 0) & (bears < 0) & (osma < 0)

    # Step 10: signed strength floors (ATR-scaled), 0 = OFF
    def floor_long(series, key):
        f = p.get(key, 0.0)
        if not f:
            return pd.Series(True, index=series.index)
        return series >= f * atr

    def floor_short(series, key):
        f = p.get(key, 0.0)
        if not f:
            return pd.Series(True, index=series.index)
        return series <= f * atr

    strong_long = floor_long(osma, "osma_min_long") & floor_long(bulls, "bulls_min_long")
    strong_short = floor_short(osma, "osma_max_short") & floor_short(bears, "bears_max_short")

    # Step 11: soft confluence count (S1..S5)
    s1_long = ((ema - ema_prev) >= p["min_ema_slope"] * atr) & (close > ema)
    s1_short = ((ema_prev - ema) >= p["min_ema_slope"] * atr) & (close < ema)
    atr_rel_ok = ind["atr"] >= p["atr_min_rel"] * ind["med_atr"].fillna(ind["atr"])
    atr_abs_ok = pd.Series(True, index=atr.index)
    if p.get("atr_min", 0):
        atr_abs_ok &= atr >= p["atr_min"]
    if p.get("atr_max", 0):
        atr_abs_ok &= atr <= p["atr_max"]
    s2 = atr_rel_ok & atr_abs_ok
    s3 = (close - ema).abs() <= p["price_stretch_mult"] * atr
    s4_long = (bulls > 0) & (bears > 0)
    s4_short = (bears < 0) & (bulls < 0)
    s5_long = rsi < p["rsi_long_max"]
    s5_short = rsi > p["rsi_short_min"]

    conf_long = (s1_long.astype(int) + s2.astype(int) + s3.astype(int)
                 + s4_long.astype(int) + s5_long.astype(int))
    conf_short = (s1_short.astype(int) + s2.astype(int) + s3.astype(int)
                  + s4_short.astype(int) + s5_short.astype(int))
    minc = int(p["min_confluence"])

    long_entries = (valid & trig_up & macd_up & accel_up & rsi_ok_long
                    & dir_long & strong_long & (conf_long >= minc))
    short_entries = (valid & trig_dn & macd_dn & accel_dn & rsi_ok_short
                     & dir_short & strong_short & (conf_short >= minc))
    return long_entries.fillna(False), short_entries.fillna(False)


def _sign_age(osma: pd.Series, sign: int) -> pd.Series:
    """Number of consecutive bars (including current) that osma has held `sign`."""
    same = (np.sign(osma) == sign).astype(int)
    # cumulative run length
    grp = (same != same.shift(1)).cumsum()
    return same.groupby(grp).cumsum() * same


# ---------------------------------------------------------------------------
# GBP-on-0.01-lot conversion (mirrors backtester._gbp_per_price_unit_001)
# ---------------------------------------------------------------------------

def gbp_per_price_unit_001(symbol: str) -> float:
    try:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
        if info and getattr(info, "trade_tick_value", None):
            tsz = getattr(info, "trade_tick_size", info.point) or info.point or 0.01
            return (info.trade_tick_value / tsz) * 0.01
    except Exception:
        pass
    return 0.7388  # fallback: GBP per $1 XAU move at 0.01 lot


# ---------------------------------------------------------------------------
# Run one config
# ---------------------------------------------------------------------------

def run_confluence(df: pd.DataFrame, symbol: str = "XAUUSD", timeframe: str = "M5",
                   params: dict | None = None) -> dict:
    p = dict(VBT_DEFAULTS)
    if params:
        p.update(params)
    ind = compute_indicators(df, p)
    longs, shorts = confluence_signals(ind, p)

    close = df["close"]
    atr = ind["atr"]
    # ATR-based SL as a fraction of price -> vectorbt sl_stop is fractional.
    # 1R = sl_atr * atr (price units). Use median ATR for a stable stop fraction.
    sl_frac = float((p["sl_atr"] * atr / close).replace([np.inf, -np.inf], np.nan).median())
    tp_frac = sl_frac * float(p["tp_rr"])

    freq = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
            "H1": "1h", "H4": "4h", "D1": "1d"}.get(timeframe, "1min")

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=longs,
        exits=pd.Series(False, index=close.index),
        short_entries=shorts,
        short_exits=pd.Series(False, index=close.index),
        sl_stop=sl_frac,
        tp_stop=tp_frac,
        fees=float(p["fees"]),
        slippage=float(p["slippage"]),
        init_cash=10_000.0,
        freq=freq,
    )

    trades = pf.trades
    n = int(trades.count()) if hasattr(trades, "count") else 0
    span_days = max(len(df) / BARS_PER_DAY.get(timeframe, 1440), 1e-9)

    # GBP on 0.01 lot: total_R * (sl_atr*avg_atr) * gbp_per_unit
    total_r = 0.0
    try:
        # returns in R: pnl / (risk per trade). Approx with trade returns * (1/sl_frac)
        rets = trades.returns.values
        total_r = float(np.nansum(rets) / sl_frac) if sl_frac else 0.0
    except Exception:
        pass
    avg_atr = float(atr.iloc[max(0, len(atr) - len(df)):].mean())
    gbp_unit = gbp_per_price_unit_001(symbol)
    gbp_total = total_r * (p["sl_atr"] * avg_atr) * gbp_unit

    win_rate = float(trades.win_rate() * 100) if n else 0.0
    pf_val = float(trades.profit_factor()) if n else 0.0
    try:
        sharpe = float(pf.sharpe_ratio())
    except Exception:
        sharpe = float("nan")

    return {
        "symbol": symbol, "timeframe": timeframe,
        "n_trades": n,
        "trades_per_day": round(n / span_days, 1),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf_val, 3),
        "sharpe": round(sharpe, 3) if sharpe == sharpe else None,
        "total_return_pct": round(float(pf.total_return() * 100), 2),
        "gbp_total_001lot": round(gbp_total, 2),
        "gbp_per_day_001lot": round(gbp_total / span_days, 2),
        "avg_atr": round(avg_atr, 3),
        "sl_frac": round(sl_frac, 6), "tp_frac": round(tp_frac, 6),
        "span_days": round(span_days, 1),
        "_pf": pf,  # keep the vectorbt Portfolio for .stats()/.plot()
    }


def sweep(df: pd.DataFrame, symbol: str, timeframe: str, grid: dict) -> pd.DataFrame:
    """Grid-sweep params. `grid` maps param name -> list of values.
    Returns a DataFrame sorted by profit_factor.
    """
    import itertools
    keys = list(grid.keys())
    rows = []
    for combo in itertools.product(*[grid[k] for k in keys]):
        params = dict(zip(keys, combo))
        try:
            r = run_confluence(df, symbol, timeframe, params)
        except Exception as e:
            rows.append({**params, "error": str(e)[:60]})
            continue
        r.pop("_pf", None)
        rows.append({**params, **r})
    out = pd.DataFrame(rows)
    if "profit_factor" in out.columns:
        out = out.sort_values("profit_factor", ascending=False)
    return out
