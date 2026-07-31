"""
Scalping Trade Engine — the real, self-contained trading loop.

Goal: accumulate a large sample (target ~100) of REAL closed trades on the
demo account across multiple symbols (XAUUSD, BTCUSD, ...) so the learning
system trains on genuine outcomes.

Design principles (see REPAIR_PLAN.md):
  * REAL execution only — via BrokerAdapter.place() (never LLM narration).
  * REAL learning — closed trades are reconciled against MT5 deal history and
    written to the experience DB with true P&L (win/loss).
  * Symbol-agnostic — everything is driven by live symbol_info.
  * Honest state — writes bot_status.json for the dashboard; no fabricated data.

This engine intentionally does NOT depend on the legacy multi-agent main.py
loop. It reuses the proven pieces: indicator calculation, the strategy
registry ensemble, the vector store, and the experience DB.
"""

from __future__ import annotations

import os
import json
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src import config
from src.utils.logger import get_logger
from src.mt5.connector import get_connector, mt5, MT5_AVAILABLE
from src.mt5.data import get_rates
from src.mt5.account import get_account_info
from src.mt5.broker_adapter import BrokerAdapter, get_algo_status
from src.strategies.xauusd_strategy import XAUUSDStrategy
from src.strategies.indicators import compute_full_indicators
from src.learning.strategy_registry import StrategyRegistry
from src.learning.experience_db import ExperienceDatabase

logger = get_logger("scalp_engine")

STATUS_PATH = os.path.join(config.DATA_DIR, "bot_status.json")


@dataclass
class TrackedPosition:
    ticket: int
    symbol: str          # resolved broker symbol
    base_symbol: str
    action: str
    entry_price: float
    volume: float
    sl: Optional[float]
    tp: Optional[float]
    confidence: float
    strategy: str
    strategy_combo: str
    opened_at: str
    db_trade_id: Optional[int] = None
    indicators: dict = field(default_factory=dict)
    mgmt_variant: Optional[str] = None
    timeframe: str = "M1"


