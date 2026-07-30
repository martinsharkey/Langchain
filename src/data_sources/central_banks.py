"""
Central Bank Data Source — Statements and sentiment from major central banks.

Collects:
- Federal Reserve (US)
- European Central Bank (ECB)
- Bank of England (BOE)
- Bank of Canada (BOC)

Tracks sentiment: hawkish, neutral, dovish
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger("data_sources.central_banks")


class CentralBankSource:
    """
    Collects central bank statements and analyzes sentiment.
    """
    
    # Central bank URLs
    SOURCES = {
        "fed": {
            "url": "https://www.federalreserve.gov/newsevents/news/monpress/",
            "name": "Federal Reserve",
            "country": "US"
        },
        "ecb": {
            "url": "https://www.ecb.europa.eu/press/govc_mpr/html/index.en.html",
            "name": "European Central Bank",
            "country": "EUR"
        },
        "boe": {
            "url": "https://www.bankofengland.co.uk/news/news-stories",
            "name": "Bank of England",
            "country": "GBP"
        },
        "boc": {
            "url": "https://www.bankofcanada.ca/news/",
            "name": "Bank of Canada",
            "country": "CAD"
        }
    }
    
    # Sentiment keywords
    HAWKISH_KEYWORDS = [
        "rate hike", "raise rates", "tightening",
        "inflation risk", "restrictive",
        "higher for longer", "hold firm",
        "remain vigilant"
    ]
    
    DOVISH_KEYWORDS = [
        "rate cut", "lower rates", "easing",
        "pause", "hold steady", "data dependent",
        "inflation moderating", "price pressures easing"
    ]
    
    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=30)
        logger.info("CentralBankSource initialized")
    
    async def collect(self) -> Dict[str, Any]:
        """
        Collect central bank data.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "fed": {"latest_statement": ..., "sentiment": ..., "rate": ...},
                "ecb": {...},
                "boe": {...},
                "boc": {...},
                "errors": [str, ...]
            }
        """
        logger.info("Collecting central bank data...")
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                tasks = [
                    self._collect_source(session, key, source)
                    for key, source in self.SOURCES.items()
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "errors": []
                }
                
                for (key, _), result in zip(self.SOURCES.items(), results):
                    if isinstance(result, Exception):
                        logger.warning(f"Error collecting {key}: {result}")
                        data["errors"].append(f"{key}: {str(result)}")
                        data[key] = {"sentiment": "neutral", "latest_statement": None}
                    else:
                        data[key] = result
                
                logger.info("Central bank data collection completed")
                return data
        
        except Exception as e:
            logger.error(f"Error collecting central bank data: {e}")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fed": {"sentiment": "neutral"},
                "ecb": {"sentiment": "neutral"},
                "boe": {"sentiment": "neutral"},
                "boc": {"sentiment": "neutral"},
                "errors": [str(e)]
            }
    
    async def _collect_source(
        self,
        session: aiohttp.ClientSession,
        key: str,
        source: Dict[str, str]
    ) -> Dict[str, Any]:
        """Collect data from a specific central bank."""
        try:
            async with session.get(source["url"]) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._parse_statement(key, html)
                else:
                    logger.warning(f"{key} returned status {response.status}")
                    return {"sentiment": "neutral", "latest_statement": None}
        
        except asyncio.TimeoutError:
            logger.warning(f"Timeout collecting {key}")
            return {"sentiment": "neutral", "latest_statement": None}
        
        except Exception as e:
            logger.warning(f"Error collecting {key}: {e}")
            return {"sentiment": "neutral", "latest_statement": None}
    
    def _parse_statement(self, key: str, html: str) -> Dict[str, Any]:
        """Parse latest statement from HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract first news/statement item
            statement_text = ""
            
            if key == "fed":
                # Find FOMC statement or monetary policy news
                items = soup.find_all('div', {'class': ['news-item', 'headline']})
                if items:
                    statement_text = items[0].get_text()
            
            elif key == "ecb":
                # ECB governing council decisions
                items = soup.find_all('div', {'class': ['news', 'news-item']})
                if items:
                    statement_text = items[0].get_text()
            
            elif key == "boe":
                # BOE monetary policy news
                items = soup.find_all('article')
                if items:
                    statement_text = items[0].get_text()
            
            elif key == "boc":
                # BOC news releases
                items = soup.find_all('div', {'class': ['news-item']})
                if items:
                    statement_text = items[0].get_text()
            
            # Analyze sentiment
            sentiment = self._analyze_sentiment(statement_text)
            
            return {
                "sentiment": sentiment,
                "latest_statement": statement_text[:200] if statement_text else None,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            logger.debug(f"Error parsing {key} statement: {e}")
            return {"sentiment": "neutral", "latest_statement": None}
    
    def _analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment from text."""
        text_lower = text.lower()
        
        hawkish_count = sum(1 for keyword in self.HAWKISH_KEYWORDS if keyword in text_lower)
        dovish_count = sum(1 for keyword in self.DOVISH_KEYWORDS if keyword in text_lower)
        
        if hawkish_count > dovish_count:
            return "hawkish"
        elif dovish_count > hawkish_count:
            return "dovish"
        else:
            return "neutral"

