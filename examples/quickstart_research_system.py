#!/usr/bin/env python3
"""
Quick Start Example — Multi-Agent Research System

This example shows how to:
1. Initialize the orchestrator
2. Start the daily research scheduler
3. Access research context
4. Apply research to trades

Run this to test the system:
    python examples/quickstart_research_system.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestration import get_orchestrator
from src.utils.logger import get_logger, console

logger = get_logger("examples.quickstart")


async def main():
    """Run the quick start example."""
    
    console.print("\n" + "=" * 70, style="bold cyan")
    console.print("MULTI-AGENT RESEARCH SYSTEM — QUICK START", style="bold cyan")
    console.print("=" * 70 + "\n", style="bold cyan")
    
    # STEP 1: Initialize orchestrator
    console.print("[1/5] Initializing orchestrator...", style="bold")
    orchestrator = get_orchestrator()
    console.print("✓ Orchestrator initialized\n")
    
    # STEP 2: Start the system
    console.print("[2/5] Starting system...", style="bold")
    orchestrator.start()
    console.print("✓ System started\n")
    
    # STEP 3: Force a research cycle (for testing)
    console.print("[3/5] Running research cycle (test)...", style="bold")
    console.print(
        "      (This would normally run at 00:00 UTC daily)\n",
        style="dim"
    )
    
    try:
        result = await orchestrator.research_agent.run_daily_cycle()
        
        if result.get("success"):
            console.print(f"✓ Research cycle completed successfully", style="green")
            console.print(f"  - Events analyzed: {result['analysis']['events_analyzed']}")
            console.print(f"  - Entries stored: {result['storage']['entries_stored']}")
            console.print(f"  - Net bias: {result['analysis']['net_bias']}")
            console.print(f"  - Confidence: {result['analysis']['confidence']:.0%}\n")
        else:
            console.print(f"✗ Research cycle failed", style="red")
            console.print(f"  - Errors: {result.get('errors')}\n")
    
    except Exception as e:
        console.print(f"✗ Error running research cycle: {e}", style="red")
        logger.error(f"Error: {e}", exc_info=True)
    
    # STEP 4: Get research context
    console.print("[4/5] Accessing research context...", style="bold")
    research_context = orchestrator.get_research_context_for_trading()
    
    if research_context.get("has_research"):
        console.print(f"✓ Research context available", style="green")
        console.print(f"  - Cycle ID: {research_context['research_cycle_id']}")
        console.print(f"  - Net bias: {research_context['analysis']['net_bias']}")
        console.print(f"  - Confidence: {research_context['analysis']['confidence']:.0%}")
        console.print(f"  - Volatility: {research_context['analysis']['volatility_risk']}")
        console.print()
    else:
        console.print(f"ℹ No research context available yet", style="yellow")
        console.print(f"  - Reason: {research_context.get('reason')}\n")
    
    # STEP 5: Test trade modification
    console.print("[5/5] Testing trade modification with research...", style="bold")
    
    # Original trade
    original_trade = {
        "action": "buy",
        "position_size": 0.1,
        "stop_loss": 45,
        "take_profit": 100,
        "confidence": 0.75
    }
    
    console.print(f"\nOriginal trade decision:")
    console.print(f"  - Action: {original_trade['action'].upper()}")
    console.print(f"  - Size: {original_trade['position_size']} lots")
    console.print(f"  - SL: {original_trade['stop_loss']} pips")
    console.print(f"  - TP: {original_trade['take_profit']} pips")
    
    # Apply research
    modified_trade = orchestrator.apply_research_to_trade_decision(original_trade)
    
    console.print(f"\nModified trade (with research applied):")
    console.print(f"  - Action: {modified_trade['action'].upper()}")
    console.print(f"  - Size: {modified_trade['position_size']} lots", 
                  style="yellow" if modified_trade['position_size'] != original_trade['position_size'] else None)
    console.print(f"  - SL: {modified_trade['stop_loss']} pips",
                  style="yellow" if modified_trade['stop_loss'] != original_trade['stop_loss'] else None)
    console.print(f"  - TP: {modified_trade['take_profit']} pips")
    
    if "research_context" in modified_trade:
        console.print(f"\nResearch applied:")
        ctx = modified_trade["research_context"]
        console.print(f"  - Cycle: {ctx['cycle_id']}")
        console.print(f"  - Bias: {ctx['net_bias']}")
        console.print(f"  - Applied at: {ctx['applied_at']}")
    
    console.print()
    
    # STEP 6: Show system status
    console.print("SYSTEM STATUS", style="bold cyan")
    console.print("-" * 70)
    orchestrator.print_status()
    
    # Graceful shutdown
    console.print("\nShutting down...", style="dim")
    orchestrator.stop()
    console.print("✓ System stopped\n", style="green")
    
    console.print("=" * 70, style="bold cyan")
    console.print("QUICK START COMPLETE", style="bold cyan")
    console.print("=" * 70 + "\n", style="bold cyan")
    
    console.print("Next steps:", style="bold")
    console.print("""
1. Review the architecture in PHASE_1_2_IMPLEMENTATION_SUMMARY.md
2. Check the orchestrator status regularly
3. Integrate real data sources in Phase 3
4. Run full integration tests

For more info, see:
  - src/orchestration/multi_agent_orchestrator.py
  - src/agents/enhanced_research_agent.py
  - RESEARCH_AGENT_DETAILED_DESIGN.md
    """)


if __name__ == "__main__":
    # Run the async main
    asyncio.run(main())
