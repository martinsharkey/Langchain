"""
Phase 3: Vectorbt Validation - Validate tuned params on out-of-sample data

Takes tuned parameters from Phase 2 and backtests them on held-out test data
(last 40% of historical data that was never seen by Optuna).

This is the CRITICAL phase that catches overfitting before deployment.
"""

import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.strategies.indicators import (
    osma as osma_fn,
    bulls_power as bp_fn,
    bears_power as bpw_fn,
    atr as atr_fn,
    ema as ema_fn,
)
from src.utils.logger import get_logger

logger = get_logger("phase3_validation")


@dataclass
class ValidationResult:
    """Result of validating one tuned indicator on out-of-sample data."""
    symbol: str
    session: str
    indicator: str
    baseline_pf_test: float
    tuned_pf_test: float
    improvement_test: float
    baseline_params: Dict
    tuned_params: Dict
    train_vs_test_gap: float  # Indicator of overfitting
    accepted: bool
    rejection_reason: str = ""
    
    def to_dict(self):
        return asdict(self)


class Phase3Validator:
    """Phase 3: Validate tuned parameters on held-out test data."""
    
    # Acceptance criteria thresholds
    MIN_IMPROVEMENT = 0.01  # At least 1% improvement required
    OVERFITTING_THRESHOLD = 0.95  # If tuned_test < baseline_test * 0.95, it's overfitting
    MIN_PF = 1.2  # Minimum acceptable PF on test data
    MAX_TRAIN_TEST_GAP = 0.10  # More than 10% gap suggests overfitting
    
    def __init__(self):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
    
    def run(self, phase2_results: Dict) -> Dict[str, ValidationResult]:
        """
        Validate tuned params from Phase 2 on out-of-sample data.
        
        Input: Phase 2 Optuna results
        Output: Accept/reject decisions
        """
        symbol = phase2_results["symbol"]
        
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 3: VECTORBT VALIDATION - {symbol}")
        logger.info(f"{'='*80}")
        logger.info("Using held-out test data (last 40% of historical data)")
        logger.info("This data was NOT seen by Optuna during tuning\n")
        
        results = {}
        accepted_count = 0
        rejected_count = 0
        
        try:
            phase2_data = phase2_results.get("results", {})
            
            for session, phase2_result in phase2_data.items():
                logger.info(f"Validating {phase2_result['indicator']} for {session}:")
                logger.info(f"  Baseline PF (test): ?")
                logger.info(f"  Tuned PF (train): {phase2_result['tuned_pf_train']:.2f}")
                logger.info(f"  Tuned params: {phase2_result['tuned_params']}")
                
                try:
                    result = self._validate_indicator(
                        symbol=symbol,
                        session=session,
                        indicator=phase2_result["indicator"],
                        baseline_params=phase2_result["baseline_params"],
                        tuned_params=phase2_result["tuned_params"],
                        tuned_pf_train=phase2_result["tuned_pf_train"],
                    )
                    
                    if result:
                        results[session] = result
                        
                        if result.accepted:
                            logger.info(f"  ✅ ACCEPTED")
                            logger.info(f"     Baseline PF (test): {result.baseline_pf_test:.2f}")
                            logger.info(f"     Tuned PF (test): {result.tuned_pf_test:.2f}")
                            logger.info(f"     Improvement: +{result.improvement_test*100:.2f}%")
                            logger.info(f"     Train/test gap: {result.train_vs_test_gap*100:.1f}%")
                            accepted_count += 1
                        else:
                            logger.info(f"  ❌ REJECTED")
                            logger.info(f"     Reason: {result.rejection_reason}")
                            rejected_count += 1
                
                except Exception as e:
                    logger.error(f"Validation failed: {e}", exc_info=True)
            
            # Summary
            logger.info(f"\n{'='*80}")
            logger.info(f"VALIDATION COMPLETE - {symbol}")
            logger.info(f"{'='*80}")
            logger.info(f"Accepted: {accepted_count}")
            logger.info(f"Rejected: {rejected_count}")
            logger.info(f"Acceptance rate: {accepted_count/(accepted_count+rejected_count)*100:.1f}%")
            
            avg_improvement = np.mean([r.improvement_test for r in results.values() if r.accepted])
            if not np.isnan(avg_improvement):
                logger.info(f"Average improvement (accepted only): +{avg_improvement*100:.2f}%")
            
            return results
        
        except Exception as e:
            logger.error(f"Validation failed for {symbol}: {e}", exc_info=True)
            return results
    
    def _validate_indicator(
        self,
        symbol: str,
        session: str,
        indicator: str,
        baseline_params: Dict,
        tuned_params: Dict,
        tuned_pf_train: float,
    ) -> ValidationResult:
        """Validate one tuned indicator on test data."""
        
        # Determine timeframe from session (simplified)
        timeframe = "H4"  # Would be inferred from Phase 1 in real system
        
        # Load full data
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
            logger.warning(f"Insufficient session data")
            return None
        
        # Split: 60% train (not used), 40% test
        split_idx = int(len(ohlcv_session) * 0.6)
        test_data = ohlcv_session[split_idx:]
        
        # Calculate indicators
        indicators = self._calculate_indicators(test_data)
        
        # Backtest baseline on TEST data
        baseline_signals = self._generate_signals(test_data, indicators, indicator, baseline_params)
        baseline_pf_test, _, _ = self._backtest(test_data['close'].values, baseline_signals)
        
        # Backtest tuned on TEST data
        tuned_signals = self._generate_signals(test_data, indicators, indicator, tuned_params)
        tuned_pf_test, _, _ = self._backtest(test_data['close'].values, tuned_signals)
        
        # Calculate improvement
        improvement = (tuned_pf_test - baseline_pf_test) / baseline_pf_test if baseline_pf_test > 0 else 0
        
        # Calculate train/test gap (overfitting indicator)
        train_test_gap = (tuned_pf_train - tuned_pf_test) / tuned_pf_test if tuned_pf_test > 0 else 0
        
        # Acceptance criteria
        criteria = {
            "improvement": improvement >= self.MIN_IMPROVEMENT,
            "no_overfitting": tuned_pf_test >= baseline_pf_test * self.OVERFITTING_THRESHOLD,
            "minimum_pf": tuned_pf_test >= self.MIN_PF,
            "reasonable_gap": train_test_gap <= self.MAX_TRAIN_TEST_GAP,
        }
        
        accepted = all(criteria.values())
        rejection_reason = self._get_rejection_reason(criteria, tuned_pf_test, baseline_pf_test)
        
        return ValidationResult(
            symbol=symbol,
            session=session,
            indicator=indicator,
            baseline_pf_test=baseline_pf_test,
            tuned_pf_test=tuned_pf_test,
            improvement_test=improvement,
            baseline_params=baseline_params,
            tuned_params=tuned_params,
            train_vs_test_gap=train_test_gap,
            accepted=accepted,
            rejection_reason=rejection_reason,
        )
    
    def _get_rejection_reason(self, criteria: Dict, tuned_pf: float, baseline_pf: float) -> str:
        """Generate human-readable rejection reason."""
        reasons = []
        
        if not criteria["improvement"]:
            reasons.append(f"Insufficient improvement ({(tuned_pf-baseline_pf)/baseline_pf*100:.1f}% < 1%)")
        
        if not criteria["no_overfitting"]:
            drop = (1 - tuned_pf/baseline_pf) * 100
            reasons.append(f"Overfitting detected (PF dropped {drop:.1f}%)")
        
        if not criteria["minimum_pf"]:
            reasons.append(f"Below minimum PF threshold ({tuned_pf:.2f} < {self.MIN_PF})")
        
        if not criteria["reasonable_gap"]:
            reasons.append(f"Large train/test gap (indicates overfitting)")
        
        return "; ".join(reasons)
    
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
    
    def _calculate_indicators(self, ohlcv: pd.DataFrame) -> Dict:
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
    ) -> pd.Series:
        """Generate signals with specific parameters."""
        
        close = indicators.get("close")
        if close is None:
            return pd.Series(0, index=ohlcv.index)
        
        if indicator_name == "osma":
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
        
        return pd.Series(0, index=ohlcv.index)
    
    def _backtest(
        self,
        close: np.ndarray,
        signals: pd.Series,
    ) -> Tuple[float, float, int]:
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
    
    def save_results(self, symbol: str, results: Dict[str, ValidationResult]) -> Path:
        """Save validation results to JSON."""
        output_dir = Path("data/qmmp") / symbol
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": {session: result.to_dict() for session, result in results.items()},
        }
        
        output_file = output_dir / f"phase3_validation_{symbol}.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to {output_file}")
        return output_file


def main():
    """Run Phase 3 on Phase 2 tuning results."""
    
    symbols = ["XAUUSD", "BTCUSD"]
    
    for symbol in symbols:
        # Load Phase 2 results
        phase2_file = Path("data/qmmp") / symbol / f"phase2_optuna_{symbol}.json"
        if not phase2_file.exists():
            logger.error(f"Phase 2 results not found: {phase2_file}")
            continue
        
        with open(phase2_file) as f:
            phase2_results = json.load(f)
        
        # Run Phase 3
        validator = Phase3Validator()
        phase3_results = validator.run(phase2_results)
        validator.save_results(symbol, phase3_results)


if __name__ == "__main__":
    main()
