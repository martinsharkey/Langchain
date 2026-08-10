import pandas as pd
import numpy as np
import yfinance as yf

# Fetch XAUUSD data from Yahoo Finance
xauusd_data = yf.download('GC=F', start='2020-01-01', end='2023-12-31')

# Save the data to a CSV file
xauusd_data.to_csv('xauusd_data.csv')
