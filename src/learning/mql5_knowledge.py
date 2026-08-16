"""
MQL5 Knowledge RAG (#22) — local, offline, embedded knowledge base of external
trading/indicator knowledge (primarily https://www.mql5.com/en/docs), used by the
CONTINUAL researcher (#32) to ground per-symbol tuning and technique discovery.

Deliberately dependency-light and editor-agnostic (portable for the standalone /
VPS build), mirroring src/learning/knowledge_store.py:
  - chromadb embedded PersistentClient (local disk, no server, offline at query time)
  - local MiniLM sentence-transformers embedder (downloads once, then cached)

SEPARATE collection ("external_trading_knowledge") so this never mixes with the
trade-experience RAG or the whale RAG.

The Playwright/Chromium crawler is OPTIONAL and non-fatal: if playwright isn't
installed, the store still works for querying whatever has been indexed (and a
small built-in seed of indicator-tuning facts is always available so the
researcher has something to reason over on day one, before any crawl).

Indexing pipeline:
  crawl (optional) -> chunk pages -> embed -> upsert with provenance
  (source_url, title, section, fetched_at) so retrieved knowledge is citable.

Query API:
  research(query, n_results) -> [{id, text, metadata{source_url,title,...}, similarity}]
  research_indicator(indicator, param) -> targeted lookup for tuning grounding
"""

from __future__ import annotations

import os
import time
import hashlib
import math
import logging
from typing import Optional
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings
# embedding_functions imported lazily (pulls torch); see knowledge_store.py note.

logger = logging.getLogger("mql5_knowledge")

EMBED_MODEL = os.getenv("KNOWLEDGE_EMBED_MODEL", "all-MiniLM-L6-v2")


class _SafeEmbeddingFunction:
    """Fallback embedder — canonical impl in src.learning.chroma_client.SafeEmbeddingFunction."""

    def __new__(cls, dim: int = 20):
        from src.learning.chroma_client import SafeEmbeddingFunction
        return SafeEmbeddingFunction(dim=dim)


# Curated allow-list of sources to crawl (mql5 docs first; extend deliberately).
DEFAULT_SOURCES = [
    "https://www.mql5.com/en/docs/indicators/imacd",
    "https://www.mql5.com/en/docs/indicators/iosma",
    "https://www.mql5.com/en/docs/indicators/iatr",
    "https://www.mql5.com/en/docs/indicators/ibullspower",
    "https://www.mql5.com/en/docs/indicators/ibearspower",
    "https://www.mql5.com/en/docs/indicators/ima",     # moving average / EMA
    "https://www.mql5.com/en/docs/indicators/irsi",
    "https://www.incrediblecharts.com/indicators/elder_ray_index.php", # Elder-Ray context
    "https://www.babypips.com/learn/forex/summary-common-chart-indicators", # Divergence / visual signals
    "https://www.tradingview.com/pine-script-reference/v6/", # Custom logic construction
]

# Built-in seed knowledge so the researcher can reason on day one (before any
# crawl) about how the confluence indicators respond to their parameters. These
# are the tuning semantics the trader called out (faster/slower = speed of signal).
SEED_KNOWLEDGE = [
    ("osma_speed", "indicator tuning: OsMA",
     "OsMA (Moving Average of Oscillator) = MACD main line minus its signal line "
     "(the MACD histogram). Its responsiveness is set by fast EMA, slow EMA and "
     "signal periods. SMALLER fast/slow periods make OsMA react FASTER to price "
     "(earlier zero-crosses, more signals, more noise/whipsaw). LARGER periods make "
     "it SLOWER/smoother (fewer, laggier but cleaner crosses). Raising the signal "
     "period smooths the histogram. To catch a cross earlier, reduce fast; to reduce "
     "false crosses, increase slow/signal."),
    ("atr_usage", "indicator tuning: ATR",
     "ATR (Average True Range) measures volatility, not direction. A SHORTER ATR "
     "period reacts faster to volatility changes (good for expansion detection); a "
     "LONGER period is smoother/more stable for baseline volatility. ATR is used to "
     "size stops/targets proportionally and to gate entries to a volatility band. "
     "'ATR expansion' = current ATR greater than the prior bar, indicating a move "
     "is picking up energy."),
    ("macd_align", "indicator tuning: MACD",
     "MACD main line above zero indicates bullish momentum regime; below zero "
     "bearish. Aligning an OsMA zero-cross entry with the MACD main line's side of "
     "zero filters counter-regime signals. Faster MACD periods = earlier but noisier."),
    ("bulls_bears_power", "indicator tuning: Bulls/Bears Power",
     "Bulls Power = High - EMA(period); Bears Power = Low - EMA(period). Bulls Power "
     "positive and rising = buyers in control; Bears Power crossing above zero from "
     "below = sellers losing control (bullish). Use the SAME EMA period as the trend "
     "EMA for consistency. They confirm the direction of an OsMA/MACD entry."),
    ("rsi_confirm", "indicator tuning: RSI",
     "RSI measures momentum 0-100. For a long entry, RSI supporting (rising, not yet "
     "overbought ~>70) confirms; entering longs at exhausted RSI risks buying the top. "
     "Shorter RSI period = more responsive/noisier."),
]


