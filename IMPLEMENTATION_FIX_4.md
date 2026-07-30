# PHASE 1, FIX #4: USE EXPERIENCE DATA IN STRATEGY SELECTION
## Query historical performance data before selecting strategies

**Status:** Ready to implement  
**Effort:** 2-3 hours  
**Priority:** HIGH (closes the learning feedback loop)  
**Dependencies:** Fix #3 (real trade outcomes) must be done first

---

## PROBLEM STATEMENT

The meta-strategy agent has access to historical performance data but ignores it.

**Current code (BROKEN):**
```python
# In MetaStrategyAgent.decide(), line ~140-144
rag_analysis = self.matcher.analyze_current_market(indicators)
optimal_combo = self.matcher.find_optimal_strategy_combination(indicators)

# ← Meta-strategy picks strategies without looking at:
#   - Which strategy has higher historical win rate
#   - Which strategy has higher average profit
#   - Which strategy failed recently
```

**Result:** Bot treats a 20% win-rate strategy the same as a 70% win-rate strategy.

---

## ROOT CAUSE

Strategy weights are HARDCODED and never updated:

```python
# In strategy_registry.py
strategies = {
    "RSI_MeanReversion": {"weight": 1.0, ...},  # ← hardcoded
    "EMA_TrendFollow": {"weight": 1.0, ...},    # ← hardcoded
    "MACD_Momentum": {"weight": 1.0, ...},      # ← hardcoded
    # All others also 1.0
}
```

Even if strategy has 15% win rate vs another with 65%, they get equal weight.

---

## IMPLEMENTATION STEPS

### Step 1: Create method in ExperienceDatabase to get strategy performance

**File:** `src/learning/experience_db.py`  
**Location:** Add new method after existing methods

**Add this method:**
```python
def get_strategy_performance(self, strategy_name: str = None) -> dict:
    """
    Get historical performance metrics for strategies.
    
    Args:
        strategy_name: If provided, get metrics for specific strategy.
                      If None, get metrics for all strategies.
    
    Returns:
        Dict with {strategy_name: {win_rate, avg_profit, loss_count, ...}}
    """
    try:
        query = """
            SELECT 
                strategy_used,
                COUNT(*) as trade_count,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as loss_count,
                ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) 
                      / NULLIF(COUNT(*), 0), 2) as win_rate,
                ROUND(AVG(profit_loss), 2) as avg_profit,
                ROUND(SUM(profit_loss), 2) as total_profit,
                ROUND(MAX(profit_loss), 2) as max_profit,
                ROUND(MIN(profit_loss), 2) as max_loss
            FROM trades
            WHERE outcome IN ('win', 'loss')  -- Exclude pending
        """
        
        if strategy_name:
            query += f" AND strategy_used = '{strategy_name}'"
        
        query += " GROUP BY strategy_used ORDER BY win_rate DESC"
        
        cursor = self.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            return {}
        
        performance = {}
        for row in rows:
            strategy = row[0]
            performance[strategy] = {
                "trade_count": row[1],
                "win_count": row[2],
                "loss_count": row[3],
                "win_rate": row[4],  # Percentage
                "avg_profit": row[5],
                "total_profit": row[6],
                "max_profit": row[7],
                "max_loss": row[8],
            }
        
        return performance
    
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}")
        return {}
```

### Step 2: Create method to calculate strategy weights based on performance

**File:** `src/learning/strategy_registry.py`  
**Location:** Add new method in StrategyRegistry class

**Add this method:**
```python
def update_weights_from_performance(self, performance_data: dict):
    """
    Update strategy weights based on historical performance.
    
    Win rate directly affects weight:
    - 60% win rate → weight 1.2x (20% boost)
    - 50% win rate → weight 1.0x (neutral)
    - 40% win rate → weight 0.8x (20% penalty)
    
    Args:
        performance_data: Dict from ExperienceDatabase.get_strategy_performance()
    """
    for strategy_name, metrics in performance_data.items():
        if strategy_name not in self.strategies:
            continue
        
        win_rate = metrics.get("win_rate", 50.0)
        
        # Calculate weight factor: (win_rate - 50) / 50 normalized
        # This gives -1.0 to +1.0 range
        factor = (win_rate - 50.0) / 50.0
        
        # Convert to weight multiplier: 0.5x to 1.5x
        # 0% WR → 0.5x, 50% WR → 1.0x, 100% WR → 1.5x
        weight = 1.0 + (factor * 0.5)
        
        # Clamp between 0.2x and 2.0x (allow significant variation)
        weight = max(0.2, min(2.0, weight))
        
        self.strategies[strategy_name]["weight"] = weight
        
        logger.info(
            f"Updated {strategy_name}: win_rate={win_rate}% → weight={weight:.2f}x"
        )
```

### Step 3: Call weight update in MetaStrategyAgent

**File:** `src/learning/meta_strategy_agent.py`  
**Location:** In `decide()` method, around line 140-144

**Change from:**
```python
def decide(self, indicators: dict, market_data: list[dict], min_confidence: float = 0.5) -> dict:
    """Make a trading decision using the full meta-strategy pipeline."""
    
    # Run RAG analysis
    rag_analysis = self.matcher.analyze_current_market(indicators)
```

