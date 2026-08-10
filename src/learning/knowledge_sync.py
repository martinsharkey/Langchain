"""
Sync durable PROJECT knowledge into the bot's own KnowledgeStore (#13).

The assistant saves durable facts/decisions/corrections to Kilo project memory
across sessions. Those same insights must ALSO live in the BOT's KnowledgeStore so
the running bot (and the continual researcher / DynamicFixer) can semantically
recall them at runtime — not just future chat sessions.

This module holds the curated, machine-relevant subset (trading edges, symbol
facts, decisions, corrections) and upserts them by stable key (idempotent — safe
to run every startup; re-running updates in place, no duplicates).

Run:  python -m src.learning.knowledge_sync
The engine also calls sync_project_knowledge() at startup.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("knowledge_sync")

# (key, kind, topic, text) — mirrors the durable Kilo project memory this session.
PROJECT_KNOWLEDGE = [
    ("edge_osma_confluence_primary", "decision", "strategy",
     "PRIMARY entry strategy = the 7-indicator OsMA confluence (MACD, OsMA, Bears Power, "
     "Bulls Power, EMA, ATR, RSI), ported from the proven GoldShark EAs (optimizer PF "
     "1.46-1.62 @ ~15% DD). Trigger: OsMA zero-cross (confirmed or anticipated) aligned "
     "with MACD; confirmed by EMA trend, ATR expansion, Bulls/Bears control, RSI. "
     "Symbol-agnostic — works on crypto too, not just gold."),
    ("edge_indicator_scale_per_symbol", "correction", "indicator scale",
     "Indicator STRENGTHS/VALUES differ by orders of magnitude across symbols (BTCUSD "
     "~63000 vs XAUUSD ~2600), so absolute OsMA/MACD/ATR/power thresholds tuned on gold "
     "are MEANINGLESS on BTC. Use ATR-relative / %-of-price / z-scored gates and "
     "calibrate thresholds per symbol from that symbol's own distribution."),
    ("edge_exit_timing_is_the_leak", "finding", "exit tuning",
     "Across symbols the dominant loss cause is EXIT TIMING, not entry: losers repeatedly "
     "run >=1.5 ATR our way after being stopped/scratched (SL too tight, winners cut "
     "early). Fix = widen SL (sl_atr), loosen giveback, let winners reach TP; the "
     "DynamicFixer applies this live and the checkpointer verifies/reverts."),
    ("edge_btcusd_247_l2", "finding", "BTCUSD",
     "BTCUSD is the only 24/7 symbol and the only one with Level-2 orderbook data (the "
     "CryptoRTI whale feed) — a unique informational edge. Hybrid design: OsMA drives "
     "regular BTC entries; a live whale signal that AGREES boosts confidence + scales the "
     "lot (when LIVE/graduated); if it opposes, dampen."),
    ("edge_whale_chunked_wave", "correction", "whale->btcusd wave",
     "A large whale movement (~$6M) is broken into ~$1M chunks that print ~6 large "
     "1-minute BTCUSD candles in a window after the event. Whale tx timestamps DO map to "
     "real 1m BTC moves. Raw deposits alone are NOT tradeable (of 455 deposits >=$1M, 0 "
     "reached selling_confirmed) — the edge is the historic-trained confidence model."),
    ("decision_feed_websocket_only", "decision", "cryptorti feed",
     "Authoritative CryptoRTI source = mTLS WebSocket, event-driven push only. Do NOT "
     "poll S3 in the hot path. Danny pushes a signal only when an event has enough data."),
    ("decision_focus_symbols", "decision", "symbol focus",
     "Focus trading on XAUUSD + GER40 + BTCUSD (best performers + the 24/7 L2 symbol). "
     "8 symbols was premature. Re-add a symbol only after it graduates (proven per-symbol "
     "edge). Size follows PROVEN per-symbol edge; TRAINING symbols stay on the micro lot."),
    ("decision_learning_safety", "decision", "learning safety",
     "Learning must be SAFE: the ConfigCheckpointer keeps each symbol's best-known config "
     "by realised expectancy and auto-reverts a change that degrades live results, "
     "recording the failed direction so it is not retried. Kill-switch "
     "LEARNING_ADAPTATION_ENABLED is the floor. Governor pause is advisory in demo."),
    ("risk_fixed_deposit_max_loss", "decision", "risk philosophy",
     "The STARTING BALANCE is the MOST that can be lost (fund e.g. £250 -> worst case is "
     "£250). So aggressiveness/lot size/compounding do NOT change downside risk: aggressive "
     "compounding to grow a small ring-fenced deposit (e.g. £250 -> £100k) is acceptable "
     "because the deposit caps the loss. Once a REAL edge is proven per symbol, compound it "
     "aggressively within the deposit; do not over-constrain size for capital preservation "
     "beyond the deposit. Still gate sizing on proven per-symbol edge (no size-up on NO edge)."),
    ("edge_macd_then_osma_sequence", "finding", "entry pattern",
     "Real BTCUSD (generalizes) entry trigger = MACD line crosses ZERO FIRST, then OsMA "
     "follows and crosses zero the SAME direction shortly after (MACD leads, OsMA confirms). "
     "Strongest when M15 and/or M5 MACD are ALIGNED with M1 MACD at the moment of the M1 OsMA "
     "cross. Backtest variations of this MACD-leads-OsMA + MTF-MACD-alignment model. When a "
     "trade fails, diagnose: real reversal vs SL too tight (stopped then recovered) vs held a "
     "winner into a loss (gave back). GoldShark optimiser shows massive growth on this."),
    ("backtest_macd_osma_exit_config", "finding", "exit config",
     "BACKTEST-PROVEN (BTCUSD, scripts/backtest_macd_osma.py): the MACD-then-OsMA pattern is "
     "profitable ONLY with a WIDE stop + TIGHT take-profit: sl_atr 1.5, tp_atr 1.0 -> 75% WR "
     "PF 1.91 (all), 77.8% WR PF 3.13 (M5-MACD-aligned). Tight-SL/wide-TP (sl 0.5-1.0, tp "
     "2.0-3.0) LOSES (PF <1) - that inverted config is what made the live bot lose. So for "
     "this pattern: sl_atr>=1.5, tp_rr<=1.0, and require M5 (ideally M15) MACD alignment. "
     "The signal was good; the exit was the leak."),
]


def sync_project_knowledge(store=None) -> int:
    """Upsert the curated project knowledge into the KnowledgeStore. Returns count."""
    if store is None:
        try:
            from src.learning.knowledge_store import KnowledgeStore
            store = KnowledgeStore()
        except Exception as e:
            logger.warning(f"KnowledgeStore unavailable for sync: {e}")
            return 0
    n = 0
    for key, kind, topic, text in PROJECT_KNOWLEDGE:
        try:
            store.remember(key=key, kind=kind, topic=topic, source="project_memory", text=text)
            n += 1
        except Exception as e:
            logger.debug(f"knowledge sync skip {key}: {e}")
    logger.info(f"synced {n} project-knowledge entries into the bot KnowledgeStore")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("synced entries:", sync_project_knowledge())
