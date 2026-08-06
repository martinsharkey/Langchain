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
    # #45.5/#5: volatility FLOOR active from day one, symbol-agnostic. ATR at entry
    # must be >= atr_min_rel x the symbol's recent median ATR (not a raw point value,
    # which would mis-gate BTC vs gold). 0.7 = skip unusually-quiet bars. Optimizer
    # can refine; atr_min/atr_max (absolute) stay available for explicit per-symbol tuning.
    "atr_min_rel": 0.7,
    "power_period": 13, "rsi_period": 14, "rsi_long_max": 72.0, "rsi_short_min": 28.0,
    "min_confluence": 4,   # re-baseline (#47): 4/5 soft checks lifted PF 1.56->2.98 vs 3
    # ENTRY TRIGGER: a pure closed-bar zero-cross is only a ~3% event, which starves
    # the bot to ~0 trades/day. GoldShark itself enters on FRESH momentum (a cross
    # within InpMaxMomentumAge bars), not only the exact flip bar. So fresh-momentum is
    # ON by default (age<=5) — the move must still pass every quality gate (strength
    # floors, MACD, EMA side, ATR, confluence), and the frequency-starvation guard +
    # optimizer keep the entry/quality balance. `allow_anticipated` stays OFF (that one
    # enters BEFORE the cross = probability, whipsaw-prone).
    "allow_fresh_momentum": True, "max_momentum_age": 5, "allow_anticipated": False,
}


def _cfg(cfg):
    c = dict(DEFAULT_CFG)
    if cfg:
        c.update(cfg)
    # KEY ALIAS: the optimizer/baseline use `min_ema_slope` but the confluence's
    # EMA-slope soft-check reads `min_ema_slope_atr`. Without this remap the tuned/
    # proven slope (e.g. pass5469's 0.2) was silently dropped and the check used the
    # 0.02 default. Alias so the tuned value actually gates the EMA-slope soft-check.
    if cfg and "min_ema_slope" in cfg and "min_ema_slope_atr" not in cfg:
        c["min_ema_slope_atr"] = cfg["min_ema_slope"]
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


def _soft_checks(direction, close, ema, ema_prev, atr, bulls, bears, rsi, c, med_atr=0.0):
    def atr_in_range():
        # relative volatility floor (symbol-agnostic): active from day one
        if c.get("atr_min_rel", 0) > 0 and med_atr > 0 and atr < c["atr_min_rel"] * med_atr:
            return False
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
            bulls > 0 and bears > 0,   # long: BOTH Bulls Power AND Bears Power > 0 (stated rule)
            rsi < c["rsi_long_max"],
        ]
    return [
        (ema - ema_prev) <= -c["min_ema_slope_atr"] * atr and close < ema,
        atr_in_range(),
        abs(close - ema) <= c["price_stretch_mult"] * atr,
        bears < 0 and bulls < 0,       # short: BOTH Bears Power AND Bulls Power < 0 (stated rule)
        rsi > c["rsi_short_min"],
    ]


