# PHASE 2, FIX #7: PERSISTENT STRATEGY WEIGHT LEARNING
## Save and restore strategy weights across sessions

**Status:** Ready to implement  
**Effort:** 2-3 hours  
**Priority:** HIGH (enables continuous learning)  
**Dependencies:** Fix #4 (weight updates)

---

## PROBLEM STATEMENT

Strategy weights are updated during a session but lost when bot restarts:

**Current behavior:**
```
Session 1 (Day 1):
  - Run 50 trades
  - RSI_MeanReversion reaches 70% win rate
  - Weight updated to 1.35x
  - Bot closed

Session 2 (Day 2):
  - Bot restarts
  - All weights reset to 1.0x
  - RSI loses learned advantage
  - Back to random strategy selection
```

**Result:** Learning lost every restart

---

## ROOT CAUSE

Strategy weights stored only in memory in StrategyRegistry:

```python
self.strategies = {
    "RSI_MeanReversion": {"weight": 1.0},  # ← In memory, not persisted
    "EMA_TrendFollow": {"weight": 1.0},
}
```

When process terminates, weights disappear.

---

## IMPLEMENTATION STEPS

### Step 1: Create strategy weights persistence table

**File:** `src/learning/experience_db.py`  
**Location:** In database schema setup

**Add table creation:**
```python
def _create_strategy_weights_table(self):
    """Create table for persisting strategy weights."""
    cursor = self.conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_weights (
            strategy_name TEXT PRIMARY KEY,
            weight REAL NOT NULL,
            win_rate REAL,
            trade_count INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    self.conn.commit()
```

### Step 2: Add persistence methods to ExperienceDatabase

**File:** `src/learning/experience_db.py`  
**Location:** Add new methods

**Add these methods:**
```python
def save_strategy_weight(self, strategy_name: str, weight: float, win_rate: float, trade_count: int):
    """Save strategy weight to persistent storage."""
    cursor = self.conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO strategy_weights
        (strategy_name, weight, win_rate, trade_count, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (strategy_name, weight, win_rate, trade_count, datetime.now().isoformat()))
    self.conn.commit()

def load_strategy_weights(self) -> dict:
    """Load persisted strategy weights."""
    cursor = self.conn.cursor()
    cursor.execute("SELECT strategy_name, weight FROM strategy_weights")
    rows = cursor.fetchall()
    
    weights = {}
    for strategy_name, weight in rows:
        weights[strategy_name] = weight
    
    logger.info(f"Loaded persisted weights for {len(weights)} strategies")
    return weights

def get_all_strategy_weights(self) -> dict:
    """Get all strategy weights with metadata."""
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT strategy_name, weight, win_rate, trade_count, updated_at
        FROM strategy_weights
        ORDER BY win_rate DESC NULLS LAST
    """)
    rows = cursor.fetchall()
    
    weights = {}
    for row in rows:
        weights[row[0]] = {
            "weight": row[1],
            "win_rate": row[2],
            "trade_count": row[3],
            "updated_at": row[4],
        }
    
    return weights
```

### Step 3: Update StrategyRegistry to use persisted weights

**File:** `src/learning/strategy_registry.py`  
**Location:** Modify initialization

**Change from:**
```python
def __init__(self, experience_db: ExperienceDatabase):
    self.exp_db = experience_db
    self.strategies = {
        "RSI_MeanReversion": {"weight": 1.0, ...},
        "EMA_TrendFollow": {"weight": 1.0, ...},
        # All others...
    }
```

**Change to:**
```python
def __init__(self, experience_db: ExperienceDatabase):
    self.exp_db = experience_db
    self.strategies = {
        "RSI_MeanReversion": {"weight": 1.0, ...},
        "EMA_TrendFollow": {"weight": 1.0, ...},
        # All others...
    }
    
    # ← ADD THIS:
    # Load persisted weights from previous sessions
    self._load_persisted_weights()

def _load_persisted_weights(self):
    """Load weights from persistent storage."""
    if not self.exp_db:
        return
    
    persisted = self.exp_db.load_strategy_weights()
    
    for strategy_name, weight in persisted.items():
        if strategy_name in self.strategies:
            self.strategies[strategy_name]["weight"] = weight
            logger.info(f"Loaded persisted weight for {strategy_name}: {weight:.2f}x")
    
    if persisted:
        logger.info(f"Restored weights for {len(persisted)} strategies from last session")
```

### Step 4: Save weights after each update

**File:** `src/learning/strategy_registry.py`  
**Location:** In `update_strategy_weight()` method

