# Trading Bot — Core Rules & Mission

> **AUTHORITY NOTE (2026-08-07):** the standardised, enforced core rules now live in
> `src/core_rules.py` (portable, asserted at startup) and are summarised in `AGENTS.md`.
> Where this document calls `XAUUSDStrategy` "the primary strategy", that is STALE:
> `XAUUSDStrategy` is only the indicator-math calculator; the sole entry is
> `OsMA_Confluence` and the sole exit is `GS_PROVEN`. Defer to `src/core_rules.py`.

## 🎯 Core Mission

Build an **autonomous agentic trading bot** that:
1. Connects **directly** to MetaTrader 5 via the silicon-metatrader5 RPyC bridge
2. Places **live trades** using real-time market data (initially XAUUSD, but symbol-agnostic)
3. Learns from its mistakes via meta-strategy learning and pattern matching
4. Operates without human intervention once running
5. Uses LangGraph agent orchestration for multi-agent decision making
6. Is symbol-agnostic — works with any tradeable instrument

---

## 🏗 System Architecture

### Agent Hierarchy

```
Main Trading Bot (src/main.py)
├── Environment Setup Agent (src/agents/env_setup_agent.py)
├── Research Agent (src/agents/research_agent.py)
├── Strategy Agent (src/agents/strategy_agent.py)
├── Risk Agent (src/agents/risk_agent.py)
├── Execution Agent (src/agents/execution_agent.py)
└── Meta-Strategy Learning System (src/learning/)
    ├── MetaStrategyAgent (src/learning/meta_strategy_agent.py)
    ├── StrategyRegistry (src/learning/strategy_registry.py)
    ├── PatternMatcher (src/learning/pattern_matcher.py)
    ├── PatternVectorStore (src/learning/vector_store.py)
    ├── ExperienceDatabase (src/learning/experience_db.py)
    └── KnowledgeBase (src/learning/knowledge_base.py)
```

### Data Flow

```
MT5 Bridge (silicon-metatrader5)
    ↓ RPyC port 8001
MT5 Connector (src/mt5/connector.py)
    ↓
Data Layer (src/mt5/data.py, account.py, orders.py)
    ↓
Strategy Layer (src/strategies/xauusd_strategy.py, indicators.py)
    ↓
Agent Layer (Research → Strategy → Risk → Execution)
    ↓
Learning Layer (MetaStrategyAgent, PatternMatcher, ExperienceDB)
    ↓
Knowledge Base (stores insights, patterns, improvements)
```

---

## 🚫 Prohibited Approaches

The following are **strictly forbidden**:

| Approach | Why It's Banned |
|----------|----------------|
| **File-based MT5 data access** (reading `.hcc`, `.hst`, `.dat`, `.bin`, `.csv` files from MT5 directories) | Goes against direct API connection; MT5 doesn't write live data under Wine |
| **MQL5 Expert Advisors** for data export | Counter-intuitive — we're building a Python bot, not an MQL5 EA |
| **Batch data export** from MT5 | We need live streaming data, not batch exports |
| **Broker REST API** as primary data source | Bypasses MT5 entirely; defeats the purpose of the bridge |
| **Simulated/mocked data** for trading decisions | Only acceptable as fallback when bridge is unavailable, never for actual trade decisions |
| **Reverse-engineering binary formats** | Waste of time; MT5 doesn't write live data under Wine |
| **Temporary analysis scripts** in `/tmp/` | All analysis must run through the bridge directly |

---

## ✅ Required Approach

### MT5 Connection (THE ONLY PATH)

```
macOS Python Client
    ↓ RPyC (port 8001)
Docker Container (Wine + QEMU)
    ↓ Windows named pipes
MetaTrader5 terminal64.exe
    ↓ MT5 API
MetaQuotes Servers (live market data)
```

**Connection Rules:**
1. All MT5 communication MUST go through [`siliconmetatrader5.MetaTrader5`](venv/lib/python3.14/site-packages/siliconmetatrader5/__init__.py:21)
2. Bridge connection (`ping()`) MUST be verified before any MT5 operation
3. `initialize()` MUST use **threading timeout** (max 8 seconds) to prevent hangs
4. All MT5 API calls MUST have proper error handling
5. Bridge runs on `localhost:8001` — this is the ONLY endpoint
6. The silicon-metatrader5 client is used AS-IS from PyPI (unmodified)

### Agent System

**LangGraph Agent Rules:**
1. Each agent is a [`BaseSubAgent`](src/agents/base_agent.py:25) wrapping a LangGraph node
2. Agents communicate via shared state ([`TradingState`](src/core/graph.py:14))
3. The main agent ([`create_main_agent()`](src/core/agent.py:77)) orchestrates the workflow
4. Agent routing is defined in [`route_based_on_phase()`](src/core/graph.py:47)
5. All agents use the LLM provider system ([`get_llm()`](litellm_providers/provider_router.py:207))

**Agent Responsibilities:**
| Agent | File | Responsibility |
|-------|------|----------------|
| Environment Setup | [`env_setup_agent.py`](src/agents/env_setup_agent.py) | Check/configure environment |
| Research | [`research_agent.py`](src/agents/research_agent.py) | Market research, news analysis |
| Strategy | [`strategy_agent.py`](src/agents/strategy_agent.py) | Generate trading signals |
| Risk | [`risk_agent.py`](src/agents/risk_agent.py) | Risk assessment, position sizing |
| Execution | [`execution_agent.py`](src/agents/execution_agent.py) | Execute trades, manage positions |

