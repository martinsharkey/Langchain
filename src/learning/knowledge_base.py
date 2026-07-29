"""
Knowledge Base — Persistent SQLite-backed store for trading knowledge.

Stores every Q&A pair the curiosity agent discovers, along with:
- Topics and subtopics (hierarchical knowledge graph)
- Source questions and follow-up chains
- Confidence scores and verification status
- Timestamps for when knowledge was acquired

This enables the bot to:
1. Remember everything it learns about XAUUSD trading
2. Build a hierarchical knowledge graph (topic → subtopic → facts)
3. Retrieve relevant knowledge during trading decisions
4. Track what it knows and what it still needs to learn
"""

import os
import json
import sqlite3
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger("learning.knowledge_base")

# Seed questions that kickstart the curiosity engine
SEED_QUESTIONS = [
    # ─── Trading Providers & Costs ───────────────────────────
    {
        "question": "What are the best brokers for XAUUSD trading and what commissions do they charge?",
        "topic": "broker_research",
        "subtopic": "commissions",
        "priority": 10,
    },
    {
        "question": "How does spread impact XAUUSD trading profitability, and what are typical spreads for gold?",
        "topic": "trading_costs",
        "subtopic": "spread",
        "priority": 9,
    },
    {
        "question": "What is slippage in XAUUSD trading and how can it be minimized?",
        "topic": "trading_costs",
        "subtopic": "slippage",
        "priority": 9,
    },
    # ─── Trading Sessions ─────────────────────────────────────
    {
        "question": "How do London, New York, and Asian trading sessions impact XAUUSD price movements?",
        "topic": "market_mechanics",
        "subtopic": "trading_sessions",
        "priority": 8,
    },
    {
        "question": "What are the best times of day to trade XAUUSD for maximum volatility and liquidity?",
        "topic": "market_mechanics",
        "subtopic": "optimal_timing",
        "priority": 8,
    },
    # ─── Market Drivers ───────────────────────────────────────
    {
        "question": "What major economic events and news releases most significantly impact gold prices?",
        "topic": "market_drivers",
        "subtopic": "economic_events",
        "priority": 10,
    },
    {
        "question": "How do geopolitical events like wars, elections, and trade disputes affect XAUUSD?",
        "topic": "market_drivers",
        "subtopic": "geopolitics",
        "priority": 9,
    },
    {
        "question": "What is the relationship between the US Dollar Index (DXY) and XAUUSD?",
        "topic": "market_drivers",
        "subtopic": "dxy_correlation",
        "priority": 9,
    },
    # ─── Sentiment & Market Psychology ────────────────────────
    {
        "question": "How can market sentiment be measured and used to inform XAUUSD trading decisions?",
        "topic": "sentiment_analysis",
        "subtopic": "sentiment_measurement",
        "priority": 8,
    },
    {
        "question": "What is the COT (Commitment of Traders) report and how does it help predict gold price direction?",
        "topic": "sentiment_analysis",
        "subtopic": "cot_report",
        "priority": 7,
    },
    # ─── Correlations ─────────────────────────────────────────
    {
        "question": "Which currency pairs and commodities have the strongest correlation with XAUUSD?",
        "topic": "correlations",
        "subtopic": "intermarket_analysis",
        "priority": 8,
    },
    {
        "question": "How do interest rates and central bank policies impact gold prices?",
        "topic": "market_drivers",
        "subtopic": "interest_rates",
        "priority": 9,
    },
    # ─── Risk Management ──────────────────────────────────────
    {
        "question": "What are the most effective risk management strategies specifically for XAUUSD trading?",
        "topic": "risk_management",
        "subtopic": "gold_specific_risk",
        "priority": 10,
    },
    {
        "question": "How does leverage impact XAUUSD trading and what are safe leverage levels for gold?",
        "topic": "risk_management",
        "subtopic": "leverage",
        "priority": 8,
    },
    # ─── Technical Analysis ───────────────────────────────────
    {
        "question": "What technical indicators and patterns work best for XAUUSD compared to other instruments?",
        "topic": "technical_analysis",
        "subtopic": "gold_specific_indicators",
        "priority": 7,
    },
    {
        "question": "How do support and resistance levels form differently for gold than for forex pairs?",
        "topic": "technical_analysis",
        "subtopic": "sr_levels_gold",
        "priority": 7,
    },
]