class ScalpEngine:
    def __init__(self):
        self.connector = get_connector()
        self.strategy = XAUUSDStrategy()          # indicator calculator (symbol-agnostic math)
        self.registry = StrategyRegistry()        # 7 real strategies + ensemble
        self.experience_db = ExperienceDatabase()

        # Register the CryptoRTI whale-signal strategy (BTC bias, status=testing)
        try:
            from src.cryptorti.strategy import register as register_cryptorti
            register_cryptorti(self.registry)
        except Exception as e:
            logger.warning(f"CryptoRTI strategy not registered: {e}")

        # one BrokerAdapter per base symbol
        self.adapters: dict[str, BrokerAdapter] = {}
        self.open_positions: dict[int, TrackedPosition] = {}   # by ticket

        # per-symbol stats + trade management (A/B learning experiments)
        from src.trading.symbol_stats import SymbolStatsEngine
        from src.trading.trade_manager import TradeManager
        self.stats_engine = SymbolStatsEngine()
        self.trade_manager = TradeManager(
            experience_db=self.experience_db,
            get_variant_weights=self._variant_weights_for,
            get_symbol_personality=self._symbol_personality_for,
        )
        self.managed: dict[int, object] = {}   # ticket -> ManagedState
        self._variant_perf_cache = {}
        self._symbol_personality_cache = {}
        # proactive self-performance researcher (analyzes what's working)
        try:
            from src.learning.performance_researcher import PerformanceResearcher
            self.perf_researcher = PerformanceResearcher(self.experience_db)
        except Exception as e:
            logger.warning(f"PerformanceResearcher unavailable: {e}")
            self.perf_researcher = None
        # objective edge scoreboard (gates sizing/compounding on proven edge)
        try:
            from src.learning.edge_metrics import EdgeCalculator
            self.edge = EdgeCalculator(self.experience_db)
        except Exception as e:
            logger.warning(f"EdgeCalculator unavailable: {e}")
            self.edge = None
        self._edge_cache = {}
        self._symbol_profit_cache = {}

        # Phase 3 — master risk gate
        from src.trading.risk_manager import RiskManager
        self.risk = RiskManager(
            get_account_info=self._safe_account,
            get_open_position_count=lambda: len(self.open_positions),
        )

        # session/market-hours awareness (researcher-maintained schedules)
        from src.trading.session_manager import SessionManager
        self.sessions = SessionManager()

        # Adaptive intelligence loop (L4 reflect -> L5 synthesize -> L6 backtest -> promote)
        try:
            from src.learning.adaptive_loop import AdaptiveLoop
            self.adaptive = AdaptiveLoop(
                self.experience_db, self.registry,
                symbol_resolver=lambda b: (self.adapters[b].resolved_symbol
                                           if b in self.adapters else b),
            )
        except Exception as e:
            logger.warning(f"AdaptiveLoop unavailable: {e}")
            self.adaptive = None
        self._adaptive_running = False

        self.cycle = 0
        self.trades_opened = 0
        self.trades_closed = 0
        self.running = False

        try:
            from src.learning.vector_store import PatternVectorStore
            self.vector_store = PatternVectorStore()
        except Exception as e:
            logger.warning(f"vector store unavailable: {e}")
            self.vector_store = None

        # RAG pattern matcher — READ at entry to adjust confidence from history (C2)
        try:
            from src.learning.pattern_matcher import PatternMatcher
            self.pattern_matcher = PatternMatcher(self.vector_store) if self.vector_store else None
        except Exception as e:
            logger.warning(f"pattern matcher unavailable: {e}")
            self.pattern_matcher = None

    # ── setup ─────────────────────────────────────────────────────────
    def initialize(self) -> bool:
        self.connector.initialize()
        if not self.connector.is_connected():
            logger.error("MT5 not connected — cannot start scalp engine")
            return False
        for base in config.TRADING_SYMBOLS:
            adapter = BrokerAdapter(base, mode=config.TRADING_MODE)
            if adapter.spec is None:
                logger.warning(f"Skipping {base}: could not resolve a broker symbol")
                continue
            if not adapter.spec.tradable and config.is_live_mode():
                logger.warning(f"Skipping {base} ({adapter.resolved_symbol}): not tradable")
                continue
            self.adapters[base] = adapter
            logger.info(f"Symbol ready: {base} -> {adapter.resolved_symbol}")
        if not self.adapters:
            logger.error("No tradable symbols resolved — cannot start")
            return False
        # Adopt any open positions (incl. manual trades) so the bot manages them.
        self._adopt_existing_positions()
        # Close the loop for any trades left 'pending' from prior runs / manual closes.
        self._reconcile_pending_from_db()
        return True

    def _adopt_existing_positions(self):
        """
        Take over open MT5 positions — INCLUDING manual trades the user opened
        by hand (different or zero magic number). The bot manages them like its
        own so a manual trade still gets trailing SL / BE / capital-preservation
        and its outcome is recorded for learning.
        """
        if not (MT5_AVAILABLE and self.connector.is_connected()):
            return
        try:
            positions = mt5.positions_get() or []
        except Exception as e:
            logger.warning(f"adopt: positions_get failed: {e}")
            return
        adopted = 0
        for p in positions:
            if p.ticket in self.open_positions:
                continue
            # map the broker symbol to one of our configured base symbols;
            # only adopt symbols we actually trade (so we have specs/stats).
            base = next((b for b, ad in self.adapters.items()
                         if ad.resolved_symbol == p.symbol), None)
            if base is None:
                logger.info(f"Not adopting {p.symbol} #{p.ticket}: symbol not in trading set")
                continue
            is_ours = getattr(p, "magic", 0) == config.BOT_MAGIC
            source = "bot" if is_ours else "manual"
            action = "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell"

            # create a DB row so the adopted trade has a real db_trade_id and
            # will be reconciled + learned from when it closes. BUT first check
            # for an existing pending row for this ticket (a bot-opened trade
            # being re-adopted after restart) so we NEVER duplicate a trade.
            db_id = None
            try:
                db_id = self.experience_db.get_open_trade_id_by_ticket(p.ticket)
                if db_id is None:
                    db_id = self.experience_db.record_trade(
                        signal={
                            "symbol": p.symbol, "action": action, "price": p.price_open,
                            "stop_loss": p.sl or 0, "take_profit": p.tp or 0,
                            "position_size": p.volume, "confidence": 0.0,
                            "strategy_used": f"adopted_{source}",
                        },
                        indicators={}, outcome="pending",
                        strategy_combination=f"adopted_{source}",
                        timeframe=config.ENTRY_TIMEFRAME, mt5_ticket=p.ticket,
                    )
            except Exception as e:
                logger.warning(f"adopt: record_trade failed for {p.ticket}: {e}")

            # use the REAL open time from MT5 so long-runners aren't mis-aged
            try:
                opened_iso = datetime.fromtimestamp(int(p.time), tz=timezone.utc).isoformat()
            except Exception:
                opened_iso = datetime.now(timezone.utc).isoformat()

            self.open_positions[p.ticket] = TrackedPosition(
                ticket=p.ticket, symbol=p.symbol, base_symbol=base,
                action=action, entry_price=p.price_open, volume=p.volume,
                sl=p.sl or None, tp=p.tp or None, confidence=0.0,
                strategy=f"adopted_{source}", strategy_combo=f"adopted_{source}",
                opened_at=opened_iso, db_trade_id=db_id,
            )
            adopted += 1
            logger.info(f"Adopted {source} position {p.symbol} #{p.ticket} "
                        f"({action} {p.volume}) — bot now managing it")
        if adopted:
            logger.info(f"Adopted {adopted} open position(s) (incl. manual) for management + reconciliation")

    def _reconcile_pending_from_db(self):
        """
        DB-driven reconciliation (independent of in-memory tracking).

        Finds trades still 'pending' in the DB, looks up their MT5 ticket in the
        deal history, and writes the REAL outcome. This closes the loop even for
        trades that closed while the engine was down or were closed manually.
        Old pending rows with no findable deal are marked 'unknown' so they stop
        skewing win/loss stats.
        """
        if not (MT5_AVAILABLE and self.connector.is_connected()):
            return
        import datetime as _dt
        try:
            pending = self.experience_db.get_pending_trades()
        except Exception as e:
            logger.warning(f"pending fetch failed: {e}")
            return
        live_tickets = set()
        try:
            live_tickets = {p.ticket for p in (mt5.positions_get() or [])}
        except Exception:
            pass

        now = _dt.datetime.now()
        for row in pending:
            tid = row["id"]
            ticket = row.get("mt5_ticket")
            if not ticket:
                # legacy row with no ticket — can't resolve; age it out if old
                self._age_out_if_stale(row, now)
                continue
            if ticket in self.open_positions or ticket in live_tickets:
                continue  # still open — leave pending
            # closed: pull real deal result
            profit, exit_price, exit_reason = self._deal_result_by_ticket(ticket)
            if profit is None:
                self._age_out_if_stale(row, now)
                continue
            outcome = "win" if profit > 0 else "loss" if profit < 0 else "breakeven"
            try:
                self.experience_db.update_trade_outcome(
                    trade_id=tid, outcome=outcome, profit_loss=profit,
                    exit_price=exit_price, exit_reason=exit_reason or "db_reconcile")
                self.risk.record_realized(profit)
                self.trades_closed += 1
                logger.info(f"DB-reconciled trade #{tid} ticket={ticket} -> {outcome} P&L={profit:.2f}")
            except Exception as e:
                logger.warning(f"db reconcile update failed for {tid}: {e}")

    def _age_out_if_stale(self, row: dict, now):
        """Mark a pending row 'unknown' if it's older than the stale window."""
        import datetime as _dt
        ts = row.get("created_at") or row.get("timestamp") or ""
        try:
            created = _dt.datetime.fromisoformat(str(ts).replace("Z", ""))
        except Exception:
            return
        age_h = (now - created).total_seconds() / 3600.0
        if age_h > config.PENDING_STALE_HOURS:
            self.experience_db.mark_unknown(row["id"], reason="stale_no_deal")

    def _deal_result_by_ticket(self, ticket: int):
        """
        (profit, exit_price, reason) from MT5 history for a position ticket, or
        (None, None, None) if no closing deal is found yet.

        IMPORTANT: the MT5 `position=` filter on history_deals_get is unreliable
        on this build (it returns account-wide deals), so we fetch the window and
        filter by d.position_id == ticket in Python, summing ONLY that position's
        deals. We only return a result once an EXIT deal (entry==OUT) exists.
        """
        import datetime as _dt
        try:
            # NOTE: MT5 stamps deals in SERVER time, which can be several hours
            # ahead of local time. Using a local 'now' upper bound silently
            # excludes just-closed deals. Use a wide future bound so recent
            # deals are always captured (filtering is by position_id anyway).
            frm = _dt.datetime.now() - _dt.timedelta(days=14)
            to = _dt.datetime.now() + _dt.timedelta(days=1)
            all_deals = mt5.history_deals_get(frm, to)
            if not all_deals:
                return None, None, None
            deals = [d for d in all_deals if getattr(d, "position_id", None) == ticket]
            if not deals:
                return None, None, None
            entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
            exit_deals = [d for d in deals if getattr(d, "entry", None) == entry_out]
            if not exit_deals:
                return None, None, None  # still open / not yet settled
            profit = sum(d.profit + d.commission + d.swap for d in deals)
            exit_price = exit_deals[-1].price
            return round(profit, 2), exit_price, "closed"
        except Exception as e:
            logger.debug(f"deal lookup failed for {ticket}: {e}")
        return None, None, None



    # ── main loop ─────────────────────────────────────────────────────
    def run(self, max_cycles: Optional[int] = None):
        if not self.initialize():
            return
        self.running = True
        logger.info(f"ScalpEngine started | mode={config.TRADING_MODE} "
                    f"symbols={list(self.adapters)} target={config.SCALP_TARGET_TRADES}")
        try:
            while self.running:
                self.cycle += 1
                try:
                    self._run_cycle()
                except Exception as e:
                    logger.error(f"cycle error: {e}", exc_info=True)
                self._write_status()
                if self.trades_closed >= config.SCALP_TARGET_TRADES:
                    logger.info(f"Reached target of {config.SCALP_TARGET_TRADES} closed trades.")
                    self._write_status()
                    break
                if max_cycles and self.cycle >= max_cycles:
                    break
                time.sleep(config.SCALP_CYCLE_SECONDS)
        finally:
            self.running = False

    def _run_cycle(self):
        # 0) adopt any NEW manual trades the user opened since last cycle
        self._adopt_existing_positions()

        # 1) reconcile any positions that closed since last cycle
        self._reconcile_closed()

        # 1c) periodic DB-driven reconciliation (catches manual/between-run closes)
        if self.cycle % 10 == 1:
            self._reconcile_pending_from_db()

        # 1b) MANAGE open positions (BE+/trail/exit) via the A/B trade manager
        self._manage_open_positions()

        # 2) adapt strategy weights from REAL closed-trade performance (L2)
        #    + refresh per-variant performance so the trade manager biases
        #    variant selection toward what actually works (visible learning).
        if self.cycle % 5 == 1:
            try:
                perf = self.experience_db.get_strategy_performance()
                if perf:
                    self.registry.update_weights_from_performance(perf)
            except Exception as e:
                logger.warning(f"strategy weight update failed: {e}")
            try:
                self._variant_perf_cache = self.experience_db.get_variant_performance()
            except Exception as e:
                logger.warning(f"variant perf refresh failed: {e}")

        # 2b) refresh per-symbol stats occasionally (cached; cheap otherwise)
        if self.cycle % 40 == 1:
            for base, adapter in self.adapters.items():
                if adapter.spec:
                    try:
                        self.stats_engine.compute(adapter.resolved_symbol,
                                                  adapter.spec.point, adapter.spec.digits)
                    except Exception as e:
                        logger.debug(f"stats compute skip {base}: {e}")

        # refresh symbol profitability occasionally (for prioritisation + dashboard)
        if self.cycle % 20 == 1:
            try:
                self._symbol_profit_cache = self.experience_db.get_symbol_profitability()
            except Exception as e:
                logger.debug(f"symbol profitability refresh skip: {e}")
            # learn per-symbol personality (aggressive scalper vs trend rider)
            try:
                self._refresh_personalities()
            except Exception as e:
                logger.debug(f"personality refresh skip: {e}")
            # proactive self-performance research (what's working?)
            if self.perf_researcher is not None:
                try:
                    self.perf_researcher.analyze()
                except Exception as e:
                    logger.debug(f"perf research skip: {e}")
            # objective edge scoreboard (drives phase-gated sizing)
            if self.edge is not None:
                try:
                    self._edge_cache = self.edge.status()
                except Exception as e:
                    logger.debug(f"edge compute skip: {e}")

        # 2c) Adaptive intelligence: reflect -> synthesize -> backtest -> promote.
        #     Runs in a BACKGROUND thread (LLM + backtest are slow) so it never
        #     blocks live trading. Cadence: periodically, once a sample exists.
        if (self.adaptive is not None and not self._adaptive_running
                and self.cycle % config.ADAPTIVE_EVERY_CYCLES == 5):
            self._maybe_run_adaptive()

        # 3) per symbol: evaluate in priority order.
        #    Prioritise OPEN symbols, then those with the best learned
        #    profitability (pnl_per_trade) — the bot leans into the 'easiest'
        #    symbol while still covering others (incl. 24/7 crypto when gold is shut).
        def _priority(item):
            base, _ = item
            is_open = self.sessions.is_open(base)
            prof = 0.0
            for sym, m in (getattr(self, "_symbol_profit_cache", {}) or {}).items():
                if sym.upper().startswith(base.upper()):
                    prof = m.get("pnl_per_trade", 0.0)
                    break
            # open symbols first (True sorts after False, so negate), then higher profit
            return (not is_open, -prof)

        for base, adapter in sorted(self.adapters.items(), key=_priority):
            if not self.sessions.is_open(base):
                continue
            open_for_symbol = sum(
                1 for p in self.open_positions.values() if p.base_symbol == base
            )
            if open_for_symbol >= config.SCALP_MAX_OPEN_PER_SYMBOL:
                continue
            self._evaluate_and_trade(base, adapter)

    def _variant_weights_for(self, base_symbol: str) -> dict:
        """
        Give the trade manager a weight per management variant, learned from real
        outcomes. Winners get more weight; unexplored variants keep a floor so the
        bot keeps exploring (explore/exploit).
        """
        from src.trading.trade_manager import VARIANTS
        weights = {v: 1.0 for v in VARIANTS}  # exploration floor
        # variant perf may be keyed by resolved symbol; match by prefix
        for sym, vmap in (self._variant_perf_cache or {}).items():
            if not sym.upper().startswith(base_symbol.upper()):
                continue
            for v, m in vmap.items():
                if v in weights and m.get("trades", 0) >= 3:
                    # weight from win rate + a nudge from net pnl sign
                    wr = m.get("win_rate", 50) / 100.0
                    weights[v] = max(0.1, wr * 2.0 + (0.3 if m.get("net_pnl", 0) > 0 else -0.1))
        return weights

    def _position_lot(self, adapter) -> float:
        """
        PHASE-GATED position sizing (robustness rule: size follows PROVEN edge,
        never a growth target).
          * Phase 0/1 (edge not yet proven): FIXED tiny lot (SCALP_LOT / micro).
            No compounding — we are only proving expectancy.
          * Phase 2+ (edge proven): fixed-fractional risk from balance, still
            capped and clamped. Auto de-risk on drawdown handled by risk manager.
        This makes it IMPOSSIBLE to escalate size before an edge exists.
        """
        base_lot = config.SCALP_LOT
        edge = self._edge_cache or {}
        phase = edge.get("phase", 0)
        if phase < 2 or not adapter.spec:
            return base_lot
        # Phase 2+: fixed-fractional risk sizing (gentle), still micro-capped in LIVE_MICRO
        try:
            acct = self._safe_account()
            balance = acct.get("balance", 0) or 0
            if balance <= 0:
                return base_lot
            risk_amt = balance * (config.RISK_PERCENT / 100.0)
            sl_pts = config.SCALP_SL_POINTS
            tick_val = adapter.spec.tick_value or 0
            if tick_val <= 0 or sl_pts <= 0:
                return base_lot
            # loss per 1.0 lot over the stop distance
            loss_per_lot = sl_pts * (adapter.spec.point / adapter.spec.tick_size) * tick_val \
                if adapter.spec.tick_size else sl_pts * tick_val
            if loss_per_lot <= 0:
                return base_lot
            lot = risk_amt / loss_per_lot
            step = adapter.spec.volume_step or 0.01
            lot = max(adapter.spec.min_volume, min(lot, config.MAX_POSITION_SIZE))
            lot = round(round(lot / step) * step, 2)
            if config.TRADING_MODE == "LIVE_MICRO":
                lot = min(lot, config.LIVE_MICRO_MAX_LOT)
            return max(lot, adapter.spec.min_volume)
        except Exception as e:
            logger.debug(f"position lot sizing fallback: {e}")
            return base_lot

    def _symbol_paused(self, base_symbol: str) -> bool:
        """
        ACT on the PerformanceResearcher's findings: pause new entries on a symbol
        that is clearly bleeding (enough sample, negative P&L, poor win rate).
        Config: SYMBOL_PAUSE_MIN_TRADES, SYMBOL_PAUSE_PNL, SYMBOL_PAUSE_WINRATE.
        """
        if self.perf_researcher is None:
            return False
        rep = getattr(self.perf_researcher, "last_report", {}) or {}
        by_sym = rep.get("by_symbol") or {}
        # match resolved symbol keys by prefix
        for sym, m in by_sym.items():
            if not sym.upper().startswith(base_symbol.upper()):
                continue
            n = m.get("n", 0)
            if n < config.SYMBOL_PAUSE_MIN_TRADES:
                continue
            wr = m.get("win_rate", 100)
            pnl = m.get("pnl", 0)
            # Pause if EITHER failure signal is clear (OR, not AND): a badly
            # negative P&L OR a very poor win rate. The previous AND-logic let
            # bleeders through (e.g. ETHUSD 9% WR but tiny -0.69 pnl; XAGUSD
            # -38.86 pnl but ~47% WR — neither tripped both conditions).
            if pnl <= config.SYMBOL_PAUSE_PNL or wr < config.SYMBOL_PAUSE_WINRATE:
                logger.info(f"{base_symbol}: PAUSED by researcher "
                            f"(pnl {pnl}, WR {wr}%, n {n}) — bleeding, no new entries")
                return True
        return False

    def _symbol_personality_for(self, base_symbol: str) -> dict:
        """
        Learn a per-symbol trading 'personality' from REAL closed trades:
          - aggressive_scalper: quick wins, cut givebacks fast (works when the
            symbol mean-reverts / spikes then fades)
          - trend_rider: winners run longer than losers, tolerate more giveback
        Derived from avg win-hold vs loss-hold and win rate. Cached and refreshed
        with the profitability cache. Returns {} (neutral defaults) until enough data.
        """
        stats = getattr(self, "_symbol_personality_cache", {}) or {}
        for sym, p in stats.items():
            if sym.upper().startswith(base_symbol.upper()):
                return p
        return {}

    def _refresh_personalities(self):
        """Compute per-symbol personality from closed trades (called on a cadence)."""
        import sqlite3, statistics
        try:
            conn = sqlite3.connect(self.experience_db.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT symbol, outcome, profit_loss, timestamp, exit_reason "
                "FROM trades WHERE outcome IN ('win','loss')"
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.debug(f"personality refresh skip: {e}")
            return
        from collections import defaultdict
        by_sym = defaultdict(list)
        for r in rows:
            by_sym[r["symbol"]].append(dict(r))
        out = {}
        for sym, trades in by_sym.items():
            if len(trades) < 8:
                continue
            wins = [t for t in trades if t["outcome"] == "win"]
            losses = [t for t in trades if t["outcome"] == "loss"]
            wr = len(wins) / len(trades)
            avg_win = statistics.mean([t["profit_loss"] for t in wins]) if wins else 0
            avg_loss = abs(statistics.mean([t["profit_loss"] for t in losses])) if losses else 0
            # if wins are bigger than losses -> letting winners run pays (trend_rider)
            # if wins are small & frequent -> scalp fast (aggressive_scalper)
            if avg_win > avg_loss * 1.3 and wr >= 0.4:
                out[sym] = {"style": "trend_rider", "giveback_frac": 0.6}
            elif wr >= 0.5 and avg_win <= avg_loss:
                out[sym] = {"style": "aggressive_scalper", "giveback_frac": 0.3}
            else:
                out[sym] = {"style": "neutral", "giveback_frac": 0.45}
        if out:
            self._symbol_personality_cache = out
            logger.info(f"Symbol personalities: { {k: v['style'] for k, v in out.items()} }")

    def _manage_open_positions(self):
        """Run the trade manager over each open position; execute SL/exit intents."""
        if not self.open_positions:
            return
        for ticket, pos in list(self.open_positions.items()):
            adapter = self.adapters.get(pos.base_symbol)
            if adapter is None or adapter.spec is None:
                continue
            st = self.managed.get(ticket)
            if st is None:
                # assign a management variant (learning biases this)
                atr_pts = self.stats_engine.atr_points(pos.symbol, pos.timeframe) or \
                    (config.SCALP_SL_POINTS)
                # is this position aligned with the higher-TF trend? (enables ride mode)
                trend_aligned = False
                try:
                    trend_aligned, _, _ = self._mtf_aligned(adapter, pos.action)
                except Exception:
                    pass
                st = self.trade_manager.register(pos, atr_points=atr_pts,
                                                 trend_aligned=trend_aligned)
                pos.mgmt_variant = st.variant
                self.managed[ticket] = st
                # persist the variant on the DB row so outcomes are attributable
                if pos.db_trade_id is not None:
                    try:
                        self._set_trade_variant(pos.db_trade_id, st.variant)
                    except Exception as e:
                        logger.warning(f"variant tagging failed for trade {pos.db_trade_id}: {e}")
            tick = adapter.live_tick()
            if tick is None:
                continue
            price = tick.bid if pos.action == "buy" else tick.ask
            spread_pts = ((tick.ask - tick.bid) / adapter.spec.point) if adapter.spec.point else 0

            # ── session pre-close handling (15–30 min before close) ──
            if self.sessions.in_preclose_window(pos.base_symbol, lo=15, hi=30):
                atr_short = self.stats_engine.atr_points(pos.symbol, "M15") or st.atr_points
                pc = self.trade_manager.preclose_decision(
                    st, price, adapter.spec.point, spread_pts, atr_short)
                if pc:
                    if "modify_sl" in pc:
                        adapter.modify_sl(ticket, pc["modify_sl"])
                    elif "close" in pc:
                        res = adapter.close(ticket)
                        logger.info(f"Pre-close managed {ticket}: {pc['close']} ({res.reason})")
                    continue  # pre-close decision takes precedence this cycle

            intent = self.trade_manager.evaluate(st, price, adapter.spec.point, spread_pts)
            if intent:
                if "modify_sl" in intent:
                    adapter.modify_sl(ticket, intent["modify_sl"])
                elif "close" in intent:
                    res = adapter.close(ticket)
                    logger.info(f"Manager closed {ticket}: {intent['close']} ({res.reason})")
                continue

            # ── HYBRID_LLM: throttled LLM review (what makes this arm distinct) ──
            if self.trade_manager.llm_review_due(st):
                self._llm_trade_review(st, pos, adapter, price, spread_pts)

    def _llm_trade_review(self, st, pos, adapter, price, spread_pts):
        """
        Periodic LLM review for HYBRID_LLM-managed trades. The LLM sees the trade
        context and returns HOLD / TIGHTEN / EXIT. This runs at most every few
        minutes (throttled) so it never slows the fast protective path.

        Degrades honestly: if no LLM is available, it logs that HYBRID_LLM is
        running rules-only (it does NOT silently pretend to be a different arm).
        """
        try:
            from src.core.llm import get_llm
        except Exception:
            logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM unavailable — rules-only review")
            return

        if st.action == "buy":
            profit_pts = (price - st.entry) / (adapter.spec.point or 1)
        else:
            profit_pts = (st.entry - price) / (adapter.spec.point or 1)

        prompt = (
            "You are a scalp trade-management reviewer. Given the open trade, reply "
            "with EXACTLY one word: HOLD, TIGHTEN, or EXIT.\n"
            f"Symbol: {st.symbol}\nSide: {st.action}\nEntry: {st.entry}\n"
            f"Current price: {price}\nProfit (points): {profit_pts:.0f}\n"
            f"Spread (points): {spread_pts:.0f}\nATR (points): {st.atr_points:.0f}\n"
            f"Already at break-even: {st.moved_to_be}\n"
            "Rules: EXIT only if the move looks exhausted/reversing against us. "
            "TIGHTEN if strongly in profit and worth locking in. Otherwise HOLD."
        )
        try:
            llm = get_llm(temperature=0.2)
            resp = llm.invoke(prompt)
            from src.core.llm import extract_text
            text = extract_text(resp).upper()
        except Exception as e:
            logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM review failed ({e}) — rules-only")
            return

        decision = "HOLD"
        for k in ("EXIT", "TIGHTEN", "HOLD"):
            if k in text:
                decision = k
                break
        st.actions.append({"t": time.time(), "action": f"llm_{decision.lower()}", "price": price})
        logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM review -> {decision} (profit {profit_pts:.0f}pts)")

        if decision == "EXIT" and profit_pts > spread_pts:
            # only act on EXIT when not crystallising a spread-sized loss
            res = adapter.close(st.ticket)
            logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM EXIT ({res.reason})")
        elif decision == "TIGHTEN" and profit_pts > (spread_pts + 20):
            tighten = max((st.atr_points or 60) * 0.3, spread_pts + 10) * adapter.spec.point
            new_sl = (price - tighten) if st.action == "buy" else (price + tighten)
            if self.trade_manager._sl_improves(st, new_sl):
                st.sl = new_sl
                adapter.modify_sl(st.ticket, round(new_sl, 6))
                logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM TIGHTEN -> SL {new_sl:.5f}")

    def _set_trade_variant(self, db_trade_id: int, variant: str):
        import sqlite3
        conn = sqlite3.connect(self.experience_db.db_path)
        conn.execute("UPDATE trades SET mgmt_variant=? WHERE id=?", (variant, db_trade_id))
        conn.commit(); conn.close()

    def _safe_account(self) -> dict:
        try:
            a = get_account_info()
            return a if isinstance(a, dict) else {}
        except Exception:
            return {}

    def _maybe_run_adaptive(self):
        """Run the adaptive intelligence loop in a background thread (non-blocking)."""
        import threading

        def _work():
            self._adaptive_running = True
            try:
                summary = self.adaptive.run_once(
                    list(self.adapters.keys()),
                    timeframe=config.ENTRY_TIMEFRAME,
                    min_sample=config.ADAPTIVE_MIN_SAMPLE,
                )
                if any(summary.get(k) for k in ("promoted", "rejected", "synthesized")):
                    logger.info(f"Adaptive pass: {summary}")
            except Exception as e:
                logger.warning(f"adaptive loop error: {e}")
            finally:
                self._adaptive_running = False

        threading.Thread(target=_work, daemon=True, name="adaptive").start()


    # ── signal + entry ────────────────────────────────────────────────
    def _mtf_aligned(self, adapter: BrokerAdapter, action: str):
        """
        Check higher-timeframe directional alignment for a proposed 1m entry.

        Returns (aligned: bool, detail: str). We require that the proposed action
        does not fight the majority of higher timeframes. Uses cached stats
        (computed periodically) so it stays fast.
        """
        resolved = adapter.resolved_symbol
        # ensure we have stats; compute lazily if missing
        s = self.stats_engine._cache.get(resolved)
        if s is None and adapter.spec:
            s = self.stats_engine.compute(resolved, adapter.spec.point, adapter.spec.digits)
        if not s:
            return True, "no stats (allow)", 0

        want = "bullish" if action == "buy" else "bearish"
        higher_tfs = config.MTF_ALIGNMENT_TFS
        dirs = []
        for tf in higher_tfs:
            d = s.timeframes.get(tf, {}).get("direction")
            if d:
                dirs.append(d)
        if not dirs:
            return True, "no higher-tf dirs (allow)", 0

        agree = sum(1 for d in dirs if d == want)
        against = sum(1 for d in dirs if d != "neutral" and d != want)
        if against > agree:
            return False, f"{against} higher TFs oppose {want} vs {agree} agree ({dirs})", against
        return True, f"aligned ({agree}/{len(dirs)} agree)", 0

    def _evaluate_and_trade(self, base: str, adapter: BrokerAdapter):
        # don't open when the market is closed for this symbol
        if not self.sessions.is_open(base):
            return
        # ACT on researcher findings: if this symbol is bleeding badly, pause new
        # entries on it (the researcher flags it; here we enforce it). This is the
        # feedback loop from analysis -> action.
        if self._symbol_paused(base):
            return
        resolved = adapter.resolved_symbol
        rates = get_rates(resolved, timeframe=config.ENTRY_TIMEFRAME, count=120)
        if not rates or len(rates) < 30:
            logger.warning(f"{base}: insufficient rate data")
            return

        indicators = compute_full_indicators(rates)
        if not indicators or indicators.get("close") is None:
            return
        # tag the symbol so symbol-specific strategies (e.g. CryptoRTI/BTC) can filter
        indicators["symbol"] = resolved
        indicators["base_symbol"] = base

        # ensemble signal from the 7 real strategies (low agreement bar for sampling)
        signal = self.registry.get_ensemble_signal(indicators, min_agreement=2)
        if signal.action == "hold":
            return

        # ── RAG: adjust confidence from similar historical patterns (C2) ──
        # The vector store is now READ at entry (not just written on close): if
        # similar past setups mostly lost, confidence is cut (or the trade vetoed);
        # if they mostly won, confidence is boosted.
        rag = None
        if self.pattern_matcher is not None:
            try:
                rag = self.pattern_matcher.analyze_current_market(indicators)
                n_similar = rag.get("similar_patterns_found", 0)
                adj = float(rag.get("confidence_adjustment", 0.0) or 0.0)
                # Only let the RAG influence decisions once there's a MEANINGFUL,
                # non-trivial sample — otherwise a tiny/biased early history would
                # freeze trading (and we'd never gather new data to learn from).
                if n_similar >= 10:
                    signal.confidence = max(0.0, min(1.0, signal.confidence + adj))
                    hist_wr = rag.get("historical_win_rate", 50.0)
                    # hard veto only with strong evidence AND a real sample
                    if hist_wr < 25 and n_similar >= 25:
                        logger.info(f"{base}: RAG veto (hist win rate {hist_wr:.0f}% over "
                                    f"{n_similar} similar)")
                        return
            except Exception as e:
                logger.debug(f"RAG analyze skip: {e}")

        if signal.confidence < config.SCALP_CONFIDENCE_MIN:
            return

        # ── Multi-timeframe alignment as a QUALITY MODIFIER (not a hard block) ──
        # A counter-trend 1m scalp is lower quality, so instead of a binary block
        # we PENALISE its confidence proportionally to how many higher TFs oppose
        # it. A genuinely strong counter-trend signal can still clear the entry
        # threshold after the penalty; a weak one falls below it and is skipped.
        # This fixes both failure modes: crypto blocked 100% in a trend, AND weak
        # counter-trend trades slipping through.
        if config.MTF_ALIGNMENT_ENABLED:
            aligned, detail, oppose = self._mtf_aligned(adapter, signal.action)
            if not aligned:
                penalty = config.MTF_COUNTERTREND_PENALTY * max(oppose, 1)
                before = signal.confidence
                signal.confidence = max(0.0, signal.confidence - penalty)
                logger.info(f"{base}: counter-trend {signal.action} penalised "
                            f"{before:.2f}->{signal.confidence:.2f} ({detail})")

        # Final confidence gate (after MTF quality penalty)
        if signal.confidence < config.SCALP_CONFIDENCE_MIN:
            return

        # scalp SL/TP — adaptive to each symbol's spread & minimum stop distance.
        # Fixed point targets work for gold but not for high-priced/wide-spread
        # symbols like BTCUSD, so we take the max of:
        #   * configured scalp points
        #   * broker minimum stop distance (trade_stops_level) + current spread
        #   * a small percentage of price (keeps BTC stops sane)
        spec = adapter.spec
        tick = adapter.live_tick()
        if tick is None:
            return
        price = tick.ask if signal.action == "buy" else tick.bid
        pt = spec.point

        try:
            si = mt5.symbol_info(resolved)
            stops_level = getattr(si, "trade_stops_level", 0) or 0
            spread_pts = (tick.ask - tick.bid) / pt if pt else 0
        except Exception:
            stops_level, spread_pts = 0, 0

        min_dist_pts = (stops_level + spread_pts) * 1.5 + 5      # safety buffer
        pct_pts = (price * 0.0015) / pt if pt else 0             # 0.15% of price
        sl_pts = max(config.SCALP_SL_POINTS, min_dist_pts, pct_pts)
        tp_pts = max(config.SCALP_TP_POINTS, min_dist_pts * 1.5, pct_pts * 1.5)

        if signal.action == "buy":
            sl = price - sl_pts * pt
            tp = price + tp_pts * pt
        else:
            sl = price + sl_pts * pt
            tp = price - tp_pts * pt
        sl = round(sl, spec.digits)
        tp = round(tp, spec.digits)

        # which strategies agreed (for learning attribution)
        combo = [n for n, s in self.registry.run_all_strategies(indicators)
                 if s.action == signal.action]
        combo_str = ",".join(combo)

        comment = f"scalp-{signal.action[:1]}-{base[:6]}"
        # Broker-side SL is mandatory — never place a naked position (esp. gold).
        if not sl or sl <= 0:
            logger.warning(f"{base}: refusing entry with no valid stop-loss")
            return

        # ── Phase 3: master risk gate ──
        risk = self.risk.check_entry(spread_points=spread_pts)
        if not risk.allowed:
            if risk.halted:
                logger.warning(f"TRADING HALTED: {risk.reason}")
            else:
                logger.info(f"{base}: entry blocked by risk ({risk.reason})")
            return

        result = adapter.place(signal.action, self._position_lot(adapter), sl=sl, tp=tp, comment=comment)

        if not result.ok:
            logger.info(f"{base}: no entry ({result.reason})")
            return

        # record as pending in experience DB
        trade_signal = {
            "symbol": resolved,
            "action": signal.action,
            "price": result.price,
            "stop_loss": sl,
            "take_profit": tp,
            "position_size": result.filled_volume,
            "confidence": signal.confidence,
            "strategy_used": combo[0] if combo else "ensemble",
        }
        db_id = self.experience_db.record_trade(
            signal=trade_signal, indicators=indicators, outcome="pending",
            strategy_combination=combo_str, timeframe=config.ENTRY_TIMEFRAME,
            mt5_ticket=result.ticket,
        )

        self.open_positions[result.ticket] = TrackedPosition(
            ticket=result.ticket, symbol=resolved, base_symbol=base,
            action=signal.action, entry_price=result.price, volume=result.filled_volume,
            sl=sl, tp=tp, confidence=signal.confidence,
            strategy=combo[0] if combo else "ensemble", strategy_combo=combo_str,
            opened_at=datetime.now(timezone.utc).isoformat(), db_trade_id=db_id,
            indicators={k: v for k, v in indicators.items()
                        if isinstance(v, (int, float, str, bool))},
        )
        self.trades_opened += 1
        logger.info(f"OPENED {signal.action.upper()} {resolved} {result.filled_volume}@{result.price} "
                    f"ticket={result.ticket} conf={signal.confidence:.2f} [{combo_str}]")

    # ── reconciliation of closed trades (REAL outcomes) ───────────────
    def _reconcile_closed(self):
        if not self.open_positions:
            return
        if not (MT5_AVAILABLE and self.connector.is_connected()):
            return

        try:
            live = mt5.positions_get() or []
            live_tickets = {p.ticket for p in live}
        except Exception as e:
            logger.warning(f"positions_get failed: {e}")
            return

        for ticket in list(self.open_positions.keys()):
            if ticket in live_tickets:
                continue  # still open
            # closed — pull the real deal outcome from history
            profit, exit_price, exit_reason = self._fetch_deal_result(ticket, self.open_positions[ticket])
            if profit is None:
                # exit deal not settled yet — leave tracked & pending, retry next cycle
                logger.info(f"Ticket {ticket} closed but no exit deal yet; will retry")
                continue
            tp = self.open_positions.pop(ticket)
            self.managed.pop(ticket, None)   # clear management state
            outcome = "win" if profit > 0 else "loss" if profit < 0 else "breakeven"

            # feed realized P&L to the risk manager (drives the daily-loss halt)
            try:
                self.risk.record_realized(profit)
            except Exception as e:
                logger.debug(f"risk record_realized skip: {e}")

            if tp.db_trade_id is not None:
                try:
                    self.experience_db.update_trade_outcome(
                        trade_id=tp.db_trade_id, outcome=outcome,
                        profit_loss=profit, exit_price=exit_price, exit_reason=exit_reason,
                    )
                except Exception as e:
                    logger.warning(f"update_trade_outcome failed: {e}")

            if self.vector_store is not None:
                try:
                    self.vector_store.store_pattern(
                        indicators=tp.indicators,
                        metadata={
                            "timestamp": tp.opened_at,
                            "price": tp.entry_price,
                            "strategy_used": tp.strategy,
                            "action": tp.action,
                            "outcome": outcome,
                            "profit_loss": profit,
                            "symbol": tp.symbol,
                        },
                    )
                except Exception as e:
                    logger.debug(f"vector store pattern skip: {e}")

            self.trades_closed += 1
            logger.info(f"CLOSED {tp.symbol} ticket={ticket} -> {outcome} "
                        f"P&L={profit:.2f} ({exit_reason}) [{self.trades_closed} closed]")

    def _fetch_deal_result(self, ticket: int, tp: TrackedPosition):
        """
        Return (profit, exit_price, exit_reason) from real MT5 deals, retrying a
        few times in case the closing deal hasn't settled yet. Returns
        (None, None, None) if no EXIT deal exists — the caller must then leave
        the trade pending rather than mis-record it as breakeven.
        """
        for attempt in range(3):
            profit, exit_price, reason = self._deal_result_by_ticket(ticket)
            if profit is not None:
                if tp.tp and abs(exit_price - tp.tp) <= (tp.tp * 0.0008):
                    reason = "tp"
                elif tp.sl and abs(exit_price - tp.sl) <= (tp.sl * 0.0008):
                    reason = "sl"
                return profit, exit_price, reason
            time.sleep(1.0)
        logger.warning(f"No exit deal yet for ticket {ticket}; leaving pending")
        return None, None, None

    # ── status file for dashboard ─────────────────────────────────────
    def _write_status(self):
        try:
            algo = get_algo_status()
            acct = get_account_info()
            symbols = []
            for base, ad in self.adapters.items():
                t = ad.live_tick()
                symbols.append({
                    "base": base,
                    "resolved": ad.resolved_symbol,
                    "tradable": ad.spec.tradable if ad.spec else False,
                    "bid": getattr(t, "bid", None),
                    "ask": getattr(t, "ask", None),
                    "open": self.sessions.is_open(base),
                    "minutes_to_close": self.sessions.minutes_to_close(base),
                })
            status = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "running": self.running,
                "mode": config.TRADING_MODE,
                "cycle": self.cycle,
                "trades_opened": self.trades_opened,
                "trades_closed": self.trades_closed,
                "target_trades": config.SCALP_TARGET_TRADES,
                "open_positions": [
                    {
                        "ticket": p.ticket, "symbol": p.symbol, "action": p.action,
                        "entry": p.entry_price, "volume": p.volume, "sl": p.sl, "tp": p.tp,
                        "confidence": p.confidence, "strategy": p.strategy,
                        "opened_at": p.opened_at, "mgmt_variant": p.mgmt_variant,
                    } for p in self.open_positions.values()
                ],
                "risk": self.risk.status(),
                "symbol_profitability": getattr(self, "_symbol_profit_cache", {}),
                "variant_performance": getattr(self, "_variant_perf_cache", {}),
                "adaptive": (self.adaptive.status() if self.adaptive else {}),
                "performance_research": (self.perf_researcher.status() if self.perf_researcher else {}),
                "edge": (self._edge_cache or {}),
                "algo_trading": {
                    "can_trade": algo.can_trade,
                    "terminal_trade_allowed": algo.terminal_trade_allowed,
                    "account_trade_allowed": algo.account_trade_allowed,
                    "connected": algo.connected,
                    "reason": algo.reason,
                },
                "account": acct if isinstance(acct, dict) else {},
                "symbols": symbols,
            }
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = STATUS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(status, f, indent=2, default=str)
            os.replace(tmp, STATUS_PATH)
        except Exception as e:
            logger.warning(f"write_status failed: {e}")


def run_scalp_engine(max_cycles: Optional[int] = None):
    engine = ScalpEngine()
    engine.run(max_cycles=max_cycles)
    return engine


if __name__ == "__main__":
    run_scalp_engine()
