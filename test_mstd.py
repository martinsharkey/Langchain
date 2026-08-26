import vectorbt as vbt
import pandas as pd
from src.mt5.data import get_rates

rates = get_rates(symbol='BTCUSD', timeframe='H1', count=1000, lock=True)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)

price = df['close']

# Test MSTD
ind = vbt.indicators.MSTD.run(price)
print('MSTD has mstd?', hasattr(ind, 'mstd'))

for attr in ['mstd', 'std', 'value', 'result', 'close']:
    if hasattr(ind, attr):
        val = getattr(ind, attr)
        print(f'{attr}: {type(val)}')
