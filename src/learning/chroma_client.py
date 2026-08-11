import os
import chromadb
from chromadb.config import Settings
from typing import Optional
from src import config
from src.utils.logger import get_logger

logger = get_logger("chroma")

class DummyCollection:
    def count(self): return 0
    def query(self, *args, **kwargs): return {"ids": [], "metadatas": [], "documents": [], "distances": []}
    def add(self, *args, **kwargs): pass
    def upsert(self, *args, **kwargs): pass
    def delete(self, *args, **kwargs): pass
    def get(self, *args, **kwargs): return {"ids": [], "metadatas": [], "documents": []}

class DummyClient:
    def get_collection(self, *args, **kwargs): return DummyCollection()
    def get_or_create_collection(self, *args, **kwargs): return DummyCollection()
    def create_collection(self, *args, **kwargs): return DummyCollection()
    def delete_collection(self, *args, **kwargs): pass

_CLIENT = None

def get_shared_chroma_client():
    global _CLIENT
    if _CLIENT is None:
        # ChromaDB Rust bindings (0.4.x / 1.5.x) are hard-crashing c10.dll/sqlite natively on this machine.
        # Bypass entirely so the bot can trade.
        if os.name == "nt":
            logger.warning("Bypassing ChromaDB on Windows to prevent native access violation. RAG is disabled.")
            _CLIENT = DummyClient()
        else:
            path = os.path.join(config.DATA_DIR, "chromadb_store")
            os.makedirs(path, exist_ok=True)
            _CLIENT = chromadb.PersistentClient(
                path=path,
                settings=Settings(anonymized_telemetry=False)
            )
    return _CLIENT

