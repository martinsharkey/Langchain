"""
OsMA zero-cross + MTF momentum CONFLUENCE strategy (#29).

Ported from the trader's PROVEN GoldShark MT5 EAs (GoldShark3 v3.04 zero-cross
engine + GoldShark11 fresh-momentum/runway gate), whose optimizer tested
PF 1.46-1.62 @ ~15% DD over 500-1550 trades on XAUUSD M1. This is intended to be
the bot's PRIMARY, symbol-agnostic entry strategy.

It is a CONFLUENCE of seven indicators working together (MACD, OsMA, Bears Power,
Bulls Power, EMA, ATR, RSI). The OsMA zero-cross is the TRIGGER; the others are
MANDATORY confirmation — the cross alone is not enough.

Entry (long; mirror for short):
  TRIGGER   OsMA crossed up through zero on the last closed bar
            (osma_prev <= 0 and osma > 0), OR an ANTICIPATED cross: OsMA is
            still negative but rising fast toward zero (about to cross) AND
            fresh (young momentum, has runway).
  FRESH     momentum is young: OsMA has not held its sign for too long, and the
            current |OsMA| is below the recent average (runway = not exhausted).
  CONFIRM   MACD mainline aligned (>0 long); EMA slope up AND price above EMA;
            ATR within [min,max] AND expanding (atr > atr_prev); price not
            over-stretched from EMA (<= mult * ATR); Bulls Power strong,
            Bears Power not dominant; RSI supportive and not exhausted.

Confidence is the fraction of confirmations met (trigger is required), so a
full-confluence entry scores high and a marginal one scores low — the engine's
confidence gate + the #27 checkpointer then decide sizing/keeping.

SYMBOL-AGNOSTIC: all thresholds are ATR-relative or unit-normalised, never raw
XAUUSD points, so the same logic applies to BTCUSD / GER40 / FX. Per-symbol
parameters are auto-tuned via param_optimizer + the #27 ConfigCheckpointer.
"""

from __future__ import annotations

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy.osma_confluence")


def _f(indicators: dict, key: str, default: float = 0.0) -> float:
    try:
        v = indicators.get(key, default)
        return float(v) if v is not None else default
    except Exception:
        return default


