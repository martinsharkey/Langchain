# Vectorbt Interface Guide

Vectorbt has a comprehensive, production-grade interface with multiple ways to use it. Here are your options:

## 1. Core Classes (What We Used)

### `vbt.Portfolio` - Main backtesting engine
```python
import vectorbt as vbt

# Create portfolio from entry/exit signals
portfolio = vbt.Portfolio.from_signals(
    close=price_data,
    entries=entry_signals,    # boolean array
    exits=exit_signals,       # boolean array
    init_cash=10000,
    freq='D'
)

# Access results
print(portfolio.stats())                 # Summary statistics
print(portfolio.sharpe_ratio())         # Sharpe ratio
print(portfolio.total_return())         # Total return
print(portfolio.max_drawdown())         # Max drawdown
print(portfolio.win_rate)               # Win rate
print(portfolio.profit_factor)          # Profit factor
```

### Pre-Built Indicators
```python
# Bollinger Bands
bb = vbt.BBANDS(close, window=20, num_std=2)
print(bb.lower_band)
print(bb.middle_band)
print(bb.upper_band)

# RSI
rsi = vbt.RSI(close, window=14)
print(rsi.rsi)

# MACD
macd = vbt.MACD(close, fast_period=12, slow_period=26, signal_period=9)
print(macd.macd)
print(macd.signal)
print(macd.histogram)

# ATR
atr = vbt.ATR(high, low, close, window=14)
print(atr.atr)

# Stochastic
stoch = vbt.STOCH(high, low, close, k_period=14, d_period=3)
print(stoch.k)
print(stoch.d)

# OBV
obv = vbt.OBV(close, volume)
print(obv.obv)
```

## 2. Advanced Portfolio Features

### Parameter Optimization (Grid Search)
```python
# Test multiple parameter combinations
params_dict = {
    'bb_period': [15, 20, 25, 30],
    'bb_std': [1.5, 2.0, 2.5, 3.0],
    'rsi_period': [7, 14, 21]
}

# Vectorbt handles combinatorial expansion automatically
for params in itertools.product(*params_dict.values()):
    bb = vbt.BBANDS(close, window=params[0], num_std=params[1])
    rsi = vbt.RSI(close, window=params[2])
    
    entries = (close <= bb.lower_band) & (rsi < 30)
    exits = (close >= bb.middle_band)
    
    pf = vbt.Portfolio.from_signals(close, entries, exits)
    print(f"PF: {pf.profit_factor()}")
```

### Walk-Forward Validation
```python
# Split data into windows
train_start, train_end = '2024-01-01', '2024-06-30'
test_start, test_end = '2024-07-01', '2024-09-30'

# Train on historical window
train_data = price_data[train_start:train_end]
test_data = price_data[test_start:test_end]

# Backtest on out-of-sample
pf_train = vbt.Portfolio.from_signals(train_data, entries_train, exits_train)
pf_test = vbt.Portfolio.from_signals(test_data, entries_test, exits_test)

print(f"In-sample: PF={pf_train.profit_factor()}")
print(f"Out-of-sample: PF={pf_test.profit_factor()}")
```

### Leverage & Position Sizing
```python
# Trade with leverage
pf = vbt.Portfolio.from_signals(
    close=price_data,
    entries=entry_signals,
    exits=exit_signals,
    size=2.0  # 2x leverage
)

# Fixed position size
pf = vbt.Portfolio.from_signals(
    close=price_data,
    entries=entry_signals,
    exits=exit_signals,
    size=100  # fixed 100 units
)
```

### Monte Carlo Analysis
```python
# Shuffle trade order to test robustness
returns = portfolio.returns()
shuffled_returns = np.random.permutation(returns)

# Test statistical significance
print(portfolio.calmar_ratio())
print(portfolio.sortino_ratio())
print(portfolio.information_ratio())
```

## 3. Data Access

### Built-in Data Sources
```python
# Yahoo Finance
data = vbt.YFData.download('AAPL', start='2024-01-01', end='2024-12-31')

# Binance (crypto)
data = vbt.BinanceData.download('BTCUSDT', start='2024-01-01', end='2024-12-31')

# Alpaca
data = vbt.AlpacaData.download('SPY', start='2024-01-01', end='2024-12-31')

# CCXT (unified crypto exchange interface)
data = vbt.CCXTData.download('BTC/USDT', start='2024-01-01', end='2024-12-31')
```

## 4. Signal Generation

### Pre-built Signal Factories
```python
# Moving Average Crossover
from vectorbt.indicators import MA

ma_fast = vbt.MA(close, window=10)
ma_slow = vbt.MA(close, window=20)

entries = ma_fast.ma > ma_slow.ma
exits = ma_fast.ma < ma_slow.ma
```

### Custom Signal Logic
```python
# Your custom logic
entries = (close <= bb.lower_band) & (rsi < 30) & (adx > 25)
exits = close >= bb.middle_band

# Convert to boolean
entries = entries.astype(bool)
exits = exits.astype(bool)
```

## 5. Visualization & Reporting

