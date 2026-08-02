"""
Learning & Meta-Strategy Module for the XAUUSD Trading Bot.

This module provides:
1. Vector Store (ChromaDB) - Fast pattern storage and retrieval using RAG
2. Strategy Registry - Dynamic discovery and selection of trading strategies
3. Pattern Matcher - Find similar historical market patterns
4. Experience Database - Persistent storage of trade outcomes for learning
5. Meta-Strategy Agent - LLM-powered agent that selects optimal strategy combinations
6. Knowledge Base - Persistent SQLite store for trading knowledge (Q&A pairs)
7. Curiosity Agent - Autonomous engine that asks questions, stores answers, and builds knowledge

The system continuously learns from market experience, storing patterns with their
outcomes and using vector similarity to identify profitable setups in real-time.
The curiosity agent drives autonomous knowledge acquisition about trading concepts,
brokers, market mechanics, sentiment, and correlations.
"""

from src.learning.vector_store import PatternVectorStore
from src.learning.strategy_registry import StrategyRegistry
from src.learning.pattern_matcher import PatternMatcher
from src.learning.experience_db import ExperienceDatabase

# #46 cleanup: MetaStrategyAgent / KnowledgeBase / CuriosityAgent are part of the
# legacy full-agent path (src/main.py) that nothing live imports. Eager-importing
# them here pulled the heavy LLM/langchain chain into EVERY `import src.learning.*`,
# which broke pure-logic tests on machines without those deps. They are now
# LAZY-loaded via __getattr__ so `from src.learning import MetaStrategyAgent` still
# works if the legacy path is ever revived, without the import-time cost/coupling.
_LAZY = {
    "MetaStrategyAgent": "src.learning.meta_strategy_agent",
    "KnowledgeBase": "src.learning.knowledge_base",
    "CuriosityAgent": "src.learning.curiosity_agent",
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
    "MetaStrategyAgent",
    "KnowledgeBase",
    "CuriosityAgent",
]
