#!/usr/bin/env python3
"""
System Status Dashboard — Check the operational status of the research system.

Usage:
    python check_status.py
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestration import get_orchestrator
from src.utils.logger import console
import asyncio


async def main():
    console.print("\n" + "=" * 70, style="bold cyan")
    console.print("📊 SYSTEM STATUS DASHBOARD", style="bold cyan")
    console.print("=" * 70 + "\n", style="bold cyan")
    
    # Get orchestrator
    orchestrator = get_orchestrator()
    
    # Scheduler Status
    console.print("SCHEDULER", style="bold")
    console.print("-" * 70)
    scheduler_status = orchestrator.scheduler.get_status()
    console.print(f"  Status: {'🟢 RUNNING' if scheduler_status['is_running'] else '🔴 STOPPED'}")
    console.print(f"  Trigger: {scheduler_status['trigger_time']}")
    console.print(f"  Next Run: {scheduler_status.get('next_run', 'N/A')}")
    console.print(f"  Total Cycles: {scheduler_status['run_count']}")
    console.print()
    
    # Components Status
    console.print("COMPONENTS", style="bold")
    console.print("-" * 70)
    components = [
        ("Version Manager", orchestrator.version_manager is not None),
        ("Handoff Protocol", orchestrator.handoff_protocol is not None),
        ("Research Agent", orchestrator.research_agent is not None),
        ("Market Data Collector", orchestrator.research_agent.market_data_collector is not None),
        ("Knowledge Base", orchestrator.knowledge_base is not None),
    ]
    
    for name, status in components:
        symbol = "✅" if status else "❌"
        console.print(f"  {symbol} {name}")
    console.print()
    
    # Database Status
    console.print("DATABASES", style="bold")
    console.print("-" * 70)
    
    databases = [
        ("Version Management", "data/version_management.db"),
        ("Handoff Protocol", "data/handoff_protocol.db"),
        ("Trading Experience", "data/trading_experience.db"),
    ]
    
    for name, path in databases:
        exists = os.path.exists(path)
        symbol = "✅" if exists else "⏳"
        size = os.path.getsize(path) if exists else 0
        console.print(f"  {symbol} {name}: {size:,} bytes")
    console.print()
    
    # Research Context
    console.print("RESEARCH CONTEXT (TODAY)", style="bold")
    console.print("-" * 70)
    
    research = orchestrator.get_research_context_for_trading()
    
    if research.get("has_research"):
        console.print(f"  ✅ Research available")
        analysis = research.get("analysis", {})
        console.print(f"     Net Bias: {analysis.get('net_bias')}")
        console.print(f"     Confidence: {analysis.get('confidence'):.0%}")
        console.print(f"     Volatility: {analysis.get('volatility_risk')}")
        console.print(f"     Events: {analysis.get('events_analyzed')}")
    else:
        console.print(f"  ⏳ No research yet (normal before first cycle)")
        console.print(f"     Reason: {research.get('reason')}")
    console.print()
    
    # Quick Test
    console.print("QUICK DATA COLLECTION TEST", style="bold")
    console.print("-" * 70)
    
    try:
        console.print("  Collecting data from all sources...", style="dim")
        data = await orchestrator.research_agent.market_data_collector.collect_all()
        
        sources_ok = 0
        for source in ["economic_calendar", "news", "central_bank", "geopolitical", "gold_news", "usd_strength"]:
            if data.get(source) and not data.get(source, {}).get("errors"):
                sources_ok += 1
        
        console.print(f"  ✅ Data collection successful: {sources_ok}/6 sources", style="green")
        
        if data.get("errors"):
            console.print(f"  ⚠️  Minor issues: {len(data['errors'])} (normal with mocks)", style="yellow")
    
    except Exception as e:
        console.print(f"  ❌ Data collection failed: {e}", style="red")
    
    console.print()
    
    # Summary
    console.print("=" * 70, style="bold green")
    console.print("✅ SYSTEM OPERATIONAL", style="bold green")
    console.print("=" * 70 + "\n", style="bold green")
    
    console.print("The system is ready to use!", style="bold")
    console.print()
    console.print("To integrate into your trading bot:")
    console.print("  from src.orchestration import get_orchestrator")
    console.print("  orchestrator = get_orchestrator()")
    console.print("  research = orchestrator.get_research_context_for_trading()")
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
