"""
Learning & Meta-Strategy Module for the XAUUSD Trading Bot.

This module provides:
1. Vector Store (ChromaDB) - Fast pattern storage and retrieval using RAG
2. Strategy Registry - Dynamic discovery and selection of trading strategies
3. Pattern Matcher - Find similar historical market patterns
4. Experience Database - Persistent storage of trade outcomes for learning
5. Knowledge Base - Persistent SQLite store for trading knowledge (still live via
   the symbol governor, post-mortem, performance researcher, orchestration + dashboard)

The system continuously learns from market experience, storing patterns with their
outcomes and using vector similarity to identify profitable setups in real-time.
"""

from src.learning.vector_store import PatternVectorStore
from src.learning.strategy_registry import StrategyRegistry
from src.learning.pattern_matcher import PatternMatcher
from src.learning.experience_db import ExperienceDatabase

# #46 cleanup: the legacy full-agent path (src/main.py, MetaStrategyAgent,
# CuriosityAgent, src/core/agent.py, src/agents/*) has been REMOVED. KnowledgeBase
# is still live (symbol governor, post-mortem, performance researcher, orchestration,
# dashboard) so it is kept, lazy-loaded to avoid pulling its deps into every import.
_LAZY = {
    "KnowledgeBase": "src.learning.knowledge_base",
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PatternVectorStore",
    "StrategyRegistry",
    "PatternMatcher",
    "ExperienceDatabase",
    "KnowledgeBase",
]
