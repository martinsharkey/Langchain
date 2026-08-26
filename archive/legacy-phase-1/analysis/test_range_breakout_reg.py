#!/usr/bin/env python
"""Quick test of RangeBreakout strategy registration."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.strategy_registry import StrategyRegistry

registry = StrategyRegistry()

# Check if RangeBreakout is registered
rb = registry.get("RangeBreakout")

if rb:
    print("SUCCESS: RangeBreakout found in registry")
    print(f"Name: {rb.name}")
    print(f"Description: {rb.description}")
    print(f"Indicators needed: {rb.indicators_used}")
else:
    print("ERROR: RangeBreakout not found")
    print("\nAvailable strategies:")
    for s in registry.get_all():
        print(f"  - {s.name}")
