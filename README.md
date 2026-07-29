# 🤖 LangChain ReAct Agent — XAUUSD MetaTrader 5 Trading Bot

An autonomous **LangChain ReAct agent** powered by **Groq's free Llama 3 70B API** that builds its own team of sub-agents to trade **XAUUSD (Gold vs USD)** on **MetaTrader 5**.

## 🎯 Mission

> *"Build the most intelligent team of AI agents to trade XAUUSD using MetaTrader 5."*

The agent:
1. **Builds its environment** — Creates venv, installs dependencies
2. **Recruits a team** — Spawns specialized sub-agents (Research, Strategy, Risk, Execution)
3. **Analyzes markets** — Fetches XAUUSD data, calculates technical indicators
4. **Designs strategies** — Creates and backtests trading strategies
5. **Executes trades** — Places orders on MT5 with proper risk management
6. **Self-improves** — Reflects on performance and adjusts strategy

## 🏗️ Architecture

```
src/
├── main.py                    # Entry point — boots the main agent
├── config.py                  # Configuration (symbols, timeframes, API keys)
├── core/
│   ├── agent.py               # Main ReAct agent (LangGraph)
│   ├── graph.py               # State graph definition
│   ├── tools.py               # Shared tool definitions
│   └── llm.py                 # Groq LLM client
├── agents/
│   ├── base_agent.py          # Base sub-agent class
│   ├── env_setup_agent.py     # Environment setup specialist
│   ├── research_agent.py      # Market research specialist
│   ├── strategy_agent.py      # Strategy design specialist
│   ├── risk_agent.py          # Risk management specialist
│   └── execution_agent.py     # Order execution specialist
├── mt5/
│   ├── connector.py           # MT5 connection (Wine bridge on macOS)
│   ├── account.py             # Account info & positions
│   ├── data.py                # Market data (OHLCV, ticks)
│   └── orders.py              # Order placement & management
├── strategies/
│   ├── base.py                # Base strategy class
│   ├── indicators.py          # Technical indicators (EMA, RSI, MACD, etc.)
│   └── xauusd_strategy.py     # XAUUSD-specific strategy
└── utils/
    ├── logger.py              # Rich console logging
    └── helpers.py             # Utility functions
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.10+** installed
2. **Groq API key** (free) — sign up at [console.groq.com](https://console.groq.com)
3. **MetaTrader 5** running under Wine (macOS) or natively (Windows)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/martinsharkey/langchain.git
cd langchain

# 2. Run the setup script (creates venv, installs deps)
chmod +x setup.sh
./setup.sh

# 3. Edit the .env file with your API keys
nano .env

# 4. Run the bot
python src/main.py
```

### Environment Variables (`.env`)

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Your Groq API key (free at console.groq.com) | ✅ Yes |
| `MT5_ACCOUNT` | MetaTrader 5 account number | Optional |
| `MT5_PASSWORD` | MetaTrader 5 password | Optional |
| `MT5_SERVER` | MetaTrader 5 broker server | Optional |
| `XAUUSD_RISK_PERCENT` | Risk per trade (default: 1.0) | Optional |
| `XAUUSD_MAX_POSITION_SIZE` | Max position size (default: 0.1) | Optional |

## 🤖 Agent Team

| Agent | Role | Tools |
|-------|------|-------|
| **Orchestrator** (main) | Leads the team, delegates tasks | Shell, Python, File I/O |
| **Environment Setup** | Creates venv, installs deps | Shell, File I/O |
| **Research** | Analyzes market data, identifies patterns | Python, Data analysis |
| **Strategy** | Designs & backtests strategies | Python, Backtesting |
| **Risk Management** | Calculates position sizing, SL/TP | Python, Calculations |
| **Execution** | Places & manages MT5 orders | Python, MT5 bridge |

## 📊 Trading Strategy

The default strategy combines multiple technical indicators for XAUUSD:

- **EMA Crossover** (9/21) — Trend direction
- **RSI** (14) — Momentum and overbought/oversold
- **MACD** (12/26/9) — Trend confirmation
- **Bollinger Bands** (20, 2σ) — Volatility context
- **ATR** (14) — Volatility-based SL/TP
- **Support/Resistance** — Key price levels

### Risk Management
- 1% risk per trade (configurable)
- Minimum 1:2 risk-reward ratio
- ATR-based stop loss placement
- Maximum 2 concurrent positions

## 🖥️ macOS + Wine Setup

Since `MetaTrader5` is a Windows-native Python package, on macOS you need:

1. Install Wine: `brew install --cask wine-stable`
2. Install MetaTrader 5 under Wine
3. The bot will automatically detect and handle the Wine bridge

**Without MT5**, the bot runs in **simulation mode** with generated data — perfect for testing!

## 💰 Costs

**Completely free to run:**
- **Groq API**: Free tier (30 req/min, 6M tokens/day, Llama 3 70B)
- **No paid API keys required**
- **Open-source** — all code is MIT licensed

## 🔄 Trading Cycle

```
1. Research → Fetch data, calculate indicators, analyze market
2. Strategy → Generate signals, evaluate opportunities
3. Risk Check → Calculate position size, validate risk parameters
4. Execute → Place order on MT5 with SL/TP
5. Reflect → Analyze performance, adjust strategy
```

## 🛠️ Development

```bash
# Activate venv
source venv/bin/activate

# Run tests
pytest tests/

# Run a single cycle (no trading)
python -c "from src.strategies.xauusd_strategy import XAUUSDStrategy; s = XAUUSDStrategy(); print('Strategy ready')"
```

## ⚠️ Disclaimer

**This software is for educational and research purposes only.** Trading financial markets involves substantial risk of loss. Past performance does not guarantee future results. Always test strategies in a demo account before trading with real money.

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.
