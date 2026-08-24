# Strategy Catalog System Design

**Date:** 2026-08-24  
**Status:** ARCHITECTURE PROPOSAL  
**Scope:** Replace rigid FOCUSED_EDGE with flexible, per-symbol strategy catalog

---

## Problem Statement

Current architecture limits trading to hardcoded strategy combinations:
- **FOCUSED_EDGE** dictionary is static and requires code changes to modify
- **Fallback chains** (Bollinger_OsMA → OsMA_Confluence) are rigid, one-size-fits-all
- **No per-symbol optimization**: Can't use Volume_Breakout for XAUUSD, Bollinger_OsMA for BTCUSD simultaneously
- **No indicator combination testing**: Can't systematically test new indicator combos
- **Duplicate work**: Vectorbt (for fast backtesting) and Optuna (for tuning) exist but not integrated into strategy selection

---

## Proposed Architecture

### 1. Strategy Registry System

**File:** `src/learning/strategy_registry.py` (enhance existing)

```python
# What we have NOW
@dataclass
class StrategyMetadata:
    name: str
    signal_fn: Callable
    indicators_used: List[str]
    suitable_regimes: List[str]
    min_confidence: float
    status: str  # "active", "testing", "disabled"
    weight: float

# What we NEED to add
@dataclass
class StrategyConfig:
    strategy_name: str
    symbol: str  # "XAUUSD", "BTCUSD", "GER40"
    enabled: bool
    rank: int  # 1=primary, 2=secondary, etc
    parameters: Dict[str, float]  # strategy-specific params
    backtest_score: float  # PF from last validation
    last_validated: datetime
    vectorbt_cached: bool  # did we cache vectorbt results?
    optuna_study_id: Optional[str]  # link to Optuna tuning
```

### 2. Strategy Configuration File

**File:** `data/strategy_config.json`

```json
{
  "strategies": {
    "XAUUSD": [
      {
        "rank": 1,
        "strategy": "OsMA_Confluence",
        "enabled": true,
        "parameters": {
          "osma_fast": 12,
          "osma_slow": 26,
          "osma_signal": 9,
          "bulls_min_long": 0.8,
          "bears_min_short": 0.8
        },
        "vectorbt_pf": 1.24,
        "optuna_study": "xauusd_osma_confluence_v1"
      },
      {
        "rank": 2,
        "strategy": "Volume_Breakout",
        "enabled": true,
        "parameters": {
          "period": 20,
          "volume_threshold": 1.5
        },
        "vectorbt_pf": 1.15,
        "optuna_study": null
      }
    ],
    "BTCUSD": [
      {
        "rank": 1,
        "strategy": "Bollinger_OsMA",
        "enabled": true,
        "parameters": {
          "max_extension_atr": 2.0,
          "ATR_Multiplier": 1.889
        },
        "vectorbt_pf": 1.18,
        "optuna_study": "btcusd_bollinger_osma_v1"
      },
      {
        "rank": 2,
        "strategy": "OsMA_Confluence",
        "enabled": true,
        "parameters": {},
        "vectorbt_pf": 1.08,
        "optuna_study": null
      }
    ],
    "GER40": [
      {
        "rank": 1,
        "strategy": "MACD_Cross",
        "enabled": true,
        "parameters": {},
        "vectorbt_pf": 1.12,
        "optuna_study": "ger40_macd_v1"
      }
    ]
  }
}
```

### 3. Vectorbt Integration

**File:** `src/learning/vectorbt_backtester.py` (NEW)

