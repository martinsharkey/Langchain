import vectorbt as vbt
import pandas as pd
from src.mt5.data import get_rates

rates = get_rates(symbol='BTCUSD', timeframe='H1', count=1000, lock=True)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)

price = df['close'].values

ind = vbt.indicators.RSI.run(price)

# Find the right attribute
print("Testing VectorBT RSI API:")
print(f"Type: {type(ind)}")
print(f"Dir: {[x for x in dir(ind) if not x.startswith('_')]}")

# Try accessing the values
try:
    print(f"ind.rsi: {ind.rsi.shape}")
except:
    print("No ind.rsi")

try:
    print(f"ind.RSI_14: {ind.RSI_14.shape}")
except:
    print("No ind.RSI_14")

try:
    print(f"ind.close: {ind.close.shape}")
except:
    print("No ind.close")

# Try to get the result directly
try:
    result_val = ind.result  # VectorBT often stores results in .result
    print(f"ind.result shape: {result_val.shape}")
except:
    print("No ind.result")
