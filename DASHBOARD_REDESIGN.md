# Dashboard Redesign: Complete Architecture

## Vision
A modern, analytics-focused trading dashboard that makes strategy performance, backtest results, and Optuna optimization visible at a glance. Focus: **data-driven insights, not raw metrics**.

## New Architecture

### Tech Stack
- **Backend**: Flask (keep existing) + FastAPI websocket layer (new)
- **Frontend**: React 18 + TypeScript
- **State Management**: Redux Toolkit
- **Charts**: Chart.js v4 + Recharts (interactive, real-time)
- **Real-time**: WebSocket (Socket.io or native WS)
- **Styling**: Tailwind CSS + Headless UI components
- **Build**: Vite + pnpm

### Data Model

```typescript
// Core domain models
interface Strategy {
  name: string
  symbol: string
  enabled: boolean
  rank: number
  
  // Backtest results
  backtest: {
    profitFactor: number
    winRate: number
    sharpeRatio: number
    maxDrawdown: number
    validatedAt: ISO8601
    walkForwardResults: WalkForwardWindow[]
  }
  
  // Live performance
  live: {
    trades: number
    winRate: number
    profitFactor: number
    netPnL: number
    lastTrade: ISO8601
  }
  
  // Vectorbt discovery
  vectorbtMetrics?: {
    regimeEdge: Record<string, number>
    discoveredAt: ISO8601
    validated: boolean
  }
  
  // Optuna optimization
  optuna?: {
    studyName: string
    trials: number
    bestValue: number
    bestParams: Record<string, any>
    improvementTrend: number[]
    lastOptimized: ISO8601
  }
}

interface WalkForwardWindow {
  window: number
  profitFactor: number
  winRate: number
  trades: number
  sharpe: number
}

interface OptunaTrial {
  trialId: number
  params: Record<string, any>
  value: number
  state: 'RUNNING' | 'COMPLETE' | 'PRUNED' | 'FAIL'
  timestamp: ISO8601
}
```

### Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Header: Status Bar | Mode Selector | Alerts | Settings     │
├─────────────────────────────────────────────────────────────┤
│  
│  MAIN CONTENT:
│  ┌───────────────────────────────────────────────────────┐
│  │ Strategy Performance Overview (hero section)          │
│  │ ┌─────────┬─────────┬─────────┬─────────┐            │
│  │ │ Best    │ Most    │ Worst   │ Win %   │            │
│  │ │ Strategy│ Traded  │ Strategy│ Average │            │
│  │ └─────────┴─────────┴─────────┴─────────┘            │
│  └───────────────────────────────────────────────────────┘
│
│  Navigation Tabs:
│  ┌─────────────────────────────────────────────────────┐
│  │ [Strategies] [Backtest] [Optimization] [Live] [Settings]
│  └─────────────────────────────────────────────────────┘
│
│  TAB 1: STRATEGIES
│  ┌──────────────────────────────────────────────────────┐
│  │ [Search/Filter]                      [Add] [Export]  │
│  ├──────────────────────────────────────────────────────┤
│  │                                                       │
│  │  Strategy Comparison Grid:                          │
│  │  ┌────────────────────────────────────────────────┐  │
│  │  │ STRATEGY NAME  │ PF  │ WR  │ SHARPE │ TRADES   │  │
│  │  │ ─────────────────────────────────────────────  │  │
│  │  │ OsMA_Confluence     1.45  52%  0.82    156     │  │
│  │  │ Bollinger_OsMA      1.18  59%  0.71    213     │  │
│  │  │ Volume_Breakout     1.15  48%  0.65     89     │  │
│  │  │                                                  │  │
│  │  │ [Click row for detailed view →]                │  │
│  │  └────────────────────────────────────────────────┘  │
│  │                                                       │
│  │  Right panel: Selected strategy detail               │
│  │  ┌────────────────────────────────────────────────┐  │
│  │  │ OsMA_Confluence                                │  │
│  │  │                                                │  │
│  │  │ Backtest (M15):                               │  │
│  │  │   PF: 1.45 | WR: 52% | Sharpe: 0.82          │  │
│  │  │   Walk-forward validation: GENERALIZES ✓     │  │
│  │  │                                                │  │
│  │  │ Live Performance:                              │  │
│  │  │   Trades: 156 | WR: 52% | P&L: +$2,340        │  │
│  │  │                                                │  │
│  │  │ Per-Regime Edge:                               │  │
│  │  │   Trending: 1.30x | Volatile: 1.15x           │  │
│  │  │   Ranging: 0.90x  | Quiet: 0.85x              │  │
│  │  │                                                │  │
│  │  │ Optuna Tuning:                                 │  │
│  │  │   Study: xauusd_osma_confluence_v2             │  │
│  │  │   Trials: 124/500 | Best: 1.52                │  │
│  │  │   Improvement: ↑ 4.8%                         │  │
│  │  │                                                │  │
│  │  └────────────────────────────────────────────────┘  │
│  │                                                       │
│  └──────────────────────────────────────────────────────┘
│
│  TAB 2: BACKTEST RESULTS
│  ┌──────────────────────────────────────────────────────┐
│  │ Backtest Suite Analysis                              │
│  │ Filter: [Symbol ▼] [TimeFrame ▼] [Date Range ▼]    │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Walk-Forward Validation Results (3 windows)    │  │
│  │ │                                                 │  │
│  │ │  Window 1 (60%):   PF 1.30  WR 51%  R 45      │  │
│  │ │  Window 2 (20%):   PF 1.25  WR 52%  R 12      │  │
│  │ │  Window 3 (20%):   PF 1.40  WR 53%  R 18      │  │
│  │ │  ──────────────────────────────────────────   │  │
│  │ │  GENERALIZES:      ✓ YES                      │  │
│  │ │  Min-window PF:    1.25 (robust)              │  │
│  │ │                                                 │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Performance Curve (Equity)                      │  │
│  │ │ [Chart.js line chart with interactive tooltips] │  │
│  │ │                                                 │  │
│  │ │  Y: Cumulative P&L | X: Bar/Trade sequence     │  │
│  │ │  [Can zoom, pan, hover for trade details]      │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Metrics Breakdown                               │  │
│  │ │ • Profit Factor: 1.32 (≥1.15 ✓)               │  │
│  │ │ • Win Rate: 52% (>50% ✓)                       │  │
│  │ │ • Average Win: $124 | Average Loss: $93        │  │
│  │ │ • Max Drawdown: 8.2% | Sharpe: 0.82           │  │
│  │ │ • Consecutive Wins: 7 | Consecutive Losses: 5 │  │
│  │ │                                                 │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  └──────────────────────────────────────────────────────┘
│
│  TAB 3: OPTIMIZATION (Optuna + Live)
│  ┌──────────────────────────────────────────────────────┐
│  │ Optuna Tuning Progress                               │
│  │                                                       │
│  │ ┌──────────────────┬─────────────────────────────┐  │
│  │ │ Study Selection  │ Study: xauusd_osma_v2      │  │
│  │ │ [xauusd_osma_v2] │ Trials: 124/500            │  │
│  │ │ [btcusd_bb_v1]   │ Best Value: 1.52           │  │
│  │ │ [ger40_osma_v1]  │ Status: RUNNING            │  │
│  │ │                  │                             │  │
│  │ │                  │ Parameter Space:            │  │
│  │ │                  │ osma_fast: [9, 15]          │  │
│  │ │                  │ osma_slow: [20, 32]         │  │
│  │ │                  │ signal_period: [5, 12]      │  │
│  │ │                  │ min_strength: [0.3, 0.8]    │  │
│  │ │                  │                             │  │
│  │ │                  │ [Pause] [Resume] [Export]   │  │
│  │ └──────────────────┴─────────────────────────────┘  │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Optimization Progress Chart                     │  │
│  │ │                                                 │  │
│  │ │  [Recharts dual-axis chart]                    │  │
│  │ │  Left Y: Best Value Over Time                  │  │
│  │ │  Right Y: Trial Count                          │  │
│  │ │                                                 │  │
│  │ │  Shows convergence trend, improvement rate     │  │
│  │ │                                                 │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Recent Trials (Top 10)                          │  │
│  │ │                                                 │  │
│  │ │ Trial │ PF    │ WR   │ Sharpe │ osma_f │ State │  │
│  │ │ ─────────────────────────────────────────────│  │  │
│  │ │ 124   │ 1.52* │ 54%  │ 0.88   │ 12     │ ✓    │  │
│  │ │ 123   │ 1.48  │ 53%  │ 0.85   │ 11     │ ✓    │  │
│  │ │ 122   │ 1.35  │ 51%  │ 0.78   │ 13     │ ✓    │  │
│  │ │ ...                                            │  │
│  │ │ [Load more →]                                  │  │
│  │ │                                                 │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  └──────────────────────────────────────────────────────┘
│
│  TAB 4: LIVE TRADING
│  ┌──────────────────────────────────────────────────────┐
│  │ Real-time Account State                              │
│  │                                                       │
│  │ ┌─────────────┬────────────┬──────────┬─────────┐   │
│  │ │ Balance     │ Equity     │ Open P&L │ Mode    │   │
│  │ │ $10,240     │ $10,580    │ +$340    │ LIVE    │   │
│  │ └─────────────┴────────────┴──────────┴─────────┘   │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Open Positions                                  │  │
│  │ │ ┌─────────────────────────────────────────────┐ │  │
│  │ │ │ SYMBOL │ SIDE │ ENTRY │ SL   │ TP  │ STRAT │ │  │
│  │ │ │ XAUUSD │ BUY  │ 2610  │ 2595 │2630 │ OsMA  │ │  │
│  │ │ │ BTCUSD │ SELL │ 42300 │42500 │42100│ BB    │ │  │
│  │ │ └─────────────────────────────────────────────┘ │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  │ ┌─────────────────────────────────────────────────┐  │
│  │ │ Recent Trades (Last 20)                         │  │
│  │ │ ┌─────────────────────────────────────────────┐ │  │
│  │ │ │ TIME │ SYMBOL │ STRAT │ ENTRY │ EXIT │ P&L  │ │  │
│  │ │ │ 10:45│ XAUUSD │ OsMA  │ 2605  │ 2620 │ +15  │ │  │
│  │ │ │ 10:30│ BTCUSD │ BB    │ 42100 │ 42200│ +100 │ │  │
│  │ │ │ ...                                          │ │  │
│  │ │ └─────────────────────────────────────────────┘ │  │
│  │ └─────────────────────────────────────────────────┘  │
│  │                                                       │
│  └──────────────────────────────────────────────────────┘
│
│  TAB 5: VECTORBT DISCOVERY
│  ┌──────────────────────────────────────────────────────┐
│  │ Edge Discovery Analysis                              │
│  │                                                       │
│  │ Last Sweep: 2026-08-24 10:00 UTC                    │
│  │ Validation: OsMA_Confluence (R1 constraint)          │
│  │                                                       │
│  │ ┌──────────────────────────────────────────────────┐ │
│  │ │ Per-Symbol Discovery Status                     │ │
│  │ │                                                  │ │
│  │ │ XAUUSD:                                         │ │
│  │ │   ✓ Validated | Pockets: 2 (trending, volatile)│ │
│  │ │   PF: 1.45 | WR: 52% | Ready to trade         │ │
│  │ │   Regimes: trending (1.30x), volatile (1.15x)  │ │
│  │ │                                                  │ │
│  │ │ BTCUSD:                                         │ │
│  │ │   ⚠ Limited | Pockets: 1 (volatile only)       │ │
│  │ │   PF: 1.18 | WR: 59% | Gathering data         │ │
│  │ │   Needs: trending validation (only 12 samples) │ │
│  │ │                                                  │ │
│  │ │ GER40:                                          │ │
│  │ │   ✗ Not yet validated | Pockets: 0             │ │
│  │ │   Collecting baseline data...                  │ │
│  │ │                                                  │ │
│  │ └──────────────────────────────────────────────────┘ │
│  │                                                       │
│  │ ┌──────────────────────────────────────────────────┐ │
│  │ │ Regime Edge Distribution (All Symbols)          │ │
│  │ │                                                  │ │
│  │ │ [Stacked bar chart by regime]                  │ │
│  │ │  Trending: XAUUSD(1.30x), BTCUSD(0.8x), ...   │ │
│  │ │  Volatile: XAUUSD(1.15x), BTCUSD(1.12x), ...  │ │
│  │ │  Ranging:  ...                                 │ │
│  │ │  Quiet:    ...                                 │ │
│  │ │                                                  │ │
│  │ └──────────────────────────────────────────────────┘ │
│  │                                                       │
│  └──────────────────────────────────────────────────────┘
│
└─────────────────────────────────────────────────────────────┘
```

## Backend Changes

### New API Endpoints (FastAPI)

```python
# Strategy Analytics
GET  /api/v2/strategies                    # List all with backtest + live metrics
GET  /api/v2/strategies/{name}             # Detailed strategy view
GET  /api/v2/strategies/{name}/backtest    # Walk-forward results
GET  /api/v2/strategies/{name}/live        # Live performance
GET  /api/v2/strategies/{name}/vectorbt    # Vectorbt discovery metrics

