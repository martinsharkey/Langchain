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
    peak_profit_points: float = 0.0  # best unrealized profit (points) ever seen (MFE)
    worst_profit_points: float = 0.0 # worst unrealized profit (points) ever seen (MAE, <=0)
    trend_aligned: bool = False      # entry aligned with higher-TF trend (ride mode)
    htf_widened: bool = False        # HTF-blip stop-widen already applied (once)
    # Peak-tracking momentum exhaustion (GoldShark11 exit, #29): track the best
    # Bulls/Bears power and OsMA magnitude seen; exit when they fall off the peak.
    peak_power: float = 0.0          # best (favourable) bulls/bears power seen
    peak_osma_abs: float = 0.0       # best |OsMA| seen
    weak_trade: bool = False         # counter-trend "Weak" trade (Playbook A: POC target, no trail)
    poc_target: float = 0.0          # Point-of-Control / balance-area target for weak trades
    # Reversal-signature capture (exit research): the indicator snapshot AT the MFE
    # peak, plus the live indicators dict, so we can compare entry vs peak vs the
    # roll-over WITHOUT reconstructing bars. Populated by evaluate() when a new peak
    # is set and each cycle; persisted on close by the engine.
    entry_indicators: dict = field(default_factory=dict)
    peak_indicators: dict = field(default_factory=dict)
    last_indicators: dict = field(default_factory=dict)
    signal_hold: bool = False        # reversal tell says the move still has legs (ride)
    _last_tick_srv: float = 0.0      # last intra-cycle tick scan in SERVER time (peak-between-polls)


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

    def retain_floor_frac(self, st) -> float:
        """
        The PROFIT-RETENTION RATCHET floor: the minimum fraction of the peak profit
        a trade must keep once the ratchet arms. Distinct from (and tighter than)
        giveback_fraction — this is a hard "don't hand the move back" guard, tuned
        from the observed leak (gold peaked £5+ then round-tripped). Higher = keep
        more. Learned per symbol; sensible default otherwise.
        """
        p = self._personality(st)
        if "retain_floor_frac" in p:
            return min(max(float(p["retain_floor_frac"]), 0.3), 0.9)
        try:
            from src import config
            return config.SCALP_RETAIN_FLOOR_FRAC
        except Exception:
            return 0.5

    def retain_arm_points(self, st) -> float:
        """
        Peak profit (points) before the retention ratchet activates. Armed EARLIER
        than the giveback guard (which waits 1.5*ATR) so we start protecting profit
        as soon as a trade has a real buffer, not only after it is already huge.
        """
        p = self._personality(st)
        if "retain_arm_points" in p:
            return float(p["retain_arm_points"])
        try:
            from src import config
            mult = config.SCALP_RETAIN_ARM_ATR
        except Exception:
            mult = 0.8
        return (st.atr_points or 60) * mult

    def _reversal_tell(self, st, live: dict, signature: dict) -> str:
        """Classify the live momentum state vs the MFE peak snapshot, guided by the
        PROVEN, PER-SYMBOL reversal signature.

        Scale-free by construction: it compares the RATIO (live magnitude / peak
        magnitude) for each momentum indicator against the thresholds the bot has
        LEARNED for THIS symbol (`median_retained_frac`). Gold and BTCUSD have wildly
        different raw OsMA/MACD scales, so we never use absolute values — only each
        symbol's own learned reversal depth.

        Returns 'rolling_over' | 'still_supported' | 'neutral'.
        """
        peak = st.peak_indicators or {}
        if not peak or not live:
            return "neutral"
        reliable = []
        for f in ("osma", "macd_histogram"):
            s = signature.get(f) or {}
            pct = s.get("shrank_toward_neutral_pct")
            if pct is not None and pct >= 60 and peak.get(f) is not None and live.get(f) is not None:
                reliable.append(f)
        if not reliable:
            return "neutral"
        shrunk = held = 0
        for f in reliable:
            pk = abs(peak[f]); lv = abs(live[f])
            if pk <= 1e-9:
                continue
            ratio = lv / pk
            # per-symbol learned reversal depth: the symbol's median retained fraction
            # at exit. 'rolling over' = we've dropped BELOW that learned retention
            # (momentum has unwound more than this symbol typically does before exit).
            learned_ret = (signature.get(f) or {}).get("median_retained_frac")
            roll_thr = learned_ret if learned_ret is not None else 0.5
            hold_thr = min(0.95, max(roll_thr + 0.25, 0.85))
            if ratio <= roll_thr:
                shrunk += 1
            elif ratio >= hold_thr:
                held += 1
        if shrunk >= 1 and shrunk >= held:
            return "rolling_over"
        if held >= 1 and held > shrunk:
            return "still_supported"
        return "neutral"

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
                 spread_points: float, indicators: Optional[dict] = None,
                 reversal_signature: Optional[dict] = None,
                 extreme_price: Optional[float] = None) -> Optional[dict]:
        """
        Return an intent dict or None. Called each cycle with the live price.
        Distances are in price units; point converts to/from points.

        `indicators` (optional): the live indicator snapshot, used to capture the
        reversal signature at the MFE peak (entry vs peak vs rollover research).
        `reversal_signature` (optional): a PROVEN per-symbol signature dict from the
        research loop. When present, enables a signal-driven exit/hold (gated - the
        engine only passes it once the signature has enough samples).
        `extreme_price` (optional): the most FAVOURABLE price seen since the last
        cycle (intra-cycle tick high/low). Fixes the 15s-poll blindness: MFE/peak are
        updated from this true extreme, while EXIT decisions still use the current
        `price` (we can only realistically exit at the live price, not a past spike).
        """
        st.point = point or st.point
        _sig_fields = ("macd_line", "macd_histogram", "osma", "bulls_power",
                       "bears_power", "rsi", "atr")
        if indicators:
            st.last_indicators = {k: indicators.get(k) for k in _sig_fields}
        if st.action == "buy":
            profit_points = (price - st.entry) / point if point else 0
            st.best_price = max(st.best_price, price)
        else:
            profit_points = (st.entry - price) / point if point else 0
            st.best_price = min(st.best_price, price)

        # intra-cycle peak: the true favourable excursion may have happened BETWEEN
        # polls. Compute peak profit from the tick extreme so MFE + the retention
        # ratchet are not blind to spikes the 15s loop skipped over.
        peak_profit_now = profit_points
        if extreme_price is not None and point:
            ext_pts = ((extreme_price - st.entry) if st.action == "buy"
                       else (st.entry - extreme_price)) / point
            if ext_pts > peak_profit_now:
                peak_profit_now = ext_pts
            if st.action == "buy":
                st.best_price = max(st.best_price, extreme_price)
            else:
                st.best_price = min(st.best_price, extreme_price) if st.best_price else extreme_price

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
        if peak_profit_now > st.peak_profit_points:
            st.peak_profit_points = peak_profit_now
            # capture the indicator snapshot AT the new peak (reversal signature).
            # Note: indicators are the current-bar values; the intra-cycle price
            # extreme may lead them slightly, which is acceptable for the tell.
            if indicators:
                st.peak_indicators = {k: indicators.get(k) for k in _sig_fields}
        st.peak_profit_points = max(st.peak_profit_points, peak_profit_now)
        st.worst_profit_points = min(st.worst_profit_points, profit_points)  # MAE tracking

        # ── PROFIT-RETENTION RATCHET (retain what we've earned) ──────────────
        # The observed leak: gold trades reached large peaks (e.g. 700+ pts / £5)
        # then round-tripped almost entirely because the giveback guard below only
        # arms at 1.5*ATR and tolerates 60-90% giveback. This ratchet fires FIRST
        # and is absolute: once a trade has banked a meaningful peak, it must not
        # surrender more than `retain_floor_frac` of that peak. It only ever tightens
        # (a ratchet), it never loosens, so winners still run — they just can't give
        # the whole move back. Tunable per symbol via config; ATR-scaled arm so it
        # is symbol-agnostic (gold's big ATR and FX's small ATR both work). It also
        # requires a real absolute buffer (>= 1*ATR of peak) so tiny winners that
        # never built a meaningful cushion are left for the trail/giveback, not
        # scratched by the ratchet.
        # Arm as soon as there is a MEANINGFUL profit buffer — NOT a full ATR. Live
        # data showed a 1xATR arm never engaged on most BTC trades (median MFE 14347
        # < 1xATR 14995), leaving big winners unprotected. Arm at a fraction of ATR
        # (or a spread-based floor), so the retain-floor can protect any real peak.
        # The 50% retain floor already prevents scratching tiny winners.
        ratchet_arm = max(self.retain_arm_points(st), spread_points + 20)
        if st.peak_profit_points >= ratchet_arm:
            retain_frac = self.retain_floor_frac(st)          # e.g. 0.5 -> keep >=50% of peak
            floor_points = st.peak_profit_points * retain_frac
            # If price has ALREADY fallen to/through the floor, a stop there would sit
            # on the wrong side of market (retcode 10016). CLOSE now — that captures
            # the floor immediately and is what a broker stop would have done anyway.
            if profit_points <= floor_points:
                self._log(st, "retention_ratchet_exit", price)
                return {"close": (f"profit retention: banked {st.peak_profit_points:.0f}pts peak, "
                                  f"protecting {retain_frac:.0%} floor ({floor_points:.0f}pts), "
                                  f"now {profit_points:.0f}pts")}
            # Otherwise price is still comfortably above the floor: place a REAL broker
            # stop at the floor (valid, below market) so it protects tick-by-tick even
            # between fast-manage ticks. Ratchets: only ever tightens toward profit.
            floor_price = (st.entry + floor_points * point) if st.action == "buy" \
                else (st.entry - floor_points * point)
            if self._sl_improves(st, floor_price):
                st.sl = floor_price
                st.moved_to_be = True
                self._log(st, "retention_ratchet_sl", floor_price)
                return {"modify_sl": round(floor_price, 6)}

        # ── SIGNAL-DRIVEN EXIT / HOLD (gated: only when a proven signature exists) ──
        # Our confluence indicators are strong for ENTRY; the reversal-signature
        # research measures whether they also mark the EXIT (indicators turning back
        # toward neutral at the peak). When the engine passes a proven signature AND
        # the trade is in real profit, we use the LIVE indicators two ways:
        #   * EXIT earlier than the blind giveback if the tell is firing (momentum
        #     rolling over) and we have already captured a decent chunk of the peak.
        #   * HOLD (loosen giveback) if the indicators still strongly support our
        #     direction — this is how we ride runners instead of scratching a dip.
        # It never overrides the retention ratchet (the floor) above.
        st.signal_hold = False
        if reversal_signature and indicators and profit_points > 0 \
                and st.peak_profit_points >= max(self.giveback_arm_points(st) * 0.6, spread_points + 20):
            tell = self._reversal_tell(st, indicators, reversal_signature)
            if tell == "rolling_over" and profit_points >= 0.5 * st.peak_profit_points:
                self._log(st, "signal_reversal_exit", price)
                return {"close": (f"reversal signal: momentum turning at "
                                  f"{profit_points:.0f}/{st.peak_profit_points:.0f}pts peak")}
            elif tell == "still_supported":
                st.signal_hold = True

        arm_peak = max(self.giveback_arm_points(st), spread_points + 15)
        if st.peak_profit_points >= arm_peak and profit_points > 0:
            giveback_frac = self.giveback_fraction(st)
            # signal-supported hold: the reversal tell says the move still has legs
            if getattr(st, "signal_hold", False):
                giveback_frac = min(giveback_frac + 0.2, 0.9)
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

    def momentum_exhaustion_exit(self, st: ManagedState, price: float, point: float,
                                 bulls: float, bears: float, osma: float,
                                 power_rev_pts: float = None,
                                 osma_drop_frac: float = None) -> Optional[dict]:
        """
        GoldShark11 peak-tracking momentum-exhaustion exit (#29). Tracks the best
        favourable power (Bulls for longs / Bears for shorts) and best |OsMA| seen
        while in the trade; exits when momentum has fallen meaningfully off its
        peak (a proxy for "the move is exhausted / balance reached"). Only acts
        once the trade is in profit, so it locks gains rather than cutting early.
        """
        # only relevant once genuinely in profit
        if st.action == "buy":
            profit_points = (price - st.entry) / point if point else 0
            fav_power = bulls
        else:
            profit_points = (st.entry - price) / point if point else 0
            fav_power = -bears  # for shorts, more-negative bears = stronger; track magnitude
        if profit_points <= 0:
            return None

        st.peak_power = max(st.peak_power, fav_power)
        st.peak_osma_abs = max(st.peak_osma_abs, abs(osma))

        # thresholds: default to fractions of the peak (symbol-agnostic), tunable.
        # power reversal: favourable power dropped by this FRACTION of its peak.
        power_frac = 0.5 if power_rev_pts is None else None
        osma_frac = osma_drop_frac if osma_drop_frac is not None else 0.5

        power_exhausted = False
        if st.peak_power > 0:
            if power_rev_pts is not None:
                power_exhausted = fav_power < (st.peak_power - power_rev_pts)
            else:
                power_exhausted = fav_power < st.peak_power * power_frac

        osma_exhausted = (st.peak_osma_abs > 0 and abs(osma) < st.peak_osma_abs * osma_frac)

        # require a real profit buffer so we don't exit on noise near entry
        armed = st.peak_profit_points >= max(self.giveback_arm_points(st) * 0.6, 1)
        if armed and (power_exhausted and osma_exhausted):
            self._log(st, "momentum_exhaustion_exit", price)
            return {"close": (f"momentum exhausted: power {fav_power:.2f} off peak "
                              f"{st.peak_power:.2f}, |OsMA| {abs(osma):.3f} off peak "
                              f"{st.peak_osma_abs:.3f}")}
        return None

    def weak_trade_poc_exit(self, st: ManagedState, price: float, point: float) -> Optional[dict]:
        """
        Playbook-A exit for a WEAK (counter-trend) trade (#29): trailing is
        disabled; the trade targets the previous balance-area Point of Control
        (POC) and is closed there, before the macro trend resumes. If no POC was
        set, this is a no-op (falls back to the normal manager logic).
        """
        if not st.weak_trade or not st.poc_target:
            return None
        if st.action == "buy" and price >= st.poc_target:
            self._log(st, "weak_poc_target_exit", price)
            return {"close": f"weak long: reached POC target {st.poc_target:.5f}"}
        if st.action == "sell" and price <= st.poc_target:
            self._log(st, "weak_poc_target_exit", price)
            return {"close": f"weak short: reached POC target {st.poc_target:.5f}"}
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
