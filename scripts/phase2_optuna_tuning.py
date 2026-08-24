"""
Phase 2: Optuna Tuning - Optimize discovered indicators

Takes best indicators from Phase 1 and uses Optuna to find better parameters.
Runs on training data (first 60%) to find optimal settings.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import optuna
import pandas as pd
from optuna.samplers import TPESampler
from dataclasses import dataclass, asdict

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.strategies.indicators import (
    osma as osma_fn,
    bulls_power as bp_fn,
    bears_power as bpw_fn,
    atr as atr_fn,
    ema as ema_fn,
)
from src.utils.logger import get_logger

logger = get_logger("phase2_optuna")


@dataclass
class OptunaResult:
    """Result of Optuna tuning for one indicator."""
    symbol: str
    session: str
    indicator: str
    baseline_pf: float
    tuned_pf_train: float
    improvement_train: float
    baseline_params: Dict
    tuned_params: Dict
    n_trials: int
    
    def to_dict(self):
        return asdict(self)


class Phase2Tuner:
    """Phase 2: Optuna optimization of discovered indicators."""
    
    # Parameter search spaces per indicator
    PARAM_SPACES = {
        "osma": {
            "fast": (5, 34, "int"),
            "slow": (20, 144, "int"),
            "signal": (5, 55, "int"),
        },
        "bulls_bears": {
            "period": (5, 34, "int"),
        },
        "atr": {
            "period": (5, 34, "int"),
        },
        "ema": {
            "period": (5, 144, "int"),
        },
    }
    
    def __init__(self, n_trials: int = 100):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.n_trials = n_trials
    
    def run(self, discovery_result: Dict) -> Dict[str, OptunaResult]:
        """
        Run Optuna tuning on all discovered indicators from Phase 1.
        
        Input: Phase 1 discovery results
        Output: Tuned parameters per session
        """
        symbol = discovery_result["symbol"]
        best_by_session = discovery_result.get("best_by_session", {})
        
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 2: OPTUNA TUNING - {symbol}")
        logger.info(f"{'='*80}")
        
        results = {}
        
        try:
            for session, session_info in best_by_session.items():
                indicator = session_info["indicator"]
                timeframe = session_info["timeframe"]
                baseline_pf = session_info["profit_factor"]
                baseline_params = session_info["baseline_params"]
                
                logger.info(f"\nTuning {indicator} for {session} ({timeframe}):")
                logger.info(f"  Baseline PF: {baseline_pf:.2f}")
                logger.info(f"  Baseline params: {baseline_params}")
                
                try:
                    result = self._tune_indicator(
                        symbol=symbol,
                        session=session,
                        timeframe=timeframe,
                        indicator=indicator,
                        baseline_params=baseline_params,
                        baseline_pf=baseline_pf,
                    )
                    
                    if result:
                        results[session] = result
                        logger.info(f"  ✓ Tuned PF: {result.tuned_pf_train:.2f} (+{result.improvement_train*100:.2f}%)")
                        logger.info(f"  ✓ Tuned params: {result.tuned_params}")
                
                except Exception as e:
                    logger.error(f"Failed to tune {indicator}: {e}", exc_info=True)
            
            # Summary
            logger.info(f"\n{'='*80}")
            logger.info(f"OPTUNA TUNING COMPLETE - {symbol}")
            logger.info(f"{'='*80}")
            logger.info(f"Sessions tuned: {len(results)}")
            total_improvement = sum(r.improvement_train for r in results.values())
            avg_improvement = total_improvement / len(results) if results else 0
            logger.info(f"Average improvement: +{avg_improvement*100:.2f}%")
            
            return results
        
        except Exception as e:
            logger.error(f"Tuning failed for {symbol}: {e}", exc_info=True)
            return results
    
    def _tune_indicator(
        self,
        symbol: str,
        session: str,
        timeframe: str,
        indicator: str,
        baseline_params: Dict,
        baseline_pf: float,
    ) -> Optional[OptunaResult]:
        """Tune one indicator using Optuna."""
        
        # Load training data (first 60%)
        bars = self.dm.get_rates(symbol, timeframe, count=12000)
        if not bars or len(bars) < 1000:
            logger.warning(f"Insufficient data for {symbol}/{timeframe}")
            return None
        
        df = pd.DataFrame(bars)
        ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
        ohlcv.index = pd.to_datetime(df['time'], unit='s')
        
        # Session filter
        ohlcv_session = self._filter_by_session(ohlcv, session)
        if len(ohlcv_session) < 100:
            logger.warning(f"Insufficient session data for {symbol}/{session}/{timeframe}")
            return None
        
        # Split: 60% train, 40% test (test not used in this phase)
        split_idx = int(len(ohlcv_session) * 0.6)
        train_data = ohlcv_session[:split_idx]
        
        # Calculate baseline indicators once
        indicators = self._calculate_indicators(train_data)
        
        # Get parameter search space
        param_space = self.PARAM_SPACES.get(indicator, {})
        if not param_space:
            logger.warning(f"No parameter space defined for {indicator}")
            return None
        
        # Define Optuna objective
        def objective(trial):
            try:
                # Suggest parameters
                suggested_params = {}
                for param_name, (lo, hi, ptype) in param_space.items():
                    if ptype == "int":
                        suggested_params[param_name] = trial.suggest_int(param_name, lo, hi)
                    else:
                        suggested_params[param_name] = trial.suggest_float(param_name, lo, hi)
                
                # Generate signals with suggested params
                signals = self._generate_signals(train_data, indicators, indicator, suggested_params)
                if signals is None:
                    return 0.0
                
                # Backtest
                pf, wr, trades = self._backtest(train_data['close'].values, signals)
                
                # Objective: maximize PF
                return pf
            
            except Exception as e:
                logger.debug(f"Trial failed: {e}")
                return 0.0
        
        # Create or load Optuna study
        optuna_dir = Path("data/qmmp") / symbol / "optuna"
        optuna_dir.mkdir(parents=True, exist_ok=True)
        
        study_name = f"tune_{symbol}_{session}_{indicator}"
        storage = f"sqlite:///{optuna_dir / 'study.db'}"
        
        sampler = TPESampler(seed=42)
        study = optuna.create_study(
            study_name=study_name,
            storage=storage,
            sampler=sampler,
            direction="maximize",
            load_if_exists=True,
        )
        
        # Run optimization
        logger.info(f"  Running {self.n_trials} Optuna trials...")
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)
        
        # Get best params
        best_params = study.best_params
        best_pf_train = study.best_value
        
        improvement = (best_pf_train - baseline_pf) / baseline_pf if baseline_pf > 0 else 0
        
        return OptunaResult(
            symbol=symbol,
            session=session,
            indicator=indicator,
            baseline_pf=baseline_pf,
            tuned_pf_train=best_pf_train,
            improvement_train=improvement,
            baseline_params=baseline_params,
            tuned_params=best_params,
            n_trials=self.n_trials,
        )
    
    def _filter_by_session(self, ohlcv: pd.DataFrame, session_name: str) -> pd.DataFrame:
        """Filter OHLCV by session."""
        session_hours = {
            "Asian": range(0, 8),
            "London": range(8, 16),
            "NewYork": range(13, 21),
        }
        
        if session_name not in session_hours:
            return ohlcv
        
        hours = session_hours[session_name]
        mask = ohlcv.index.hour.isin(hours)
        return ohlcv[mask]
    
    def _calculate_indicators(self, ohlcv: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate all indicators."""
        close = pd.Series(ohlcv['close'].values)
        
        return {
            "close": close,
            "osma": osma_fn(close, 12, 26, 9),
            "bulls": bp_fn(ohlcv, 13),
            "bears": bpw_fn(ohlcv, 13),
            "atr": atr_fn(ohlcv, 14),
            "ema": ema_fn(close, 13),
        }
    
    def _generate_signals(
        self,
        ohlcv: pd.DataFrame,
        indicators: Dict,
        indicator_name: str,
        params: Dict,
    ) -> Optional[pd.Series]:
        """Generate signals with specific parameters."""
        
        try:
            close = indicators.get("close")
            if close is None:
                return None
            
            if indicator_name == "osma":
                # Recalculate osma with suggested params
                osma = osma_fn(close, params.get("fast", 12), params.get("slow", 26), params.get("signal", 9))
                return (osma > osma.std() * 0.5).astype(int)
            
            elif indicator_name == "bulls_bears":
                period = params.get("period", 13)
                bulls = bp_fn(ohlcv, period)
                bears = bpw_fn(ohlcv, period)
                return (bulls > bears).astype(int)
            
            elif indicator_name == "atr":
                period = params.get("period", 14)
                atr = atr_fn(ohlcv, period)
                return (close > close.rolling(20).mean() + atr).astype(int)
            
            elif indicator_name == "ema":
                period = params.get("period", 13)
                ema = ema_fn(close, period)
                return (close > ema).astype(int)
            
            return None
        
        except Exception as e:
            logger.debug(f"Signal generation error: {e}")
            return None
    
    def _backtest(
        self,
        close: np.ndarray,
        signals: pd.Series,
    ) -> tuple:
        """Backtest and return (pf, wr, trades)."""
        
        try:
            signals = signals.fillna(0).values.astype(int)
            
            entries = np.where(np.diff(signals) == 1)[0]
            exits = np.where(np.diff(signals) == -1)[0]
            
            if len(entries) == 0 or len(exits) == 0:
                return 0.0, 0.0, 0
            
            if exits[0] < entries[0]:
                exits = exits[1:]
            if len(entries) > len(exits):
                entries = entries[:-1]
            
            entry_prices = close[entries]
            exit_prices = close[exits]
            pnls = exit_prices - entry_prices
            
            wins = np.sum(pnls[pnls > 0])
            losses = np.abs(np.sum(pnls[pnls < 0]))
            pf = wins / losses if losses > 0 else 0.0
            
            wr = np.sum(pnls > 0) / len(pnls) if len(pnls) > 0 else 0.0
            
            return float(pf), float(wr), len(pnls)
        
        except Exception as e:
            logger.debug(f"Backtest error: {e}")
            return 0.0, 0.0, 0
    
    def save_results(self, symbol: str, results: Dict[str, OptunaResult], 
                     output_dir: str = None) -> Path:
        """Save tuning results to JSON."""
        if output_dir is None:
            output_dir = Path("data/qmmp") / symbol
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": {session: result.to_dict() for session, result in results.items()},
        }
        
        output_file = output_dir / f"phase2_optuna_{symbol}.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to {output_file}")
        return output_file


def main():
    """Run Phase 2 on Phase 1 discovery results."""
    
    symbols = ["XAUUSD", "BTCUSD"]
    
    for symbol in symbols:
        # Load Phase 1 results
        phase1_file = Path("data/qmmp") / symbol / f"phase1_discovery_{symbol}.json"
        if not phase1_file.exists():
            logger.error(f"Phase 1 results not found: {phase1_file}")
            continue
        
        with open(phase1_file) as f:
            phase1_results = json.load(f)
        
        # Run Phase 2
        tuner = Phase2Tuner(n_trials=100)
        phase2_results = tuner.run(phase1_results)
        tuner.save_results(symbol, phase2_results)


if __name__ == "__main__":
    main()