### Plotting
```python
# Plot price with indicators
fig = vbt.make_subplots(rows=3, cols=1)

fig.add_trace(go.Scatter(y=close, name='Price'), row=1, col=1)
fig.add_trace(go.Scatter(y=bb.upper_band, name='BB Upper'), row=1, col=1)
fig.add_trace(go.Scatter(y=bb.lower_band, name='BB Lower'), row=1, col=1)

fig.add_trace(go.Scatter(y=rsi.rsi, name='RSI'), row=2, col=1)
fig.add_trace(go.Scatter(y=macd.macd, name='MACD'), row=3, col=1)

fig.show()
```

### Performance Reports
```python
# Comprehensive statistics
stats = portfolio.stats()
print(stats)

# Key metrics
print(f"Total Return: {portfolio.total_return() * 100:.2f}%")
print(f"Annual Return: {portfolio.annualized_return() * 100:.2f}%")
print(f"Sharpe Ratio: {portfolio.sharpe_ratio():.2f}")
print(f"Sortino Ratio: {portfolio.sortino_ratio():.2f}")
print(f"Max Drawdown: {portfolio.max_drawdown() * 100:.2f}%")
print(f"Win Rate: {portfolio.trades.win_rate * 100:.2f}%")
print(f"Profit Factor: {portfolio.trades.profit_factor:.2f}")
```

## 6. What We DIDN'T Use (But Could)

### ✗ Signal Factory (automatic signal generation)
```python
# Vectorbt can auto-generate entry/exit signals from indicators
from vectorbt.signals import SignalFactory

# Define custom signal logic
signal_factory = SignalFactory.from_apply_func(
    lambda close, rsi: (rsi < 30, rsi > 70),
    close=close,
    rsi=rsi_indicator
)
```

### ✗ Multi-level optimization
```python
# Vectorbt supports parameter sweeps with automatic grid search
# Instead of manual loops, you can use vbt's built-in parameter optimization
```

### ✗ Parallel processing
```python
# Vectorbt uses Numba for JIT compilation + parallel processing
# This makes it orders of magnitude faster for large backtests
```

### ✗ Realtime backtesting
```python
# Can simulate tick-by-tick execution with realistic slippage/commissions
pf = vbt.Portfolio.from_signals(
    ...,
    fees=0.001,  # 0.1% per trade
    freq='1min'  # minute-level precision
)
```

## 7. Our Current Limitations vs Vectorbt Capabilities

| Feature | Current | Vectorbt |
|---------|---------|----------|
| Indicator calculations | Manual | 50+ built-in indicators |
| Signal generation | Manual | Factories + auto-generation |
| Portfolio backtesting | Manual loop | Vectorized |
| Parameter optimization | Manual grid | Automatic grid search |
| Walk-forward validation | Not implemented | Built-in |
| Position sizing | Fixed SL/TP | Flexible sizing rules |
| Leverage handling | Not tested | Native support |
| Slippage/commissions | Not modeled | Built-in |
| Trade statistics | Basic | 50+ metrics |
| Visualization | None | Interactive plots |
| Parallel processing | Single-threaded | Numba JIT + parallel |

## 8. Recommended Next Steps

### To fully leverage vectorbt:

1. **Replace manual indicator calc** → Use `vbt.BBANDS()`, `vbt.RSI()`, etc.
2. **Replace manual signals** → Use `vbt.Portfolio.from_signals()`
3. **Add walk-forward validation** → Test on multiple time windows
4. **Add parameter sweeps** → Test 50,000+ combinations (vectorbt is fast enough)
5. **Add slippage/commission** → Model real trading costs
6. **Add position sizing rules** → Not just fixed SL/TP
7. **Add Monte Carlo analysis** → Test robustness
8. **Add visualization** → See results in interactive plots

## 9. Example: Complete Production-Grade Backtest

```python
import vectorbt as vbt
import pandas as pd
import numpy as np

# Load data
close = vbt.YFData.download('AAPL').get('Close')

# Test multiple strategies
results = []
for bb_period in [15, 20, 25]:
    for bb_std in [1.5, 2.0, 2.5]:
        for rsi_period in [7, 14, 21]:
            # Calculate indicators
            bb = vbt.BBANDS(close, window=bb_period, num_std=bb_std)
            rsi = vbt.RSI(close, window=rsi_period)
            
            # Generate signals
            entries = (close <= bb.lower_band) & (rsi < 30)
            exits = close >= bb.middle_band
            
            # Backtest
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=entries,
                exits=exits,
                init_cash=10000,
                fees=0.001,
                freq='D'
            )
            
            # Store results
            results.append({
                'bb_period': bb_period,
                'bb_std': bb_std,
                'rsi_period': rsi_period,
                'profit_factor': pf.trades.profit_factor(),
                'sharpe': pf.sharpe_ratio(),
                'win_rate': pf.trades.win_rate,
                'total_trades': len(pf.trades.records)
            })

# Find best
df = pd.DataFrame(results).sort_values('profit_factor', ascending=False)
print(df.head(10))
```

---

**Vectorbt is production-ready and significantly more powerful than what we currently use.**

The main reason we didn't use more features is **speed of development** — we focused on getting 30,000 combinations tested quickly rather than using every available tool. The framework is extensible and you can add these features incrementally.

