# LOW LEVEL DESIGN - Execution Service

**Service**: Live Trade Execution & Real-Time Monitoring  
**Port**: 8006  
**Technology**: MT5 Integration, Real-time Data Streaming, FastAPI  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready

---

## 📋 Service Overview

The Execution Service handles real-time trade execution, position management, and strategy performance monitoring. It continuously monitors deployed strategies, executes trading signals, and tracks performance metrics across all live accounts.

### Service Responsibilities
- ✅ Execute trading signals
- ✅ Manage open positions
- ✅ Monitor account performance
- ✅ Track real-time metrics
- ✅ Handle error conditions
- ✅ Provide execution reports
- ✅ Monitor strategy health

---

## 🏗️ Service Architecture

```
services/execution-service/
├── app/                         # API Layer
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # Endpoints
│   │   └── schemas.py          # Request/response models
│   ├── websocket/
│   │   ├── __init__.py
│   │   └── handlers.py         # WebSocket handlers
│   └── __lld__.md              # API design
│
├── core/                        # Business Logic
│   ├── __init__.py
│   ├── execution_engine.py     # Main execution logic
│   ├── position_manager.py     # Position management
│   ├── order_executor.py       # Order execution
│   ├── performance_tracker.py  # Performance tracking
│   └── __lld__.md              # Logic design
│
├── models/                      # Data Models
│   ├── __init__.py
│   ├── database.py             # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   └── __lld__.md              # Data design
│
├── tests/
│   ├── __init__.py
│   ├── test_api.py             # 15+ endpoint tests
│   ├── test_core.py            # 20+ logic tests
│   └── conftest.py             # Fixtures
│
├── __lld__.md                  # THIS FILE
├── API_SPEC.md                 # API specification
├── Dockerfile                  # Container definition
├── requirements.txt            # Dependencies
└── README.md                   # Service README
```

---

## 🔌 API Endpoints

### POST /execute/trade
**Execute a trade order**

Request:
```json
{
  "strategy_id": "strat_123456",
  "symbol": "BTCUSD",
  "direction": "buy",
  "volume": 0.1,
  "entry_price": 45000,
  "stop_loss": 44000,
  "take_profit": 46000
}
```

Response:
```json
{
  "order_id": "ord_xyz789",
  "strategy_id": "strat_123456",
  "status": "executed",
  "symbol": "BTCUSD",
  "direction": "buy",
  "volume": 0.1,
  "entry_price": 45000,
  "executed_at": "2026-08-25T15:00:00Z",
  "pnl": 0,
  "pnl_pct": 0
}
```

### GET /execute/positions
**Get open positions**

Response:
```json
{
  "strategy_id": "strat_123456",
  "positions": [
    {
      "position_id": "pos_123",
      "symbol": "BTCUSD",
      "direction": "buy",
      "volume": 0.1,
      "entry_price": 45000,
      "current_price": 45250,
      "pnl": 250,
      "pnl_pct": 0.56,
      "open_time": "2026-08-25T15:00:00Z"
    }
  ],
  "total_open_positions": 1,
  "total_pnl": 250,
  "total_pnl_pct": 0.56
}
```

### GET /execute/performance/{strategy_id}
**Get strategy performance metrics**

Response:
```json
{
  "strategy_id": "strat_123456",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "uptime_seconds": 86400,
  "trades_total": 25,
  "trades_winning": 16,
  "trades_losing": 9,
  "win_rate": 0.64,
  "profit_factor": 2.3,
  "gross_profit": 5000,
  "gross_loss": -2173,
  "net_pnl": 2827,
  "max_consecutive_wins": 5,
  "max_consecutive_losses": 3,
  "max_drawdown": -0.08,
  "recovery_factor": 35.3,
  "sharpe_ratio": 1.85
}
```

### WebSocket /ws/stream/{strategy_id}
**Real-time execution stream**

