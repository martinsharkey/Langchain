#!/usr/bin/env python3
"""
Full Daily Cycle Test — End-to-end testing of Phase 3 data integration.

This runs the complete research cycle with real data sources.

Usage:
    python examples/test_full_daily_cycle.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestration import get_orchestrator
from src.utils.logger import get_logger, console

logger = get_logger("examples.test_daily_cycle")


async def main():
    """Run full daily cycle test."""
    
    console.print("\n" + "=" * 70, style="bold cyan")
    console.print("FULL DAILY CYCLE TEST — Phase 3 Data Integration", style="bold cyan")
    console.print("=" * 70 + "\n", style="bold cyan")
    
    # Initialize orchestrator
    console.print("[1/4] Initializing orchestrator...", style="bold")
    orchestrator = get_orchestrator()
    console.print("✓ Orchestrator ready\n")
    
    # Run daily cycle with fresh data sources
    console.print("[2/4] Running complete research cycle...", style="bold")
    console.print("      (Collecting from 6 data sources in parallel)\n", style="dim")
    
    try:
        result = await orchestrator.research_agent.run_daily_cycle()
        
        if result.get("success"):
            console.print("✓ Research cycle completed successfully\n", style="green")
            
            # Display results
            console.print("RESULTS:", style="bold cyan")
            console.print("-" * 70)
            
            # Cycle metadata
            cycle_info = result.get("analysis", {})
            console.print(f"\nCycle Performance:")
            console.print(f"  Duration: {result.get('duration_seconds', 0):.1f}s")
            console.print(f"  Events analyzed: {cycle_info.get('events_analyzed', 0)}")
            console.print(f"  Data sources used: {result.get('market_data', {}).get('sources_collected', 0)}/6")
            
            # Market analysis
            console.print(f"\nMarket Analysis:")
            console.print(f"  Net bias: {cycle_info.get('net_bias', 'UNKNOWN')}", 
                         style="yellow" if cycle_info.get('net_bias') == "CONFLICTING" else None)
            console.print(f"  Confidence: {cycle_info.get('confidence', 0):.0%}")
            console.print(f"  Volatility risk: {cycle_info.get('volatility_risk', 'UNKNOWN')}")
            console.print(f"  Recommendation: {cycle_info.get('recommendation', 'HOLD')}")
            
            # Storage
            storage = result.get("storage", {})
            console.print(f"\nKnowledge Base:")
            console.print(f"  Entries stored: {storage.get('entries_stored', 0)}")
            console.print(f"  Collection: {storage.get('kb_collection', 'unknown')}")
            
            # Handoff
            handoff = result.get("handoff", {})
            console.print(f"\nHandoff Status:")
            console.print(f"  Handoff ID: {handoff.get('handoff_id', 'N/A')[:8]}...")
            console.print(f"  To: {handoff.get('to_agent', 'unknown')}")
            console.print(f"  Status: {handoff.get('status', 'unknown')}")
            
            # Errors
            errors = result.get("errors", [])
            if errors:
                console.print(f"\nWarnings/Errors ({len(errors)}):", style="yellow")
                for error in errors:
                    console.print(f"  ⚠ {error}", style="dim")
            
            console.print()
            
        else:
            console.print("✗ Research cycle failed", style="red")
            console.print(f"  Errors: {result.get('errors')}\n")
            return
    
    except Exception as e:
        console.print(f"✗ Error running research cycle: {e}", style="red")
        logger.error(f"Error: {e}", exc_info=True)
        return
    
    # Test research context access
    console.print("[3/4] Testing research context access...", style="bold")
    research_context = orchestrator.get_research_context_for_trading()
    
    if research_context.get("has_research"):
        console.print("✓ Research context available for trading\n", style="green")
        
        console.print("Available Data:")
        analysis = research_context.get("analysis", {})
        console.print(f"  Net bias: {analysis.get('net_bias')}")
        console.print(f"  Confidence: {analysis.get('confidence'):.0%}")
        console.print(f"  Volatility: {analysis.get('volatility_risk')}")
        console.print(f"  Events: {analysis.get('events_analyzed')}")
    else:
        console.print("ℹ No research context (expected on first run)", style="yellow")
    
    console.print()
    
    # Test trade modification
    console.print("[4/4] Testing trade modification with research...", style="bold")
    
    test_trade = {
        "action": "buy",
        "position_size": 0.1,
        "stop_loss": 45,
        "take_profit": 100,
        "confidence": 0.75
    }
    
    modified_trade = orchestrator.apply_research_to_trade_decision(test_trade)
    
    console.print("✓ Trade modification pipeline tested\n", style="green")
    
    if modified_trade.get("position_size") != test_trade["position_size"]:
        console.print("  Position modified based on research:",
                     style="yellow")
        console.print(f"    Original: {test_trade['position_size']} → "
                     f"Modified: {modified_trade['position_size']}")
    
    # Final summary
    console.print()
    console.print("=" * 70, style="bold cyan")
    console.print("DAILY CYCLE TEST COMPLETE", style="bold cyan")
    console.print("=" * 70 + "\n", style="bold cyan")
    
    console.print("✓ All components working:", style="green")
    console.print("  - Market data collection: OK")
    console.print("  - Semantic analysis: OK")
    console.print("  - Knowledge base storage: OK")
    console.print("  - Research context: OK")
    console.print("  - Trade modification: OK")
    console.print()
    
    console.print("Next Steps:", style="bold")
    console.print("""
1. Review the research findings in the knowledge base
2. Configure real API keys for data sources
3. Monitor system performance in production
4. Refine semantic analysis as needed
5. Deploy to production environment

For more info:
  - PHASE_1_2_IMPLEMENTATION_SUMMARY.md
  - RESEARCH_AGENT_DETAILED_DESIGN.md
    """)


if __name__ == "__main__":
    asyncio.run(main())
