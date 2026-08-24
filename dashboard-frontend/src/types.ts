/**
 * API Type Definitions
 * Matches backend DashboardAPIv2 responses
 */

export interface RegimeEdge {
  regime: string
  multiplier: number
}

export interface BacktestMetrics {
  pf: number
  wr: number
  sharpe: number
  trades: number
  validated_at: string
}

export interface LiveMetrics {
  trades: number
  wr: number
  pf: number
  pnl: number
  avg_win: number
  avg_loss: number
}

export interface OptunaMetrics {
  study: string
  trials: number
  best_value: number | null
  improvement_pct: number | null
  last_optimized: string | null
}

export interface Strategy {
  symbol: string
  name: string
  rank: number
  enabled: boolean
  validated: boolean
  vectorbt_pf: number | null
  regime_edges: RegimeEdge[]
  backtest?: BacktestMetrics
  live?: LiveMetrics
  optuna?: OptunaMetrics
}

export interface BacktestResult {
  symbol: string
  strategy: string
  profit_factor: number
  win_rate: number
  sharpe: number
  trades: number
  generalizes: boolean
  min_window_pf: number
  validated_at: string
}

export interface VectorbtDiscovery {
  swept_at: string
  min_pf_threshold: number
  timeframe: string
  symbols: Record<string, {
    validated: boolean
    pockets: number
  }>
}

export interface DashboardSummary {
  total_strategies: number
  validated_strategies: number
  avg_profit_factor: number
  best_strategy: {
    name: string
    symbol: string
    pf: number
  } | null
  worst_strategy: {
    name: string
    symbol: string
    pf: number
  } | null
}

export interface SymbolStatus {
  symbol: string
  status: 'ready' | 'onboarding' | 'onboarded' | 'error'
  progress?: number
  results?: {
    best_strategy: string
    profit_factor: number
    win_rate: number
    sharpe_ratio: number
    total_trades: number
    best_session?: string
    validated: boolean
  }
  sessions?: Record<string, SessionResult>
  enabled_sessions?: string[]  // Sessions enabled for trading
  error?: string
  last_updated?: string
}

export interface SessionResult {
  session: string
  timeframe?: string
  best_strategy: string
  secondary_filter: string
  profit_factor: number
  win_rate: number
  sharpe_ratio: number
  total_trades: number
  sl_multiplier: number
  tp_ratio: number
  floor_config?: {
    strategy: string
    filter: string
    sl: number
    tp: number
  }
  alternative_timeframes?: Array<{
    timeframe: string
    best_strategy: string
    secondary_filter: string
    profit_factor: number
    win_rate: number
    sharpe_ratio: number
    total_trades: number
  }>
}

export interface OnboardingTask {
  task_id: string
  symbol: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  started_at: string
  completed_at?: string
}

export interface ApiResponse<T> {
  status: string
  data: T
  error?: string
}
