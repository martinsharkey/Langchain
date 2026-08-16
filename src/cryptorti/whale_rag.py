"""
Whale-Event Pattern RAG — retrievable memory of the whale->candle wave pattern.

The correlation miner (correlation_miner.py) produces an aggregate table in
data/cryptorti_correlation.json. That table is great for exact profile lookup,
but it is NOT retrievable by similarity and it is NOT where the bot's learning
lives. This module stores each whale-event profile (and human-confirmed
observations, like the "$6M sale -> ~6 large 1M candles" case the trader saw and
verified against MT5) as vectors in a ChromaDB collection, so the live predictor
can:

  1. Look up the closest historical whale profile for a live event
     (by size / exchange / direction) even when there is no exact match, and
  2. Learn continuously — real wave-trade outcomes update the stored patterns.

This is deliberately a SEPARATE collection from the XAUUSD indicator patterns in
src/learning/vector_store.py so the two RAG spaces don't mix.

Embedding features (4 dims — EVENT IDENTITY only, all normalised ~0..1):
  0: size bucket ordinal        (<1M=0.1 .. 10M+=1.0)
  1: log-scaled usd             (0..1 over ~$100k..$50M)
  2: direction                  (sell=0.0, buy=1.0)
  3: exchange ordinal           (stable hash bucket, 0..1)

The learned RESPONSE (hit_rate, peak_bps, n_large chunk count, lag) is stored in
metadata, NOT in the embedding — so similarity search matches on the shape of the
EVENT (which live signals have) and returns the historical response as the answer.
Mixing response into the vector made high-confidence confirmed records (100% hit,
extreme values) look "far" from a neutral query and drop out of results.
"""

from __future__ import annotations

import os
import json
import math
import hashlib
import logging
from typing import Optional
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings

from src import config

logger = logging.getLogger("cryptorti.whale_rag")

class _SafeEmbeddingFunction:
    """Fallback embedding function that avoids torch/sentence-transformers.

    Canonical hash-embed math lives in src.learning.chroma_client.SafeEmbeddingFunction.
    This thin subclass preserves the existing collection embedder name
    ('safe_hash_embedder_dim4') so the persisted whale_wave_patterns collection stays
    compatible."""

    def __init__(self, dim: int = 4):
        from src.learning.chroma_client import SafeEmbeddingFunction
        self._impl = SafeEmbeddingFunction(dim=dim)
        self.dim = dim

    def name(self) -> str:
        return "safe_hash_embedder_dim4"

    def __call__(self, input: list) -> list:
        return self._impl(input)


_SIZE_ORDINAL = {"<1M": 0.1, "1-2M": 0.3, "2-5M": 0.5, "5-10M": 0.75, "10M+": 1.0}


def _size_bucket(usd: float) -> str:
    if usd >= 10_000_000:
        return "10M+"
    if usd >= 5_000_000:
        return "5-10M"
    if usd >= 2_000_000:
        return "2-5M"
    if usd >= 1_000_000:
        return "1-2M"
    return "<1M"


def _exchange_ordinal(exchange: str) -> float:
    """Stable 0..1 bucket for an exchange name (so similar names map consistently)."""
    if not exchange or exchange == "?":
        return 0.5
    h = int(hashlib.md5(exchange.lower().encode()).hexdigest()[:8], 16)
    return (h % 1000) / 1000.0


