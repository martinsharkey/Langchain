"""
News Aggregator Data Source — Real-time financial news from multiple APIs.

Collects news from:
- NewsAPI.org (requires API key)
- Built-in news parsing (fallback)

Focuses on:
- Gold/precious metals news
- USD strength news
- Interest rate news
- Central bank announcements
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
import aiohttp
import os

logger = logging.getLogger("data_sources.news_aggregator")


class NewsAggregatorSource:
    """
    Aggregates financial news from multiple sources.
    Focuses on news relevant to XAUUSD trading.
    """
    
    # API configuration
    NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
    NEWSAPI_URL = "https://newsapi.org/v2/everything"
    
    # Search terms for XAUUSD-relevant news
    GOLD_KEYWORDS = [
        "gold prices",
        "XAUUSD",
        "precious metals",
        "gold demand",
        "gold mining"
    ]
    
    USD_KEYWORDS = [
        "US dollar",
        "dollar strength",
        "USD",
        "Federal Reserve",
        "interest rates",
        "inflation",
        "CPI"
    ]
    
    SAFE_HAVEN_KEYWORDS = [
        "market volatility",
        "geopolitical",
        "recession",
        "economic crisis",
        "stock market crash"
    ]
    
    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.has_api_key = bool(self.NEWSAPI_KEY)
        
        if self.has_api_key:
            logger.info("NewsAggregatorSource initialized with API key")
        else:
            logger.warning("NewsAggregatorSource initialized WITHOUT API key (mock mode)")
    
    async def collect(self) -> Dict[str, Any]:
        """
        Collect financial news relevant to XAUUSD.
        
        Returns:
            {
                "timestamp": ISO timestamp,
                "gold_news": [{"title": ..., "source": ..., "url": ...}, ...],
                "usd_news": [...],
                "sentiment_news": [...],
                "total_articles": int,
                "errors": [str, ...]
            }
        """
        logger.info("Collecting financial news...")
        
        if not self.has_api_key:
            return await self._collect_mock()
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Collect from all keywords in parallel
                tasks = [
                    self._search_news(session, keywords, category)
                    for keywords, category in [
                        (self.GOLD_KEYWORDS, "gold"),
                        (self.USD_KEYWORDS, "usd"),
                        (self.SAFE_HAVEN_KEYWORDS, "sentiment")
                    ]
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                news_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "gold_news": results[0] if not isinstance(results[0], Exception) else [],
                    "usd_news": results[1] if not isinstance(results[1], Exception) else [],
                    "sentiment_news": results[2] if not isinstance(results[2], Exception) else [],
                    "total_articles": 0,
                    "errors": []
                }
                
                # Count articles and collect errors
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.warning(f"Error collecting category {i}: {result}")
                        news_data["errors"].append(str(result))
                    else:
                        news_data["total_articles"] += len(result)
                
                logger.info(f"Collected {news_data['total_articles']} news articles")
                return news_data
        
        except Exception as e:
            logger.error(f"Error collecting news: {e}")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gold_news": [],
                "usd_news": [],
                "sentiment_news": [],
                "total_articles": 0,
                "errors": [str(e)]
            }
    
    async def _search_news(
        self,
        session: aiohttp.ClientSession,
        keywords: List[str],
        category: str
    ) -> List[Dict[str, Any]]:
        """Search for news by keywords."""
        articles = []
        
        for keyword in keywords:
            try:
                params = {
                    "q": keyword,
                    "apiKey": self.NEWSAPI_KEY,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 10  # 10 articles per keyword
                }
                
                async with session.get(self.NEWSAPI_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for article in data.get("articles", []):
                            articles.append({
                                "title": article.get("title"),
                                "source": article.get("source", {}).get("name"),
                                "url": article.get("url"),
                                "published_at": article.get("publishedAt"),
                                "category": category,
                                "keyword": keyword
                            })
                    else:
                        logger.warning(f"NewsAPI returned status {response.status}")
            
            except Exception as e:
                logger.warning(f"Error searching for '{keyword}': {e}")
        
        # Remove duplicates and limit
        unique_articles = {}
        for article in articles:
            key = article.get("url")
            if key not in unique_articles:
                unique_articles[key] = article
        
        return list(unique_articles.values())[:20]  # Top 20 articles
    
    async def _collect_mock(self) -> Dict[str, Any]:
        """Return mock news data."""
        logger.info("Using mock news data (API key not available)")
        
        mock_articles = [
            {
                "title": "Gold prices rise amid Fed uncertainty",
                "source": "Bloomberg",
                "url": "https://example.com/news1",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "category": "gold",
                "keyword": "gold prices"
            },
            {
                "title": "US dollar weakens as inflation concerns mount",
                "source": "Reuters",
                "url": "https://example.com/news2",
                "published_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "category": "usd",
                "keyword": "US dollar"
            },
            {
                "title": "Market volatility increases: investors flee to safe havens",
                "source": "CNBC",
                "url": "https://example.com/news3",
                "published_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "category": "sentiment",
                "keyword": "market volatility"
            }
        ]
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gold_news": [mock_articles[0]],
            "usd_news": [mock_articles[1]],
            "sentiment_news": [mock_articles[2]],
            "total_articles": 3,
            "errors": ["Mock data - API key not configured"]
        }
