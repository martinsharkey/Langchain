"""
Documentation RAG — query vectorbt, optuna, and TA library docs.

Collections:
  vectorbt_docs  — Portfolio.from_signals(), IndicatorFactory, splitters, records, etc.
  optuna_docs    — create_study(), Trial.suggest_*, TPE/CMA samplers, pruners, RDB storage
  ta_libs_docs   — ta, pandas-ta, ta-lib indicator references

Source documents (tracked in git):
  docs/lib_docs/vectorbt/   — fetched from vectorbt.dev and github.com/polakowo/vectorbt
  docs/lib_docs/optuna/     — fetched from optuna.readthedocs.io and github.com/optuna/optuna
  docs/lib_docs/ta_libs/    — fetched from readthedocs and github READMEs for ta/pandas-ta/ta-lib

ChromaDB collections (runtime, gitignored, rebuilt from docs/lib_docs/):
  data/chromadb_store/vectorbt_docs
  data/chromadb_store/optuna_docs
  data/chromadb_store/ta_libs_docs

Usage:
    from src.learning.docs_rag import DocsRAG
    rag = DocsRAG()
    results = rag.query("Portfolio.from_signals sl_stop trailing stop", collection="vectorbt_docs", n=5)
    for r in results:
        print(r["text"][:300])

    # Rebuild collections from docs/lib_docs/ (run once after cloning or updating docs):
    DocsRAG.build_collections()

Agents must query this RAG before writing any vectorbt or optuna code to ensure
they use real library APIs and not custom reimplementations.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

import chromadb
from chromadb.config import Settings

PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "chromadb_store",
)

# Tracked source docs — committed to git, used to (re)build ChromaDB collections
DOCS_SOURCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs", "lib_docs",
)

CollectionName = Literal["vectorbt_docs", "optuna_docs", "ta_libs_docs"]
_VALID_COLLECTIONS: tuple[str, ...] = ("vectorbt_docs", "optuna_docs", "ta_libs_docs")


def _embed(text: str, dim: int = 64) -> list[float]:
    """Deterministic char-frequency embedding — consistent with the ingest script."""
    h = hashlib.sha256(text.encode()).digest()
    vec = [((b / 255.0) * 2 - 1) for b in h]
    words = text.lower().split()
    for i in range(dim - 32):
        word = words[i % max(len(words), 1)] if words else str(i)
        b = hashlib.md5(f"{word}{i}".encode()).digest()[0]
        vec.append((b / 255.0) * 2 - 1)
    return vec[:dim]


class DocsRAG:
    """Query the library documentation RAG collections stored in ChromaDB.

    Each collection stores chunked markdown text from the fetched docs.
    Call :meth:`query` to retrieve the most relevant chunks for a given question.
    Agents should call this before writing any vectorbt / optuna code.
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        self._dir = persist_dir or PERSIST_DIR
        self._client = chromadb.PersistentClient(
            path=self._dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collections: dict[str, chromadb.Collection] = {}

    def _get_collection(self, name: str) -> chromadb.Collection | None:
        if name not in self._collections:
            try:
                self._collections[name] = self._client.get_collection(name)
            except Exception:
                return None
        return self._collections[name]

    def query(
        self,
        question: str,
        collection: CollectionName = "vectorbt_docs",
        n: int = 5,
    ) -> list[dict]:
        """Return top-n relevant documentation chunks for a question.

        Args:
            question: Natural language question or keyword phrase.
            collection: Which documentation collection to search.
            n: Number of chunks to return.

        Returns:
            List of dicts with keys: ``text``, ``source``, ``score``.
        """
        col = self._get_collection(collection)
        if col is None:
            return [{"text": f"Collection '{collection}' not found. Run docs_rag build first.", "source": "", "score": 0.0}]

        vec = _embed(question)
        count = col.count()
        if count == 0:
            return []

        results = col.query(
            query_embeddings=[vec],
            n_results=min(n, count),
            include=["documents", "metadatas", "distances"],
        )

        out = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                out.append({
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "source": results["metadatas"][0][i].get("source", ""),
                    "score": round(1.0 - results["distances"][0][i], 4),
                })
        return out

    def query_all(self, question: str, n: int = 3) -> dict[str, list[dict]]:
        """Query all three collections and return combined results."""
        return {name: self.query(question, collection=name, n=n) for name in _VALID_COLLECTIONS}

    def available_collections(self) -> list[str]:
        """Return the names of collections present in the store."""
        try:
            return [c.name for c in self._client.list_collections() if c.name in _VALID_COLLECTIONS]
        except Exception:
            return []

    def collection_stats(self) -> dict[str, int]:
        """Return chunk counts per collection."""
        stats = {}
        for name in _VALID_COLLECTIONS:
            col = self._get_collection(name)
            stats[name] = col.count() if col else 0
        return stats

    @classmethod
    def build_collections(
        cls,
        persist_dir: str | None = None,
        docs_dir: str | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> dict[str, int]:
        """Build (or rebuild) all three ChromaDB collections from docs/lib_docs/.

        Call this once after cloning the repo or after updating the source docs.
        Safe to re-run — deletes and recreates each collection.

        Args:
            persist_dir: Override ChromaDB storage path (default: data/chromadb_store/).
            docs_dir: Override source docs path (default: docs/lib_docs/).
            chunk_size: Characters per chunk.
            chunk_overlap: Overlap between consecutive chunks.

        Returns:
            Dict of {collection_name: chunk_count}.
        """
        from pathlib import Path

        _persist = persist_dir or PERSIST_DIR
        _docs = Path(docs_dir or DOCS_SOURCE_DIR)

        os.makedirs(_persist, exist_ok=True)
        client = chromadb.PersistentClient(
            path=_persist,
            settings=Settings(anonymized_telemetry=False),
        )

        collections_map: dict[str, list] = {
            "vectorbt_docs": list((_docs / "vectorbt").glob("*.md")),
            "optuna_docs":   list((_docs / "optuna").glob("*.md")),
            "ta_libs_docs":  list((_docs / "ta_libs").glob("*.md")),
        }

        results: dict[str, int] = {}

        for col_name, files in collections_map.items():
            # Delete and recreate for clean rebuild
            try:
                client.delete_collection(col_name)
            except Exception:
                pass
            col = client.create_collection(
                name=col_name,
                metadata={"description": f"Documentation RAG: {col_name}"},
            )

            ids, embeddings, documents, metadatas = [], [], [], []

            for fpath in sorted(files):
                text = fpath.read_text(errors="replace").strip()
                if len(text) < 100:
                    continue  # skip near-empty pages (JS-rendered shells)

                # Split into overlapping chunks
                start = 0
                chunks = []
                while start < len(text):
                    end = min(start + chunk_size, len(text))
                    chunks.append(text[start:end])
                    start += chunk_size - chunk_overlap

                for ci, chunk in enumerate(chunks):
                    chunk = chunk.strip()
                    if len(chunk) < 50:
                        continue
                    doc_id = f"{fpath.stem}_{ci:04d}"
                    ids.append(doc_id)
                    embeddings.append(_embed(chunk))
                    documents.append(chunk)
                    metadatas.append({
                        "source": fpath.name,
                        "collection": col_name,
                        "chunk_index": ci,
                        "total_chunks": len(chunks),
                        "char_count": len(chunk),
                    })

            # Batch upsert in groups of 500
            batch = 500
            for i in range(0, len(ids), batch):
                col.upsert(
                    ids=ids[i:i + batch],
                    embeddings=embeddings[i:i + batch],
                    documents=documents[i:i + batch],
                    metadatas=metadatas[i:i + batch],
                )

            results[col_name] = len(ids)

        return results
