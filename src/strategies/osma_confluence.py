"""
OsMA 7-indicator confluence — LIVE entry strategy (thin adapter, #unify).

This is the strategy REGISTERED and traded live. To eliminate the drift that
previously existed between the live rules and the backtested rules, this file no
longer implements the confluence itself — it is a THIN ADAPTER over the single
source of truth `src.strategies.confluence_signal.evaluate_confluence_bar`, so the
EXACT same rule set is both traded and validated.

The confluence: MACD, OsMA, Bears Power, Bulls Power, EMA, ATR, RSI. OsMA
zero-cross trigger (confirmed OR anticipated — the anticipated-cross is KEPT and
tracked so the learning loop can evaluate it vs confirmed crosses), MACD must lead,
hard gates (MACD aligned + ATR expanding), soft confirmations (EMA slope+price,
ATR range incl. the relative vol floor, price-stretch, Bulls>0&Bears>0 / Bears<0&
Bulls<0, RSI). Confidence = fraction of soft confirmations met (magnitude-scaled
confidence is a tracked follow-up).

Reads the single-bar indicators dict from compute_full_indicators (which carries
osma_prev, osma_recent, ema_prev, atr_prev). `med_atr`/`macd_led` are passed when
available; the live single-bar path can't see the full MACD-lead window, so it
falls back to MACD alignment (the bar-loop backtest enforces the full lead).
"""

from __future__ import annotations

from src.strategies.base import Signal
from src.strategies.confluence_signal import evaluate_confluence_bar
from src.utils.logger import get_logger

logger = get_logger("strategy.osma_confluence")


def osma_confluence_signal(indicators: dict, params: dict) -> Signal:
    """Thin adapter: delegate the confluence decision to the shared rule set."""
    p = params or {}
    close = indicators.get("close")
    if close is None:
        return Signal(action="hold", reason="osma_confluence: no price", confidence=0.0)

    # build the single-bar snapshot the shared evaluator expects
    ind = {
        "close": close,
        "osma": indicators.get("osma", 0.0),
        "osma_prev": indicators.get("osma_prev", 0.0),
        "macd_line": indicators.get("macd_line", 0.0),
        "ema_fast": indicators.get("ema_fast", close),
        "ema_prev": indicators.get("ema_prev", indicators.get("ema_fast", close)),
        "atr": indicators.get("atr", 0.0),
        "atr_prev": indicators.get("atr_prev", indicators.get("atr", 0.0)),
        "bulls_power": indicators.get("bulls_power", 0.0),
        "bears_power": indicators.get("bears_power", 0.0),
        "rsi": indicators.get("rsi", 50.0),
        "med_atr": indicators.get("med_atr", 0.0),
    }
    if "macd_led" in indicators:
        ind["macd_led"] = indicators["macd_led"]

    # runway (FinalMultiplier proxy): |OsMA_now| vs recent average |OsMA| — how far
    # this cross extends beyond the recent baseline. GoldShark's key gold gate.
    _recent = indicators.get("osma_recent") or []
    try:
        _mags = [abs(float(x)) for x in _recent if x is not None]
        if _mags:
            ind["osma_recent_avg"] = sum(_mags) / len(_mags)
    except Exception:
        pass

    r = evaluate_confluence_bar(ind, p)   # single source of truth (backtest == live)
    if r["action"] == "hold":
        return Signal(action="hold", reason=f"osma_confluence: {r['reason']}",
                      confidence=round(r["confluence"] / 5.0, 3))

    n_soft = 5
    base_conf = r["confluence"] / n_soft
    # a confirmed cross is higher conviction than an anticipated one
    if r["trigger_kind"] == "cross":
        base_conf = min(1.0, base_conf + 0.15)
    elif r["trigger_kind"] == "anticipated":
        base_conf *= 0.85   # slightly lower conviction; tracked separately for the loop
    base_conf = round(base_conf, 3)

    return Signal(action=r["action"], confidence=base_conf, price=close,
                  reason=f"OsMA {r['trigger_kind']} {r['action']} | {r['reason']}",
                  metadata={"strategy": "OsMA_Confluence", "trigger": r["trigger_kind"],
                            "confirmations": r["confluence"]})


def register(registry):
    """Register the OsMA confluence strategy (thin adapter over confluence_signal)."""
    registry.register_custom(
        name="OsMA_Confluence",
        signal_fn=osma_confluence_signal,
        description=("PRIMARY 7-indicator confluence (MACD/OsMA/Bulls/Bears/EMA/ATR/RSI) "
                     "via the SHARED confluence_signal rule set (backtest == live). "
                     "OsMA cross (confirmed or anticipated) + MACD-lead + hard gates + "
                     "soft confirmations. Ported from proven GoldShark EAs."),
        indicators_used=["osma", "osma_prev", "macd_line", "ema_fast", "ema_prev",
                         "atr", "atr_prev", "bulls_power", "bears_power", "rsi"],
        suitable_regimes=["trending", "volatile", "ranging", "quiet"],
        min_confidence=0.4,
        weight=1.5,
        status="active",
    )
    logger.info("Registered OsMA_Confluence strategy (thin adapter over confluence_signal; active)")
