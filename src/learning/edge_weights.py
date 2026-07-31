"""
Per-symbol backtest-derived edge map.

CRITICAL: edge is SYMBOL-SPECIFIC. The same indicator combo that wins on gold
loses on an index (e.g. Volume_Breakout PF 1.32 on XAUUSD but 0.91 on GER40).
So weights are keyed by symbol, applied at ensemble vote time. Unlisted
symbols/strategies default to neutral (1.0).

Values are OUT-OF-SAMPLE profit-factor-derived multipliers from the edge sweep
(tools/edge_sweep) on Jan-onward MT5 history. The live L2 learning loop adapts
from these seeds. Re-run the sweep to refresh as more data accrues.

Match is by symbol PREFIX (XAUUSD-ECN matches 'XAUUSD').
"""

EDGE_WEIGHTS_BY_SYMBOL = {
    # XAUUSD-ECN M15 evidence: Volume_Breakout 1.32, BB_Bounce 1.15,
    # CCI_Breakout 1.13, RSI_MeanReversion 1.10, MACD_OsMA_Power 1.08,
    # ADX 1.07; losers: BB_SqueezeBreakout 0.75, Stochastic 0.95, MACD_Cross ~1.0
    "XAUUSD": {
        "Volume_Breakout": 2.5,
        "BB_Bounce": 1.8,
        "CCI_Breakout": 1.7,
        "RSI_MeanReversion": 1.4,
        "MACD_OsMA_Power_Confluence": 1.3,
        "ADX_TrendStrength": 1.2,
        "EMA_TrendFollow": 1.1,
        "RSI_Momentum": 0.7,
        "MACD_Cross": 0.6,
        "GoldenCross_50_200": 0.5,
        "Stochastic_Reversal": 0.4,
        "BB_SqueezeBreakout": 0.3,
    },
    # GER40 M15 evidence: MACD_Momentum 1.02, MACD_Cross 1.02, CCI 1.06,
    # BB_SqueezeBreakout 1.2, MACD_OsMA_Power 1.05; losers: RSI_MeanReversion 0.79,
    # Volume_Breakout 0.91, BB_Bounce 0.91, RSI_Momentum 0.95
    "GER40": {
        "BB_SqueezeBreakout": 1.6,
        "CCI_Breakout": 1.4,
        "MACD_OsMA_Power_Confluence": 1.3,
        "MACD_Cross": 1.2,
        "MACD_Momentum": 1.2,
        "Volume_Breakout": 0.5,
        "BB_Bounce": 0.5,
        "RSI_MeanReversion": 0.3,
        "RSI_Momentum": 0.6,
    },
}


def edge_weight(symbol: str, strategy: str) -> float:
    """Per-symbol edge multiplier for a strategy (prefix match); 1.0 if unknown."""
    if not symbol:
        return 1.0
    su = symbol.upper()
    for key, table in EDGE_WEIGHTS_BY_SYMBOL.items():
        if su.startswith(key):
            return float(table.get(strategy, 1.0))
    return 1.0
