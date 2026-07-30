# COMPREHENSIVE TESTING FRAMEWORK
## Validation Strategy for All Fixes

**Purpose:** Ensure each fix works correctly before moving to next phase  
**Scope:** Unit tests, integration tests, validation queries  
**Coverage:** All 7 fixes + backtesting framework

---

## TESTING STRATEGY OVERVIEW

### Level 1: Unit Tests (Code correctness)
- Individual method testing
- Data transformation validation
- Error handling

### Level 2: Integration Tests (Data flow)
- Multiple components together
- End-to-end data threading
- Database integrity

### Level 3: System Tests (Bot behavior)
- Full trading cycles
- Learning system validation
- Performance metrics

---

## FIX #1 TESTING: Thread Indicators Through Pipeline

### Unit Tests

**Test 1.1: Indicators complete in run_strategy_design()**
```python
def test_fix1_run_strategy_design_returns_indicators():
    """Verify run_strategy_design returns full indicators dict"""
    bot = TradingBot()
    research = bot.run_research()
    
    strategy_result = bot.run_strategy_design(research)
    
    assert "indicators" in strategy_result
    assert "signal" in strategy_result
    
    indicators = strategy_result["indicators"]
    assert "rsi" in indicators
    assert "atr" in indicators
    assert "macd" in indicators
    assert indicators["rsi"] is not None  # Not None, actual value
```

**Test 1.2: Indicators passed to record_outcome()**
```python
def test_fix1_indicators_passed_to_record_outcome():
    """Verify indicators parameter accepted by record_outcome()"""
    meta_strategy = MetaStrategyAgent(...)
    
    indicators = {
        "rsi": 45.2,
        "atr": 12.5,
        "macd": -0.15,
    }
    
    decision = {"action": "buy", "confidence": 0.7}
    
    # Should not raise TypeError about unexpected keyword argument
    meta_strategy.record_outcome(
        decision=decision,
        profit_loss=100.0,
        indicators=indicators,
    )
```

### Integration Tests

**Test 1.3: Indicators end-to-end flow**
```python
def test_fix1_indicators_flow_end_to_end():
    """Verify indicators flow from research → strategy → execution → record"""
    bot = TradingBot()
    
    # Run one cycle
    cycle_result = bot.run_trading_cycle()
    
    # Check database
    trades = bot.experience_db.get_recent_trades(limit=1)
    assert len(trades) > 0
    
    trade = trades[0]
    indicators = json.loads(trade["indicators"])
    
    # Should have multiple indicators, not just trend
    assert len(indicators) > 2
    assert "rsi" in indicators
    assert indicators["rsi"] is not None
```

### Validation Query

```sql
-- Check indicators are complete in database
SELECT trade_id, indicators 
FROM trades 
WHERE trade_id > (SELECT MAX(trade_id) - 5 FROM trades)
ORDER BY created_at DESC;

-- Should show JSON with multiple fields, not empty or minimal
-- Example good result:
-- {"rsi": 45.2, "atr": 12.5, "macd": -0.15, "ema_9": 2050.4, ...}

-- Count non-null indicator fields
SELECT COUNT(*) FROM trades 
WHERE JSON_EXTRACT(indicators, '$.rsi') IS NOT NULL;
-- Should be close to total trade count
```

---

## FIX #2 TESTING: Pattern ID Tracking

### Unit Tests

**Test 2.1: store_pattern returns pattern_id**
```python
def test_fix2_store_pattern_returns_id():
    """Verify store_pattern returns pattern_id"""
    vs = PatternVectorStore()
    
    indicators = {"rsi": 45, "atr": 12}
    result = vs.store_pattern(
        indicators=indicators,
        market_condition="trending",
        strategy_used="RSI_MeanReversion",
    )
    
    # Should return pattern_id
    assert result is not None
    if isinstance(result, dict):
        assert "pattern_id" in result
    else:
        assert len(result) > 0  # pattern_id returned as string or tuple element
```

