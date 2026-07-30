# ENHANCED ARCHITECTURAL DESIGN
## Symbol Research Agent with Market Intelligence Integration

**Enhanced Date:** 2026-07-30  
**Status:** Ready for Implementation  
**Scope:** Daily research cycle + semantic market analysis

---

## WHAT WE'RE ADDING

### The Daily Research Trigger System
```
Scheduler: Daily at 00:00 UTC (or configurable)
  ├─ Wake up Symbol Research Agent
  ├─ Query multiple data sources simultaneously
  ├─ Analyze for XAUUSD impact
  ├─ Store semantic analysis in KB
  └─ Make available to trading agent by market open

Autonomous: No human intervention needed
Repeating: Every 24 hours automatically
```

### The Market Intelligence Pipeline
```
Raw Data Sources:
  ├─ Economic Calendar (Forex Factory, Trading Economics)
  ├─ News APIs (Newsapi, Bloomberg, Reuters)
  ├─ Central Bank statements
  ├─ Geopolitical events
  ├─ Gold-specific news
  └─ USD strength indicators

  ↓ (Semantic Analysis)

Semantic Interpreter:
  ├─ "Fed raises rates" → HIGH USD STRENGTH → SELL gold
  ├─ "Geopolitical tensions" → SAFE HAVEN → BUY gold
  ├─ "Inflation CPI hot" → RISK (could spike either direction)
  └─ "Market closed (holiday)" → AVOID trading

  ↓ (Store in KB with reasoning)

Knowledge Base Entry:
  {
    "date": "2026-07-30",
    "event": "Fed Meeting Minutes",
    "impact_direction": "BEARISH_GOLD",
    "confidence": 0.85,
    "reasoning": "Hawkish tone suggests rates stay high, USD strong",
    "risk_level": "HIGH",
    "trading_recommendation": "BIAS_SHORT | REDUCE_POSITION",
    "sources": ["Reuters", "Bloomberg"],
    "semantic_score": 0.87
  }
```

---

## DETAILED ARCHITECTURE: Symbol Research Agent v2

### Component 1: Daily Scheduler
```python
# Pseudo-code
class DailyResearchScheduler:
    def __init__(self):
        self.schedule = APScheduler()
        self.schedule.add_job(
            func=self.run_research_cycle,
            trigger="cron",
            hour=0,          # 00:00 UTC
            minute=0,
            timezone="UTC",
            id="daily_research"
        )
    
    def run_research_cycle(self):
        """Triggered daily at market open"""
        research_agent.start_async_research()
        # Returns immediately, runs in background
```

