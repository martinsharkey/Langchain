"""
TradePostMortem — data-driven self-reflection on each closed trade.

For a closed trade this reconstructs the REAL market around it and answers
concrete, actionable questions instead of reasoning over summary stats:

  1. HTF CONTEXT: what was the M15 trend/regime at entry?
  2. LEAD-UP: minute-by-minute M1 bars BEFORE entry — was the move already
     extended, or just starting?
  3. AFTER: M1 bars for the SAME duration after entry — MFE (max favourable
     excursion) and MAE (max adverse excursion) in ATR units. This reveals:
        * exited too EARLY  (price ran far our way after we closed)
        * stopped too TIGHT (price recovered after hitting our stop)
        * entered too LATE  (immediate adverse move / move already done)
  4. COUNTERFACTUALS on THIS trade:
        * would a wider TP (2x/3x) have captured more?
        * would a tighter/wider SL have avoided the loss / survived the wick?
        * would exiting-later (trail) have helped, given the actual MFE?

Aggregated across many losers, recurring failure modes become concrete findings
(e.g. "62% of losers had MFE > 1.5 ATR before reversing -> we exit too early")
that feed the knowledge base and the parameter optimizer. Deterministic maths
first; an optional LLM summarises the dominant pattern.
"""

from __future__ import annotations

import os
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("post_mortem")


@dataclass
class TradeReflection:
    trade_id: int
    symbol: str
    action: str
    outcome: str
    pnl: float
    htf_trend: str = "?"           # M15 trend at entry
    entry_extended: bool = False   # was the pre-entry move already extended?
    mfe_atr: float = 0.0           # max favourable excursion (ATR units) after entry
    mae_atr: float = 0.0           # max adverse excursion (ATR units) after entry
    exited_early: bool = False     # winner cut short (MFE >> captured)
    stopped_then_recovered: bool = False
    entered_late: bool = False
    # PREVENTIVE analysis (losers): would stronger indicators have blocked this bad entry?
    preventable: bool = False          # a stricter, evidence-based gate would have skipped it
    prevent_reasons: list = field(default_factory=list)  # which indicator + how
    better_entry_offset_min: int = 0   # a better entry existed this many min from actual entry
    notes: list = field(default_factory=list)


