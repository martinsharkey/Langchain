"""
run_trader.py — single entry point for the REAL trading engine.

Starts the ScalpEngine which trades the configured symbols on the connected
MT5 demo account, records real outcomes, and drives toward the learning target.

Usage:
    python run_trader.py                 # uses TRADING_MODE from .env (default OBSERVE)
    TRADING_MODE=LIVE_MICRO python run_trader.py

Modes (safety gate):
    OBSERVE     analyze only, no orders
    PAPER       simulated fills at live prices
    LIVE_MICRO  REAL orders on demo, capped to 0.01 lots
    LIVE        REAL orders, full sizing
"""

import os
import sys

# Allow overriding mode via first CLI arg for convenience:
#   python run_trader.py LIVE_MICRO
if len(sys.argv) > 1 and sys.argv[1].upper() in ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE"):
    os.environ["TRADING_MODE"] = sys.argv[1].upper()

from src.trading.scalp_engine import run_scalp_engine
from src.utils.logger import get_logger

logger = get_logger("run_trader")

if __name__ == "__main__":
    logger.info(f"Starting trader in mode={os.environ.get('TRADING_MODE', 'OBSERVE')}")
    run_scalp_engine()