```python
class VectorbtBacktester:
    """Fast backtesting using vectorbt for strategy comparison."""
    
    def backtest_strategy(self, symbol, strategy_name, 
                         params, candle_df, 
                         cache=True) -> BacktestResult:
        """
        Run fast vectorbt backtest on strategy + params combo.
        
        Args:
            symbol: Trading symbol
            strategy_name: Name of strategy to test
            params: Strategy parameters
            candle_df: OHLCV data from MT5
            cache: Use cached results if available
        
        Returns:
            BacktestResult with PF, WR, trades, etc
        """
        # 1. Check cache first
        cache_key = f"{symbol}_{strategy_name}_{hash(params)}"
        if cache:
            cached = load_cache(cache_key)
            if cached:
                return cached
        
        # 2. Generate entry/exit signals using strategy signal_fn
        signals = self._generate_signals(strategy_name, candle_df, params)
        
        # 3. Use vectorbt to calculate returns, drawdown, etc
        import vectorbt as vbt
        
        pf = vbt.Portfolio.from_signals(
            entries=signals['buy'],
            exits=signals['sell'],
            close=candle_df['close'],
            freq='1min'  # M1 data
        )
        
        result = BacktestResult(
            symbol=symbol,
            strategy=strategy_name,
            trades=len(pf.trades.records),
            win_rate=pf.trades.win_rate,
            profit_factor=pf.trades.profit_factor,
            sharpe_ratio=pf.sharpe_ratio(),
            max_drawdown=pf.max_drawdown(),
            # ... other metrics
        )
        
        # 4. Cache results
        if cache:
            save_cache(cache_key, result)
        
        return result
```

### 4. Optuna Integration

**File:** `src/learning/optuna_strategy_tuner.py` (NEW)

```python
class OptunaStrategyTuner:
    """Tuning strategy parameters using Optuna with vectorbt validation."""
    
    def create_study_for_strategy(self, symbol, strategy_name):
        """
        Create Optuna study to tune strategy parameters.
        
        Example: BTCUSD + Bollinger_OsMA
          - Objective: maximize profit_factor in walk-forward validation
          - Parameters: max_extension_atr (1.0-3.0), ATR_Multiplier (1.0-3.0)
          - Constraints: must maintain WR > 45%
        """
        import optuna
        
        def objective(trial):
            # Suggest parameters based on strategy
            params = self._suggest_params(trial, strategy_name)
            
            # Fast backtest with vectorbt
            result = self.vectorbt_backtester.backtest_strategy(
                symbol, strategy_name, params, 
                cache=True
            )
            
            # Optuna maximizes PF, but rejects if WR < 45%
            if result.win_rate < 0.45:
                raise optuna.TrialPruning()
            
            return result.profit_factor
        
        study = optuna.create_study(
            direction="maximize",
            study_name=f"{symbol}_{strategy_name}",
            storage=f"sqlite:///data/optuna_studies.db"
        )
        
        return study
    
    def tune_live_parameters(self):
        """
        Run Optuna tuning every 24 hours for active strategies.
        
        This runs alongside live trading:
        1. Get best params from recent Optuna trial
        2. Validate on out-of-sample data (walk-forward)
        3. If better than current, mark for live bot to use
        4. Live bot picks up via strategy_config.json overlay
        """
        for symbol, strategies in self.strategy_config.items():
            for strategy_cfg in strategies:
                if strategy_cfg['enabled']:
                    study = optuna.load_study(
                        study_name=strategy_cfg['optuna_study'],
                        storage="sqlite:///data/optuna_studies.db"
                    )
                    
                    # Run N trials
                    study.optimize(
                        objective, 
                        n_trials=100,  # or based on compute budget
                        timeout=3600  # 1 hour max
                    )
                    
                    # Validate best trial on walk-forward
                    best = study.best_trial
                    validated = self.validate_walk_forward(
                        symbol,
                        strategy_cfg['strategy'],
                        best.params
                    )
                    
                    # If improves on current, propose to live bot
                    if validated.profit_factor > strategy_cfg['vectorbt_pf']:
                        self.propose_parameter_update(
                            symbol,
                            strategy_cfg['strategy'],
                            best.params,
                            validated
                        )
```

### 5. Strategy Selection Logic

**File:** `src/learning/edge_weights.py` (refactor `focused_rules`)