Subscribe to real-time trade updates:
```json
{
  "type": "trade_executed",
  "data": {
    "order_id": "ord_xyz789",
    "symbol": "BTCUSD",
    "price": 45000,
    "timestamp": "2026-08-25T15:00:00Z"
  }
}
```

### GET /health
**Health check**

Response:
```json
{
  "status": "healthy",
  "mt5_connections": 5,
  "active_strategies": 8,
  "executing_trades": 3,
  "database": "connected"
}
```

---

## 📦 Core Components

### 1. execution_engine.py - Main Execution Logic

```python
import logging
from typing import Dict, List
import asyncio
from core.order_executor import OrderExecutor
from core.position_manager import PositionManager
from core.performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """Main execution engine."""
    
    def __init__(self, db_session):
        self.db = db_session
        self.order_executor = OrderExecutor()
        self.position_manager = PositionManager(db_session)
        self.performance_tracker = PerformanceTracker(db_session)
        self.active_strategies = {}
    
    async def execute_trade(
        self,
        strategy_id: str,
        symbol: str,
        direction: str,
        volume: float,
        entry_price: float,
        stop_loss: float = None,
        take_profit: float = None
    ) -> Dict:
        """Execute a trade order."""
        
        logger.info(f"Executing {direction} order: {symbol} {volume}")
        
        try:
            # Pre-execution validation
            await self._validate_order(strategy_id, symbol, volume)
            
            # Execute order
            order_result = await self.order_executor.execute(
                symbol=symbol,
                direction=direction,
                volume=volume,
                entry_price=entry_price
            )
            
            # Create position record
            position = await self.position_manager.create_position(
                strategy_id=strategy_id,
                order_id=order_result["order_id"],
                symbol=symbol,
                direction=direction,
                volume=volume,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # Track execution
            execution = Execution(
                order_id=order_result["order_id"],
                strategy_id=strategy_id,
                symbol=symbol,
                direction=direction,
                volume=volume,
                entry_price=entry_price,
                status="executed",
                executed_at=datetime.utcnow()
            )
            
            self.db.add(execution)
            self.db.commit()
            
            logger.info(f"Trade executed: {order_result['order_id']}")
            
            return {
                "order_id": order_result["order_id"],
                "strategy_id": strategy_id,
                "status": "executed",
                "symbol": symbol,
                "direction": direction,
                "volume": volume,
                "entry_price": entry_price,
                "executed_at": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Trade execution failed: {str(e)}")
            raise
    
    async def get_positions(self, strategy_id: str) -> Dict:
        """Get open positions for strategy."""
        return await self.position_manager.get_open_positions(strategy_id)
    
    async def get_performance(self, strategy_id: str) -> Dict:
        """Get strategy performance metrics."""
        return await self.performance_tracker.calculate_metrics(strategy_id)
    
    async def monitor_strategies(self):
        """Continuously monitor active strategies."""
        while True:
            try:
                # Get all active strategies
                strategies = self.db.query(Deployment).filter_by(
                    status="deployed"
                ).all()
                
                for strategy in strategies:
                    # Update performance
                    metrics = await self.performance_tracker.calculate_metrics(
                        strategy.strategy_id
                    )
                    
                    # Check health
                    if metrics['net_pnl'] < strategy.parameters.get('stop_loss_pnl', -5000):
                        logger.warning(f"Strategy stop loss triggered: {strategy.strategy_id}")
                        # Could auto-rollback here
                    
                    # Broadcast metrics
                    await self._broadcast_metrics(strategy.strategy_id, metrics)
                
                # Check every 5 minutes
                await asyncio.sleep(300)
            
            except Exception as e:
                logger.error(f"Strategy monitoring error: {str(e)}")
    
    async def _validate_order(self, strategy_id: str, symbol: str, volume: float):
        """Validate order before execution."""
        strategy = self.db.query(Deployment).filter_by(
            strategy_id=strategy_id
        ).first()
        
        if not strategy or strategy.status != "deployed":
            raise ValueError(f"Strategy not deployed: {strategy_id}")
        
        if strategy.symbol != symbol:
            raise ValueError(f"Symbol mismatch: {symbol}")
        
        if volume <= 0:
            raise ValueError(f"Invalid volume: {volume}")
    
    async def _broadcast_metrics(self, strategy_id: str, metrics: Dict):
        """Broadcast metrics to connected WebSocket clients."""
        # Implementation broadcasts to WebSocket connections
        pass
```

