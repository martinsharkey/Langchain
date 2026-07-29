"""
Curiosity Agent — Autonomous Knowledge Acquisition Engine.

This agent drives the bot's curiosity by:
1. Starting with seed questions about XAUUSD trading
2. Asking the LLM each question and storing the answer
3. Analyzing the answer to generate follow-up questions (chain of curiosity)
4. Building a hierarchical knowledge graph (topic → subtopic → facts)
5. Running continuously in the background during trading cycles
6. Injecting relevant knowledge into trading decisions

The curiosity agent enables the bot to:
- Learn about brokers, commissions, spreads, slippage
- Understand trading sessions (London, NY, Asian)
- Discover market drivers (economic events, geopolitics, wars)
- Build sentiment analysis capability
- Learn correlations with other symbols (DXY, EUR/USD)
- Never repeat the same mistake by storing all learnings

Example curiosity chain:
  "What impacts XAUUSD?" 
  → "London, NY, Asian sessions"
  → "What are the specific impacts of each session?"
  → "London session sees highest volatility during economic releases"
  → "What economic releases most affect gold?"
  → "NFP, CPI, FOMC minutes, geopolitical events"
  → "How do geopolitical events like wars affect gold?"
  → "Gold rises during uncertainty, safe-haven flows"
  → "How can we measure sentiment for gold?"
  → "COT report, gold ETF flows, fear index"
  → "Build a sentiment indicator based on this knowledge"
"""

import json
import logging
import time
from typing import Optional
from datetime import datetime

from src.learning.knowledge_base import KnowledgeBase
from src.core.llm import get_llm, mark_provider_failed

logger = logging.getLogger("learning.curiosity_agent")

# Maximum follow-up depth to prevent infinite chains
MAX_FOLLOW_UP_DEPTH = 5

# Maximum questions per cycle to avoid excessive API usage
MAX_QUESTIONS_PER_CYCLE = 2

# Confidence threshold for storing knowledge
MIN_CONFIDENCE_THRESHOLD = 0.3