def _resolve_data_dir() -> str:
    env = os.getenv("CRYPTO_DATA_DIR")
    if env:
        return env
    try:
        from src import config
        return config.DATA_DIR
    except Exception:
        return os.path.join(os.getcwd(), "data")


def _chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = " ".join((text or "").split())
    if len(text) <= size:
        return [text] if text else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


class MQL5Knowledge:
    """Embedded, local, offline RAG of external trading/indicator knowledge."""

    COLLECTION_NAME = "external_trading_knowledge"

    def __init__(self, persist_directory: Optional[str] = None, seed: bool = True):
        base = persist_directory or os.path.join(_resolve_data_dir(), "chromadb_store")
        os.makedirs(base, exist_ok=True)
        self.persist_dir = base
        from src.learning.chroma_client import get_shared_chroma_client
        self.client = get_shared_chroma_client()
        # Avoid Native Access Violation (c10.dll crash) on Windows by skipping torch entirely
        if os.name == "nt" or os.environ.get("USE_SAFE_EMBEDDER", "1") == "1":
            logger.warning("Windows host detected: using safe hash embedder to avoid torch/c10.dll native crash.")
            self._embedder = _SafeEmbeddingFunction(dim=20)
        else:
            try:
                from chromadb.utils import embedding_functions  # lazy: pulls torch
                self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=EMBED_MODEL
                )
            except Exception as e:
                logger.warning(f"SentenceTransformerEmbeddingFunction unavailable ({e}); using safe fallback")
                self._embedder = _SafeEmbeddingFunction(dim=20)
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME, embedding_function=self._embedder,
                metadata={"description": "External trading/indicator knowledge (mql5 docs etc.)"}
            )
        except Exception:
            try:
                self.client.delete_collection(self.COLLECTION_NAME)
            except Exception:
                pass
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME, embedding_function=self._embedder,
                metadata={"description": "External trading/indicator knowledge (mql5 docs etc.)"}
            )
        if seed:
            try:
                if self.collection.count() == 0:
                    self._seed()
            except Exception:
                pass
        logger.info(f"MQL5Knowledge ready at {base}")

    def _seed(self):
        for key, title, text in SEED_KNOWLEDGE:
            self.index_document(text, source_url="builtin://seed", title=title,
                                section=key, doc_id=f"seed_{key}")
        logger.info(f"MQL5Knowledge seeded with {len(SEED_KNOWLEDGE)} built-in facts")

    def index_document(self, text: str, source_url: str, title: str = "",
                       section: str = "", doc_id: Optional[str] = None):
        """Chunk + embed + upsert a document with provenance for citation."""
        chunks = _chunk(text)
        if not chunks:
            return 0
        ids, docs, metas = [], [], []
        for idx, ch in enumerate(chunks):
            base_id = doc_id or hashlib.md5(source_url.encode()).hexdigest()[:12]
            ids.append(f"{base_id}_{idx}")
            docs.append(ch)
            metas.append({
                "source_url": source_url, "title": title, "section": section,
                "chunk": idx, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "ts": time.time(),
            })
        self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(chunks)

    def research(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic recall of external knowledge with provenance for citation."""
        if self.collection.count() == 0:
            return []
        res = self.collection.query(
            query_texts=[query], n_results=min(n_results, self.collection.count()),
            include=["documents", "metadatas", "distances"])
        out = []
        if res.get("ids") and res["ids"][0]:
            for i in range(len(res["ids"][0])):
                out.append({
                    "id": res["ids"][0][i],
                    "text": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "similarity": 1.0 - (res["distances"][0][i] if res.get("distances") else 0),
                })
        return out

    def research_indicator(self, indicator: str, param: str = "") -> list[dict]:
        """Targeted lookup for grounding a specific indicator/parameter tuning."""
        q = f"how does the {param} parameter change the {indicator} indicator behaviour speed responsiveness".strip()
        return self.research(q, n_results=3)

    def count(self) -> int:
        return self.collection.count()

    # ── optional crawler (Playwright/Chromium) — non-fatal if unavailable ──
    def search_and_crawl(self, query: str, num_links: int = 2) -> dict:
        """Search DuckDuckGo via Chromium and crawl the top trusted links."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            return {"error": "playwright not installed"}
        
        urls_to_crawl = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                import urllib.parse
                safe_query = urllib.parse.quote(query)
                page.goto(f"https://html.duckduckgo.com/html/?q={safe_query}", timeout=30000)
                links = page.query_selector_all("a.result__snippet")
                for link in links[:num_links]:
                    href = link.get_attribute("href")
                    if href and "http" in href:
                        if "uddg=" in href:
                            href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                        urls_to_crawl.append(href)
            except Exception as e:
                logger.warning(f"search skip {query}: {e}")
            browser.close()
            
        if urls_to_crawl:
            self._append_to_data_sources(urls_to_crawl)
            return self.crawl_and_index(urls=urls_to_crawl)
        return {"crawled": 0}

    def _append_to_data_sources(self, urls: list[str]):
        """Store newly discovered sources in DATA_SOURCES.md for github tracking."""
        try:
            ds_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA_SOURCES.md")
            if os.path.exists(ds_path):
                with open(ds_path, "a") as f:
                    for url in set(urls):
                        f.write(f"\n- Auto-discovered (via Chromium Search): {url}")
        except Exception:
            pass

    def crawl_and_index(self, urls: Optional[list[str]] = None, rate_limit_s: float = 2.0) -> dict:
        """
        Crawl the allow-listed URLs with Playwright/Chromium (headless), extract
        readable text, chunk + index. Optional heavy dependency; returns a summary.
        Politely rate-limited. Safe to call repeatedly (upsert de-dupes by URL).
        """
        urls = urls or DEFAULT_SOURCES
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            msg = (f"Playwright not installed ({e}). Skipping crawl; querying uses "
                   f"seed + previously-indexed content. Install: pip install playwright "
                   f"&& playwright install chromium")
            logger.warning(msg)
            return {"crawled": 0, "indexed_chunks": 0, "skipped": True, "reason": msg}
        indexed = 0
        crawled = 0
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            for url in urls:
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    title = page.title()
                    # extract main text; fall back to body
                    text = page.inner_text("body")
                    n = self.index_document(text, source_url=url, title=title,
                                            section="mql5_docs")
                    indexed += n
                    crawled += 1
                    logger.info(f"indexed {n} chunks from {url}")
                    time.sleep(rate_limit_s)
                except Exception as e:
                    logger.warning(f"crawl skip {url}: {e}")
            browser.close()
        return {"crawled": crawled, "indexed_chunks": indexed, "skipped": False}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    kb = MQL5Knowledge()
    print(f"chunks: {kb.count()}")
    print("\nresearch 'how do I make OsMA react faster to catch the cross earlier':")
    for h in kb.research("how do I make OsMA react faster to catch the cross earlier", 3):
        print(f"  [{h['similarity']:.2f}] {h['metadata'].get('title')}: {h['text'][:100]}...")
    # optional: crawl the mql5 docs if playwright is available
    print("\nattempting crawl (optional):")
    print(kb.crawl_and_index())
