#!/usr/bin/env python3
"""
Autonomous Trading Bot Launcher — Continuous Learning Mode

Runs the XAUUSD trading bot in an infinite loop with:
- Continuous market analysis
- Meta-strategy signal generation
- Risk-managed trade execution
- Persistent learning via RAG + SQLite + Curiosity agent

Usage:
    python run_bot.py
"""

import sys
import os
import time
import logging
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import LOGS_DIR
from src.utils.logger import get_logger
from src.main import TradingBot

logger = get_logger("launcher")


def main():
    """Run the trading bot continuously."""
    os.makedirs(LOGS_DIR, exist_ok=True)

    logger.info("=" * 60)
    logger.info("AUTONOMOUS TRADING BOT — CONTINUOUS LEARNING MODE")
    logger.info("=" * 60)
    logger.info(f"Start time: {datetime.now().isoformat()}")
    logger.info("Press Ctrl+C to stop")

    bot = TradingBot()

    try:
        # Phase 1-5: Setup
        bot.check_environment()
        bot.setup_environment()
        bot.build_team()
        bot.connect_mt5()
        bot.initialize_strategy()

        logger.info("Bot initialized. Starting trading loop...")

        # Phase 6-7: Continuous trading loop
        bot.running = True
        while bot.running:
            try:
                cycle_result = bot.run_trading_cycle()

                # Log cycle summary
                signal = cycle_result.get("signal", {})
                trade = cycle_result.get("trade", {})
                logger.info(
                    f"Cycle #{cycle_result['cycle']} complete | "
                    f"Signal: {signal.get('action', 'N/A')} | "
                    f"Trade: {'EXECUTED' if trade.get('executed') else 'SKIPPED'}"
                )

                # Wait between cycles (shorter when market is active)
                wait_time = 10
                logger.info(f"Waiting {wait_time}s before next cycle...")
                time.sleep(wait_time)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Cycle error: {str(e)}", exc_info=True)
                time.sleep(30)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
    finally:
        bot.shutdown()
        logger.info(f"End time: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
