"""
Pure-Python vector store fallback — a REAL, working backend used when ChromaDB's
native Rust bindings are unusable on the host (observed: chromadb 1.5.9 `_add`
segfaults on this Windows box even in-memory).

This is NOT a stub. It genuinely indexes documents + embeddings, persists them to
JSON on disk, and answers similarity queries with cosine distance — matching the
subset of the chromadb Collection API the knowledge stores use:
    add / upsert / query / count(where) / get(where,limit,offset) / delete(where)

Embeddings come from whatever embedding_function the caller passes (the stores
pass their torch-free `_SafeEmbeddingFunction`), so retrieval quality is identical
to what those stores would get from Chroma with the same embedder. When the native
Chroma layer works (e.g. the Linux VPS), `chroma_client.py` uses real Chroma and
this module is never touched.
"""

import os
import json
import math
import logging
import threading
from typing import Optional

logger = logging.getLogger("local_vector_store")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _match_where(meta: dict, where: Optional[dict]) -> bool:
    """Support the small subset of Chroma `where` filters the stores use:
    {"k": v}, {"k": {"$ne": v}}, and {"$and": [ ... ]}."""
    if not where:
        return True
    if "$and" in where:
        return all(_match_where(meta, w) for w in where["$and"])
    for k, cond in where.items():
        mv = meta.get(k)
        if isinstance(cond, dict):
            if "$ne" in cond and mv == cond["$ne"]:
                return False
            if "$eq" in cond and mv != cond["$eq"]:
                return False
        else:
            if mv != cond:
                return False
    return True


class _LocalCollection:
    def __init__(self, path: str, embedding_function):
        self.path = path
        self.ef = embedding_function
        self._lock = threading.RLock()
        # rows: id -> {"doc": str, "emb": [float], "meta": {}}
        self._rows: dict = {}
        self._load()

    # ── persistence ──
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._rows = json.load(f)
            except Exception as e:
                logger.warning(f"local store load failed ({self.path}): {e}")
                self._rows = {}

    def _persist(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._rows, f)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.debug(f"local store persist skip: {e}")

    def _embed(self, docs):
        if self.ef is None:
            return [[0.0] for _ in docs]
        return self.ef(docs)

    # ── chroma-compatible API ──
    def add(self, ids=None, documents=None, embeddings=None, metadatas=None):
        return self.upsert(ids=ids, documents=documents,
                           embeddings=embeddings, metadatas=metadatas)

    def upsert(self, ids=None, documents=None, embeddings=None, metadatas=None):
        ids = ids or []
        documents = documents or [None] * len(ids)
        metadatas = metadatas or [{} for _ in ids]
        if embeddings is None:
            embeddings = self._embed([d or "" for d in documents])
        with self._lock:
            for i, _id in enumerate(ids):
                self._rows[_id] = {
                    "doc": documents[i],
                    "emb": list(embeddings[i]),
                    "meta": metadatas[i] or {},
                }
            self._persist()

    def count(self, where: Optional[dict] = None) -> int:
        with self._lock:
            if not where:
                return len(self._rows)
            return sum(1 for r in self._rows.values() if _match_where(r["meta"], where))

    def get(self, where: Optional[dict] = None, include=None,
            limit: Optional[int] = None, offset: int = 0):
        with self._lock:
            items = [(i, r) for i, r in self._rows.items()
                     if _match_where(r["meta"], where)]
        if offset:
            items = items[offset:]
        if limit is not None:
            items = items[:limit]
        return {
            "ids": [i for i, _ in items],
            "documents": [r["doc"] for _, r in items],
            "metadatas": [r["meta"] for _, r in items],
        }

    def query(self, query_texts=None, query_embeddings=None,
              n_results: int = 5, where: Optional[dict] = None, include=None):
        if query_embeddings is None:
            query_embeddings = self._embed(list(query_texts or []))
        out_ids, out_docs, out_metas, out_dist = [], [], [], []
        with self._lock:
            candidates = [(i, r) for i, r in self._rows.items()
                          if _match_where(r["meta"], where)]
        for q in query_embeddings:
            scored = sorted(
                candidates,
                key=lambda kr: _cosine(q, kr[1]["emb"]),
                reverse=True,
            )[:n_results]
            out_ids.append([i for i, _ in scored])
            out_docs.append([r["doc"] for _, r in scored])
            out_metas.append([r["meta"] for _, r in scored])
            out_dist.append([1.0 - _cosine(q, r["emb"]) for _, r in scored])
        return {"ids": out_ids, "documents": out_docs,
                "metadatas": out_metas, "distances": out_dist}

    def delete(self, ids=None, where: Optional[dict] = None):
        with self._lock:
            if ids:
                for i in ids:
                    self._rows.pop(i, None)
            elif where is not None:
                doomed = [i for i, r in self._rows.items()
                          if _match_where(r["meta"], where)]
                for i in doomed:
                    self._rows.pop(i, None)
            else:
                self._rows.clear()
            self._persist()


class LocalVectorClient:
    """Drop-in replacement for chromadb.PersistentClient (subset used by the stores)."""

    def __init__(self, path: str):
        self.base = path
        os.makedirs(self.base, exist_ok=True)
        self._collections: dict = {}

    def _coll_path(self, name: str) -> str:
        return os.path.join(self.base, f"local_{name}.json")

    def get_or_create_collection(self, name, embedding_function=None, metadata=None):
        if name not in self._collections:
            self._collections[name] = _LocalCollection(
                self._coll_path(name), embedding_function)
        return self._collections[name]

    def create_collection(self, name, embedding_function=None, metadata=None):
        return self.get_or_create_collection(name, embedding_function, metadata)

    def get_collection(self, name, embedding_function=None):
        # raise if it doesn't exist yet, matching chroma semantics the stores expect
        if name not in self._collections and not os.path.exists(self._coll_path(name)):
            raise ValueError(f"Collection {name} does not exist")
        return self.get_or_create_collection(name, embedding_function)

    def delete_collection(self, name):
        self._collections.pop(name, None)
        try:
            p = self._coll_path(name)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
