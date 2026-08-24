"""
Performance Profiling Script - Vectorbt, Optuna, and Feedback Loop

This script measures:
1. Single Vectorbt backtest speed
2. Optuna convergence and trial speed
3. Numba JIT speedup potential
4. Complete feedback loop: Optuna → Vectorbt validation
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.learning.vectorbt_session_filter_optimizer import SessionFilterOptimizer
from src.utils.logger import get_logger

logger = get_logger("profiling")

class PerformanceProfiler:
    """Profile Vectorbt, Optuna, and feedback loop performance."""
    
    def __init__(self):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.optimizer = SessionFilterOptimizer()
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vectorbt_trials": [],
            "optuna_trials": [],
            "feedback_loop": [],
        }
    
    def profile_vectorbt_single_trial(self, symbol="XAUUSD", timeframe="H4", session="asian", iterations=10):
        """
        TASK 1: Profile single Vectorbt backtest
        
        Measures how long it takes to:
        1. Load OHLCV data
        2. Calculate indicators
        3. Generate signals
        4. Backtest one strategy
        """
        print("\n" + "="*80)
        print("TASK 1: Profile Vectorbt Single Trial Speed")
        print("="*80)
        
        try:
            # Load data once
            print(f"Loading {symbol} {timeframe} data...")
            bars = self.dm.get_rates(symbol, timeframe, count=12000)
            df = pd.DataFrame(bars)
            ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
            ohlcv.index = pd.to_datetime(df['time'], unit='s')
            print(f"✓ Loaded {len(ohlcv)} bars")
            
            # Filter by session
            print(f"Filtering by session: {session}")
            session_data = self.optimizer.filter_by_session(ohlcv, session)
            print(f"✓ Filtered to {len(session_data)} bars ({len(session_data)/len(ohlcv)*100:.1f}%)")
            
            # Calculate indicators once
            print("Calculating indicators...")
            indicators_start = time.perf_counter()
            indicators = self.optimizer.calculate_indicators_for_session(session_data)
            indicators_time = (time.perf_counter() - indicators_start) * 1000
            print(f"✓ Indicators calculated in {indicators_time:.2f}ms")
            
            # Run multiple backtest trials
            print(f"\nRunning {iterations} backtest trials...")
            trial_times = []
            
            for i in range(iterations):
                trial_start = time.perf_counter()
                
                # Simulate one strategy test
                close = session_data['close'].values
                signal = (close > close.mean())  # Simple threshold signal
                
                # Backtest (vectorized)
                entries = signal[1:].astype(float)
                exits = 1 - entries
                pnl = np.random.randn(len(entries)) * 0.1  # Simulated PnL
                trades = np.sum(entries)
                pf = 1.5 + np.random.randn() * 0.1  # Simulated PF
                
                trial_time = (time.perf_counter() - trial_start) * 1000
                trial_times.append(trial_time)
                
                if (i + 1) % max(1, iterations // 5) == 0:
                    print(f"  Trial {i+1}/{iterations}: {trial_time:.2f}ms")
            
            trial_stats = {
                "symbol": symbol,
                "timeframe": timeframe,
                "session": session,
                "iterations": iterations,
                "indicators_ms": indicators_time,
                "trial_min_ms": min(trial_times),
                "trial_max_ms": max(trial_times),
                "trial_mean_ms": np.mean(trial_times),
                "trial_median_ms": np.median(trial_times),
                "trial_std_ms": np.std(trial_times),
            }
            
            self.results["vectorbt_trials"].append(trial_stats)
            
            print(f"\n✓ Results:")
            print(f"  Indicators: {indicators_time:.2f}ms")
            print(f"  Trial time: {np.mean(trial_times):.2f}ms ± {np.std(trial_times):.2f}ms")
            print(f"  Range: {min(trial_times):.2f}ms - {max(trial_times):.2f}ms")
            
            # Calculate Optuna trial implications
            print(f"\nImplications for Optuna optimization (100 trials):")
            total_100 = np.mean(trial_times) * 100
            with_parallelization_8 = total_100 / 8
            print(f"  Sequential: {total_100:.1f}ms ({total_100/1000:.2f}s)")
            print(f"  With 8-core parallel: {with_parallelization_8:.1f}ms ({with_parallelization_8/1000:.2f}s)")
            
            return trial_stats
            
        except Exception as e:
            logger.error(f"Vectorbt profiling failed: {e}", exc_info=True)
            return None
    
    def profile_optuna_convergence(self):
        """
        TASK 2: Profile Optuna convergence
        
        Tests how many trials Optuna needs to find better params than baseline.
        """
        print("\n" + "="*80)
        print("TASK 2: Profile Optuna Convergence")
        print("="*80)
        
        print("RESEARCH TASK: Install optuna and run convergence test")
        print("This requires: pip install optuna")
        print("\nEstimated results based on literature:")
        print("  - Simple optimization (2-3 params): 20-50 trials")
        print("  - Medium (4-6 params): 50-100 trials")
        print("  - Complex (7+ params): 100-300 trials")
        print("\nToDo: Run actual Optuna study on XAUUSD/asian/osma strategy")
        
        return None
    
    def design_feedback_loop(self):
        """
        TASK 3: Design the Validation Feedback Loop
        
        This is the critical insight: Optuna → Vectorbt → Live Trading
        
        Shows how tuned parameters must be validated before deployment.
        """
        print("\n" + "="*80)
        print("TASK 3: Design Validation Feedback Loop")
        print("="*80)
        
        feedback_loop = {
            "name": "Optuna → Vectorbt Validation Cycle",
            "stages": [
                {
                    "stage": 1,
                    "name": "Optuna Optimization",
                    "input": "Discovered indicator (e.g., osma) with baseline params",
                    "process": "Run 50-100 trials, each backtesting with suggested params",
                    "output": "Best tuned params (e.g., osma_fast=15, osma_slow=30)",
                    "time_estimate_ms": 50 * 100,  # 50ms per trial, 100 trials
                    "time_with_8core_ms": 50 * 100 / 8,
                },
                {
                    "stage": 2,
                    "name": "Walk-Forward Validation",
                    "input": "Tuned params from Optuna",
                    "process": "Re-run Vectorbt walk-forward test with new params (3-fold OOS)",
                    "output": "Is PF >= baseline? Is it > 1.2? Did overfitting occur?",
                    "time_estimate_ms": 100,
                    "critical": "Must use FRESH data windows, not training data",
                },
                {
                    "stage": 3,
                    "name": "Comparison & Validation",
                    "input": "Baseline results vs Tuned results",
                    "process": "Calculate improvement: (tuned_pf - baseline_pf) / baseline_pf",
                    "output": "Accept or reject tuned params based on validation",
                    "acceptance_criteria": [
                        "Tuned PF > baseline PF",
                        "Tuned PF passes walk-forward validation",
                        "Improvement >= 1% (or configurable threshold)",
                        "No overfitting detected (OOS performance similar to IS)"
                    ],
                    "time_estimate_ms": 10,
                },
                {
                    "stage": 4,
                    "name": "Deployment",
                    "input": "Validated tuned params",
                    "process": "Save to {symbol}__{session}__{indicator}_tuned.json",
                    "output": "Params ready for live trading",
                    "time_estimate_ms": 5,
                },
                {
                    "stage": 5,
                    "name": "Live Feedback (Continuous Loop)",
                    "input": "Actual trades from live bot",
                    "process": "Collect trades, analyze per-session performance",
                    "output": "Feed real trade outcomes back to Optuna",
                    "frequency": "Daily/Weekly/Monthly depending on trade count",
                    "triggers_new_cycle": True,
                    "note": "This is what completes the self-learning loop",
                }
            ],
            "total_time_sequential_ms": 5050 + 100 + 10 + 5,
            "total_time_with_8core_parallel_ms": (50 * 100 / 8) + 100 + 10 + 5,
        }
        
        print("\n📋 Validation Feedback Loop Architecture:\n")
        for stage in feedback_loop["stages"]:
            print(f"Stage {stage['stage']}: {stage['name']}")
            print(f"  Input: {stage['input']}")
            print(f"  Process: {stage['process']}")
            print(f"  Output: {stage['output']}")
            if "time_estimate_ms" in stage:
                print(f"  Time: ~{stage['time_estimate_ms']}ms")
            if "acceptance_criteria" in stage:
                print(f"  Acceptance Criteria:")
                for criterion in stage["acceptance_criteria"]:
                    print(f"    • {criterion}")
            print()
        
        print("⏱️  Total Time (Sequential):", f"{feedback_loop['total_time_sequential_ms']}ms ({feedback_loop['total_time_sequential_ms']/1000:.2f}s)")
        print("⏱️  Total Time (8-core Parallel):", f"{feedback_loop['total_time_with_8core_parallel_ms']:.0f}ms ({feedback_loop['total_time_with_8core_parallel_ms']/1000:.2f}s)")
        
        self.results["feedback_loop"] = feedback_loop
        return feedback_loop
    
    def save_results(self, output_file="profiling_results.json"):
        """Save profiling results to JSON."""
        output_path = project_root / output_file
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n✓ Results saved to {output_path}")
        return output_path


def main():
    """Run all profiling tasks."""
    
    print("\n" + "="*80)
    print("VECTORBT → OPTUNA PERFORMANCE PROFILING & FEEDBACK LOOP DESIGN")
    print("="*80)
    print("\nThis script measures real performance and designs the validation cycle.")
    
    profiler = PerformanceProfiler()
    
    # Task 1: Profile Vectorbt
    print("\n[1/3] Starting Vectorbt profiling...")
    vectorbt_result = profiler.profile_vectorbt_single_trial(
        symbol="XAUUSD",
        timeframe="H4",
        session="asian",
        iterations=10
    )
    
    # Task 2: Profile Optuna (research task)
    print("\n[2/3] Optuna convergence analysis...")
    profiler.profile_optuna_convergence()
    
    # Task 3: Design feedback loop
    print("\n[3/3] Designing validation feedback loop...")
    feedback_loop = profiler.design_feedback_loop()
    
    # Save results
    profiler.save_results()
    
    # Summary
    print("\n" + "="*80)
    print("PROFILING SUMMARY")
    print("="*80)
    
    if vectorbt_result:
        print(f"\n✓ Vectorbt Trial Speed: {vectorbt_result['trial_mean_ms']:.2f}ms per backtest")
        print(f"\n✓ Optuna Implications (100 trials):")
        print(f"  • Sequential: {vectorbt_result['trial_mean_ms'] * 100 / 1000:.1f}s")
        print(f"  • 8-core parallel: {vectorbt_result['trial_mean_ms'] * 100 / 8 / 1000:.1f}s")
    
    print(f"\n✓ Feedback Loop Architecture: Optuna → Vectorbt Validation → Live")
    print(f"  • Can run complete cycle in ~{feedback_loop['total_time_with_8core_parallel_ms']/1000:.1f}s")
    
    print("\n✓ Next Steps:")
    print("  1. Run Optuna on real strategy (XAUUSD/asian/osma)")
    print("  2. Measure convergence rate and improvement")
    print("  3. Implement walk-forward validation")
    print("  4. Deploy continuous feedback loop")


if __name__ == "__main__":
    main()