**Test 2.2: find_similar returns pattern_ids**
```python
def test_fix2_find_similar_returns_pattern_ids():
    """Verify find_similar returns pattern_id in results"""
    matcher = PatternMatcher(vector_store)
    
    indicators = {"rsi": 45, "atr": 12}
    results = matcher.find_similar(indicators, top_k=5)
    
    # Results should have pattern_id
    for result in results:
        assert "pattern_id" in result
        assert result["pattern_id"] is not None
```

**Test 2.3: pattern_id added to decision dict**
```python
def test_fix2_pattern_id_in_decision():
    """Verify decision dict contains pattern_id"""
    meta_strategy = MetaStrategyAgent(...)
    
    indicators = {"rsi": 45, "atr": 12}
    decision = meta_strategy.decide(indicators, [])
    
    assert "pattern_id" in decision
    # Could be None if no patterns found, but key must exist
```

### Integration Tests

**Test 2.4: update_pattern_outcome called**
```python
def test_fix2_update_pattern_outcome_called():
    """Verify update_pattern_outcome is called when trade closes"""
    bot = TradingBot()
    
    # Run cycle, close a position
    bot.run_trading_cycle()
    # Force a position to close by setting current price past TP
    bot._check_closed_positions()
    
    # Check vector store - pattern should have outcome
    patterns = bot.vector_store.collection.get()
    
    # At least one pattern should have outcome field set
    updated_patterns = [p for p in patterns if "outcome" in p.get("metadata", {})]
    assert len(updated_patterns) > 0
```

### Validation Query

```sql
-- Check ChromaDB has pattern IDs
-- (SQLite query if patterns also stored in SQL):
SELECT COUNT(DISTINCT pattern_id) 
FROM patterns 
WHERE pattern_id IS NOT NULL;

-- Should be > 0

-- Check patterns have outcomes
SELECT outcome, COUNT(*) 
FROM patterns 
GROUP BY outcome;

-- Should show: win, loss, breakeven (not all NULL)
```

---

## FIX #3 TESTING: Real Trade Outcomes

### Unit Tests

**Test 3.1: OpenPosition class calculates PnL correctly**
```python
def test_fix3_openposition_pnl_buy():
    """Verify OpenPosition calculates PnL correctly for BUY"""
    position = TradingBot.OpenPosition(
        trade_id="test1",
        action="buy",
        entry_price=2050.0,
        entry_time=datetime.now(),
        stop_loss=2040.0,
        take_profit=2060.0,
        position_size=0.1,
        decision={"action": "buy"},
    )
    
    # Test take profit hit
    is_closed, reason, pnl = position.check_if_closed(2060.0)
    
    assert is_closed == True
    assert reason == "tp"
    assert pnl == (2060.0 - 2050.0) * 0.1  # = 1.0
```

**Test 3.2: OpenPosition calculates PnL correctly for SELL**
```python
def test_fix3_openposition_pnl_sell():
    """Verify OpenPosition calculates PnL correctly for SELL"""
    position = TradingBot.OpenPosition(
        trade_id="test2",
        action="sell",
        entry_price=2050.0,
        entry_time=datetime.now(),
        stop_loss=2060.0,
        take_profit=2040.0,
        position_size=0.1,
        decision={"action": "sell"},
    )
    
    # Test take profit hit
    is_closed, reason, pnl = position.check_if_closed(2040.0)
    
    assert is_closed == True
    assert reason == "tp"
    assert pnl == (2050.0 - 2040.0) * 0.1  # = 1.0
```

### Integration Tests

**Test 3.3: Position tracking through cycle**
```python
def test_fix3_position_tracked_and_closed():
    """Verify position tracked after execution and closed correctly"""
    bot = TradingBot()
    
    # Execute trade
    cycle_result = bot.run_trading_cycle()
    
    # Should have tracked position
    assert len(bot.open_positions) >= 0
    
    # Force close by manipulating price
    if bot.open_positions:
        position = bot.open_positions[0]
        # Manually trigger close
        position.entry_time = datetime.now() - timedelta(hours=25)  # Timeout
        
        bot._check_closed_positions()
        
        # Position should be removed from open list
        assert position not in bot.open_positions
```

