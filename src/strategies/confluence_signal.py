"""
Shared MACD-leads-OsMA 7-indicator CONFLUENCE trigger (single source of truth).

The trader's proven edge is the FULL confluence — MACD, OsMA, Bears Power, Bulls
Power, EMA, ATR, RSI — NOT the bare OsMA/MACD cross. Historically several backtest
/optimizer modules re-implemented only the cross and understated the edge. This
module defines the confluence ONCE so the live strategy, pattern optimizer,
excursion analyzer, backtests and the researcher all agree.

find_confluence_triggers(m1, m5, m15, cfg) -> (triggers, m1_df)
Each trigger: M1 OsMA zero-cross that (a) MACD LED (crossed zero same direction
within cfg.macd_lead_bars), (b) passes HARD gates (MACD aligned side-of-zero +
ATR expanding), and (c) meets >= cfg.min_confluence of the 5 SOFT confirmations
(EMA trend, ATR range, price-stretch, Bulls/Bears control, RSI not exhausted),
plus HTF (M5/M15) MACD side for optional filtering downstream.
"""

from __future__ import annotations

import pandas as pd

from src.strategies.indicators import (
    macd as macd_fn, osma as osma_fn, atr as atr_fn, ema as ema_fn,
    rsi as rsi_fn, bulls_power as bulls_fn, bears_power as bears_fn,
)

DEFAULT_CFG = {
    "osma_fast": 12, "osma_slow": 26, "osma_signal": 9, "macd_lead_bars": 5,
    "ema_period": 50, "min_ema_slope_atr": 0.02, "price_stretch_mult": 2.0,
    "atr_period": 14, "atr_min": 0.0, "atr_max": 0.0,
    "power_period": 13, "rsi_period": 14, "rsi_long_max": 72.0, "rsi_short_min": 28.0,
    "min_confluence": 3,
}


def _cfg(cfg):
    c = dict(DEFAULT_CFG)
    if cfg:
        c.update(cfg)
    return c


def compute_confluence(df, cfg):
    """All 7 indicator series aligned to df."""
    c = _cfg(cfg)
    close = df["close"].reset_index(drop=True)
    f, s, sig = c["osma_fast"], c["osma_slow"], c["osma_signal"]
    return {
        "macd": macd_fn(close, f, s, sig)[0].reset_index(drop=True),
        "osma": osma_fn(close, f, s, sig).reset_index(drop=True),
        "atr": atr_fn(df, c["atr_period"]).reset_index(drop=True),
        "ema": ema_fn(close, c["ema_period"]).reset_index(drop=True),
        "rsi": rsi_fn(close, c["rsi_period"]).reset_index(drop=True),
        "bulls": bulls_fn(df, c["power_period"]).reset_index(drop=True),
        "bears": bears_fn(df, c["power_period"]).reset_index(drop=True),
    }


def _htf_side(ts, htf_times, htf_macd):
    lo, hi, idx = 0, len(htf_times) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if htf_times[mid] <= ts:
            idx = mid; lo = mid + 1
        else:
            hi = mid - 1
    if idx < 0 or idx >= len(htf_macd):
        return 0
    v = htf_macd[idx]
    return 1 if v > 0 else (-1 if v < 0 else 0)


def _soft_checks(direction, close, ema, ema_prev, atr, bulls, bears, rsi, c):
    def atr_in_range():
        if c["atr_min"] <= 0 and c["atr_max"] <= 0:
            return True
        if c["atr_min"] > 0 and atr < c["atr_min"]:
            return False
        if c["atr_max"] > 0 and atr > c["atr_max"]:
            return False
        return True
    if direction == "buy":
        return [
            (ema - ema_prev) >= c["min_ema_slope_atr"] * atr and close > ema,
            atr_in_range(),
            abs(close - ema) <= c["price_stretch_mult"] * atr,
            bulls > 0 and bears > -abs(bulls),
            rsi < c["rsi_long_max"],
        ]
    return [
        (ema - ema_prev) <= -c["min_ema_slope_atr"] * atr and close < ema,
        atr_in_range(),
        abs(close - ema) <= c["price_stretch_mult"] * atr,
        bears < 0 and bulls < abs(bears),
        rsi > c["rsi_short_min"],
    ]


def find_confluence_triggers(m1, m5, m15, cfg=None):
    """Full 7-indicator confluence triggers on M1 with HTF context. m1/m5/m15 are
    DataFrames with time/open/high/low/close."""
    c = _cfg(cfg)
    ind = compute_confluence(m1, c)
    macd1, osma1, atr1 = ind["macd"], ind["osma"], ind["atr"]
    ema1, rsi1, bulls1, bears1 = ind["ema"], ind["rsi"], ind["bulls"], ind["bears"]
    m5_macd = compute_confluence(m5, c)["macd"]; m5_t = m5["time"].tolist()
    m15_macd = compute_confluence(m15, c)["macd"]; m15_t = m15["time"].tolist()
    times = m1["time"].tolist(); closes = m1["close"].tolist()
    lead = c["macd_lead_bars"]
    start = max(c["osma_slow"] + c["osma_signal"], c["ema_period"], 30)
    out = []
    for i in range(start, len(m1) - 1):
        cu = osma1[i - 1] <= 0 < osma1[i]
        cd = osma1[i - 1] >= 0 > osma1[i]
        if not (cu or cd):
            continue
        direction = "buy" if cu else "sell"
        led = False
        for k in range(1, lead + 1):
            j = i - k
            if j < 1:
                break
            if (direction == "buy" and macd1[j - 1] <= 0 < macd1[j]) or \
               (direction == "sell" and macd1[j - 1] >= 0 > macd1[j]):
                led = True; break
        if not led:
            continue
        atr = float(atr1[i] or 0)
        if atr <= 0:
            continue
        macd = float(macd1[i]); atr_prev = float(atr1[i - 1] or atr)
        # HARD gates: MACD aligned + ATR expanding
        if (direction == "buy" and not macd > 0) or (direction == "sell" and not macd < 0):
            continue
        if not atr > atr_prev:
            continue
        checks = _soft_checks(direction, closes[i], float(ema1[i]), float(ema1[i - 1]),
                              atr, float(bulls1[i] or 0), float(bears1[i] or 0),
                              float(rsi1[i] or 50), c)
        conf = sum(1 for x in checks if x)
        if conf < c["min_confluence"]:
            continue
        ts = times[i]; want = 1 if direction == "buy" else -1
        trig = {"i": i, "direction": direction, "entry": closes[i], "atr": atr,
                "confluence": conf,
                "m5_ok": _htf_side(ts, m5_t, m5_macd) == want,
                "m15_ok": _htf_side(ts, m15_t, m15_macd) == want}
        # #43: carry CryptoRTI whale features if attached to the bars (causal), so
        # backtests can validate the whale hybrid boost. whale_active is 1 when a
        # deposit/credit-window/flow is active at-or-before this bar.
        if "whale_active" in m1.columns:
            trig["whale_active"] = int(m1["whale_active"].iloc[i]) if i < len(m1) else 0
            if "vpin_percentile" in m1.columns:
                trig["vpin_pct"] = float(m1["vpin_percentile"].iloc[i] or 0)
            # #45.2: carry the whale ORDER SIZE so backtests gate on the same
            # >=$6M threshold the live path uses (validate what we trade).
            if "whale_deposit_usd_1h" in m1.columns:
                trig["whale_usd"] = float(m1["whale_deposit_usd_1h"].iloc[i] or 0)
        out.append(trig)
    return out, m1