def evaluate_confluence_bar(ind: dict, cfg=None) -> dict:
    """
    SHARED per-bar confluence decision used by BOTH the backtest bar-loop and the
    LIVE single-bar path (osma_confluence.py) -- one rule set, no drift (#unify).

    `ind` = single-bar snapshot: osma, osma_prev, macd_line, ema_fast, ema_prev,
    atr, atr_prev, bulls_power, bears_power, rsi, close; optionally macd_led (bool)
    and med_atr (symbol median ATR for the relative vol floor).
    Returns {action: buy|sell|hold, trigger_kind: cross|anticipated|None,
             confluence: int, reason: str}. Keeps the anticipated-cross trigger.
    """
    c = _cfg(cfg)
    close = float(ind.get("close") or ind.get("ema_fast") or 0)
    atr = float(ind.get("atr") or 0)
    if atr <= 0 or close <= 0:
        return {"action": "hold", "trigger_kind": None, "confluence": 0, "reason": "no atr/price"}
    osma_now = float(ind.get("osma") or 0); osma_prev = float(ind.get("osma_prev") or 0)
    macd = float(ind.get("macd_line") or 0); atr_prev = float(ind.get("atr_prev") or atr)
    # PURE EVENT-DRIVEN TRIGGER (GoldShark Master directive): the entry MUST be the
    # exact closed-bar OsMA zero-cross — a strict 1-candle polarity shift across 0.0.
    # NO 'anticipated' (probability, not event -> whipsaw) and NO 'fresh momentum /
    # sign-age' (state, not event -> entering late / chasing). These are OFF by default
    # and only re-enabled via explicit config flags for research.
    cu = osma_prev <= 0 < osma_now      # confirmed cross UP through zero
    cd = osma_prev >= 0 > osma_now      # confirmed cross DOWN through zero
    au = ad = fresh_up = fresh_dn = False
    if c.get("allow_anticipated", False):
        band = c.get("osma_anticipate_atr", 0.15) * atr
        au = (not cu) and (-band <= osma_now <= 0) and (osma_now > osma_prev)
        ad = (not cd) and (0 <= osma_now <= band) and (osma_now < osma_prev)
    if c.get("allow_fresh_momentum", False):
        max_age = int(c.get("max_momentum_age", 5))
        recent = ind.get("osma_recent") or []
        recent_closed = recent[:-1] if len(recent) > 1 else recent
        def _sign_age(positive: bool) -> int:
            age = 0
            for v in reversed(recent_closed):
                try: fv = float(v)
                except (TypeError, ValueError): break
                if (positive and fv > 0) or ((not positive) and fv < 0):
                    age += 1
                else:
                    break
            return age
        fresh_up = (not (cu or au)) and osma_now > 0 and 0 < _sign_age(True) <= max_age
        fresh_dn = (not (cd or ad)) and osma_now < 0 and 0 < _sign_age(False) <= max_age
    if not (cu or cd or au or ad or fresh_up or fresh_dn):
        return {"action": "hold", "trigger_kind": None, "confluence": 0, "reason": "no OsMA zero-cross"}
    direction = "buy" if (cu or au or fresh_up) else "sell"
    trigger_kind = "cross" if (cu or cd) else ("anticipated" if (au or ad) else "fresh")
    # MACD confirmation — GOLDSHARK PARITY: GoldShark's IsM1MACDAligned checks
    # macdMain > macdSignal (main vs SIGNAL line), NOT macd vs the ZERO line. macd_main
    # minus signal IS the OsMA, so this is effectively "OsMA on the right side" — which
    # the trigger already guarantees. Our old `macd_line > 0` (vs zero) gate was an
    # over-restriction GoldShark does NOT have: it blocked OsMA-aligned entries into big
    # moves where MACD hadn't yet crossed zero (e.g. BTC osma +15 but macd -5). Use the
    # main-vs-signal check when the signal is available; else fall back to OsMA sign.
    macd_sig = ind.get("macd_signal")
    is_anticipated = trigger_kind == "anticipated"
    if is_anticipated:
        # ANTICIPATED cross hasn't happened yet (osma_now is still on the OLD side by
        # definition), so a strict sign/main-vs-signal gate would ALWAYS reject it,
        # making allow_anticipated a silent no-op. Use a DIRECTION-only check: OsMA
        # must be MOVING the right way (toward/through zero) for the intended side.
        macd_aligned = (osma_now > osma_prev) if direction == "buy" else (osma_now < osma_prev)
    elif macd_sig is not None:
        macd_aligned = (macd > float(macd_sig)) if direction == "buy" else (macd < float(macd_sig))
    else:
        macd_aligned = (osma_now > 0) if direction == "buy" else (osma_now < 0)
    if not macd_aligned:
        return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0, "reason": "MACD not aligned (vs signal)"}
    if "macd_led" in ind and not ind["macd_led"]:
        return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0, "reason": "MACD did not lead"}
    # OsMA acceleration IS part of the GoldShark rule (osma[1] > osma[2] for long), so
    # keep it for cross/anticipated triggers. But "ATR strictly RISING every bar" is
    # NOT a GoldShark gate — GoldShark uses ATR IN-RANGE (MinATR<=atr<=MaxATR, handled
    # in the soft checks). The strict-rising gate blocked ~100% of bars (ATR is a
    # smoothed average, flat/falling half the time) and starved trading. Removed.
    if trigger_kind in ("cross", "anticipated"):
        if (direction == "buy" and not osma_now > osma_prev) or \
           (direction == "sell" and not osma_now < osma_prev):
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": "OsMA not accelerating"}
    # LEARNED PRICE-STRETCH gate (the ONE entry feature that actually separates
    # winners from losers in the full GoldShark telemetry: winners enter MUCH closer
    # to the EMA — PriceStretch 85% separation on BTC — losers enter over-extended).
    # NOTE: OsMA/Bulls/Bears STRENGTH magnitude does NOT separate winners (verified:
    # raising those thresholds lowers win-rate), so we deliberately do NOT gate on
    # strength. `max_stretch_atr` is learned per symbol (|close-ema|/ATR ceiling);
    # absent/0 -> no extra gate (soft-check stretch still applies).
    ema_fast = float(ind.get("ema_fast") or close)
    max_stretch = c.get("max_stretch_atr", 0.0)
    if max_stretch and atr > 0:
        stretch = abs(close - ema_fast) / atr
        if stretch > max_stretch:
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": f"over-extended: stretch {stretch:.2f}xATR > learned max {max_stretch:.2f}"}
    # MINED ENTRY-QUALITY gates (from all EA telemetry: the recipe that lifts entry-
    # direction success toward 95%). All ATR-normalized, learned per symbol, applied
    # only when the harness proved they raise entry-success:
    #   accel_min  — OsMA acceleration magnitude |osma_now-osma_prev|/ATR (freshness)
    #   dom_min    — dominant-side power (Bulls long / Bears mag short) / ATR
    #   runway_min — FinalMultiplier proxy: |osma_now| / recent-avg |osma| (runway)
    accel_min = c.get("accel_min", 0.0)
    if accel_min and atr > 0:
        accel = abs(osma_now - osma_prev) / atr
        if accel < accel_min:
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": f"weak OsMA accel {accel:.3f} < learned {accel_min:.3f}"}
    dom_min = c.get("dom_min", 0.0)
    if dom_min and atr > 0:
        dom = (float(ind.get("bulls_power") or 0) if direction == "buy"
               else -float(ind.get("bears_power") or 0)) / atr
        if dom < dom_min:
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": f"weak dominant power {dom:.3f} < learned {dom_min:.3f}"}
    runway_min = c.get("runway_min", 0.0)
    osma_avg = float(ind.get("osma_recent_avg") or 0)   # avg |OsMA| over recent bars
    if runway_min and osma_avg > 0:
        runway = abs(osma_now) / osma_avg
        if runway < runway_min:
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": f"low runway {runway:.2f} < learned {runway_min:.2f} (FinalMultiplier)"}
    # ── SIGNED PER-SIDE STRENGTH FLOORS (the core signal: how VIGOROUS buyer/seller
    # activity is). Floors are ATR-NORMALIZED (scale-free) so ONE wide PARAM_SPACE range
    # works for gold (~0.5) and BTC (~15+): the stored floor is in ATR units and scaled
    # by this bar's ATR here. The optimizer + walk-forward DISCOVER them. Default 0 =
    # gate OFF (sign-only). Long floors are MINIMUMS (>=), short floors MAXIMUMS (<=).
    # Bulls>0 AND Bears>0 (long) / Bears<0 AND Bulls<0 (short) stays enforced in soft checks.
    bulls_v = float(ind.get("bulls_power") or 0); bears_v = float(ind.get("bears_power") or 0)
    macd_v = macd
    _a = atr if atr > 0 else 1.0
    # floors_raw=True -> use the stored floor AS-IS (raw units), matching the proven
    # pass5469 backtest (reproduce_pass5469.py) which gates on raw osma/bulls/bears values.
    # Default (False) -> ATR-normalized (stored floor is in ATR units, scaled by this bar's
    # ATR) so one PARAM_SPACE range works across gold/BTC/GER40. XAUUSD is pinned to raw
    # via SYMBOL_BASELINES["XAUUSD"]["floors_raw"]=True so live == the 2.73x backtest.
    _raw = bool(c.get("floors_raw", False))
    def _floor(key):
        v = float(c.get(key, 0.0) or 0.0)
        return v if _raw else v * _a
    if direction == "buy":
        gates = [
            ("osma", osma_now, _floor("osma_min_long"), ">="),
            ("macd", macd_v, _floor("macd_min_long"), ">="),
            ("bulls", bulls_v, _floor("bulls_min_long"), ">="),
            ("bears", bears_v, _floor("bears_min_long"), ">="),
        ]
    else:
        gates = [
            ("osma", osma_now, _floor("osma_max_short"), "<="),
            ("macd", macd_v, _floor("macd_max_short"), "<="),
            ("bears", bears_v, _floor("bears_max_short"), "<="),
            ("bulls", bulls_v, _floor("bulls_max_short"), "<="),
        ]
    for nm, val, floor, op in gates:
        if floor == 0.0:
            continue   # gate off
        if (op == ">=" and val < floor) or (op == "<=" and val > floor):
            return {"action": "hold", "trigger_kind": trigger_kind, "confluence": 0,
                    "reason": f"{nm} strength {val:.3f} fails {op}{floor:.3f} floor"}
    checks = _soft_checks(direction, close, float(ind.get("ema_fast") or close),
                          float(ind.get("ema_prev") or ind.get("ema_fast") or close),
                          atr, float(ind.get("bulls_power") or 0), float(ind.get("bears_power") or 0),
                          float(ind.get("rsi") or 50), c, float(ind.get("med_atr") or 0))
    conf = sum(1 for x in checks if x)
    if conf < c["min_confluence"]:
        return {"action": "hold", "trigger_kind": trigger_kind, "confluence": conf,
                "reason": f"weak confluence {conf}/{len(checks)}"}
    return {"action": direction, "trigger_kind": trigger_kind, "confluence": conf,
            "reason": f"OsMA {trigger_kind} {direction}, confluence {conf}/{len(checks)}"}



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
    anticip_band = c.get("osma_anticipate_atr", 0.15)  # anticipated-cross band (frac of ATR)
    # median ATR for the symbol-agnostic relative volatility floor (#5)
    _atr_vals = [float(a) for a in atr1 if a and a > 0]
    med_atr = (sorted(_atr_vals)[len(_atr_vals) // 2] if _atr_vals else 0.0)
    start = max(c["osma_slow"] + c["osma_signal"], c["ema_period"], 30)
    out = []
    for i in range(start, len(m1) - 1):
        atr = float(atr1[i] or 0)
        if atr <= 0:
            continue
        osma_now = float(osma1[i]); osma_prev = float(osma1[i - 1])
        # CONFIRMED cross
        cu = osma_prev <= 0 < osma_now
        cd = osma_prev >= 0 > osma_now
        # ANTICIPATED cross (#4, KEPT): OsMA still the wrong side but within a band
        # of zero and moving TOWARD it. Tagged so the learning loop evaluates it vs
        # confirmed crosses (kept until there is clear evidence it doesn't work).
        band = anticip_band * atr
        au = (not cu) and (-band <= osma_now <= 0) and (osma_now > osma_prev)
        ad = (not cd) and (0 <= osma_now <= band) and (osma_now < osma_prev)
        if not (cu or cd or au or ad):
            continue
        direction = "buy" if (cu or au) else "sell"
        trigger_kind = "cross" if (cu or cd) else "anticipated"
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
        macd = float(macd1[i]); atr_prev = float(atr1[i - 1] or atr)
        osma_i = float(osma1[i] or 0)
        # HARD gates: MACD aligned (GoldShark parity = main vs SIGNAL line = OsMA sign,
        # NOT vs zero) + ATR expanding. macd_line - signal == OsMA, so use OsMA sign.
        if (direction == "buy" and not osma_i > 0) or (direction == "sell" and not osma_i < 0):
            continue
        if not atr > atr_prev:
            continue
        checks = _soft_checks(direction, closes[i], float(ema1[i]), float(ema1[i - 1]),
                              atr, float(bulls1[i] or 0), float(bears1[i] or 0),
                              float(rsi1[i] or 50), c, med_atr)
        conf = sum(1 for x in checks if x)
        if conf < c["min_confluence"]:
            continue
        ts = times[i]; want = 1 if direction == "buy" else -1
        trig = {"i": i, "direction": direction, "entry": closes[i], "atr": atr,
                "confluence": conf, "trigger_kind": trigger_kind,
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