class KnowledgeBase:
    """
    SQLite-backed persistent knowledge store for trading insights.
    
    Stores hierarchical knowledge (topic → subtopic → facts) with
    full provenance tracking (source question, follow-up chain, confidence).
    """

    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "trading_knowledge.db",
    )

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the knowledge base.
        
        Args:
            db_path: Override the default database path.
        """
        self.db_path = db_path or self.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._seed_questions = list(SEED_QUESTIONS)
        logger.info(f"Knowledge base initialized at {self.db_path}")

    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ─── Knowledge entries (Q&A pairs) ────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                topic TEXT NOT NULL,
                subtopic TEXT NOT NULL,
                priority INTEGER DEFAULT 5,
                confidence REAL DEFAULT 0.5,
                verified INTEGER DEFAULT 0,
                follow_up_from INTEGER,
                follow_up_depth INTEGER DEFAULT 0,
                source TEXT DEFAULT 'llm_query',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (follow_up_from) REFERENCES knowledge_entries(id)
            )
        """)

        # ─── Topics hierarchy ──────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                parent_topic TEXT,
                entry_count INTEGER DEFAULT 0,
                avg_confidence REAL DEFAULT 0.0,
                last_queried TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # ─── Knowledge tags for cross-referencing ──────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (entry_id) REFERENCES knowledge_entries(id)
            )
        """)

        # ─── Pending questions queue ───────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                topic TEXT NOT NULL,
                subtopic TEXT NOT NULL,
                priority INTEGER DEFAULT 5,
                follow_up_from INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (follow_up_from) REFERENCES knowledge_entries(id)
            )
        """)

        conn.commit()
        conn.close()

    # ─── Core Operations ──────────────────────────────────────

    def store_knowledge(
        self,
        question: str,
        answer: str,
        topic: str,
        subtopic: str,
        priority: int = 5,
        confidence: float = 0.5,
        follow_up_from: Optional[int] = None,
        follow_up_depth: int = 0,
        tags: Optional[list[str]] = None,
    ) -> int:
        """
        Store a new knowledge entry (Q&A pair).
        
        Args:
            question: The question that was asked.
            answer: The answer received.
            topic: Main topic category.
            subtopic: Subtopic within the topic.
            priority: Importance (1-10, higher = more important).
            confidence: How confident we are in this knowledge (0.0-1.0).
            follow_up_from: ID of the question this was a follow-up to.
            follow_up_depth: How deep in the follow-up chain (0 = seed).
            tags: Optional list of tags for cross-referencing.
        
        Returns:
            The ID of the new knowledge entry.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO knowledge_entries
                (question, answer, topic, subtopic, priority, confidence,
                 follow_up_from, follow_up_depth)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (question, answer, topic, subtopic, priority, confidence,
              follow_up_from, follow_up_depth))
        
        entry_id = cursor.lastrowid

        # Store tags
        if tags:
            for tag in tags:
                cursor.execute("""
                    INSERT INTO knowledge_tags (entry_id, tag) VALUES (?, ?)
                """, (entry_id, tag))

        # Upsert topic
        cursor.execute("""
            INSERT INTO topics (name, description, entry_count, avg_confidence, last_queried)
            VALUES (?, ?, 1, ?, datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                entry_count = entry_count + 1,
                avg_confidence = (avg_confidence + ?) / 2.0,
                last_queried = datetime('now')
        """, (topic, f"Knowledge about {topic}", confidence, confidence))

        conn.commit()
        conn.close()

        logger.info(f"Stored knowledge: [{topic}/{subtopic}] Q: {question[:60]}...")
        return entry_id

    def get_knowledge(self, topic: Optional[str] = None, subtopic: Optional[str] = None,
                      limit: int = 20) -> list[dict]:
        """
        Retrieve knowledge entries, optionally filtered by topic/subtopic.
        
        Args:
            topic: Filter by topic (optional).
            subtopic: Filter by subtopic (optional).
            limit: Maximum entries to return.
        
        Returns:
            List of knowledge entry dicts.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM knowledge_entries WHERE 1=1"
        params = []

        if topic:
            query += " AND topic = ?"
            params.append(topic)
        if subtopic:
            query += " AND subtopic = ?"
            params.append(subtopic)

        query += " ORDER BY priority DESC, confidence DESC, created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": r[0],
                "question": r[1],
                "answer": r[2],
                "topic": r[3],
                "subtopic": r[4],
                "priority": r[5],
                "confidence": r[6],
                "verified": r[7],
                "follow_up_from": r[8],
                "follow_up_depth": r[9],
                "source": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]

    def search_knowledge(self, query_text: str, limit: int = 10) -> list[dict]:
        """
        Search knowledge entries by text matching (simple LIKE search).
        
        Args:
            query_text: Text to search for in questions and answers.
            limit: Maximum results.
        
        Returns:
            List of matching knowledge entry dicts.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM knowledge_entries
            WHERE question LIKE ? OR answer LIKE ? OR topic LIKE ? OR subtopic LIKE ?
            ORDER BY priority DESC, confidence DESC
            LIMIT ?
        """, (f"%{query_text}%", f"%{query_text}%", f"%{query_text}%", f"%{query_text}%", limit))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": r[0],
                "question": r[1],
                "answer": r[2],
                "topic": r[3],
                "subtopic": r[4],
                "priority": r[5],
                "confidence": r[6],
                "verified": r[7],
                "follow_up_from": r[8],
                "follow_up_depth": r[9],
                "source": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]

    def get_knowledge_summary(self) -> dict:
        """
        Get a summary of all knowledge in the database.
        
        Returns:
            Dict with counts, topics, and stats.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM knowledge_entries")
        total_entries = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT topic) FROM knowledge_entries")
        total_topics = cursor.fetchone()[0]

        cursor.execute("""
            SELECT topic, COUNT(*) as cnt, AVG(confidence) as avg_conf
            FROM knowledge_entries
            GROUP BY topic
            ORDER BY cnt DESC
        """)
        topic_breakdown = [
            {"topic": r[0], "count": r[1], "avg_confidence": r[2]}
            for r in cursor.fetchall()
        ]

        cursor.execute("SELECT COUNT(*) FROM pending_questions WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]

        conn.close()

        return {
            "total_entries": total_entries,
            "total_topics": total_topics,
            "topic_breakdown": topic_breakdown,
            "pending_questions": pending_count,
        }

    # ─── Question Queue Management ────────────────────────────

    def get_seed_questions(self) -> list[dict]:
        """Get the list of seed questions to start the curiosity engine."""
        return list(self._seed_questions)

    def enqueue_question(self, question: str, topic: str, subtopic: str,
                         priority: int = 5, follow_up_from: Optional[int] = None):
        """
        Add a question to the pending queue.
        
        Args:
            question: The question to ask.
            topic: Topic category.
            subtopic: Subtopic.
            priority: Importance (1-10).
            follow_up_from: ID of the knowledge entry this follows from.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Avoid duplicate pending questions
        cursor.execute("""
            SELECT id FROM pending_questions
            WHERE question = ? AND status = 'pending'
        """, (question,))
        
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO pending_questions
                    (question, topic, subtopic, priority, follow_up_from)
                VALUES (?, ?, ?, ?, ?)
            """, (question, topic, subtopic, priority, follow_up_from))
            logger.info(f"Enqueued question: [{topic}/{subtopic}] {question[:60]}...")

        conn.commit()
        conn.close()

    def dequeue_next_question(self) -> Optional[dict]:
        """
        Get the highest-priority pending question.
        
        Returns:
            Dict with question details, or None if queue is empty.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, question, topic, subtopic, priority, follow_up_from
            FROM pending_questions
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if row is None:
            conn.close()
            return None

        # Mark as in progress
        cursor.execute("""
            UPDATE pending_questions SET status = 'in_progress' WHERE id = ?
        """, (row[0],))
        conn.commit()
        conn.close()

        return {
            "id": row[0],
            "question": row[1],
            "topic": row[2],
            "subtopic": row[3],
            "priority": row[4],
            "follow_up_from": row[5],
        }

    def mark_question_completed(self, question_id: int):
        """Mark a pending question as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pending_questions SET status = 'completed' WHERE id = ?
        """, (question_id,))
        conn.commit()
        conn.close()

    def get_pending_count(self) -> int:
        """Get the number of pending questions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_questions WHERE status = 'pending'")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_knowledge_for_context(self, topic: Optional[str] = None,
                                   max_entries: int = 10) -> str:
        """
        Get a formatted string of relevant knowledge for LLM context.
        
        Used to inject learned knowledge into trading decisions.
        
        Args:
            topic: Filter by topic (optional).
            max_entries: Maximum entries to include.
        
        Returns:
            Formatted string of knowledge entries.
        """
        entries = self.get_knowledge(topic=topic, limit=max_entries)
        
        if not entries:
            return "No knowledge acquired yet on this topic."
        
        lines = ["📚 KNOWLEDGE BASE EXTRACT:", ""]
        for e in entries:
            lines.append(f"[{e['topic']}/{e['subtopic']}] (confidence: {e['confidence']:.0%})")
            lines.append(f"  Q: {e['question']}")
            # Truncate long answers
            answer = e['answer'][:300] + "..." if len(e['answer']) > 300 else e['answer']
            lines.append(f"  A: {answer}")
            lines.append("")
        
        return "\n".join(lines)

    def get_all_topics(self) -> list[str]:
        """Get all distinct topics in the knowledge base."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT name FROM topics ORDER BY name")
        topics = [r[0] for r in cursor.fetchall()]
        conn.close()
        return topics

    def clear(self):
        """Clear all knowledge (for testing/reset)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_entries")
        cursor.execute("DELETE FROM topics")
        cursor.execute("DELETE FROM knowledge_tags")
        cursor.execute("DELETE FROM pending_questions")
        conn.commit()
        conn.close()
        logger.info("Knowledge base cleared")