# Backtest Analysis
GET  /api/v2/backtest/results              # List recent backtests
GET  /api/v2/backtest/{id}                 # Detailed backtest
GET  /api/v2/backtest/{id}/equity          # Equity curve data
GET  /api/v2/backtest/{id}/trades          # Individual trades

# Optuna Optimization
GET  /api/v2/optuna/studies                # List active studies
GET  /api/v2/optuna/studies/{name}         # Study detail + trials
GET  /api/v2/optuna/studies/{name}/trials  # Paginated trials
GET  /api/v2/optuna/studies/{name}/progress # Improvement over time

# Vectorbt Discovery
GET  /api/v2/vectorbt/sweeps               # Recent discovery sweeps
GET  /api/v2/vectorbt/sweeps/{id}          # Sweep results by symbol
GET  /api/v2/vectorbt/regime-edges         # All regime edges

# Live Account
GET  /api/v2/account/status                # Account state (balance, equity, mode)
GET  /api/v2/account/positions             # Open positions
GET  /api/v2/account/trades                # Recent closed trades
GET  /api/v2/account/symbols               # Symbol status

# Control (existing, but updated)
POST /api/v2/control/mode                  # Change mode
POST /api/v2/control/pause-symbol          # Pause trading
POST /api/v2/control/resume-symbol         # Resume trading

