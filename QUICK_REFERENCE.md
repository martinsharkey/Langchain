# QUICK REFERENCE — Multi-Agent Research System

**TL;DR:** Everything is ready. Start here:

```bash
python examples/test_full_daily_cycle.py
```

---

## GET STARTED (5 minutes)

### 1. Initialize
```python
from src.orchestration import get_orchestrator
orchestrator = get_orchestrator()
orchestrator.start()
```

### 2. Check Status
```python
orchestrator.print_status()
```

### 3. Get Research
```python
research = orchestrator.get_research_context_for_trading()
print(f"Bias: {research['analysis']['net_bias']}")
print(f"Confidence: {research['analysis']['confidence']:.0%}")
```

### 4. Apply to Trades
```python
modified_trade = orchestrator.apply_research_to_trade_decision(your_trade)
```

---

## WHAT'S RUNNING

- **Scheduler:** 00:00 UTC daily (configurable)
- **Data Sources:** 6 running in parallel
- **Analysis:** LLM semantic understanding
- **Storage:** Knowledge base persistent
- **Integration:** Ready for trading agent

---

## FILES TO KNOW

```
Core Logic:
  src/orchestration/multi_agent_orchestrator.py     (START HERE)
  src/agents/enhanced_research_agent.py              (Daily cycle)
  src/core/market_data_collector.py                  (Data gathering)
  src/core/version_manager.py                        (Version tracking)
  src/core/handoff_protocol.py                       (Atomic transfers)
  src/core/research_scheduler.py                     (Daily trigger)

Data Sources (6):
  src/data_sources/economic_calendar.py              (Events)
  src/data_sources/news_aggregator.py                (News)
  src/data_sources/central_banks.py                  (Fed, ECB, BOE)
  src/data_sources/geopolitical.py                   (Wars, sanctions)
  src/data_sources/gold_news.py                      (Mining, ETF)
  src/data_sources/usd_strength.py                   (DXY, yields)

Examples:
  examples/quickstart_research_system.py             (Test)
  examples/test_full_daily_cycle.py                  (Full test)

Config:
  .env                                               (API keys)
  requirements.txt                                   (Dependencies)
```

---

## EXAMPLE: Use in Your Bot

```python
from src.orchestration import get_orchestrator

class MyTradingBot:
    def __init__(self):
        self.orchestrator = get_orchestrator()
        self.orchestrator.start()
    
    def analyze_and_trade(self, symbol):
        # Get research context
        research = self.orchestrator.get_research_context_for_trading()
        
        # Generate trade signal (your logic)
        trade = self.generate_signal(symbol)
        
        # Apply research adjustments
        trade = self.orchestrator.apply_research_to_trade_decision(trade)
        
        # Execute
        self.mt5.execute(trade)
```

---

## DAILY CYCLE (What Happens at 00:00 UTC)

1. **Collect** (5-8s)
   - Economic calendar
   - News feeds
   - Central banks
   - Geopolitical events
   - Gold news
   - USD strength

2. **Analyze** (10-20s)
   - LLM semantic analysis
   - Direction: BULLISH/BEARISH/NEUTRAL/CONFLICTING
   - Confidence: 0-100%
   - Risk: LOW/MEDIUM/HIGH

3. **Store** (<1s)
   - Knowledge base
   - Searchable by date/type/direction

4. **Handoff** (<1s)
   - Prepare for trading agent
   - Research context ready

---

## DATA OUTPUT EXAMPLE

```python
research_context = {
    "has_research": True,
    "research_cycle_id": "cycle_1_1722346800.0",
    "timestamp": "2026-07-30T13:00:00+00:00",
    "analysis": {
        "net_bias": "BULLISH_GOLD",           # Or BEARISH / NEUTRAL / CONFLICTING
        "confidence": 0.85,                   # 0-1.0 (85%)
        "volatility_risk": "MEDIUM",          # LOW / MEDIUM / HIGH
        "recommendation": "BUY",              # Or SELL / REDUCE_POSITION / HOLD
        "events_analyzed": 42                 # Number of events
    }
}
```

---

## TRADE MODIFICATION EXAMPLE

