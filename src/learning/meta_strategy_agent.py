"""
Meta-Strategy Agent — LLM-Powered Strategy Selection & Orchestration.

This is the central intelligence of the learning module. It:
1. Takes current market indicators and conditions
2. Queries the PatternMatcher (RAG) for similar historical patterns
3. Runs all 7 strategies from the StrategyRegistry
4. Uses an LLM (via LiteLLM) to evaluate which strategy/combination is best
5. Returns the optimal signal with confidence, reasoning, and metadata

The meta-strategy agent enables the bot to:
- Dynamically select the best strategy for current market conditions
- Learn from past trades via RAG-based pattern matching
- Combine multiple strategies when confidence is low on individual ones
- Continuously improve as the vector store and experience DB grow
"""

import json
import logging
from typing import Optional
from datetime import datetime

from src.learning.vector_store import PatternVectorStore
from src.learning.strategy_registry import StrategyRegistry
from src.learning.pattern_matcher import PatternMatcher
from src.learning.experience_db import ExperienceDatabase
from src.strategies.base import Signal
from src.core.llm import get_llm, mark_provider_failed

logger = logging.getLogger("learning.meta_strategy_agent")


class MetaStrategyAgent:
    """
    LLM-powered meta-strategy agent that selects optimal strategy combinations.
    
    Uses a three-stage pipeline:
    1. ANALYZE: Run all strategies + RAG pattern matching
    2. REASON: LLM evaluates results and selects best approach
    3. DECIDE: Return optimal signal with confidence and reasoning
    
    Usage:
        agent = MetaStrategyAgent(vector_store, registry, matcher, exp_db)
        
        # Get the best trading decision
        decision = agent.decide(indicators, market_data)
        
        # Record outcome for learning
        agent.record_outcome(decision, profit_loss, exit_price)
    """
    
    def __init__(
        self,
        vector_store: PatternVectorStore,
        strategy_registry: StrategyRegistry,
        pattern_matcher: PatternMatcher,
        experience_db: ExperienceDatabase,
    ):
        """
        Initialize the meta-strategy agent.
        
        Args:
            vector_store: PatternVectorStore for RAG pattern retrieval.
            strategy_registry: StrategyRegistry with all available strategies.
            pattern_matcher: PatternMatcher for historical similarity analysis.
            experience_db: ExperienceDatabase for trade outcome persistence.
        """
        self.vector_store = vector_store
        self.registry = strategy_registry
        self.matcher = pattern_matcher
        self.exp_db = experience_db
        
        # Cache for the LLM instance
        self._llm = None
        
        # Track which strategies have been used and their outcomes
        self.strategy_tracker = {}
        
        logger.info("MetaStrategyAgent initialized with %d strategies", self.registry.count)
    
    def _get_llm(self):
        """Get or create the LLM instance for strategy evaluation."""
        if self._llm is None:
            self._llm = get_llm(temperature=0.3)  # Low temp for analytical decisions
        return self._llm
    
    def decide(
        self,
        indicators: dict,
        market_data: list[dict],
        min_confidence: float = 0.5,
    ) -> dict:
        """
        Make a trading decision using the full meta-strategy pipeline.
        
        This is the main entry point. It:
        1. Runs all strategies in parallel
        2. Queries the RAG pattern matcher
        3. Gets learning insights from experience DB
        4. Uses LLM to evaluate and select the best approach
        5. Returns a structured decision
        
        Args:
            indicators: Dict of technical indicators.
            market_data: List of OHLCV candles.
            min_confidence: Minimum confidence threshold.
        
        Returns:
            Dict with the trading decision:
            {
                "action": "buy" | "sell" | "hold",
                "confidence": float (0.0-1.0),
                "price": float,
                "stop_loss": float or None,
                "take_profit": float or None,
                "strategy_used": str,
                "strategy_combination": list[str],
                "reasoning": str,
                "rag_insights": list[str],
                "learning_insights": list[str],
                "market_regime": str,
                "ensemble_signal": dict or None,
                "all_strategy_signals": list[dict],
                "timestamp": str,
            }
        """
        logger.info("Meta-strategy agent making decision...")
        
        close = indicators.get("close", 0)
        timestamp = datetime.now().isoformat()
        
        # ─── STAGE 1: ANALYZE ─────────────────────────────────
        # ← FIX #4: Update strategy weights from historical performance
        performance = self.exp_db.get_strategy_performance()
        if performance:
            self.registry.update_weights_from_performance(performance)
            logger.debug(f"Updated strategy weights based on {len(performance)} strategies")
        
        # Run all strategies in parallel
        all_signals = self.registry.run_all_strategies(indicators)
        ensemble = self.registry.get_ensemble_signal(indicators, min_agreement=2)
        
        # Get RAG-based pattern analysis
        rag_analysis = self.matcher.analyze_current_market(indicators)
        
        # ← FIX #2: Capture RAG pattern_id
        rag_pattern_id = rag_analysis.get("pattern_id")
        
        # Get optimal strategy combination from historical data
        optimal_combo = self.matcher.find_optimal_strategy_combination(indicators)
        
        # Get learning insights from experience DB
        learning_insights = self.exp_db.get_learning_insights()
        
        # Detect market regime
        regime = self.registry._detect_market_regime(indicators)
        
        # Find suitable strategies for current regime
        suitable_strategies = self.registry.find_suitable(indicators)
        suitable_names = [s.name for s in suitable_strategies]
        
        # ─── STAGE 2: REASON (LLM Evaluation) ─────────────────
        # Build a prompt for the LLM to evaluate all signals
        llm_prompt = self._build_evaluation_prompt(
            indicators=indicators,
            all_signals=all_signals,
            ensemble=ensemble,
            rag_analysis=rag_analysis,
            optimal_combo=optimal_combo,
            learning_insights=learning_insights,
            regime=regime,
            suitable_strategies=suitable_names,
            min_confidence=min_confidence,
        )
        
        # Get LLM evaluation
        llm_decision = self._evaluate_with_llm(llm_prompt)
        
        # ─── STAGE 3: DECIDE ──────────────────────────────────
        # Combine LLM evaluation with quantitative signals
        decision = self._synthesize_decision(
            llm_decision=llm_decision,
            all_signals=all_signals,
            ensemble=ensemble,
            rag_analysis=rag_analysis,
            optimal_combo=optimal_combo,
            indicators=indicators,
            regime=regime,
            min_confidence=min_confidence,
        )
        
        # Add metadata
        decision["timestamp"] = timestamp
        decision["rag_pattern_id"] = rag_pattern_id  # ← FIX #2: Include RAG pattern_id
        decision["rag_insights"] = rag_analysis.get("insights", [])
        decision["learning_insights"] = learning_insights
        decision["market_regime"] = regime
        decision["all_strategy_signals"] = [
            {
                "strategy": name,
                "action": s.action,
                "confidence": s.confidence,
                "reason": s.reason,
            }
            for name, s in all_signals
        ]
        decision["ensemble_signal"] = {
            "action": ensemble.action,
            "confidence": ensemble.confidence,
            "reason": ensemble.reason,
        }
        
        # Store the pattern in the vector store for future learning
        pattern_metadata = {
            "timestamp": timestamp,
            "price": close,
            "trend": indicators.get("trend", "neutral"),
            "strategy_used": decision.get("strategy_used", "meta_strategy"),
            "signal_action": decision.get("action", "hold"),
            "signal_confidence": decision.get("confidence", 0.0),
            "trade_outcome": "pending",
            "profit_loss": 0.0,
            "market_regime": regime,
        }
        pattern_id = self.vector_store.store_pattern(indicators, pattern_metadata)
        decision["pattern_id"] = pattern_id
        
        logger.info(
            "Meta-strategy decision: %s (confidence=%.2f, strategy=%s, regime=%s)",
            decision.get("action", "hold").upper(),
            decision.get("confidence", 0),
            decision.get("strategy_used", "unknown"),
            regime,
        )
        
        return decision
    
    def _build_evaluation_prompt(
        self,
        indicators: dict,
        all_signals: list,
        ensemble: Signal,
        rag_analysis: dict,
        optimal_combo: dict,
        learning_insights: list[str],
        regime: str,
        suitable_strategies: list[str],
        min_confidence: float,
    ) -> str:
        """Build a structured prompt for the LLM to evaluate strategies."""
        
        # Format all strategy signals
        signals_text = ""
        for name, signal in all_signals:
            signals_text += (
                f"  - {name}: {signal.action.upper()} "
                f"(confidence={signal.confidence:.2f}, reason={signal.reason})\n"
            )
        
        # Format RAG insights
        rag_text = "\n".join(f"  - {i}" for i in rag_analysis.get("insights", []))
        
        # Format learning insights
        learning_text = "\n".join(f"  - {i}" for i in learning_insights)
        
        # Format optimal combination
        combo_text = (
            f"  Primary: {optimal_combo.get('primary_strategy', 'N/A')}\n"
            f"  Secondary: {', '.join(optimal_combo.get('secondary_strategies', [])) or 'None'}\n"
            f"  Ensemble recommended: {optimal_combo.get('ensemble_recommended', False)}\n"
            f"  Reason: {optimal_combo.get('reason', 'N/A')}"
        )
        
        prompt = f"""You are a professional XAUUSD (Gold) trading strategist. Analyze the following market data and strategy signals to determine the optimal trading decision.

CURRENT MARKET CONDITIONS:
- Price: ${indicators.get('close', 0):.2f}
- RSI (14): {indicators.get('rsi', 'N/A'):.1f}
- ATR (14): ${indicators.get('atr', 0):.2f}
- Trend: {indicators.get('trend', 'N/A')}
- MACD Histogram: {indicators.get('macd_histogram', 'N/A')}
- Market Regime: {regime}
- Suitable Strategies: {', '.join(suitable_strategies)}

ALL STRATEGY SIGNALS:
{signals_text}
ENSEMBLE SIGNAL: {ensemble.action.upper()} (confidence={ensemble.confidence:.2f})
Reason: {ensemble.reason}

HISTORICAL PATTERN ANALYSIS (RAG):
Similar patterns found: {rag_analysis.get('similar_patterns_found', 0)}
Historical win rate: {rag_analysis.get('historical_win_rate', 50):.1f}%
Recommended action: {rag_analysis.get('recommended_action', 'insufficient_data')}
Confidence adjustment: {rag_analysis.get('confidence_adjustment', 0):+.2f}
{rag_text}

OPTIMAL STRATEGY COMBINATION (from historical data):
{combo_text}

LEARNING INSIGHTS FROM PAST TRADES:
{learning_text if learning_text else '  No trade history yet'}

DECISION CRITERIA:
- Minimum confidence threshold: {min_confidence}
- Risk:Reward minimum: 2.0
- Only trade if at least one strategy shows a clear signal
- Consider market regime when evaluating strategy suitability
- Use RAG historical data to adjust confidence
- Prefer ensemble signals when multiple strategies agree
- If no clear signal, recommend HOLD

Respond with a JSON object ONLY (no markdown, no code blocks):
{{
    "action": "buy" | "sell" | "hold",
    "confidence": <float 0.0-1.0>,
    "strategy_used": "<best strategy name or 'ensemble' or 'hold'>",
    "strategy_combination": ["<strategy1>", "<strategy2>", ...],
    "stop_loss_distance": <float in points or null>,
    "take_profit_distance": <float in points or null>,
    "reasoning": "<concise explanation of your decision>",
    "key_factors": ["<factor1>", "<factor2>", ...]
}}
"""
        return prompt
    
    def _evaluate_with_llm(self, prompt: str) -> dict:
        """
        Get strategy evaluation from the LLM.
        
        Falls back to quantitative-only decision if LLM is unavailable.
        """
        try:
            llm = self._get_llm()
            response = llm.invoke(prompt)
            
            # Parse the response content — handle both string and structured (list) content
            raw_content = response.content if hasattr(response, 'content') else str(response)
            
            # Handle structured content from OpenAI-compatible APIs (e.g., Kilo Gateway)
            # that returns lists of content blocks like:
            # [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]
            if isinstance(raw_content, list):
                texts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            texts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            texts.append(block.get("thinking", ""))
                    elif isinstance(block, str):
                        texts.append(block)
                content = "\n".join(texts)
            else:
                content = raw_content
            
            # Try to extract JSON from the response
            # Handle cases where LLM wraps in markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            decision = json.loads(content)
            
            # Validate required fields
            required = ["action", "confidence", "reasoning"]
            for field in required:
                if field not in decision:
                    raise ValueError(f"Missing required field: {field}")
            
            logger.info("LLM evaluation: %s (confidence=%.2f)", decision["action"], decision["confidence"])
            return decision
            
        except Exception as e:
            logger.warning(f"LLM evaluation failed, using quantitative fallback: {e}")
            return {
                "action": "hold",
                "confidence": 0.0,
                "strategy_used": "fallback",
                "strategy_combination": [],
                "stop_loss_distance": None,
                "take_profit_distance": None,
                "reasoning": f"LLM evaluation failed: {e}. Using quantitative fallback.",
                "key_factors": ["fallback_mode"],
            }
    
    def _synthesize_decision(
        self,
        llm_decision: dict,
        all_signals: list,
        ensemble: Signal,
        rag_analysis: dict,
        optimal_combo: dict,
        indicators: dict,
        regime: str,
        min_confidence: float,
    ) -> dict:
        """
        Synthesize the final decision from LLM evaluation + quantitative signals.
        
        The LLM's decision is weighted against the quantitative ensemble signal.
        If they disagree, the system becomes more conservative.
        """
        close = indicators.get("close", 0)
        
        # Get the best quantitative signal
        best_quant_signal = None
        best_quant_confidence = 0
        best_quant_strategy = None
        
        for name, signal in all_signals:
            if signal.action != "hold" and signal.confidence > best_quant_confidence:
                best_quant_confidence = signal.confidence
                best_quant_signal = signal
                best_quant_strategy = name
        
        # LLM decision
        llm_action = llm_decision.get("action", "hold")
        llm_confidence = llm_decision.get("confidence", 0.0)
        llm_strategy = llm_decision.get("strategy_used", "unknown")
        llm_strategy_combo = llm_decision.get("strategy_combination", [])
        
        # Apply RAG confidence adjustment
        rag_adjustment = rag_analysis.get("confidence_adjustment", 0.0)
        
        # ─── Decision Synthesis Logic ─────────────────────────
        
        # Case 1: LLM and quantitative signals agree
        if llm_action != "hold" and best_quant_signal and llm_action == best_quant_signal.action:
            # Boost confidence from agreement
            final_confidence = (llm_confidence + best_quant_confidence) / 2 + rag_adjustment
            final_confidence = max(0.0, min(1.0, final_confidence))
            
            if final_confidence >= min_confidence:
                # Calculate SL and TP
                sl_distance = llm_decision.get("stop_loss_distance")
                tp_distance = llm_decision.get("take_profit_distance")
                
                sl = None
                tp = None
                if sl_distance and close:
                    sl = close - sl_distance if llm_action == "buy" else close + sl_distance
                if tp_distance and close:
                    tp = close + tp_distance if llm_action == "buy" else close - tp_distance
                
                return {
                    "action": llm_action,
                    "confidence": round(final_confidence, 3),
                    "price": close,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "strategy_used": llm_strategy or best_quant_strategy or "ensemble",
                    "strategy_combination": llm_strategy_combo or [best_quant_strategy] if best_quant_strategy else [],
                    "reasoning": f"LLM+Quant agreement: {llm_decision.get('reasoning', '')}",
                    "key_factors": llm_decision.get("key_factors", []),
                }
        
        # Case 2: Only LLM sees a signal (quantitative is hold)
        if llm_action != "hold" and not best_quant_signal:
            final_confidence = llm_confidence * 0.8 + rag_adjustment  # Penalize for no quant support
            final_confidence = max(0.0, min(1.0, final_confidence))
            
            if final_confidence >= min_confidence + 0.1:  # Higher threshold for LLM-only
                return {
                    "action": llm_action,
                    "confidence": round(final_confidence, 3),
                    "price": close,
                    "stop_loss": None,
                    "take_profit": None,
                    "strategy_used": llm_strategy or "llm_only",
                    "strategy_combination": llm_strategy_combo,
                    "reasoning": f"LLM-only signal: {llm_decision.get('reasoning', '')}",
                    "key_factors": llm_decision.get("key_factors", []),
                }
        
        # Case 3: Only quantitative sees a signal (LLM says hold)
        if best_quant_signal and llm_action == "hold":
            final_confidence = best_quant_confidence * 0.7 + rag_adjustment  # Penalize for no LLM support
            final_confidence = max(0.0, min(1.0, final_confidence))
            
            if final_confidence >= min_confidence + 0.15:  # Higher threshold for quant-only
                return {
                    "action": best_quant_signal.action,
                    "confidence": round(final_confidence, 3),
                    "price": close,
                    "stop_loss": best_quant_signal.stop_loss,
                    "take_profit": best_quant_signal.take_profit,
                    "strategy_used": best_quant_strategy or "quant_only",
                    "strategy_combination": [best_quant_strategy] if best_quant_strategy else [],
                    "reasoning": f"Quant-only signal from {best_quant_strategy}: {best_quant_signal.reason}",
                    "key_factors": [f"Quantitative: {best_quant_signal.reason[:50]}"],
                }
        
        # Case 4: LLM and quant disagree on direction
        if llm_action != "hold" and best_quant_signal and llm_action != best_quant_signal.action:
            logger.warning(
                "LLM (%s) and quant (%s) disagree — defaulting to HOLD",
                llm_action, best_quant_signal.action,
            )
            return {
                "action": "hold",
                "confidence": 0.0,
                "price": close,
                "stop_loss": None,
                "take_profit": None,
                "strategy_used": "conflict_resolution",
                "strategy_combination": [],
                "reasoning": (
                    f"LLM recommends {llm_action.upper()} but quantitative best "
                    f"({best_quant_strategy}) recommends {best_quant_signal.action.upper()}. "
                    f"Conflict resolved to HOLD."
                ),
                "key_factors": ["llm_quant_conflict"],
            }
        
        # Case 5: Everything says hold
        return {
            "action": "hold",
            "confidence": 0.0,
            "price": close,
            "stop_loss": None,
            "take_profit": None,
            "strategy_used": "no_clear_signal",
            "strategy_combination": [],
            "reasoning": (
                f"No clear signal. LLM: {llm_action.upper()}, "
                f"Best quant: {best_quant_strategy or 'none'} "
                f"({best_quant_signal.action if best_quant_signal else 'HOLD'}). "
                f"RAG confidence adjustment: {rag_adjustment:+.2f}"
            ),
            "key_factors": ["no_clear_signal"],
        }
    
    def record_outcome(
        self,
        decision: dict,
        profit_loss: float,
        exit_price: Optional[float] = None,
        exit_reason: Optional[str] = None,
        indicators: Optional[dict] = None,  # ← FIX #1: Add indicators parameter
    ):
        """
        Record the outcome of a trade for learning.
        
        This updates both the vector store (for RAG) and the experience DB
        (for structured analytics), enabling continuous learning.
        
        Args:
            decision: The decision dict returned by decide().
            profit_loss: P&L in dollars.
            exit_price: Exit price if trade was closed.
            exit_reason: Why the trade was closed.
        """
        if decision.get("action") == "hold":
            return  # Nothing to record
        
        # Determine outcome
        if profit_loss > 0:
            outcome = "win"
        elif profit_loss < 0:
            outcome = "loss"
        else:
            outcome = "breakeven"
        
        # Update the vector store pattern with the outcome
        pattern_id = decision.get("pattern_id")
        if pattern_id:
            self.vector_store.update_pattern_outcome(pattern_id, outcome, profit_loss)
        
        # Record in experience DB
        strategy_combo = ",".join(decision.get("strategy_combination", []))
        
        signal_dict = {
            "action": decision.get("action", "hold"),
            "price": decision.get("price", 0),
            "stop_loss": decision.get("stop_loss"),
            "take_profit": decision.get("take_profit"),
            "confidence": decision.get("confidence", 0),
            "strategy_used": decision.get("strategy_used", "unknown"),
            "symbol": "XAUUSD",
        }
        
        # We need indicators for the experience DB - store what we have
        # ← FIX #1: Use passed-in indicators, fallback to minimal if not provided
        if indicators is None:
            # Fallback: create minimal indicators from decision
            indicators = {
                "trend": decision.get("market_regime", "unknown"),
                "rsi": None,
                "atr": None,
            }
        # Otherwise use the full indicators dict that was passed in
        
        self.exp_db.record_trade(
            signal=signal_dict,
            indicators=indicators,
            outcome=outcome,
            profit_loss=profit_loss,
            exit_price=exit_price,
            exit_reason=exit_reason,
            strategy_combination=strategy_combo,
        )
        
        logger.info(
            "Recorded outcome: %s (${:.2f}) using %s".format(profit_loss),
            outcome.upper(),
            decision.get("strategy_used", "unknown"),
        )
    
    def get_learning_summary(self) -> dict:
        """
        Get a summary of what the meta-strategy agent has learned.
        
        Returns:
            Dict with learning statistics and insights.
        """
        vector_stats = self.vector_store.get_statistics()
        perf_stats = self.exp_db.get_performance_stats()
        strategy_perf = self.exp_db.get_strategy_performance()
        insights = self.exp_db.get_learning_insights()
        
        return {
            "vector_store": vector_stats,
            "performance": perf_stats,
            "strategy_performance": strategy_perf,
            "insights": insights,
            "total_patterns": vector_stats.get("total_patterns", 0),
            "total_trades": perf_stats.get("total_trades", 0),
            "overall_win_rate": perf_stats.get("win_rate", 0),
        }
    
    def get_strategy_recommendations(self) -> list[dict]:
        """
        Get current strategy recommendations based on all learning.
        
        Returns:
            List of recommended strategies with reasoning.
        """
        # Get best strategies from vector store
        best_from_store = self.vector_store.get_best_strategies(min_samples=1)
        
        # Get strategy performance from experience DB
        strategy_perf = self.exp_db.get_strategy_performance()
        
        # Combine and rank
        strategy_scores = {}
        
        for s in best_from_store:
            strategy_scores[s["strategy"]] = {
                "win_rate": s["win_rate"],
                "total_trades": s["total_trades"],
                "source": "vector_store",
            }
        
        for s in strategy_perf:
            name = s["strategy_name"]
            if name in strategy_scores:
                strategy_scores[name]["win_rate"] = (
                    strategy_scores[name]["win_rate"] + s["win_rate"]
                ) / 2
                strategy_scores[name]["total_trades"] += s["total_trades"]
                strategy_scores[name]["source"] = "combined"
            else:
                strategy_scores[name] = {
                    "win_rate": s["win_rate"],
                    "total_trades": s["total_trades"],
                    "source": "experience_db",
                }
        
        # Sort by win rate
        ranked = sorted(
            strategy_scores.items(),
            key=lambda x: x[1]["win_rate"],
            reverse=True,
        )
        
        return [
            {
                "strategy": name,
                "win_rate": data["win_rate"],
                "total_trades": data["total_trades"],
                "source": data["source"],
            }
            for name, data in ranked
        ]
