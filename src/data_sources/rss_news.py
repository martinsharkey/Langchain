"""
Free RSS news source — real headlines with NO API key required.

Pulls public RSS feeds (Yahoo Finance, CoinDesk, etc.) for gold/crypto/FX/macro
context. This gives the research layer genuine live news even without a NEWSAPI
key. Returns structured headlines; never fabricates data (empty on failure).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.utils.logger import get_logger

logger = get_logger("rss_news")

# Key-free public RSS feeds, tagged by relevance.
FEEDS = {
    "markets": "https://finance.yahoo.com/news/rssindex",
    "crypto": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "gold": "https://www.investing.com/rss/commodities_Gold.rss",
    "forex": "https://www.investing.com/rss/news_1.rss",
    "economy": "https://www.investing.com/rss/news_14.rss",
}

# lightweight keyword tags to help downstream relevance filtering
SYMBOL_KEYWORDS = {
    "XAUUSD": ["gold", "xau", "bullion", "fed", "inflation", "dollar", "treasury"],
    "BTCUSD": ["bitcoin", "btc", "crypto"],
    "ETHUSD": ["ethereum", "eth", "crypto"],
    "EURUSD": ["euro", "ecb", "eurozone", "dollar"],
}


class RSSNewsSource:
    def __init__(self, timeout: int = 8, cache_seconds: int = 300):
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self._cache = None
        self._cache_at = 0.0

    def available(self) -> bool:
        try:
            import feedparser  # noqa
            return True
        except Exception:
            return False

    def fetch(self, max_per_feed: int = 8) -> list[dict]:
        """Return recent headlines across all feeds (cached)."""
        now = time.time()
        if self._cache is not None and (now - self._cache_at) < self.cache_seconds:
            return self._cache
        try:
            import feedparser
        except Exception as e:
            logger.warning(f"feedparser unavailable: {e}")
            return []

        items = []
        for tag, url in FEEDS.items():
            try:
                d = feedparser.parse(url)
                for e in d.entries[:max_per_feed]:
                    title = getattr(e, "title", "")
                    items.append({
                        "tag": tag,
                        "title": title,
                        "link": getattr(e, "link", ""),
                        "published": getattr(e, "published", ""),
                    })
            except Exception as ex:
                logger.debug(f"rss feed {tag} failed: {ex}")
        self._cache = items
        self._cache_at = now
        logger.info(f"RSS news fetched: {len(items)} headlines across {len(FEEDS)} feeds")
        return items

    def headlines_for(self, base_symbol: str, limit: int = 10) -> list[dict]:
        """Headlines relevant to a symbol (keyword-filtered), newest first."""
        kws = SYMBOL_KEYWORDS.get(base_symbol.upper(), [])
        items = self.fetch()
        if not kws:
            return items[:limit]
        rel = [it for it in items if any(k in it["title"].lower() for k in kws)]
        return (rel or items)[:limit]

    def status(self) -> dict:
        items = self.fetch()
        return {
            "available": bool(items),
            "count": len(items),
            "feeds": list(FEEDS.keys()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sample": [it["title"] for it in items[:5]],
        }
