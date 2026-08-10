"""
Per-symbol graduation (#24).

Decides whether a symbol has PROVEN a real edge and may (a) size up beyond the
fixed micro lot and (b) unlock re-enabling a disabled symbol. Graduation is a
STRICTLY HARDER, per-symbol promotion above the Phase-1 edge gate — size only
ever follows proven, realised, per-symbol edge, never a growth target.

States:
  PROVING    building sample / edge unproven -> fixed micro lot
  GRADUATED  edge proven on the best-known config -> eligible for size-up
  PROBATION  was graduated, recently degrading -> pull back to micro, keep trading
  DEMOTED    lost its edge -> back to PROVING

Thresholds are env-driven (defaults below), evaluated on the per-symbol, account-
scoped Edge from EdgeCalculator.compute(symbol). Persists to data/graduation.json.
Safety: SymbolGovernor + ConfigCheckpointer can only LOWER the state, never raise it.
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("graduation")


def _f(env, default):
    try:
        return float(os.getenv(env, str(default)))
    except Exception:
        return default


def _i(env, default):
    try:
        return int(os.getenv(env, str(default)))
    except Exception:
        return default


# graduation thresholds (strictly above the Phase-1 gate)
G_MIN_TRADES = _i("GRAD_MIN_TRADES", 150)
G_MIN_PF = _f("GRAD_MIN_PF", 1.35)
G_MIN_EXP_R = _f("GRAD_MIN_EXPECTANCY_R", 0.10)
G_MAX_DD = _f("GRAD_MAX_DD_PCT", 15.0)
G_MIN_WR = _f("GRAD_MIN_WIN_RATE", 45.0)
G_MAX_STREAK = _i("GRAD_MAX_LOSS_STREAK", 8)
# demotion floor
DEMOTE_PF = _f("DEMOTE_PF_FLOOR", 1.15)


def _path() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "graduation.json")


class Graduation:
    def __init__(self, edge_calculator, checkpointer=None):
        self.edge = edge_calculator
        self.checkpointer = checkpointer
        self._state = self._load()

    def _load(self) -> dict:
        try:
            p = _path()
            if os.path.exists(p):
                with open(p) as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"graduation load skip: {e}")
        return {}

    def _persist(self):
        try:
            p = _path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp, p)
        except Exception as e:
            logger.debug(f"graduation persist skip: {e}")

    def state(self, symbol: str) -> str:
        return (self._state.get(symbol.upper()[:6], {}) or {}).get("state", "PROVING")

    def is_graduated(self, symbol: str) -> bool:
        return self.state(symbol) == "GRADUATED"

    def _meets_graduation(self, e) -> tuple:
        """Return (ok, blocker) for the full graduation gate on an Edge object."""
        checks = [
            ("trades", e.closed_trades >= G_MIN_TRADES),
            ("profit_factor", e.profit_factor >= G_MIN_PF),
            ("expectancy_r", e.expectancy_r >= G_MIN_EXP_R and e.expectancy > 0),
            ("max_drawdown", e.max_drawdown_pct < G_MAX_DD),
            ("win_rate", e.win_rate >= G_MIN_WR),
            ("loss_streak", e.longest_loss_streak <= G_MAX_STREAK),
        ]
        for name, ok in checks:
            if not ok:
                return False, name
        return True, None

    def evaluate(self, symbol: str) -> dict:
        """Recompute the symbol's graduation state from its realised edge."""
        key = symbol.upper()[:6]
        try:
            e = self.edge.compute(symbol=symbol)
        except Exception as ex:
            logger.debug(f"graduation edge compute skip {symbol}: {ex}")
            return {"symbol": key, "state": self.state(symbol), "error": str(ex)}
        prev = self.state(symbol)
        ok, blocker = self._meets_graduation(e)

        if ok:
            new_state = "GRADUATED"
        elif prev in ("GRADUATED", "PROBATION"):
            # was graduated: PROBATION unless it has fully lost the edge -> DEMOTED
            if e.profit_factor < DEMOTE_PF or e.expectancy <= 0:
                new_state = "DEMOTED" if prev == "PROBATION" else "PROBATION"
            else:
                new_state = "PROBATION"
        else:
            new_state = "PROVING"

        rec = {
            "state": new_state, "prev": prev, "blocker": blocker,
            "profit_factor": e.profit_factor, "expectancy": e.expectancy,
            "expectancy_r": e.expectancy_r, "win_rate": e.win_rate,
            "closed_trades": e.closed_trades, "max_drawdown_pct": e.max_drawdown_pct,
            "longest_loss_streak": e.longest_loss_streak,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._state[key] = rec
        self._persist()
        if new_state != prev:
            logger.info(f"[GRADUATION] {key}: {prev} -> {new_state} "
                        f"(PF {e.profit_factor} exp {e.expectancy} n {e.closed_trades} "
                        f"blocker={blocker})")
        return {"symbol": key, **rec}

    def force_probation(self, symbol: str, reason: str = ""):
        """Safety override: governor/checkpointer can only LOWER state."""
        key = symbol.upper()[:6]
        cur = self.state(symbol)
        if cur == "GRADUATED":
            self._state.setdefault(key, {})["state"] = "PROBATION"
            self._state[key]["prev"] = cur
            self._state[key]["blocker"] = f"forced: {reason}"
            self._persist()
            logger.warning(f"[GRADUATION] {key}: GRADUATED -> PROBATION (forced: {reason})")

    def snapshot(self) -> dict:
        return {k: {"state": v.get("state"), "pf": v.get("profit_factor"),
                    "exp": v.get("expectancy"), "n": v.get("closed_trades"),
                    "blocker": v.get("blocker")}
                for k, v in self._state.items()}
