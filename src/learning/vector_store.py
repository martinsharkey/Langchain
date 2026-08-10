"""
Vector Store for Market Pattern Storage and Retrieval (RAG).

Uses ChromaDB to store market patterns as vector embeddings, enabling
lightning-fast similarity search. Each pattern stores:
- Technical indicator snapshot (as the embedding vector)
- Market conditions at the time
- Strategy that was used
- Trade outcome (for learning)
- Timestamp and metadata

This is the core RAG component that allows the bot to:
1. Find similar historical market conditions instantly
2. Retrieve what strategies worked in similar conditions
3. Learn from past trades by associating patterns with outcomes
"""

import os
import json
import time
import math
import hashlib
import logging
from typing import Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("learning.vector_store")


# ═══════════════════════════════════════════════════════════════════════════════
#  PATTERN SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each pattern stored in the vector DB has:
#
#   id:          Unique hash based on timestamp + indicator values
#   embedding:   Float vector of normalized indicator values (20-dim)
#   metadata: {
#     timestamp:      ISO datetime when pattern was captured
#     price:          Current XAUUSD price
#     trend:          "bullish" | "bearish" | "neutral" | "crossover"
#     rsi:            RSI value
#     atr:            ATR value
#     macd_histogram: MACD histogram value
#     bb_position:    Price position within Bollinger Bands (0.0-1.0)
#     ema_fast:       Fast EMA value
#     ema_slow:       Slow EMA value
#     support_level:  Nearest support
#     resistance_level: Nearest resistance
#     strategy_used:  Name of strategy that generated signal
#     signal_action:  "buy" | "sell" | "hold"
#     signal_confidence: 0.0-1.0
#     trade_outcome:  "win" | "loss" | "pending" | "none"
#     profit_loss:    P&L in dollars if trade was taken
#     market_regime:  "trending" | "ranging" | "volatile" | "quiet"
#   }
# ═══════════════════════════════════════════════════════════════════════════════


