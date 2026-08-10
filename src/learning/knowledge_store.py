"""
Local Knowledge Store — portable, embedded RAG for accumulated trading knowledge.

Deliberately dependency-light and editor-agnostic so it works both inside the
current repo and later as a STANDALONE APPLICATION outside VS Code. It uses only:
  - chromadb (embedded PersistentClient, local disk — no server, no network)
  - the sentence-transformers default embedder that ships with chromadb

This is where durable, human-confirmed findings, corrections, and decisions live
so the bot (and any future app build) can semantically recall them locally at
lightning speed, with NO Kilo / VS Code / cloud dependency.

Categories (metadata.kind):
  finding    — an empirical discovery (e.g. whale tx dates map to 1m BTCUSD trades)
  correction — a fix to a previously wrong belief (kept so we don't regress)
  decision   — an agreed choice (e.g. WebSocket-only feed)
  note       — anything else worth recalling

Storage path resolves from CRYPTO_DATA_DIR env or src.config.DATA_DIR, falling
back to ./data — so the exact same file works when lifted out of this repo.
"""

from __future__ import annotations

import os
import time
import hashlib
import logging
from typing import Optional
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger("knowledge_store")

# Local, offline sentence-transformers embedder (downloads once, then cached).
# Pinned explicitly so the standalone app build is deterministic and has no
# network dependency at query time. ~90MB one-time model download.
EMBED_MODEL = os.getenv("KNOWLEDGE_EMBED_MODEL", "all-MiniLM-L6-v2")


class _SafeEmbeddingFunction:
    """Fallback embedding function that avoids torch/sentence-transformers."""

    def __init__(self, dim: int = 20):
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:
        import math, hashlib
        out: list[list[float]] = []
        for text in input:
            h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
            vec = [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


def _resolve_data_dir() -> str:
    """Portable data dir: env override -> src.config -> ./data."""
    env = os.getenv("CRYPTO_DATA_DIR")
    if env:
        return env
    try:
        from src import config
        return config.DATA_DIR
    except Exception:
        return os.path.join(os.getcwd(), "data")


class KnowledgeStore:
    """Embedded, local, portable semantic knowledge store (no server)."""

    COLLECTION_NAME = "trading_knowledge_rag"

    def __init__(self, persist_directory: Optional[str] = None):
        base = persist_directory or os.path.join(_resolve_data_dir(), "chromadb_store")
        os.makedirs(base, exist_ok=True)
        self.persist_dir = base
        self.client = chromadb.PersistentClient(
            path=base, settings=Settings(anonymized_telemetry=False)
        )
        # Explicit local MiniLM embedder (offline after first download).
        try:
            self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBED_MODEL
            )
        except Exception as e:
            logger.warning(f"SentenceTransformerEmbeddingFunction unavailable ({e}); using safe fallback")
            self._embedder = _SafeEmbeddingFunction(dim=20)
        try:
            self.collection = self.client.get_collection(
                self.COLLECTION_NAME, embedding_function=self._embedder
            )
        except Exception:
            self.collection = self.client.create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self._embedder,
                metadata={"description": "Durable trading knowledge: findings, corrections, decisions"},
            )
        logger.info(f"KnowledgeStore ready ({self.collection.count()} entries) at {base}")

    def remember(self, text: str, kind: str = "note", topic: str = "",
                 source: str = "assistant", confidence: float = 1.0,
                 key: Optional[str] = None) -> str:
        """
        Store a piece of knowledge. `key` makes it idempotent (re-remembering the
        same key updates in place). Chroma computes the embedding from `text`.
        """
        eid = key or hashlib.md5(f"{kind}:{topic}:{text}".encode()).hexdigest()[:16]
        self.collection.upsert(
            ids=[eid],
            documents=[text],
            metadatas=[{
                "kind": kind,
                "topic": topic,
                "source": source,
                "confidence": float(confidence),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "ts": time.time(),
            }],
        )
        logger.info(f"knowledge[{kind}] stored ({eid}): {text[:80]}")
        return eid

    def recall(self, query: str, n_results: int = 5,
               kind: Optional[str] = None) -> list[dict]:
        """Semantic recall of stored knowledge (optionally filtered by kind)."""
        if self.collection.count() == 0:
            return []
        where = {"kind": kind} if kind else None
        res = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, self.collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
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

    def count(self) -> int:
        return self.collection.count()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ks = KnowledgeStore()

    # The corrected finding (this supersedes the earlier wrong claim).
    ks.remember(
        key="whale_tx_maps_to_1m_btcusd_trades",
        kind="correction",
        topic="whale->btcusd wave",
        source="trader_confirmed",
        confidence=1.0,
        text=(
            "CORRECTION: The earlier claim that 'no single whale wallet movement "
            "produced a successful BTCUSD move' was WRONG. We analysed whale "
            "transaction DATES and TIMES and mapped them to single 1-minute BTCUSD "
            "trades on the SAME day. Interpretation: wallets can be massive, but the "
            "flow that actually HITS the symbol is broken into smaller (~$1M) chunks. "
            "A ~$6M sale mapped to ~6 large M1 candles. This is the chunked-sale wave "
            "and it IS tradeable: position at the event, ride ~N chunks, trail out. "
            "Whale-event timestamps DO align with real 1m candle moves."
        ),
    )
    ks.remember(
        key="feed_websocket_only",
        kind="decision",
        topic="cryptorti feed",
        source="danny",
        text=("Authoritative CryptoRTI source = mTLS WebSocket, event-driven push "
              "only. Do NOT poll S3 / dashboard.json in the hot path. Danny pushes "
              "a signal only when an event happens with enough data to act on."),
    )

    print(f"knowledge entries: {ks.count()}")
    print("\nrecall 'did whale movements cause btc trades?':")
    for h in ks.recall("did whale wallet movements cause real btcusd trades", n_results=3):
        print(f"  [{h['similarity']:.2f}] ({h['metadata']['kind']}) {h['text'][:90]}...")