```python
def focused_rules(symbol: str):
    """
    Return ranked list of (strategy, params) for a symbol.
    
    Replaces hard-coded FOCUSED_EDGE fallback chain.
    Now supports:
    1. Per-symbol strategy ranking
    2. Dynamic parameter loading
    3. Optuna-tuned parameters
    4. Runtime configuration via data/strategy_config.json
    """
    
    # 1. Load configuration
    config = load_strategy_config()
    
    # 2. Get strategies for this symbol
    symbol_strategies = config.get('strategies', {}).get(symbol, [])
    
    # 3. Sort by rank and return with parameters
    ranked = sorted(
        [s for s in symbol_strategies if s.get('enabled')],
        key=lambda x: x.get('rank', 999)
    )
    
    # 4. Return [(strategy_name, params, rank), ...]
    return [
        (s['strategy'], s.get('parameters', {}), s['rank'])
        for s in ranked
    ]

def get_signal(symbol, indicators, regime=None):
    """
    NEW: Request signal from best-ranked strategy for symbol.
    
    Returns signal from primary strategy. If primary rejects (returns hold),
    tries secondary, etc - but NO fallback across symbols.
    
    Each symbol has its OWN best strategy, not a chain.
    """
    
    rules = focused_rules(symbol)
    
    for strategy_name, params, rank in rules:
        strategy_fn = registry.get(strategy_name).signal_fn
        
        # Pass strategy-specific parameters
        signal = strategy_fn(indicators, params)
        
        if signal.action != "hold":
            # Log which strategy fired
            logger.info(f"[SIGNAL] {symbol}: {strategy_name} (rank {rank})")
            return signal
    
    # All strategies rejected
    return Signal(action="hold")
```

### 6. Self-Learning Loop

**File:** `src/learning/strategy_learner.py` (NEW)

```python
class StrategyLearner:
    """Continuous learning: backtest → Optuna → live parameters."""
    
    def learn_cycle(self):
        """
        Daily/hourly cycle:
        1. Collect new trades from live bot
        2. Re-backtest all strategies with new data
        3. Run Optuna to find better parameters
        4. Validate on walk-forward
        5. Deploy best parameters to live
        """
        
        while True:
            try:
                # 1. Get latest OHLCV from MT5
                for symbol in ['XAUUSD', 'BTCUSD', 'GER40']:
                    candles = self.get_mt5_history(symbol, bars=12000)
                    
                    # 2. Re-backtest active strategies
                    active_strategies = self.get_active_strategies(symbol)
                    
                    for strategy_name in active_strategies:
                        # Load current best params from config
                        current_params = self.load_current_params(
                            symbol, strategy_name
                        )
                        
                        # Fast vectorbt backtest
                        result = self.vectorbt_backtester.backtest_strategy(
                            symbol, strategy_name, current_params, 
                            candles, cache=False  # fresh test
                        )
                        
                        logger.info(
                            f"{symbol}/{strategy_name}: WR {result.win_rate:.1%}, "
                            f"PF {result.profit_factor:.2f}"
                        )
                        
                        # 3. If performance degrading, trigger Optuna
                        if result.profit_factor < 1.0:
                            logger.warning(
                                f"Triggering Optuna: {symbol}/{strategy_name} "
                                f"PF dropped to {result.profit_factor:.2f}"
                            )
                            self.optuna_tuner.optimize_parameters(
                                symbol, strategy_name, 
                                n_trials=100
                            )
                    
                    # Wait before next symbol
                    sleep(60)
                
                # 4. Sleep before next cycle
                # Daily: sleep until next UTC day
                # Hourly: sleep until next hour
                sleep_until_next_cycle()
                
            except Exception as e:
                logger.error(f"Learn cycle failed: {e}")
                sleep(300)  # Retry after 5 min
```

---

## Integration Points

### How Live Bot Uses This

**File:** `src/trading/scalp_engine.py`