**Modify the method:**
```python
def update_strategy_weight(self, strategy_name: str, new_weight: float):
    """
    Update strategy weight.
    
    Changes are automatically persisted.
    """
    if strategy_name not in self.strategies:
        logger.error(f"Unknown strategy: {strategy_name}")
        return
    
    old_weight = self.strategies[strategy_name].get("weight", 1.0)
    self.strategies[strategy_name]["weight"] = new_weight
    
    # ← ADD THIS:
    # Save to persistent storage
    performance = self.exp_db.get_strategy_performance(strategy_name)
    if performance:
        perf = performance.get(strategy_name, {})
        self.exp_db.save_strategy_weight(
            strategy_name=strategy_name,
            weight=new_weight,
            win_rate=perf.get("win_rate"),
            trade_count=perf.get("trade_count", 0),
        )
    
    logger.info(
        f"Updated {strategy_name}: {old_weight:.2f}x → {new_weight:.2f}x "
        f"(persisted)"
    )
```

### Step 5: Display persisted weights on startup

**File:** `src/main.py`  
**Location:** In TradingBot.__init__()

**Add this:**
```python
def __init__(self):
    # ... existing code ...
    
    # ← ADD THIS:
    # Display persisted strategy weights
    self._show_persisted_weights()

def _show_persisted_weights(self):
    """Display persisted strategy weights on startup."""
    if not self.strategy_registry:
        return
    
    weights = self.strategy_registry.exp_db.get_all_strategy_weights()
    
    if weights:
        console.print("\n[bold cyan]Loaded Strategy Weights from Previous Sessions:[/bold cyan]")
        for strategy, data in weights.items():
            console.print(
                f"  {strategy}: {data['weight']:.2f}x "
                f"({data['win_rate']:.1f}% WR, {data['trade_count']} trades)"
            )
        console.print()
```

### Step 6: Add weight history tracking (optional but recommended)

**File:** `src/learning/experience_db.py`  
**Location:** Add table and method

**Add table:**
```python
def _create_weight_history_table(self):
    """Create table for tracking weight changes over time."""
    cursor = self.conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            old_weight REAL,
            new_weight REAL,
            reason TEXT,
            win_rate REAL,
            trade_count INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    self.conn.commit()
```

**Add tracking method:**
```python
def record_weight_change(self, strategy_name: str, old_weight: float, 
                        new_weight: float, reason: str = None):
    """Record a weight change for auditing."""
    cursor = self.conn.cursor()
    
    # Get current performance
    perf = self.get_strategy_performance(strategy_name)
    data = perf.get(strategy_name, {})
    
    cursor.execute("""
        INSERT INTO weight_history
        (strategy_name, old_weight, new_weight, reason, win_rate, trade_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        strategy_name,
        old_weight,
        new_weight,
        reason or "Performance-based update",
        data.get("win_rate"),
        data.get("trade_count", 0),
    ))
    self.conn.commit()
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] strategy_weights table created
- [ ] save_strategy_weight() method works
- [ ] load_strategy_weights() retrieves persisted weights
- [ ] Weights loaded on startup
- [ ] Weights saved after updates
- [ ] Bot shutdown and restart preserves weights
- [ ] Console shows loaded weights
- [ ] Code compiles without errors

**Test scenario:**
1. Run bot, record a strategy reaching 70% win rate
2. Verify weight updated to 1.35x
3. Check database: weight persisted
4. Shut down bot
5. Restart bot
6. Check console: "Loaded Strategy Weights..." shown
7. Verify weight still 1.35x (not reset to 1.0)

**SQL Query:**
```sql
SELECT strategy_name, weight, win_rate, updated_at
FROM strategy_weights
ORDER BY updated_at DESC;

-- Should show multiple records over time
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] strategy_weights table created
- [ ] save_strategy_weight() method works
- [ ] load_strategy_weights() retrieves weights
- [ ] Weights loaded on startup
- [ ] Weights saved after updates
- [ ] Bot shutdown/restart preserves weights
- [ ] Console shows loaded weights
- [ ] No errors on startup

---

## DEPENDENCIES

**Depends on:** Fix #4 (weight updates) - Must update before can persist

**Enables:** Continuous learning across sessions

---

## ESTIMATED TIME BREAKDOWN

- Create persistence table: 10 min
- Add save/load methods: 20 min
- Update StrategyRegistry: 15 min
- Integrate with startup: 15 min
- History tracking (optional): 15 min
- Testing + debugging: 30-40 min

**Total: 2-3 hours**

---

## IMPACT

**After this fix:**
- Bot learning persists across restarts
- Strategies continuously improve
- Weight history shows learning trajectory
- System truly becomes adaptive over time

**Metrics to track:**
- Average strategy weight over time
- Win rate correlation with weight changes
- Learning curve (do weights improve with more trades?)

---

## NEXT STEP

After Fix #7, Phase 2 is complete:
- ✅ Unblock learning (Phase 1: Fixes #1-4)
- ✅ Optimize decisions (Phase 2: Fixes #5-7)
- System now learns continuously
- Ready for Phase 3 enhancements

**Capability improves from 40% to 60%**
