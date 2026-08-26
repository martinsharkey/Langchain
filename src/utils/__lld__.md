# LOW LEVEL DESIGN - src/utils Module

**Module**: Utility Functions  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active

---

## 📋 Module Overview

The `src/utils` module provides common utility functions used throughout the application including logging, decorators, helpers, and common algorithms.

### Module Responsibilities
- ✅ Logging utilities
- ✅ Decorators (caching, timing, retries)
- ✅ Helper functions
- ✅ Common algorithms

---

## 🏗️ Module Architecture

```
src/utils/
├── __init__.py              # Module exports
├── logging.py               # Logging configuration
├── decorators.py            # Common decorators
├── helpers.py               # Helper functions
└── __lld__.md              # This document
```

---

## 📦 Components

### 1. logging.py - Logging Configuration

```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

def get_logger(name: str) -> logging.Logger:
    """Get configured logger."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger
```

### 2. decorators.py - Common Decorators

```python
import time
import functools
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)

def timing(func: Callable) -> Callable:
    """Decorator to time function execution."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} took {duration:.2f}s")
        return result
    return wrapper

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Decorator to retry function on failure."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                    time.sleep(delay)
        return wrapper
    return decorator

def cached(ttl: int = 3600):
    """Decorator to cache function results."""
    def decorator(func: Callable) -> Callable:
        cache = {}
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(kwargs.items()))
            
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < ttl:
                    return result
            
            result = func(*args, **kwargs)
            cache[key] = (result, time.time())
            return result
        return wrapper
    return decorator
```

### 3. helpers.py - Helper Functions

```python
from typing import List, Dict, Any
from decimal import Decimal

def calculate_profit_factor(trades: List[Dict[str, float]]) -> float:
    """Calculate profit factor from trades."""
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    
    if gross_loss == 0:
        return 0.0
    return gross_profit / gross_loss

def calculate_win_rate(trades: List[Dict[str, float]]) -> float:
    """Calculate win rate from trades."""
    if not trades:
        return 0.0
    
    winning = sum(1 for t in trades if t['pnl'] > 0)
    return winning / len(trades)

def calculate_max_drawdown(trades: List[Dict[str, float]]) -> float:
    """Calculate maximum drawdown from trades."""
    if not trades:
        return 0.0
    
    cumulative = 0
    max_cumulative = 0
    max_drawdown = 0
    
    for trade in trades:
        cumulative += trade['pnl']
        if cumulative > max_cumulative:
            max_cumulative = cumulative
        
        drawdown = (cumulative - max_cumulative) / max(max_cumulative, 1)
        max_drawdown = min(max_drawdown, drawdown)
    
    return max_drawdown

def round_price(price: float, decimals: int = 5) -> float:
    """Round price to decimal places."""
    if decimals < 0:
        raise ValueError("Decimals must be non-negative")
    return round(price, decimals)

def format_percentage(value: float, decimals: int = 2) -> str:
    """Format value as percentage string."""
    return f"{value * 100:.{decimals}f}%"
```

### 4. __init__.py - Module Exports

```python
"""Utils module exports."""

from .logging import get_logger, JSONFormatter
from .decorators import timing, retry, cached
from .helpers import (
    calculate_profit_factor,
    calculate_win_rate,
    calculate_max_drawdown,
    round_price,
    format_percentage,
)

__all__ = [
    # Logging
    "get_logger",
    "JSONFormatter",
    # Decorators
    "timing",
    "retry",
    "cached",
    # Helpers
    "calculate_profit_factor",
    "calculate_win_rate",
    "calculate_max_drawdown",
    "round_price",
    "format_percentage",
]
```

---

## 🔄 Usage Examples

### Using Logging
```python
from src.utils import get_logger

logger = get_logger(__name__)

logger.info("Starting discovery")
logger.error("Discovery failed", exc_info=True)
```

### Using Decorators
```python
from src.utils import timing, retry, cached

@timing
@retry(max_attempts=3, delay=1.0)
def fetch_data():
    """Fetch data with timing and retry."""
    return some_expensive_operation()

@cached(ttl=3600)
def get_strategy(strategy_id: str):
    """Get strategy with 1-hour cache."""
    return db.query(Strategy).filter_by(id=strategy_id).first()
```

### Using Helpers
```python
from src.utils import (
    calculate_profit_factor,
    calculate_win_rate,
    format_percentage,
)

trades = [
    {"pnl": 100},
    {"pnl": -50},
    {"pnl": 150},
]

pf = calculate_profit_factor(trades)
wr = calculate_win_rate(trades)

print(f"Profit Factor: {pf}")
print(f"Win Rate: {format_percentage(wr)}")
```

---

## 🧪 Testing

**Location**: `tests/unit/test_utils.py`

```python
def test_calculate_profit_factor():
    """Test profit factor calculation."""
    trades = [
        {"pnl": 100},
        {"pnl": -50},
        {"pnl": 150},
    ]
    pf = calculate_profit_factor(trades)
    assert pf == 5.0  # 250 / 50

def test_timing_decorator():
    """Test timing decorator."""
    @timing
    def slow_function():
        time.sleep(0.1)
        return "done"
    
    result = slow_function()
    assert result == "done"

def test_retry_decorator():
    """Test retry decorator."""
    call_count = 0
    
    @retry(max_attempts=3)
    def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("Failed")
        return "success"
    
    result = failing_function()
    assert result == "success"
    assert call_count == 3
```

---

**Status**: Production Ready
