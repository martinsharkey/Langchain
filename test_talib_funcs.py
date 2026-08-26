import talib
import numpy as np
from src.mt5.data import get_rates
import pandas as pd

# Get data
rates = get_rates(symbol='BTCUSD', timeframe='H1', count=1000, lock=True)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)

price = df['close'].values
high = df['high'].values
low = df['low'].values

print('Testing ta-lib indicators:')

# RSI
rsi = talib.RSI(price, timeperiod=14)
print('RSI: min={:.2f}, max={:.2f}, valid={}'.format(np.nanmin(rsi), np.nanmax(rsi), (~np.isnan(rsi)).sum()))

# BBANDS
upper, middle, lower = talib.BBANDS(price, timeperiod=20)
print('BBANDS: upper={:.2f}-{:.2f}'.format(np.nanmin(upper), np.nanmax(upper)))

# MACD
macd, signal, hist = talib.MACD(price)
print('MACD: valid={}'.format((~np.isnan(macd)).sum()))

# ADX
adx = talib.ADX(high, low, price)
print('ADX: min={:.2f}, max={:.2f}'.format(np.nanmin(adx), np.nanmax(adx)))

print('Total ta-lib functions available: {}'.format(len([x for x in dir(talib) if not x.startswith('_')])))
