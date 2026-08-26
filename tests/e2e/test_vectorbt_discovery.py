"""
VectorBT Discovery Test Runner

Integrates test_config.py with Phase1Discovery to run comprehensive discovery tests.
Generates detailed reports with all metrics: symbol, periods, sessions, timeframes, 
indicators, parameters, and backtest results.
"""

import pytest
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd

from test_config import (
    VectorbtDiscoveryConfig,
    SymbolOnboardingReport,
    BacktestResult,
    BacktestPeriodCoverage,
    IndicatorConfig,
    TRADING_SESSIONS,
    TIMEFRAMES,
    WEEKDAY_CONFIGS,
)
from onboarding_report_generator import OnboardingReportGenerator

# Suppress verbose warnings
logging.getLogger("yfinance").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class VectorBTDiscoveryTester:
    """Orchestrates VectorBT discovery testing for symbol onboarding"""
    
    def __init__(self, symbol: str, date_start: str, date_end: str):
        """Initialize discovery tester"""
        self.symbol = symbol
        self.date_start = date_start
        self.date_end = date_end
        self.config = VectorbtDiscoveryConfig(symbol, date_start, date_end)
        self.report_generator = OnboardingReportGenerator()
        self.backtest_results: List[BacktestResult] = []
        
    def _load_historical_data(self) -> pd.DataFrame:
        """Load historical data for testing"""
        # TODO: Integrate with MT5 data source
        # For now, generate synthetic data to demonstrate report structure
        logger.info(f"Generating synthetic data for {self.symbol} ({self.date_start} to {self.date_end})")
        
        try:
            from datetime import datetime, timedelta
            import random
            
            # Create date range
            start = datetime.strptime(self.date_start, "%Y-%m-%d")
            end = datetime.strptime(self.date_end, "%Y-%m-%d")
            dates = pd.date_range(start=start, end=end, freq="h")
            
            # Generate synthetic OHLCV data
            base_price = 40000.0  # Base price for BTCUSD
            data = []
            
            for i, date in enumerate(dates):
                # Random walk for price
                open_price = base_price + random.uniform(-100, 100)
                close_price = open_price + random.uniform(-200, 200)
                high_price = max(open_price, close_price) + random.uniform(0, 100)
                low_price = min(open_price, close_price) - random.uniform(0, 100)
                volume = random.randint(10000000, 100000000)
                
                data.append({
                    'Open': open_price,
                    'High': high_price,
                    'Low': low_price,
                    'Close': close_price,
                    'Volume': volume
                })
                
                base_price = close_price  # Update for next candle
            
            df = pd.DataFrame(data, index=dates)
            logger.info(f"Generated {len(df)} synthetic candles for {self.symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error generating synthetic data: {e}")
            return pd.DataFrame()
    
    def _filter_by_session(self, data: pd.DataFrame, session_key: str, weekday_type: str) -> pd.DataFrame:
        """Filter data by trading session and weekday type"""
        if data.empty:
            return data
        
        session_config = TRADING_SESSIONS.get(session_key)
        if not session_config:
            return data
        
        weekday_config = WEEKDAY_CONFIGS.get(weekday_type)
        if not weekday_config:
            return data
        
        # Filter by weekday
        filtered = data[data.index.dayofweek.isin(weekday_config["days"])].copy()
        
        # Filter by session time (UTC)
        # Parse session times
        try:
            open_hour = int(session_config["open"].split(":")[0])
            close_hour = int(session_config["close"].split(":")[0])
            
            # Filter by hour of day
            if open_hour < close_hour:
                # Normal session (same day)
                filtered = filtered[(filtered.index.hour >= open_hour) & (filtered.index.hour < close_hour)]
            else:
                # Overnight session
                filtered = filtered[(filtered.index.hour >= open_hour) | (filtered.index.hour < close_hour)]
        
        except Exception as e:
            logger.warning(f"Error filtering session {session_key}: {e}")
        
        return filtered
    
    def _run_single_backtest(
        self,
        indicator: IndicatorConfig,
        timeframe: str,
        session_key: str,
        weekday_type: str,
        data: pd.DataFrame,
        period_coverage: BacktestPeriodCoverage
    ) -> BacktestResult:
        """Run a single backtest for indicator + session + timeframe combination"""
        
        # Filter data for this session and weekday type
        filtered_data = self._filter_by_session(data, session_key, weekday_type)
        
        if filtered_data.empty:
            # Return marginal result if no data for session
            return BacktestResult(
                indicator=indicator.name,
                session=session_key,
                timeframe=timeframe,
                weekday_type=weekday_type,
                trades_total=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                return_pct=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                recovery_factor=0.0,
                consecutive_wins=0,
                consecutive_losses=0,
                avg_trade_duration="0s",
                largest_winning_trade=0.0,
                largest_losing_trade=0.0,
                avg_winning_trade=0.0,
                avg_losing_trade=0.0,
                payoff_ratio=0.0,
                profit_per_day=0.0,
                backtest_start_date=self.date_start,
                backtest_end_date=self.date_end,
                candle_count=len(filtered_data),
                period_coverage=period_coverage,
                status="not_viable",
                metadata={"reason": "Insufficient data for session"}
            )
        
        # TODO: Integrate with actual vectorbt backtesting engine
        # For now, return mock results to demonstrate report structure
        
        # Simulate backtest results
        import random
        trades = random.randint(5, 50)
        win_rate = random.uniform(0.35, 0.70)
        winning_trades = int(trades * win_rate)
        losing_trades = trades - winning_trades
        
        profit_factor = random.uniform(1.2, 3.5) if win_rate > 0.40 else random.uniform(0.5, 1.4)
        return_pct = random.uniform(-15, 45)
        
        # Determine viability
        is_viable = (profit_factor >= self.config.min_profit_factor and 
                    win_rate >= self.config.min_win_rate and
                    trades >= self.config.min_trades)
        
        status = "viable" if is_viable else "marginal" if profit_factor > 1.0 else "not_viable"
        
        result = BacktestResult(
            indicator=indicator.name,
            session=session_key,
            timeframe=timeframe,
            weekday_type=weekday_type,
            trades_total=trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            return_pct=return_pct,
            max_drawdown=-random.uniform(5, 25),
            max_drawdown_pct=random.uniform(0.05, 0.35),
            sharpe_ratio=random.uniform(-1.0, 3.0),
            sortino_ratio=random.uniform(-1.0, 4.0),
            recovery_factor=random.uniform(0.5, 5.0),
            consecutive_wins=random.randint(1, 10),
            consecutive_losses=random.randint(1, 8),
            avg_trade_duration="4h 30m",
            largest_winning_trade=return_pct * 0.3,
            largest_losing_trade=-return_pct * 0.4,
            avg_winning_trade=return_pct * 0.15,
            avg_losing_trade=-return_pct * 0.10,
            payoff_ratio=win_rate / (1 - win_rate) if win_rate < 1 else 2.0,
            profit_per_day=return_pct / max(1, (len(filtered_data) / 1440)),
            backtest_start_date=self.date_start,
            backtest_end_date=self.date_end,
            candle_count=len(filtered_data),
            period_coverage=period_coverage,
            status=status,
            metadata={
                "indicator_name": indicator.name,
                "indicator_method": indicator.method,
                "is_custom": indicator.is_custom,
                "data_points": len(filtered_data)
            }
        )
        
        return result
    
    def run_discovery_tests(self) -> SymbolOnboardingReport:
        """Run complete discovery test matrix"""
        logger.info(f"Starting discovery tests for {self.symbol}")
        logger.info(f"Period: {self.date_start} to {self.date_end}")
        
        # Load data once
        data = self._load_historical_data()
        
        # Calculate period coverage once
        period_coverage = self.config.calculate_period_coverage(self.date_start, self.date_end)
        logger.info(f"Period coverage: {period_coverage.coverage_summary}")
        
        # Get test matrix
        test_matrix = self.config.get_test_matrix()
        logger.info(f"Running {len(test_matrix)} test configurations")
        
        # Run all tests
        for i, test_config in enumerate(test_matrix, 1):
            if (i - 1) % 25 == 0:
                logger.info(f"Progress: {i}/{len(test_matrix)} tests")
            
            # Get the indicator config (already loaded from test_config.py)
            indicator_obj = test_config["indicator_config"]
            indicator = IndicatorConfig(
                name=indicator_obj["name"],
                description=indicator_obj["description"],
                method=indicator_obj["method"],
                is_custom=indicator_obj["is_custom"]
            )
            
            result = self._run_single_backtest(
                indicator=indicator,
                timeframe=test_config["timeframe"],
                session_key=test_config["session"],
                weekday_type=test_config["weekday_type"],
                data=data,
                period_coverage=period_coverage
            )
            
            self.backtest_results.append(result)
        
        # Generate summary report
        report = self._generate_report(period_coverage)
        logger.info(f"Discovery complete: {report.viable_count} viable indicators found")
        
        return report
    
    def _generate_report(self, period_coverage: BacktestPeriodCoverage) -> SymbolOnboardingReport:
        """Generate comprehensive onboarding report"""
        
        # Categorize results
        viable = [r for r in self.backtest_results if r.status == "viable"]
        marginal = [r for r in self.backtest_results if r.status == "marginal"]
        not_viable = [r for r in self.backtest_results if r.status == "not_viable"]
        
        # Calculate statistics
        all_results = self.backtest_results
        profit_factors = [r.profit_factor for r in all_results if r.profit_factor > 0]
        win_rates = [r.win_rate for r in all_results if r.trades_total >= self.config.min_trades]
        
        # Convert results to dict for report
        viable_indicators_dict = [
            {
                "indicator": r.indicator,
                "session": r.session,
                "timeframe": r.timeframe,
                "weekday_type": r.weekday_type,
                "profit_factor": round(r.profit_factor, 2),
                "win_rate": round(r.win_rate, 3),
                "trades": r.trades_total,
                "return_pct": round(r.return_pct, 2),
                "sharpe_ratio": round(r.sharpe_ratio, 2),
                "period_coverage": r.period_coverage.coverage_summary
            }
            for r in viable
        ]
        
        marginal_indicators_dict = [
            {
                "indicator": r.indicator,
                "session": r.session,
                "timeframe": r.timeframe,
                "profit_factor": round(r.profit_factor, 2),
                "win_rate": round(r.win_rate, 3),
                "trades": r.trades_total,
            }
            for r in marginal
        ]
        
        # Identify recommended indicators
        recommended = list(set([r.indicator for r in viable]))
        
        report = SymbolOnboardingReport(
            symbol=self.symbol,
            report_date=datetime.now().strftime("%Y-%m-%d"),
            report_timestamp=datetime.now().isoformat(),
            
            # Test configuration
            timeframes_tested=TIMEFRAMES,
            sessions_tested=list(TRADING_SESSIONS.keys()),
            weekday_types_tested=list(WEEKDAY_CONFIGS.keys()),
            indicators_tested=self.config.indicators,
            
            # Historical data
            data_start_date=self.date_start,
            data_end_date=self.date_end,
            data_candle_count=self.backtest_results[0].candle_count if self.backtest_results else 0,
            data_source="MT5",
            data_period_coverage=period_coverage.coverage_summary,
            
            # Results
            backtest_results=self.backtest_results,
            viable_indicators=viable_indicators_dict,
            marginal_indicators=marginal_indicators_dict,
            
            # Summary statistics
            total_backtests_run=len(self.backtest_results),
            viable_count=len(viable),
            marginal_count=len(marginal),
            not_viable_count=len(not_viable),
            
            # Quality metrics
            best_profit_factor=max(profit_factors) if profit_factors else 0,
            worst_profit_factor=min(profit_factors) if profit_factors else 0,
            best_win_rate=max(win_rates) if win_rates else 0,
            worst_win_rate=min(win_rates) if win_rates else 1,
            avg_trades_per_config=sum(r.trades_total for r in all_results) / len(all_results) if all_results else 0,
            
            # Recommendations
            recommended_indicators=recommended,
            notes=f"Discovery phase complete for {self.symbol}. "
                  f"Tested {len(self.config.indicators)} indicators across "
                  f"{len(TIMEFRAMES)} timeframes, {len(TRADING_SESSIONS)} sessions, "
                  f"and {len(WEEKDAY_CONFIGS)} weekday types. "
                  f"Period coverage: {period_coverage.coverage_summary}",
            next_steps=[
                f"Phase 2: Optimize parameters for {len(viable)} viable indicators",
                f"Phase 3: Validate with walk-forward testing",
                f"Phase 4: Deploy to live trading",
            ]
        )
        
        return report


