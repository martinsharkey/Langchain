"""
Market Data Collector — Gathers data from multiple sources asynchronously.

This module collects data from:
1. Economic calendar (Forex Factory, Trading Economics)
2. News feeds (NewsAPI, Reuters, Bloomberg)
3. Central bank statements (Fed, ECB, BOE)
4. Geopolitical events
5. Gold-specific news
6. USD strength indicators

All requests run in parallel with a timeout.

Usage:
    collector = MarketDataCollector()
    data = await collector.collect_all()
"""

import os
import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
import json

from src.data_sources.economic_calendar import EconomicCalendarSource
from src.data_sources.news_aggregator import NewsAggregatorSource
from src.data_sources.central_banks import CentralBankSource
from src.data_sources.geopolitical import GeopoliticalSource
from src.data_sources.gold_news import GoldNewsSource
from src.data_sources.usd_strength import USDStrengthSource

logger = logging.getLogger("core.market_data_collector")


class MarketDataCollector:
    """
    Asynchronously collects market data from multiple sources.
    
    Non-blocking: All requests run in parallel.
    Timeout: 5 minutes per source, overall 10 minutes.
    """
    
    def __init__(self):
        """Initialize data collector with all data sources."""
        self.timeout = 300  # 5 minutes per source
        self.total_timeout = 600  # 10 minutes overall
        
        # Initialize data sources
        self.economic_calendar = EconomicCalendarSource()
        self.news_aggregator = NewsAggregatorSource()
        self.central_banks = CentralBankSource()
        self.geopolitical = GeopoliticalSource()
        self.gold_news = GoldNewsSource()
        self.usd_strength = USDStrengthSource()
        
        logger.info("MarketDataCollector initialized with all data sources")
    
    async def collect_all(self) -> Dict[str, Any]:
        """
        Collect all market data in parallel.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "economic_calendar": {...},
                "news": {...},
                "central_bank": {...},
                "geopolitical": {...},
                "gold_news": {...},
                "usd_strength": {...},
                "errors": [...]  # Any failures
            }
        """
        
        logger.info("Starting market data collection from all sources...")
        start_time = datetime.now(timezone.utc)
        
        try:
            # Create all collection tasks
            tasks = [
                self.economic_calendar.collect(),
                self.news_aggregator.collect(),
                self.central_banks.collect(),
                self.geopolitical.collect(),
                self.gold_news.collect(),
                self.usd_strength.collect(),
            ]
            
            # Run all tasks in parallel with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.total_timeout
            )
            
            # Process results
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "economic_calendar": None,
                "news": None,
                "central_bank": None,
                "geopolitical": None,
                "gold_news": None,
                "usd_strength": None,
                "sources_available": 0,
                "errors": []
            }
            
            result_keys = [
                "economic_calendar", "news", "central_bank",
                "geopolitical", "gold_news", "usd_strength"
            ]
            
            errors = []
            for key, result in zip(result_keys, results):
                if isinstance(result, Exception):
                    logger.warning(f"Error collecting {key}: {result}")
                    errors.append(f"{key}: {str(result)}")
                else:
                    data[key] = result
                    if result and "errors" not in result or not result.get("errors"):
                        data["sources_available"] += 1
            
            data["errors"] = errors
            
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"Market data collection completed in {elapsed:.1f}s "
                f"({data['sources_available']}/6 sources, {len(errors)} errors)"
            )
            
            return data
            
        except asyncio.TimeoutError:
            logger.error("Market data collection timed out after 10 minutes")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "economic_calendar": None,
                "news": None,
                "central_bank": None,
                "geopolitical": None,
                "gold_news": None,
                "usd_strength": None,
                "sources_available": 0,
                "errors": ["Overall timeout: 10 minutes exceeded"]
            }
