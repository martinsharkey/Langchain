"""
run_trader.py -- DEPRECATED (#46). Use `python app.py LIVE_MICRO` instead.

app.py is the SINGLE supported launcher (dashboard + engine + research + CryptoRTI
feed together, with mode from CLI arg). This script is kept only for backward
reference and forwards to the same engine; do not add new logic here.

Original: single entry point for the REAL trading engine (ScalpEngine).
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
