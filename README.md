# Agentic Trader â€” MT5 (XAUUSD, BTCUSD, extensible)

A self-learning, multi-strategy trading system that connects to a live
**MetaTrader 5** account (VT Markets flavour), trades on a **demo account** to
accumulate real outcomes, and learns from them. It ships with a live dashboard
showing **only real data**.

> Current status: places **real orders on the demo account** in `LIVE_MICRO`
> mode (0.01 lots), reconciles closed trades against real MT5 deal history, and
> records genuine win/loss outcomes for learning. Goal: reach ~100 closed
> trades to build a statistically meaningful learning base.

---

## Quick start

```bash
# 1. Ensure MT5 terminal is running, logged into the demo account,
#    and the "Algo Trading" button is GREEN (enabled).

# 2. Start everything (dashboard + trading engine) in one command:
python app.py OBSERVE       # analyze only, no orders (safe default)
python app.py PAPER         # simulated fills at live prices
python app.py LIVE_MICRO    # REAL demo orders, 0.01 lots  â† use this to trade & learn
python app.py LIVE          # REAL orders, full sizing

# 3. Open the dashboard:
#    http://localhost:5000
```

You can also run the engine alone:

```bash
python app.py LIVE_MICRO
```

---

## Trading modes (master safety gate)

Set via `TRADING_MODE` in `.env`, or as the first CLI arg to `app.py` (the single launcher).

| Mode         | Orders?            | Learning data | Use for |
|--------------|--------------------|---------------|---------|
| `OBSERVE`    | none               | none          | Dry-run, verify signals |
| `PAPER`      | simulated @ live   | tagged PAPER  | Realistic no-risk test |
| `LIVE_MICRO` | REAL, 0.01 lots    | real outcomes | **Demo learning (recommended)** |
| `LIVE`       | REAL, full sizing  | real outcomes | Only after readiness gate |

---

## How it works

Each cycle (default every 15s), for each configured symbol:

1. **Fetch live candles** from MT5 (`XAUUSD-ECN`, `BTCUSD`, ...).
2. **Compute indicators** (OsMA, MACD, Bulls/Bears Power, EMA, ATR, RSI).
3. **Entry = OsMA_Confluence ONLY** (the single proven GoldShark rule). Trigger:
   OsMA zero-cross / anticipated / fresh momentum (sign-age within max age) on the
   CLOSED bar; MACD aligned (main-vs-signal); Bulls>0 AND Bears>0 for long / mirror
   for short; EMA side + not over-stretched; ATR active; RSI not exhausted. Signed
   per-side STRENGTH floors (osma/macd/bulls/bears, ATR-normalized) are learned per
   symbol by the optimizer + walk-forward — the core "how vigorous is buyer/seller
   activity" signal. There is NO ensemble fallback: if confluence holds, no trade.
4. **Adaptive SL/TP** sized to each symbol's spread & minimum stop distance
   (fixed points for gold; percentage-based for high-priced BTC).
5. **Place a real order** via the `BrokerAdapter` (0.01 lots in LIVE_MICRO).
6. **Track** the position by its real MT5 ticket.
7. **Reconcile on close**: match the ticket to MT5 deal history, compute the
   real net P&L, and write the true outcome (win/loss/breakeven) to the
   experience DB + pattern store â€” this is how it *actually* learns.

The **BrokerAdapter** is the single execution boundary. It:
- resolves a base symbol (`XAUUSD`) to the broker's **tradable** variant
  (`XAUUSD-ECN`, skipping the disabled `XAUUSD.crp`),
- sizes lots correctly from live `tick_value` (no gold-specific magic numbers),
- checks the **Algo Trading** terminal flag and refuses to trade (with a clear
  reason) when it's disabled,
- is symbol-agnostic, so adding crypto/other symbols is a config change.

---

## Configuration (`.env`)

```env
# MT5 (required)
MT5_ACCOUNT=1176166
MT5_PASSWORD=...
MT5_SERVER=VTMarkets-Demo

# Trading
TRADING_MODE=OBSERVE            # OBSERVE | PAPER | LIVE_MICRO | LIVE
TRADING_SYMBOLS=XAUUSD,BTCUSD   # base symbols; suffixes resolved automatically
SCALP_TARGET_TRADES=100         # learning goal
SCALP_LOT=0.01
SCALP_CYCLE_SECONDS=15

# Optional research
NEWSAPI_KEY=                    # set to enable live news (else shown "unavailable")
USE_KILO_GATEWAY=true           # API-key-free LLM for research/analysis
```

See `src/config.py` for all options.

---

## Dashboard (http://localhost:5000)

Shows **only real data**, auto-refreshing every ~4s:

- **Account & Algo Trading** â€” live balance/equity/margin + green/red Algo light
- **Trading Readiness** â€” score from real closed trades + connection + win rate
- **Learning Progress** â€” closed trades vs target, wins/losses, net P&L
- **Live Open Positions** â€” currently open trades by ticket
- **Symbols Learned** â€” per-symbol trade counts & P&L
- **Research & News** â€” news status, knowledge topics
- **Strategy Performance** â€” per-strategy win rate & P&L from real trades
- **Best Strategy per Symbol** â€” which strategy performs best where
- **Bot Trades** â€” trades the agent placed, with outcomes
- **MT5 Account Deal History** â€” live deal history straight from MT5

---

## Project layout (current)

```
langchain/
â”œâ”€â”€ app.py                       # Unified launcher (dashboard + engine)
â”œâ”€â”€ dashboard/app.py             # Dashboard (Flask, real-data endpoints + UI)
â”œâ”€â”€ src/
â”‚   â”œâ”€â”€ config.py                # Config incl. TRADING_MODE, symbols, scalp params
â”‚   â”œâ”€â”€ mt5/
â”‚   â”‚   â”œâ”€â”€ broker_adapter.py    # â† Single execution boundary (real orders, sizing, algo guard)
â”‚   â”‚   â”œâ”€â”€ connector.py         # MT5 connection
â”‚   â”‚   â”œâ”€â”€ data.py              # Live rates / prices / symbol info
â”‚   â”‚   â”œâ”€â”€ account.py           # Account, positions, deal history
â”‚   â”‚   â””â”€â”€ orders.py            # Low-level order_send helpers
â”‚   â”œâ”€â”€ trading/
â”‚   â”‚   â””â”€â”€ scalp_engine.py      # â† The real trading loop + outcome reconciliation
â”‚   â”œâ”€â”€ strategies/              # Indicator math + XAUUSD strategy
â”‚   â”œâ”€â”€ learning/                # Strategy registry, experience DB, vector store, knowledge base
â”‚   â”œâ”€â”€ data_sources/            # News / economic / central-bank sources (research)
â”‚   â”œâ”€â”€ agents/                  # LLM sub-agents (research, etc.)
â”‚   â””â”€â”€ orchestration/           # Research scheduler/orchestrator (best-effort)
â””â”€â”€ data/                        # SQLite DBs, ChromaDB, bot_status.json
```

## Key docs

- `REPAIR_PLAN.md` â€” full phased plan (what's done, what's next).
- `LEARNING_ARCHITECTURE.md` â€” how learning works vs Hermes/TradingAgents + plan to improve accuracy.
- `PHASE_1_BROKER_ADAPTER_DESIGN.md` â€” execution-layer design.
- `BACKTEST_STRATEGY.md` â€” planned no-look-ahead backtest (future phase).
- `SESSION_LOG.md` â€” build log.
