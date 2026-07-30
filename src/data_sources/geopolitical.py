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
        # In production, could use GDELT or similar API
        self.use_mock = True  # Default to mock until API configured
        logger.info("GeopoliticalSource initialized")
    
    async def collect(self) -> Dict[str, Any]:
        """
        Collect geopolitical events.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "wars": [{"location": ..., "severity": ..., "impact": ...}, ...],
                "sanctions": [...],
                "elections": [...],
                "trade_tensions": [...],
                "safe_haven_demand": 0.5,  # 0.0-1.0
                "crisis_level": "low|medium|high",
                "errors": [str, ...]
            }
        """
        logger.info("Collecting geopolitical events...")
        
        if self.use_mock:
            return await self._collect_mock()
        
        try:
            # Could integrate real APIs here (GDELT, NewsAPI, etc.)
            # For now, returning structured format
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "wars": [],
                "sanctions": [],
                "elections": [],
                "trade_tensions": [],
                "safe_haven_demand": 0.5,
                "crisis_level": "low",
                "errors": ["Geopolitical API not configured"]
            }
        
        except Exception as e:
            logger.error(f"Error collecting geopolitical data: {e}")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "wars": [],
                "sanctions": [],
                "elections": [],
                "trade_tensions": [],
                "safe_haven_demand": 0.5,
                "crisis_level": "low",
                "errors": [str(e)]
            }
    
    async def _collect_mock(self) -> Dict[str, Any]:
        """Return mock geopolitical data."""
        logger.info("Using mock geopolitical data")
        
        mock_events = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wars": [
                {
                    "location": "Ukraine",
                    "severity": 3,
                    "impact": "bullish",
                    "description": "Ongoing Russia-Ukraine conflict",
                    "trend": "stable",
                    "gold_impact_direction": "BUY"
                }
            ],
            "sanctions": [
                {
                    "target": "Russia",
                    "source": "Western nations",
                    "severity": 2,
                    "impact": "bullish",
                    "recent": True,
                    "gold_impact_direction": "BUY"
                }
            ],
            "elections": [
                {
                    "country": "US",
                    "date": (datetime.now(timezone.utc) + timedelta(days=200)).date().isoformat(),
                    "severity": 1,
                    "impact": "neutral",
                    "uncertainty": True,
                    "gold_impact_direction": "HOLD"
                }
            ],
            "trade_tensions": [
                {
                    "parties": "US-China",
                    "severity": 2,
                    "impact": "bullish",
                    "tariffs": True,
                    "gold_impact_direction": "BUY"
                }
            ],
            "safe_haven_demand": 0.6,  # Medium-high
            "crisis_level": "medium",
            "major_risks": [
                "Persistent Russia-Ukraine conflict",
                "Potential Taiwan tension escalation",
                "US election uncertainty 2024"
            ],
            "errors": ["Mock data - real geopolitical API not configured"]
        }
        
        return mock_events
    
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
