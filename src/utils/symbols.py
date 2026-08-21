"""
Symbol helpers — single source of truth for broker-specific suffix stripping.

All live trading paths should normalize through `symbol_base()` rather than
hand-rolling `.upper().split("-")[0]` so that suffix changes (e.g. -ECN, -micro)
are handled consistently.
"""
from __future__ import annotations


def symbol_base(symbol: str) -> str:
    """Strip broker-specific suffix and trailing dots from a symbol.

    Examples:
        XAUUSD-ECN  -> XAUUSD
        xauusd.ecn  -> XAUUSD
        BTCUSD      -> BTCUSD
        EURUSD.micro -> EURUSD
    """
    if not symbol:
        return ""
    return symbol.upper().split("-")[0].split(".")[0].rstrip(".")
