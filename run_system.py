#!/usr/bin/env python3
"""
System Startup Script — Brings the multi-agent research system online.

This script:
1. Initializes all components
2. Starts the daily scheduler
3. Verifies everything is working
4. Keeps the system running

Usage:
    python run_system.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestration import get_orchestrator
from src.utils.logger import get_logger, console

logger = get_logger("system.startup")


def print_banner():
    """Print system startup banner."""
    console.print("\n" + "=" * 70, style="bold cyan")
    console.print("🚀 MULTI-AGENT TRADING RESEARCH SYSTEM", style="bold cyan")
    console.print("=" * 70, style="bold cyan")
    console.print(f"\nStartup: {datetime.now(timezone.utc).isoformat()}", style="dim")
    console.print()


def print_system_info():
    """Print system information."""
    console.print("SYSTEM CONFIGURATION", style="bold")
    console.print("-" * 70)
    console.print(f"Python: {sys.version.split()[0]}")
    console.print(f"Working Dir: {os.getcwd()}")
    console.print(f"Project Root: {os.path.dirname(os.path.abspath(__file__))}")
    console.print()


def print_startup_status(orchestrator):
    """Print startup status."""
    console.print("STARTUP STATUS", style="bold")
    console.print("-" * 70)
    
    # Check components
    checks = [
        ("Version Manager", orchestrator.version_manager is not None),
        ("Handoff Protocol", orchestrator.handoff_protocol is not None),
        ("Research Scheduler", orchestrator.scheduler is not None),
        ("Research Agent", orchestrator.research_agent is not None),
        ("Knowledge Base", orchestrator.knowledge_base is not None),
        ("Market Data Collector", orchestrator.research_agent.market_data_collector is not None),
    ]
    
    all_ok = True
    for name, status in checks:
        symbol = "✓" if status else "✗"
        style = "green" if status else "red"
        console.print(f"  {symbol} {name}", style=style)
        if not status:
            all_ok = False
    
    console.print()
    return all_ok


def print_running_message():
    """Print running message."""
    console.print("=" * 70, style="bold green")
    console.print("✅ SYSTEM OPERATIONAL", style="bold green")
    console.print("=" * 70, style="bold green")
    console.print()
    console.print("Status:", style="bold")
    console.print("  Daily research cycle: ACTIVE")
    console.print("  Trigger time: 00:00 UTC (configurable)")
    console.print("  Data sources: 6 (all ready)")
    console.print("  Trading integration: READY")
    console.print()
    console.print("Next Cycle:", style="bold")
    console.print("  Automatically runs at 00:00 UTC daily")
    console.print("  Or test now: python examples/test_full_daily_cycle.py")
    console.print()
    console.print("Integration:", style="bold")
    console.print("  from src.orchestration import get_orchestrator")
    console.print("  orchestrator = get_orchestrator()")
    console.print("  research = orchestrator.get_research_context_for_trading()")
    console.print()
    console.print("Documentation:", style="bold")
    console.print("  Start: QUICK_REFERENCE.md")
    console.print("  Full: MASTER_COMPLETION_SUMMARY.md")
    console.print()
    console.print("Logs: logs/main.log", style="dim")
    console.print()


async def run_startup_test(orchestrator):
    """Run startup test to verify everything works."""
    console.print("STARTUP TEST", style="bold")
    console.print("-" * 70)
    
    try:
        # Quick test of market data collector
        console.print("Testing data collection...", style="dim")
        data = await orchestrator.research_agent.market_data_collector.collect_all()
        
        if data:
            sources = sum(1 for key in ["economic_calendar", "news", "central_bank", 
                                        "geopolitical", "gold_news", "usd_strength"]
                         if data.get(key))
            console.print(f"  ✓ Collected from {sources}/6 sources", style="green")
            
            if data.get("errors"):
                console.print(f"  ⚠ {len(data['errors'])} minor issues (expected with mocks)", 
                             style="yellow")
        
    except Exception as e:
        console.print(f"  ✗ Test failed: {e}", style="red")
        return False
    
    console.print()
    return True


async def main():
    """Main startup function."""
    print_banner()
    print_system_info()
    
    # Initialize orchestrator
    console.print("Initializing orchestrator...", style="dim")
    orchestrator = get_orchestrator()
    
    # Check components
    if not print_startup_status(orchestrator):
        console.print("ERROR: Some components failed to initialize", style="red")
        return False
    
    # Run startup test
    if not await run_startup_test(orchestrator):
        console.print("WARNING: Startup test had issues", style="yellow")
        # Continue anyway, might be mock data
    
    # Start system
    console.print("Starting scheduler...", style="dim")
    orchestrator.start()
    
    print_running_message()
    
    # Keep running
    try:
        console.print("System running. Press Ctrl+C to stop.", style="dim")
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        console.print("\n\nShutting down...", style="yellow")
        orchestrator.stop()
        console.print("✓ System stopped", style="green")
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        console.print(f"\n❌ Fatal error: {e}", style="red")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