### 2. order_executor.py - Order Execution

```python
import MetaTrader5 as mt5

class OrderExecutor:
    """Execute orders on MT5."""
    
    async def execute(
        self,
        symbol: str,
        direction: str,
        volume: float,
        entry_price: float
    ) -> Dict:
        """Execute order on MT5."""
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
            "price": entry_price,
            "comment": "StrategyOps Order",
        }
        
        try:
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Order failed: {result.comment}")
            
            return {
                "order_id": result.order,
                "status": "executed"
            }
        
        except Exception as e:
            raise RuntimeError(f"Execution error: {str(e)}")
```

### 3. performance_tracker.py - Performance Tracking

```python
class PerformanceTracker:
    """Track strategy performance."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def calculate_metrics(self, strategy_id: str) -> Dict:
        """Calculate performance metrics."""
        
        # Get all trades for strategy
        trades = self.db.query(Execution).filter_by(
            strategy_id=strategy_id
        ).all()
        
        if not trades:
            return {
                "trades_total": 0,
                "net_pnl": 0,
                "win_rate": 0
            }
        
        # Calculate metrics
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = sum(abs(t.pnl) for t in losing_trades)
        
        return {
            "trades_total": len(trades),
            "trades_winning": len(winning_trades),
            "trades_losing": len(losing_trades),
            "win_rate": len(winning_trades) / len(trades) if trades else 0,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else 0,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": gross_profit - gross_loss
        }
```

---

## 🗄️ Data Models

### Execution (Database Model)

```python
from sqlalchemy import Column, String, Float, DateTime

class Execution(Base):
    __tablename__ = "executions"
    
    order_id = Column(String, primary_key=True)
    strategy_id = Column(String, ForeignKey("deployments.strategy_id"))
    symbol = Column(String, nullable=False)
    direction = Column(String)  # buy/sell
    volume = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    status = Column(String)  # executed, closed, error
    executed_at = Column(DateTime)
    closed_at = Column(DateTime, nullable=True)
```

---

## 🧪 Testing

### Unit Tests (test_core.py)

```python
import pytest
from core.execution_engine import ExecutionEngine

@pytest.mark.asyncio
async def test_execute_trade(db_session):
    """Test trade execution."""
    engine = ExecutionEngine(db_session)
    
    result = await engine.execute_trade(
        strategy_id="strat_123456",
        symbol="BTCUSD",
        direction="buy",
        volume=0.1,
        entry_price=45000
    )
    
    assert "order_id" in result
    assert result["status"] == "executed"

@pytest.mark.asyncio
async def test_get_positions(db_session):
    """Test get open positions."""
    engine = ExecutionEngine(db_session)
    
    result = await engine.get_positions("strat_123456")
    
    assert "positions" in result
    assert isinstance(result["positions"], list)

@pytest.mark.asyncio
async def test_get_performance(db_session):
    """Test get performance metrics."""
    engine = ExecutionEngine(db_session)
    
    result = await engine.get_performance("strat_123456")
    
    assert "trades_total" in result
    assert "net_pnl" in result
    assert "win_rate" in result
```

---

## 🔄 Real-Time Features

### WebSocket Connections
- Real-time trade execution updates
- Live price feeds
- Performance metric streaming
- Error notifications
- Strategy health alerts

### Performance Monitoring
- Live P&L tracking
- Win/loss rate calculation
- Drawdown monitoring
- Recovery factor tracking
- Sharpe ratio calculation

---

**Status**: Production Ready  
**Last Updated**: August 25, 2026  
**Maintainer**: @team-dev