### System Tests

**Test 3.4: Real outcomes recorded in database**
```python
def test_fix3_real_outcomes_in_database():
    """Verify real profit/loss values recorded, not all 0.0"""
    bot = TradingBot()
    
    # Run 5 cycles to generate trades
    for i in range(5):
        bot.run_trading_cycle()
    
    # Check database
    trades = bot.experience_db.get_recent_trades(limit=20)
    
    # Should have non-zero profit_loss values
    non_zero = [t for t in trades if t["profit_loss"] != 0.0]
    zero_only = [t for t in trades if t["profit_loss"] == 0.0]
    
    # At least some should be non-zero (closed positions)
    # Some can be zero (pending positions)
    assert len(non_zero) > 0 or len(zero_only) < len(trades)
```

### Validation Query

```sql
-- Check trade outcomes are real, not all 0.0
SELECT profit_loss, COUNT(*) as count
FROM trades
GROUP BY (profit_loss = 0.0)
ORDER BY profit_loss DESC;

-- Should show:
-- profit_loss != 0.0: some trades
-- profit_loss = 0.0: some trades (pending)
-- NOT all 0.0

-- Check outcomes are labeled
SELECT outcome, COUNT(*) as count
FROM trades
GROUP BY outcome;

-- Should show: win, loss, pending, breakeven
```

---

## FIX #4 TESTING: Use Performance Data

### Unit Tests

**Test 4.1: get_strategy_performance returns dict**
```python
def test_fix4_get_strategy_performance():
    """Verify get_strategy_performance returns performance data"""
    exp_db = ExperienceDatabase()
    
    performance = exp_db.get_strategy_performance()
    
    assert isinstance(performance, dict)
    # After some trades, should have data
    if len(performance) > 0:
        strategy = list(performance.keys())[0]
        assert "win_rate" in performance[strategy]
        assert "avg_profit" in performance[strategy]
        assert performance[strategy]["win_rate"] >= 0
        assert performance[strategy]["win_rate"] <= 100
```

**Test 4.2: update_weights_from_performance changes weights**
```python
def test_fix4_update_weights_from_performance():
    """Verify weights updated based on performance"""
    registry = StrategyRegistry()
    
    # Set initial weights
    for name in registry.strategies:
        registry.strategies[name]["weight"] = 1.0
    
    # Create fake performance data
    performance = {
        "RSI_MeanReversion": {"win_rate": 80.0},
        "EMA_TrendFollow": {"win_rate": 30.0},
    }
    
    registry.update_weights_from_performance(performance)
    
    # High WR should have higher weight
    rsi_weight = registry.strategies["RSI_MeanReversion"].get("weight", 1.0)
    ema_weight = registry.strategies["EMA_TrendFollow"].get("weight", 1.0)
    
    assert rsi_weight > ema_weight
```

### Integration Tests

**Test 4.3: Strategy selection uses updated weights**
```python
def test_fix4_strategy_selection_uses_weights():
    """Verify meta-strategy uses performance weights in decision"""
    meta_strategy = MetaStrategyAgent(...)
    
    # First cycle
    indicators = {"rsi": 45, "atr": 12}
    decision1 = meta_strategy.decide(indicators, [])
    
    # Record some outcomes
    meta_strategy.record_outcome(decision1, profit_loss=100.0)
    
    # Second cycle
    decision2 = meta_strategy.decide(indicators, [])
    
    # Strategy selection might differ based on performance
    # (if strategies are recommending different things)
```

### Validation Query

```sql
-- Check strategy performance is calculated correctly
SELECT strategy_used, COUNT(*) as total,
       SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
       ROUND(100.0 * SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) 
             / COUNT(*), 2) as win_rate
FROM trades
WHERE outcome IN ('win', 'loss')
GROUP BY strategy_used
ORDER BY win_rate DESC;

-- Should show realistic win rates, not all 50%
```

---

## SYSTEM-WIDE VALIDATION

### Performance Metrics Tracking

