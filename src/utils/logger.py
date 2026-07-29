"""
Logging configuration with Rich console output.
"""

import os
import logging
from datetime import datetime
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from src.config import LOGS_DIR

# Custom theme for the trading bot
CUSTOM_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "trade": "bold magenta",
    "agent": "bold blue",
})

console = Console(theme=CUSTOM_THEME)

def setup_logger(name: str = "trading_bot") -> logging.Logger:
    """Set up a logger with both file and console handlers."""
    # Ensure logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # File handler (detailed, all levels)
    log_file = os.path.join(
        LOGS_DIR,
        f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (Rich, INFO+)
    console_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_time=False,
        show_path=False,
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "trading_bot") -> logging.Logger:
    """Get or create a logger instance."""
    return setup_logger(name)
