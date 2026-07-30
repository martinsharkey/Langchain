# 🔍 DASHBOARD DATA SOURCE AUDIT

**Date:** 2026-07-30  
**Status:** Analysis Complete  
**Finding:** Mix of real and mock data - needs fixing

---

## EXECUTIVE SUMMARY

The dashboard pulls data from **REAL sources** but many tables display **EMPTY/MOCK data** because:
1. **Real Data Available:** MT5 connection, account info, live prices
2. **Missing Data:** No historical trades, no strategy performance, no knowledge entries
3. **Issue:** Dashboard shows placeholders and empty states instead of real data

---

## DATA SOURCE BREAKDOWN

### ✅ REAL DATA (Actual Live Sources)

#### 1. **MT5 Connection Status** (REAL - Lines 199-234)
```
Source: MetaTrader 5 API
Live Data: ✅ YES
Data Points:
  - Connected status (live/demo/offline)
  - Account name and server
  - Current XAUUSD price (live bid/ask)
  - Account balance
  - Account equity
  - Leverage
  - Currency
  - Server info
```

#### 2. **Trades Database** (REAL DATABASE - Lines 238-250, 324-329)
```
Source: SQLite trading_experience.db
Database: ✅ EXISTS
Problem: ⚠️ EMPTY (no trades recorded yet)
Query:
  SELECT id, timestamp, symbol, action, entry_price, stop_loss,
         take_profit, position_size, confidence, strategy_used,
         outcome, profit_loss, exit_price, exit_reason
  FROM trades
Shows: [Empty state] "No trades recorded yet"
```

#### 3. **Knowledge Base** (REAL DATABASE - Lines 283-310)
```
Source: SQLite trading_knowledge.db (or knowledge_base.db)
Database: ✅ EXISTS
Problem: ⚠️ EMPTY (no learning entries)
Queries:
  - SELECT COUNT(*) FROM knowledge_entries
  - SELECT DISTINCT topic FROM knowledge_entries
  - SELECT * FROM pending_questions
Shows: [Empty state] "No knowledge yet"
```

#### 4. **Strategy Performance** (REAL DATABASE - Lines 253-280)
```
Source: SQLite trading_experience.db
Database Table: strategy_performance
Problem: ⚠️ TABLE DOESN'T EXIST (not created)
Queries would look for:
  - strategy_name
  - total_trades
  - winning_trades
  - losing_trades
  - total_profit
  - avg_confidence
Shows: [Empty state] "No strategy data yet"
```

#### 5. **Pattern Store** (REAL CODE - Lines 312-319)
```
Source: src/learning/vector_store.PatternVectorStore
Status: ⚠️ WORKING but no data stored yet
Returns: pattern_count (currently 0)
```

---

## READINESS SCORE CALCULATION (REAL - Lines 58-183)

This IS calculated from real data sources:

```python
Score Breakdown (Total 100 points):

1. Historical Trades (30 points)           → Reads from trades DB
2. Win Rate (25 points)                    → Calculates from trades
3. Strategy Diversity (15 points)          → Checks strategy_performance table
4. Knowledge Base (15 points)              → Counts knowledge_entries
5. Pattern History (10 points)             → Counts patterns in vector store
6. Account Stability (5 points)            → Checks MT5 connection
   TOTAL = 100 points
```

**All calculations pull REAL data** but currently show:
- Trades: 0 → score 0
- Win rate: N/A → score 0  
- Strategies: 0 → score 0
- Knowledge: 0 → score 0
- Patterns: 0 → score 0
- Connection: 5 points (only real working data)

**Result:** Dashboard shows accurate ~5% readiness (only MT5 connection works)

---

## WHAT'S MISSING / MOCK DATA

### ❌ NEVER POPULATED

1. **Trades Table** 
   - Should contain: All executed trades (buy/sell)
   - Currently: Empty
   - Populated by: Trading bot execution (not implemented)

2. **Strategy Performance Table**
   - Should contain: Performance metrics per strategy
   - Currently: Table doesn't exist
   - Should be created: When first trade executes

3. **Knowledge Entries**
   - Should contain: Learned patterns and rules
   - Currently: Empty
   - Populated by: Curiosity agent learning (implemented but not running)

4. **Patterns**
   - Should contain: Trading patterns from vector store
   - Currently: 0 patterns
   - Populated by: Pattern matching during trading

---

## DATA FLOW DIAGRAM