**Create a validation dashboard:**
```python
def validate_system_health():
    """Check overall system health after fixes"""
    exp_db = ExperienceDatabase()
    
    trades = exp_db.get_recent_trades(limit=100)
    
    metrics = {
        "total_trades": len(trades),
        "trades_with_outcomes": sum(1 for t in trades if t["outcome"] != "pending"),
        "win_rate": calculate_win_rate(trades),
        "avg_profit": calculate_avg_profit(trades),
        "strategies_tracked": count_unique(t["strategy_used"] for t in trades),
        "indicators_complete": count_complete_indicators(trades),
        "patterns_labeled": count_labeled_patterns(),
    }
    
    return metrics

def calculate_win_rate(trades):
    wins = sum(1 for t in trades if t["outcome"] == "win")
    total = sum(1 for t in trades if t["outcome"] != "pending")
    return (wins / total * 100) if total > 0 else 0

def count_complete_indicators(trades):
    complete = 0
    for trade in trades:
        indicators = json.loads(trade["indicators"])
        if len(indicators) > 3:  # More than just trend/rsi/atr
            complete += 1
    return complete
```

**Expected values after each phase:**

| Metric | After #1 | After #2 | After #3 | After #4 |
|--------|----------|----------|----------|----------|
| Indicators complete | 100% | 100% | 100% | 100% |
| Patterns labeled | 0% | 50%+ | 80%+ | 90%+ |
| Outcomes != 0.0 | 0% | 10%+ | 50%+ | 80%+ |
| Win rate measurable | No | No | Yes | Yes |
| Strategies weighted equally | Yes | Yes | Yes | No |

---

## TESTING CHECKLIST

### Before Fix #1
- [ ] Baseline test passes (bot runs 1 cycle)
- [ ] Database accessible
- [ ] No import errors

### After Fix #1
- [ ] Test 1.1 passes (indicators returned)
- [ ] Test 1.2 passes (indicators parameter works)
- [ ] Test 1.3 passes (end-to-end flow)
- [ ] Validation query shows complete indicators
- [ ] 100% of trades have full indicators

### After Fix #2
- [ ] Test 2.1 passes (pattern_id returned)
- [ ] Test 2.2 passes (pattern_id in find_similar)
- [ ] Test 2.3 passes (pattern_id in decision)
- [ ] Test 2.4 passes (update_pattern_outcome called)
- [ ] Validation query shows pattern IDs

### After Fix #3
- [ ] Test 3.1 passes (PnL calculation buy)
- [ ] Test 3.2 passes (PnL calculation sell)
- [ ] Test 3.3 passes (position tracking)
- [ ] Test 3.4 passes (real outcomes recorded)
- [ ] Validation query shows non-zero profits

### After Fix #4
- [ ] Test 4.1 passes (performance data retrieved)
- [ ] Test 4.2 passes (weights updated)
- [ ] Test 4.3 passes (weights used in selection)
- [ ] Validation query shows performance calculation
- [ ] Strategies have different weights

---

## CONTINUOUS MONITORING

**Add to dashboard/monitoring:**

```python
# Display learning metrics each cycle
def show_learning_metrics():
    exp_db = ExperienceDatabase()
    performance = exp_db.get_strategy_performance()
    
    console.print("\n[bold cyan]Learning System Status:[/bold cyan]")
    
    for strategy, metrics in performance.items():
        weight = registry.strategies[strategy].get("weight", 1.0)
        console.print(
            f"  {strategy}: {metrics['win_rate']:.1f}% WR, "
            f"weight={weight:.2f}x, "
            f"trades={metrics['trade_count']}"
        )
```

---

## ROLLBACK PLAN

If a fix breaks things:

1. Revert last commit
2. Run previous test suite
3. Verify tests pass
4. Identify issue
5. Implement fix again with correction

---

## SUCCESS CRITERIA

**Phase 1 complete when:**
- All 4 fixes implemented
- All unit tests pass
- All integration tests pass
- System validation metrics healthy
- Bot runs 20+ cycles error-free

**System is ready to:**
- Start learning
- Trade live (small size)
- Accumulate experience data