**Change to:**
```python
def decide(self, indicators: dict, market_data: list[dict], min_confidence: float = 0.5) -> dict:
    """Make a trading decision using the full meta-strategy pipeline."""
    
    # ← ADD THIS SECTION:
    # Update strategy weights from historical performance
    performance = self.exp_db.get_strategy_performance()
    if performance:
        self.registry.update_weights_from_performance(performance)
        logger.debug(f"Updated strategy weights based on {len(performance)} strategies")
    
    # Run RAG analysis
    rag_analysis = self.matcher.analyze_current_market(indicators)
```

### Step 4: Use strategy weights in ensemble voting

**File:** `src/learning/pattern_matcher.py` or `src/strategies/xauusd_strategy.py`  
**Location:** Find `get_ensemble_signal()` method

**Change from:**
```python
def get_ensemble_signal(self, signals: dict) -> dict:
    """Simple ensemble: count votes."""
    buy_votes = sum(1 for s in signals.values() if s.action == "buy")
    sell_votes = sum(1 for s in signals.values() if s.action == "sell")
    
    if buy_votes > sell_votes:
        return Signal(action="buy", ...)
    elif sell_votes > buy_votes:
        return Signal(action="sell", ...)
    else:
        return Signal(action="hold", ...)
```

**Change to:**
```python
def get_ensemble_signal(self, signals: dict, strategy_weights: dict = None) -> dict:
    """Weighted ensemble: use strategy weights."""
    if not strategy_weights:
        strategy_weights = {}
    
    weighted_buy = 0.0
    weighted_sell = 0.0
    
    for strategy_name, signal in signals.items():
        weight = strategy_weights.get(strategy_name, {}).get("weight", 1.0)
        
        if signal.action == "buy":
            weighted_buy += weight
        elif signal.action == "sell":
            weighted_sell += weight
    
    # Calculate net confidence based on dominance
    total_weight = weighted_buy + weighted_sell
    if total_weight == 0:
        return Signal(action="hold", confidence=0.5)
    
    confidence = abs(weighted_buy - weighted_sell) / total_weight
    
    if weighted_buy > weighted_sell:
        return Signal(action="buy", confidence=confidence, ...)
    elif weighted_sell > weighted_buy:
        return Signal(action="sell", confidence=confidence, ...)
    else:
        return Signal(action="hold", confidence=0.5, ...)
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] `get_strategy_performance()` method works
- [ ] Query returns actual performance data
- [ ] `update_weights_from_performance()` updates weights correctly
- [ ] Weights reflect win rates (higher WR = higher weight)
- [ ] `decide()` calls weight update each cycle
- [ ] Ensemble voting uses weights in calculation
- [ ] Code compiles without errors

**Test in Python REPL:**
```python
from src.learning.experience_db import ExperienceDatabase

exp_db = ExperienceDatabase()
performance = exp_db.get_strategy_performance()

for strategy, metrics in performance.items():
    print(f"{strategy}: {metrics['win_rate']}% WR, weight={metrics.get('weight', 1.0)}")
```

Should show strategies with high win rates having higher weights.

---

## DEPENDENCIES

**Depends on:** Fix #3 (real trade outcomes) - Without this, performance data is all zeros

**Enables:** Full learning feedback loop

---

## ESTIMATED TIME BREAKDOWN

- Creating get_strategy_performance() method: 30 min
- Implementing weight update logic: 20 min
- Updating decide() to call it: 10 min
- Modifying ensemble voting: 30 min
- Testing + verification: 30-40 min

**Total: 2-3 hours**

---

## EXAMPLE BEHAVIOR AFTER FIX

**Scenario:** After 20 trades:
- RSI_MeanReversion: 12 wins, 3 losses → 80% WR → weight 1.4x
- EMA_TrendFollow: 4 wins, 5 losses → 44% WR → weight 0.88x
- MACD_Momentum: 8 wins, 2 losses → 80% WR → weight 1.4x
- Bollinger_Bands: 1 win, 8 losses → 11% WR → weight 0.2x (minimum)

**Ensemble voting:**
```
Current market situation:
- RSI_MeanReversion says: BUY (1.4x weight)
- EMA_TrendFollow says: SELL (0.88x weight)
- MACD_Momentum says: BUY (1.4x weight)
- Bollinger_Bands says: SELL (0.2x weight)

Weighted votes:
- BUY: 1.4 + 1.4 = 2.8
- SELL: 0.88 + 0.2 = 1.08

Result: Signal = BUY with confidence = (2.8 - 1.08) / (2.8 + 1.08) = 44.9%
```

High win-rate strategies dominate the decision!

---

## NEXT STEP

Fix #4 COMPLETES PHASE 1. After this:
- Bot collects complete indicator data ✅
- Bot labels patterns with outcomes ✅
- Bot calculates real trade outcomes ✅
- Bot uses performance data in decisions ✅

Result: **Full learning feedback loop enabled**

Next phase (Phase 2) optimizes the decisions:
- Fix #5: Apply RAG adjustments early
- Fix #6: Extract knowledge rules
- Fix #7: Make strategy weights persistent

---

## MONITORING

After this fix, add monitoring to console:

```python
# In decide() after weight update
console.print("\n[bold cyan]Strategy Weights:[/bold cyan]")
for strategy, data in self.registry.strategies.items():
    weight = data.get("weight", 1.0)
    console.print(f"  {strategy}: {weight:.2f}x")
```

This shows the bot learning in real-time!