### Trading Strategy System

**Strategy Rules:**
1. All strategies inherit from [`BaseStrategy`](src/strategies/base.py:76)
2. Strategies use [`indicators.py`](src/strategies/indicators.py) for technical analysis
3. The primary strategy is [`XAUUSDStrategy`](src/strategies/xauusd_strategy.py:25)
4. Strategies return [`Signal`](src/strategies/base.py:12) dataclass instances
5. Multiple strategies are registered in [`StrategyRegistry`](src/learning/strategy_registry.py:419)

### Learning System

**Learning Rules:**
1. [`MetaStrategyAgent`](src/learning/meta_strategy_agent.py:33) decides which strategy to use based on market conditions
2. [`PatternMatcher`](src/learning/pattern_matcher.py:24) finds similar historical patterns
3. [`PatternVectorStore`](src/learning/vector_store.py:62) stores pattern vectors in ChromaDB
4. [`ExperienceDatabase`](src/learning/experience_db.py:26) records all trades and outcomes
5. [`KnowledgeBase`](src/learning/knowledge_base.py:134) stores insights and research findings
6. The curiosity agent generates learning questions autonomously

---

## 🔧 Implementation Rules

### File Organization

| File | Purpose |
|------|---------|
| [`src/mt5/connector.py`](src/mt5/connector.py) | Bridge connection management, initialize() with timeout |
| [`src/mt5/data.py`](src/mt5/data.py) | Market data fetching via bridge |
| [`src/mt5/orders.py`](src/mt5/orders.py) | Order placement and management via bridge |
| [`src/mt5/account.py`](src/mt5/account.py) | Account info and positions via bridge |
| [`src/main.py`](src/main.py) | Main trading bot orchestration |
| [`src/core/graph.py`](src/core/graph.py) | LangGraph state and routing |
| [`src/core/agent.py`](src/core/agent.py) | Main agent creation |
| [`src/core/llm.py`](src/core/llm.py) | LLM provider configuration |
| [`src/core/tools.py`](src/core/tools.py) | Agent tools (shell, python, file ops) |
| [`src/agents/base_agent.py`](src/agents/base_agent.py) | Base agent class |
| [`src/strategies/`](src/strategies/) | Trading strategies and indicators |
| [`src/learning/`](src/learning/) | Learning system components |
| [`litellm_providers/`](litellm_providers/) | LLM provider routing |

### Coding Standards

1. **No temporary files** in `/tmp/` for MT5 analysis — all analysis through the bridge
2. **No file-based data sources** — the bridge is the ONLY data source
3. **Timeout all remote calls** — `initialize()` hangs under Wine, use threading timeout
4. **Keep silicon-metatrader5 client UNMODIFIED** — use as-is from PyPI
5. **All MT5 config** goes in [`connector.py`](src/mt5/connector.py)
6. **All data fetching** goes in [`data.py`](src/mt5/data.py)
7. **All order management** goes in [`orders.py`](src/mt5/orders.py)
8. **All account info** goes in [`account.py`](src/mt5/account.py)
9. **Error handling**: Use [`@mt5_error_handler`](src/mt5/connector.py:60) decorator for all MT5 functions
10. **Logging**: Use the project logger from [`src/utils/logger.py`](src/utils/logger.py)

---

## 🔄 Decision Flow

```
Bot starts (src/main.py)
    ↓
check_environment() → verify Python, dependencies, config
    ↓
setup_environment() → ensure directories, DBs exist
    ↓
build_team() → initialize all agents
    ↓
connect_mt5() → try bridge connection
    ├── ping() == True → try initialize() with 8s timeout
    │   ├── success → use MT5 API for ALL operations
    │   └── failure → log error, retry, fallback to simulation
    └── ping() == False → log error, fallback to simulation
    ↓
initialize_strategy() → load strategy registry, patterns
    ↓
run_trading_cycle() (loop):
    ├── run_research() → research agent analyzes market
    ├── run_strategy_design() → strategy agent generates signals
    ├── run_risk_check() → risk agent validates and sizes
    ├── execute_trade() → execution agent places trade
    └── reflect_and_improve() → learning system records outcome
    ↓
shutdown() → close connections, save state
```

---

## 🧪 Testing Rules

1. Test through the bridge ONLY — no local MT5 installation
2. Verify bridge is up with `ping()` before each test
3. Use `eval()` and `execute()` from silicon-metatrader5 for raw RPyC access
4. Never create analysis scripts in `/tmp/` — run analysis through the bridge
5. Test each layer independently: bridge → connector → data → strategy → agent

---

## 📚 Learning System Rules

1. Every trade outcome is recorded in [`ExperienceDatabase`](src/learning/experience_db.py)
2. Market patterns are stored in [`PatternVectorStore`](src/learning/vector_store.py) for similarity matching
3. [`MetaStrategyAgent`](src/learning/meta_strategy_agent.py) evaluates strategy performance and recommends adjustments
4. [`KnowledgeBase`](src/learning/knowledge_base.py) stores research findings and trading insights
5. The curiosity agent generates learning questions to fill knowledge gaps
6. Strategy registry is updated based on performance metrics

---

## 🚨 Error Handling Rules

1. Bridge connection failure → retry 3 times with exponential backoff
2. `initialize()` timeout → log and fallback to simulation
3. MT5 API call failure → log error, retry once, fallback to simulation
4. Agent failure → log error, skip that phase, continue cycle
5. Critical failure (no bridge, no simulation) → graceful shutdown
