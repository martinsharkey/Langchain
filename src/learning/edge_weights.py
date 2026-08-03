"""
Per-symbol backtest-derived edge map.

CRITICAL: edge is SYMBOL-SPECIFIC. The same indicator combo that wins on gold
loses on an index (e.g. Volume_Breakout PF 1.32 on XAUUSD but 0.91 on GER40).
So weights are keyed by symbol, applied at ensemble vote time. Unlisted
symbols/strategies default to neutral (1.0).

Values are OUT-OF-SAMPLE profit-factor-derived multipliers from the edge sweep
(tools/edge_sweep) on Jan-onward MT5 history. The live L2 learning loop adapts
from these seeds. Re-run the sweep to refresh as more data accrues.

Match is by symbol PREFIX (XAUUSD-ECN matches 'XAUUSD').

RUNTIME OVERLAY (#31): a machine-local data/edge_weights.json, produced by the
automated per-symbol edge-discovery sweep (edge_discovery.py), is merged OVER
these static seeds at import. This lets NEW symbols get validated edges without
hand-editing this file. Discovered entries win; static dicts are the fallback.
"""

import os
import json
import logging

_log = logging.getLogger("edge_weights")


def _overlay_path() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "edge_weights.json")


def _load_overlay() -> dict:
    """Load the discovered edge overlay {edge_weights, regime_edge, focused_edge}."""
    try:
        p = _overlay_path()
        if os.path.exists(p):
            with open(p) as f:
                data = json.load(f)
            _log.info(f"edge_weights overlay loaded from {p} "
                      f"({len(data.get('edge_weights', {}))} symbols)")
            return data or {}
    except Exception as e:
        _log.warning(f"edge_weights overlay load failed: {e}")
    return {}


_OVERLAY = _load_overlay()

EDGE_WEIGHTS_BY_SYMBOL = {
    # XAUUSD-ECN M15 evidence: Volume_Breakout 1.32, BB_Bounce 1.15,
    # CCI_Breakout 1.13, RSI_MeanReversion 1.10, MACD_OsMA_Power 1.08,
    # ADX 1.07; losers: BB_SqueezeBreakout 0.75, Stochastic 0.95, MACD_Cross ~1.0
    "XAUUSD": {
        "Volume_Breakout": 2.5,
        "BB_Bounce": 1.8,
        "CCI_Breakout": 1.7,
        "RSI_MeanReversion": 1.4,
        "OsMA_Confluence": 1.3,
        "ADX_TrendStrength": 1.2,
        "EMA_TrendFollow": 1.1,
        "RSI_Momentum": 0.7,
        "MACD_Cross": 0.6,
        "GoldenCross_50_200": 0.5,
        "Stochastic_Reversal": 0.4,
        "BB_SqueezeBreakout": 0.3,
    },
    # GER40 M15 evidence: MACD_Momentum 1.02, MACD_Cross 1.02, CCI 1.06,
    # BB_SqueezeBreakout 1.2, MACD_OsMA_Power 1.05; losers: RSI_MeanReversion 0.79,
    # Volume_Breakout 0.91, BB_Bounce 0.91, RSI_Momentum 0.95
    "GER40": {
        "BB_SqueezeBreakout": 1.6,
        "CCI_Breakout": 1.4,
        "OsMA_Confluence": 1.3,
        "MACD_Cross": 1.2,
        "MACD_Momentum": 1.2,
        "Volume_Breakout": 0.5,
        "BB_Bounce": 0.5,
        "RSI_MeanReversion": 0.3,
        "RSI_Momentum": 0.6,
    },
}


def edge_weight(symbol: str, strategy: str) -> float:
    """Per-symbol edge multiplier for a strategy (prefix match); 1.0 if unknown.
    Discovered overlay (#31) wins over the static seed."""
    if not symbol:
        return 1.0
    su = symbol.upper()
    ov = _OVERLAY.get("edge_weights", {})
    for key, table in ov.items():
        if su.startswith(key) and strategy in table:
            return float(table.get(strategy, 1.0))
    for key, table in EDGE_WEIGHTS_BY_SYMBOL.items():
        if su.startswith(key):
            return float(table.get(strategy, 1.0))
    return 1.0


