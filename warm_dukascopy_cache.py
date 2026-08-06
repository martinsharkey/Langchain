import sys
from datetime import datetime, timezone, timedelta
from src.data_sources.dukascopy import fetch_ticks

# Warm the cache for a multi-week XAUUSD window so backtests run instantly afterwards.
start = sys.argv[1] if len(sys.argv) > 1 else "2024-04-01"
end = sys.argv[2] if len(sys.argv) > 2 else "2024-05-31"
d0 = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
d1 = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
n = fetch_ticks("XAUUSD", d0, d1, use_cache=True, workers=4)
print(f"WARM_DONE ticks={n if isinstance(n,int) else len(n)} {start}..{end}")