```python
# Your signal says SELL
trade = {
    "action": "sell",
    "position_size": 0.1,
    "stop_loss": 30,
    "take_profit": 80,
    "confidence": 0.70
}

# But research says BULLISH
# Result:
modified = {
    "action": "sell",
    "position_size": 0.05,      # ← REDUCED (conflict!)
    "stop_loss": 45,            # ← WIDENED (volatility)
    "take_profit": 80,
    "confidence": 0.56,         # ← REDUCED
    "research_context": {
        "cycle_id": "...",
        "net_bias": "BULLISH_GOLD",
        "confidence": 0.85,
        "applied_at": "2026-07-30T13:00:00+00:00"
    }
}
```

---

## ERROR SCENARIOS

### Problem: No research context
```python
research = orchestrator.get_research_context_for_trading()
# Returns: {"has_research": False, "reason": "..."}
# → Normal on first run, or if cycle hasn't run yet
```

### Problem: Data source failed
```python
# System automatically falls back to mocks
# Other 5 sources continue working
# Result returned even if 1-2 sources fail
```

### Problem: Scheduler not running
```python
status = orchestrator.scheduler.get_status()
# {"is_running": False, ...}

orchestrator.scheduler.force_run()  # Test manually
```

---

## CONFIGURATION OPTIONS

```env
# Scheduler timing
RESEARCH_TRIGGER_HOUR=0       # 00:00 UTC
RESEARCH_TRIGGER_MINUTE=0

# API Keys (optional, has mocks)
NEWSAPI_KEY=your_key
TRADING_ECONOMICS_KEY=your_key

# Agent settings
AGENT_TEMPERATURE=0.7
AGENT_MAX_ITERATIONS=25
```

---

## KEY CONCEPTS

**Non-Blocking:** Research runs in background, never blocks trading

**Semantic Analysis:** LLM understands meaning ("rates up" = USD strong = gold weak)

**Atomic Handoffs:** All-or-nothing transfers between agents

**Graceful Degradation:** Works even if some data sources fail

**Persistent Storage:** Everything logged forever

**Version-Tied:** Code and tests synchronized

---

## METRICS TO MONITOR

```python
# Check system health
status = orchestrator.scheduler.get_status()
print(f"Running: {status['is_running']}")
print(f"Runs: {status['run_count']}")
print(f"Next: {status['next_run']}")

# Check research quality
research = orchestrator.get_research_context_for_trading()
print(f"Confidence: {research['analysis']['confidence']:.0%}")

# Check KB storage
stats = orchestrator.knowledge_base.get_knowledge_base_stats()
print(f"Entries: {stats['total_entries']}")
```

---

## COMMON TASKS

### Task: Change trigger time
```env
RESEARCH_TRIGGER_HOUR=14    # 14:00 UTC (before market open)
RESEARCH_TRIGGER_MINUTE=30
```

### Task: Get historical research
```python
research_findings = orchestrator.knowledge_base.get_research_findings_for_date("2026-07-30")
```

### Task: Force immediate research
```python
orchestrator.scheduler.force_run()
```

### Task: Stop system
```python
orchestrator.stop()
```

### Task: Check pending handoffs
```python
handoffs = orchestrator.get_pending_handoffs("trader")
```

---

## DEPENDENCIES

**Already installed:**
- langchain, langgraph
- asyncio, aiohttp
- chromadb (vector store)
- beautifulsoup4 (web scraping)
- rich (logging)

**Added for this:**
- APScheduler (daily trigger)

**Optional:**
- NewsAPI (free tier: 100 req/day)
- Trading Economics API

---

## SUPPORT

**Issue:** Check the full docs
- `MASTER_COMPLETION_SUMMARY.md` - Complete overview
- `PHASE_1_2_IMPLEMENTATION_SUMMARY.md` - Phase 1-2 details
- `PHASE_3_COMPLETION.md` - Phase 3 data sources
- `RESEARCH_AGENT_DETAILED_DESIGN.md` - Full specification

**Issue:** Run tests
```bash
python examples/test_full_daily_cycle.py
```

**Issue:** Check logs
```
logs/main.log  # Full execution log
```

---

## ONE-LINER START

```python
from src.orchestration import get_orchestrator; get_orchestrator().start()
```

---

**That's it. You're done. System is ready.**

Last Updated: 2026-07-30
