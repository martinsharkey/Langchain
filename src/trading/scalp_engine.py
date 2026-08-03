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

        # Register the PRIMARY OsMA 7-indicator confluence strategy (#29), ported
        # from the proven GoldShark EAs. Symbol-agnostic; status=testing until it
        # proves out per symbol via walk-forward + the #27 checkpointer.
        try:
            from src.strategies.osma_confluence import register as register_osma
            register_osma(self.registry)
        except Exception as e:
            logger.warning(f"OsMA_Confluence strategy not registered: {e}")

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
        # Bug 2/3: when the MANAGER closes a position it must not silently discard the
        # excursion state before _reconcile_closed can persist MFE/MAE. Stash it in a
        # tombstone cache keyed by ticket; reconcile reads here if `managed` is empty.
        self._closed_state_cache: dict[int, object] = {}
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
        # SymbolGovernor: learning-loop pause/fail decisions + failure reports
        try:
            from src.learning.symbol_governor import SymbolGovernor
            kb = getattr(self.perf_researcher, "kb", None) if self.perf_researcher else None
            if kb is None:
                try:
                    from src.learning.knowledge_base import KnowledgeBase
                    kb = KnowledgeBase()
                except Exception:
                    kb = None
            self.governor = SymbolGovernor(knowledge_base=kb)
        except Exception as e:
            logger.warning(f"SymbolGovernor unavailable: {e}")
            self.governor = None
        # Trade post-mortem: data-driven self-reflection on each closed trade
        try:
            from src.learning.post_mortem import TradePostMortem
            _kb = getattr(self.governor, "kb", None)
            self.post_mortem = TradePostMortem(self.experience_db, knowledge_base=_kb)
        except Exception as e:
            logger.warning(f"TradePostMortem unavailable: {e}")
            self.post_mortem = None
        self._postmortem_cache = {}
        self._edge_cache = {}
        self._symbol_profit_cache = {}

        # Self-learning parameter optimizer (autonomous indicator tuning)
        try:
            from src.learning.backtester import Backtester
            from src.learning.param_optimizer import ParameterOptimizer
            _bt = Backtester(self.registry)
            self.param_optimizer = ParameterOptimizer(
                self.registry,
                lambda sym, params, sl_atr, tp_rr: _bt.walkforward_focused(
                    sym, params, sl_atr=sl_atr, tp_rr=tp_rr),
            )
        except Exception as e:
            logger.warning(f"ParameterOptimizer unavailable: {e}")
            self.param_optimizer = None

        # Config checkpointer (#27/#25): revert-to-best-config + learn-from-failure.
        # Keeps a per-symbol best-known config (by REALISED expectancy) and reverts
        # when a change degrades live results, recording the failed direction.
        # A KnowledgeStore is wired in so failed tuning directions are stored
        # SEMANTICALLY (not just to disk), closing the learn-from-failure loop so
        # the reflection layer can recall "we tried this and it failed". Lazy +
        # non-fatal (MiniLM downloads once; if unavailable we still persist to disk).
        self.knowledge_store = None
        try:
            from src.learning.knowledge_store import KnowledgeStore
            self.knowledge_store = KnowledgeStore()
            # sync durable PROJECT knowledge (the same insights saved to Kilo memory)
            # into the BOT's store so the running bot learns from them too (#13).
            try:
                from src.learning.knowledge_sync import sync_project_knowledge
                sync_project_knowledge(self.knowledge_store)
            except Exception as e:
                logger.debug(f"knowledge sync skip: {e}")
        except Exception as e:
            logger.warning(f"KnowledgeStore unavailable (failures persist to disk only): {e}")
        try:
            from src.learning.config_checkpointer import ConfigCheckpointer
            self.checkpointer = ConfigCheckpointer(knowledge_store=self.knowledge_store)
        except Exception as e:
            logger.warning(f"ConfigCheckpointer unavailable: {e}")
            self.checkpointer = None
        # per-symbol giveback override applied by a revert (None = use normal logic)
        self._giveback_override: dict[str, float] = {}
        # dashboard control state (#19): live pause + scalping toggle
        self._paused = False
        self._scalping_enabled = True
        self._last_control_ts = None
        # #36 live per-symbol exit override (sl_atr/tp_rr) set by the DynamicFixer,
        # bypassing the backtest gate so a diagnosed "SL too tight" fix reaches
        # live trades immediately (checkpointer verifies + reverts if worse).
        self._exit_override: dict = {}

        # mql5 knowledge RAG (#22) + edge discovery (#31) + continual researcher (#32).
        # All optional/non-fatal; they make the learning loop continually improve.
        self.mql5_knowledge = None
        self.edge_discovery = None
        self.researcher = None
        try:
            from src.learning.mql5_knowledge import MQL5Knowledge
            self.mql5_knowledge = MQL5Knowledge()
        except Exception as e:
            logger.warning(f"MQL5Knowledge unavailable: {e}")
        try:
            from src.learning.edge_discovery import EdgeDiscovery
            from src.learning.backtester import Backtester
            self.edge_discovery = EdgeDiscovery(
                self.registry, Backtester(self.registry),
                knowledge_store=self.knowledge_store)
        except Exception as e:
            logger.warning(f"EdgeDiscovery unavailable: {e}")
        try:
            from src.learning.continual_researcher import ContinualResearcher
            from src.learning.pattern_optimizer import PatternOptimizer
            from src.learning.excursion_analyzer import ExcursionAnalyzer
            from src.mt5.data import get_rates as _get_rates
            _patopt = PatternOptimizer(_get_rates)
            _exc = ExcursionAnalyzer(_get_rates)
            _robust = None
            try:
                from scripts.robust_tester import RobustTester
                _robust = RobustTester(days=40, n_random=8, iters=6)
            except Exception as e:
                logger.debug(f"RobustTester unavailable: {e}")
            self.researcher = ContinualResearcher(
                self.experience_db, mql5_knowledge=self.mql5_knowledge,
                knowledge_store=self.knowledge_store, edge_discovery=self.edge_discovery,
                pattern_optimizer=_patopt, apply_exit_config=self._apply_exit_config,
                excursion_analyzer=_exc, robust_tester=_robust)
        except Exception as e:
            logger.warning(f"ContinualResearcher unavailable: {e}")

        # #25: give the optimizer its ReAct alternatives — mql5-grounded tuning
        # direction + avoid the checkpointer's failed directions (no blind search).
        if self.param_optimizer is not None:
            try:
                self.param_optimizer.mql5_knowledge = self.mql5_knowledge
                if self.checkpointer is not None:
                    self.param_optimizer.is_failed_fn = self.checkpointer.is_failed
            except Exception as e:
                logger.debug(f"optimizer ReAct wiring skip: {e}")

        # #24: per-symbol graduation (edge -> size-up gate). Non-fatal.
        self.graduation = None
        try:
            from src.learning.graduation import Graduation
            if self.edge is not None:
                self.graduation = Graduation(self.edge, checkpointer=self.checkpointer)
        except Exception as e:
            logger.warning(f"Graduation unavailable: {e}")

        # #44/#46: whale outcome store — the bot records live whale signals + their
        # realised candle response, building its OWN dataset (self-sustaining, no
        # reliance on Danny history). Seeded once from the Danny correlation study.
        self.whale_outcomes = None
        try:
            from src.cryptorti.whale_outcome_store import WhaleOutcomeStore
            self.whale_outcomes = WhaleOutcomeStore()
            if self.whale_outcomes.stats()["resolved"] == 0:
                self.whale_outcomes.seed_from_study()
        except Exception as e:
            logger.warning(f"WhaleOutcomeStore unavailable: {e}")

        # #45.1: GitHub-visible learning-adjustments log (reporting only, non-fatal).
        self.learning_log = None
        try:
            from src.learning.learning_log import LearningLog
            self.learning_log = LearningLog()
        except Exception as e:
            logger.warning(f"LearningLog unavailable: {e}")

        # #36: intelligent per-symbol ReAct fixer (applies post-mortem fixes LIVE,
        # escalates exit-fix -> retune -> strategy-switch -> research). Non-fatal.
        self.fixer = None
        try:
            from src.learning.dynamic_fixer import DynamicFixer
            self.fixer = DynamicFixer(self)
        except Exception as e:
            logger.warning(f"DynamicFixer unavailable: {e}")

        # #42: ONNX learned trade-outcome predictor (learned entry confidence).
        # Non-fatal; predict() returns None if no model yet -> engine uses existing
        # confidence. Trained on a cadence in the adaptive loop.
        self.onnx_predictor = None
        try:
            from src.learning.onnx_predictor import OnnxOutcomePredictor
            self.onnx_predictor = OnnxOutcomePredictor(self.experience_db)
        except Exception as e:
            logger.warning(f"OnnxOutcomePredictor unavailable: {e}")

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

        # Reversal-signature analyzer — measures whether the confluence indicators
        # reliably turn at the MFE peak (signal-driven exit/hold research). Reads
        # the live-captured peak/exit snapshots; stores the per-symbol signature.
        try:
            from src.learning.reversal_signature import ReversalSignatureAnalyzer
            self.reversal_analyzer = ReversalSignatureAnalyzer(
                self.experience_db,
                point_fn=lambda s: (self.adapters[s].spec.point
                                    if s in self.adapters and self.adapters[s].spec else
                                    (0.01 if "XAU" in s.upper() else 0.0001)))
            self._reversal_signatures = {}   # base_symbol -> latest signature dict
        except Exception as e:
            logger.warning(f"reversal analyzer unavailable: {e}")
            self.reversal_analyzer = None
            self._reversal_signatures = {}

        # HTF context — multi-timeframe alignment for ENTRY + trade MANAGEMENT.
        # Every symbol (incl. gold) now "sees" M5/M15/M30/H1 to survive wicks when
        # HTF still aligns, and to cut when HTF momentum genuinely reverses.
        try:
            from src.learning.htf_context import HTFContext
            self.htf = HTFContext(get_rates)
        except Exception as e:
            logger.warning(f"HTFContext unavailable: {e}")
            self.htf = None
        # Self-managing TRAINING/LIVE mode per symbol (removes manual loosen/tighten)
        try:
            from src.learning.operating_mode import OperatingModeManager
            self.mode_mgr = OperatingModeManager(self.experience_db)
        except Exception as e:
            logger.warning(f"OperatingModeManager unavailable: {e}")
            self.mode_mgr = None
        # observability counters (learning-health, per Grok review)
        self._rag_lookups = 0
        self._rag_hits = 0
        self._last_weight_refresh = None
        self._last_learning_error = None

    # ── setup ─────────────────────────────────────────────────────────
    def initialize(self) -> bool:
        self.connector.initialize()
        if not self.connector.is_connected():
            logger.error("MT5 not connected — cannot start scalp engine")
            return False
        # #21: resolve + set the connected account so all writes/stats scope to it,
        # and detect demo/live or account switches (never blend histories).
        try:
            self._resolve_and_set_account()
        except Exception as e:
            logger.debug(f"account resolve skip: {e}")
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
        # Arm the reversal-signature exit from ANY data already in the DB (incl. the
        # seeded GoldShark lifecycle records) so the gated signal-driven exit/hold is
        # active from cycle 1, not only after the background researcher loop first runs.
        self._load_seeded_signatures()
        return True

    def _load_seeded_signatures(self):
        """Populate _reversal_signatures at startup from whatever the DB already holds
        (seeded GoldShark + prior live trades). Uses the same per-symbol scale-free
        analyzer + the same >=20-trade activation gate as the live loop."""
        if self.reversal_analyzer is None:
            return
        for _b in list(self.adapters.keys()):
            try:
                sig = self.reversal_analyzer.signature_from_captured(_b)
                meta = sig.get("_meta", {}) if sig else {}
                if meta.get("n_trades", 0) >= 20:
                    self._reversal_signatures[_b] = sig
                    osma = sig.get("osma", {})
                    logger.info(f"[REVERSAL-SEED] {_b}: armed from {meta.get('n_trades')} trades "
                                f"(osma retain {osma.get('median_retained_frac')}, "
                                f"shrinks {osma.get('shrank_toward_neutral_pct')}%, "
                                f"capture {meta.get('median_capture_ratio')})")
                    # persist to the KnowledgeStore so the RESEARCHER recalls the
                    # seeded exit signature (integration into the learning loop).
                    if self.knowledge_store is not None:
                        try:
                            self.knowledge_store.remember(
                                key=f"reversal_signature_{_b.upper()}", kind="finding",
                                topic="exit_signature",
                                text=(f"{_b} seeded reversal signature (n={meta.get('n_trades')}, "
                                      f"GoldShark real-tick): osma retained-at-exit "
                                      f"{osma.get('median_retained_frac')} (shrinks toward neutral "
                                      f"{osma.get('shrank_toward_neutral_pct')}% of trades), "
                                      f"osma peak ~{osma.get('median_peak_over_atr')}xATR, "
                                      f"capture {meta.get('median_capture_ratio')}. Use OsMA reversal "
                                      f"depth as the per-symbol exit tell."))
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"seed signature skip {_b}: {e}")
        if not self._reversal_signatures:
            logger.info("[REVERSAL-SEED] no symbol has >=20 captured trades yet; "
                        "signal-driven exit stays in measuring mode")

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
        if not config.LEARNING_ADAPTATION_ENABLED:
            logger.warning(
                "LEARNING ADAPTATION FROZEN (LEARNING_ADAPTATION_ENABLED=false): the bot "
                "will TRADE, reconcile real outcomes, and record data, but will NOT auto-mutate "
                "strategy weights / giveback personality / variant bias / synthesize strategies. "
                "Use this while proving the learning loop is net-positive (#27/#23)."
            )
        else:
            logger.info("Learning adaptation ENABLED (online self-tuning active).")

        # #13: recall durable lessons at startup so each run visibly begins with
        # its accumulated knowledge (corrections + decisions + prior failures).
        if self.knowledge_store is not None:
            try:
                lessons = []
                for kind in ("correction", "decision"):
                    lessons += self.knowledge_store.recall(
                        "trading edge exit tuning symbol strategy", n_results=3, kind=kind)
                if lessons:
                    logger.info(f"[KNOWLEDGE] starting with {self.knowledge_store.count()} stored "
                                f"lessons. Top recalled:")
                    for h in lessons[:5]:
                        logger.info(f"  - ({h['metadata'].get('kind')}) {h['text'][:110]}")
                    self._known_lessons = [h["text"] for h in lessons[:5]]
            except Exception as e:
                logger.debug(f"knowledge startup recall skip: {e}")
        # SAFETY: if we are managing REAL open positions but are NOT in a live
        # mode, every manager exit/SL-modify will be SIMULATED (no real order).
        # A winner the manager decides to lock in will keep running on the
        # broker. Make this impossible to miss.
        if self.open_positions and not config.is_live_mode():
            logger.warning(
                f"*** {len(self.open_positions)} REAL open position(s) are being "
                f"managed in mode={config.TRADING_MODE} — manager exits and SL "
                f"changes will be SIMULATED ONLY (no real orders). Winners the "
                f"bot decides to close will NOT actually close. Restart with "
                f"LIVE_MICRO to manage them for real. ***"
            )
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
                # FAST MANAGEMENT SUB-TICKS (#53 fix): the full entry/learning cycle
                # runs every SCALP_CYCLE_SECONDS, but OPEN POSITIONS are managed much
                # more often so a peak->reversal between full cycles is caught. This
                # is the structural fix for the intra-cycle exit leak: the ratchet /
                # reversal / trail now get a look every SCALP_MANAGE_SECONDS.
                self._fast_manage_until(time.time() + config.SCALP_CYCLE_SECONDS)
        finally:
            self.running = False

    def _fast_manage_until(self, deadline: float):
        """Between full cycles, run manage-open-positions + reconcile on a fast tick
        so intra-cycle peaks are protected (does NOT evaluate new entries or learning)."""
        every = max(1, config.SCALP_MANAGE_SECONDS)
        while self.running and time.time() < deadline:
            time.sleep(min(every, max(0.0, deadline - time.time())))
            if not (self.open_positions):
                continue
            try:
                self._reconcile_closed()
                self._manage_open_positions()
            except Exception as e:
                logger.debug(f"fast-manage tick error: {e}")

    def _apply_control(self):
        """
        Apply a pending dashboard control request from data/control.json (#19):
        set trading mode live (config + every adapter), pause/resume new entries,
        toggle scalping, or change the disabled-symbol set. Idempotent via the
        request timestamp so we only act on a NEW request.
        """
        path = os.path.join(config.DATA_DIR, "control.json")
        try:
            if not os.path.exists(path):
                return
            with open(path) as f:
                req = json.load(f)
        except Exception:
            return
        ts = req.get("requested_at")
        if ts is None or ts == getattr(self, "_last_control_ts", None):
            return
        self._last_control_ts = ts
        m = req.get("mode")
        if m and m != config.TRADING_MODE:
            config.TRADING_MODE = m
            for ad in self.adapters.values():
                try:
                    ad.mode = m
                except Exception:
                    pass
            logger.warning(f"[CONTROL] trading mode -> {m} (from dashboard)")
        if "paused" in req:
            self._paused = bool(req["paused"])
            logger.warning(f"[CONTROL] new entries {'PAUSED' if self._paused else 'RESUMED'} (dashboard)")
        if "scalping" in req:
            self._scalping_enabled = bool(req["scalping"])
            logger.warning(f"[CONTROL] scalping {'ON' if self._scalping_enabled else 'OFF'} (dashboard)")
        if isinstance(req.get("disabled_symbols"), list):
            config.DISABLED_SYMBOLS = [s.upper() for s in req["disabled_symbols"]]
            logger.warning(f"[CONTROL] disabled symbols -> {config.DISABLED_SYMBOLS} (dashboard)")

    def _run_cycle(self):
        # 0) apply any pending dashboard control request (#19)
        self._apply_control()
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
        #    GATED by LEARNING_ADAPTATION_ENABLED (#27): when adaptation is frozen
        #    we still MEASURE performance (read caches) but do NOT mutate weights.
        if self.cycle % 5 == 1:
            if config.LEARNING_ADAPTATION_ENABLED:
                try:
                    perf = self.experience_db.get_strategy_performance()
                    if perf:
                        self.registry.update_weights_from_performance(perf)
                    import datetime as _dt
                    self._last_weight_refresh = _dt.datetime.now().strftime("%H:%M:%S")
                except Exception as e:
                    logger.warning(f"strategy weight update failed: {e}")
                    self._last_learning_error = f"weight update: {str(e)[:80]}"
            try:
                self._variant_perf_cache = self.experience_db.get_variant_performance()
            except Exception as e:
                logger.warning(f"variant perf refresh failed: {e}")
                self._last_learning_error = f"variant refresh: {str(e)[:80]}"

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
            # GATED (#27): when adaptation is frozen, do NOT reclassify giveback
            # per symbol (this was part of the doom loop that cut winners).
            if config.LEARNING_ADAPTATION_ENABLED:
                try:
                    self._refresh_personalities()
                except Exception as e:
                    logger.debug(f"personality refresh skip: {e}")
            # learn per-direction win rate (directional-balance guard, #3)
            try:
                self._refresh_directional_winrate()
            except Exception as e:
                logger.debug(f"directional winrate refresh skip: {e}")
            # ReAct revert+learn (#27/#25): checkpoint best config / revert on
            # degradation / remember failed directions. Runs even when adaptation
            # is frozen (it's the safety mechanism that MAKES learning safe).
            if config.LEARNING_AUTO_REVERT_ENABLED:
                try:
                    self._run_checkpointer()
                except Exception as e:
                    logger.debug(f"checkpointer run skip: {e}")
            # #41: CONTINUOUSLY re-calibrate + ACTION per-symbol exits (excursion +
            # pattern lock) on a moderate cadence — not once/day. Outcomes are
            # applied LIVE immediately; the checkpointer verifies + reverts. This is
            # what makes the learning ACT, not sit in the KnowledgeStore.
            if self.researcher is not None and self.cycle % config.EXIT_CALIBRATION_CYCLES == 7:
                for _b in self.adapters:
                    if not self.sessions.is_open(_b):
                        continue  # need live movement; skip closed markets
                    try:
                        self.researcher.measure_excursion(_b, self.adapters[_b].resolved_symbol)
                        self.researcher.lock_in_pattern(_b, self.adapters[_b].resolved_symbol)
                    except Exception as e:
                        logger.debug(f"exit calibration skip {_b}: {e}")
            # #44/#46: resolve pending whale-signal outcomes against realised candles
            # (labels the bot's own whale dataset as the window elapses).
            if self.whale_outcomes is not None and self.cycle % config.EXIT_CALIBRATION_CYCLES == 11:
                try:
                    from src.mt5.data import get_rates as _gr
                    self.whale_outcomes.resolve_pending(_gr, "BTCUSD")
                except Exception as e:
                    logger.debug(f"whale outcome resolve skip: {e}")
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
            # #24: re-evaluate per-symbol graduation state (edge -> size-up gate)
            if self.graduation is not None:
                for _b in self.adapters:
                    try:
                        self.graduation.evaluate(_b)
                    except Exception as e:
                        logger.debug(f"graduation eval skip {_b}: {e}")

        # 2c) Adaptive intelligence: reflect -> synthesize -> backtest -> promote.
        #     Runs in a BACKGROUND thread (LLM + backtest are slow) so it never
        #     blocks live trading. Cadence: periodically, once a sample exists.
        #     GATED by LEARNING_ADAPTATION_ENABLED (#27): frozen -> no self-tuning.
        if (config.LEARNING_ADAPTATION_ENABLED
                and self.adaptive is not None and not self._adaptive_running
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

        GATED (#27): when adaptation is frozen, return UNIFORM weights so variant
        selection is pure exploration and is not biased by the net-negative
        historical variant performance.
        """
        from src.trading.trade_manager import VARIANTS
        weights = {v: 1.0 for v in VARIANTS}  # exploration floor
        if not config.LEARNING_ADAPTATION_ENABLED:
            return weights
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
        # SAFETY (per review): a symbol in TRAINING mode trades with a LOOSENED entry
        # bar, so it must NEVER size up — that would be loosened entries at full risk,
        # the opposite of the design. Require the per-symbol OperatingMode == LIVE.
        if self.mode_mgr is not None:
            try:
                mp = self.mode_mgr.params_for(adapter.resolved_symbol)
                from src.learning.operating_mode import LIVE as _LIVE_MODE
                if getattr(mp, "mode", None) != _LIVE_MODE:
                    return base_lot
            except Exception:
                return base_lot
        # #24: per-symbol graduation gate — only size UP a symbol that has proven
        # its OWN realised edge (not just the pooled phase). Non-graduated symbols
        # stay on the fixed micro lot even in global Phase 2.
        if self.graduation is not None:
            try:
                if not self.graduation.is_graduated(adapter.base_symbol):
                    return base_lot
            except Exception:
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
        Consult the SymbolGovernor (learning-loop component, unit-tested) to decide
        if this symbol should be paused/failed. Judged on RECENT trades + per-
        strategy breakdown; healthy symbols (WR>=45%) are never blocked so we
        never freeze all trading. The governor persists a FAILURE REPORT on pause.

        TRAINING/DEMO: when GOVERNOR_PAUSE_BLOCKS_ENTRIES is false, the pause is
        ADVISORY ONLY — the governor still evaluates + records reports (visible in
        status/dashboard) but does NOT hard-block new entries, so the bot keeps
        trading + learning (and can validate a new strategy) on demo. On a live
        account set it true to let the governor freeze bleeders.
        """
        if self.governor is None:
            return False
        # NOTE: we still run the governor evaluation below (it records failure
        # reports + snapshot for the dashboard). Whether a paused decision actually
        # BLOCKS entries is gated at the end by GOVERNOR_PAUSE_BLOCKS_ENTRIES.
        try:
            import sqlite3
            from src.learning.symbol_governor import SymbolStats
            conn = sqlite3.connect(self.experience_db.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT outcome, profit_loss, strategy_used FROM trades "
                "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
                "ORDER BY id DESC LIMIT ?",
                (base_symbol.upper() + "%", config.SYMBOL_PAUSE_WINDOW),
            ).fetchall()
            conn.close()
        except Exception:
            return False

        n = len(rows)
        wins = sum(1 for r in rows if r["outcome"] == "win")
        pnl = sum((r["profit_loss"] or 0) for r in rows)
        per_strat = {}
        for r in rows:
            k = r["strategy_used"] or "unknown"
            d = per_strat.setdefault(k, {"n": 0, "wins": 0, "pnl": 0.0})
            d["n"] += 1
            d["wins"] += 1 if r["outcome"] == "win" else 0
            d["pnl"] = round(d["pnl"] + (r["profit_loss"] or 0), 2)
        stats = SymbolStats(symbol=base_symbol, n=n,
                            win_rate=(wins / n * 100) if n else 0.0,
                            pnl=pnl, per_strategy=per_strat)
        decision = self.governor.evaluate(stats)
        paused = decision.status in ("paused", "failed")
        # #24 safety: a governor pause can only LOWER graduation (never raise).
        if paused and self.graduation is not None:
            try:
                self.graduation.force_probation(base_symbol, reason="governor pause")
            except Exception:
                pass
        # TRAINING/DEMO: advisory only — do not block entries unless explicitly enabled.
        if paused and not config.GOVERNOR_PAUSE_BLOCKS_ENTRIES:
            return False
        return paused

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
        base_p = {}
        for sym, p in stats.items():
            if sym.upper().startswith(base_symbol.upper()):
                base_p = dict(p)
                break
        # A revert (#27) pins giveback to the best-known value; it overrides any
        # learned personality giveback so the profitable config is what runs.
        ov = getattr(self, "_giveback_override", {}).get(base_symbol.upper())
        if ov is not None:
            base_p["giveback_frac"] = ov
        return base_p

    def _directional_winrate(self, base_symbol: str) -> dict:
        """
        Recent realised win rate per direction for a symbol, e.g.
        {'buy': {'n': 40, 'wr': 33.0}, 'sell': {'n': 12, 'wr': 43.0}}.
        Cached; refreshed with the profitability cache. Used by the directional-
        balance guard (#3) to trim the side that is empirically losing.
        """
        return (getattr(self, "_dir_winrate_cache", {}) or {}).get(base_symbol.upper(), {})

    def _directional_penalty(self, base_symbol: str, action: str) -> float:
        """
        Confidence penalty for the PROPOSED direction when it is empirically the
        weaker side for this symbol. Symmetric: penalises long OR short skew.
        Returns 0.0 until both directions have a real sample.
        """
        if not config.DIRECTIONAL_BALANCE_ENABLED:
            return 0.0
        dw = self._directional_winrate(base_symbol)
        this = dw.get(action)
        other = dw.get("sell" if action == "buy" else "buy")
        if not this or not other:
            return 0.0
        min_n = config.DIRECTIONAL_BALANCE_MIN_SAMPLE
        if this.get("n", 0) < min_n or other.get("n", 0) < min_n:
            return 0.0
        # only penalise the proposed side if it is clearly worse than the other
        if this["wr"] + 8.0 < other["wr"]:
            return config.DIRECTIONAL_BALANCE_PENALTY
        return 0.0

    def _refresh_directional_winrate(self):
        """Compute recent per-direction win rate per symbol (called on a cadence)."""
        import sqlite3
        try:
            conn = sqlite3.connect(self.experience_db.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT symbol, action, outcome FROM trades "
                "WHERE outcome IN ('win','loss') ORDER BY id DESC LIMIT 400"
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.debug(f"directional winrate refresh skip: {e}")
            return
        from collections import defaultdict
        agg = defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0}))
        for r in rows:
            base = None
            for b in self.adapters:
                if (r["symbol"] or "").upper().startswith(b.upper()):
                    base = b.upper()
                    break
            if not base or r["action"] not in ("buy", "sell"):
                continue
            d = agg[base][r["action"]]
            d["n"] += 1
            d["w"] += 1 if r["outcome"] == "win" else 0
        out = {}
        for base, dirs in agg.items():
            out[base] = {
                a: {"n": v["n"], "wr": round(v["w"] / v["n"] * 100, 1) if v["n"] else 0.0}
                for a, v in dirs.items()
            }
        if out:
            self._dir_winrate_cache = out

    def _live_indicators(self, base_symbol: str, adapter) -> dict:
        """
        Lightweight recent-bar indicators for a symbol (bulls/bears/osma etc.),
        used by the momentum-exhaustion exit (#29). Cached per cycle so managing
        several positions doesn't recompute. Returns {} on any failure.
        """
        cache = getattr(self, "_live_ind_cache", None)
        if cache is None:
            cache = {}
            self._live_ind_cache = cache
        ck = (base_symbol, self.cycle)
        if ck in cache:
            return cache[ck]
        result = {}
        try:
            resolved = adapter.resolved_symbol
            rates = get_rates(resolved, timeframe=config.ENTRY_TIMEFRAME, count=60)
            if rates and len(rates) >= 30:
                ind = compute_full_indicators(rates, self._tuned_params(resolved))
                if ind:
                    result = ind
        except Exception as e:
            logger.debug(f"live indicators skip {base_symbol}: {e}")
        cache.clear()  # keep only current cycle
        cache[ck] = result
        return result

    def _weak_poc_target(self, pos, live: dict) -> float:
        """
        #29 Playbook-A: pick a Point-of-Control / balance-area target for a WEAK
        (counter-trend) trade = the nearest structural level in the trade's favour,
        so we exit into the prior balance area before the macro trend resumes.
        Uses support/resistance from the live indicators; falls back to ~1.2x ATR.
        Returns 0.0 if unavailable.
        """
        if not live:
            return 0.0
        entry = getattr(pos, "entry", None) or getattr(pos, "entry_price", None)
        atr = live.get("atr") or 0
        if not entry:
            return 0.0
        res = live.get("resistance_levels") or []
        sup = live.get("support_levels") or []
        if pos.action == "buy":
            above = sorted([r for r in res if r > entry])
            if above:
                return float(above[0])
            return float(entry + 1.2 * atr) if atr else 0.0
        else:
            below = sorted([s for s in sup if s < entry], reverse=True)
            if below:
                return float(below[0])
            return float(entry - 1.2 * atr) if atr else 0.0

    def _whale_predict_for_btc(self) -> dict:
        """
        Hybrid layer (#26/#29): current whale confidence-to-enter from the live
        CryptoRTI signal via the wave predictor. {} when no active signal. Cached
        per cycle, non-fatal.
        """
        if getattr(self, "_whale_pred_cycle", None) == self.cycle:
            return getattr(self, "_whale_pred_cache", {}) or {}
        result = {}
        try:
            from src.cryptorti import signal_client
            from src.cryptorti.wave_predictor import WhaleWavePredictor
            bias = signal_client.current_short_bias()
            if bias:
                if not hasattr(self, "_wave_predictor"):
                    self._wave_predictor = WhaleWavePredictor()
                result = self._wave_predictor.predict(
                    usd=float(bias.get("amount_usd", 0) or 0),
                    exchange=str(bias.get("exchange", "") or ""),
                    direction="sell" if bias.get("action") == "sell" else "buy",
                    stage=bias.get("stage") or bias.get("status")) or {}
        except Exception as e:
            logger.debug(f"whale predict skip: {e}")
        self._whale_pred_cycle = self.cycle
        self._whale_pred_cache = result
        return result

    def _current_symbol_config(self, base_symbol: str) -> dict:
        """The tunable config that affects this symbol's live behaviour: the
        optimizer's tuned indicator/exit params + the effective giveback."""
        resolved = self.adapters[base_symbol].resolved_symbol if base_symbol in self.adapters else base_symbol
        params = self._tuned_params(resolved)
        cfg = dict(params) if params else {}
        cfg["giveback"] = self._giveback_override.get(base_symbol.upper(),
                                                       config.SCALP_GIVEBACK_FRAC)
        return cfg

    def _recent_expectancy(self, base_symbol: str, limit: int = 30) -> tuple:
        """(expectancy_per_trade, n) over this symbol's most recent closed trades."""
        import sqlite3
        try:
            conn = sqlite3.connect(self.experience_db.db_path)
            conn.row_factory = sqlite3.Row
            ac, ap = self.experience_db._account_clause()
            rows = conn.execute(
                "SELECT profit_loss FROM trades WHERE symbol LIKE ? "
                "AND outcome IN ('win','loss','breakeven') "
                "AND (exit_reason IS NULL OR exit_reason<>'pre_rebuild_synthetic') "
                "AND (data_source IS NULL OR data_source<>'SIMULATED_OHLC')"
                + ac +
                " ORDER BY id DESC LIMIT ?",
                tuple([base_symbol.upper() + "%"] + ap + [limit]),
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.debug(f"recent expectancy skip {base_symbol}: {e}")
            return 0.0, 0
        n = len(rows)
        if n == 0:
            return 0.0, 0
        return round(sum((r[0] or 0) for r in rows) / n, 4), n

    def _run_checkpointer(self):
        """
        ReAct revert+learn (#27/#25): for each active symbol, checkpoint the
        best-known config by REALISED expectancy and REVERT when the current
        config has degraded, recording the failed direction so it isn't repeated.
        """
        if self.checkpointer is None:
            return
        for base in self.adapters:
            try:
                exp, n = self._recent_expectancy(base)
                if n < self.checkpointer.min_sample:
                    continue
                cfg = self._current_symbol_config(base)
                decision = self.checkpointer.evaluate(base, cfg, exp, n)
                if decision.get("action") == "revert":
                    self._apply_reverted_config(base, decision.get("best_config") or {})
            except Exception as e:
                logger.debug(f"checkpointer skip {base}: {e}")

    def _apply_exit_config(self, base_symbol: str, sl_atr: float, tp_rr: float, source: str = "pattern"):
        """#40/#41: lock a discovered exit config into the LIVE per-symbol override
        (entry sizing reads _exit_override). Sources: 'pattern' (MACD-leads-OsMA
        backtest) and 'excursion' (OsMA-cycle movement). When both exist we BLEND
        (average) so the exit reflects both the backtested edge and the symbol's
        real movement. The #27 checkpointer verifies realised expectancy + reverts."""
        ov = self._exit_override.setdefault(base_symbol.upper(), {})
        srcs = ov.setdefault("_by_source", {})
        srcs[source] = {"sl_atr": round(float(sl_atr), 2), "tp_rr": round(float(tp_rr), 2)}
        # blend across available sources (mean) -> the effective live exit config
        sls = [v["sl_atr"] for v in srcs.values()]
        rrs = [v["tp_rr"] for v in srcs.values()]
        ov["sl_atr"] = round(sum(sls) / len(sls), 2)
        ov["tp_rr"] = round(sum(rrs) / len(rrs), 2)
        logger.warning(f"[EXIT-LOCK] {base_symbol}: {source} sl_atr {sl_atr} tp_rr {tp_rr} "
                       f"-> blended live sl_atr {ov['sl_atr']} tp_rr {ov['tp_rr']} "
                       f"(let winners run / cut losers early)")
        if self.learning_log is not None:
            try:
                exp, n = self._recent_expectancy(base_symbol)
                self.learning_log.exit_lock(base_symbol, ov["sl_atr"], ov["tp_rr"], source,
                                            metric=f"recent expectancy {exp} (n={n})")
            except Exception:
                pass

    def _apply_reverted_config(self, base_symbol: str, best_cfg: dict):
        """Restore a best-known config live: tuned params -> optimizer, giveback -> override."""
        if not best_cfg:
            return
        resolved = self.adapters[base_symbol].resolved_symbol if base_symbol in self.adapters else base_symbol
        if self.param_optimizer is not None:
            try:
                param_keys = {k: v for k, v in best_cfg.items() if k != "giveback"}
                if param_keys:
                    key = resolved.upper()
                    entry = self.param_optimizer.tuned.get(key, {})
                    entry["params"] = {**entry.get("params", {}), **param_keys}
                    entry["reverted_at"] = datetime.now(timezone.utc).isoformat()
                    self.param_optimizer.tuned[key] = entry
                    self.param_optimizer._persist()
            except Exception as e:
                logger.debug(f"revert params apply skip {base_symbol}: {e}")
        if "giveback" in best_cfg:
            self._giveback_override[base_symbol.upper()] = float(best_cfg["giveback"])
        # #24 safety: a config revert means the graduated config was abandoned ->
        # drop the symbol to at least PROBATION (only lowers).
        if self.graduation is not None:
            try:
                self.graduation.force_probation(base_symbol, reason="config revert")
            except Exception:
                pass
        logger.warning(f"[REVERT-APPLIED] {base_symbol}: restored best-known config "
                       f"{best_cfg} (live). Future trades use this until it is beaten.")
        if self.learning_log is not None:
            try:
                self.learning_log.revert(base_symbol, why="live expectancy degraded vs best-known",
                                         metric=f"restored sl_atr {best_cfg.get('sl_atr')} tp_rr {best_cfg.get('tp_rr')}")
            except Exception:
                pass

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
            # NOTE: avg_win <= avg_loss is often a SYMPTOM of cutting winners too
            # early, not evidence that fast scalping works. So we no longer drop
            # giveback to a tiny value on that condition (that created a doom loop
            # where over-cutting -> small wins -> even more cutting). Floors keep
            # the bias toward letting winners run.
            if avg_win > avg_loss * 1.3 and wr >= 0.4:
                out[sym] = {"style": "trend_rider", "giveback_frac": 0.75}
            elif wr >= 0.55 and avg_win <= avg_loss:
                out[sym] = {"style": "aggressive_scalper", "giveback_frac": 0.55}
            else:
                out[sym] = {"style": "neutral", "giveback_frac": 0.6}
        if out:
            self._symbol_personality_cache = out
            logger.info(f"Symbol personalities: { {k: v['style'] for k, v in out.items()} }")

    def _same_level_open(self, base_symbol: str, action: str, price: float, atr: float) -> bool:
        """
        #20: True if we already hold a position on this symbol in the SAME
        direction within a small ATR-relative distance of `price` — i.e. this
        would be a redundant same-level re-entry (e.g. GER40 6x at one price).
        ATR-relative so it's symbol-agnostic; falls back to a 0.1% band.
        """
        if not price:
            return False
        try:
            gap = getattr(config, "REENTRY_MIN_ATR_GAP", 0.75)
            band = (atr * gap) if atr else (price * 0.001)
        except Exception:
            band = price * 0.001
        for pos in self.open_positions.values():
            if pos.base_symbol != base_symbol or pos.action != action:
                continue
            entry = getattr(pos, "entry", None) or getattr(pos, "entry_price", None)
            if entry and abs(price - entry) <= band:
                return True
        return False

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
                # reversal-signature: remember the entry indicator snapshot so the
                # manager/analyzer can compare entry -> peak -> rollover live.
                try:
                    st.entry_indicators = {k: pos.indicators.get(k) for k in
                                           ("macd_line", "macd_histogram", "osma", "bulls_power",
                                            "bears_power", "rsi", "atr")} if pos.indicators else {}
                except Exception:
                    st.entry_indicators = {}
                # #29 Playbook-A: a COUNTER-TREND (not HTF-aligned) trade is "weak"
                # -> target the nearest balance-area POC and disable trailing. Use
                # the recent support/resistance as a POC proxy from live indicators.
                if not trend_aligned:
                    try:
                        live = self._live_indicators(pos.base_symbol, adapter)
                        poc = self._weak_poc_target(pos, live)
                        if poc:
                            st.weak_trade = True
                            st.poc_target = poc
                            logger.info(f"{pos.base_symbol} #{ticket}: WEAK (counter-trend) "
                                        f"-> Playbook-A POC target {poc:.5f}, trailing off")
                    except Exception as e:
                        logger.debug(f"weak-poc set skip {ticket}: {e}")
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
            # intra-cycle peak fix: the 15s loop is blind to spikes BETWEEN polls, so
            # MFE/ratchet would understate the true peak. Pull the real favourable
            # extreme (tick high/low since last check) so peak tracking sees it.
            extreme_price = self._favourable_extreme_since(pos, adapter, st) or price

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
                        if res.ok and not res.simulated:
                            logger.info(f"Pre-close CLOSED {ticket}: {pc['close']} ({res.reason})")
                            self._retire_managed(ticket)
                        elif res.simulated or adapter.mode in ("OBSERVE", "PAPER"):
                            logger.warning(
                                f"Pre-close wanted to close {ticket} ({pc['close']}) but "
                                f"mode={adapter.mode} — SIMULATED, no real order. Trade left running."
                            )
                        else:
                            logger.warning(f"Pre-close close of {ticket} FAILED ({res.reason}); "
                                           f"keeping tracked")
                    continue  # pre-close decision takes precedence this cycle

            # ── HTF-aware wick survival vs reversal (the trader's key ask) ──
            # If the trade is in adverse territory, ask the HTF context whether
            # this is a BLIP (higher TFs still align -> give room by widening the
            # stop so we don't get wicked out) or a genuine REVERSAL (HTF momentum
            # flipped against us -> cut now). Applies to gold and all symbols.
            if self.htf is not None and adapter.spec.point:
                if pos.action == "buy":
                    adverse_pts = (pos.entry_price - price) / adapter.spec.point
                else:
                    adverse_pts = (price - pos.entry_price) / adapter.spec.point
                # only intervene once meaningfully offside (beyond spread noise)
                if adverse_pts > max(spread_pts * 1.5, st.atr_points * 0.4):
                    try:
                        verdict = self.htf.blip_or_reversal(pos.symbol, pos.action)
                    except Exception:
                        verdict = "neutral"
                    if verdict == "reversal":
                        res = adapter.close(ticket)
                        if res.ok and not res.simulated:
                            logger.info(f"HTF REVERSAL exit {ticket} ({pos.base_symbol}): "
                                        f"HTF momentum flipped against {pos.action} ({res.reason})")
                            self._retire_managed(ticket)
                            continue
                        elif res.simulated or adapter.mode in ("OBSERVE", "PAPER"):
                            logger.warning(
                                f"HTF REVERSAL wanted to exit {ticket} but mode={adapter.mode} "
                                f"— SIMULATED, no real order. Trade left running."
                            )
                            continue
                        else:
                            logger.warning(f"HTF REVERSAL close of {ticket} FAILED ({res.reason}); "
                                           f"keeping tracked")
                            continue
                    if verdict == "blip" and not getattr(st, "htf_widened", False):
                        # widen the broker stop to survive the wick, ONCE, capped
                        widen = max(st.atr_points * config.HTF_WICK_WIDEN_ATR, spread_pts * 3) * adapter.spec.point
                        new_sl = (pos.entry_price - widen) if pos.action == "buy" else (pos.entry_price + widen)
                        r = adapter.modify_sl(ticket, round(new_sl, adapter.spec.digits))
                        if r.ok:
                            st.htf_widened = True
                            logger.info(f"HTF BLIP: widened SL on {ticket} ({pos.base_symbol}) "
                                        f"to survive wick (HTF still aligned)")
                        continue

            intent = self.trade_manager.evaluate(st, price, adapter.spec.point, spread_pts,
                                                 indicators=self._live_indicators(pos.base_symbol, adapter),
                                                 reversal_signature=self._reversal_signatures.get(pos.base_symbol),
                                                 extreme_price=extreme_price)
            # ── #29 proven GoldShark exits, layered over the giveback/trail logic ──
            if intent is None:
                # 1) WEAK counter-trend trade -> Playbook-A POC target (no trail)
                intent = self.trade_manager.weak_trade_poc_exit(st, price, adapter.spec.point)
            if intent is None:
                # 2) momentum-exhaustion exit (peak-tracking Bulls/Bears + OsMA)
                try:
                    live = self._live_indicators(pos.base_symbol, adapter)
                    if live:
                        intent = self.trade_manager.momentum_exhaustion_exit(
                            st, price, adapter.spec.point,
                            bulls=live.get("bulls_power", 0.0),
                            bears=live.get("bears_power", 0.0),
                            osma=live.get("osma", 0.0),
                        )
                except Exception as e:
                    logger.debug(f"exhaustion exit skip {ticket}: {e}")
            if intent:
                if "modify_sl" in intent:
                    _mres = adapter.modify_sl(ticket, intent["modify_sl"])
                    if not _mres.ok:
                        logger.warning(f"SL modify REJECTED {ticket} -> {intent['modify_sl']}: "
                                       f"{_mres.reason} (retcode={getattr(_mres,'retcode',None)})")
                        # If this was a PROFIT-PROTECTING ratchet stop we could not place,
                        # protect the gain by closing outright rather than leaving it exposed.
                        if st.peak_profit_points >= max(self.trade_manager.retain_arm_points(st),
                                                        st.atr_points or 0):
                            _cres = adapter.close(ticket)
                            if _cres.ok and not _cres.simulated:
                                logger.info(f"Ratchet fallback CLOSE {ticket}: SL unplaceable, "
                                            f"protecting {st.peak_profit_points:.0f}pt peak")
                                self._retire_managed(ticket)
                                continue
                    elif not _mres.simulated:
                        logger.info(f"SL moved {ticket} -> {intent['modify_sl']} "
                                    f"({intent.get('_tag','trail/ratchet')})")
                elif "close" in intent:
                    res = adapter.close(ticket)
                    if res.ok and not res.simulated:
                        logger.info(f"Manager CLOSED {ticket}: {intent['close']} ({res.reason})")
                        # real close confirmed — stop managing; reconcile will
                        # record the true outcome from the deal history.
                        self._retire_managed(ticket)
                    elif res.simulated or self.adapters[pos.base_symbol].mode in ("OBSERVE", "PAPER"):
                        logger.warning(
                            f"Manager wanted to close {ticket} ({intent['close']}) but "
                            f"mode={adapter.mode} — SIMULATED, no real order sent. "
                            f"Trade left running. Restart in LIVE_MICRO to close for real."
                        )
                    else:
                        logger.warning(f"Manager close of {ticket} FAILED ({res.reason}); "
                                       f"keeping trade tracked, will retry next cycle")
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
            if res.ok and not res.simulated:
                logger.info(f"[HYBRID_LLM] #{st.ticket}: LLM EXIT ({res.reason})")
                self.managed.pop(st.ticket, None)
            elif res.simulated or adapter.mode in ("OBSERVE", "PAPER"):
                logger.warning(f"[HYBRID_LLM] #{st.ticket}: LLM EXIT wanted but mode="
                               f"{adapter.mode} — SIMULATED, no real order")
            else:
                logger.warning(f"[HYBRID_LLM] #{st.ticket}: LLM EXIT close FAILED ({res.reason})")
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

    def _resolve_and_set_account(self):
        """#21: read the connected MT5 account identity, set it on the experience
        DB (so writes/stats scope to it), and log demo/live + account switches."""
        login = server = None
        trade_mode = "UNKNOWN"
        try:
            if mt5 is not None:
                ai = mt5.account_info()
                if ai:
                    login = getattr(ai, "login", None)
                    server = getattr(ai, "server", None)
                    tm = getattr(ai, "trade_mode", None)
                    trade_mode = {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(tm, "UNKNOWN")
        except Exception as e:
            logger.debug(f"mt5 account_info skip: {e}")
        if login is None:
            a = self._safe_account()
            login = a.get("login"); server = a.get("server")
        prev = getattr(self, "_active_account", None)
        acct = {"login": login, "server": server, "trade_mode": trade_mode}
        self._active_account = acct
        try:
            self.experience_db.set_current_account(login=login, server=server, trade_mode=trade_mode)
        except Exception as e:
            logger.debug(f"set_current_account skip: {e}")
        if prev and (prev.get("login") != login or prev.get("server") != server
                     or prev.get("trade_mode") != trade_mode):
            logger.warning(f"*** ACCOUNT SWITCH detected: {prev} -> {acct}. Starting a fresh "
                           f"account-scoped track; histories are NOT blended. ***")
            if prev.get("trade_mode") != "REAL" and trade_mode == "REAL":
                logger.warning("*** DEMO->LIVE switch: prior demo edge is NOT live-proven. "
                               "Live account starts with zero proven edge. ***")
            # flush account-bound caches so old-account learning doesn't leak
            for attr in ("_symbol_profit_cache", "_variant_perf_cache", "_dir_winrate_cache",
                         "_symbol_personality_cache", "_edge_cache"):
                if hasattr(self, attr):
                    setattr(self, attr, {} if "cache" in attr else None)
            self._giveback_override = {}
        logger.info(f"[ACCOUNT] connected {trade_mode} login={login} server={server}")

    def _learning_health(self) -> dict:
        """
        Observability (per external review): make learning VISIBLE so stalls are
        obvious. Reports pending count, RAG hit rate, last weight refresh, last
        learning error, and per-symbol RECENT expectancy (not all-time).
        """
        import sqlite3
        health = {
            "pending_trades": None,
            "rag_lookups": self._rag_lookups,
            "rag_hits": self._rag_hits,
            "rag_hit_rate": round(self._rag_hits / self._rag_lookups * 100, 1) if self._rag_lookups else 0.0,
            "last_weight_refresh": self._last_weight_refresh,
            "last_learning_error": self._last_learning_error,
            "adaptive_running": self._adaptive_running,
            "adaptation_enabled": config.LEARNING_ADAPTATION_ENABLED,
            "auto_revert_enabled": config.LEARNING_AUTO_REVERT_ENABLED,
            "knowledge_entries": (self.knowledge_store.count() if self.knowledge_store else 0),
            "exit_capture": (self.experience_db.capture_stats() if self.experience_db else {}),
            "recent_expectancy": {},
        }
        try:
            conn = sqlite3.connect(self.experience_db.db_path); conn.row_factory = sqlite3.Row
            health["pending_trades"] = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE outcome='pending'").fetchone()[0]
            # per-symbol recent (last 20) expectancy
            for base in self.adapters:
                rows = conn.execute(
                    "SELECT profit_loss FROM trades WHERE symbol LIKE ? "
                    "AND outcome IN ('win','loss','breakeven') ORDER BY id DESC LIMIT 20",
                    (base.upper() + "%",)).fetchall()
                if len(rows) >= 5:
                    pnls = [r[0] or 0 for r in rows]
                    health["recent_expectancy"][base] = round(sum(pnls) / len(pnls), 4)
            conn.close()
        except Exception as e:
            health["error"] = str(e)[:120]
        # stalled flag: pending piling up, or a learning error recorded
        health["stalled"] = bool(
            (health["pending_trades"] or 0) > 10 or self._last_learning_error)
        return health

    def _tuned_params(self, resolved_symbol: str) -> dict:
        """Optimizer-tuned indicator params for this symbol (or {} = defaults)."""
        if self.param_optimizer is None:
            return {}
        try:
            return self.param_optimizer.current_params(resolved_symbol)
        except Exception:
            return {}

    def _maybe_run_adaptive(self):
        """Run the adaptive intelligence loop in a background thread (non-blocking)."""

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
                # DATA-DRIVEN SELF-REFLECTION -> AUTONOMOUS TUNING (closed loop):
                # 1) post-mortem each symbol's real bars -> failure modes + directives
                # 2) feed those directives into the optimizer so reflection STEERS
                #    the parameter search, then walk-forward VALIDATES before keeping.
                # This is the full reflect -> adjust -> validate -> keep cycle, automatic.
                self._postmortem_cache = {}
                per_symbol_directives = {}
                if self.post_mortem is not None:
                    # overall pass (for dashboard/knowledge base)
                    try:
                        self._postmortem_cache = self.post_mortem.analyze(limit=40)
                        if self._postmortem_cache.get("findings"):
                            logger.info(f"[POST-MORTEM] {self._postmortem_cache['findings']}")
                            # #13: persist the reflection finding so lessons survive
                            # across runs (stable key -> updates in place, no dupes).
                            if self.knowledge_store is not None:
                                try:
                                    self.knowledge_store.remember(
                                        key="postmortem_overall_findings",
                                        kind="finding", topic="reflection",
                                        source="post_mortem",
                                        text=f"Post-mortem findings: {self._postmortem_cache['findings']}")
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"post-mortem skip: {e}")
                    # per-symbol reflection -> directives that steer that symbol's tuning
                    for base, adapter in self.adapters.items():
                        sym = adapter.resolved_symbol
                        try:
                            pm = self.post_mortem.analyze(symbol=sym, limit=40)
                            if pm and pm.get("directives"):
                                per_symbol_directives[sym] = pm["directives"]
                                # CLOSE THE GIVEBACK LOOP (#18/#27): the post-mortem
                                # 'giveback' directive was previously never consumed.
                                # Apply it to this symbol's live giveback override
                                # (clamped) so "winners cut too early" actually
                                # loosens giveback, and record the lesson.
                                gb = pm["directives"].get("giveback")
                                if gb:
                                    cur = self._giveback_override.get(
                                        base.upper(), config.SCALP_GIVEBACK_FRAC)
                                    new_gb = max(0.2, min(0.9, cur + float(gb)))
                                    if abs(new_gb - cur) > 1e-6:
                                        self._giveback_override[base.upper()] = new_gb
                                        logger.info(f"[REFLECTION] {base}: giveback {cur:.2f}->{new_gb:.2f} "
                                                    f"from post-mortem directive {gb:+.2f}")
                                        if self.knowledge_store is not None:
                                            try:
                                                self.knowledge_store.remember(
                                                    key=f"giveback_adj_{base.upper()}",
                                                    kind="finding", topic=f"exit tuning {base.upper()}",
                                                    source="post_mortem",
                                                    text=(f"{base.upper()}: post-mortem found exit-timing leak; "
                                                          f"adjusted giveback fraction to {new_gb:.2f} "
                                                          f"(directive {gb:+.2f}). Findings: {pm.get('findings')}"))
                                            except Exception:
                                                pass
                        except Exception as e:
                            logger.debug(f"post-mortem {sym} skip: {e}")

                # AUTONOMOUS PARAMETER TUNING guided by reflection, gated by walk-forward.
                if self.param_optimizer is not None and config.OPTIMIZER_ENABLED:
                    for base, adapter in self.adapters.items():
                        sym = adapter.resolved_symbol
                        try:
                            r = self.param_optimizer.optimize(
                                sym, iterations=config.OPTIMIZER_ITERATIONS,
                                directives=per_symbol_directives.get(sym))
                            if r.get("improved"):
                                src = "reflection-guided" if r.get("from_reflection") else "random-search"
                                logger.info(f"[OPTIMIZER] {sym} improved ({src}): "
                                            f"min-PF {r['score']} params {r['params']}")
                        except Exception as e:
                            logger.debug(f"optimizer {sym} skip: {e}")

                # CONTINUAL RESEARCHER (#32): once-per-day ReAct pass that reviews
                # per-symbol results, queries the mql5 RAG for better techniques,
                # kicks a gate-enforced edge re-sweep, and auto-files GitHub issues
                # for development-worthy discoveries. Idempotent per UTC day.
                if self.researcher is not None:
                    try:
                        summ = self.researcher.daily_cycle(list(self.adapters.keys()))
                        if not summ.get("skipped"):
                            logger.info(f"[RESEARCHER] daily cycle: {summ.get('symbols')} "
                                        f"issues_filed={summ.get('issues_filed')}")
                    except Exception as e:
                        logger.debug(f"continual researcher skip: {e}")

                # #36 INTELLIGENT PER-SYMBOL FIXER: for each LOSING symbol, run one
                # ReAct fix step (exit-fix -> retune -> strategy-switch -> research),
                # applying the post-mortem's diagnosed fix LIVE. The #27 checkpointer
                # then verifies realised expectancy and reverts if it didn't help.
                if self.fixer is not None:
                    for _b in self.adapters:
                        try:
                            self.fixer.fix_symbol(_b)
                        except Exception as e:
                            logger.debug(f"fixer skip {_b}: {e}")

                # #42: retrain PER-SYMBOL ONNX outcome predictors on accumulated
                # trades (chronological holdout; kept only if it beats the bar +
                # incumbent — verify/revert).
                if self.onnx_predictor is not None:
                    try:
                        res = self.onnx_predictor.train_all(list(self.adapters.keys()))
                        kept = {k: v for k, v in res.items() if v.get("kept")}
                        if kept:
                            logger.info(f"[ONNX] retrained: {kept}")
                            if self.learning_log is not None:
                                for k, v in kept.items():
                                    try:
                                        self.learning_log.onnx(k, v.get("auc"), True, v.get("n", 0))
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.debug(f"onnx train skip: {e}")

                # Reversal-signature: measure whether the confluence indicators turn
                # at the MFE peak (from live-captured snapshots). Store per symbol so
                # the (gated) signal-driven exit can use it once it is proven.
                if self.reversal_analyzer is not None:
                    for _b in list(self.adapters.keys()):
                        try:
                            sig = self.reversal_analyzer.signature_from_captured(_b)
                            meta = sig.get("_meta", {}) if sig else {}
                            if meta.get("n_trades", 0) >= 20:
                                self._reversal_signatures[_b] = sig
                                logger.info(f"[REVERSAL] {_b}: capture "
                                            f"{meta.get('median_capture_ratio')} "
                                            f"({meta.get('left_on_table_pct')}% left); "
                                            f"osma retain {sig.get('osma',{}).get('median_retained_frac')} "
                                            f"(shrinks {sig.get('osma',{}).get('shrank_toward_neutral_pct')}%), "
                                            f"peak/ATR {sig.get('osma',{}).get('median_peak_over_atr')}")
                                if self.knowledge_store is not None:
                                    try:
                                        self.knowledge_store.remember(
                                            key=f"reversal_signature_{_b.upper()}", kind="finding",
                                            topic="exit_signature",
                                            text=(f"{_b} per-symbol reversal signature (n={meta.get('n_trades')}, "
                                                  f"scale-free): capture {meta.get('median_capture_ratio')}, "
                                                  f"osma median retained-at-exit {sig.get('osma',{}).get('median_retained_frac')} "
                                                  f"(shrinks toward neutral {sig.get('osma',{}).get('shrank_toward_neutral_pct')}% of trades), "
                                                  f"osma peak magnitude ~{sig.get('osma',{}).get('median_peak_over_atr')}xATR, "
                                                  f"macd_hist retained {sig.get('macd_histogram',{}).get('median_retained_frac')}."))
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.debug(f"reversal signature skip {_b}: {e}")
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
        # dashboard control: new entries paused / scalping disabled (#19)
        if getattr(self, "_paused", False) or not getattr(self, "_scalping_enabled", True):
            return
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

        # Use the optimizer's TUNED indicator params for this symbol if the
        # self-learning loop has found a validated improvement (else defaults).
        tuned = self._tuned_params(resolved)
        indicators = compute_full_indicators(rates, tuned)
        if not indicators or indicators.get("close") is None:
            return
        # tag the symbol so symbol-specific strategies (e.g. CryptoRTI/BTC) can filter
        indicators["symbol"] = resolved
        indicators["base_symbol"] = base

        # FOCUSED mode: prefer validated high-edge (strategy x regime) pockets,
        # which backtest far better than the broad ensemble (PF 1.24 vs 1.04).
        # Fall back to the weighted ensemble when there's no focused rule OR the
        # current regime doesn't match a pocket (so the symbol still trades and we
        # keep accumulating a learning sample instead of going silent).
        signal = None
        if config.FOCUSED_MODE:
            fs = self.registry.get_focused_signal(indicators)
            if fs is not None and fs.action != "hold":
                signal = fs
        if signal is None:
            signal = self.registry.get_ensemble_signal(indicators, min_agreement=2)
        if signal.action == "hold":
            return

        # ── HYBRID whale/order-flow layer (#26/#29/#43) for BTC ──
        # OsMA drives regular entries; a live CryptoRTI whale signal that AGREES
        # boosts confidence + flags a lot SCALE; if it opposes, dampen.
        # AUTHORITY IS CONSERVATIVE: the whale hybrid boost is NOT yet walk-forward
        # validated (validate_whale_backtest showed whale_active PF ~0.70 vs 0.60,
        # marginal/inconclusive on ~20d). So we keep a SMALL boost + capped scale
        # until it proves out on more data (config WHALE_BOOST_MAX / WHALE_SCALE_MAX).
        # NOTE (#43 follow-up): the live boost uses wave_predictor/signal_client;
        # the backtest validates the feature_align whale_active/VPIN column. These
        # should be reconciled so we validate exactly what we trade.
        self._whale_scale = 1.0
        if "BTC" in resolved.upper():
            try:
                wp = self._whale_predict_for_btc()
                boost_max = getattr(config, "WHALE_BOOST_MAX", 0.06)
                scale_max = getattr(config, "WHALE_SCALE_MAX", 0.5)
                if wp and wp.get("confidence", 0) >= 0.5 and wp.get("action"):
                    if wp["action"] == signal.action:
                        boost = boost_max * wp["confidence"]
                        signal.confidence = min(1.0, signal.confidence + boost)
                        # conservative lot scale (capped) until the boost validates
                        self._whale_scale = 1.0 + min(scale_max, scale_max * wp["confidence"])
                        signal.reason += f" | +whale {wp['action']} conf{wp['confidence']:.2f} (scale x{self._whale_scale:.2f})"
                        logger.info(f"BTCUSD HYBRID: OsMA {signal.action} + aligned whale "
                                    f"conf {wp['confidence']:.2f} -> +{boost:.3f}, scale x{self._whale_scale:.2f} (conservative, unvalidated)")
                    else:
                        signal.confidence = max(0.0, signal.confidence - boost_max)
                        logger.info(f"BTCUSD HYBRID: whale {wp['action']} OPPOSES OsMA "
                                    f"{signal.action} -> dampened")
            except Exception as e:
                logger.debug(f"whale hybrid skip: {e}")

        # Self-managing mode: per-symbol TRAINING (loose, gather sample) vs LIVE
        # (tight, proven-edge only). Gives the effective entry thresholds so the
        # bot regulates its own selectivity — no manual loosen/tighten needed.
        eff_conf_min = config.SCALP_CONFIDENCE_MIN
        eff_ct_penalty = config.MTF_COUNTERTREND_PENALTY
        if self.mode_mgr is not None:
            try:
                mp = self.mode_mgr.params_for(resolved)
                eff_conf_min = mp.confidence_min
                eff_ct_penalty = mp.countertrend_penalty
            except Exception as e:
                logger.debug(f"mode params skip: {e}")
        # ── RAG: adjust confidence from similar historical patterns (C2) ──
        # The vector store is now READ at entry (not just written on close): if
        # similar past setups mostly lost, confidence is cut (or the trade vetoed);
        # if they mostly won, confidence is boosted.
        rag = None
        if self.pattern_matcher is not None:
            try:
                rag = self.pattern_matcher.analyze_current_market(indicators)
                n_similar = rag.get("similar_patterns_found", 0)
                self._rag_lookups += 1
                if n_similar > 0:
                    self._rag_hits += 1
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

        # #42: LEARNED entry confidence — the PER-SYMBOL ONNX model (chronological
        # holdout, scale-free features) predicts P(win). Given its validation is
        # inherently the softest part of the pipeline, its live authority is
        # CONSERVATIVE: a small NUDGE (not a 50/50 blend), and a veto only for
        # genuinely low P(win) AND only once the symbol's model has a real sample.
        if self.onnx_predictor is not None:
            try:
                p_win = self.onnx_predictor.predict_win_prob(indicators)
                if p_win is not None:
                    n_model = self.onnx_predictor.model_trades(indicators)
                    before = signal.confidence
                    # small nudge: +/-0.10 max, scaled by how far P(win) is from 0.5
                    nudge = max(-0.10, min(0.10, (p_win - 0.5) * 0.4))
                    signal.confidence = round(max(0.0, min(1.0, signal.confidence + nudge)), 3)
                    # veto only a genuinely bad entry, and only for a matured model
                    if p_win < 0.30 and n_model >= 120:
                        logger.info(f"{base}: ONNX veto (P(win) {p_win:.2f}, model n={n_model})")
                        return
                    if abs(signal.confidence - before) > 0.01:
                        logger.info(f"{base}: ONNX P(win) {p_win:.2f} (n={n_model}) "
                                    f"nudge {before:.2f}->{signal.confidence:.2f}")
            except Exception as e:
                logger.debug(f"onnx confidence skip: {e}")

        if signal.confidence < eff_conf_min:
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
                penalty = eff_ct_penalty * max(oppose, 1)
                before = signal.confidence
                signal.confidence = max(0.0, signal.confidence - penalty)
                logger.info(f"{base}: counter-trend {signal.action} penalised "
                            f"{before:.2f}->{signal.confidence:.2f} ({detail})")

        # ── Directional-balance guard (#3): trim the empirically weaker side ──
        # The bot showed a persistent long bias (buy ~4x sell volume, far worse
        # P&L). If this symbol's recent win rate for the PROPOSED direction is
        # clearly worse than the other side, trim confidence so weak trades on
        # the losing side fall below the entry bar. Symmetric + evidence-driven.
        dir_pen = self._directional_penalty(base, signal.action)
        if dir_pen > 0:
            before = signal.confidence
            signal.confidence = max(0.0, signal.confidence - dir_pen)
            logger.info(f"{base}: directional-balance penalty on {signal.action} "
                        f"{before:.2f}->{signal.confidence:.2f} (weaker side by win rate)")

        # HTF context (M5/M15/M30/H1) — applies to EVERY symbol incl. gold. Strong
        # multi-timeframe agreement boosts confidence; disagreement trims it. Stored
        # on the trade so management can re-check the same context later.
        htf_read = None
        if self.htf is not None:
            try:
                htf_read = self.htf.read(resolved, signal.action)
                signal.confidence = max(0.0, min(1.0, signal.confidence + 0.15 * htf_read.alignment))
                indicators["htf_alignment"] = htf_read.alignment
            except Exception as e:
                logger.debug(f"HTF read skip: {e}")

        # Final confidence gate (after MTF + HTF quality adjustment)
        if signal.confidence < eff_conf_min:
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
        # SL/TP sized to volatility (ATR). Use the OPTIMIZER-TUNED sl_atr/tp_rr
        # for this symbol if the self-learning loop found a validated set, else
        # the config defaults. This is how learned exit params reach live trades.
        _tp = self._tuned_params(resolved)
        # #29/#36 DYNAMIC FIX: the post-mortem ReAct fixer can set a LIVE per-symbol
        # sl_atr/tp_rr override that bypasses the backtest gate (the diagnosed
        # "SL too tight" fix must reach live trades, not be stuck behind WR>=50).
        # The #27 checkpointer verifies realised expectancy and reverts if worse.
        _ov = (getattr(self, "_exit_override", {}) or {}).get(base.upper(), {})
        sl_atr_mult = _ov.get("sl_atr", _tp.get("sl_atr", config.SCALP_SL_ATR_MULT))
        tp_rr = _ov.get("tp_rr", _tp.get("tp_rr", config.SCALP_TP_RR))
        atr_pts = (indicators.get("atr", 0) or 0) / pt if pt else 0
        sl_pts = max(sl_atr_mult * atr_pts, min_dist_pts) if atr_pts > 0 \
            else max(config.SCALP_SL_POINTS, min_dist_pts)
        # PAYOFF LEVER (backtest-proven): TP as a MULTIPLE of the actual SL.
        tp_pts = sl_pts * tp_rr

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

        # ── #20 same-level re-entry guard ──
        # Block a new entry at (nearly) the same price + direction as a still-open
        # position on this symbol, to stop the repeated same-level re-entries seen
        # in the journal (e.g. GER40 6x at 25706.65). Distance measured in ATR.
        if self._same_level_open(base, signal.action, signal.price,
                                 indicators.get("atr", 0)):
            logger.info(f"{base}: skip re-entry — already have a {signal.action} near "
                        f"{signal.price} (same-level guard)")
            return

        # ── Phase 3: master risk gate ──
        risk = self.risk.check_entry(spread_points=spread_pts)
        if not risk.allowed:
            if risk.halted:
                logger.warning(f"TRADING HALTED: {risk.reason}")
            else:
                logger.info(f"{base}: entry blocked by risk ({risk.reason})")
            return

        # #26 hybrid: scale the lot when an aligned whale signal boosted conviction
        # (clamped by the broker/LIVE_MICRO cap inside place()). SAFETY: only scale
        # UP a symbol that has earned it (graduated/LIVE) — a TRAINING symbol still
        # gets the whale CONFIDENCE boost (better entry) but NOT a size increase.
        _lot = self._position_lot(adapter)
        _ws = getattr(self, "_whale_scale", 1.0)
        _may_scale = True
        try:
            if self.graduation is not None and not self.graduation.is_graduated(base):
                _may_scale = False
        except Exception:
            _may_scale = False
        if _ws and _ws > 1.0 and _may_scale:
            _lot = round(_lot * _ws, 2)
        result = adapter.place(signal.action, _lot, sl=sl, tp=tp, comment=comment)

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
    def _retire_managed(self, ticket: int):
        """Manager-close path: move the ManagedState into the tombstone cache instead
        of discarding it, so _reconcile_closed can still persist MFE/MAE (Bug 2/3)."""
        st = self.managed.pop(ticket, None)
        if st is not None:
            self._closed_state_cache[ticket] = st
            # cap: reconcile normally drains this next cycle; guard against a leak if a
            # close is never reconciled (e.g. ticket vanishes from history).
            if len(self._closed_state_cache) > 256:
                for _old in list(self._closed_state_cache.keys())[:64]:
                    self._closed_state_cache.pop(_old, None)
        return st

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
            # excursion state: prefer live managed, else the tombstone cache the
            # manager-close path stashed it in (Bug 2/3 — never lose MFE/MAE).
            _mst = self.managed.pop(ticket, None) or self._closed_state_cache.pop(ticket, None)
            outcome = "win" if profit > 0 else "loss" if profit < 0 else "breakeven"
            # exit-capture study: pull MFE/MAE/exit-points from the manager's tracking
            _mfe = round(_mst.peak_profit_points, 1) if _mst else None
            _mae = round(_mst.worst_profit_points, 1) if _mst else None
            _exit_pts = None
            try:
                _adp = self.adapters.get(tp.base_symbol)
                _pt = _adp.spec.point if (_adp and _adp.spec) else None
                if _pt:
                    _exit_pts = round((exit_price - tp.entry_price) / _pt
                                      * (1 if tp.action == "buy" else -1), 1)
            except Exception as e:
                logger.debug(f"exit_points calc skip {ticket}: {e}")
                _exit_pts = None

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
                        mfe_points=_mfe, mae_points=_mae, exit_points=_exit_pts,
                    )
                    # reversal-signature: persist indicator snapshots at peak/exit
                    try:
                        if _mst is not None:
                            self.experience_db.update_trade_signature(
                                trade_id=tp.db_trade_id,
                                peak_indicators=getattr(_mst, "peak_indicators", None) or None,
                                exit_indicators=getattr(_mst, "last_indicators", None) or None)
                    except Exception as e:
                        logger.debug(f"signature persist skip: {e}")
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

    def _favourable_extreme_since(self, pos, adapter, st):
        """Return the most FAVOURABLE price seen since the last cycle (the intra-cycle
        peak the poll would otherwise miss). Buys -> highest bid; sells -> lowest ask.

        HARDENED (#53): copy_ticks_range takes SERVER time, but a naive local-epoch
        window pulled the WRONG ticks and produced phantom peaks (e.g. MFE 1795pts on
        a trade whose MAE was only -9 — physically impossible). We now (a) time the
        window in SERVER seconds via the symbol's own last tick, and (b) REJECT any
        extreme that is more than a sane bound (a few ATR) beyond the current price,
        so bad/whipsaw ticks cannot inflate MFE. Returns None -> caller uses poll price.
        """
        try:
            import MetaTrader5 as mt5
            tick = adapter.live_tick()
            if tick is None or not adapter.spec or not adapter.spec.point:
                return None
            point = adapter.spec.point
            cur = tick.bid if pos.action == "buy" else tick.ask
            # server-timed window from the live tick (avoids local/server offset bug)
            now_srv = float(tick.time)
            last = getattr(st, "_last_tick_srv", None)
            frm = last if last else now_srv - config.SCALP_CYCLE_SECONDS
            st._last_tick_srv = now_srv
            ticks = mt5.copy_ticks_range(pos.symbol, frm, now_srv + 1, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                return None
            # sane bound: a real favourable tick can't be more than a few ATR beyond
            # the CURRENT price; anything past that is a feed artifact / bad tick.
            atr_pts = st.atr_points or 0
            max_move = (atr_pts * 3.0) * point if atr_pts else None
            if pos.action == "buy":
                vals = [float(t["bid"]) for t in ticks if t["bid"] > 0
                        and (max_move is None or (t["bid"] - cur) <= max_move)]
                return max(vals) if vals else None
            else:
                vals = [float(t["ask"]) for t in ticks if t["ask"] > 0
                        and (max_move is None or (cur - t["ask"]) <= max_move)]
                return min(vals) if vals else None
        except Exception as e:
            logger.debug(f"favourable_extreme skip {pos.ticket}: {e}")
            return None

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
            # #21: enrich with the resolved account identity for the dashboard badge
            _aa = getattr(self, "_active_account", None) or {}
            if isinstance(acct, dict):
                acct = {**acct,
                        "login": acct.get("login") or _aa.get("login"),
                        "trade_mode": acct.get("trade_mode") or _aa.get("trade_mode"),
                        "is_live": (_aa.get("trade_mode") == "REAL")}
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
                "tuned_params": (self.param_optimizer.status() if self.param_optimizer else {}),
                "symbol_governance": (self.governor.snapshot() if self.governor else {}),
                "post_mortem": (getattr(self, "_postmortem_cache", {}) or {}),
                "learning_health": self._learning_health(),
                "config_checkpoints": (self.checkpointer.snapshot() if self.checkpointer else {}),
                "graduation": (self.graduation.snapshot() if self.graduation else {}),
                "dynamic_fixer": (self.fixer.snapshot() if self.fixer else {}),
                "onnx_model": (self.onnx_predictor.status() if self.onnx_predictor else {}),
                "exit_calibration": (self.researcher.excursion_snapshot() if self.researcher else {}),
                "operating_modes": (self.mode_mgr.snapshot() if self.mode_mgr else {}),
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
    # Allow the trading mode to be set as the first CLI arg, mirroring app.py:
    #     python -m src.trading.scalp_engine LIVE_MICRO
    # This MUST run before `src.config` is imported anywhere in this process,
    # otherwise config.TRADING_MODE is already frozen at its .env/default value.
    # Because this module imports `from src import config` at the top, config is
    # already loaded here; so we set the env AND reload the resolved mode.
    import sys as _sys
    _valid = ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE")
    if len(_sys.argv) > 1 and _sys.argv[1].upper() in _valid:
        os.environ["TRADING_MODE"] = _sys.argv[1].upper()
        # config was imported at module load; re-resolve the mode from the env
        # so a direct `-m` launch is not silently stuck in OBSERVE.
        config.TRADING_MODE = _sys.argv[1].upper()
    else:
        logger.warning(
            "No trading mode argument given to scalp_engine. Running in "
            f"mode={config.TRADING_MODE!r} (from .env/default). If you intend to "
            "place/close REAL demo orders, launch with: "
            "python -m src.trading.scalp_engine LIVE_MICRO"
        )
    run_scalp_engine()
