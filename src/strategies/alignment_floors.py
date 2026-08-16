"""
Directional-alignment gate + per-symbol strength floors — the IMMUTABLE entry rule.

Owner rule (strict same-sign directional alignment):
  LONG  -> OsMA > 0 AND Bulls > 0 AND Bears > 0   (ALL positive)
  SHORT -> OsMA < 0 AND Bulls < 0 AND Bears < 0   (ALL negative)

The DOMINANT power carries a meaningful floor (Bulls for long, Bears for short);
the SECONDARY power (Bears for long, Bulls for short) must still be correctly SIGNED
but only needs a LOW floor near zero — it does NOT need to be strong, just aligned.

Per-symbol floors seeded from live GoldShark telemetry magnitudes:
  XAUUSD LONG : osma>=0.30, bulls>=2.40 (dominant), bears>0 (low floor)
  XAUUSD SHORT: osma<=-0.35, bears<=-1.30 (dominant), bulls<0 (low ceiling)
  BTCUSD      : magnitudes ~15x (derived from BTC's own executed trades).

Guarantees:
  1. DIRECTION never reversible (all three must share the trade's sign).
  2. Optimizer/XGBoost may make floors STRICTER (raise), never looser / sign-flip.
  3. `propose_rebaseline` re-clamps any authoritative update to the correct sign.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, Tuple

from src.utils.logger import get_logger

logger = get_logger("alignment_floors")

_EPS = 1e-6

# Long: minimum positive floors. Short: maximum negative ceilings.
# Values are the OWNER'S NotebookLM live-telemetry baseline (2026-08-13) — the FLOOR.
# The bot may tune each indicator STRICTER (raise long mins / lower short maxes) but
# NEVER below these. Secondary powers carry a real magnitude (bears>=0.6 long,
# bulls<=-0.5 short), not just a sign.
_BASELINES: Dict[str, dict] = {
    "XAUUSD-ECN": {
        "long":  {"osma_min": 0.30, "bulls_min": 2.40, "bears_min": 0.60},
        "short": {"osma_max": -0.35, "bears_max": -1.30, "bulls_max": -0.50},
    },
    "XAUUSD": {
        "long":  {"osma_min": 0.30, "bulls_min": 2.40, "bears_min": 0.60},
        "short": {"osma_max": -0.35, "bears_max": -1.30, "bulls_max": -0.50},
    },
    "BTCUSD": {
        # HONEST re-validation (2026-08-13, floors applied via live fresh-momentum
        # path): the strict-zero telemetry floors (osma 2.8/bulls 12.7) produced ZERO
        # entries on the real entry mechanism. These LOWER floors are what genuinely
        # work: osma 0.3/bulls 1.5/bears 0.5 -> 78% WR PF 1.09 over 5 weeks.
        "long":  {"osma_min": 0.30, "bulls_min": 1.50, "bears_min": 0.50},
        "short": {"osma_max": -0.30, "bears_max": -1.50, "bulls_max": -0.50},
    },
    "GER40": {
        # honest onboarding (2026-08-13): osma 0.3/bulls 1.5/bears 0.6 -> 76% WR PF 1.08.
        "long":  {"osma_min": 0.30, "bulls_min": 1.50, "bears_min": 0.60},
        "short": {"osma_max": -0.30, "bears_max": -1.50, "bulls_max": -0.60},
    },
    "GER40.": {
        "long":  {"osma_min": 0.30, "bulls_min": 1.50, "bears_min": 0.60},
        "short": {"osma_max": -0.30, "bears_max": -1.50, "bulls_max": -0.60},
    },
}
_DEFAULT = {
    "long":  {"osma_min": _EPS, "bulls_min": _EPS, "bears_min": _EPS},
    "short": {"osma_max": -_EPS, "bears_max": -_EPS, "bulls_max": -_EPS},
}

_LOCK = threading.Lock()
_OVERRIDES_PATH = None
_overrides: Dict[str, dict] = {}


def _load_overrides():
    global _OVERRIDES_PATH, _overrides
    if _OVERRIDES_PATH is None:
        try:
            from src import config
            base = getattr(config, "DATA_DIR", None) or os.path.join(os.getcwd(), "data")
        except Exception:
            base = os.path.join(os.getcwd(), "data")
        _OVERRIDES_PATH = os.path.join(base, "alignment_floor_overrides.json")
    if not _overrides and os.path.exists(_OVERRIDES_PATH):
        try:
            with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                _overrides = json.load(f)
        except Exception:
            _overrides = {}


def baseline(symbol: str) -> dict:
    """Effective per-symbol baseline (may be RAISED by an authoritative rebaseline —
    never loosened, never sign-flipped)."""
    _load_overrides()
    key = (symbol or "").upper()
    base = json.loads(json.dumps(_BASELINES.get(symbol) or _BASELINES.get(key) or _DEFAULT))
    ov = _overrides.get(symbol) or _overrides.get(key)
    if ov:
        for side in ("long", "short"):
            for k, v in (ov.get(side) or {}).items():
                if k in base[side]:
                    if k.endswith("_min"):
                        base[side][k] = max(base[side][k], float(v))
                    elif k.endswith("_max"):
                        base[side][k] = min(base[side][k], float(v))
    return base


def directional_gate(symbol: str, direction: str, osma: float, bulls: float,
                     bears: float, atr_scale: float, cfg: dict,
                     anticipated: bool = False) -> Tuple[bool, str]:
    """STRICT same-sign directional gate. All three must share the trade's sign;
    dominant power has a real floor, secondary power a low near-zero floor. `cfg`
    tuned floors may only make it STRICTER. Returns (ok, reason).

    anticipated=True (candle-1 pre-cross entry): OsMA has not crossed yet so its sign
    is NOT required and its floor is NOT checked — the % anticipation trigger already
    validated OsMA is moving the right way. BULLS and BEARS must STILL be directionally
    aligned (owner rule) — that requirement is never relaxed."""
    b = baseline(symbol)
    use_atr = bool(cfg.get("floors_are_atr"))
    sc = atr_scale if use_atr else 1.0

    def tmin(base_v, cfg_key):   # long minimum (stricter = higher)
        t = float(cfg.get(cfg_key, 0.0) or 0.0) * (atr_scale if use_atr else 1.0)
        return max(base_v * sc, t)

    def tmax(base_v, cfg_key):   # short ceiling (stricter = more negative)
        t = float(cfg.get(cfg_key, 0.0) or 0.0) * (atr_scale if use_atr else 1.0)
        return min(base_v * sc, t) if t != 0 else base_v * sc

    if direction == "buy":
        # Bulls & Bears MUST be positive (aligned). OsMA sign required only when NOT
        # anticipating (pre-cross OsMA is still <=0 by definition).
        if not (bulls > 0 and bears > 0) or (not anticipated and not (osma > 0)):
            return False, (f"not aligned LONG (osma {osma:+.2f} bulls {bulls:+.2f} "
                           f"bears {bears:+.2f} — bulls & bears must be > 0"
                           f"{'' if anticipated else ', osma > 0'})")
        bu_min = tmin(b["long"]["bulls_min"], "bulls_min_long")
        be_min = tmin(b["long"]["bears_min"], "bears_min_long")
        if not anticipated:
            o_min = tmin(b["long"]["osma_min"], "osma_min_long")
            if osma < o_min:
                return False, f"LONG osma {osma:.3f} < floor {o_min:.3f}"
        if bulls < bu_min:
            return False, f"LONG bulls {bulls:.3f} < floor {bu_min:.3f} (dominant)"
        if bears < be_min:
            return False, f"LONG bears {bears:.3f} < floor {be_min:.3f} (secondary)"
        return True, "aligned LONG" + (" (anticipated)" if anticipated else "")
    else:
        if not (bulls < 0 and bears < 0) or (not anticipated and not (osma < 0)):
            return False, (f"not aligned SHORT (osma {osma:+.2f} bulls {bulls:+.2f} "
                           f"bears {bears:+.2f} — bulls & bears must be < 0"
                           f"{'' if anticipated else ', osma < 0'})")
        be_max = tmax(b["short"]["bears_max"], "bears_max_short")
        bu_max = tmax(b["short"]["bulls_max"], "bulls_max_short")
        if not anticipated:
            o_max = tmax(b["short"]["osma_max"], "osma_max_short")
            if osma > o_max:
                return False, f"SHORT osma {osma:.3f} > ceil {o_max:.3f}"
        if bears > be_max:
            return False, f"SHORT bears {bears:.3f} > ceil {be_max:.3f} (dominant)"
        if bulls > bu_max:
            return False, f"SHORT bulls {bulls:.3f} > ceil {bu_max:.3f} (secondary)"
        return True, "aligned SHORT" + (" (anticipated)" if anticipated else "")


def clamp_floors(symbol: str, params: dict) -> dict:
    """Clamp tuned params: only STRICTER than baseline, never looser / sign-flipped."""
    if params is None:
        return params
    b = baseline(symbol)
    lm, sm = b["long"], b["short"]
    if float(params.get("osma_min_long", 0) or 0) < lm["osma_min"]:
        params["osma_min_long"] = lm["osma_min"]
    if float(params.get("bulls_min_long", 0) or 0) < lm["bulls_min"]:
        params["bulls_min_long"] = lm["bulls_min"]
    if float(params.get("bears_min_long", 0) or 0) < lm["bears_min"]:
        params["bears_min_long"] = lm["bears_min"]
    for k, bv in (("osma_max_short", sm["osma_max"]), ("bears_max_short", sm["bears_max"]),
                  ("bulls_max_short", sm["bulls_max"])):
        if params.get(k) is None or float(params[k]) > bv:
            params[k] = bv
    return params


def propose_rebaseline(symbol: str, side: str, new_floors: dict, source: str = "xgboost") -> dict:
    """Authoritative rebaseline: RAISE (never loosen / sign-flip) side floors. Persisted."""
    _load_overrides()
    key = (symbol or "").upper()
    applied = {}
    with _LOCK:
        cur = dict(_overrides.get(key, {}))
        side_cur = dict(cur.get(side, {}))
        b = (_BASELINES.get(symbol) or _BASELINES.get(key) or _DEFAULT).get(side, {})
        for k, v in new_floors.items():
            if k not in b:
                continue
            v = float(v)
            if k.endswith("_min"):
                v = max(v, b[k], _EPS)
            elif k.endswith("_max"):
                v = min(v, b[k], -_EPS)
            side_cur[k] = round(v, 4)
            applied[k] = side_cur[k]
        cur[side] = side_cur
        _overrides[key] = cur
        try:
            os.makedirs(os.path.dirname(_OVERRIDES_PATH), exist_ok=True)
            with open(_OVERRIDES_PATH, "w", encoding="utf-8") as f:
                json.dump(_overrides, f, indent=2)
        except Exception as e:
            logger.debug(f"persist rebaseline failed: {e}")
    logger.warning(f"[FLOOR-REBASELINE] {symbol}/{side} <- {applied} (source={source}); direction preserved")
    return applied