class PatternVectorStore:
    """
    ChromaDB-backed vector store for market pattern storage and retrieval.
    
    Provides RAG (Retrieval-Augmented Generation) capabilities for the
    trading bot, allowing it to find similar historical patterns and
    learn from past outcomes.
    
    Usage:
        store = PatternVectorStore()
        
        # Store a pattern
        pattern_id = store.store_pattern(indicators, metadata)
        
        # Find similar patterns
        similar = store.find_similar(indicators, n_results=5)
        
        # Get statistics
        stats = store.get_statistics()
    """
    
    # Collection name in ChromaDB
    COLLECTION_NAME = "xauusd_market_patterns"
    
    # Path for persistent storage
    PERSIST_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "chromadb_store"
    )
    
    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            persist_directory: Override the default persistence path.
        """
        self.persist_dir = persist_directory or self.PERSIST_DIR
        os.makedirs(self.persist_dir, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        
        # Get or create the collection
        try:
            self.collection = self.client.get_collection(self.COLLECTION_NAME)
            count = self.collection.count()
            logger.info(f"Loaded existing pattern store with {count} patterns")
        except (ValueError, Exception):
            try:
                self.collection = self.client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "XAUUSD market patterns for RAG-based trading", "hnsw:space": "cosine"},
                )
                logger.info("Created new pattern store")
            except Exception:
                # If both get and create fail, delete and recreate
                try:
                    self.client.delete_collection(self.COLLECTION_NAME)
                except Exception:
                    pass
                self.collection = self.client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "XAUUSD market patterns for RAG-based trading", "hnsw:space": "cosine"},
                )
                logger.info("Recreated pattern store after conflict")
        
        self._dimension = 20  # Number of features in our embedding
    
    # ─── Embedding Generation ─────────────────────────────────
    
    def _indicators_to_vector(self, indicators: dict) -> list[float]:
        """
        Convert technical indicators into a normalized feature vector.
        
        The vector captures the market's "fingerprint" at a point in time,
        enabling similarity search across historical patterns.
        
        Features (20 dimensions):
        0:  Normalized price (0-1 within recent range)
        1:  RSI (0-100, already normalized)
        2:  ATR normalized by price
        3:  MACD histogram (tanh-normalized)
        4:  BB position (0=lower, 0.5=middle, 1=upper)
        5:  EMA fast/slow ratio (1.0 = equal)
        6:  Trend encoded: bullish=1.0, bearish=-1.0, neutral=0.0
        7:  Price distance to support (0=at support, 1=far)
        8:  Price distance to resistance (0=at resistance, 1=far)
        9:  Volume relative to average
        10: Price change over last 5 candles (normalized)
        11: Price change over last 10 candles (normalized)
        12: Volatility ratio (current ATR / 10-period ATR)
        13: Stochastic %K (0-100)
        14: Stochastic %D (0-100)
        15: ADX or trend strength (0-100)
        16: Price position relative to 50-period SMA
        17: Candle body ratio (abs(close-open)/(high-low))
        18: Upper wick ratio
        19: Lower wick ratio
        """
        close = indicators.get("close", 0) or 0
        rsi_val = indicators.get("rsi", 50) or 50
        atr_val = indicators.get("atr", 0) or 0
        macd_hist = indicators.get("macd_histogram", 0) or 0
        bb_upper = indicators.get("bb_upper", close) or close
        bb_lower = indicators.get("bb_lower", close) or close
        bb_middle = indicators.get("bb_middle", close) or close
        ema_fast = indicators.get("ema_fast", close) or close
        ema_slow = indicators.get("ema_slow", close) or close
        support = indicators.get("support_levels", [])
        resistance = indicators.get("resistance_levels", [])
        trend = indicators.get("trend", "neutral")
        
        # 0: Normalized price (0-1 within BB range)
        bb_range = bb_upper - bb_lower
        norm_price = (close - bb_lower) / bb_range if bb_range > 0 else 0.5
        
        # 1: RSI (already 0-100, divide by 100)
        rsi_norm = rsi_val / 100.0
        
        # 2: ATR normalized by price
        atr_norm = min(atr_val / max(close, 1), 0.1) * 10  # Scale to ~0-1
        
        # 3: MACD histogram (tanh normalization)
        macd_norm = max(min(macd_hist / max(abs(macd_hist) + 0.001, 0.001), 1.0), -1.0)
        macd_norm = (macd_norm + 1.0) / 2.0  # Shift to 0-1
        
        # 4: BB position
        bb_pos = norm_price  # Already 0-1
        
        # 5: EMA ratio
        ema_ratio = ema_fast / max(ema_slow, 0.001)
        ema_ratio = min(max(ema_ratio, 0.9), 1.1)  # Clamp
        ema_norm = (ema_ratio - 0.9) / 0.2  # 0-1 range
        
        # 6: Trend encoding
        trend_map = {
            "bullish": 1.0,
            "bullish_crossover": 0.75,
            "neutral": 0.5,
            "bearish_crossover": 0.25,
            "bearish": 0.0,
        }
        trend_norm = trend_map.get(trend, 0.5)
        
        # 7: Distance to support
        nearest_support = max(support) if support else close * 0.95
        dist_to_support = (close - nearest_support) / max(close, 1)
        support_norm = min(max(dist_to_support * 10, 0), 1)  # Scale
        
        # 8: Distance to resistance
        nearest_resistance = min(resistance) if resistance else close * 1.05
        dist_to_resistance = (nearest_resistance - close) / max(close, 1)
        resistance_norm = min(max(dist_to_resistance * 10, 0), 1)
        
        # 9: Volume relative to its moving average
        vol = indicators.get("volume", 0) or 0
        vol_sma = indicators.get("volume_sma", 0) or 0
        if vol_sma > 0:
            volume_norm = min(max((vol / vol_sma) / 2.0, 0.0), 1.0)  # 1.0 avg -> 0.5
        else:
            volume_norm = 0.5

        # 10-11: Price changes over last 5 / 10 candles (tanh-normalized to 0-1)
        pc5 = indicators.get("price_change_5", 0.0) or 0.0
        pc10 = indicators.get("price_change_10", 0.0) or 0.0
        price_change_5 = (math.tanh(pc5 * 50) + 1) / 2
        price_change_10 = (math.tanh(pc10 * 50) + 1) / 2

        # 12: Volatility ratio (current ATR / slow ATR), 1.0 -> 0.5
        vr = indicators.get("volatility_ratio", 1.0) or 1.0
        volatility_norm = min(max(vr / 2.0, 0.0), 1.0)

        # 13-14: Stochastic %K / %D (0-100 -> 0-1)
        stoch_k = min(max((indicators.get("stoch_k", 50.0) or 50.0) / 100.0, 0.0), 1.0)
        stoch_d = min(max((indicators.get("stoch_d", 50.0) or 50.0) / 100.0, 0.0), 1.0)

        # 15: Trend strength via ADX (0-100 -> 0-1)
        trend_strength = min(max((indicators.get("adx", 20.0) or 20.0) / 100.0, 0.0), 1.0)

        # 16: Price position relative to 50-period SMA (above=>1, below=>0)
        sma_50 = indicators.get("sma_50", close) or close
        if sma_50 > 0:
            sma_position = min(max((close / sma_50 - 0.98) / 0.04, 0.0), 1.0)  # ±2% band
        else:
            sma_position = 0.5

        # 17-19: Candle body / wick ratios (already 0-1)
        body_ratio = min(max(indicators.get("body_ratio", 0.5) or 0.5, 0.0), 1.0)
        upper_wick = min(max(indicators.get("upper_wick", 0.5) or 0.5, 0.0), 1.0)
        lower_wick = min(max(indicators.get("lower_wick", 0.5) or 0.5, 0.0), 1.0)
        
        # Build the vector
        vector = [
            norm_price,
            rsi_norm,
            atr_norm,
            macd_norm,
            bb_pos,
            ema_norm,
            trend_norm,
            support_norm,
            resistance_norm,
            volume_norm,
            price_change_5,
            price_change_10,
            volatility_norm,
            stoch_k,
            stoch_d,
            trend_strength,
            sma_position,
            body_ratio,
            upper_wick,
            lower_wick,
        ]
        
        # Ensure all values are floats
        return [float(v) for v in vector]
    
    def _generate_pattern_id(self, indicators: dict, metadata: dict) -> str:
        """Generate a unique pattern ID based on content."""
        raw = f"{metadata.get('timestamp', time.time())}_{indicators.get('close', 0)}_{indicators.get('rsi', 0)}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    
    # ─── Store Operations ─────────────────────────────────────
    
    def store_pattern(
        self,
        indicators: dict,
        metadata: dict,
    ) -> str:
        """
        Store a market pattern in the vector database.
        
        Args:
            indicators: Dict of technical indicator values.
            metadata: Dict with timestamp, price, strategy_used, etc.
        
        Returns:
            Pattern ID string.
        """
        vector = self._indicators_to_vector(indicators)
        pattern_id = self._generate_pattern_id(indicators, metadata)
        
        # Prepare metadata for ChromaDB (must be strings, ints, or floats)
        chroma_metadata = {
            "timestamp": str(metadata.get("timestamp", datetime.now().isoformat())),
            "price": float(metadata.get("price", indicators.get("close", 0) or 0)),
            "trend": str(metadata.get("trend", indicators.get("trend", "neutral"))),
            "rsi": float(indicators.get("rsi", 50) or 50),
            "atr": float(indicators.get("atr", 0) or 0),
            "macd_histogram": float(indicators.get("macd_histogram", 0) or 0),
            "strategy_used": str(metadata.get("strategy_used", "unknown")),
            "signal_action": str(metadata.get("signal_action", "hold")),
            "signal_confidence": float(metadata.get("signal_confidence", 0.0)),
            "trade_outcome": str(metadata.get("trade_outcome", "none")),
            "profit_loss": float(metadata.get("profit_loss", 0.0)),
            "market_regime": str(metadata.get("market_regime", "unknown")),
            # Bug 4: provenance so simulated-OHLC patterns can be excluded from RAG.
            "data_source": str(metadata.get("data_source", "LIVE_MICRO")),
            "symbol": str(metadata.get("symbol", "")),
        }
        
        # Upsert the pattern
        self.collection.upsert(
            ids=[pattern_id],
            embeddings=[vector],
            metadatas=[chroma_metadata],
        )
        
        return pattern_id
    
    def find_similar(
        self,
        indicators: dict,
        n_results: int = 5,
        filter_outcome: Optional[str] = None,
        exclude_simulated_ohlc: bool = True,
        symbol: str = "",
    ) -> list[dict]:
        """
        Find similar market patterns using vector similarity search.
        
        This is the RAG retrieval step - given current market conditions,
        find historically similar patterns and their outcomes.
        
        Args:
            indicators: Current technical indicators.
            n_results: Number of similar patterns to return.
            filter_outcome: Optional filter (e.g., "win" to find only winning patterns).
            exclude_simulated_ohlc: If True, exclude patterns from simulated OHLC data.
            symbol: Base symbol to filter patterns by (e.g. "XAUUSD", "BTCUSD").
                    Mandatory for live lookups to avoid cross-symbol contamination.
        
        Returns:
            List of dicts with pattern metadata and similarity distance.
        """
        if self.collection.count() == 0:
            return []
        
        vector = self._indicators_to_vector(indicators)
        
        # Build query filter if specified
        conds = []
        if symbol:
            conds.append({"symbol": symbol})
        if filter_outcome:
            conds.append({"trade_outcome": filter_outcome})
        # Bug 4: never retrieve fictitious interpolated-OHLC patterns for live RAG.
        if exclude_simulated_ohlc:
            conds.append({"data_source": {"$ne": "SIMULATED_OHLC"}})
        if not conds:
            where_filter = None
        elif len(conds) == 1:
            where_filter = conds[0]
        else:
            where_filter = {"$and": conds}
        
        results = self.collection.query(
            query_embeddings=[vector],
            n_results=min(n_results, self.collection.count()),
            where=where_filter,
            include=["metadatas", "distances"],
        )
        
        patterns = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                patterns.append({
                    "pattern_id": results["ids"][0][i],  # ← FIX #2: Explicit pattern_id
                    "id": results["ids"][0][i],  # Keep for backward compat
                    "metadata": results["metadatas"][0][i],
                    "similarity": 1.0 - (results["distances"][0][i] if results.get("distances") else 0),
                })
        
        return patterns
    
    def find_winning_patterns(
        self,
        indicators: dict,
        n_results: int = 5,
        symbol: str = "",
    ) -> list[dict]:
        """Find similar patterns that resulted in winning trades."""
        return self.find_similar(indicators, n_results=n_results, filter_outcome="win", symbol=symbol)
    
    def find_losing_patterns(
        self,
        indicators: dict,
        n_results: int = 5,
        symbol: str = "",
    ) -> list[dict]:
        """Find similar patterns that resulted in losing trades."""
        return self.find_similar(indicators, n_results=n_results, filter_outcome="loss", symbol=symbol)
    
    def update_pattern_outcome(
        self,
        pattern_id: str,
        outcome: str,
        profit_loss: float,
    ):
        """
        Update a pattern with its trade outcome after the trade closes.
        This is how the bot learns from experience.
        
        Args:
            pattern_id: The pattern ID to update.
            outcome: "win" or "loss".
            profit_loss: P&L in dollars.
        """
        try:
            self.collection.update(
                ids=[pattern_id],
                metadatas=[{
                    "trade_outcome": outcome,
                    "profit_loss": float(profit_loss),
                }],
            )
            logger.info(f"Updated pattern {pattern_id}: outcome={outcome}, pnl=${profit_loss:.2f}")
        except Exception as e:
            logger.error(f"Failed to update pattern {pattern_id}: {e}")
    
    # ─── Analytics ────────────────────────────────────────────
    
    def get_statistics(self) -> dict:
        """Get statistics about stored patterns."""
        count = self.collection.count()
        
        if count == 0:
            return {
                "total_patterns": 0,
                "winning_patterns": 0,
                "losing_patterns": 0,
                "pending_patterns": 0,
                "strategies_used": [],
                "win_rate": 0.0,
            }
        
        # Safe summary via targeted counts (avoids loading all metadata).
        wins = self.collection.count(where={"trade_outcome": "win"})
        losses = self.collection.count(where={"trade_outcome": "loss"})
        pending = self.collection.count(where={"trade_outcome": "pending"})
        total_trades = wins + losses
        
        return {
            "total_patterns": count,
            "winning_patterns": wins,
            "losing_patterns": losses,
            "pending_patterns": pending,
            "strategies_used": [],
            "win_rate": round(wins / max(total_trades, 1) * 100, 2),
        }
    
    def get_patterns_by_strategy(self, strategy_name: str) -> list[dict]:
        """Get all patterns for a specific strategy."""
        results = self.collection.get(
            where={"strategy_used": strategy_name},
            include=["metadatas"],
        )
        
        patterns = []
        if results["ids"]:
            for i in range(len(results["ids"])):
                patterns.append({
                    "id": results["ids"][i],
                    "metadata": results["metadatas"][i],
                })
        
        return patterns
    
    def get_best_strategies(self, min_samples: int = 3) -> list[dict]:
        """
        Find which strategies have the best win rates.
        Used by the meta-strategy agent to select optimal strategies.
        
        NOTE: This method is currently dead code (not called on the live path).
        It uses a safe batched fetch to avoid loading all metadata at once.
        """
        strategy_stats = {}
        offset = 0
        limit = 500
        while True:
            batch = self.collection.get(
                include=["metadatas"],
                offset=offset,
                limit=limit,
            )
            if not batch.get("ids"):
                break
            for i, meta in enumerate(batch.get("metadatas", [])):
                strategy = meta.get("strategy_used", "unknown")
                outcome = meta.get("trade_outcome", "none")
                if strategy not in strategy_stats:
                    strategy_stats[strategy] = {"wins": 0, "losses": 0, "total": 0}
                if outcome == "win":
                    strategy_stats[strategy]["wins"] += 1
                    strategy_stats[strategy]["total"] += 1
                elif outcome == "loss":
                    strategy_stats[strategy]["losses"] += 1
                    strategy_stats[strategy]["total"] += 1
            offset += limit
            if len(batch.get("ids", [])) < limit:
                break
        
        results = []
        for strategy, stats in strategy_stats.items():
            if stats["total"] >= min_samples:
                results.append({
                    "strategy": strategy,
                    "win_rate": round(stats["wins"] / max(stats["total"], 1) * 100, 2),
                    "total_trades": stats["total"],
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                })
        
        return sorted(results, key=lambda x: x["win_rate"], reverse=True)
    
    def clear(self):
        """Clear all patterns from the store."""
        count = self.collection.count()
        self.collection.delete(where={})
        logger.info(f"Cleared {count} patterns from store")
    
    @property
    def pattern_count(self) -> int:
        """Total number of stored patterns."""
        return self.collection.count()
