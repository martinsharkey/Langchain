"""
Pattern Matcher — Fast Historical Pattern Recognition via RAG.

This module provides the RAG (Retrieval-Augmented Generation) pipeline
for the trading bot. Given current market conditions, it:
1. Converts indicators into a vector embedding
2. Queries the vector store for similar historical patterns
3. Analyzes what strategies worked/failed in similar conditions
4. Returns actionable insights for the meta-strategy agent

The pattern matcher enables the bot to "remember" past market conditions
and learn from experience, getting smarter over time.
"""

import logging
from typing import Optional
from datetime import datetime

from src.learning.vector_store import PatternVectorStore

logger = logging.getLogger("learning.pattern_matcher")


class PatternMatcher:
    """
    RAG-based pattern matcher for market analysis.
    
    Uses vector similarity search to find historical patterns
    similar to current market conditions, enabling the bot to
    learn from past experience.
    
    Usage:
        matcher = PatternMatcher(vector_store)
        
        # Get insights for current market
        insights = matcher.analyze_current_market(indicators)
        
        # Check if current setup has been profitable historically
        confidence_boost = matcher.get_historical_confidence(indicators)
    """
    
    def __init__(self, vector_store: PatternVectorStore):
        """
        Initialize the pattern matcher.
        
        Args:
            vector_store: An initialized PatternVectorStore instance.
        """
        self.vector_store = vector_store
    
    def analyze_current_market(self, indicators: dict) -> dict:
        """
        Analyze current market conditions against historical patterns.
        
        This is the main RAG pipeline entry point. It:
        1. Finds similar historical patterns
        2. Analyzes what strategies worked in similar conditions
        3. Identifies which strategies to prefer/avoid
        4. Provides a confidence boost/penalty based on history
        
        Args:
            indicators: Current technical indicators.
        
        Returns:
            Dict with analysis results:
            {
                "similar_patterns_found": int,
                "winning_patterns": int,
                "losing_patterns": int,
                "historical_win_rate": float,
                "best_strategies": [str],
                "worst_strategies": [str],
                "recommended_action": str,
                "confidence_adjustment": float,
                "insights": [str],
            }
        """
        # Find similar patterns (both winning and losing)
        similar = self.vector_store.find_similar(indicators, n_results=10)
        winning = self.vector_store.find_winning_patterns(indicators, n_results=5)
        losing = self.vector_store.find_losing_patterns(indicators, n_results=5)
        
        if not similar:
            return {
                "similar_patterns_found": 0,
                "winning_patterns": 0,
                "losing_patterns": 0,
                "historical_win_rate": 50.0,
                "best_strategies": [],
                "worst_strategies": [],
                "recommended_action": "insufficient_data",
                "confidence_adjustment": 0.0,
                "insights": ["No historical patterns found for current market conditions"],
            }
        
        # Analyze strategies used in similar patterns
        strategy_performance = {}
        for pattern in similar:
            meta = pattern["metadata"]
            strategy = meta.get("strategy_used", "unknown")
            outcome = meta.get("trade_outcome", "none")
            
            if strategy not in strategy_performance:
                strategy_performance[strategy] = {"wins": 0, "losses": 0, "total": 0}
            
            if outcome == "win":
                strategy_performance[strategy]["wins"] += 1
                strategy_performance[strategy]["total"] += 1
            elif outcome == "loss":
                strategy_performance[strategy]["losses"] += 1
                strategy_performance[strategy]["total"] += 1
        
        # Rank strategies by win rate
        ranked = sorted(
            [(s, p["wins"] / max(p["total"], 1) * 100, p["total"])
             for s, p in strategy_performance.items()],
            key=lambda x: x[1],
            reverse=True,
        )
        
        best_strategies = [s for s, wr, t in ranked if wr >= 50 and t >= 1][:3]
        worst_strategies = [s for s, wr, t in ranked if wr < 50 and t >= 1][:3]
        
        # Calculate historical win rate for similar conditions
        total_similar = len(winning) + len(losing)
        historical_win_rate = (len(winning) / max(total_similar, 1)) * 100
        
        # Confidence adjustment based on historical performance
        if historical_win_rate >= 70:
            confidence_adjustment = 0.15  # Strong historical support
            recommended_action = "favor"
        elif historical_win_rate >= 50:
            confidence_adjustment = 0.05  # Slight positive
            recommended_action = "cautious_favor"
        elif historical_win_rate >= 30:
            confidence_adjustment = -0.05  # Slight negative
            recommended_action = "cautious_avoid"
        else:
            confidence_adjustment = -0.15  # Strong historical warning
            recommended_action = "avoid"
        
        # Generate insights
        insights = []
        if best_strategies:
            insights.append(f"Best performing strategies in similar conditions: {', '.join(best_strategies)}")
        if worst_strategies:
            insights.append(f"Poorly performing strategies in similar conditions: {', '.join(worst_strategies)}")
        
        insights.append(f"Historical win rate in similar conditions: {historical_win_rate:.1f}% ({len(winning)}W/{len(losing)}L)")
        
        if confidence_adjustment > 0:
            insights.append(f"Confidence boosted by {confidence_adjustment:.0%} based on historical success")
        elif confidence_adjustment < 0:
            insights.append(f"Confidence reduced by {abs(confidence_adjustment):.0%} based on historical losses")
        
        return {
            "similar_patterns_found": len(similar),
            "winning_patterns": len(winning),
            "losing_patterns": len(losing),
            "historical_win_rate": round(historical_win_rate, 1),
            "best_strategies": best_strategies,
            "worst_strategies": worst_strategies,
            "recommended_action": recommended_action,
            "confidence_adjustment": confidence_adjustment,
            "insights": insights,
        }
    
    def get_historical_confidence(
        self,
        indicators: dict,
        strategy_name: Optional[str] = None,
    ) -> float:
        """
        Get a confidence boost/penalty based on historical performance.
        
        Returns a value between -0.3 and +0.3 that should be added to
        the strategy's base confidence.
        
        Args:
            indicators: Current technical indicators.
            strategy_name: Optional strategy name to filter by.
        
        Returns:
            Confidence adjustment (-0.3 to +0.3).
        """
        if strategy_name:
            # Find similar patterns where this strategy was used
            similar = self.vector_store.find_similar(indicators, n_results=20)
            strategy_patterns = [
                p for p in similar
                if p["metadata"].get("strategy_used") == strategy_name
            ]
            
            if not strategy_patterns:
                return 0.0
            
            wins = sum(1 for p in strategy_patterns if p["metadata"].get("trade_outcome") == "win")
            losses = sum(1 for p in strategy_patterns if p["metadata"].get("trade_outcome") == "loss")
            total = wins + losses
            
            if total == 0:
                return 0.0
            
            win_rate = wins / total
            return (win_rate - 0.5) * 0.6  # Scale to -0.3 to +0.3
        else:
            # General historical confidence
            analysis = self.analyze_current_market(indicators)
            return analysis["confidence_adjustment"]
    
    def get_strategy_recommendations(self, indicators: dict) -> list[dict]:
        """
        Get ranked strategy recommendations for current market.
        
        Returns a list of strategies with their expected performance
        based on historical similarity matching.
        
        Args:
            indicators: Current technical indicators.
        
        Returns:
            List of dicts with strategy name, expected win rate, and confidence.
        """
        similar = self.vector_store.find_similar(indicators, n_results=30)
        
        if not similar:
            return []
        
        # Aggregate by strategy
        strategy_stats = {}
        for pattern in similar:
            meta = pattern["metadata"]
            strategy = meta.get("strategy_used", "unknown")
            outcome = meta.get("trade_outcome", "none")
            similarity = pattern.get("similarity", 0.5)
            
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {
                    "wins": 0, "losses": 0, "total": 0,
                    "total_similarity": 0.0,
                }
            
            if outcome in ("win", "loss"):
                strategy_stats[strategy]["total"] += 1
                strategy_stats[strategy]["total_similarity"] += similarity
                if outcome == "win":
                    strategy_stats[strategy]["wins"] += 1
                else:
                    strategy_stats[strategy]["losses"] += 1
        
        recommendations = []
        for strategy, stats in strategy_stats.items():
            if stats["total"] > 0:
                avg_similarity = stats["total_similarity"] / stats["total"]
                win_rate = stats["wins"] / stats["total"] * 100
                confidence = (win_rate / 100) * avg_similarity
                
                recommendations.append({
                    "strategy": strategy,
                    "expected_win_rate": round(win_rate, 1),
                    "sample_size": stats["total"],
                    "confidence": round(confidence, 3),
                    "avg_similarity": round(avg_similarity, 3),
                })
        
        return sorted(recommendations, key=lambda x: x["confidence"], reverse=True)
    
    def find_optimal_strategy_combination(
        self,
        indicators: dict,
    ) -> dict:
        """
        Find the optimal combination of strategies for current conditions.
        
        Uses historical data to determine which single strategy or
        combination of strategies would have performed best in
        similar market conditions.
        
        Args:
            indicators: Current technical indicators.
        
        Returns:
            Dict with optimal strategy recommendation.
        """
        recommendations = self.get_strategy_recommendations(indicators)
        
        if not recommendations:
            return {
                "primary_strategy": None,
                "secondary_strategies": [],
                "ensemble_recommended": False,
                "reason": "Insufficient historical data",
            }
        
        # Best single strategy
        best = recommendations[0]
        
        # Find complementary strategies (different indicators, good performance)
        complementary = [r for r in recommendations[1:] if r["confidence"] > 0.3][:2]
        
        # Determine if ensemble is better than single
        ensemble_confidence = sum(r["confidence"] for r in recommendations[:3]) / 3
        ensemble_recommended = ensemble_confidence > best["confidence"] * 1.2
        
        return {
            "primary_strategy": best["strategy"],
            "primary_confidence": best["confidence"],
            "primary_win_rate": best["expected_win_rate"],
            "secondary_strategies": [r["strategy"] for r in complementary],
            "ensemble_recommended": ensemble_recommended,
            "ensemble_confidence": round(ensemble_confidence, 3) if ensemble_recommended else None,
            "reason": (
                f"Best single: {best['strategy']} ({best['expected_win_rate']:.1f}% win rate, "
                f"{best['sample_size']} samples)"
            ),
        }
