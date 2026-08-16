"""
Golden baseline — the OWNER-PROVEN configuration and the PERMANENT fallback floor.

Purpose (owner directive 2026-08-13): the frequency-starvation revert and the
config checkpointer used to fall back to a "last known firing" config that was
actually a WEAK config, silently undoing hand-tuned values. Instead, everything
that reverts/falls back must land on THIS golden baseline — the proven values the
owner tuned by hand — never a weaker one.

Guarantees:
  * `golden(symbol)` returns the proven entry floors + exit geometry for a symbol.
  * Auto-tuning may only make floors STRICTER than these (via alignment_floors),
    and any revert/starvation fallback restores exactly these values.
  * The starvation guard still protects against a config so tight it stops trading,
    but its fallback is the golden baseline (which DOES trade), not a weak config.

Update this ONLY when the owner promotes a new proven baseline.
"""

from __future__ import annotations
from typing import Optional

# Proven per-symbol config (2026-08-13). Entry: strict directional alignment with
# these floors; Exit: wide fixed SL, break-even, trail-activation, trail-distance,
# NO fixed TP. Values are the owner's hand-tuned, backtest-confirmed baseline
# (XAUUSD: 77-84% WR, PF 1.23-1.37, generalising).
GOLDEN = {
    "XAUUSD-ECN": {
        # entry floors (owner NotebookLM live-telemetry baseline 2026-08-13). The bot
        # tunes STRICTER from here per indicator, never below.
        "osma_min_long": 0.30, "bulls_min_long": 2.40, "bears_min_long": 0.60,
        "osma_max_short": -0.35, "bears_max_short": -1.30, "bulls_max_short": -0.50,
        # exit geometry (points) — wide SL, BE, trail-activate, trail-distance, no TP
        "sl_min_points": 500, "be_trigger_points": 150,
        "trail_activate_points": 250, "trail_points": 150,
    },
}
# alias
GOLDEN["XAUUSD"] = GOLDEN["XAUUSD-ECN"]


def golden(symbol: str) -> Optional[dict]:
    if not symbol:
        return None
    return GOLDEN.get(symbol) or GOLDEN.get(symbol.upper())


def golden_entry_floors(symbol: str) -> dict:
    g = golden(symbol) or {}
    return {k: g[k] for k in ("osma_min_long", "bulls_min_long", "bears_min_long",
                              "osma_max_short", "bears_max_short", "bulls_max_short") if k in g}