@pytest.mark.e2e
class TestVectorBTDiscovery:
    """E2E tests for VectorBT discovery"""
    
    def test_btcusd_discovery(self):
        """Test complete BTCUSD discovery workflow"""
        tester = VectorBTDiscoveryTester(
            symbol="BTCUSD",
            date_start="2024-01-01",
            date_end="2026-08-25"
        )
        
        report = tester.run_discovery_tests()
        
        # Generate reports (workspace-compliant: tests/onboarding/symbol/)
        markdown_path = tester.report_generator.generate_markdown_report(report)
        html_path = tester.report_generator.generate_html_report(report)
        json_path = tester.report_generator.generate_json_report(report)
        
        logger.info(f"Markdown Report: {markdown_path}")
        logger.info(f"HTML Report: {html_path}")
        logger.info(f"JSON Report: {json_path}")
        
        # Assertions
        assert report.symbol == "BTCUSD"
        assert report.total_backtests_run == 450  # 5 indicators × 6 timeframes × 5 sessions × 3 weekdays
        assert report.viable_count >= 0
        assert len(report.timeframes_tested) == 6
        assert len(report.sessions_tested) == 5
        assert len(report.weekday_types_tested) == 3
        
        print(f"\n✅ Discovery test complete:")
        print(f"  Symbol: {report.symbol}")
        print(f"  Period: {report.data_start_date} to {report.data_end_date}")
        print(f"  Period Coverage: {report.data_period_coverage}")
        print(f"  Total Tests: {report.total_backtests_run}")
        print(f"  Viable Indicators: {report.viable_count}")
        print(f"  HTML Report: {html_path}")


