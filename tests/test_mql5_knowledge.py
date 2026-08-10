"""
Tests for MQL5Knowledge (#22) — offline seed + research + indexing. No network.

Uses a temp persist dir. Exercises the built-in seed knowledge and the research
API so the continual researcher (#32) has something to ground on day one.
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contextlib


@contextlib.contextmanager
def _tmpdir():
    """Manual temp dir with best-effort cleanup (ChromaDB holds a sqlite handle
    open on Windows, which breaks TemporaryDirectory's strict teardown)."""
    d = tempfile.mkdtemp()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _kb(tmp):
    from src.learning.mql5_knowledge import MQL5Knowledge
    return MQL5Knowledge(persist_directory=tmp, seed=True)


def test_seeds_on_first_init():
    with _tmpdir() as d:
        kb = _kb(os.path.join(d, "cdb"))
        assert kb.count() >= 5, f"expected seeded knowledge, got {kb.count()}"


def test_research_returns_osma_tuning():
    with _tmpdir() as d:
        kb = _kb(os.path.join(d, "cdb"))
        hits = kb.research("make OsMA react faster catch the cross earlier", n_results=3)
        assert hits, "expected research hits"
        joined = " ".join(h["text"].lower() for h in hits)
        assert "osma" in joined and ("fast" in joined or "period" in joined)
        # provenance present
        assert "source_url" in hits[0]["metadata"]


def test_index_document_and_recall():
    with _tmpdir() as d:
        kb = _kb(os.path.join(d, "cdb"))
        n = kb.index_document(
            "The iADX indicator measures trend strength; values above 25 indicate a "
            "strong trend regardless of direction. A shorter ADX period reacts faster.",
            source_url="https://www.mql5.com/en/docs/indicators/iadx",
            title="iADX", section="mql5_docs")
        assert n >= 1
        hits = kb.research("how to measure trend strength ADX", n_results=3)
        assert any("adx" in h["text"].lower() for h in hits)


def test_research_indicator_targeted():
    with _tmpdir() as d:
        kb = _kb(os.path.join(d, "cdb"))
        hits = kb.research_indicator("OsMA", "fast period")
        assert hits and "osma" in " ".join(h["text"].lower() for h in hits)


if __name__ == "__main__":
    test_seeds_on_first_init()
    test_research_returns_osma_tuning()
    test_index_document_and_recall()
    test_research_indicator_targeted()
    print("mql5 knowledge tests passed")
