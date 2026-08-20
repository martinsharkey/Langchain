"""Data acquisition package — broker-agnostic historical data management.

Quick start:
    from src.data_acquisition import get_data_manager
    dm = get_data_manager(broker="vt_markets")
    bars = dm.get_rates("XAUUSD", "M15", bars=12000)
    ticks = dm.get_ticks("XAUUSD", start_ts, end_ts)

Or inject directly into Backtester:
    from src.data_acquisition import make_backtester_data_source
    rates_fn, ticks_fn = make_backtester_data_source(broker="vt_markets")
    bt = Backtester(registry, rates_fn=rates_fn, ticks_fn=ticks_fn)
"""

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.data_acquisition.refresh import DataRefreshManager


def get_data_manager(broker: str = "vt_markets") -> DataManager:
    """Create a DataManager for a named broker."""
    return DataManager(DataSourceConfig(broker=broker))


def make_backtester_data_source(broker: str = "vt_markets"):
    """Return (rates_fn, ticks_fn) matching Backtester's expected signatures.

    rates_fn(symbol, timeframe, count) -> list[dict]
    ticks_fn(symbol, from_epoch, to_epoch) -> dict | None
    """
    dm = get_data_manager(broker)

    def rates_fn(symbol: str, timeframe: str = "M15", count: int = 12000) -> list[dict]:
        return dm.get_rates(symbol, timeframe, count)

    def ticks_fn(symbol: str, from_epoch: float, to_epoch: float) -> dict | None:
        return dm.get_ticks(symbol, from_epoch, to_epoch)

    return rates_fn, ticks_fn


def get_refresh_manager(broker: str = "vt_markets", data_manager=None) -> DataRefreshManager:
    """Create a DataRefreshManager for a named broker."""
    if data_manager is None:
        data_manager = get_data_manager(broker)
    return DataRefreshManager(broker=broker, data_manager=data_manager)
