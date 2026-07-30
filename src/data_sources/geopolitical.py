"""
Geopolitical Events Data Source — Tracks events affecting safe-haven demand.

Monitors:
- Wars and conflicts
- Sanctions and trade wars
- Elections and political instability
- Natural disasters
- Pandemics

These drive safe-haven flows to gold.
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
import aiohttp

logger = logging.getLogger("data_sources.geopolitical")


class GeopoliticalSource:
    """
    Collects geopolitical events that drive safe-haven demand.
    """
    
    # Major geopolitical regions to monitor
    REGIONS = [
        "middle_east", "ukraine", "taiwan", "korea",
        "russia", "china", "europe", "americas"
    ]
    
    # Event types
    EVENT_TYPES = {
        "war": {"severity": 3, "gold_impact": "bullish"},
        "sanctions": {"severity": 2, "gold_impact": "bullish"},
        "election": {"severity": 1, "gold_impact": "neutral"},
        "trade_war": {"severity": 2, "gold_impact": "bullish"},
        "natural_disaster": {"severity": 2, "gold_impact": "bullish"},
        "pandemic": {"severity": 3, "gold_impact": "bullish"},
        "political_crisis": {"severity": 2, "gold_impact": "bullish"},
    }
    
    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=30)
        logger.info("GeopoliticalSource initialized (requires external API)")
    
    async def collect(self) -> Dict[str, Any]:
        """
        Collect geopolitical events.
        
        REQUIRED: Requires real geopolitical API (GDELT, NewsAPI, etc.).
        Does NOT use mock data.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "wars": [{"location": ..., "severity": ..., "impact": ...}, ...],
                "sanctions": [...],
                "elections": [...],
                "trade_tensions": [...],
                "safe_haven_demand": 0.0-1.0,
                "crisis_level": "low|medium|high",
                "errors": [str, ...]
            }
            
        Raises:
            ConnectionError: If geopolitical API not configured
        """
        logger.info("Collecting geopolitical events...")
        
        raise ConnectionError(
            "Geopolitical data source not configured.\n"
            "Requires integration with GDELT API or similar geopolitical event service.\n"
            "Current implementation only provides mock data which is disabled.\n"
            "Configure a real geopolitical API to enable this data source."
        )
    
    def calculate_safe_haven_pressure(
        self,
        events: Dict[str, Any]
    ) -> float:
        """
        Calculate safe-haven demand based on events.
        
        Returns:
            Float 0.0-1.0 (higher = more safe-haven demand = gold bullish)
        """
        pressure = 0.5  # Base neutral
        
        # Wars increase safe-haven demand
        war_pressure = len(events.get("wars", [])) * 0.15
        pressure += min(war_pressure, 0.3)  # Cap at 0.3
        
        # Sanctions increase slightly
        sanction_pressure = len(events.get("sanctions", [])) * 0.05
        pressure += sanction_pressure
        
        # Elections add uncertainty (increases demand slightly)
        election_pressure = len(events.get("elections", [])) * 0.02
        pressure += election_pressure
        
        # Trade tensions
        trade_pressure = len(events.get("trade_tensions", [])) * 0.1
        pressure += trade_pressure
        
        # Clamp to 0-1
        return min(max(pressure, 0.0), 1.0)
