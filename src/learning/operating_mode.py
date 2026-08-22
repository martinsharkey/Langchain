"""
OperatingMode — the bot's self-managing TRAINING vs LIVE state, PER SYMBOL.

Removes the manual "loosen entry to gather data / tighten once it works" loop.
The bot decides for itself, from data:

  TRAINING: not enough closed trades yet, or no proven edge. Entry is LOOSENED
            (lower confidence floor, smaller counter-trend penalty) to accumulate
            a real reconciled sample fast. Sizing stays tiny/fixed (no compounding).
  LIVE:     enough sample AND a validated edge (profit factor over the window).
            Entry TIGHTENS to only high-quality/proven setups; this is where the
            bot trades "for real" on what it has learned.

A symbol can also be FORCED to a mode via manual override (dashboard/env) — the
override is respected but visible, so intervention is deliberate, not constant.

Pure decision (testable); the engine consumes `entry_params()` each evaluation.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from src import config
from src.utils.logger import get_logger

logger = get_logger("operating_mode")

TRAINING = "training"
LIVE = "live"
OVERRIDE_PATH = os.path.join(config.DATA_DIR, "mode_overrides.json")

# These are POLICY BOUNDS, not tuned magic numbers: the absolute floor of trades
# below which ANY win rate is statistically meaningless, and the hard cap on how
# far the bot may loosen/tighten its own entry bar. Everything WITHIN these
# bounds is DERIVED from the symbol's own data (see decide_mode). Overridable by
# env only as safety rails.
MIN_TRADES_FLOOR = int(os.getenv("MODE_MIN_TRADES_FLOOR", "20"))   # stats floor
MAX_CONF_ADJ = float(os.getenv("MODE_MAX_CONF_ADJ", "0.15"))       # max loosen/tighten
BREAKEVEN_PF = 1.0                                                  # definition, not a knob


@dataclass
class ModeParams:
    mode: str
    confidence_min: float
    countertrend_penalty: float
    reason: str


def _load_overrides() -> dict:
    try:
        if os.path.exists(OVERRIDE_PATH):
            with open(OVERRIDE_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _required_sample(win_rate: float) -> int:
    """
    DERIVED graduation sample size: how many closed trades are needed before a
    measured edge is statistically distinguishable from a coin-flip, given the
    symbol's OWN win rate. Uses a normal-approx significance heuristic:
    n ≈ p(1-p) / (effect_size^2). A win rate near 50% (little signal) needs more
    trades; a clearly skewed win rate needs fewer. Bounded by the stats floor.
    """
    p = max(0.05, min(0.95, (win_rate or 50.0) / 100.0))
    effect = abs(p - 0.5)
    if effect < 0.02:
        return 200                      # basically a coin flip -> need a lot
    # z~1.64 (90%): n ≈ (z^2 * p(1-p)) / effect^2, scaled to a sane range
    import math
    n = (1.64 ** 2) * p * (1 - p) / (effect ** 2)
    return int(max(MIN_TRADES_FLOOR, min(300, math.ceil(n))))


def decide_mode(symbol: str, closed: int, pf: float, win_rate: float = 50.0,
                pf_stdev: float = 0.0, currently: str = None,
                override: str = None) -> ModeParams:
    """
    Fully DATA-DERIVED decision (no hardcoded thresholds beyond policy bounds):

      * graduation sample size is derived from the symbol's win rate (significance).
      * the PF needed to go LIVE is breakeven (1.0) plus a MARGIN derived from the
        symbol's own PF variability (pf_stdev) — noisier symbols must clear a
        higher bar; stable ones can graduate at a smaller edge.
      * the amount we loosen/tighten scales with how far the symbol is from its
        sample target and edge, capped by MAX_CONF_ADJ.
    """
    base_conf = config.SCALP_CONFIDENCE_MIN
    base_pen = config.MTF_COUNTERTREND_PENALTY

    required = _required_sample(win_rate)
    # edge bar the symbol must beat = breakeven + its own noise margin (>=0.05)
    edge_bar = BREAKEVEN_PF + max(0.05, pf_stdev)
    demote_bar = BREAKEVEN_PF - max(0.05, pf_stdev * 0.5)

    if override in (TRAINING, LIVE):
        mode, reason = override, f"manual override -> {override}"
    elif closed < required:
        mode, reason = TRAINING, f"gathering sample ({closed}/{required}, WR-derived)"
    elif pf >= edge_bar:
        mode, reason = LIVE, f"edge proven (PF {pf} >= {edge_bar:.2f} self-derived, {closed} trades)"
    elif currently == LIVE and pf >= demote_bar:
        mode, reason = LIVE, f"holding LIVE (PF {pf} >= demote {demote_bar:.2f})"
    else:
        mode, reason = TRAINING, f"no edge yet (PF {pf} < {edge_bar:.2f}); keep training"

    if mode == TRAINING:
        # loosen PROPORTIONAL to how far below the sample target we are (more
        # data needed -> loosen more to gather it faster), capped.
        shortfall = max(0.0, 1.0 - (closed / required)) if required else 0.0
        adj = min(MAX_CONF_ADJ, 0.03 + 0.12 * shortfall)
        return ModeParams(TRAINING, round(base_conf - adj, 3),
                          round(base_pen * (1.0 - 0.5 * shortfall), 3), reason)
    # LIVE: tighten PROPORTIONAL to how strong the proven edge is (stronger edge
    # -> can afford to be pickier), capped.
    strength = min(1.0, max(0.0, (pf - edge_bar)))
    adj = min(MAX_CONF_ADJ, 0.03 + 0.10 * strength)
    return ModeParams(LIVE, round(base_conf + adj, 3), base_pen, reason)


class OperatingModeManager:
    def __init__(self, experience_db):
        self.experience_db = experience_db
        self.state: dict = {}   # symbol -> {mode, params, reason, updated_at}
        # Issue #135: anti-thrash hysteresis so a symbol hovering at the mode
        # boundary does not flip every cycle.
        self._transition_hold: dict[str, int] = {}
        self._HYSTERESIS_CYCLES = int(os.getenv("MODE_HYSTERESIS_CYCLES", "5"))

    def _recent(self, symbol: str, window: int = 40):
        import sqlite3, statistics
        conn = sqlite3.connect(self.experience_db.db_path); conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT outcome, profit_loss FROM trades WHERE symbol LIKE ? "
            "AND outcome IN ('win','loss','breakeven') ORDER BY id DESC LIMIT ?",
            (symbol.upper() + "%", window)).fetchall()
        conn.close()
        closed = len(rows)
        wins = sum(1 for r in rows if r["outcome"] == "win")
        win_rate = round(wins / closed * 100, 1) if closed else 50.0
        gw = sum(r["profit_loss"] for r in rows if (r["profit_loss"] or 0) > 0)
        gl = abs(sum(r["profit_loss"] for r in rows if (r["profit_loss"] or 0) < 0))
        pf = round(gw / gl, 2) if gl > 0 else (gw if gw else 0.0)
        # PF variability: split the window into halves/thirds and measure spread,
        # so a symbol whose edge is unstable must clear a higher live bar.
        # Issue #131: use a robust MAD-based estimator instead of raw stddev so a
        # single outlier trade cannot spike the variance and mis-grade the mode.
        pf_stdev = 0.0
        if closed >= 12:
            chunks = [rows[i::3] for i in range(3)]   # interleaved thirds
            pfs = []
            for ch in chunks:
                g = sum(r["profit_loss"] for r in ch if (r["profit_loss"] or 0) > 0)
                loss = abs(sum(r["profit_loss"] for r in ch if (r["profit_loss"] or 0) < 0))
                pfs.append(g / loss if loss > 0 else (g if g else 0.0))
            try:
                med = statistics.median(pfs)
                mad = statistics.median([abs(v - med) for v in pfs]) or 1e-9
                # MAD -> stddev consistent estimator for normal-ish tails
                pf_stdev = round(mad / 0.6745, 3)
            except Exception:
                pf_stdev = 0.0
        return closed, pf, win_rate, pf_stdev

    def params_for(self, symbol: str) -> ModeParams:
        overrides = _load_overrides()
        closed, pf, win_rate, pf_stdev = self._recent(symbol)
        currently = (self.state.get(symbol) or {}).get("mode")
        mp = decide_mode(symbol, closed, pf, win_rate=win_rate, pf_stdev=pf_stdev,
                         currently=currently,
                         override=overrides.get(symbol) or overrides.get("ALL"))
        prev = currently
        # Issue #135: N-cycle hysteresis to prevent thrashing at the boundary.
        hold = self._transition_hold.get(symbol, 0)
        mode_changed = prev and prev != mp.mode
        if mode_changed:
            if hold > 0:
                mp = ModeParams(prev,
                                self.state[symbol]["confidence_min"],
                                self.state[symbol]["countertrend_penalty"],
                                f"hysteresis hold ({hold}/{self._HYSTERESIS_CYCLES}) — was {mp.reason}")
                self._transition_hold[symbol] = hold - 1
            else:
                self._transition_hold[symbol] = self._HYSTERESIS_CYCLES
        else:
            self._transition_hold[symbol] = 0

        self.state[symbol] = {
            "mode": mp.mode, "confidence_min": mp.confidence_min,
            "countertrend_penalty": mp.countertrend_penalty, "reason": mp.reason,
            "closed": closed, "pf": pf, "win_rate": win_rate, "pf_stdev": pf_stdev,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if prev and prev != mp.mode:
            logger.info(f"[MODE] {symbol}: {prev} -> {mp.mode.upper()} ({mp.reason})")
        return mp

    def snapshot(self) -> dict:
        return dict(self.state)
