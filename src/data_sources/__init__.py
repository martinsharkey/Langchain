"""
Data Sources module — Aggregates market data from all sources.
"""

from src.data_sources.economic_calendar import EconomicCalendarSource, EconomicCalendarSourceMock
from src.data_sources.news_aggregator import NewsAggregatorSource
from src.data_sources.central_banks import CentralBankSource, CentralBankSourceMock
from src.data_sources.geopolitical import GeopoliticalSource
from src.data_sources.gold_news import GoldNewsSource
from src.data_sources.usd_strength import USDStrengthSource

__all__ = [
    "EconomicCalendarSource",
    "EconomicCalendarSourceMock",
    "NewsAggregatorSource",
    "CentralBankSource",
    "CentralBankSourceMock",
    "GeopoliticalSource",
    "GoldNewsSource",
    "USDStrengthSource",
]