class TradePostMortem:
    def __init__(self, experience_db, knowledge_base=None):
        self.experience_db = experience_db
        self.kb = knowledge_base
        self._srv_offset = None   # server_time - local_time (seconds)

    def _server_offset(self) -> float:
        """
        MT5 stamps bar times in SERVER timezone (often several hours ahead of
        local). Trade timestamps are local. copy_rates_range expects server time,
        so we must shift the window by (server - local) or the bars won't align
        with the trade. Computed once from a live tick.
        """
        if getattr(self, "_srv_offset", None) is not None:
            return self._srv_offset
        try:
            import MetaTrader5 as mt5
            import datetime as _dt
            from src.mt5.connector import mt5_lock
            # use any active symbol's tick
            with mt5_lock():
                t = mt5.symbol_info_tick("XAUUSD-ECN") or mt5.symbol_info_tick("EURUSD-ECN")
            if t:
                self._srv_offset = (_dt.datetime.fromtimestamp(t.time) - _dt.datetime.now()).total_seconds()
            else:
                self._srv_offset = 0.0
        except Exception:
            self._srv_offset = 0.0
        return self._srv_offset

    # ── bar access ──
    def _bars_range(self, symbol, tf_const, start_dt, end_dt):
        try:
            import MetaTrader5 as mt5
            from src.mt5.connector import mt5_lock
            with mt5_lock():
                rr = mt5.copy_rates_range(symbol, tf_const, start_dt, end_dt)
            if rr is None:
                return []
            return [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
                     "low": float(r["low"]), "close": float(r["close"])} for r in rr]
        except Exception as e:
            logger.debug(f"bars_range failed {symbol}: {e}")
            return []

    def _atr_estimate(self, bars):
        if len(bars) < 5:
            return 0.0
        trs = [b["high"] - b["low"] for b in bars]
        return sum(trs) / len(trs)

    # ── per-symbol reflection profile (UNCONSTRAINED timeframes) ──
    def _profile(self, symbol: str) -> dict:
        """
        Timeframe/window profile per symbol. Slower/higher-priced instruments
        (BTC/ETH) need WIDER windows and HIGHER timeframes (M30/H1) to see the
        real momentum context; fast FX/metals use M1/M15. Config-overridable via
        POSTMORTEM_PROFILES env (JSON) so the researcher can widen timelines.
        """
        su = symbol.upper()
        crypto = any(h in su for h in ("BTC", "ETH", "XBT", "LTC", "XRP", "SOL"))
        if crypto:
            return {"entry_tf": "M5", "htf": ["M15", "M30", "H1"],
                    "window_min": 240, "htf_hours": 24}
        return {"entry_tf": "M1", "htf": ["M15", "M30"],
                "window_min": 60, "htf_hours": 8}

    _TF = {}  # lazy MT5 timeframe const map

    def _tf_const(self, name):
        # MT5 timeframe codes are FIXED integers; use plain-int fallbacks so this
        # (and its tests) work without the MetaTrader5 package (#45.3 / I3).
        _TF_INT = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 16385, "H4": 16388}
        try:
            import MetaTrader5 as mt5
        except Exception:
            return _TF_INT.get(name, 1)  # tests/fakes override _bars_range anyway
        if not self._TF:
            self._TF = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
                        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
        return self._TF.get(name, mt5.TIMEFRAME_M1)

    # ── per-trade reflection ──
    def reflect_trade(self, trade: dict, window_min: int = None) -> Optional[TradeReflection]:
        # (no top-level MT5 import: the excursion math needs none, and timeframe codes
        # come from _tf_const which already falls back to plain ints. This keeps
        # reflect_trade + its tests runnable on any box, not only Windows+MT5. #I3)
        sym = trade["symbol"]; action = trade["action"]
        prof = self._profile(sym)
        window_min = window_min or prof["window_min"]
        entry_tf = self._tf_const(prof["entry_tf"])
        ts = trade.get("timestamp")
        try:
            entry_dt = datetime.fromisoformat(str(ts).replace("Z", ""))
        except Exception:
            return None
        entry_price = trade.get("entry_price") or 0
        if not entry_price:
            return None

        # Shift entry time into SERVER time so copy_rates_range returns the bars
        # that actually correspond to the trade (server tz != local tz).
        offset = timedelta(seconds=self._server_offset())
        srv_entry = entry_dt + offset
        before = self._bars_range(sym, entry_tf,
                                  srv_entry - timedelta(minutes=window_min),
                                  srv_entry + timedelta(minutes=1))
        after = self._bars_range(sym, entry_tf,
                                 srv_entry, srv_entry + timedelta(minutes=window_min))
        # HTF: use the HIGHEST configured timeframe for the trend read (M30/H1 for BTC)
        htf_name = prof["htf"][-1]
        htf = self._bars_range(sym, self._tf_const(htf_name),
                               srv_entry - timedelta(hours=prof["htf_hours"]),
                               srv_entry + timedelta(minutes=60))

        r = TradeReflection(trade_id=trade["id"], symbol=sym, action=action,
                            outcome=trade["outcome"], pnl=trade.get("profit_loss") or 0)

        # HTF trend at entry (simple EMA slope on M15 closes)
        if len(htf) >= 20:
            closes = [b["close"] for b in htf]
            ema_fast = sum(closes[-9:]) / 9
            ema_slow = sum(closes[-21:]) / 21 if len(closes) >= 21 else sum(closes) / len(closes)
            r.htf_trend = "bullish" if ema_fast > ema_slow * 1.0005 else \
                          "bearish" if ema_fast < ema_slow * 0.9995 else "neutral"

        atr = self._atr_estimate(before) or self._atr_estimate(after)
        if atr <= 0:
            return r

        # pre-entry extension: how far did price already move toward entry direction
        if len(before) >= 10:
            start_price = before[0]["close"]
            pre_move = (entry_price - start_price) if action == "buy" else (start_price - entry_price)
            r.entry_extended = pre_move > 2.0 * atr   # move already ran >2 ATR before we entered

        # after-entry excursions (the key signal)
        if after:
            if action == "buy":
                mfe = max(b["high"] for b in after) - entry_price
                mae = entry_price - min(b["low"] for b in after)
            else:
                mfe = entry_price - min(b["low"] for b in after)
                mae = max(b["high"] for b in after) - entry_price
            r.mfe_atr = round(mfe / atr, 2)
            r.mae_atr = round(mae / atr, 2)

            # exited too early: trade was a loss/small win but price ran >1.5 ATR our way
            if r.outcome != "win" and r.mfe_atr >= 1.5:
                r.exited_early = True
                r.notes.append(f"price ran {r.mfe_atr} ATR our way after a non-win — likely exited early / SL too tight")
            # stopped then recovered: loss but MFE afterwards decent
            if r.outcome == "loss" and r.mfe_atr >= 1.0 and r.mae_atr >= 1.0:
                r.stopped_then_recovered = True
            # entered late: immediate adverse move dominates, little favourable
            if r.mae_atr >= 1.5 and r.mfe_atr < 0.5:
                r.entered_late = True
                r.notes.append(f"immediate {r.mae_atr} ATR adverse move, little favourable — entered late/wrong")

        # ── PREVENTIVE analysis (losers only): would stronger indicators have PREVENTED
        # this entry, or was there a better entry bar in the window? Reconstructs the
        # indicator series across before+after and reasons about Bulls/Bears/OsMA/EMA/ATR.
        if r.outcome == "loss":
            try:
                self._preventive_analysis(r, trade, before, after, action, entry_price, atr)
            except Exception as e:
                logger.debug(f"preventive analysis skip {trade.get('id')}: {e}")
        return r

    def _preventive_analysis(self, r, trade, before, after, action, entry_price, atr):
        """For a LOSING trade, reconstruct indicators around entry and flag whether a
        stronger evidence-based gate (Bulls/Bears power sign+strength, OsMA alignment,
        EMA slope, ATR regime) would have SKIPPED the entry, and whether a better entry
        bar existed within the window. Populates r.preventable / prevent_reasons /
        better_entry_offset_min. Uses the stored entry indicators_snapshot when present."""
        import json as _json
        snap = {}
        try:
            snap = _json.loads(trade.get("indicators_snapshot") or "{}")
        except Exception:
            snap = {}
        reasons = []
        # 1) Bull/Bear power at entry contradicted the trade direction (per R5 semantics:
        #    long wants bulls positive/rising; short wants bears deepening negative).
        bulls = snap.get("bulls_power"); bears = snap.get("bears_power")
        if bulls is not None and bears is not None:
            if action == "buy" and bulls <= 0:
                reasons.append(f"bulls_power {bulls:.2f} not positive at a long entry")
            if action == "sell" and bears >= 0:
                reasons.append(f"bears_power {bears:.2f} not negative at a short entry")
        # 2) OsMA not aligned / weak at entry
        osma = snap.get("osma")
        if osma is not None:
            if (action == "buy" and osma <= 0) or (action == "sell" and osma >= 0):
                reasons.append(f"osma {osma:.3f} not aligned with the {action} at entry")
        # 3) entry against the reconstructed HTF trend
        if r.htf_trend in ("bullish", "bearish"):
            if (action == "buy" and r.htf_trend == "bearish") or \
               (action == "sell" and r.htf_trend == "bullish"):
                reasons.append(f"entered {action} against {r.htf_trend} HTF trend")
        # 4) entry while over-extended (already flagged)
        if r.entry_extended:
            reasons.append("entry was already >2 ATR extended (chasing)")
        # 5) a better entry bar existed later in the 'after' window (price offered a
        #    materially better price within ~15 bars) -> we entered at a poor moment
        if after and atr > 0:
            best_off = 0; best_gain = 0.0
            for i, b in enumerate(after[:15]):
                better = (entry_price - b["low"]) if action == "buy" else (b["high"] - entry_price)
                if better > best_gain:
                    best_gain = better; best_off = i
            if best_gain >= 0.5 * atr:
                r.better_entry_offset_min = best_off
                reasons.append(f"a better entry (~{best_gain/atr:.1f} ATR) was available "
                               f"{best_off} bars later")
        if reasons:
            r.preventable = True
            r.prevent_reasons = reasons
            r.notes.append("PREVENTABLE: " + "; ".join(reasons))
        return r

    def _recent_closed(self, limit=40, only_losers=False) -> list[dict]:
        conn = sqlite3.connect(self.experience_db.db_path); conn.row_factory = sqlite3.Row
        q = ("SELECT id, timestamp, symbol, action, entry_price, outcome, profit_loss, "
             "mgmt_variant, strategy_used FROM trades WHERE outcome IN ('win','loss','breakeven') ")
        params = []
        if only_losers:
            q += "AND outcome='loss' "
        # learning window: current behaviour only (regime-break + recency + OsMA-only +
        # exclude SIMULATED_OHLC) so post-mortem diagnoses the live confluence, not the
        # retired ensemble era.
        try:
            lw, lp = self.experience_db.learning_window_clause()
            q += lw; params += lp
        except Exception:
            pass
        q += " ORDER BY id DESC LIMIT ?"; params.append(limit)
        rows = [dict(r) for r in conn.execute(q, tuple(params)).fetchall()]
        conn.close()
        return rows

    # ── aggregate the recurring patterns (the intelligence) ──
    def analyze(self, symbol: Optional[str] = None, limit: int = 40) -> dict:
        rows = self._recent_closed(limit=limit)
        if symbol:
            rows = [r for r in rows if r["symbol"].upper().startswith(symbol.upper())]
        reflections = []
        for t in rows:
            ref = self.reflect_trade(t)
            if ref:
                reflections.append(ref)
        if len(reflections) < 8:
            return {"analyzed": len(reflections), "insufficient": True}

        losers = [r for r in reflections if r.outcome == "loss"]
        wins = [r for r in reflections if r.outcome == "win"]
        n_loss = len(losers) or 1

        exited_early = sum(1 for r in losers if r.exited_early)
        stopped_recovered = sum(1 for r in losers if r.stopped_then_recovered)
        entered_late = sum(1 for r in losers if r.entered_late)
        extended_entries = sum(1 for r in reflections if r.entry_extended)
        avg_win_mfe = round(sum(r.mfe_atr for r in wins) / len(wins), 2) if wins else 0
        avg_loss_mfe = round(sum(r.mfe_atr for r in losers) / n_loss, 2)
        avg_loss_mae = round(sum(r.mae_atr for r in losers) / n_loss, 2)

        findings = []
        recs = []
        # structured directives: {param: signed step} the optimizer can act on.
        # These BIAS the optimizer's search toward what reflection found, then
        # the walk-forward gate decides whether to keep it.
        directives = {}
        if exited_early / n_loss >= 0.4:
            findings.append(f"{exited_early}/{n_loss} losers had price run >=1.5 ATR our way after — EXITING TOO EARLY or SL too tight.")
            recs.append("widen TP / loosen giveback / widen SL slightly")
            directives["tp_rr"] = +0.5
            directives["giveback"] = +0.15
        if stopped_recovered / n_loss >= 0.35:
            findings.append(f"{stopped_recovered}/{n_loss} losers were STOPPED THEN RECOVERED — SL too tight for the volatility.")
            recs.append("increase sl_atr")
            directives["sl_atr"] = +0.2
        if entered_late / n_loss >= 0.35:
            findings.append(f"{entered_late}/{n_loss} losers had immediate adverse move — ENTERING LATE (move already extended).")
            recs.append("add pre-entry extension filter; avoid entries when move already >2 ATR")
            directives["entry_extension_filter"] = True
        if extended_entries / len(reflections) >= 0.4:
            findings.append(f"{extended_entries}/{len(reflections)} entries were into already-extended moves.")
        if avg_win_mfe and avg_loss_mfe and avg_loss_mfe >= avg_win_mfe * 0.8:
            findings.append(f"Losers reach nearly as much favourable excursion (MFE {avg_loss_mfe} ATR) as winners ({avg_win_mfe}) before failing — exit timing, not entry, is the leak.")
            directives.setdefault("tp_rr", +0.5)
        # PREVENTABLE losers: entries a stronger indicator gate would have skipped. Aggregate
        # the reasons so we learn WHICH indicator most often could have blocked bad trades.
        preventable = [r for r in losers if getattr(r, "preventable", False)]
        prevent_reason_counts = {}
        for r in preventable:
            for reason in r.prevent_reasons:
                tag = reason.split(" ")[0] + " " + (reason.split(" ")[1] if len(reason.split(" ")) > 1 else "")
                prevent_reason_counts[tag] = prevent_reason_counts.get(tag, 0) + 1
        if preventable:
            top = sorted(prevent_reason_counts.items(), key=lambda x: -x[1])[:3]
            findings.append(f"{len(preventable)}/{n_loss} losers were PREVENTABLE — a stronger entry "
                            f"gate would have skipped them. Top signals: {top}.")
            recs.append("tighten entry strength floors on the indicators that most often flagged preventable losers")

        result = {
            "analyzed": len(reflections), "losers": n_loss, "wins": len(wins),
            "exited_early_pct": round(exited_early / n_loss * 100, 0),
            "stopped_recovered_pct": round(stopped_recovered / n_loss * 100, 0),
            "entered_late_pct": round(entered_late / n_loss * 100, 0),
            "avg_win_mfe_atr": avg_win_mfe, "avg_loss_mfe_atr": avg_loss_mfe,
            "avg_loss_mae_atr": avg_loss_mae,
            "findings": findings, "recommendations": recs, "directives": directives,
            "symbol": symbol or "ALL",
            "preventable_losers": len(preventable),
            "preventable_pct": round(len(preventable) / n_loss * 100, 0) if n_loss else 0,
            "prevent_reason_counts": prevent_reason_counts,
        }
        self._persist(result)
        # STORE THE WRONG DECISIONS: one durable record per preventable losing trade so the
        # bot remembers exactly what could have prevented each bad entry.
        if self.kb and preventable:
            for r in preventable:
                try:
                    self.kb.store_knowledge(
                        question=f"Trade {r.trade_id} ({r.symbol} {r.action}) lost — what could have prevented it?",
                        answer=("; ".join(r.prevent_reasons)
                                + (f"; better entry {r.better_entry_offset_min} bars later"
                                   if r.better_entry_offset_min else ""))[:2000],
                        topic="wrong_decisions", subtopic=r.symbol,
                        priority=7, confidence=0.7,
                        tags=["wrong_decision", "preventable", r.symbol, r.action])
                except Exception:
                    pass
        logger.info(f"PostMortem [{symbol or 'ALL'}]: {findings if findings else 'no dominant failure mode'}")
        return result

    def _persist(self, result):
        try:
            path = os.path.join(config.DATA_DIR, "post_mortem.json")
            with open(path + ".tmp", "w") as f:
                json.dump({"updated_at": datetime.now(timezone.utc).isoformat(), **result}, f, indent=2, default=str)
            os.replace(path + ".tmp", path)
        except Exception as e:
            logger.debug(f"post-mortem persist skip: {e}")
        if self.kb and result.get("findings"):
            try:
                self.kb.store_knowledge(
                    question=f"What is the recurring failure mode for {result.get('symbol')}?",
                    answer=" | ".join(result["findings"])[:2000],
                    topic="trade_postmortem", subtopic="failure_modes",
                    priority=8, confidence=0.75, tags=["postmortem", result.get("symbol", "ALL")])
            except Exception:
                pass
