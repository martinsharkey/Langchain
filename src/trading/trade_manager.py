"""
Trade Manager — manages OPEN positions, and does so as a LEARNING EXPERIMENT.

Per your directive: don't hardcode the "right" way to manage a trade — let the
bot TRIAL competing management styles per symbol and let the learning loop pick
winners from real outcomes.

Each open trade is assigned a MANAGEMENT VARIANT (an A/B/C experiment arm):

  BE_PLUS_TRAIL  — wait for a profit buffer, then move SL to break-even+ (in
                   profit so spread noise can't stop it flat), then trail to a
                   "less destructive" distance. (Your gold concern, done right.)
  TRAIL_ONLY     — never move to BE; trail at an ATR distance once in profit.
  SCALP_FIXED    — take profit quickly at the fixed scalp target, hard SL, no BE.
  HYBRID_LLM     — deterministic fast reactions, but an LLM review can widen/tighten
                   or exit based on context (slower; trialled against the rest).

Every management action and the final outcome is tagged with the variant + symbol,
written to the experience DB, so we can measure which variant wins per symbol and
shift future assignment toward it. THIS is the visible learning-behaviour change.

Broker-side SL is ALWAYS set on entry (handled by the engine via BrokerAdapter);
this manager only MODIFIES the existing broker SL — it never leaves a trade naked.
"""

from __future__ import annotations

import time
import random
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("trade_manager")

# Experiment arms
VARIANTS = ("BE_PLUS_TRAIL", "TRAIL_ONLY", "SCALP_FIXED", "HYBRID_LLM")


@dataclass
class ManagedState:
    ticket: int
    symbol: str
    base_symbol: str
    action: str                # buy|sell
    entry: float
    volume: float
    sl: float
    tp: float
    point: float
    atr_points: float          # typical move on entry timeframe (for trailing distance)
    variant: str
    opened_at: float
    moved_to_be: bool = False
    trail_active: bool = False
    best_price: float = 0.0    # most favourable price seen (for trailing)
    actions: list = field(default_factory=list)
    last_llm_review: float = 0.0   # epoch of last HYBRID_LLM review (throttle)
    peak_profit_points: float = 0.0  # best unrealized profit (points) ever seen
    trend_aligned: bool = False      # entry aligned with higher-TF trend (ride mode)
    htf_widened: bool = False        # HTF-blip stop-widen already applied (once)


