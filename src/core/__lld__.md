# LOW LEVEL DESIGN - src/core Module

**Module**: Core Application Utilities  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active

---

## 📋 Module Overview

The `src/core` module provides fundamental, shared functionality used across the entire application. This module contains data models, schemas, and core utilities that form the foundation of the StrategyOps platform.

### Module Responsibilities
- ✅ Define core data structures (Strategy, Trade, PerformanceMetrics)
- ✅ Provide Pydantic schemas for API validation
- ✅ Define enums and constants
- ✅ Expose shared utilities and helpers

### Core Principle
**Single Source of Truth**: All core data models are defined here to ensure consistency across services.

---

## 🏗️ Module Architecture

```
src/core/
├── __init__.py              # Module exports
├── models.py                # Data models (Strategy, Trade, etc.)
├── schemas.py              # Pydantic schemas for API validation
├── enums.py                # Enumerations (SessionType, TimeFrame)
├── constants.py            # Application constants
└── exceptions.py           # Custom exceptions
```

---

## 📦 Components

### 1. models.py - Data Models

**Purpose**: Define core data structures using Python dataclasses or Pydantic.

**Key Classes**:

#### Strategy
```python
class Strategy(BaseModel):
    """Trading strategy definition."""
    id: str                    # Unique identifier
    name: str                  # Human-readable name
    symbol: str                # Trading symbol (e.g., BTCUSD)
    session: str               # Trading session (London, NY, Tokyo)
    timeframe: str             # Candle timeframe (M15, H1, D1)
    indicators: List[str]      # Indicator names
    parameters: Dict[str, Any] # Indicator parameters
    status: StrategyStatus     # Strategy status
    created_at: datetime       # Creation timestamp
```

#### Trade
```python
class Trade(BaseModel):
    """Executed trade record."""
    id: str                    # Trade ID
    strategy_id: str           # Associated strategy
    symbol: str                # Trading symbol
    direction: TradeDirection  # Buy or Sell
    entry_price: float         # Entry price
    exit_price: Optional[float] # Exit price (if closed)
    volume: float              # Trade size
    pnl: float                 # Profit/Loss
    opened_at: datetime        # Entry time
    closed_at: Optional[datetime] # Exit time
```

#### PerformanceMetrics
```python
class PerformanceMetrics(BaseModel):
    """Strategy performance metrics."""
    profit_factor: float       # Gross profit / Gross loss
    win_rate: float            # Percentage of winning trades
    total_return: float        # Total return percentage
    max_drawdown: float        # Maximum drawdown
    sharpe_ratio: float        # Risk-adjusted return
    trades: int                # Total trade count
```

### 2. schemas.py - API Schemas

**Purpose**: Define Pydantic models for request/response validation.

**Key Schemas**:

```python
class StrategyCreateRequest(BaseModel):
    """Request to create a new strategy."""
    symbol: str                # Trading symbol
    session: str               # Trading session
    timeframe: str             # Candle timeframe
    indicators: List[str]      # Indicators to use
    parameters: Dict[str, Any] # Indicator parameters

class StrategyResponse(BaseModel):
    """Strategy API response."""
    id: str
    name: str
    symbol: str
    status: str
    created_at: datetime
    metrics: Optional[PerformanceMetrics]
```

### 3. enums.py - Enumerations

**Purpose**: Define type-safe enums for options.

```python
class SessionType(str, Enum):
    """Trading session types."""
    LONDON = "london"
    NEW_YORK = "new_york"
    TOKYO = "tokyo"
    SYDNEY = "sydney"

class TimeFrame(str, Enum):
    """Candle timeframes."""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

class StrategyStatus(str, Enum):
    """Strategy status."""
    DRAFT = "draft"
    TESTING = "testing"
    APPROVED = "approved"
    LIVE = "live"
    PAUSED = "paused"
    ARCHIVED = "archived"
```

### 4. constants.py - Application Constants

**Purpose**: Define application-wide constants.

```python
# Database settings
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000

# Trading settings
MIN_PROFIT_FACTOR = 1.5
MIN_TRADES_FOR_VALIDATION = 30
MAX_LEVERAGE = 10

# Timeouts (seconds)
DISCOVERY_TIMEOUT = 1800  # 30 minutes
OPTIMIZATION_TIMEOUT = 3600  # 1 hour
VALIDATION_TIMEOUT = 900  # 15 minutes

# Performance targets
MIN_COVERAGE = 0.80  # 80%
MAX_DRAWDOWN_TOLERANCE = -0.20  # -20%
MIN_SHARPE_RATIO = 1.0
```

### 5. exceptions.py - Custom Exceptions

**Purpose**: Define domain-specific exceptions.