class CuriosityAgent:
    """
    Autonomous curiosity-driven learning agent.
    
    Runs in the background during trading cycles, asking questions,
    storing answers, and building a knowledge base. The knowledge
    is then injected into trading decisions to improve performance.
    
    Usage:
        agent = CuriosityAgent(knowledge_base)
        agent.run_learning_cycle()  # Ask 1-2 questions per cycle
        context = agent.get_knowledge_context("market_drivers")
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """
        Initialize the curiosity agent.
        
        Args:
            knowledge_base: KnowledgeBase instance for persistent storage.
        """
        self.kb = knowledge_base
        self._llm = None
        self._cycle_count = 0
        self._total_questions_asked = 0
        
        # Seed the question queue on first run
        self._seed_questions()
        
        logger.info("CuriosityAgent initialized")

    def _get_llm(self):
        """Get or create the LLM instance."""
        if self._llm is None:
            self._llm = get_llm(temperature=0.7)  # Higher temp for creative curiosity
        return self._llm

    def _seed_questions(self):
        """Add seed questions to the queue if it's empty."""
        if self.kb.get_pending_count() == 0 and self.kb.get_knowledge_summary()["total_entries"] == 0:
            for seed in self.kb.get_seed_questions():
                self.kb.enqueue_question(
                    question=seed["question"],
                    topic=seed["topic"],
                    subtopic=seed["subtopic"],
                    priority=seed["priority"],
                )
            logger.info(f"Seeded {len(self.kb.get_seed_questions())} initial questions")

    def run_learning_cycle(self) -> dict:
        """
        Run one learning cycle — ask 1-2 questions and store answers.
        
        Returns:
            Dict with results of the learning cycle.
        """
        self._cycle_count += 1
        results = {
            "cycle": self._cycle_count,
            "questions_asked": 0,
            "follow_ups_generated": 0,
            "knowledge_stored": 0,
            "errors": [],
        }

        # Ask up to MAX_QUESTIONS_PER_CYCLE questions
        for _ in range(MAX_QUESTIONS_PER_CYCLE):
            question_data = self.kb.dequeue_next_question()
            if question_data is None:
                logger.info("No more pending questions — curiosity satisfied for now")
                break

            try:
                # Ask the LLM
                answer = self._ask_llm(question_data["question"])
                
                if not answer or len(answer.strip()) < 10:
                    logger.warning(f"Empty/short answer for: {question_data['question'][:60]}...")
                    self.kb.mark_question_completed(question_data["id"])
                    continue

                # Store the knowledge
                entry_id = self.kb.store_knowledge(
                    question=question_data["question"],
                    answer=answer,
                    topic=question_data["topic"],
                    subtopic=question_data["subtopic"],
                    priority=question_data["priority"],
                    confidence=0.7,  # Initial confidence, verified later
                    follow_up_from=question_data.get("follow_up_from"),
                    follow_up_depth=question_data.get("follow_up_depth", 0),
                    tags=[question_data["topic"], question_data["subtopic"]],
                )

                self._total_questions_asked += 1
                results["questions_asked"] += 1
                results["knowledge_stored"] += 1

                # Mark the question as completed
                self.kb.mark_question_completed(question_data["id"])

                # Generate follow-up questions from the answer
                follow_ups = self._generate_follow_ups(
                    question=question_data["question"],
                    answer=answer,
                    topic=question_data["topic"],
                    current_depth=question_data.get("follow_up_depth", 0),
                    parent_id=entry_id,
                )
                results["follow_ups_generated"] += follow_ups

                logger.info(
                    f"Curiosity cycle: asked '{question_data['question'][:60]}...' "
                    f"→ stored knowledge #{entry_id} "
                    f"→ generated {follow_ups} follow-ups"
                )

            except Exception as e:
                error_msg = f"Error processing question '{question_data['question'][:60]}...': {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                # Re-queue the question for later retry
                self.kb.enqueue_question(
                    question=question_data["question"],
                    topic=question_data["topic"],
                    subtopic=question_data["subtopic"],
                    priority=max(question_data["priority"] - 1, 1),  # Lower priority on retry
                    follow_up_from=question_data.get("follow_up_from"),
                )

        return results

    def _ask_llm(self, question: str) -> str:
        """
        Ask a question to the LLM and get a detailed answer.
        
        Args:
            question: The question to ask.
        
        Returns:
            The LLM's answer as a string.
        """
        llm = self._get_llm()

        prompt = f"""You are a professional XAUUSD (Gold) trading expert with deep knowledge of forex markets, 
commodities, technical analysis, and risk management. Answer the following question in detail.

QUESTION: {question}

Provide a comprehensive, accurate, and practical answer. Include:
- Specific facts and data points where possible
- Practical trading implications
- How this knowledge can be used to make better trading decisions
- Any caveats or important considerations

Your answer should be informative and actionable for a gold trader.
"""

        response = llm.invoke(prompt)

        # Handle structured content (list of content blocks from OpenAI-compatible APIs)
        raw_content = response.content if hasattr(response, 'content') else str(response)
        
        if isinstance(raw_content, list):
            texts = []
            for block in raw_content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        texts.append(block.get("thinking", ""))
                elif isinstance(block, str):
                    texts.append(block)
            return "\n".join(texts)
        
        return str(raw_content)

    def _generate_follow_ups(self, question: str, answer: str, topic: str,
                              current_depth: int, parent_id: int) -> int:
        """
        Analyze an answer and generate follow-up questions.
        
        Uses the LLM to identify knowledge gaps and generate deeper questions.
        
        Args:
            question: The original question.
            answer: The answer received.
            topic: The topic category.
            current_depth: Current follow-up depth.
            parent_id: ID of the parent knowledge entry.
        
        Returns:
            Number of follow-up questions generated.
        """
        # Stop if we've gone too deep
        if current_depth >= MAX_FOLLOW_UP_DEPTH:
            return 0

        try:
            llm = self._get_llm()

            prompt = f"""You are a curious XAUUSD trading student. You just learned the following:

QUESTION ASKED: {question}

ANSWER RECEIVED:
{answer[:1000]}

Based on this answer, identify 1-2 specific follow-up questions that would deepen your understanding.
These should be:
- Specific and focused (not broad)
- Build on the knowledge just acquired
- Aim to uncover practical trading insights
- Explore connections to other topics (sentiment, correlations, risk management)

For example, if you learned about trading sessions, a good follow-up would be:
"What specific economic releases during the London session have the biggest impact on gold?"

Respond with a JSON array ONLY (no markdown, no code blocks):
[
    {{
        "question": "<specific follow-up question>",
        "subtopic": "<specific subtopic>",
        "priority": <integer 1-10>,
        "reason": "<why this question matters for trading>"
    }}
]

Return an empty array [] if no meaningful follow-up is needed.
"""

            response = llm.invoke(prompt)
            raw_content = response.content if hasattr(response, 'content') else str(response)

            # Handle structured content
            if isinstance(raw_content, list):
                texts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            texts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            texts.append(block.get("thinking", ""))
                    elif isinstance(block, str):
                        texts.append(block)
                content = "\n".join(texts)
            else:
                content = str(raw_content)

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            follow_ups = json.loads(content)

            if not isinstance(follow_ups, list):
                return 0

            count = 0
            for fu in follow_ups[:2]:  # Max 2 follow-ups
                if not isinstance(fu, dict) or "question" not in fu:
                    continue
                
                self.kb.enqueue_question(
                    question=fu["question"],
                    topic=topic,
                    subtopic=fu.get("subtopic", "general"),
                    priority=fu.get("priority", 5),
                    follow_up_from=parent_id,
                )
                count += 1

            return count

        except Exception as e:
            logger.debug(f"Could not generate follow-ups: {e}")
            return 0

    def get_knowledge_context(self, topic: Optional[str] = None) -> str:
        """
        Get formatted knowledge for injection into trading decisions.
        
        Args:
            topic: Optional topic filter.
        
        Returns:
            Formatted string of relevant knowledge.
        """
        return self.kb.get_knowledge_for_context(topic=topic)

    def get_learning_summary(self) -> dict:
        """
        Get a summary of what the curiosity agent has learned.
        
        Returns:
            Dict with learning statistics.
        """
        kb_summary = self.kb.get_knowledge_summary()
        
        return {
            "total_questions_asked": self._total_questions_asked,
            "learning_cycles_run": self._cycle_count,
            "knowledge_entries": kb_summary["total_entries"],
            "topics_covered": kb_summary["total_topics"],
            "topic_breakdown": kb_summary["topic_breakdown"],
            "pending_questions": kb_summary["pending_questions"],
        }

    def get_knowledge_for_symbol(self, symbol: str = "XAUUSD") -> str:
        """
        Get all knowledge relevant to a specific trading symbol.
        
        Args:
            symbol: The trading symbol (default: XAUUSD).
        
        Returns:
            Formatted knowledge string for LLM context injection.
        """
        entries = self.kb.get_knowledge(limit=20)
        
        if not entries:
            return "No knowledge acquired yet."
        
        lines = [
            f"📚 KNOWLEDGE BASE FOR {symbol}:",
            f"   ({len(entries)} entries across {len(self.kb.get_all_topics())} topics)",
            "",
        ]
        
        # Group by topic
        topics = {}
        for e in entries:
            t = e["topic"]
            if t not in topics:
                topics[t] = []
            topics[t].append(e)
        
        for topic, topic_entries in topics.items():
            lines.append(f"  [{topic.upper()}]")
            for e in topic_entries[:3]:  # Max 3 per topic
                answer_preview = e["answer"][:150].replace("\n", " ")
                lines.append(f"    • {e['question']}")
                lines.append(f"      → {answer_preview}...")
            if len(topic_entries) > 3:
                lines.append(f"      ... and {len(topic_entries) - 3} more entries")
            lines.append("")
        
        return "\n".join(lines)
