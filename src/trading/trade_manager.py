"""
Trade Manager — manages OPEN positions using the ONE proven exit model.

STANDARDISED (legacy removal): after the audit, the bot uses a SINGLE management
variant — GS_PROVEN — the proven GoldShark exit:

  GS_PROVEN — a data-derived WIDE broker SL set on entry (keeps ~96% of winners),
              then at +be_trigger pts move SL to BE + a small locked profit, then
              TRAIL behind best_price and REMOVE the broker TP once trailing arms so
              a runner is never capped. SL only ever moves favourably (a ratchet).

The old A/B management arms (BE_PLUS_TRAIL / TRAIL_ONLY / SCALP_FIXED / HYBRID_LLM /
GS13_MFE) and the generic retention-ratchet / signal-driven / giveback guards have
been REMOVED — they never ran once GS_PROVEN became the only assigned variant.

Every management action and the final outcome is tagged with the variant + symbol,
written to the experience DB.

Broker-side SL is ALWAYS set on entry (handled by the engine via BrokerAdapter);
this manager only MODIFIES the existing broker SL — it never leaves a trade naked.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("trade_manager")

# The ONE proven management model (legacy A/B arms removed).
VARIANTS = ("GS_PROVEN",)


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

    def _wick_points(self, st) -> float:
        """The symbol's typical adverse WICK size in points — the breathing room a
        trailing stop needs so normal noise doesn't wick it out. Learned per symbol
        (personality 'wick_points'); else derived from ATR (~0.35xATR default)."""
        p = self._personality(st)
        if "wick_points" in p:
            return max(float(p["wick_points"]), 1.0)
        return max((st.atr_points or 60) * 0.35, 5.0)

    def _be_trigger_points(self, st, spread_points, wick) -> float:
        """Profit (pts) needed before moving to break-even: must clear the symbol's
        wick noise + spread so we don't BE-out on a normal retrace. Learnable."""
        p = self._personality(st)
        if "be_trigger_pts" in p:
            return max(float(p["be_trigger_pts"]), spread_points + 5)
        return max(spread_points + wick * 1.2, spread_points + 20)

    def _trail_points(self, st, spread_points, wick) -> float:
        """RESPONSIVE trail distance (pts): wick-sized breathing room, NOT raw ATR
        (which gave too much back). Default ~1.3x wick — follows closely yet survives
        normal wicks; learnable per symbol via 'trail_wick_mult'. A fixed 'trail_points'
        (e.g. pass5469's proven 73) overrides the wick-relative trail when present."""
        p = self._personality(st)
        if "trail_points" in p:
            return max(float(p["trail_points"]), spread_points + 5)
        mult = float(p.get("trail_wick_mult", 1.3))
        return max(wick * mult, spread_points + 12)

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
        # FIXED RULE (scalability): EVERY symbol uses the ONE proven GoldShark exit model
        # (GS_PROVEN) — data-derived wide SL + BE-lock + trailing with the TP removed once
        # trailing arms. No per-symbol split exit variants; one pattern scales to any symbol.
        # The ONLY complementary exception is BTCUSD's CryptoRTI websocket (whale-wave), which
        # AUGMENTS entries/confidence via a separate path — it does not change this exit model.
        # (The other variants remain defined only for historical A/B analysis of past trades.)
        return "GS_PROVEN"

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
        # capital-preservation threshold: prefer ATR-scaled, but FALL BACK to a spread/point
        # floor when atr_points is missing (0/None) so this software failsafe is UNCONDITIONAL
        # (the broker SL still protects regardless, but never leave the in-code guard off).
        _viol_thresh = (max(st.atr_points * 1.5, 2 * spread_points + 50) if st.atr_points
                        else (2 * spread_points + 50))
        violent = adverse_points > _viol_thresh
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

        if v == "GS_PROVEN":
            # PROVEN GoldShark gold exit (data-derived + pass5469 .set). Broker SL is set
            # WIDE at entry (hard_sl_points, ~400pts — keeps ~96% of winners). This arm:
            #   1) at +be_trigger pts, move SL to BE + be_lock (small locked profit);
            #   2) from then on TRAIL behind best_price and REMOVE the broker TP so the
            #      runner is never capped (user rule: at BE we trail, drop the TP);
            #   3) SL only ever moves favourably (ratchet).
            # Params per-symbol via personality (proven gold defaults below). Exempt from
            # the generic ratchet/giveback (gated by st.variant) so it's the pure model.
            p = self._personality(st)
            be_trig = float(p.get("be_trigger_pts", 200.0))
            be_lock = float(p.get("be_lock_pts", 50.0))
            trail = float(p.get("trail_points", 73.0))
            sgn = 1 if st.action == "buy" else -1
            if not st.moved_to_be and profit_points >= be_trig:
                be_plus = st.entry + be_lock * point * sgn
                st.moved_to_be = True
                st.trail_active = True
                st.sl = be_plus   # keep in-memory SL consistent with the broker SL
                self._log(st, "gs_proven_be_lock", be_plus)
                # remove the safety-TP now that we're trailing (let the runner run)
                return {"modify_sl": round(be_plus, 6), "remove_tp": True, "_tag": "gs_proven_be"}
            if st.trail_active:
                trail_dist = trail * point
                new_sl = (st.best_price - trail_dist) if st.action == "buy" else (st.best_price + trail_dist)
                if self._sl_improves(st, new_sl):
                    st.sl = new_sl
                    self._log(st, "gs_proven_trail", new_sl)
                    return {"modify_sl": round(new_sl, 6), "remove_tp": True, "_tag": "gs_proven_trail"}
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

    def _sl_improves(self, st: ManagedState, new_sl: float) -> bool:
        """Only ever move SL in the protective direction (never widen risk)."""
        if st.sl == 0:
            return True
        return new_sl > st.sl if st.action == "buy" else new_sl < st.sl

    def _log(self, st: ManagedState, action: str, price: float):
        st.actions.append({"t": time.time(), "action": action, "price": price})
        logger.info(f"[{st.variant}] {st.base_symbol} #{st.ticket}: {action} @ {price:.5f}")
