"""
Floor validator + auto-escalation — the CANONICAL high-quality-floor discovery used
by BOTH the live researcher and the symbol-onboarding process.

Owner method (2026-08-13), proven on XAUUSD (79% WR) and BTCUSD (85% WR):
  * Validate over a MULTI-WEEK period (>= 1 week; default ~5-7 weeks of M1), NOT a
    2.8-day window, and with NO arbitrary per-window min-trade gate. A high-quality,
    low-frequency strategy (e.g. 15-20 trades/week at >70% WR) is a VALID result.
  * Start at the per-symbol baseline floors (alignment_floors, from telemetry).
  * If win rate < target (default 70%), AUTO-ESCALATE: raise LONG floors (+step) and
    lower SHORT ceilings (-step) — the owner principle that HIGHER indicator strength
    increases entry quality — re-testing until WR >= target OR entries dry up.
  * Uses the be_trail exit model (wide SL + BE + trail, no TP), matching live.

Directional alignment is NEVER reversed (longs stay positive, shorts negative);
escalation only makes floors STRICTER. Discovered floors are returned so the caller
can persist them via alignment_floors.propose_rebaseline (which re-clamps to stay on
the correct side of zero).
"""

from __future__ import annotations

from typing import Optional
from src.utils.logger import get_logger
from src.strategies.alignment_floors import baseline

logger = get_logger("floor_validator")

# escalation step per indicator (native units): fine for gold, coarser for BTC-scale.
_STEP = {
    "XAUUSD-ECN": {"osma": 0.05, "bulls": 0.25, "bears": 0.10},
    "XAUUSD":     {"osma": 0.05, "bulls": 0.25, "bears": 0.10},
    "BTCUSD":     {"osma": 0.5,  "bulls": 2.5,  "bears": 0.5},
}
_DEFAULT_STEP = {"osma": 0.05, "bulls": 0.25, "bears": 0.10}
# per-symbol exit geometry (points) — BTC scaled ~15x gold.
_EXIT = {
    "XAUUSD-ECN": (500, 150, 150), "XAUUSD": (500, 150, 150),
    "BTCUSD": (8000, 800, 1000),
}
_DEFAULT_EXIT = (500, 150, 150)


def _auto_step(df, pt):
    """Derive escalation steps from the symbol's OWN indicator magnitudes so
    onboarding auto-scales to ANY symbol (gold ~0.05 osma, BTC ~0.5, index in
    between) instead of hardcoded per-symbol steps. Step ~= 5% of the 90th-pct
    absolute indicator value, so ~20 levels span the meaningful range."""
    try:
        import numpy as np
        from src.strategies.indicators import osma as _osma, bulls_power as _bp, bears_power as _be
        o = _osma(df["close"], 12, 26, 9).abs().dropna()
        b = _bp(df, 13).abs().dropna()
        be = _be(df, 13).abs().dropna()
        so = max(round(float(np.nanpercentile(o, 90)) * 0.02, 4), 0.01)
        sb = max(round(float(np.nanpercentile(b, 90)) * 0.02, 4), 0.05)
        sbe = max(round(float(np.nanpercentile(be, 90)) * 0.02, 4), 0.05)
        return {"osma": so, "bulls": sb, "bears": sbe}
    except Exception:
        return _DEFAULT_STEP


def _auto_exit(df, pt):
    """Derive wide-SL/BE/trail (points) from the symbol's ATR when no explicit exit
    geometry is configured, so any symbol gets sensible, scale-correct exits.
    SL ~= 30x ATR (wide), BE ~= 8x ATR, trail ~= 10x ATR — in points."""
    try:
        import numpy as np
        from src.strategies.indicators import atr as _atr
        a = float(np.nanmedian(_atr(df, 14).dropna()))
        atr_pts = a / pt if pt else a
        return (max(int(atr_pts * 30), 100), max(int(atr_pts * 8), 30), max(int(atr_pts * 10), 40))
    except Exception:
        return _DEFAULT_EXIT


