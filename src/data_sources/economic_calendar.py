"""
Economic Calendar Data Source — Real market data from Forex Factory.

Collects economic events and their impact on XAUUSD.
Provides both upcoming and released economic data.

Data includes:
- Event name, date, time
- Country and impact rating
- Forecast vs actual vs previous
- Market impact (typically shown as stars: 1-3)

Usage:
    collector = EconomicCalendarSource()
    data = await collector.collect()
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import aiohttp
from bs4 import BeautifulSoup
import re

logger = logging.getLogger("data_sources.economic_calendar")


@dataclass
class EconomicEvent:
    """Represents an economic event."""
    name: str
    country: str
    time: str  # UTC time
    impact: int  # 1-3 (stars)
    forecast: Optional[float] = None
    previous: Optional[float] = None
    actual: Optional[float] = None
    unit: str = ""
    date: str = ""  # YYYY-MM-DD
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "country": self.country,
            "time": self.time,
            "impact": self.impact,
            "forecast": self.forecast,
            "previous": self.previous,
            "actual": self.actual,
            "unit": self.unit,
            "date": self.date,
            "is_released": self.actual is not None
        }


class EconomicCalendarSource:
    """
    Collects economic calendar data from Forex Factory.
    
    Forex Factory is the standard for forex traders for economic calendars.
    We scrape: https://www.forexfactory.com/calendar/
    """
    
    BASE_URL = "https://www.forexfactory.com/calendar/"
    
    # High-impact events for XAUUSD
    HIGH_IMPACT_EVENTS = {
        "US": [
            "FOMC Meeting Minutes",
            "FOMC Interest Rate Decision",
            "Non-Farm Payrolls (NFP)",
            "Initial Jobless Claims",
            "CPI m/m",
            "PCE m/m",
            "Retail Sales m/m",
            "PPI m/m",
            "ISM Manufacturing PMI",
            "ISM Non-Manufacturing PMI",
            "Consumer Sentiment",
            "Housing Starts",
            "Existing Home Sales",
            "Fed Funds Rate",
        ],
        "EUR": [
            "ECB Interest Rate Decision",
            "ECB Press Conference",
            "Eurozone CPI",
            "Eurozone Unemployment",
            "Eurozone PMI Manufacturing",
            "Eurozone PMI Services",
        ],
        "GBP": [
            "BOE Interest Rate Decision",
            "UK CPI",
            "UK Unemployment",
            "UK Retail Sales",
        ]
    }
    
    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=30)
        logger.info("EconomicCalendarSource initialized")
    
    async def collect(self) -> Dict[str, Any]:
        """
        Collect economic calendar data.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "upcoming": [EconomicEvent, ...],
                "released": [EconomicEvent, ...],
                "high_impact_upcoming": [EconomicEvent, ...],
                "errors": [str, ...]
            }
        """
        logger.info("Collecting economic calendar data...")
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                html = await self._fetch_page(session)
                
                if not html:
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "upcoming": [],
                        "released": [],
                        "high_impact_upcoming": [],
                        "errors": ["Failed to fetch calendar page"]
                    }
                
                # Parse calendar
                events = self._parse_calendar(html)
                
                # Separate upcoming and released
                upcoming = [e for e in events if e.actual is None]
                released = [e for e in events if e.actual is not None]
                
                # Filter high-impact upcoming
                high_impact = [
                    e for e in upcoming 
                    if e.impact >= 2 and self._is_high_impact_event(e)
                ]
                
                logger.info(
                    f"Calendar: {len(upcoming)} upcoming, "
                    f"{len(released)} released, "
                    f"{len(high_impact)} high-impact"
                )
                
                return {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "upstream": [e.to_dict() for e in upcoming[:20]],  # Next 20
                    "released": [e.to_dict() for e in released[-10:]],  # Last 10
                    "high_impact_upcoming": [e.to_dict() for e in high_impact],
                    "total_upcoming": len(upcoming),
                    "errors": []
                }
        
        except asyncio.TimeoutError:
            logger.error("Timeout fetching economic calendar")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "upstream": [],
                "released": [],
                "high_impact_upcoming": [],
                "errors": ["Timeout fetching calendar"]
            }
        
        except Exception as e:
            logger.error(f"Error collecting economic calendar: {e}")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "upstream": [],
                "released": [],
                "high_impact_upcoming": [],
                "errors": [str(e)]
            }
    
    async def _fetch_page(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Fetch the calendar page."""
        try:
            async with session.get(self.BASE_URL) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Calendar request returned {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching calendar page: {e}")
            return None
    
    def _parse_calendar(self, html: str) -> List[EconomicEvent]:
        """Parse economic calendar from HTML."""
        events = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find calendar rows
            rows = soup.find_all('tr', {'class': 'calendar__row'})
            
            for row in rows:
                try:
                    event = self._parse_row(row)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue
            
            logger.info(f"Parsed {len(events)} events from calendar")
            
        except Exception as e:
            logger.error(f"Error parsing calendar HTML: {e}")
        
        return events
    
    def _parse_row(self, row) -> Optional[EconomicEvent]:
        """Parse a single calendar row."""
        try:
            # Extract data from row
            cols = row.find_all('td')
            if len(cols) < 6:
                return None
            
            # Date and time
            date_str = cols[0].text.strip()
            time_str = cols[1].text.strip()
            
            # Country
            country = cols[2].text.strip()
            
            # Event name
            event_name = cols[3].text.strip()
            
            # Impact (stars: usually displayed as colored symbols)
            impact_str = cols[4].text.strip()
            impact = len(impact_str)  # Rough estimate: more characters = more impact
            impact = min(max(impact, 1), 3)  # Clamp to 1-3
            
            # Previous, forecast, actual
            previous = self._parse_value(cols[5].text if len(cols) > 5 else "")
            forecast = self._parse_value(cols[6].text if len(cols) > 6 else "")
            actual = self._parse_value(cols[7].text if len(cols) > 7 else "")
            
            # Today's date as fallback
            today = datetime.now(timezone.utc).date().isoformat()
            
            event = EconomicEvent(
                name=event_name,
                country=country,
                time=time_str,
                impact=impact,
                forecast=forecast,
                previous=previous,
                actual=actual,
                date=date_str or today
            )
            
            return event
            
        except Exception as e:
            logger.debug(f"Error parsing row: {e}")
            return None
    
    def _parse_value(self, text: str) -> Optional[float]:
        """Parse a numeric value from text."""
        if not text or text == "N/A" or text == "-":
            return None
        
        try:
            # Remove common suffixes
            text = text.replace("K", "000").replace("M", "000000")
            text = re.sub(r'[^\d.-]', '', text)
            
            if not text:
                return None
            
            return float(text)
        except:
            return None
    
    def _is_high_impact_event(self, event: EconomicEvent) -> bool:
        """Check if this is a high-impact event for trading."""
        for country, event_names in self.HIGH_IMPACT_EVENTS.items():
            if event.country == country:
                for event_name in event_names:
                    if event_name.lower() in event.name.lower():
                        return True
        return False


# Fallback implementation if web scraping fails
# This uses a mock/cached approach
class EconomicCalendarSourceMock(EconomicCalendarSource):
    """Mock implementation for testing without web scraping."""
    
    async def collect(self) -> Dict[str, Any]:
        """Return mock economic calendar data."""
        logger.info("Using mock economic calendar (web scraping unavailable)")
        
        # Mock some high-impact upcoming events
        mock_events = [
            {
                "name": "US CPI m/m",
                "country": "US",
                "time": "13:30 GMT",
                "impact": 3,
                "forecast": 0.2,
                "previous": 0.3,
                "actual": None,
                "date": datetime.now(timezone.utc).date().isoformat()
            },
            {
                "name": "US Non-Farm Payrolls",
                "country": "US",
                "time": "13:30 GMT",
                "impact": 3,
                "forecast": 200000,
                "previous": 186000,
                "actual": None,
                "date": (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
            },
            {
                "name": "ECB Interest Rate Decision",
                "country": "EUR",
                "time": "12:45 GMT",
                "impact": 3,
                "forecast": 5.5,
                "previous": 5.5,
                "actual": None,
                "date": (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
            }
        ]
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "upstream": mock_events,
            "released": [],
            "high_impact_upcoming": mock_events,
            "total_upcoming": 3,
            "errors": ["Mock data - web scraping not available"]
        }
