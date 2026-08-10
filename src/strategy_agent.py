import pandas as pd
import numpy as np

# Load XAUUSD data from CSV file
xauusd_data = pd.read_csv('xauusd_data.csv')

# Define the trading strategy
def strategy(data):
    # Calculate the moving averages
    data['MA_50'] = data['Close'].rolling(window=50).mean()
    data['MA_200'] = data['Close'].rolling(window=200).mean()

    # Generate buy and sell signals
    data['Signal'] = 0
    data.loc[(data['MA_50'] > data['MA_200']) & (data['MA_50'].shift(1) <= data['MA_200'].shift(1)), 'Signal'] = 1
    data.loc[(data['MA_50'] < data['MA_200']) & (data['MA_50'].shift(1) >= data['MA_200'].shift(1)), 'Signal'] = -1

    return data

# Apply the trading strategy
xauusd_data = strategy(xauusd_data)

# Save the strategy results to a new CSV file
xauusd_data.to_csv('xauusd_strategy.csv')