**Implementation:**
- Use APScheduler (already common in Python trading bots)
- Runs in background_process (doesn't block trading)
- Configurable via config.py
- Logs every trigger (audit trail)

---

### Component 2: Multi-Source Data Collector
```python
class MarketDataCollector:
    """Gathers data from all relevant sources"""
    
    async def collect_all(self):
        # Fetch in parallel (don't wait sequentially)
        results = await asyncio.gather(
            self.fetch_economic_calendar(),    # Forex Factory, Trading Econ
            self.fetch_news_feeds(),            # NewsAPI, Bloomberg
            self.fetch_central_bank_data(),     # ECB, Fed, BOE statements
            self.fetch_geopolitical_events(),   # GDELT, GPT analysis
            self.fetch_gold_specific_news(),    # Gold mining, supply news
            self.fetch_usd_strength(),          # DXY, USD pairs
            timeout=300  # 5-minute timeout per source
        )
        return results

    async def fetch_economic_calendar(self):
        """Get upcoming and released economic data"""
        # Forex Factory API + Trading Economics API
        return {
            "upcoming": [...],  # CPI, NFP, GDP, etc.
            "released": [...],  # Today's releases
            "forecast_vs_actual": [...]
        }

    async def fetch_news_feeds(self):
        """Aggregate financial news"""
        return {
            "bloomberg": [...],
            "reuters": [...],
            "newsapi": [...],
            "gold_specific": [...]
        }

    async def fetch_central_bank_data(self):
        """Federal Reserve, ECB, BOE statements"""
        return {
            "fed": {...},
            "ecb": {...},
            "boe": {...},
            "sentiment": "hawkish|neutral|dovish"
        }

    async def fetch_geopolitical_events(self):
        """Wars, elections, sanctions, etc."""
        # Could use GDELT API or scrape news
        return {
            "tensions": [...],
            "trade_wars": [...],
            "safe_haven_demand": float  # 0.0 to 1.0
        }

    async def fetch_gold_specific_news(self):
        """Mining, production, ETF flows"""
        return {
            "mining_news": [...],
            "etf_flows": {...},
            "supply_demand": {...}
        }

    async def fetch_usd_strength(self):
        """USD index and correlations"""
        return {
            "dxy": float,          # Dollar index
            "momentum": "up|down",
            "real_yields": float,  # Real interest rates
            "correlation_gold": float  # Historical correlation
        }
```

**Implementation:**
- Playwright: Browser automation for Forex Factory, News sites
- BeautifulSoup: Web scraping
- API clients: newsapi.org, trading-economics.com
- Async/await: All requests in parallel (5-minute total timeout)
- Error handling: If one source fails, continue with others
- Caching: Store raw data with timestamp to avoid duplicate requests

---

### Component 3: Semantic Impact Interpreter
```python
class SemanticImpactInterpreter:
    """
    Uses LLM to understand market events and their impact on XAUUSD
    
    Core question: "Does this news make gold go up or down?"
    
    Classification matrix:
    - Direction: BULLISH_GOLD, BEARISH_GOLD, NEUTRAL, CONFLICTING
    - Confidence: 0.0 to 1.0 (how sure are we?)
    - Risk Level: LOW, MEDIUM, HIGH (how volatile will it be?)
    - Recommendation: BUY, SELL, REDUCE_POSITION, AVOID, HOLD
    """
    
    def analyze_event(self, event_data: dict) -> dict:
        """
        Analyze single market event
        
        Example inputs:
          {"type": "economic", "name": "Fed raises rates to 5.5%"}
          {"type": "news", "title": "War escalates in Middle East"}
          {"type": "geopolitical", "event": "Election results"}
        """
        
        prompt = f"""
        Market Event Analysis for XAUUSD (Gold vs USD):
        
        Event: {event_data['name']}
        Type: {event_data['type']}
        Date: {event_data['date']}
        
        Analyze this event for impact on gold:
        1. Direct impact (rate-sensitive, USD-sensitive, safe haven, etc)
        2. Historical precedent (how did gold move last time this happened?)
        3. Current market state (is market already priced this in?)
        4. Confidence level (0-100%)
        5. Risk assessment (low/medium/high volatility expected?)
        6. Trading recommendation for next 24-48 hours
        7. Position sizing guidance (full size? reduced? avoid?)
        
        Return JSON:
        {{
            "direction": "BULLISH_GOLD | BEARISH_GOLD | NEUTRAL | CONFLICTING",
            "confidence": 0.75,
            "reasoning": "Clear explanation",
            "risk_level": "HIGH",
            "historical_precedent": "Similar event in [date] moved gold [X] pips",
            "recommendation": "BIAS_SHORT | REDUCE_POSITION | HOLD",
            "position_size_adjustment": 0.8,  # multiply by normal size
            "volatility_expected": "HIGH",
            "time_horizon": "24h | 48h | week"
        }}
        """
        
        response = llm.invoke(prompt)
        analysis = json.loads(response.content)
        
        return {
            **analysis,
            "source_event": event_data,
            "timestamp": datetime.now(),
            "semantic_score": self._calculate_semantic_confidence(analysis)
        }
    
    def analyze_combined(self, all_events: list[dict]) -> dict:
        """
        Analyze ALL events together (interactions matter)
        
        Example: Interest rate UP + Geopolitical tensions UP = CONFLICTING
        - Rates suggest SELL (USD strong)
        - Tensions suggest BUY (safe haven)
        - Net recommendation: HOLD, HIGH volatility expected
        """
        
        prompt = f"""
        Combined Market Analysis for XAUUSD:
        
        Today's major events:
        {json.dumps(all_events, indent=2)}
        
        Analyze the COMBINED impact:
        1. Are these events reinforcing (same direction) or conflicting?
        2. What's the net bias for gold?
        3. What's the highest confidence signal today?
        4. Are there major economic data releases? (CPI, NFP, etc - high volatility)
        5. What's the risk/reward today?
        
        Return JSON:
        {{
            "net_bias": "BULLISH_GOLD | BEARISH_GOLD | NEUTRAL | CONFLICTING",
            "confidence": 0.72,
            "primary_driver": "Description of strongest signal",
            "contradictions": ["List of conflicting signals"],
            "overall_recommendation": "BUY | SELL | REDUCE_POSITION | AVOID",
            "volatility_risk": "LOW | MEDIUM | HIGH",
            "trading_confidence": 0.65,
            "suggested_position_size": 0.5,  # fraction of normal
            "suggested_stop_loss": 50,  # pips
            "suggested_take_profit": 100,  # pips
            "market_condition_description": "Clear explanation"
        }}
        """
        
        response = llm.invoke(prompt)
        return json.loads(response.content)
    
    def _calculate_semantic_confidence(self, analysis: dict) -> float:
        """Calculate confidence score from analysis"""
        base_confidence = analysis.get("confidence", 0.5)
        
        # Adjust for conflicts
        if analysis.get("direction") == "CONFLICTING":
            base_confidence *= 0.6  # Reduce confidence for conflicting signals
        
        # Adjust for known patterns
        if "precedent" in analysis.get("historical_precedent", "").lower():
            base_confidence *= 1.1  # Boost if historical precedent exists
        
        return min(0.95, base_confidence)  # Cap at 0.95
```

**Implementation:**
- LLM prompt (Claude Opus for nuanced reasoning)
- JSON parsing
- Reasoning chain visible to user (explainability)
- Confidence scores based on: clarity + historical precedent + market state

---

### Component 4: Knowledge Base Storage with Rich Metadata
```python
class ResearchKnowledgeEntry:
    """
    Each daily research produces multiple KB entries
    """
    
    def __init__(self):
        self.entries = []
    
    def create_entry(self, analysis: dict) -> dict:
        """
        Create KB entry from semantic analysis
        
        Stored in ChromaDB (separate from trading patterns)
        """
        
        entry = {
            # Metadata
            "date": datetime.now().isoformat(),
            "research_cycle_id": str(uuid.uuid4()),
            
            # The Event
            "event_name": analysis["source_event"]["name"],
            "event_type": analysis["source_event"]["type"],
            
            # The Analysis
            "direction": analysis["direction"],
            "confidence": analysis["confidence"],
            "reasoning": analysis["reasoning"],
            "risk_level": analysis["risk_level"],
            "recommendation": analysis["recommendation"],
            
            # Actionable Intelligence
            "position_size_multiplier": analysis["position_size_adjustment"],
            "volatility_expected": analysis["volatility_expected"],
            "time_horizon": analysis["time_horizon"],
            
            # Semantic Tags (for retrieval)
            "tags": [
                f"event_type_{analysis['source_event']['type']}",
                f"direction_{analysis['direction']}",
                f"risk_{analysis['risk_level']}",
                f"volatility_{analysis['volatility_expected']}",
            ],
            
            # Embedding (for semantic search)
            "text_for_embedding": f"""
                Event: {analysis['source_event']['name']}
                Impact: {analysis['direction']}
                Reasoning: {analysis['reasoning']}
                Risk: {analysis['risk_level']}
            """,
        }
        
        # Store in ChromaDB
        self.vector_store.add(
            documents=[entry["text_for_embedding"]],
            metadatas=[entry],
            ids=[entry["research_cycle_id"]]
        )
        
        return entry
```

**Stored in:** ChromaDB (separate collection: `symbol_research_daily`)

**Retrievable by:**
- Date range
- Event type
- Direction (BULLISH/BEARISH)
- Risk level
- Confidence threshold
- Semantic similarity search

---

### Component 5: Integration with Trading Agent
```python
class TradingAgentIntegration:
    """
    How trading cycle USES today's research
    """
    
    def get_todays_research_context(self) -> dict:
        """
        Called at start of trading cycle (or when considering a trade)
        
        Returns today's market context from research
        """
        
        today_entries = self.research_kb.search_by_date(date.today())
        
        if not today_entries:
            return {"has_research": False}
        
        # Combine all today's research
        combined_analysis = self.semantic_interpreter.analyze_combined(
            [e["source_event"] for e in today_entries]
        )
        
        return {
            "has_research": True,
            "research_date": date.today(),
            "net_bias": combined_analysis["net_bias"],
            "confidence": combined_analysis["confidence"],
            "position_size_adjustment": combined_analysis["suggested_position_size"],
            "stop_loss_adjustment": combined_analysis["suggested_stop_loss"],
            "take_profit_adjustment": combined_analysis["suggested_take_profit"],
            "volatility_warning": combined_analysis["volatility_risk"],
            "recommendation": combined_analysis["overall_recommendation"],
            "reasoning": combined_analysis["market_condition_description"],
            "individual_events": today_entries,  # Raw data for detailed review
        }
    
    def apply_research_to_trade(self, trade_decision: dict, research_context: dict) -> dict:
        """
        Modify trade based on today's research
        
        Example:
          trade_decision says: "BUY 0.1 lots"
          research_context says: "CONFLICTING bias, HIGH volatility, reduce position"
          → trade_decision becomes: "BUY 0.05 lots with wider stops"
        """
        
        if not research_context.get("has_research"):
            return trade_decision  # No research today, use original decision
        
        # Check for conflicts
        trade_bias = "BUY" if trade_decision["action"] == "buy" else "SELL"
        research_bias = research_context["net_bias"]
        
        if trade_bias not in research_bias and research_context["confidence"] > 0.70:
            # Trade conflicts with research
            console.print(f"⚠️  Trade conflicts with research: {research_bias}", style="yellow")
            trade_decision["position_size"] *= 0.5  # Reduce size
            trade_decision["confidence"] *= 0.8  # Reduce confidence
        
        elif trade_bias in research_bias:
            # Trade aligns with research
            console.print(f"✅ Trade aligns with research: {research_bias}", style="green")
            trade_decision["confidence"] *= 1.1  # Boost confidence
        
        # Apply volatility adjustments
        if research_context["volatility_warning"] == "HIGH":
            trade_decision["stop_loss"] = research_context["stop_loss_adjustment"]
            trade_decision["take_profit"] = research_context["take_profit_adjustment"]
        
        # Add research metadata to trade record
        trade_decision["research_context"] = research_context
        
        return trade_decision
```

**Non-blocking:** Research context is *advisory*, not mandatory. Trading continues even without research.

---

## DAILY RESEARCH WORKFLOW DIAGRAM

```
00:00 UTC (Daily Trigger)
│
├─ 1. AWAKEN (scheduler triggers)
│
├─ 2. COLLECT DATA (async, all sources in parallel)
│   ├─ Economic calendar API
│   ├─ News feeds (NewsAPI, Reuters, Bloomberg)
│   ├─ Central bank statements
│   ├─ Geopolitical events
│   ├─ Gold-specific news
│   └─ USD strength data
│   └─ Timeout: 5 minutes
│
├─ 3. SEMANTIC ANALYSIS (LLM-powered)
│   ├─ For each event: direction, confidence, risk, recommendation
│   ├─ Combined analysis: net bias, interactions, conflicts
│   └─ Generate market condition summary
│
├─ 4. STORE IN KB (ChromaDB)
│   ├─ Individual event entries
│   ├─ Combined daily summary
│   ├─ Semantic tags for retrieval
│   └─ Timestamp and metadata
│
├─ 5. NOTIFY TRADING AGENT
│   ├─ "Research available for market open"
│   ├─ Quick summary: net bias + confidence
│   └─ Full context available on demand
│
└─ 6. SLEEP
    └─ Await next 00:00 UTC trigger

During Trading Hours:
  - Trading agent queries research context
  - Applies research to modify trade decisions
  - Research is advisory (non-blocking)
  - Trading continues regardless of research quality
```

---

## CONFIGURATION (in config.py)

```python
# Research Configuration
RESEARCH_SCHEDULER_ENABLED = True
RESEARCH_TRIGGER_HOUR = 0      # 00:00 UTC
RESEARCH_TRIGGER_MINUTE = 0
RESEARCH_TIMEOUT_SECONDS = 300  # 5 minutes

# Data Sources
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
TRADING_ECONOMICS_KEY = os.getenv("TRADING_ECONOMICS_KEY")
FOREX_FACTORY_ENABLED = True

# Analysis
SEMANTIC_ANALYSIS_MODEL = "claude-opus-4.1"  # Complex reasoning
SEMANTIC_CONFIDENCE_THRESHOLD = 0.60
POSITION_SIZE_MULTIPLIER_RANGE = (0.3, 1.3)  # 30% to 130% of normal

# Storage
RESEARCH_KB_COLLECTION = "symbol_research_daily"
RESEARCH_DATA_RETENTION_DAYS = 90

# Trading Integration
APPLY_RESEARCH_TO_TRADES = True
RESEARCH_BLOCKS_TRADING = False  # Advisory only
```

---

## INNOVATIVE ADDITIONS TO ARCHITECTURE

### 1. **Event Interaction Matrix**
```
When multiple events occur same day:
  Fed raises rates + Geopolitical tensions
  → Calculate interaction effect
  → "Rates push USD UP, tensions push USD DOWN"
  → Net effect on gold = complex
  → Warn trading agent: HIGH UNCERTAINTY
```

### 2. **Historical Pattern Library**
```
Every time research finds "X causes Y":
  Store in separate KB: "Event X caused gold move Y pips on [date]"
  
Next time Event X occurs:
  Look up historical: "Last 3 times this happened: +45 pips, -30 pips, +60 pips"
  Use as reference for confidence
```

### 3. **Real-Time News Sentiment**
```
As market opens, continuously check:
  - Stock market sentiment (S&P, DAX, etc)
  - USD pairs movement (if conflicting with overnight research)
  - Safe-haven flows (VIX, bond yields)
  
Adjust position size in real-time if sentiment shifts from overnight research
```

### 4. **Risk Event Calendar**
```
Pre-load known high-impact events:
  - FOMC meeting minutes (every 6 weeks)
  - NFP releases (first Friday of month)
  - CPI/PPI data (10th and 12th of month)
  
Prioritize analysis on these dates
Warn trading agent: "Major data release expected"
```

### 5. **Confidence Decay**
```
Research from yesterday: confidence 0.80
Research from 2 days ago: confidence 0.65
Research from 5 days ago: confidence 0.40
Research from 10+ days ago: ignore

Markets change fast - stale research has low value
```

---

## TIMELINE & IMPLEMENTATION PHASES

### Phase 1: Foundation (8-12 hours)
- ✅ Version system
- ✅ Handoff protocol
- ✅ Daily scheduler (APScheduler)
- ✅ Data collector skeleton

### Phase 2: Agent Choreography (16-20 hours)
- ✅ Tester/Developer/Trading agents enhanced
- ✅ Handoff workflow
- ✅ Research KB integration

### Phase 3: Symbol Research CORE (16-20 hours)
- ✅ Multi-source data collection
- ✅ Semantic impact interpreter (LLM)
- ✅ ChromaDB storage for daily research
- ✅ Trading agent integration

### Phase 4: Advanced Intelligence (12-16 hours)
- ✅ Event interaction analysis
- ✅ Historical pattern library
- ✅ Real-time sentiment monitoring
- ✅ Risk event calendar
- ✅ Confidence decay system

### Phase 5: Integration Testing (4-6 hours)
- ✅ Full workflow: Research → Trading → Outcome
- ✅ Verify non-blocking behavior
- ✅ Validate semantic analysis quality

---

## TOTAL EFFORT ESTIMATE

**Phases 1-5: 56-74 hours** (8-10 week sprint at 10h/week)

But broken into independent phases:
- Can deploy Phase 1-3 (~40 hours) and get value
- Phase 4 is optional optimization
- Phase 5 is validation

---

## KEY PRINCIPLES

1. **Non-blocking**: Research never blocks trading. Always advisory.
2. **Automated**: Trigger daily at 00:00 UTC without human intervention
3. **Semantic**: Use LLM to understand *meaning*, not just keywords
4. **Explainable**: Every recommendation includes clear reasoning
5. **Learnable**: Pattern library grows over time
6. **Decayable**: Old research loses influence naturally
7. **Auditable**: Every analysis logged with timestamp and source

---

## WHAT THIS ENABLES

**Without Research Agent:**
- Bot trades based on technical indicators only
- Trades during major news events blindly
- Doesn't know "NFP was hot today, USD strong"

**With Research Agent:**
- Bot knows market context before trading
- Can bias decision based on macro landscape
- Avoids trading into known high-volatility events
- Adapts position size to uncertainty
- Learns which events historically help/hurt gold
- Improves over time as historical library grows

**Result:** From 40% capability to 60%+ capability (technical only → technical + macro context)

---

**Status:** Ready to implement starting with Phase 1 (Version System + Scheduler foundation)

**Should we proceed with this design?**