```
REAL DATA SOURCES:
├─ MetaTrader 5 API
│  ├─ Connection status ✅ REAL
│  ├─ Account info ✅ REAL
│  ├─ XAUUSD price ✅ REAL
│  └─ Live metrics ✅ REAL
│
├─ Trading Database (SQLite)
│  ├─ Trades ⚠️ EMPTY (waiting for trades)
│  ├─ Strategy Performance ⚠️ EMPTY (waiting for trades)
│  └─ Account history ⚠️ EMPTY (waiting for trades)
│
├─ Knowledge Database (SQLite)
│  ├─ Learning entries ⚠️ EMPTY (waiting for learning)
│  ├─ Patterns ⚠️ EMPTY (waiting for patterns)
│  └─ Questions ⚠️ EMPTY (waiting for curiosity)
│
└─ Vector Store (ChromaDB)
   └─ Patterns ⚠️ EMPTY (0 patterns)

DASHBOARD DISPLAYS:
├─ Connection ✅ REAL (shows actual MT5 status)
├─ Account ✅ REAL (shows actual balance/equity)
├─ Performance ✅ REAL (calculates from empty trades)
├─ Readiness Meter ✅ REAL (but shows 5% because data empty)
├─ Trades Table ⚠️ SHOWS EMPTY STATE
├─ Strategy Table ⚠️ SHOWS EMPTY STATE
└─ Knowledge Table ⚠️ SHOWS EMPTY STATE
```

---

## WHAT NEEDS TO BE FIXED

### Priority 1: Database Schema (CRITICAL)

The `strategy_performance` table is queried but never created:

```python
# Currently queries a table that doesn't exist:
SELECT strategy_name, total_trades, winning_trades, losing_trades
FROM strategy_performance  # ← THIS TABLE DOESN'T EXIST
```

**Fix:** Create table definition or modify query

### Priority 2: Trade Execution Integration

Dashboard expects trades table to be populated by:
- Trading bot executing real trades
- Storing results in `trading_experience.db`

**Current state:** Trading bot exists but no integration to record trades

### Priority 3: Learning System Integration

Dashboard expects knowledge entries but:
- Curiosity agent is implemented but not integrated
- Knowledge base is created but not populated

**Current state:** Learning system exists but not connected

---

## RECOMMENDED CHANGES

### Option A: Show Only Real Data (RECOMMENDED)
Remove sections that display empty data:
```
Keep:
  ✅ MT5 Connection Badge (real)
  ✅ Account Info (real)
  ✅ Live XAUUSD Price (real)
  ✅ Readiness Meter (real calculation)

Remove:
  ❌ Recent Trades table (empty)
  ❌ Strategy Performance (empty)
  ❌ Knowledge Base table (empty)
```

### Option B: Add Sample/Mock Data
Populate databases with test data for demonstration:
```
- Add 10-20 sample trades
- Add sample strategy performance
- Add sample knowledge entries
```

### Option C: Implement Full Integration
Connect all systems:
- Enable trading execution
- Store actual trades
- Populate learning system
- Run full pipeline

---

## CURRENT DATA STATUS

| Component | Source | Real? | Status |
|-----------|--------|-------|--------|
| **MT5 Connection** | MetaTrader 5 API | ✅ YES | ✅ Working |
| **Account Balance** | MT5 API | ✅ YES | ✅ Real data |
| **Account Equity** | MT5 API | ✅ YES | ✅ Real data |
| **XAUUSD Price** | MT5 API | ✅ YES | ✅ Live data |
| **Leverage** | MT5 API | ✅ YES | ✅ Real data |
| **Currency** | MT5 API | ✅ YES | ✅ Real data |
| **Trades** | SQLite DB | ✅ YES | ⚠️ Empty |
| **Strategy Performance** | SQLite DB | ✅ YES | ⚠️ Table missing |
| **Knowledge Entries** | SQLite DB | ✅ YES | ⚠️ Empty |
| **Patterns** | ChromaDB | ✅ YES | ⚠️ Empty |
| **Readiness Score** | Calculation | ✅ YES | ✅ Accurate (5%) |

---

## CONCLUSION

**The dashboard is NOT showing fake data.**

It's showing:
- ✅ **Real data** from MT5 API (connection, account, price)
- ✅ **Real calculations** (readiness score from actual metrics)
- ⚠️ **Empty states** for features not yet implemented (trades, learning)

**The dashboard is honest** - it shows what data actually exists.

---

## NEXT STEPS

Choose one approach:

### Approach 1: Clean Dashboard (Show only working data)
- Remove empty trade/strategy/knowledge tables
- Keep MT5 connection and account info
- Focus on readiness score

### Approach 2: Mock Data for Demo
- Populate databases with sample data
- Showcase full dashboard features
- Clear labels: "SAMPLE DATA"

### Approach 3: Full Integration
- Connect trading system
- Enable learning
- Populate all tables with real data

**Recommendation:** Start with Approach 1 (clean dashboard with real data only), then add Approach 2 (mock data) for demonstration.

---

Generated: 2026-07-30 13:32 UTC+1
