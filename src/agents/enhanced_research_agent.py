"""
Enhanced Research Agent — Daily market intelligence orchestration.

This agent runs daily at 00:00 UTC and:
1. Collects market data from multiple sources (async)
2. Analyzes data semantically (using LLM)
3. Stores findings in knowledge base
4. Makes research context available to trading agent

This is the CORE of the multi-agent handoff system.

Usage:
    agent = create_enhanced_research_agent()
    await agent.run_daily_cycle()
"""

import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from src.core.market_data_collector import MarketDataCollector
from src.core.version_manager import VersionManager
from src.core.handoff_protocol import HandoffProtocol
from src.learning.knowledge_base import KnowledgeBase
from src.core.llm import get_groq_llm

logger = logging.getLogger("agents.enhanced_research_agent")


class EnhancedResearchAgent:
    """
    Research agent that gathers and analyzes market intelligence daily.
    
    Lifecycle:
    1. Wake up at 00:00 UTC
    2. Collect data from all sources (parallel)
    3. Analyze with semantic interpreter
    4. Store in KB
    5. Prepare handoff to trading agent
    6. Sleep until next 00:00 UTC
    """
    
    def __init__(
        self,
        market_data_collector: Optional[MarketDataCollector] = None,
        version_manager: Optional[VersionManager] = None,
        handoff_protocol: Optional[HandoffProtocol] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
    ):
        """
        Initialize research agent with components.
        
        All components are optional and will be created if not provided.
        """
        self.name = "research_agent"
        self.market_data_collector = market_data_collector or MarketDataCollector()
        self.version_manager = version_manager or VersionManager()
        self.handoff_protocol = handoff_protocol or HandoffProtocol(self.version_manager)
        self.knowledge_base = knowledge_base or KnowledgeBase()
        
        # LLM for semantic analysis
        self.llm = get_groq_llm()
        
        # State tracking
        self.last_cycle_timestamp = None
        self.last_cycle_data = None
        self.cycle_count = 0
        
        logger.info("EnhancedResearchAgent initialized")
    
    async def run_daily_cycle(self) -> Dict[str, Any]:
        """
        Run the daily research cycle.
        
        This is called by the scheduler at 00:00 UTC.
        
        Returns:
            {
                "success": bool,
                "cycle_id": str,
                "data": {...},
                "analysis": {...},
                "stored_entries": int,
                "errors": [str, ...]
            }
        """
        
        logger.info("=" * 70)
        logger.info("DAILY RESEARCH CYCLE STARTING")
        logger.info("=" * 70)
        
        cycle_start = datetime.now(timezone.utc)
        self.cycle_count += 1
        cycle_id = f"cycle_{self.cycle_count}_{cycle_start.timestamp()}"
        
        errors = []
        stored_entries = 0
        
        try:
            # STEP 1: Collect data from all sources
            logger.info("STEP 1: Collecting market data from all sources...")
            market_data = await self.market_data_collector.collect_all()
            
            if market_data.get("errors"):
                for error in market_data["errors"]:
                    logger.warning(f"  ⚠️  {error}")
                    errors.append(error)
            
            # STEP 2: Analyze each event semantically
            logger.info("STEP 2: Semantic analysis of market events...")
            analysis_results = await self._analyze_market_data(market_data)
            
            # STEP 3: Store findings in KB
            logger.info("STEP 3: Storing research findings in knowledge base...")
            stored_entries = self._store_research_findings(cycle_id, analysis_results)
            
            # STEP 4: Create daily summary
            logger.info("STEP 4: Creating daily market summary...")
            daily_summary = self._create_daily_summary(analysis_results)
            
            # STEP 5: Prepare handoff to trading agent
            logger.info("STEP 5: Preparing handoff to trading agent...")
            handoff = self._prepare_trading_handoff(cycle_id, daily_summary)
            
            cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            
            result = {
                "success": True,
                "cycle_id": cycle_id,
                "duration_seconds": cycle_duration,
                "market_data": {
                    "timestamp": market_data.get("timestamp"),
                    "sources_collected": self._count_sources(market_data),
                    "errors": market_data.get("errors", [])
                },
                "analysis": {
                    "events_analyzed": len(analysis_results.get("individual_events", [])),
                    "net_bias": analysis_results.get("net_bias"),
                    "confidence": analysis_results.get("confidence"),
                    "volatility_risk": analysis_results.get("volatility_risk"),
                    "recommendation": analysis_results.get("overall_recommendation")
                },
                "storage": {
                    "entries_stored": stored_entries,
                    "kb_collection": "symbol_research_daily"
                },
                "handoff": {
                    "handoff_id": handoff.id,
                    "to_agent": "trading_agent",
                    "status": handoff.status
                },
                "errors": errors
            }
            
            self.last_cycle_timestamp = cycle_start
            self.last_cycle_data = result
            
            logger.info("=" * 70)
            logger.info(f"DAILY RESEARCH CYCLE COMPLETED")
            logger.info(f"  Duration: {cycle_duration:.1f}s")
            logger.info(f"  Events analyzed: {result['analysis']['events_analyzed']}")
            logger.info(f"  Entries stored: {stored_entries}")
            logger.info(f"  Net bias: {daily_summary.get('net_bias')}")
            logger.info(f"  Confidence: {daily_summary.get('confidence'):.2%}")
            logger.info("=" * 70)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during research cycle: {e}", exc_info=True)
            errors.append(str(e))
            
            return {
                "success": False,
                "cycle_id": cycle_id,
                "duration_seconds": (datetime.now(timezone.utc) - cycle_start).total_seconds(),
                "errors": errors
            }
    
    async def _analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform semantic analysis of market data.
        
        Uses LLM to understand:
        - Direction (BULLISH_GOLD, BEARISH_GOLD, NEUTRAL, CONFLICTING)
        - Confidence (0.0 to 1.0)
        - Risk level (LOW, MEDIUM, HIGH)
        - Trading recommendation
        """
        
        # Build list of market events from raw data
        events = self._extract_events_from_data(market_data)
        
        if not events:
            logger.warning("No market events extracted from data")
            return {
                "individual_events": [],
                "net_bias": "NEUTRAL",
                "confidence": 0.0,
                "overall_recommendation": "HOLD"
            }
        
        logger.info(f"  Extracted {len(events)} market events for analysis")
        
        # Analyze individual events
        individual_analyses = []
        for event in events:
            try:
                analysis = await self._analyze_single_event(event)
                individual_analyses.append(analysis)
            except Exception as e:
                logger.warning(f"  Error analyzing event {event.get('name')}: {e}")
                continue
        
        logger.info(f"  Successfully analyzed {len(individual_analyses)} events")
        
        # Perform combined analysis
        try:
            combined_analysis = await self._analyze_combined_events(individual_analyses)
        except Exception as e:
            logger.warning(f"  Error in combined analysis: {e}")
            combined_analysis = {
                "net_bias": "NEUTRAL",
                "confidence": 0.5,
                "overall_recommendation": "HOLD",
                "volatility_risk": "MEDIUM",
                "trading_confidence": 0.5
            }
        
        return {
            "individual_events": individual_analyses,
            **combined_analysis
        }
    
    async def _analyze_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single market event."""
        
        prompt = f"""
        Analyze this market event for impact on XAUUSD (Gold vs USD):
        
        Event: {event.get('name')}
        Type: {event.get('type')}
        Description: {event.get('description', 'N/A')}
        
        Provide analysis in JSON format:
        {{
            "direction": "BULLISH_GOLD | BEARISH_GOLD | NEUTRAL | CONFLICTING",
            "confidence": 0.75,
            "reasoning": "Clear explanation of impact",
            "risk_level": "LOW | MEDIUM | HIGH",
            "recommendation": "BUY | SELL | REDUCE_POSITION | HOLD | AVOID",
            "position_size_adjustment": 0.8,
            "volatility_expected": "LOW | MEDIUM | HIGH"
        }}
        
        Be concise but clear. Focus on the XAUUSD relationship specifically.
        """
        
        try:
            response = self.llm.invoke(prompt)
            analysis_text = response.content
            
            # Extract JSON
            import re
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(analysis_text)
            
            analysis["event"] = event
            return analysis
            
        except Exception as e:
            logger.warning(f"Error analyzing single event: {e}")
            return {
                "direction": "NEUTRAL",
                "confidence": 0.3,
                "reasoning": f"Analysis failed: {str(e)}",
                "risk_level": "MEDIUM",
                "recommendation": "HOLD",
                "position_size_adjustment": 1.0,
                "event": event
            }
    
    async def _analyze_combined_events(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze interactions between multiple events."""
        
        # Build summary of individual analyses
        summary = "\n".join([
            f"- {a.get('direction')} (confidence: {a.get('confidence')}, "
            f"reason: {a.get('reasoning')})"
            for a in analyses
        ])
        
        prompt = f"""
        Analyze the combined impact of these market events on XAUUSD:
        
        {summary}
        
        Provide combined analysis in JSON format:
        {{
            "net_bias": "BULLISH_GOLD | BEARISH_GOLD | NEUTRAL | CONFLICTING",
            "confidence": 0.72,
            "primary_driver": "Description of strongest signal",
            "contradictions": ["List of any conflicting signals"],
            "overall_recommendation": "BUY | SELL | REDUCE_POSITION | HOLD | AVOID",
            "volatility_risk": "LOW | MEDIUM | HIGH",
            "trading_confidence": 0.65,
            "suggested_position_size": 0.8,
            "market_condition_description": "Overall market context"
        }}
        """
        
        try:
            response = self.llm.invoke(prompt)
            analysis_text = response.content
            
            # Extract JSON
            import re
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(analysis_text)
            
            return analysis
            
        except Exception as e:
            logger.warning(f"Error in combined analysis: {e}")
            return {
                "net_bias": "NEUTRAL",
                "confidence": 0.5,
                "overall_recommendation": "HOLD",
                "volatility_risk": "MEDIUM",
                "trading_confidence": 0.5,
                "suggested_position_size": 1.0
            }
    
    def _store_research_findings(self, cycle_id: str, analysis: Dict[str, Any]) -> int:
        """
        Store research findings in knowledge base.
        
        Returns:
            Number of entries stored
        """
        entries_stored = 0
        
        # Store individual event analyses
        for event_analysis in analysis.get("individual_events", []):
            try:
                entry = {
                    "cycle_id": cycle_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_name": event_analysis.get("event", {}).get("name"),
                    "event_type": event_analysis.get("event", {}).get("type"),
                    "direction": event_analysis.get("direction"),
                    "confidence": event_analysis.get("confidence"),
                    "reasoning": event_analysis.get("reasoning"),
                    "recommendation": event_analysis.get("recommendation"),
                    "risk_level": event_analysis.get("risk_level"),
                    "volatility": event_analysis.get("volatility_expected"),
                }
                
                # Store in KB
                self.knowledge_base.add_research_finding(entry)
                entries_stored += 1
                
            except Exception as e:
                logger.warning(f"Error storing research finding: {e}")
        
        # Store combined analysis summary
        try:
            summary_entry = {
                "cycle_id": cycle_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "daily_summary",
                "net_bias": analysis.get("net_bias"),
                "confidence": analysis.get("confidence"),
                "overall_recommendation": analysis.get("overall_recommendation"),
                "volatility_risk": analysis.get("volatility_risk"),
                "trading_confidence": analysis.get("trading_confidence"),
                "market_description": analysis.get("market_condition_description")
            }
            
            self.knowledge_base.add_research_finding(summary_entry)
            entries_stored += 1
            
        except Exception as e:
            logger.warning(f"Error storing daily summary: {e}")
        
        return entries_stored
    
    def _create_daily_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create summary for trading agent."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "net_bias": analysis.get("net_bias"),
            "confidence": analysis.get("confidence"),
            "overall_recommendation": analysis.get("overall_recommendation"),
            "volatility_risk": analysis.get("volatility_risk"),
            "trading_confidence": analysis.get("trading_confidence"),
            "suggested_position_size": analysis.get("suggested_position_size"),
            "market_description": analysis.get("market_condition_description"),
            "event_count": len(analysis.get("individual_events", []))
        }
    
    def _prepare_trading_handoff(self, cycle_id: str, summary: Dict[str, Any]):
        """Prepare handoff to trading agent."""
        
        handoff = self.handoff_protocol.prepare_handoff(
            from_agent="research",
            to_agent="trader",
            version_id=cycle_id,
            payload={
                "research_cycle_id": cycle_id,
                "market_summary": summary,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            reason="Daily market research cycle completed",
            metadata={
                "cycle_number": self.cycle_count,
                "data_sources": ["economic_calendar", "news", "central_banks", "geopolitical", "gold", "usd"]
            }
        )
        
        return handoff
    
    def _extract_events_from_data(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract events from raw market data."""
        events = []
        
        # Extract from economic calendar
        if market_data.get("economic_calendar"):
            cal = market_data["economic_calendar"]
            for item in cal.get("upcoming", []) + cal.get("released", []):
                events.append({
                    "type": "economic",
                    "name": item.get("name", "Unknown event"),
                    "description": item.get("description", "")
                })
        
        # Extract from news
        if market_data.get("news"):
            for article in market_data["news"].get("bloomberg", []) + \
                           market_data["news"].get("reuters", []):
                events.append({
                    "type": "news",
                    "name": article.get("title", "News"),
                    "description": article.get("summary", "")
                })
        
        # Extract from geopolitical
        if market_data.get("geopolitical"):
            geo = market_data["geopolitical"]
            for event in geo.get("wars", []) + geo.get("sanctions", []):
                events.append({
                    "type": "geopolitical",
                    "name": event.get("name", "Geopolitical event"),
                    "description": event.get("description", "")
                })
        
        return events
    
    def _count_sources(self, market_data: Dict[str, Any]) -> int:
        """Count how many sources returned data."""
        count = 0
        for source in ["economic_calendar", "news", "central_bank", "geopolitical", "gold_news", "usd_strength"]:
            if market_data.get(source) is not None:
                count += 1
        return count


# Factory function
def create_enhanced_research_agent() -> EnhancedResearchAgent:
    """Create and return an enhanced research agent."""
    return EnhancedResearchAgent()
