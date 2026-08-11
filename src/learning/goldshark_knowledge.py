import os
import glob
import logging
from typing import Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings

from src import config
from src.learning.chroma_client import get_shared_chroma_client

logger = logging.getLogger("goldshark_knowledge")

class _SafeEmbeddingFunction:
    """Fallback embedding function that avoids torch/c10.dll native crashes on Windows."""
    def __init__(self, dim: int = 20):
        self.dim = dim

    def name(self) -> str:
        return "safe_hash_embedder"

    def __call__(self, input: list[str]) -> list[list[float]]:
        import math, hashlib
        out: list[list[float]] = []
        for text in input:
            h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
            vec = [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

class GoldSharkKnowledge:
    """
    A local 'NotebookLM' clone specifically for historical GoldShark strategies, 
    XGBoost findings, and proprietary trading rules. 
    
    Reads any .txt or .md files dropped into data/goldshark_notebook/ and makes 
    them semantically queryable by the ContinualResearcher.
    """
    COLLECTION_NAME = "goldshark_historical_notebook"
    NOTEBOOK_DIR = os.path.join(config.DATA_DIR, "goldshark_notebook")

    def __init__(self):
        os.makedirs(self.NOTEBOOK_DIR, exist_ok=True)
        self.client = get_shared_chroma_client()
        
        _safe_embed = None
        if os.name == "nt" or os.environ.get("USE_SAFE_EMBEDDER", "1") == "1":
            _safe_embed = _SafeEmbeddingFunction(dim=20)
            
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME, 
                embedding_function=_safe_embed,
                metadata={"description": "Historical GoldShark rules, XGBoost data, and baseline logic"}
            )
        except Exception:
            try:
                self.client.delete_collection(self.COLLECTION_NAME)
            except Exception:
                pass
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME, 
                embedding_function=_safe_embed,
                metadata={"description": "Historical GoldShark rules, XGBoost data, and baseline logic"}
            )
            
        # Automatically ingest new files on startup
        self._ingest_notebook_folder()
        logger.info(f"GoldSharkKnowledge ready ({self.collection.count()} chunks) at {self.NOTEBOOK_DIR}")

    def _ingest_notebook_folder(self):
        """Reads local text/markdown files and ingests them into the RAG."""
        files = glob.glob(os.path.join(self.NOTEBOOK_DIR, "*.txt")) + glob.glob(os.path.join(self.NOTEBOOK_DIR, "*.md"))
        if not files:
            return

        docs = []
        metas = []
        ids = []

        for filepath in files:
            filename = os.path.basename(filepath)
            # Use file modification time to skip re-ingesting unless changed
            mtime = os.path.getmtime(filepath)
            doc_id_prefix = f"{filename}_{mtime}"
            
            # Check if this file version is already in the DB
            try:
                existing = self.collection.get(where={"filename": filename})
                if existing and existing.get("metadatas"):
                    stored_mtime = existing["metadatas"][0].get("mtime", 0)
                    if stored_mtime >= mtime:
                        continue # Already ingested this version
                    else:
                        # File was updated, delete old chunks
                        self.collection.delete(where={"filename": filename})
            except Exception:
                pass

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Simple chunking by paragraphs to keep context
                chunks = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 50]
                
                for i, chunk in enumerate(chunks):
                    docs.append(chunk)
                    metas.append({
                        "source": "goldshark_history",
                        "filename": filename,
                        "mtime": mtime,
                        "chunk_idx": i
                    })
                    ids.append(f"{doc_id_prefix}_chunk{i}")
            except Exception as e:
                logger.warning(f"Failed to read GoldShark source {filename}: {e}")

        if docs:
            # Batch upsert
            batch_size = 100
            for i in range(0, len(docs), batch_size):
                self.collection.upsert(
                    documents=docs[i:i+batch_size],
                    metadatas=metas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
            logger.info(f"Ingested {len(docs)} new chunks from GoldShark notebook.")

    def research(self, query: str, n_results: int = 3) -> list[dict]:
        """Semantic recall of GoldShark historical knowledge."""
        if self.collection.count() == 0:
            return []
        
        try:
            res = self.collection.query(
                query_texts=[query], 
                n_results=min(n_results, self.collection.count()),
                include=["documents", "metadatas", "distances"]
            )
            out = []
            if res.get("ids") and res["ids"][0]:
                for i in range(len(res["ids"][0])):
                    out.append({
                        "text": res["documents"][0][i],
                        "similarity": 1.0 - (res["distances"][0][i] if "distances" in res else 0.0),
                        "metadata": res["metadatas"][0][i]
                    })
            return out
        except Exception as e:
            logger.error(f"GoldShark research query failed: {e}")
            return []

    def count(self) -> int:
        return self.collection.count()
