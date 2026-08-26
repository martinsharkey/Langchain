#!/usr/bin/env python
"""Quick test of the new OsMA_RegimeAdaptive strategy."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.strategy_registry import StrategyRegistry

registry = StrategyRegistry()

# Check if new strategy is registered
new_strat = registry.get("OsMA_RegimeAdaptive")

if new_strat:
    print("✓ OsMA_RegimeAdaptive found in registry")
    print(f"  Description: {new_strat.description}")
    print(f"  Indicators: {new_strat.indicators_used}")
else:
    print("❌ OsMA_RegimeAdaptive not found")
    print("\nAvailable strategies:")
    for s in registry.get_all():
        print(f"  - {s.name}")