# WebSocket
WS   /ws/live                              # Real-time updates stream
    • account.balance_update
    • account.position_filled
    • account.position_closed
    • trade.completed
    • strategy.update
    • optuna.trial_complete
```

## Frontend Components (React)

```typescript
// Main pages
StrategyDashboard.tsx        // Tab 1: Strategy comparison
BacktestResultsPage.tsx      // Tab 2: Backtest analysis
OptimizationDashboard.tsx    // Tab 3: Optuna tracking
LiveTradingPage.tsx          // Tab 4: Account state
VectorbtDiscoveryPage.tsx    // Tab 5: Edge discovery

// Reusable components
StrategyCard.tsx             // Summary card for one strategy
WalkForwardChart.tsx         // 3-window validation visualization
EquityCurve.tsx              // Interactive equity chart
OptimizationProgress.tsx     // Trial progress + convergence
TrialsTable.tsx              // Paginated trials with sorting
PerformanceMetrics.tsx       // PF, WR, Sharpe badge display
ParameterOptimizer.tsx       // Parameter space visualization

// Layout
Header.tsx                   // Status + mode selector
Sidebar.tsx                  // Tab navigation
Footer.tsx                   // Links + about
```

## Migration Path

### Phase 0 (Week 1): Setup
- Create `dashboard/` directory structure
- Setup Node.js project with Vite + React + TypeScript
- Install Chart.js, Recharts, Tailwind
- Setup build pipeline

### Phase 1 (Week 2): Backend API
- Create FastAPI app alongside Flask
- Implement `/api/v2/strategies/*` endpoints
- Implement `/api/v2/backtest/*` endpoints
- Integrate with existing SQLite DBs

### Phase 2 (Week 3): Frontend Basic
- Build static HTML structure
- Implement Strategy comparison page
- Implement Backtest results page
- Setup Redux state management

### Phase 3 (Week 4): Optimization + Vectorbt
- Implement Optuna tracking dashboard
- Implement Vectorbt discovery page
- Add interactive charts

### Phase 4 (Week 5): Real-time + Polish
- Implement WebSocket layer
- Add live trading page
- Styling pass (Tailwind)
- Performance optimization

### Phase 5: Deployment
- Bundle frontend
- Deploy alongside existing Flask app
- Redirect `/dashboard` to new React app
- Keep old dashboard as fallback

## Benefits

✅ **Modern UI/UX** - Clean, professional appearance  
✅ **Data-focused** - Backtest results, optimization tracking, vectorbt insights  
✅ **Real-time** - WebSocket updates, no polling lag  
✅ **Interactive** - Zoom, pan, hover on charts  
✅ **Responsive** - Works on desktop, tablet, mobile  
✅ **Maintainable** - React components, TypeScript, proper architecture  
✅ **Extensible** - Easy to add new pages, components, features  

## Start With

Would you like me to:
1. Start with the backend API layer (create endpoints + data models)?
2. Start with the frontend framework (React setup + basic layout)?
3. Focus on one specific page (e.g., Strategy Dashboard first)?