```python
class StrategyOpsException(Exception):
    """Base exception for StrategyOps."""
    pass

class ValidationError(StrategyOpsException):
    """Data validation failed."""
    pass

class DiscoveryError(StrategyOpsException):
    """Discovery process failed."""
    pass

class OptimizationError(StrategyOpsException):
    """Optimization process failed."""
    pass

class DeploymentError(StrategyOpsException):
    """Deployment failed."""
    pass
```

---

## 📤 Module Exports (__init__.py)

```python
"""Core module exports."""

from .models import Strategy, Trade, PerformanceMetrics
from .schemas import StrategyCreateRequest, StrategyResponse
from .enums import SessionType, TimeFrame, StrategyStatus
from .constants import DEFAULT_PAGE_SIZE, MIN_PROFIT_FACTOR
from .exceptions import (
    StrategyOpsException,
    ValidationError,
    DiscoveryError,
)

__all__ = [
    # Models
    "Strategy",
    "Trade",
    "PerformanceMetrics",
    # Schemas
    "StrategyCreateRequest",
    "StrategyResponse",
    # Enums
    "SessionType",
    "TimeFrame",
    "StrategyStatus",
    # Constants
    "DEFAULT_PAGE_SIZE",
    "MIN_PROFIT_FACTOR",
    # Exceptions
    "StrategyOpsException",
    "ValidationError",
    "DiscoveryError",
]
```

---

## 🔄 Usage Examples

### Using Core Models
```python
from src.core import Strategy, PerformanceMetrics

# Create a strategy
strategy = Strategy(
    id="strat_001",
    name="Bollinger OsMA",
    symbol="BTCUSD",
    session="london",
    timeframe="M15",
    indicators=["Bollinger_Bands", "OsMA"],
    parameters={"bb_period": 20, "osma_fast": 12},
    status="testing"
)

# Use performance metrics
metrics = PerformanceMetrics(
    profit_factor=1.67,
    win_rate=0.58,
    total_return=0.23,
    max_drawdown=-0.12,
    sharpe_ratio=1.45,
    trades=245
)
```

### Using Enums
```python
from src.core import SessionType, TimeFrame

def get_session_hours(session: SessionType) -> Tuple[int, int]:
    """Get trading hours for session."""
    hours = {
        SessionType.LONDON: (8, 17),
        SessionType.NEW_YORK: (14, 21),
        SessionType.TOKYO: (1, 10),
    }
    return hours[session]
```

### Validation with Schemas
```python
from src.core import StrategyCreateRequest

# Request validation (automatic with Pydantic)
request_data = {
    "symbol": "BTCUSD",
    "session": "london",
    "timeframe": "M15",
    "indicators": ["Bollinger_Bands", "OsMA"],
    "parameters": {"bb_period": 20}
}

request = StrategyCreateRequest(**request_data)
# If validation fails, Pydantic raises ValidationError
```

---

## 🔗 Dependencies

### Internal
- None (core module has no internal dependencies)

### External
- `pydantic` - Data validation
- `python-dateutil` - Date/time utilities
- `typing` - Type hints (stdlib)

### Services Depending on This Module
- All 6 microservices import from `src/core`
- All API endpoints use `src/core` schemas

---

## 🧪 Testing Strategy

### Unit Tests Location
`tests/unit/test_core.py`

**Key Test Areas**:
- Model instantiation and validation
- Enum value validation
- Schema request/response validation
- Exception raising

```python
def test_strategy_model_validation():
    """Test Strategy model validates correctly."""
    # Valid strategy
    strategy = Strategy(...)
    assert strategy.id is not None
    
    # Invalid strategy
    with pytest.raises(ValidationError):
        Strategy(symbol="", session="invalid")
```

---

## 📋 Design Decisions

### Decision 1: Pydantic for Models
**Rationale**: Automatic validation, OpenAPI generation, JSON serialization  
**Alternative**: Dataclasses (no validation)  
**Selected**: Pydantic ✅

### Decision 2: Enum for Fixed Values
**Rationale**: Type safety, IDE autocomplete, prevents invalid values  
**Alternative**: String constants  
**Selected**: Enum ✅

### Decision 3: Shared Core Module
**Rationale**: Single source of truth, prevents duplication  
**Alternative**: Per-service models  
**Selected**: Shared Core ✅

---

## 🚀 Future Enhancements

1. **Database Models** - SQLAlchemy ORM models
2. **Event Models** - Domain events for event sourcing
3. **DTO Pattern** - Request/Response DTOs
4. **Serializers** - Custom JSON serializers
5. **Validators** - Custom validators for complex logic

---

## 📞 Contact & Questions

- **Owner**: Architecture Team
- **Slack**: #architecture-discussions
- **Related**: src/config, src/integrations

---

**Status**: Production Ready  
**Last Review**: August 25, 2026  
**Next Review**: October 1, 2026