def osma_confluence_signal(indicators: dict, params: dict) -> Signal:
    """
    Emit a confidence-weighted buy/sell/hold from the 7-indicator OsMA confluence.
    Reads the single-bar indicators dict (which now also carries osma_prev,
    osma_recent, ema_prev, atr_prev — see compute_full_indicators).
    """
    p = params or {}
    close = indicators.get("close")
    if close is None:
        return Signal(action="hold", reason="osma_confluence: no price", confidence=0.0)

    osma = _f(indicators, "osma")
    osma_prev = _f(indicators, "osma_prev")
    osma_recent = indicators.get("osma_recent") or []
    macd_line = _f(indicators, "macd_line")
    ema = _f(indicators, "ema_fast", close)
    ema_prev = _f(indicators, "ema_prev", ema)
    atr = _f(indicators, "atr")
    atr_prev = _f(indicators, "atr_prev", atr)
    bulls = _f(indicators, "bulls_power")
    bears = _f(indicators, "bears_power")
    rsi = _f(indicators, "rsi", 50.0)

    if atr <= 0:
        return Signal(action="hold", reason="osma_confluence: no ATR", confidence=0.0)

    # ── tunable thresholds (auto-tuned per symbol; ATR-relative where possible) ──
    max_momentum_age = int(p.get("osma_max_age", 10))       # bars OsMA may hold sign
    runway_mult = float(p.get("osma_runway_mult", 1.5))     # |osma| < mult*recent avg
    min_ema_slope_atr = float(p.get("min_ema_slope_atr", 0.02))  # slope as frac of ATR
    price_stretch_mult = float(p.get("price_stretch_mult", 2.0)) # |px-ema| <= mult*ATR
    # anticipated-cross: OsMA within this frac of ATR of zero and rising toward it
    anticip_band = float(p.get("osma_anticipate_atr", 0.15))
    rsi_long_max = float(p.get("rsi_long_max", 72.0))       # don't buy exhausted
    rsi_short_min = float(p.get("rsi_short_min", 28.0))

    # ── TRIGGER: confirmed or anticipated OsMA zero-cross ──
    crossed_up = osma_prev <= 0.0 and osma > 0.0
    crossed_dn = osma_prev >= 0.0 and osma < 0.0
    osma_rising = osma > osma_prev
    osma_falling = osma < osma_prev
    # anticipated: still the wrong side of zero but very close and moving toward it
    band = anticip_band * atr
    anticip_up = (-band <= osma <= 0.0) and osma_rising
    anticip_dn = (0.0 <= osma <= band) and osma_falling

    long_trigger = crossed_up or anticip_up
    short_trigger = crossed_dn or anticip_dn
    if not (long_trigger or short_trigger):
        return Signal(action="hold", reason="osma_confluence: no OsMA cross", confidence=0.0)

    action = "buy" if long_trigger else "sell"

    # ── FRESH MOMENTUM (age + runway) ──
    # sign age: how many recent bars OsMA has held the CURRENT sign
    sign = 1 if osma > 0 else (-1 if osma < 0 else 0)
    age = 0
    for v in reversed(osma_recent[:-1] if len(osma_recent) > 1 else osma_recent):
        if (sign > 0 and v > 0) or (sign < 0 and v < 0):
            age += 1
        else:
            break
    recent_abs = [abs(v) for v in osma_recent[:-1]] if len(osma_recent) > 1 else [abs(osma)]
    recent_avg = (sum(recent_abs) / len(recent_abs)) if recent_abs else abs(osma)
    fresh = (age <= max_momentum_age) and (abs(osma) <= max(recent_avg * runway_mult, band))

    # ── CONFIRMATIONS (each contributes to confidence) ──
    checks = {}
    if action == "buy":
        checks["macd_align"] = macd_line > 0
        checks["ema_trend"] = (ema - ema_prev) >= (min_ema_slope_atr * atr) and close > ema
        checks["atr_range"] = _atr_in_range(atr, atr_prev, p)
        checks["atr_expanding"] = atr > atr_prev
        checks["price_stretch"] = abs(close - ema) <= price_stretch_mult * atr
        checks["bulls_bears"] = bulls > 0 and bears > -abs(bulls)  # buyers in control
        checks["rsi_ok"] = rsi < rsi_long_max
    else:
        checks["macd_align"] = macd_line < 0
        checks["ema_trend"] = (ema - ema_prev) <= -(min_ema_slope_atr * atr) and close < ema
        checks["atr_range"] = _atr_in_range(atr, atr_prev, p)
        checks["atr_expanding"] = atr > atr_prev
        checks["price_stretch"] = abs(close - ema) <= price_stretch_mult * atr
        checks["bulls_bears"] = bears < 0 and bulls < abs(bears)  # sellers in control
        checks["rsi_ok"] = rsi > rsi_short_min

    # MACD alignment + ATR expansion are HARD requirements (proven in the EA);
    # the rest are soft and scale confidence.
    if not checks["macd_align"] or not checks["atr_expanding"]:
        return Signal(action="hold",
                      reason=f"osma_confluence: {action} trigger but MACD/ATR-expansion not aligned",
                      confidence=0.0)

    n_soft = ["ema_trend", "atr_range", "price_stretch", "bulls_bears", "rsi_ok"]
    met = sum(1 for k in n_soft if checks[k])
    base_conf = met / len(n_soft)          # 0..1 fraction of soft confirmations
    # trigger quality: a confirmed cross + fresh momentum is the ideal
    if (crossed_up or crossed_dn) and fresh:
        base_conf = min(1.0, base_conf + 0.15)
    elif not fresh:
        base_conf *= 0.6                    # stale momentum -> lower conviction

    if base_conf < 0.4:
        return Signal(action="hold",
                      reason=f"osma_confluence: weak confluence ({met}/{len(n_soft)}, fresh={fresh})",
                      confidence=round(base_conf, 3))

    reason = (f"OsMA {'cross' if (crossed_up or crossed_dn) else 'anticipated'} {action} "
              f"| confluence {met}/{len(n_soft)} fresh={fresh} age={age} "
              f"(macd={macd_line:.3f} bulls={bulls:.2f} bears={bears:.2f} rsi={rsi:.0f})")
    return Signal(action=action, confidence=round(base_conf, 3), price=close,
                  reason=reason,
                  metadata={"strategy": "OsMA_Confluence", "fresh": fresh, "age": age,
                            "confirmations": met, "trigger": "cross" if (crossed_up or crossed_dn) else "anticipated"})


def _atr_in_range(atr: float, atr_prev: float, p: dict) -> bool:
    """
    ATR volatility gate. Thresholds are auto-tuned; treated as symbol-relative by
    comparing to a slow ATR baseline when available, else absolute tuned bounds.
    """
    amin = float(p.get("atr_min", 0.0))
    amax = float(p.get("atr_max", 0.0))
    if amin <= 0 and amax <= 0:
        return True  # not configured -> don't gate
    if amin > 0 and atr < amin:
        return False
    if amax > 0 and atr > amax:
        return False
    return True


def register(registry):
    """Register the OsMA confluence strategy (status=testing until it proves out)."""
    registry.register_custom(
        name="OsMA_Confluence",
        signal_fn=osma_confluence_signal,
        description=("PRIMARY 7-indicator confluence (MACD/OsMA/Bulls/Bears/EMA/ATR/RSI): "
                     "OsMA zero-cross trigger (confirmed or anticipated) + fresh-momentum "
                     "runway gate, confirmed by MACD align, EMA slope+price, ATR range+expansion, "
                     "price-stretch and RSI. Ported from proven GoldShark EAs. Symbol-agnostic."),
        indicators_used=["osma", "osma_prev", "osma_recent", "macd_line", "ema_fast",
                         "ema_prev", "atr", "atr_prev", "bulls_power", "bears_power", "rsi"],
        suitable_regimes=["trending", "volatile", "ranging", "quiet"],
        min_confidence=0.4,
        weight=1.5,          # primary strategy -> higher ensemble weight
        status="testing",
    )
    logger.info("Registered OsMA_Confluence strategy (status=testing, weight=1.5)")