# ── Regime-conditioned edge (from _regime_sweep, XAUUSD-ECN M15) ──
# A strategy's edge often lives in ONE regime. Volume_Breakout is PF 2.1 in
# VOLATILE but weaker elsewhere; BB_Bounce is PF 1.54 in RANGING but ~1.0
# trending. This nested map {symbol: {strategy: {regime: mult}}} lets the
# ensemble boost a strategy in its proven regime and cut it in bad ones.
REGIME_EDGE = {
    "XAUUSD": {
        "Volume_Breakout":            {"volatile": 1.6, "trending": 1.2, "ranging": 0.5, "quiet": 0.6},
        "BB_Bounce":                  {"ranging": 1.6,  "volatile": 1.0, "trending": 0.8, "quiet": 1.0},
        "CCI_Breakout":               {"volatile": 1.2, "trending": 1.2, "ranging": 1.0, "quiet": 0.9},
        "RSI_MeanReversion":          {"trending": 1.2, "volatile": 1.0, "ranging": 0.9, "quiet": 0.9},
        "ADX_TrendStrength":          {"trending": 1.3, "volatile": 0.7, "ranging": 0.7, "quiet": 0.8},
        "OsMA_Confluence":            {"trending": 1.3, "ranging": 0.8, "volatile": 0.7, "quiet": 0.8},
    },
}


def regime_edge_weight(symbol: str, strategy: str, regime: str) -> float:
    """Multiplier for a strategy in a given regime on a symbol; 1.0 if unknown.
    Discovered overlay (#31) wins over the static seed."""
    if not symbol or not regime:
        return 1.0
    su = symbol.upper()
    ov = _OVERLAY.get("regime_edge", {})
    for key, table in ov.items():
        if su.startswith(key):
            r = table.get(strategy)
            if r and regime in r:
                return float(r.get(regime, 1.0))
    for key, table in REGIME_EDGE.items():
        if su.startswith(key):
            r = table.get(strategy)
            if r:
                return float(r.get(regime, 1.0))
    return 1.0


# ── FOCUSED high-edge pockets (validated on history) ──
# Backtest proof (XAUUSD-ECN M15, out-of-sample): trading ONLY these
# strategy×regime pockets gives PF 1.24 (vs 1.04 for the full ensemble), and
# PF 1.46 / R 94 with a wide 3.0-ATR take-profit. Concentration + letting
# winners run beats voting everything. {symbol_prefix: [(strategy, {regimes})]}
#
# WALK-FORWARD VALIDATION (reconciled system SL=1.0ATR/RR=2.0/giveback=0.55,
# 3 sequential windows). GENERALIZES = PF>=1.0 in all 3 windows:
#   XAUUSD-ECN M15: PF [1.16, 1.00, 1.34]  -> GENERALIZES (primary, robust)
#   XAUUSD-ECN M5:  PF [1.15, 1.04, 1.13]  -> GENERALIZES
#   GER40 M5:       PF [1.01, 1.16, 1.06]  -> GENERALIZES (M5 only)
#   XAUUSD H1, GER40 M15, GER40 H1         -> INCONSISTENT (do not trust)
# Engine trades M15, so XAUUSD-ECN M15 is the validated primary. GER40 M15 is
# NOT validated — its focused rules stay but the researcher auto-pause governs
# it (quarantines if it bleeds live).
FOCUSED_EDGE = {
    # XAUUSD now trades ONLY the proven 7-indicator confluence (OsMA_Confluence),
    # the single source of truth in confluence_signal.py. The old grab-bag
    # (Volume_Breakout/BB_Bounce/CCI_Breakout) is retired: it did not consume the
    # tuned osma_/ema_/atr_ params, so the optimizer could not validate it (1a/1c).
    # Re-run edge-discovery/walk-forward before trusting this pocket live.
    "XAUUSD": [
        ("OsMA_Confluence", {"trending", "volatile", "ranging", "quiet"}),
    ],
    # GER40: unvalidated on M15 (walk-forward inconsistent). Consolidated onto the
    # SAME confluence implementation as XAUUSD (1b) — the third, lighter-weight
    # MACD_OsMA_Power_Confluence is deleted so there is ONE confluence everywhere.
    # Still auto-pause-governed (quarantines if it bleeds live).
    "GER40": [
        ("OsMA_Confluence", {"trending", "volatile"}),
    ],
}


def focused_rules(symbol: str):
    """Return the list of (strategy, allowed_regimes) pockets for a symbol, or None.
    Discovered overlay (#31) wins over the static seed."""
    if not symbol:
        return None
    su = symbol.upper()
    ov = _OVERLAY.get("focused_edge", {})
    for key, rules in ov.items():
        if su.startswith(key):
            # overlay stores [[strategy, [regimes]], ...] (JSON) -> normalise
            return [(r[0], set(r[1])) for r in rules]
    for key, rules in FOCUSED_EDGE.items():
        if su.startswith(key):
            return rules
    return None


def reload_overlay():
    """Re-read data/edge_weights.json at runtime (after a sweep writes it)."""
    global _OVERLAY
    _OVERLAY = _load_overlay()
    return _OVERLAY


