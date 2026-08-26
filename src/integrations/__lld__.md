# LOW LEVEL DESIGN - src/integrations Module

**Module**: External Integrations  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active

---

## 📋 Module Overview

The `src/integrations` module manages all external service integrations including MT5 trading platform, database connections, and third-party APIs.

### Module Responsibilities
- ✅ MT5 platform integration
- ✅ Database connection management
- ✅ External API clients
- ✅ Integration error handling

---

## 🏗️ Module Architecture

```
src/integrations/
├── __init__.py              # Module exports
├── mt5/                     # MT5 trading platform
│   ├── __init__.py
│   ├── client.py           # MT5 client wrapper
│   ├── data_fetcher.py     # Historical data
│   └── __lld__.md
├── database/                # Database connections
│   ├── __init__.py
│   ├── connection.py        # Connection management
│   ├── models.py           # SQLAlchemy models
│   └── __lld__.md
└── __lld__.md              # This document
```

---

## 📦 Components

### 1. MT5 Integration (mt5/client.py)

```python
import MetaTrader5 as mt5
from typing import List, Dict

class MT5Client:
    """Wrapper for MT5 trading platform."""
    
    def __init__(self, login: int, password: str, server: str):
        """Initialize MT5 connection."""
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to MT5."""
        if not mt5.initialize(login=self.login, password=self.password, server=self.server):
            raise ConnectionError("Failed to connect to MT5")
        self.connected = True
        return True
    
    def disconnect(self):
        """Disconnect from MT5."""
        if self.connected:
            mt5.shutdown()
            self.connected = False
    
    def get_account_info(self) -> Dict:
        """Get account information."""
        if not self.connected:
            raise RuntimeError("Not connected to MT5")
        
        info = mt5.account_info()
        return {
            "balance": info.balance,
            "equity": info.equity,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "open_orders": info.orders_limit,
        }
    
    def open_order(self, symbol: str, direction: str, volume: float, price: float):
        """Place a trading order."""
        if not self.connected:
            raise RuntimeError("Not connected to MT5")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "comment": "StrategyOps Order",
        }
        
        result = mt5.order_send(request)
        return result.order if result.retcode == mt5.TRADE_RETCODE_DONE else None
    
    def close_order(self, ticket: int, volume: float, price: float):
        """Close an open order."""
        if not self.connected:
            raise RuntimeError("Not connected to MT5")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
```

### 2. Database Integration (database/connection.py)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

class DatabaseConnection:
    """Manage database connections."""
    
    def __init__(self, database_url: str, pool_size: int = 20):
        """Initialize database connection."""
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=40,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
    
    def get_session(self):
        """Get database session."""
        return self.SessionLocal()
    
    def health_check(self) -> bool:
        """Check database health."""
        try:
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False
```

### 3. __init__.py - Module Exports

```python
"""Integrations module exports."""

from .mt5.client import MT5Client
from .database.connection import DatabaseConnection

__all__ = [
    "MT5Client",
    "DatabaseConnection",
]
```

---

## 🔄 Usage Examples

### MT5 Integration
```python
from src.integrations import MT5Client

# Create client
client = MT5Client(login=12345, password="password", server="ICMarkets-Demo")

# Connect
client.connect()

# Get account info
account = client.get_account_info()
print(f"Balance: {account['balance']}")

# Place order
order_id = client.open_order("BTCUSD", "buy", 0.1, 45000.0)

# Close order
client.close_order(order_id, 0.1, 45100.0)

# Disconnect
client.disconnect()
```

### Database Integration
```python
from src.integrations import DatabaseConnection

# Create connection
db = DatabaseConnection("postgresql://user:pass@localhost/strategyops")

# Get session
session = db.get_session()

# Use session
try:
    strategies = session.query(Strategy).all()
finally:
    session.close()

# Health check
if db.health_check():
    print("Database is healthy")
```

---

## 🧪 Testing

**Location**: `tests/unit/test_integrations.py`

```python
@pytest.fixture
def mt5_client():
    """Create mock MT5 client."""
    return MT5Client(login=12345, password="password", server="demo")

def test_mt5_connect(mt5_client, mocker):
    """Test MT5 connection."""
    mocker.patch("MetaTrader5.initialize", return_value=True)
    assert mt5_client.connect() is True

def test_database_connection():
    """Test database connection."""
    db = DatabaseConnection("sqlite:///:memory:")
    assert db.health_check() is True
```

---

## ⚠️ Error Handling

```python
try:
    client.connect()
except ConnectionError:
    logger.error("Failed to connect to MT5")
    raise

try:
    session = db.get_session()
    strategies = session.query(Strategy).all()
except DatabaseError:
    logger.error("Database error")
    raise
finally:
    session.close()
```

---

**Status**: Production Ready
