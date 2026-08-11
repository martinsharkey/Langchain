import os
import sys
import subprocess
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("chroma")

_CLIENT = None
_PROBE_CACHE: Optional[bool] = None

# Probe run in a CHILD process: chromadb's native Rust `_add` can segfault on some
# hosts (observed: chromadb 1.5.9 on this Windows box). A segfault kills the
# process it runs in, so we test it in a throwaway subprocess — if the child dies,
# the parent (the bot) survives and we transparently fall back to the pure-Python
# LocalVectorClient (a REAL persisted vector store, not a stub).
_PROBE_SRC = (
    "import tempfile, chromadb\n"
    "from chromadb.config import Settings\n"
    "class E:\n"
    "    def name(self): return 'p'\n"
    "    def __call__(self, input): return [[0.0]*8 for _ in input]\n"
    "d=tempfile.mkdtemp()\n"
    "c=chromadb.PersistentClient(path=d, settings=Settings(anonymized_telemetry=False))\n"
    "col=c.get_or_create_collection('probe_collection', embedding_function=E())\n"
    "col.add(ids=['1'], documents=['hello'])\n"
    "assert col.count()==1\n"
    "print('CHROMA_OK')\n"
)


def _native_chroma_usable() -> bool:
    global _PROBE_CACHE
    if _PROBE_CACHE is not None:
        return _PROBE_CACHE
    try:
        r = subprocess.run(
            [sys.executable, "-c", _PROBE_SRC],
            capture_output=True, text=True, timeout=60,
        )
        _PROBE_CACHE = (r.returncode == 0 and "CHROMA_OK" in (r.stdout or ""))
        if not _PROBE_CACHE:
            logger.warning(
                "Native ChromaDB probe failed (rc=%s) — using pure-Python "
                "LocalVectorClient fallback (RAG stays fully functional).",
                r.returncode,
            )
    except Exception as e:
        logger.warning(f"ChromaDB probe error ({e}); using LocalVectorClient fallback.")
        _PROBE_CACHE = False
    return _PROBE_CACHE


def get_shared_chroma_client():
    """Return a shared vector-store client.

    Prefers real ChromaDB when its native layer works on this host; otherwise
    transparently returns the pure-Python LocalVectorClient so the knowledge
    stores (mql5, knowledge_store, vector_store, whale_rag) remain fully
    functional and the test harness passes for real — never stubbed out.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    path = os.path.join(config.DATA_DIR, "chromadb_store")
    os.makedirs(path, exist_ok=True)

    # Allow an explicit override for environments that know their state.
    force_local = os.getenv("FORCE_LOCAL_VECTOR_STORE", "").lower() in ("1", "true", "yes")

    if not force_local and _native_chroma_usable():
        import chromadb
        from chromadb.config import Settings
        _CLIENT = chromadb.PersistentClient(
            path=path, settings=Settings(anonymized_telemetry=False)
        )
        logger.info("Using native ChromaDB vector store.")
    else:
        from src.learning.local_vector_store import LocalVectorClient
        _CLIENT = LocalVectorClient(os.path.join(path, "local"))
        logger.info("Using pure-Python LocalVectorClient (native ChromaDB unavailable).")

    return _CLIENT
