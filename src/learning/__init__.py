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
from src.learning.meta_strategy_agent import MetaStrategyAgent
from src.learning.knowledge_base import KnowledgeBase
from src.learning.curiosity_agent import CuriosityAgent

__all__ = [
    "PatternVectorStore",
    "StrategyRegistry",
    "PatternMatcher",
    "ExperienceDatabase",
    "MetaStrategyAgent",
    "KnowledgeBase",
    "CuriosityAgent",
]
