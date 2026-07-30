"""
Multi-Agent Orchestration System — Integration of Version, Handoff, and Research

This module provides the unified system that orchestrates:
1. Version management (code and tests synchronized)
2. Handoff protocol (atomic agent-to-agent transfers)
3. Daily research cycle (market intelligence)
4. Trading integration (research context applied to trades)

Usage:
    orchestrator = MultiAgentOrchestrator()
    orchestrator.start()  # Starts the research scheduler
    orchestrator.stop()   # Stops the scheduler
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from src.core.version_manager import VersionManager
from src.core.handoff_protocol import HandoffProtocol
from src.core.research_scheduler import ResearchScheduler
from src.agents.enhanced_research_agent import EnhancedResearchAgent
from src.learning.knowledge_base import KnowledgeBase

logger = logging.getLogger("orchestration.multi_agent_orchestrator")


class MultiAgentOrchestrator:
    """
    Central orchestration system for all agents and handoffs.
    """
    
    def __init__(self):
        """Initialize all components."""
        self.version_manager = VersionManager()
        self.handoff_protocol = HandoffProtocol(self.version_manager)
        self.knowledge_base = KnowledgeBase()
        self.research_agent = EnhancedResearchAgent(
            version_manager=self.version_manager,
            handoff_protocol=self.handoff_protocol,
            knowledge_base=self.knowledge_base
        )
        
        # Create and configure scheduler
        self.scheduler = ResearchScheduler(
            research_callback=self.research_agent.run_daily_cycle
        )
        
        self.is_running = False
        
        logger.info("MultiAgentOrchestrator initialized")
    
    def start(self):
        """Start the orchestration system."""
        logger.info("=" * 70)
        logger.info("STARTING MULTI-AGENT ORCHESTRATION SYSTEM")
        logger.info("=" * 70)
        
        self.scheduler.start()
        self.is_running = True
        
        logger.info("✓ Research scheduler started")
        logger.info("✓ All agents ready")
        logger.info("")
        logger.info("System status:")
        self.print_status()
    
    def stop(self):
        """Stop the orchestration system."""
        logger.info("Stopping multi-agent orchestration system...")
        
        self.scheduler.stop()
        self.is_running = False
        
        logger.info("✓ Research scheduler stopped")
        logger.info("✓ All agents stopped")
    
    def print_status(self):
        """Print current system status."""
        scheduler_status = self.scheduler.get_status()
        
        print(f"""
  Scheduler Status:
    - Running: {scheduler_status['is_running']}
    - Trigger: {scheduler_status['trigger_time']}
    - Next run: {scheduler_status.get('next_run', 'N/A')}
    - Total runs: {scheduler_status['run_count']}
  
  Research Agent:
    - Name: {self.research_agent.name}
    - Status: {'Ready' if self.is_running else 'Stopped'}
    - Cycles completed: {self.research_agent.cycle_count}
  
  Version Manager:
    - Database: {self.version_manager.db_path}
    - Status: Active
  
  Handoff Protocol:
    - Database: {self.handoff_protocol.db_path}
    - Status: Active
  
  Knowledge Base:
    - Status: Active
        """)
    
    def get_research_context_for_trading(self) -> Dict[str, Any]:
        """
        Get today's research context for the trading agent to use.
        
        Called by trading agent when making decisions.
        """
        
        if not self.research_agent.last_cycle_data:
            return {
                "has_research": False,
                "reason": "No research cycle has run yet"
            }
        
        cycle_data = self.research_agent.last_cycle_data
        
        if not cycle_data.get("success"):
            return {
                "has_research": False,
                "reason": "Last research cycle failed",
                "error": cycle_data.get("errors", [])
            }
        
        # Build trading context from research
        return {
            "has_research": True,
            "research_cycle_id": cycle_data.get("cycle_id"),
            "timestamp": cycle_data.get("market_data", {}).get("timestamp"),
            "analysis": {
                "net_bias": cycle_data.get("analysis", {}).get("net_bias"),
                "confidence": cycle_data.get("analysis", {}).get("confidence"),
                "volatility_risk": cycle_data.get("analysis", {}).get("volatility_risk"),
                "recommendation": cycle_data.get("analysis", {}).get("recommendation"),
                "events_analyzed": cycle_data.get("analysis", {}).get("events_analyzed")
            },
            "full_cycle_data": cycle_data
        }
    
    def apply_research_to_trade_decision(
        self,
        trade_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Modify a trade decision based on research context.
        
        Called by trading agent before executing a trade.
        
        Args:
            trade_decision: Original trade decision with action, size, sl, tp, etc.
            
        Returns:
            Modified trade decision with research-based adjustments
        """
        
        research_context = self.get_research_context_for_trading()
        
        if not research_context.get("has_research"):
            logger.info("No research context available for trade")
            return trade_decision
        
        # Get research bias
        research_bias = research_context["analysis"]["net_bias"]
        trade_action = trade_decision.get("action", "").upper()  # BUY or SELL
        
        # Check for conflicts
        if "BULLISH" in research_bias and trade_action == "SELL":
            logger.warning(
                f"Trade CONFLICT: Research is BULLISH_GOLD but trade is SELL. "
                f"Reducing position size."
            )
            trade_decision["position_size"] *= 0.5
            trade_decision["confidence"] *= 0.8
            
        elif "BEARISH" in research_bias and trade_action == "BUY":
            logger.warning(
                f"Trade CONFLICT: Research is BEARISH_GOLD but trade is BUY. "
                f"Reducing position size."
            )
            trade_decision["position_size"] *= 0.5
            trade_decision["confidence"] *= 0.8
        
        # Apply volatility adjustments
        volatility = research_context["analysis"]["volatility_risk"]
        if volatility == "HIGH":
            logger.info(f"High volatility expected. Widening stops.")
            if "stop_loss" in trade_decision:
                trade_decision["stop_loss"] *= 1.5  # Wider stops
            if "take_profit" in trade_decision:
                trade_decision["take_profit"] *= 1.2  # Keep TP closer for risk management
        
        # Add research metadata to trade record
        trade_decision["research_context"] = {
            "cycle_id": research_context["research_cycle_id"],
            "net_bias": research_bias,
            "confidence": research_context["analysis"]["confidence"],
            "applied_at": datetime.now(timezone.utc).isoformat()
        }
        
        return trade_decision
    
    def get_pending_handoffs(self, agent_name: str) -> list:
        """Get all pending handoffs for a specific agent."""
        return self.handoff_protocol.get_pending_handoffs(agent_name)
    
    def record_code_change(
        self,
        module: str,
        description: str,
        author: str,
        code_content: Optional[str] = None
    ):
        """Record a code change."""
        return self.version_manager.record_code_change(
            module=module,
            description=description,
            author=author,
            code_content=code_content
        )
    
    def record_test_results(
        self,
        version_id: str,
        test_name: str,
        passed: bool,
        agent_run_by: str,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Record test results."""
        return self.version_manager.record_test_results(
            version_id=version_id,
            test_name=test_name,
            passed=passed,
            agent_run_by=agent_run_by,
            error_message=error_message,
            details=details
        )


# Global instance
_orchestrator: Optional[MultiAgentOrchestrator] = None


def get_orchestrator() -> MultiAgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MultiAgentOrchestrator()
    return _orchestrator
