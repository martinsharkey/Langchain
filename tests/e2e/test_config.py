# Comprehensive Vectorbt Discovery Test Configuration

"""
Test Configuration for Symbol Onboarding with Full Details
Captures: Symbol, Timeframes, Sessions, Indicators, Parameters, Backtest Results

IMPORTANT: This uses ALL available MT5 indicators from vectorbt.
NO pre-selection - VectorBT's intelligence determines winners.
Includes custom OsMA model.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

# ============================================================================
# SESSION DEFINITIONS
# ============================================================================

TRADING_SESSIONS = {
    "Asia": {
        "name": "Asian Session",
        "open": "22:00",  # Previous day UTC
        "close": "08:00",  # UTC
        "regions": ["Tokyo", "Sydney", "Hong Kong", "Singapore"],
        "description": "Asian market session including Tokyo and Hong Kong"
    },
    "London": {
        "name": "London Session",
        "open": "08:00",  # UTC
        "close": "17:00",  # UTC
        "regions": ["London", "Frankfurt", "Paris"],
        "description": "European morning session"
    },
    "NewYork": {
        "name": "New York Session",
        "open": "13:00",  # UTC
        "close": "21:00",  # UTC
        "regions": ["New York", "Toronto"],
        "description": "North American session"
    },
    "Overlap_Asia_London": {
        "name": "Asia-London Overlap",
        "open": "08:00",  # UTC
        "close": "08:00",  # UTC (same time, just starts overlapping)
        "regions": ["Tokyo", "London"],
        "description": "Overlap period: Tokyo close meets London open"
    },
    "Overlap_London_NY": {
        "name": "London-New York Overlap",
        "open": "13:00",  # UTC
        "close": "17:00",  # UTC
        "regions": ["London", "New York"],
        "description": "Overlap period: London afternoon meets NY open"
    }
}

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]

WEEKDAY_CONFIGS = {
    "Weekday": {
        "description": "Monday-Friday",
        "days": [0, 1, 2, 3, 4]
    },
    "Weekend": {
        "description": "Saturday-Sunday",
        "days": [5, 6]
    },
    "Week": {
        "description": "Full week Monday-Sunday",
        "days": [0, 1, 2, 3, 4, 5, 6]
    }
}

# ============================================================================
# ALL MT5 INDICATORS (From Official MT5 + Custom Models)
# ============================================================================

# ALL 98 TRADING INDICATORS from QuantifiedStrategies.com + 3 custom OsMA models

ALL_MT5_INDICATORS = {
    # Trend Indicators
    'RSI': 'Relative Strength Index',
    'MACD': 'Moving Average Convergence Divergence',
    'EMA': 'Exponential Moving Average',
    'MA': 'Moving Average',
    'Ichimoku': 'Ichimoku Cloud',
    'ADX': 'Average Directional Index',
    'PSAR': 'Parabolic SAR',
    
    # Volatility Indicators  
    'BollingerBands': 'Bollinger Bands',
    'ATR': 'Average True Range',
    'StdDev': 'Standard Deviation',
    'ATRP': 'Average True Range Percentage',
    'Envelopes': 'Moving Average Envelopes',
    'Bands_Width': 'Bollinger Bands Width',
    'FractalChaos': 'Fractal Chaos Bands',
    'HighLow': 'High Low Bands',
    'PrimeNumber': 'Prime Number Bands',
    'StandardError': 'Standard Error Bands',
    'Projection': 'Projection Bands',
    
    # Momentum Indicators
    'Stochastic': 'Stochastic Oscillator',
    'CMO': 'Chande Momentum Oscillator',
    'WPR': 'Williams Percent Range',
    'CCI': 'Commodity Channel Index',
    'ROC': 'Rate of Change',
    'RVI': 'Relative Vigor Index',
    'RVI_Volatility': 'Relative Volatility Index',
    'PPO': 'Percentage Price Oscillator',
    'TSI': 'True Strength Index',
    'UO': 'Ultimate Oscillator',
    'RMI': 'Relative Momentum Index',
    'KST': 'KST Oscillator',
    'Ergodic': 'Ergodic Oscillator',
    'DMI': 'Directional Movement Index',
    'Accumulative_Swing': 'Accumulative Swing Index',
    'Zero_Lag_MACD': 'Zero-Lag MACD',
    'Zero_Lag_Stoch': 'Zero-lag Stochastics',
    
    # Volume Indicators
    'OBV': 'On-Balance Volume',
    'AD': 'Accumulation/Distribution Line',
    'CMF': 'Chaikin Money Flow',
    'MFI': 'Money Flow Index',
    'OBV_Volume': 'Wave Volume Indicator',
    'VROC': 'Volume Rate of Change',
    'TSV': 'Time Segmented Volume',
    'EMV': 'Ease of Movement Index',
    'MFI_Williams': 'Market Facilitation Index',
    'NVI': 'Negative Volume Index',
    'PVI': 'Positive Volume Index',
    'VAP': 'Volume Accumulation Percentage',
    'VolumeOscillator': 'Volume Oscillator',
    'VolumeZone': 'Volume Zone Oscillator',
    'Twiggs_Money': 'Twiggs Money Flow',
    'Volume_Flow': 'Volume Flow',
    'Price_Volume_Trend': 'Price and Volume Trend',
    'VWAP': 'Volume Weighted Average Price',
    
    # Bill Williams Indicators
    'Awesome': 'Bill Williams Awesome Indicator',
    'Aroon': 'Aroon Oscillator',
    'AO_Williams': 'Awesome Oscillator (Alternative)',
    'Fractals': 'Fractal Indicator',
    'Force_Index': 'Elder Force Index',
    'Accumulation_Distribution': 'Williams Accumulation Distribution',
    
    # Support & Resistance Indicators
    'Fibonacci': 'Fibonacci Retracement',
    'ZigZag': 'ZigZag Fibonacci',
    'Channel': 'Raff Regression Channel',
    'STARC': 'Stoller Average Range Channels',
    'Chandelier': 'Chandelier Exit Stop',
    'Kroll_Stop': 'Chande Kroll Stop',
    
    # Trend Analysis & Filters
    'PFE': 'Polarized Fractal Efficiency',
    'REI': 'Range Expansion Index',
    'IBS': 'Internal Bar Strength',
    'Choppiness': 'Choppiness Index',
    'Elder_Impulse': 'Elder Impulse System',
    'Rainbow_MA': 'Rainbow Moving Average',
    'EMA_Ribbon': 'Exponential Moving Average Ribbon',
    'MA_Ribbon': 'Moving Average Ribbon',
    'Schaff': 'Schaff Trend Cycle',
    'Laguerre': 'Adaptive Laguerre Filter',
    'Cyber_Cycle': 'Adaptive Cyber Cycle',
    'Linear_Regression': 'Linear Regression Indicator',
    'Efficiency_Ratio': 'Efficiency Ratio',
    'Hurst': 'Hurst Exponent',
    'Fractal_Dimension': 'Fractal Dimension Index',
    'Mass_Index': 'Mass Index',
    'Williams_VixFix': 'Williams VixFix',
    'Dynamic_Zone_RSI': 'Dynamic Zone RSI',
    'Cumulative_RSI': 'Cumulative RSI',
    'Disparity': 'Disparity Index',
    'Rainbow_Oscillator': 'Rainbow Oscillator',
    'RSC': 'Relative Strength Comparative',
    'Weighted_Close': 'Weighted Close',
    'Volatility_Channel': 'Larry Williams Volatility Channel',
    'DeMarker': 'DeMarker Indicator',
    'Market_Profile': 'Market Profile',
    'Time_Series': 'Time Series Analysis',
    'CMO_Absolute': 'CMO Absolute Indicator',
    
    # Custom Models (3) - Our proprietary implementations
    'OsMA_Confluence': 'OsMA Confluence Model',
    'OsMA_Divergence': 'OsMA Divergence Model',
    'OsMA_Floor': 'OsMA Floor Model',
}

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class IndicatorConfig:
    """Configuration for an indicator to test"""
    name: str
    description: str
    method: str  # e.g., 'RSI', 'MACD', 'BollingerBands'
    is_custom: bool = False  # True for custom models like OsMA_*

@dataclass
class BacktestPeriodCoverage:
    """Coverage analysis for backtest periods"""
    total_days: int  # Total days in backtest period
    days_30: bool    # Last 30 days covered
    days_60: bool    # Last 60 days covered
    days_90: bool    # Last 90 days covered
    days_180: bool   # Last 180 days covered
    days_365: bool   # Last 365 days covered
    days_730: bool   # Last 2 years covered
    coverage_summary: str  # Human-readable summary

@dataclass
class BacktestResult:
    """Result from a single backtest"""
    indicator: str
    session: str
    timeframe: str
    weekday_type: str
    trades_total: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    recovery_factor: float
    consecutive_wins: int
    consecutive_losses: int
    avg_trade_duration: str
    largest_winning_trade: float
    largest_losing_trade: float
    avg_winning_trade: float
    avg_losing_trade: float
    payoff_ratio: float
    profit_per_day: float
    backtest_start_date: str
    backtest_end_date: str
    candle_count: int
    
    # Period Coverage Analysis
    period_coverage: BacktestPeriodCoverage  # Period coverage details
    
    status: str  # viable, marginal, not_viable
    metadata: Dict[str, Any] = None

    def to_dict(self):
        return asdict(self)

@dataclass
class SymbolOnboardingReport:
    """Comprehensive report for symbol onboarding"""
    symbol: str
    report_date: str
    report_timestamp: str
    
    # Test Configuration
    timeframes_tested: List[str]
    sessions_tested: List[str]
    weekday_types_tested: List[str]
    indicators_tested: List[IndicatorConfig]
    
    # Historical Data
    data_start_date: str
    data_end_date: str
    data_candle_count: int
    data_source: str  # e.g., 'MT5', 'CSV', 'API'
    
    # Results
    backtest_results: List[BacktestResult]
    viable_indicators: List[Dict[str, Any]]  # Indicators passing viability threshold
    marginal_indicators: List[Dict[str, Any]]  # Indicators near threshold
    
    # Summary Statistics
    total_backtests_run: int
    viable_count: int
    marginal_count: int
    not_viable_count: int
    
    # Quality Metrics
    best_profit_factor: float
    worst_profit_factor: float
    best_win_rate: float
    worst_win_rate: float
    avg_trades_per_config: float
    
    # Recommendations
    recommended_indicators: List[str]
    notes: str
    next_steps: List[str]
    
    # Optional fields with defaults
    data_period_coverage: str = ""  # e.g., "990 days (30d, 60d, 90d, 180d, 1y, 2y)"

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "report_date": self.report_date,
            "report_timestamp": self.report_timestamp,
            "timeframes_tested": self.timeframes_tested,
            "sessions_tested": self.sessions_tested,
            "weekday_types_tested": self.weekday_types_tested,
            "indicators_tested": [asdict(ind) for ind in self.indicators_tested],
            "data_start_date": self.data_start_date,
            "data_end_date": self.data_end_date,
            "data_candle_count": self.data_candle_count,
            "data_source": self.data_source,
            "data_period_coverage": self.data_period_coverage,
            "backtest_results": [r.to_dict() for r in self.backtest_results],
            "viable_indicators": self.viable_indicators,
            "marginal_indicators": self.marginal_indicators,
            "total_backtests_run": self.total_backtests_run,
            "viable_count": self.viable_count,
            "marginal_count": self.marginal_count,
            "not_viable_count": self.not_viable_count,
            "best_profit_factor": self.best_profit_factor,
            "worst_profit_factor": self.worst_profit_factor,
            "best_win_rate": self.best_win_rate,
            "worst_win_rate": self.worst_win_rate,
            "avg_trades_per_config": self.avg_trades_per_config,
            "recommended_indicators": self.recommended_indicators,
            "notes": self.notes,
            "next_steps": self.next_steps
        }

    def to_json(self) -> str:
        """Export to JSON"""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def save_json(self, filepath: str):
        """Save to JSON file"""
        with open(filepath, 'w') as f:
            f.write(self.to_json())

# ============================================================================
# VECTORBT TEST CONFIGURATION
# ============================================================================

class VectorbtDiscoveryConfig:
    """Configuration for vectorbt discovery testing"""
    
    def __init__(self, symbol: str, date_start: str, date_end: str):
        self.symbol = symbol
        self.date_start = date_start
        self.date_end = date_end
        
        # Viability thresholds
        self.min_profit_factor = 1.5
        self.min_win_rate = 0.40
        self.max_drawdown_threshold = -0.25
        self.min_trades = 10  # Need minimum trades for validity
        
        # Configuration - Load ALL MT5 indicators available
        # NO pre-selection - VectorBT determines winners
        self.indicators = [
            IndicatorConfig(
                name=ind_key,
                description=ind_name,
                method=ind_key,
                is_custom=ind_key.startswith('OsMA_')
            )
            for ind_key, ind_name in ALL_MT5_INDICATORS.items()
        ]
    
    def get_test_matrix(self):
        """Generate test matrix: indicators × timeframes × sessions × weekdays"""
        test_matrix = []
        
        for indicator in self.indicators:
            for timeframe in TIMEFRAMES:
                for session_key, session_data in TRADING_SESSIONS.items():
                    for weekday_key, weekday_data in WEEKDAY_CONFIGS.items():
                        test_matrix.append({
                            "indicator": indicator.name,
                            "indicator_config": asdict(indicator),
                            "timeframe": timeframe,
                            "session": session_key,
                            "session_data": session_data,
                            "weekday_type": weekday_key,
                            "weekday_data": weekday_data,
                        })
        
        return test_matrix
    
    def calculate_period_coverage(self, start_date: str, end_date: str) -> BacktestPeriodCoverage:
        """Calculate period coverage for backtest results"""
        from datetime import datetime
        
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days
        
        # Calculate if each period is covered
        days_30 = total_days >= 30
        days_60 = total_days >= 60
        days_90 = total_days >= 90
        days_180 = total_days >= 180
        days_365 = total_days >= 365
        days_730 = total_days >= 730
        
        # Generate summary
        coverage_labels = []
        if days_30:
            coverage_labels.append("30d")
        if days_60:
            coverage_labels.append("60d")
        if days_90:
            coverage_labels.append("90d")
        if days_180:
            coverage_labels.append("180d")
        if days_365:
            coverage_labels.append("1y")
        if days_730:
            coverage_labels.append("2y")
        
        coverage_summary = f"{total_days} days ({', '.join(coverage_labels)})" if coverage_labels else f"{total_days} days"
        
        return BacktestPeriodCoverage(
            total_days=total_days,
            days_30=days_30,
            days_60=days_60,
            days_90=days_90,
            days_180=days_180,
            days_365=days_365,
            days_730=days_730,
            coverage_summary=coverage_summary
        )

# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Create configuration for BTCUSD
    config = VectorbtDiscoveryConfig(
        symbol="BTCUSD",
        date_start="2024-01-01",
        date_end="2026-08-25"
    )
    
    # Get test matrix
    test_matrix = config.get_test_matrix()
    
    print(f"Symbol: {config.symbol}")
    print(f"Period: {config.date_start} to {config.date_end}")
    print(f"\nTest Matrix:")
    print(f"  Indicators: {len(config.indicators)} ({', '.join([i.name for i in config.indicators])})")
    print(f"  Timeframes: {len(TIMEFRAMES)} ({', '.join(TIMEFRAMES)})")
    print(f"  Sessions: {len(TRADING_SESSIONS)} ({', '.join(TRADING_SESSIONS.keys())})")
    print(f"  Weekday Types: {len(WEEKDAY_CONFIGS)} ({', '.join(WEEKDAY_CONFIGS.keys())})")
    print(f"\n  Total Test Configurations: {len(test_matrix)}")
    print(f"  Calculation: {len(config.indicators)} × {len(TIMEFRAMES)} × {len(TRADING_SESSIONS)} × {len(WEEKDAY_CONFIGS)}")
    
    # Show custom models
    custom_indicators = [ind for ind in config.indicators if ind.is_custom]
    print(f"\n  Custom Models Included: {len(custom_indicators)}")
    for ind in custom_indicators:
        print(f"    - {ind.name}: {ind.description}")
    
    # Example of what each test configuration includes
    print(f"\nExample Test Configuration:")
    example = test_matrix[0]
    print(f"  Indicator: {example['indicator']}")
    print(f"  Timeframe: {example['timeframe']}")
    print(f"  Session: {example['session']} ({example['session_data']['name']})")
    print(f"  Weekday Type: {example['weekday_type']}")