def _find_triggers_with_floors(df, m5, m15, cfg, symbol):
    """Find entries the SAME way LIVE does: walk EVERY bar through
    evaluate_confluence_bar (the single source of truth) with the fresh-momentum
    series windows the live osma_confluence adapter builds. This enters a few bars
    AFTER the zero-cross once OsMA has built to the strength floor — so the floors
    genuinely bite in backtest exactly as they do live (fixes the validator-vs-live
    mismatch where find_confluence_triggers evaluated only the near-zero cross bar
    and never applied the floors). Returns [{i, direction, entry}]."""
    from src.strategies.confluence_signal import evaluate_confluence_bar
    from src.strategies.indicators import compute_indicator_series
    series = compute_indicator_series(df.to_dict("records"), cfg)
    n = len(series)
    if n < 60:
        return []
    kept = []
    last_i = -1
    cooldown = int(cfg.get("max_momentum_age", 5)) + 1
    for i in range(35, n):
        s = series[i]
        if not s or s.get("close") is None or not s.get("atr"):
            continue
        if i - last_i < cooldown:      # one entry per momentum burst (avoid dupes)
            continue
        ind = dict(s)
        ind["symbol"] = symbol
        ind["osma_closed"] = s.get("osma")
        ind["osma_prev"] = series[i-1].get("osma") if i >= 1 else 0.0
        ind["ema_fast"] = s.get("ema")
        ind["ema_prev"] = series[i-1].get("ema") if i >= 1 else s.get("ema")
        ind["atr_prev"] = series[i-1].get("atr") if i >= 1 else s.get("atr")
        # fresh-momentum series (sign-age) + runway, as the live adapter provides
        recent = [series[j].get("osma") for j in range(max(0, i-8), i+1)]
        ind["osma_recent"] = recent
        mags = [abs(float(x)) for x in recent if x is not None]
        if mags:
            ind["osma_recent_avg"] = sum(mags) / len(mags)
        r = evaluate_confluence_bar(ind, cfg)
        if r.get("action") in ("buy", "sell"):
            kept.append({"i": i, "direction": r["action"], "entry": s["close"]})
            last_i = i
    return kept


def _simulate(trig, hi, lo, cl, pt, sl_pts, be_pts, tr_pts):
    """be_trail exit sim (wide SL, BE, trail, no TP) over confluence entries.
    Returns (n, win_rate_pct, pf, net_R)."""
    SL, BE, TR = sl_pts * pt, be_pts * pt, tr_pts * pt
    N = len(cl); w = l = 0; gw = gl = 0.0; netR = 0.0
    for t in trig:
        i = t["i"]; d = t.get("direction") or t.get("dir"); e = t["entry"]
        sl = (e - SL) if d == "buy" else (e + SL); best = e; be = False; R = None
        for k in range(i + 1, min(i + 1000, N)):
            if d == "buy":
                if lo[k] <= sl: R = (sl - e) / SL; break
                best = max(best, hi[k])
                if not be and (best - e) >= BE: sl = max(sl, e + 2 * pt); be = True
                if be: sl = max(sl, best - TR)
            else:
                if hi[k] >= sl: R = (e - sl) / SL; break
                best = min(best, lo[k])
                if not be and (e - best) >= BE: sl = min(sl, e - 2 * pt); be = True
                if be: sl = min(sl, best + TR)
        if R is None:
            last = cl[min(i + 1000, N - 1)]
            R = ((last - e) if d == "buy" else (e - last)) / SL
        netR += R
        if R > 0: w += 1; gw += R
        else: l += 1; gl += abs(R)
    n = w + l
    pf = (gw / gl) if gl > 0 else (gw if gw else 0.0)
    return n, (w / n * 100 if n else 0.0), round(pf, 2), round(netR, 1)


