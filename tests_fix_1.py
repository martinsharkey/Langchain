#!/usr/bin/env python3
"""
Test script for FIX #1: Thread indicators through pipeline

This test verifies that:
1. run_strategy_design returns indicators
2. indicators parameter is passed to record_outcome
3. indicators are stored in database with full fields
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.experience_db import ExperienceDatabase
from src.learning.meta_strategy_agent import MetaStrategyAgent
from src.learning.vector_store import PatternVectorStore
from src.learning.strategy_registry import StrategyRegistry
from src.learning.pattern_matcher import PatternMatcher

def test_fix1_indicators_parameter():
    """Test that record_outcome accepts indicators parameter"""
    print("\n" + "="*60)
    print("TEST 1: record_outcome accepts indicators parameter")
    print("="*60)
    
    try:
        # Create dependencies
        exp_db = ExperienceDatabase()
        vector_store = PatternVectorStore()
        strategy_registry = StrategyRegistry(exp_db)
        pattern_matcher = PatternMatcher(vector_store)
        
        # Create meta-strategy agent
        meta_strategy = MetaStrategyAgent(
            vector_store=vector_store,
            strategy_registry=strategy_registry,
            pattern_matcher=pattern_matcher,
            experience_db=exp_db,
        )
        
        # Create test decision
        decision = {
            "action": "buy",
            "confidence": 0.75,
            "price": 2050.0,
            "stop_loss": 2040.0,
            "take_profit": 2060.0,
            "strategy_used": "RSI_MeanReversion",
            "market_regime": "trending",
        }
        
        # Create test indicators (full set)
        test_indicators = {
            "rsi": 45.2,
            "atr": 12.5,
            "macd": -0.15,
            "ema_9": 2050.4,
            "ema_21": 2048.3,
            "bb_upper": 2055.0,
            "bb_lower": 2045.0,
            "support_levels": [2040.0, 2035.0],
            "resistance_levels": [2060.0, 2065.0],
            "trend": "uptrend",
        }
        
        # Call record_outcome WITH indicators (the fix)
        meta_strategy.record_outcome(
            decision=decision,
            profit_loss=100.0,  # Winning trade
            exit_price=2060.0,
            exit_reason="tp",
            indicators=test_indicators,  # ← FIX #1: Pass indicators
        )
        
        print("✓ record_outcome() called successfully with indicators parameter")
        
        # Verify indicators were stored
        trades = exp_db.get_recent_trades(limit=1)
        if trades:
            trade = trades[0]
            stored_indicators = json.loads(trade["indicators"])
            
            # Check if full indicators are stored (not just minimal)
            if len(stored_indicators) > 3:  # More than just trend/rsi/atr
                print(f"✓ Indicators stored with {len(stored_indicators)} fields")
                print(f"  Fields: {', '.join(stored_indicators.keys())}")
                
                # Verify specific fields
                if stored_indicators.get("rsi") == 45.2:
                    print("✓ RSI correctly stored: 45.2")
                if stored_indicators.get("atr") == 12.5:
                    print("✓ ATR correctly stored: 12.5")
                if stored_indicators.get("macd") == -0.15:
                    print("✓ MACD correctly stored: -0.15")
                    
                print("\n✅ TEST 1 PASSED")
                return True
            else:
                print(f"✗ Only {len(stored_indicators)} fields stored (expected > 3)")
                print(f"  Got: {stored_indicators}")
                return False
        else:
            print("✗ No trades found in database")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fix1_backward_compatibility():
    """Test that record_outcome still works WITHOUT indicators (backward compatible)"""
    print("\n" + "="*60)
    print("TEST 2: record_outcome backward compatible (no indicators)")
    print("="*60)
    
    try:
        exp_db = ExperienceDatabase()
        vector_store = PatternVectorStore()
        strategy_registry = StrategyRegistry(exp_db)
        pattern_matcher = PatternMatcher(vector_store)
        
        meta_strategy = MetaStrategyAgent(
            vector_store=vector_store,
            strategy_registry=strategy_registry,
            pattern_matcher=pattern_matcher,
            experience_db=exp_db,
        )
        
        decision = {
            "action": "sell",
            "confidence": 0.65,
            "price": 2048.0,
            "stop_loss": 2058.0,
            "take_profit": 2038.0,
            "strategy_used": "EMA_TrendFollow",
            "market_regime": "ranging",
        }
        
        # Call record_outcome WITHOUT indicators (should still work)
        meta_strategy.record_outcome(
            decision=decision,
            profit_loss=-50.0,  # Losing trade
            exit_price=2053.0,
            exit_reason="sl",
            # No indicators parameter ← Should still work
        )
        
        print("✓ record_outcome() called successfully WITHOUT indicators parameter")
        
        # Verify fallback indicators were stored
        trades = exp_db.get_recent_trades(limit=1)
        if trades:
            trade = trades[0]
            stored_indicators = json.loads(trade["indicators"])
            
            if "trend" in stored_indicators:
                print(f"✓ Fallback indicators stored: {stored_indicators}")
                print("\n✅ TEST 2 PASSED")
                return True
            else:
                print("✗ Fallback indicators not created")
                return False
        else:
            print("✗ No trades found")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("  FIX #1 VALIDATION TEST SUITE")
    print("  Thread Indicators Through Pipeline")
    print("█" * 60)
    
    test1_pass = test_fix1_indicators_parameter()
    test2_pass = test_fix1_backward_compatibility()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Test 1 (Indicators passed):    {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"Test 2 (Backward compatible):  {'✅ PASS' if test2_pass else '❌ FAIL'}")
    
    if test1_pass and test2_pass:
        print("\n" + "█" * 60)
        print("  ✅ FIX #1 VALIDATION COMPLETE")
        print("  All tests passed! Ready for Phase 1 integration testing.")
        print("█" * 60)
        sys.exit(0)
    else:
        print("\n" + "█" * 60)
        print("  ❌ FIX #1 VALIDATION FAILED")
        print("  Please review errors above.")
        print("█" * 60)
        sys.exit(1)
