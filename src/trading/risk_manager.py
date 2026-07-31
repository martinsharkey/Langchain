"""
RiskManager — Phase 3 master safety layer.

The single gate every entry must pass. Enforces:
  * Kill switch (persisted file — dashboard/user can toggle; halts all new trades)
  * Daily-loss halt — when realized loss for the day reaches a % of the day's
    OPENING balance. Percentage-based so it scales with the account (50% of £100
    demo, or a tighter % of a £50k live account). Auto-resets on a new UTC day so
    "the bot can go again".
  * Max open positions across all symbols
  * Minimum free margin
  * Spread ceiling (optional)

State (start-of-day balance, day key, realized P&L) is persisted so a restart
mid-day keeps the same daily budget rather than resetting it.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from dataclasses import dataclass

from src import config
from src.utils.logger import get_logger

logger = get_logger("risk_manager")

STATE_PATH = os.path.join(config.DATA_DIR, "risk_state.json")


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    halted: bool = False          # True if a hard halt is active (daily loss / kill switch)


class RiskManager:
    def __init__(self, get_account_info, get_open_position_count):
        """
        get_account_info: callable -> dict with balance/equity/free_margin
        get_open_position_count: callable -> int (live open positions)
        """
        self._account = get_account_info
        self._open_count = get_open_position_count
        self.day_key = None
        self.day_open_balance = 0.0
        self.realized_pnl_today = 0.0
        self._halt_reason = None
        self._load()

    # ── persistence ──
    def _load(self):
        try:
            if os.path.exists(STATE_PATH):
                with open(STATE_PATH) as f:
                    s = json.load(f)
                self.day_key = s.get("day_key")
                self.day_open_balance = s.get("day_open_balance", 0.0)
                self.realized_pnl_today = s.get("realized_pnl_today", 0.0)
        except Exception as e:
            logger.debug(f"risk state load skip: {e}")

    def _persist(self):
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump({
                    "day_key": self.day_key,
                    "day_open_balance": self.day_open_balance,
                    "realized_pnl_today": self.realized_pnl_today,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            logger.warning(f"risk state persist failed: {e}")

    # ── daily rollover ──
    def _ensure_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.day_key != today:
            acct = self._account() or {}
            bal = acct.get("balance", 0.0) if isinstance(acct, dict) else 0.0
            self.day_key = today
            self.day_open_balance = float(bal or 0.0)
            self.realized_pnl_today = 0.0
            self._persist()
            logger.info(f"Risk daily reset: {today} open_balance={self.day_open_balance:.2f} "
                        f"(bot can trade again)")

    # ── called by the engine when a trade closes ──
    def record_realized(self, pnl: float):
        self._ensure_day()
        self.realized_pnl_today += float(pnl or 0.0)
        self._persist()

    # ── the gate ──
    def kill_switch_active(self) -> bool:
        return os.path.exists(config.KILL_SWITCH_FILE)

    def daily_loss_limit_value(self) -> float:
        pct = config.effective_daily_loss_pct()
        base = self.day_open_balance or 0.0
        return base * pct / 100.0

    def daily_loss_used(self) -> float:
        """Positive number = how much has been lost today."""
        return max(0.0, -self.realized_pnl_today)

    def is_halted(self) -> tuple[bool, str]:
        if self.kill_switch_active():
            return True, "KILL SWITCH active (remove data/KILL_SWITCH to resume)"
        limit = self.daily_loss_limit_value()
        if limit > 0 and self.daily_loss_used() >= limit:
            return True, (f"Daily loss limit hit: lost {self.daily_loss_used():.2f} "
                          f">= {limit:.2f} ({config.effective_daily_loss_pct()}% of "
                          f"{self.day_open_balance:.2f})")
        return False, ""

    def check_entry(self, spread_points: float = 0.0) -> RiskDecision:
        """Full pre-trade gate. Called before every order."""
        self._ensure_day()

        halted, reason = self.is_halted()
        if halted:
            return RiskDecision(False, reason, halted=True)

        # max open positions
        try:
            open_n = self._open_count()
        except Exception:
            open_n = 0
        if open_n >= config.MAX_OPEN_POSITIONS:
            return RiskDecision(False, f"Max open positions reached ({open_n}/{config.MAX_OPEN_POSITIONS})")

        # free margin
        acct = self._account() or {}
        if isinstance(acct, dict):
            fm = acct.get("free_margin", acct.get("margin_free", None))
            if fm is not None and fm < config.MIN_FREE_MARGIN:
                return RiskDecision(False, f"Free margin too low ({fm:.2f} < {config.MIN_FREE_MARGIN})")

        # spread ceiling (optional)
        if config.MAX_SPREAD_POINTS > 0 and spread_points > config.MAX_SPREAD_POINTS:
            return RiskDecision(False, f"Spread too wide ({spread_points:.0f} > {config.MAX_SPREAD_POINTS} pts)")

        return RiskDecision(True, "ok")

    # ── status for dashboard ──
    def status(self) -> dict:
        halted, reason = self.is_halted()
        limit = self.daily_loss_limit_value()
        used = self.daily_loss_used()
        return {
            "day": self.day_key,
            "day_open_balance": round(self.day_open_balance, 2),
            "daily_loss_limit_pct": config.effective_daily_loss_pct(),
            "daily_loss_limit_value": round(limit, 2),
            "daily_loss_used": round(used, 2),
            "daily_loss_used_pct": round(used / limit * 100, 1) if limit else 0.0,
            "realized_pnl_today": round(self.realized_pnl_today, 2),
            "kill_switch": self.kill_switch_active(),
            "halted": halted,
            "halt_reason": reason,
            "max_open_positions": config.MAX_OPEN_POSITIONS,
        }