class TradeManager:
    """
    Decides SL modifications / early exits for open positions.

    Pure logic: given the current price + state, returns an intent:
      {"modify_sl": price} | {"close": reason} | None
    The engine executes the intent via BrokerAdapter (broker-side).
    """

    def __init__(self, experience_db=None, get_variant_weights=None,
                 get_symbol_personality=None):
        self.experience_db = experience_db
        # optional callable(symbol) -> {variant: weight} so learning biases selection
        self.get_variant_weights = get_variant_weights
        # optional callable(base_symbol) -> personality dict, learned per symbol:
        #   {"style": "aggressive_scalper"|"trend_rider", "giveback_frac": float,
        #    "giveback_arm_points": float}
        self.get_symbol_personality = get_symbol_personality

    def _personality(self, st) -> dict:
        base = getattr(st, "base_symbol", "") or ""
        if self.get_symbol_personality:
            try:
                p = self.get_symbol_personality(base)
                if p:
                    return p
            except Exception:
                pass
        return {}

    def giveback_fraction(self, st) -> float:
        """
        Fraction of peak profit we allow a winner to give back before cutting.
        Aggressive scalper -> cut fast (small fraction); trend rider -> tolerate more.
        Learned per symbol; sensible default otherwise.
        """
        p = self._personality(st)
        if "giveback_frac" in p:
            # never let a learned personality cut winners on tiny pullbacks:
            # realised data showed the manager was giving back winners into
            # small losers (only 5 TP hits vs 198 early closes). Floor the
            # learned value so "let winners run" is the bias, not "scratch fast".
            return max(float(p["giveback_frac"]), 0.5)
        style = p.get("style")
        if style == "aggressive_scalper":
            return 0.55
        if style == "trend_rider":
            return 0.75
        # neutral default: backtest-tuned (loosening giveback from 0.45 lifted PF)
        try:
            from src import config
            return config.SCALP_GIVEBACK_FRAC
        except Exception:
            return 0.6

    def giveback_arm_points(self, st) -> float:
        """
        Minimum peak profit (points) before the giveback guard activates.

        Realised data showed the guard was arming at just 0.5*ATR of profit and
        firing ~198 times, cutting would-be TP runners into tiny scratches
        (placed RR ~2.0 but realised payoff ~0.7). Arm it MUCH later so it only
        protects genuinely large winners and lets normal trades reach TP.
        """
        p = self._personality(st)
        if "giveback_arm_points" in p:
            return float(p["giveback_arm_points"])
        try:
            from src import config
            mult = config.SCALP_GIVEBACK_ARM_ATR
        except Exception:
            mult = 1.5
        # default: ~1.5x the typical move on the entry timeframe (was 0.5x)
        return (st.atr_points or 60) * mult

    # ── variant assignment (learning biases this over time) ──
    def assign_variant(self, symbol: str) -> str:
        weights = None
        if self.get_variant_weights:
            try:
                weights = self.get_variant_weights(symbol)
            except Exception:
                weights = None
        if weights:
            # weighted random choice — exploit winners but keep exploring
            arms = list(weights.keys())
            w = [max(weights[a], 0.01) for a in arms]
            return random.choices(arms, weights=w, k=1)[0]
        # cold start: uniform exploration across all arms
        return random.choice(VARIANTS)

    def register(self, pos, atr_points: float, trend_aligned: bool = False) -> ManagedState:
        variant = self.assign_variant(pos.base_symbol)
        st = ManagedState(
            ticket=pos.ticket, symbol=pos.symbol, base_symbol=pos.base_symbol,
            action=pos.action, entry=pos.entry_price, volume=pos.volume,
            sl=pos.sl or 0.0, tp=pos.tp or 0.0, point=0.0, atr_points=atr_points,
            variant=variant, opened_at=time.time(), best_price=pos.entry_price,
            trend_aligned=trend_aligned,
        )
        logger.info(f"Trade {pos.ticket} ({pos.base_symbol}) managed with "
                    f"variant={variant} trend_aligned={trend_aligned}")
        return st

    # ── the per-cycle decision ──
    def evaluate(self, st: ManagedState, price: float, point: float,
                 spread_points: float) -> Optional[dict]:
        """
        Return an intent dict or None. Called each cycle with the live price.
        Distances are in price units; point converts to/from points.
        """
        st.point = point or st.point
        if st.action == "buy":
            profit_points = (price - st.entry) / point if point else 0
            st.best_price = max(st.best_price, price)
            fav_points = (st.best_price - st.entry) / point if point else 0
        else:
            profit_points = (st.entry - price) / point if point else 0
            st.best_price = min(st.best_price, price)
            fav_points = (st.entry - st.best_price) / point if point else 0

        v = st.variant

        # Common capital-preservation: if price violently reverses past a hard
        # threshold beyond entry against us, exit (applies to all variants).
        adverse_points = -profit_points
        violent = st.atr_points and adverse_points > max(st.atr_points * 1.5, 2 * spread_points + 50)
        if violent:
            self._log(st, "capital_preservation_exit", price)
            return {"close": f"violent reversal ({adverse_points:.0f}pts adverse)"}

        # ── P&L-TRAJECTORY GIVEBACK GUARD (the AI edge: watch the live winner) ──
        # Track the best profit this trade ever showed. If it ran meaningfully
        # into profit and is now handing a large fraction of it back, it is a
        # winner rolling into a loser — cut it. The giveback fraction and the
        # minimum peak to arm it are per-symbol, learned/tunable via config.
        st.peak_profit_points = max(st.peak_profit_points, profit_points)
        arm_peak = max(self.giveback_arm_points(st), spread_points + 15)
        if st.peak_profit_points >= arm_peak and profit_points > 0:
            giveback_frac = self.giveback_fraction(st)
            # ride mode: if aligned with the higher-TF trend, tolerate more giveback
            if st.trend_aligned:
                giveback_frac = min(giveback_frac + 0.2, 0.9)
            # TP-awareness: if the trade is still on its way to a much larger TP
            # and hasn't yet reached most of that target, don't scratch it on a
            # normal pullback — let the pre-set RR play out. Only the giveback
            # guard (not the broker TP) was cutting winners early.
            if st.tp and point:
                tp_points = abs(st.tp - st.entry) / point
                if tp_points > 0 and st.peak_profit_points < 0.6 * tp_points:
                    # peak is still well short of TP — require a BIG giveback to cut
                    giveback_frac = max(giveback_frac, 0.8)
            given_back = (st.peak_profit_points - profit_points) / st.peak_profit_points
            if given_back >= giveback_frac:
                self._log(st, "giveback_exit", price)
                return {"close": (f"winner rolling over: gave back {given_back:.0%} of peak "
                                  f"{st.peak_profit_points:.0f}pts")}

        if v == "SCALP_FIXED":
            return None  # rely on broker TP/SL only

        if v in ("BE_PLUS_TRAIL", "HYBRID_LLM"):
            # Both share the fast, deterministic protection (BE+ then trail).
            # HYBRID_LLM ADDITIONALLY gets a throttled LLM review, applied by the
            # engine (see llm_review_due) — that is what makes it a distinct arm.
            # 1) move to BE+ only after a real profit buffer (avoid premature BE)
            buffer_pts = max(1.5 * spread_points + 30, st.atr_points * 0.5 if st.atr_points else 30)
            if not st.moved_to_be and profit_points >= buffer_pts:
                be_plus = st.entry + (spread_points + 10) * point * (1 if st.action == "buy" else -1)
                st.moved_to_be = True
                st.trail_active = True
                self._log(st, "move_to_be_plus", be_plus)
                return {"modify_sl": round(be_plus, 6)}
            # 2) once trailing, follow at a "less destructive" distance
            if st.trail_active:
                trail_dist = max((st.atr_points or 60) * 0.6, spread_points + 20) * point
                new_sl = (st.best_price - trail_dist) if st.action == "buy" else (st.best_price + trail_dist)
                if self._sl_improves(st, new_sl):
                    st.sl = new_sl
                    self._log(st, "trail_sl", new_sl)
                    return {"modify_sl": round(new_sl, 6)}
            return None

        if v == "TRAIL_ONLY":
            # trail from the start once any profit exists
            if profit_points > (spread_points + 10):
                trail_dist = max((st.atr_points or 60) * 0.8, spread_points + 25) * point
                new_sl = (st.best_price - trail_dist) if st.action == "buy" else (st.best_price + trail_dist)
                if self._sl_improves(st, new_sl):
                    st.sl = new_sl
                    self._log(st, "trail_sl", new_sl)
                    return {"modify_sl": round(new_sl, 6)}
            return None

        return None

    def preclose_decision(self, st: ManagedState, price: float, point: float,
                          spread_points: float, atr_points_short: float) -> Optional[dict]:
        """
        Decision when a symbol is 15–30 min from a session close.

        Rules (per the trader's directive):
          * Profitable SHORT-TERM trade at wick risk over the gap → CLOSE to lock it.
          * Losing trade → KEEP (don't crystallize a loss) unless already flagged
            as a violent turn (handled separately in evaluate()).
          * Long-running trade (open for days) in profit → LET IT RUN, but WIDEN the
            trailing SL so a large gap/wick candle doesn't stop it out.
        """
        if st.action == "buy":
            profit_points = (price - st.entry) / point if point else 0
        else:
            profit_points = (st.entry - price) / point if point else 0

        age_hours = (time.time() - st.opened_at) / 3600.0
        long_running = age_hours >= 24  # days/weeks trade

        # profitable enough to be worth protecting (beyond spread noise)
        in_profit = profit_points > (spread_points + 10)

        if long_running and in_profit:
            # let it run, but widen the protective stop against gap wicks
            widen = max((atr_points_short or 60) * 2.0, spread_points + 100) * point
            new_sl = (price - widen) if st.action == "buy" else (price + widen)
            if self._sl_improves(st, new_sl):
                self._log(st, "preclose_widen_sl_longrun", new_sl)
                return {"modify_sl": round(new_sl, 6)}
            return None

        if in_profit and not long_running:
            # short-term winner at wick risk over the gap → lock it in
            self._log(st, "preclose_close_shortterm_winner", price)
            return {"close": "pre-close: lock short-term profit before session gap"}

        # losing or breakeven short-term trade → keep (unless violent turn caught in evaluate)
        return None

    def llm_review_due(self, st: ManagedState, interval_sec: int = 180) -> bool:
        """True if a HYBRID_LLM position is due for its throttled LLM review."""
        if st.variant != "HYBRID_LLM":
            return False
        now = time.time()
        if now - st.last_llm_review >= interval_sec:
            st.last_llm_review = now
            return True
        return False

    def _sl_improves(self, st: ManagedState, new_sl: float) -> bool:
        """Only ever move SL in the protective direction (never widen risk)."""
        if st.sl == 0:
            return True
        return new_sl > st.sl if st.action == "buy" else new_sl < st.sl

    def _log(self, st: ManagedState, action: str, price: float):
        st.actions.append({"t": time.time(), "action": action, "price": price})
        logger.info(f"[{st.variant}] {st.base_symbol} #{st.ticket}: {action} @ {price:.5f}")