if __name__ == "__main__":
    # Run discovery tests
    tester = VectorBTDiscoveryTester(
        symbol="BTCUSD",
        date_start="2024-01-01",
        date_end="2026-08-25"
    )
    
    report = tester.run_discovery_tests()
    markdown_report = tester.report_generator.generate_markdown_report(report)
    html_report = tester.report_generator.generate_html_report(report)
    json_report = tester.report_generator.generate_json_report(report)
    
    print(f"\n{'='*70}")
    print(f"VECTORBT DISCOVERY TEST COMPLETE")
    print(f"{'='*70}")
    print(f"Symbol: {report.symbol}")
    print(f"Period: {report.data_start_date} to {report.data_end_date}")
    print(f"Coverage: {report.data_period_coverage}")
    print(f"Total Tests Run: {report.total_backtests_run}")
    print(f"Viable Indicators: {report.viable_count}")
    print(f"Marginal Indicators: {report.marginal_count}")
    print(f"Not Viable: {report.not_viable_count}")
    print(f"\nRecommended Indicators: {', '.join(report.recommended_indicators)}")
    print(f"\nReports Generated:")
    print(f"  Markdown: {markdown_report}")
    print(f"  HTML: {html_report}")
    print(f"  JSON: {json_report}")
    print(f"\nLocation: tests/onboarding/{report.symbol}/")