```python
def _get_entry_signal(self, symbol, indicators):
    """
    NEW: Use flexible strategy catalog.
    
    OLD:
        rules = focused_rules(symbol)  # Returns fallback chain
        signal = registry.get_focused_signal(...)  # Try each in chain
    
    NEW:
        signal = self.strategy_selector.get_signal(
            symbol, 
            indicators,
            regime=self.detect_regime(indicators)
        )
    """
    
    # Get signal from best-ranked strategy for this symbol
    signal = self.strategy_selector.get_signal(symbol, indicators)
    
    # If signal fires, execute trade (same as before)
    if signal.action in ['buy', 'sell']:
        self.execute_trade(symbol, signal)
```

### How Configuration Updates Work

1. **Optuna finds better parameters** → saved to DB
2. **Proposal module validates** → checks walk-forward
3. **Parameter update proposed** → strategy_config.json updated
4. **Live bot reloads config** → uses new parameters on next check cycle
5. **No restart needed** → hot config reload

---

## Vectorbt + Optuna Critical Functionality

### Vectorbt Is Used For

1. **Fast backtesting**: Test strategy on 12,000 bars in <1 second (vs minutes with tick-by-tick)
2. **Walk-forward validation**: Split data into 3 windows, backtest each
3. **Parameter search space**: Optuna proposes params → vectorbt validates quickly
4. **Performance metrics**: PF, WR, Sharpe, MDD calculated efficiently
5. **Caching**: Store results to avoid redundant backtests

### Optuna Is Used For

1. **Parameter tuning**: Find optimal entry/exit thresholds per strategy/symbol
2. **Constraint satisfaction**: Maintain WR > 45%, PF > 1.0 while maximizing objective
3. **Trial pruning**: Stop unpromising trials early
4. **Study persistence**: Save tuning progress to SQLite for multi-session optimization
5. **Live tuning**: Run continuously as new data arrives

---

## Files to Create/Refactor

1. **NEW:** `src/learning/vectorbt_backtester.py` - Vectorbt wrapper
2. **NEW:** `src/learning/optuna_strategy_tuner.py` - Optuna orchestration
3. **NEW:** `src/learning/strategy_learner.py` - Self-learning loop
4. **NEW:** `src/learning/strategy_selector.py` - Per-symbol strategy selection
5. **NEW:** `data/strategy_config.json` - Runtime configuration
6. **REFACTOR:** `src/learning/edge_weights.py` - Remove FOCUSED_EDGE fallback chain
7. **REFACTOR:** `src/trading/scalp_engine.py` - Use new strategy selector
8. **ENHANCE:** `src/learning/strategy_registry.py` - Add config metadata

---

## Benefits

| Feature | Before | After |
|---------|--------|-------|
| Strategy per symbol | ❌ Fallback chain | ✅ Per-symbol ranking |
| Runtime config changes | ❌ Edit code, restart bot | ✅ Update JSON, hot-reload |
| Parameter tuning | ❌ Manual Optuna runs | ✅ Continuous, automated |
| New strategy testing | ❌ Modify FOCUSED_EDGE | ✅ Add to config |
| Indicator combinations | ❌ Limited, hardcoded | ✅ Pluggable via registry |
| Backtest speed | ❌ Slow tick-by-tick | ✅ Fast vectorbt cached |
| Self-learning | ⚠️ Basic | ✅ Closed-loop tuning |

---

## Implementation Phases

### Phase 1: Configuration (1 hour)
- Create strategy_config.json structure
- Refactor focused_rules() to load from config

### Phase 2: Vectorbt Integration (2 hours)
- Create VectorbtBacktester wrapper
- Implement result caching
- Validate on current strategies

### Phase 3: Strategy Selector (1 hour)
- Implement per-symbol selection logic
- Update scalp_engine to use new selector

### Phase 4: Optuna + Learning (3 hours)
- Create OptunaStrategyTuner
- Implement StrategyLearner loop
- Wire parameter updates to live bot

### Phase 5: Testing (2 hours)
- Integration tests
- Live bot compatibility tests
- Walk-forward validation

---

## Migration Path

**No downtime required:**

1. Deploy Phase 1-3 while bot runs with old logic
2. Activate new selector alongside old (A/B test)
3. Compare signal counts/quality before full switch
4. When confident, replace old logic completely
5. Deploy learning loop