class WhalePatternRAG:
    """ChromaDB-backed retrievable store of whale-event -> BTCUSD wave patterns."""

    COLLECTION_NAME = "whale_wave_patterns"
    PERSIST_DIR = os.path.join(config.DATA_DIR, "chromadb_store")

    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_dir = persist_directory or self.PERSIST_DIR
        os.makedirs(self.persist_dir, exist_ok=True)
        from src.learning.chroma_client import get_shared_chroma_client
        self.client = get_shared_chroma_client()
        
        # Avoid Native Access Violation (c10.dll crash) on Windows by skipping torch entirely
        _safe_embed = None
        if os.name == "nt" or os.environ.get("USE_SAFE_EMBEDDER", "1") == "1":
            _safe_embed = _SafeEmbeddingFunction(dim=4)

        try:
            self.collection = self.client.get_collection(
                self.COLLECTION_NAME,
                embedding_function=_safe_embed
            )
            logger.info("Loaded whale pattern store")
        except Exception:
            try:
                self.collection = self.client.create_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=_safe_embed,
                    metadata={"description": "CryptoRTI whale-event -> BTCUSD wave patterns", "hnsw:space": "cosine"},
                )
            except Exception:
                try:
                    self.client.delete_collection(self.COLLECTION_NAME)
                except:
                    pass
                self.collection = self.client.create_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=_safe_embed,
                    metadata={"description": "CryptoRTI whale-event -> BTCUSD wave patterns", "hnsw:space": "cosine"},
                )
            logger.info("Created new whale pattern store")

    # ─── Embedding (EVENT IDENTITY only) ──────────────────────
    def _vector(self, size_bucket: str, usd: float, direction: str,
                exchange: str) -> list[float]:
        """Embed the EVENT shape only. Response metrics live in metadata."""
        log_usd = math.log10(max(usd, 1))
        log_norm = min(max((log_usd - 5.0) / (7.7 - 5.0), 0.0), 1.0)  # ~1e5..~5e7
        return [
            _SIZE_ORDINAL.get(size_bucket, 0.5),
            log_norm,
            1.0 if direction == "buy" else 0.0,
            _exchange_ordinal(exchange),
        ]

    def _profile_id(self, profile: str, source: str) -> str:
        return hashlib.md5(f"{source}:{profile}".encode()).hexdigest()[:16]

    # ─── Store ────────────────────────────────────────────────
    def store_profile(self, profile: str, stats: dict, source: str = "miner") -> str:
        """
        Store one whale profile. `profile` is "size|exchange|direction"; `stats`
        is a correlation-table entry (hit_rate, avg_peak_bps, avg_n_large, ...).
        """
        parts = profile.split("|")
        size_bucket = parts[0] if parts else "<1M"
        exchange = parts[1] if len(parts) > 1 else "?"
        direction = stats.get("direction") or (parts[2] if len(parts) > 2 else "sell")
        # representative usd for the bucket (mid-ish)
        usd_repr = {"<1M": 750_000, "1-2M": 1_500_000, "2-5M": 3_500_000,
                    "5-10M": 7_500_000, "10M+": 15_000_000}.get(size_bucket, 1_000_000)

        hit = float(stats.get("hit_rate", 0) or 0)
        peak = float(stats.get("avg_peak_bps", 0) or 0)
        n_large = float(stats.get("avg_n_large", 0) or 0)
        lag = float(stats.get("avg_lag_min", 45) or 45)
        samples = int(stats.get("samples", 0) or 0)

        vec = self._vector(size_bucket, usd_repr, direction, exchange)
        pid = self._profile_id(profile, source)
        doc = (
            f"Whale {direction} {size_bucket} via {exchange}: historically draws "
            f"~{n_large:.1f} large BTCUSD candles, first ~{lag:.0f} min after the "
            f"event, peak move ~{peak:.0f} bps, hit rate {hit:.0f}% over {samples} "
            f"events. Spike-then-revert: target the peak, exit near lag+peak, do "
            f"not hold to window end."
        )
        self.collection.upsert(
            ids=[pid],
            embeddings=[vec],
            documents=[doc],
            metadatas=[{
                "profile": profile,
                "size_bucket": size_bucket,
                "exchange": exchange,
                "direction": direction,
                "hit_rate": hit,
                "avg_peak_bps": peak,
                "avg_n_large": n_large,
                "avg_lag_min": lag,
                "samples": samples,
                "source": source,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }],
        )
        return pid

    def store_confirmed_observation(
        self,
        usd: float,
        exchange: str,
        direction: str,
        n_large_candles: float,
        chunk_size_usd: float,
        timeframe: str,
        note: str,
        peak_bps: float = 0.0,
        lag_min: float = 30.0,
    ) -> str:
        """
        Store a HUMAN-CONFIRMED whale-event observation (verified against MT5),
        e.g. the trader's ~$6M sale that split into ~6 x $1M chunks drawing ~6
        large 1M candles. Marked source='confirmed' + hit_rate=100 so the
        predictor treats it as high-confidence ground truth.
        """
        size_bucket = _size_bucket(usd)
        vec = self._vector(size_bucket, usd, direction, exchange)
        pid = self._profile_id(
            f"CONFIRMED|{size_bucket}|{exchange}|{direction}|{n_large_candles}", "confirmed"
        )
        doc = (
            f"CONFIRMED (verified vs MT5): a ~${usd:,.0f} {direction} via {exchange} "
            f"split into ~{usd/max(chunk_size_usd,1):.0f} chunks of ~${chunk_size_usd:,.0f} "
            f"and drew ~{n_large_candles:.0f} large {timeframe} BTCUSD candles. {note}"
        )
        self.collection.upsert(
            ids=[pid],
            embeddings=[vec],
            documents=[doc],
            metadatas=[{
                "profile": f"{size_bucket}|{exchange}|{direction}",
                "size_bucket": size_bucket,
                "exchange": exchange,
                "direction": direction,
                "hit_rate": 100.0,
                "avg_peak_bps": peak_bps,
                "avg_n_large": float(n_large_candles),
                "avg_lag_min": lag_min,
                "chunk_size_usd": chunk_size_usd,
                "usd": usd,
                "timeframe": timeframe,
                "samples": 1,
                "source": "confirmed",
                "note": note,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }],
        )
        logger.info(f"Stored CONFIRMED whale observation: {doc}")
        return pid

    # ─── Retrieve ─────────────────────────────────────────────
    def lookup(self, usd: float, exchange: str, direction: str,
               n_results: int = 3) -> list[dict]:
        """
        Retrieve the closest historical whale patterns for a live event. Query
        embedding uses neutral response features so it matches on the EVENT shape
        (size/exchange/direction) and returns the learned response as metadata.
        """
        if self.collection.count() == 0:
            return []
        size_bucket = _size_bucket(usd)
        vec = self._vector(size_bucket, usd, direction, exchange)
        res = self.collection.query(
            query_embeddings=[vec],
            n_results=min(n_results, self.collection.count()),
            include=["metadatas", "documents", "distances"],
        )
        out = []
        if res.get("ids") and res["ids"][0]:
            for i in range(len(res["ids"][0])):
                out.append({
                    "id": res["ids"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "document": res["documents"][0][i] if res.get("documents") else "",
                    "similarity": 1.0 - (res["distances"][0][i] if res.get("distances") else 0),
                })
        return out

    def count(self) -> int:
        return self.collection.count()


def ingest_correlation_table(rag: Optional[WhalePatternRAG] = None,
                             table_path: Optional[str] = None) -> int:
    """
    Load data/cryptorti_correlation.json and store every profile in the RAG.
    Returns the number of profiles ingested.
    """
    rag = rag or WhalePatternRAG()
    path = table_path or os.path.join(config.DATA_DIR, "cryptorti_correlation.json")
    if not os.path.exists(path):
        logger.warning(f"correlation table not found at {path}")
        return 0
    with open(path) as f:
        payload = json.load(f)
    profiles = payload.get("profiles", {})
    n = 0
    for profile, stats in profiles.items():
        rag.store_profile(profile, stats, source="miner")
        n += 1
    logger.info(f"Ingested {n} whale profiles into RAG from {path}")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rag = WhalePatternRAG()

    # 1) Ingest the mined correlation table (37 profiles from 2,997 events).
    ingest_correlation_table(rag)

    # 2) Store the trader's CONFIRMED observation: ~$6M sell that split into
    #    ~6 x $1M chunks and drew ~6 large 1M BTCUSD candles (verified vs MT5).
    rag.store_confirmed_observation(
        usd=6_000_000,
        exchange="binance",
        direction="sell",
        n_large_candles=6,
        chunk_size_usd=1_000_000,
        timeframe="M1",
        note=(
            "Trader-observed and date-checked against MT5: a ~6M whale movement "
            "resulted in 6 x 1M-chunk sells that printed 6 large M1 candles. "
            "Confirms the chunked-sale wave: position at the event, ride ~6 "
            "chunks, trail as each completes."
        ),
        peak_bps=35.0,
        lag_min=28.0,
    )

    print(f"whale pattern store now holds {rag.count()} patterns")
    print("\nlookup for a live ~6M binance sell:")
    for hit in rag.lookup(6_000_000, "binance", "sell", n_results=3):
        m = hit["metadata"]
        print(f"  [{hit['similarity']:.2f}] {m['profile']} src={m['source']} "
              f"n_large={m['avg_n_large']} peak={m['avg_peak_bps']}bps "
              f"hit={m['hit_rate']}% lag={m['avg_lag_min']}min")
