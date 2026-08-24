"""
Phase 1: Vectorbt Discovery - Find best indicators per symbol/session/timeframe

Tests all indicator combinations across all sessions and timeframes.
Outputs baseline indicators and parameters for Phase 2 (Optuna tuning).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.strategies.indicators import (
    osma as osma_fn,
    bulls_power as bp_fn,
    bears_power as bpw_fn,
    atr as atr_fn,
    ema as ema_fn,
)
from src.strategies.sessions import session_of
from src.utils.logger import get_logger

logger = get_logger("phase1_discovery")


@dataclass
class DiscoveryResult:
    """Result of testing one indicator on one session/timeframe."""
    symbol: str
    session: str
    timeframe: str
    indicator_name: str
    profit_factor: float
    win_rate: float
    trades: int
    baseline_params: Dict
    
    def to_dict(self):
        return asdict(self)


class VectorbtDiscovery:
    """Phase 1: Discover best indicators per symbol/session/timeframe."""
    
    # Constants
    INDICATORS = ["osma", "bulls_bears", "atr", "ema"]  # Indicator families to test
    MIN_PF = 1.2  # Minimum acceptable profit factor
    MIN_TRADES = 20  # Minimum trades for statistical significance
    
    # Default parameters per indicator
    DEFAULT_PARAMS = {
        "osma": {"fast": 12, "slow": 26, "signal": 9},
        "bulls_bears": {"period": 13},
        "atr": {"period": 14},
        "ema": {"period": 13},
    }
    
    def __init__(self, symbols: List[str] = None, sessions: List[str] = None, 
                 timeframes: List[str] = None):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.symbols = symbols or ["XAUUSD", "BTCUSD"]
        self.sessions = sessions or ["Asian", "London", "NewYork"]
        self.timeframes = timeframes or ["M1", "M5", "M15", "H1", "H4"]
        
        # Results storage
        self.discovery_results: Dict[str, DiscoveryResult] = {}
        self.best_by_session: Dict[str, Dict] = {}
    
    def run(self, symbol: str) -> Dict:
        """
        Run discovery for one symbol across all sessions/timeframes.
        
        Returns:
            {
                "symbol": "XAUUSD",
                "all_results": [...],
                "best_by_session": {
                    "Asian": {"timeframe": "H4", "indicator": "osma", "pf": 10.24, ...},
                    ...
                }
            }
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 1: VECTORBT DISCOVERY - {symbol}")
        logger.info(f"{'='*80}")
        
        all_results = []
        self.best_by_session[symbol] = {}
        
        try:
            # For each session
            for session in self.sessions:
                best_result = None
                best_pf = 0
                
                logger.info(f"\n{session} session:")
                
                # For each timeframe
                for timeframe in self.timeframes:
                    logger.info(f"  {timeframe}:", end=" ")
                    
                    # Test all indicators
                    session_results = []
                    
                    for indicator_name in self.INDICATORS:
                        try:
                            result = self._test_indicator(
                                symbol, session, timeframe, indicator_name
                            )
                            
                            if result is not None:
                                session_results.append(result)
                                all_results.append(result)
                                
                                # Track best for this session×timeframe
                                if result.profit_factor > best_pf:
                                    best_pf = result.profit_factor
                                    best_result = result
                        
                        except Exception as e:
                            logger.warning(f"Failed to test {indicator_name}: {e}")
                    
                    # Log results for this timeframe
                    if session_results:
                        best_tf = max(session_results, key=lambda r: r.profit_factor)
                        logger.info(f"✓ {best_tf.indicator_name} PF={best_tf.profit_factor:.2f} n={best_tf.trades}")
                    else:
                        logger.info("✗ No viable indicators found")
                
                # Record best for this session
                if best_result:
                    self.best_by_session[symbol][session] = {
                        "timeframe": best_result.timeframe,
                        "indicator": best_result.indicator_name,
                        "profit_factor": best_result.profit_factor,
                        "win_rate": best_result.win_rate,
                        "trades": best_result.trades,
                        "baseline_params": best_result.baseline_params,
                    }
                    logger.info(f"  → Best for {session}: {best_result.indicator_name} on {best_result.timeframe} (PF={best_result.profit_factor:.2f})")
            
            # Summary
            logger.info(f"\n{'='*80}")
            logger.info(f"DISCOVERY COMPLETE - {symbol}")
            logger.info(f"{'='*80}")
            logger.info(f"Total combos tested: {len(all_results)}")
            logger.info(f"Best indicators by session:")
            for session, result in self.best_by_session[symbol].items():
                logger.info(f"  {session}: {result['indicator']} on {result['timeframe']} (PF={result['profit_factor']:.2f})")
            
            return {
                "symbol": symbol,
                "all_results": [r.to_dict() for r in all_results],
                "best_by_session": self.best_by_session[symbol],
            }
        
        except Exception as e:
            logger.error(f"Discovery failed for {symbol}: {e}", exc_info=True)
            return {
                "symbol": symbol,
                "error": str(e),
                "all_results": [r.to_dict() for r in all_results],
                "best_by_session": self.best_by_session[symbol],
            }
    
    def _test_indicator(
        self,
        symbol: str,
        session: str,
        timeframe: str,
        indicator_name: str,
    ) -> Optional[DiscoveryResult]:
        """
        Test one indicator on one symbol/session/timeframe combo.
        
        Returns DiscoveryResult if PF >= MIN_PF, else None.
        """
        try:
            # Load data
            bars = self.dm.get_rates(symbol, timeframe, count=12000)
            if not bars or len(bars) < 1000:
                return None
            
            df = pd.DataFrame(bars)
            ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
            ohlcv.index = pd.to_datetime(df['time'], unit='s')
            
            # Session filter
            ohlcv_session = self._filter_by_session(ohlcv, session)
            if len(ohlcv_session) < 100:
                return None
            
            # Calculate indicators
            indicators = self._calculate_indicators(ohlcv_session)
            
            # Generate signals
            close = ohlcv_session['close'].values
            signals = self._generate_signals(ohlcv_session, indicators, indicator_name)
            
            if signals is None:
                return None
            
            # Backtest
            pf, wr, trades = self._backtest(close, signals)
            
            # Check minimum thresholds
            if pf >= self.MIN_PF and trades >= self.MIN_TRADES:
                return DiscoveryResult(
                    symbol=symbol,
                    session=session,
                    timeframe=timeframe,
                    indicator_name=indicator_name,
                    profit_factor=pf,
                    win_rate=wr,
                    trades=trades,
                    baseline_params=self.DEFAULT_PARAMS.get(indicator_name, {}),
                )
            
            return None
        
        except Exception as e:
            logger.debug(f"Error testing {indicator_name} on {symbol}/{session}/{timeframe}: {e}")
            return None
    
    def _filter_by_session(self, ohlcv: pd.DataFrame, session_name: str) -> pd.DataFrame:
        """Filter OHLCV by session (Asian, London, NewYork)."""
        try:
            # Session mapping: hour ranges (GMT)
            session_hours = {
                "Asian": range(0, 8),      # 00:00 - 07:59 GMT
                "London": range(8, 16),    # 08:00 - 15:59 GMT
                "NewYork": range(13, 21),  # 13:00 - 20:59 GMT
            }
            
            if session_name not in session_hours:
                return ohlcv
            
            hours = session_hours[session_name]
            mask = ohlcv.index.hour.isin(hours)
            return ohlcv[mask]
        
        except Exception as e:
            logger.warning(f"Session filter error for {session_name}: {e}")
            return ohlcv
    
    def _calculate_indicators(self, ohlcv: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate all indicators."""
        try:
            close = pd.Series(ohlcv['close'].values)
            high = pd.Series(ohlcv['high'].values)
            low = pd.Series(ohlcv['low'].values)
            
            return {
                "close": close,
                "osma": osma_fn(close, 12, 26, 9),
                "bulls": bp_fn(ohlcv, 13),
                "bears": bpw_fn(ohlcv, 13),
                "atr": atr_fn(ohlcv, 14),
                "ema": ema_fn(close, 13),
            }
        except Exception as e:
            logger.warning(f"Indicator calculation error: {e}")
            return {}
    
    def _generate_signals(
        self,
        ohlcv: pd.DataFrame,
        indicators: Dict[str, pd.Series],
        indicator_name: str,
    ) -> Optional[pd.Series]:
        """Generate entry signals based on indicator."""
        try:
            close = indicators.get("close")
            if close is None:
                return None
            
            if indicator_name == "osma":
                osma = indicators.get("osma")
                if osma is None:
                    return None
                # Entry: osma crosses zero (simple threshold)
                return (osma > osma.std() * 0.5).astype(int)
            
            elif indicator_name == "bulls_bears":
                bulls = indicators.get("bulls")
                bears = indicators.get("bears")
                if bulls is None or bears is None:
                    return None
                # Entry: bulls > bears (bullish confluence)
                return (bulls > bears).astype(int)
            
            elif indicator_name == "atr":
                atr = indicators.get("atr")
                if atr is None:
                    return None
                # Entry: price > atr (momentum)
                return (close > close.rolling(20).mean() + atr).astype(int)
            
            elif indicator_name == "ema":
                ema = indicators.get("ema")
                if ema is None:
                    return None
                # Entry: price > ema (uptrend)
                return (close > ema).astype(int)
            
            return None
        
        except Exception as e:
            logger.debug(f"Signal generation error for {indicator_name}: {e}")
            return None
    
    def _backtest(
        self,
        close: np.ndarray,
        signals: pd.Series,
    ) -> Tuple[float, float, int]:
        """
        Simple backtest: calculate profit factor, win rate, trade count.
        
        Returns:
            (profit_factor, win_rate, trade_count)
        """
        try:
            signals = signals.fillna(0).values.astype(int)
            
            # Entry and exit
            entries = np.where(np.diff(signals) == 1)[0]
            exits = np.where(np.diff(signals) == -1)[0]
            
            if len(entries) == 0 or len(exits) == 0:
                return 0.0, 0.0, 0
            
            # Align entries/exits
            if exits[0] < entries[0]:
                exits = exits[1:]
            if len(entries) > len(exits):
                entries = entries[:-1]
            
            # Calculate P&L
            entry_prices = close[entries]
            exit_prices = close[exits]
            pnls = exit_prices - entry_prices
            
            # Profit factor
            wins = np.sum(pnls[pnls > 0])
            losses = np.abs(np.sum(pnls[pnls < 0]))
            pf = wins / losses if losses > 0 else (wins / 0.001 if wins > 0 else 0.0)
            
            # Win rate
            win_rate = np.sum(pnls > 0) / len(pnls) if len(pnls) > 0 else 0.0
            
            trade_count = len(pnls)
            
            return float(pf), float(win_rate), int(trade_count)
        
        except Exception as e:
            logger.debug(f"Backtest error: {e}")
            return 0.0, 0.0, 0
    
    def save_results(self, symbol: str, output_dir: str = None) -> Path:
        """Save discovery results to JSON."""
        if output_dir is None:
            output_dir = Path("data/qmmp") / symbol
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timeframes_tested": self.timeframes,
            "sessions_tested": self.sessions,
            "all_results": [r.to_dict() for r in self.discovery_results.values()],
            "best_by_session": self.best_by_session.get(symbol, {}),
        }
        
        output_file = output_dir / f"phase1_discovery_{symbol}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to {output_file}")
        return output_file


def main():
    """Run Phase 1 discovery on test symbols."""
    
    # Test on XAUUSD and BTCUSD
    symbols = ["XAUUSD", "BTCUSD"]
    sessions = ["Asian", "London", "NewYork"]
    timeframes = ["M1", "M5", "M15", "H1", "H4"]
    
    discovery = VectorbtDiscovery(symbols=symbols, sessions=sessions, timeframes=timeframes)
    
    all_results = {}
    for symbol in symbols:
        results = discovery.run(symbol)
        all_results[symbol] = results
        discovery.save_results(symbol)
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("PHASE 1 COMPLETE - ALL SYMBOLS")
    logger.info(f"{'='*80}")
    for symbol, results in all_results.items():
        if "error" not in results:
            logger.info(f"\n{symbol}:")
            for session, best in results["best_by_session"].items():
                logger.info(f"  {session}: {best['indicator']} on {best['timeframe']} (PF={best['profit_factor']:.2f})")
    
    return all_results


if __name__ == "__main__":
    main()