def discover_high_quality_floors(symbol: str, get_rates_fn=None, *, target_wr: float = 70.0,
                                 bars: int = 50000, min_total: int = 8,
                                 max_steps: int = 25) -> dict:
    """Validate + auto-escalate floors for one symbol over a multi-week window.

    Returns {found: bool, levels: [...], best: {...}|None, weeks: float}. `best`
    (when found) has the escalated floor dict + n, wr, pf, netR, trades_per_week.
    Pure research: it does NOT mutate live config — the caller decides to persist.
    """
    try:
        import MetaTrader5 as mt5
        import pandas as pd
        from src.strategies.confluence_signal import find_confluence_triggers
        from src.learning.param_optimizer import DEFAULTS
    except Exception as e:
        return {"found": False, "error": f"deps unavailable: {e}", "levels": []}

    try:
        df = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars)).rename(columns={"tick_volume": "volume"})
        m5 = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars // 5 + 50)).rename(columns={"tick_volume": "volume"})
        m15 = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars // 15 + 50)).rename(columns={"tick_volume": "volume"})
        if df.empty or "time" not in df:
            return {"found": False, "error": "no bars", "levels": []}
        weeks = (df["time"].iloc[-1] - df["time"].iloc[0]) / 86400.0 / 7
        if weeks < 1.0:
            return {"found": False, "error": f"only {weeks:.1f} weeks of data (<1wk)", "levels": [], "weeks": weeks}
        hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
        pt = (mt5.symbol_info(symbol).point if mt5.symbol_info(symbol) else 0.01) or 0.01
        # explicit per-symbol geometry/step if configured, else AUTO-SCALE from the
        # symbol's own ATR/indicator magnitudes so onboarding works for ANY symbol.
        sl_pts, be_pts, tr_pts = _EXIT.get(symbol) or _auto_exit(df, pt)
        step = _STEP.get(symbol) or _auto_step(df, pt)

        b = baseline(symbol)
        fl = {"osma_min_long": b["long"]["osma_min"], "bulls_min_long": b["long"]["bulls_min"],
              "bears_min_long": b["long"]["bears_min"], "osma_max_short": b["short"]["osma_max"],
              "bears_max_short": b["short"]["bears_max"], "bulls_max_short": b["short"]["bulls_max"]}

        levels = []; best = None
        for lvl in range(max_steps):
            p = dict(DEFAULTS); p["symbol"] = symbol; p["min_confluence"] = 3; p.update(fl)
            trig = _find_triggers_with_floors(df, m5, m15, p, symbol)
            n, wr, pf, netR = _simulate(trig, hi, lo, cl, pt, sl_pts, be_pts, tr_pts)
            twk = round(n / weeks, 1) if weeks else 0
            rec = {"level": lvl, **{k: fl[k] for k in fl}, "n": n, "trades_per_week": twk,
                   "win_rate": round(wr, 1), "pf": pf, "net_R": netR}
            levels.append(rec)
            if n < min_total:
                break
            if wr >= target_wr and pf >= 1.0:
                best = dict(rec); break
            fl["osma_min_long"] = round(fl["osma_min_long"] + step["osma"], 2)
            fl["bulls_min_long"] = round(fl["bulls_min_long"] + step["bulls"], 2)
            fl["bears_min_long"] = round(fl["bears_min_long"] + step["bears"], 2)
            fl["osma_max_short"] = round(fl["osma_max_short"] - step["osma"], 2)
            fl["bears_max_short"] = round(fl["bears_max_short"] - step["bulls"], 2)
            fl["bulls_max_short"] = round(fl["bulls_max_short"] - step["bears"], 2)

        return {"found": best is not None, "best": best, "levels": levels, "weeks": round(weeks, 1),
                "exit": {"sl_pts": sl_pts, "be_pts": be_pts, "trail_pts": tr_pts}}
    except Exception as e:
        logger.warning(f"floor discovery failed {symbol}: {e}")
        return {"found": False, "error": str(e), "levels": []}
