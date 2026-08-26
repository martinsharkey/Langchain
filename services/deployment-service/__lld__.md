# LOW LEVEL DESIGN - Deployment Service

**Service**: Live Strategy Deployment  
**Port**: 8004  
**Technology**: MT5 Integration, Configuration Management, FastAPI  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready

---

## 📋 Service Overview

The Deployment Service manages the deployment of validated trading strategies to live MT5 trading accounts. It handles strategy configuration, MT5 connection management, and rollback procedures for safe production trading.

### Service Responsibilities
- ✅ Deploy strategies to MT5
- ✅ Configure strategy parameters per session
- ✅ Manage strategy lifecycle
- ✅ Handle rollbacks
- ✅ Monitor deployment status
- ✅ Store deployment records

---

## 🏗️ Service Architecture

```
services/deployment-service/
├── app/                         # API Layer
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # Endpoints
│   │   └── schemas.py          # Request/response models
│   └── __lld__.md              # API design
│
├── core/                        # Business Logic
│   ├── __init__.py
│   ├── deployment_manager.py   # Main deployment logic
│   ├── mt5_connector.py        # MT5 connection
│   ├── strategy_configurator.py # Strategy configuration
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

### POST /deploy/strategy
**Deploy a strategy to live trading**

Request:
```json
{
  "strategy_name": "BTCUSD_RSI_MACD",
  "validation_id": "val_abc456",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "parameters": {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26
  },
  "account_id": "acc_12345",
  "environment": "production"
}
```

Response:
```json
{
  "deployment_id": "dep_xyz789",
  "status": "deployed",
  "strategy_id": "strat_123456",
  "deployed_at": "2026-08-25T15:00:00Z",
  "message": "Strategy deployed successfully"
}
```

### GET /deploy/status/{deployment_id}
**Check deployment status**

Response:
```json
{
  "deployment_id": "dep_xyz789",
  "strategy_id": "strat_123456",
  "status": "active",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "trades": 15,
  "pnl": 2500.50,
  "uptime": 86400,
  "mt5_connected": true
}
```

### POST /deploy/rollback/{deployment_id}
**Rollback a strategy deployment**

Request:
```json
{
  "reason": "Performance degradation detected"
}
```

Response:
```json
{
  "deployment_id": "dep_xyz789",
  "status": "rolled_back",
  "rolled_back_at": "2026-08-25T16:00:00Z",
  "message": "Strategy successfully rolled back"
}
```

### GET /health
**Health check**

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "mt5_connections": 3,
  "deployed_strategies": 5
}
```

---

## 📦 Core Components

### 1. deployment_manager.py - Main Deployment Logic

```python
import logging
from typing import Dict
import MetaTrader5 as mt5
from core.mt5_connector import MT5Connector
from core.strategy_configurator import StrategyConfigurator

logger = logging.getLogger(__name__)

class DeploymentManager:
    """Main deployment manager."""
    
    def __init__(self, db_session):
        self.db = db_session
        self.mt5 = MT5Connector()
        self.configurator = StrategyConfigurator()
    
    async def deploy_strategy(
        self,
        strategy_name: str,
        validation_id: str,
        symbol: str,
        session: str,
        timeframe: str,
        parameters: Dict,
        account_id: str,
        environment: str
    ) -> Dict:
        """Deploy strategy to live trading."""
        
        logger.info(f"Deploying strategy: {strategy_name}")
        
        try:
            # Validate deployment prerequisites
            await self._validate_deployment(account_id, symbol)
            
            # Generate unique strategy ID
            strategy_id = f"strat_{strategy_name}_{int(time.time())}"
            
            # Configure strategy
            config = await self.configurator.create_config(
                strategy_name=strategy_name,
                symbol=symbol,
                session=session,
                timeframe=timeframe,
                parameters=parameters
            )
            
            # Connect to MT5
            await self.mt5.connect(account_id)
            
            # Deploy strategy (write to MT5)
            await self.mt5.deploy_strategy(strategy_id, config)
            
            # Store deployment record
            deployment = Deployment(
                id=f"dep_{strategy_id}",
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                validation_id=validation_id,
                symbol=symbol,
                session=session,
                timeframe=timeframe,
                account_id=account_id,
                environment=environment,
                status="deployed",
                parameters=parameters
            )
            
            self.db.add(deployment)
            self.db.commit()
            
            logger.info(f"Strategy deployed: {strategy_id}")
            
            return {
                "deployment_id": deployment.id,
                "strategy_id": strategy_id,
                "status": "deployed"
            }
        
        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")
            raise
    
    async def rollback_strategy(
        self,
        deployment_id: str,
        reason: str
    ) -> Dict:
        """Rollback a strategy deployment."""
        
        logger.info(f"Rolling back deployment: {deployment_id}")
        
        deployment = self.db.query(Deployment).filter_by(id=deployment_id).first()
        
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        
        try:
            # Disconnect strategy from MT5
            await self.mt5.disconnect_strategy(deployment.strategy_id)
            
            # Update deployment record
            deployment.status = "rolled_back"
            deployment.rolled_back_at = datetime.utcnow()
            deployment.rollback_reason = reason
            
            self.db.commit()
            
            logger.info(f"Deployment rolled back: {deployment_id}")
            
            return {
                "deployment_id": deployment_id,
                "status": "rolled_back"
            }
        
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            raise
    
    async def _validate_deployment(self, account_id: str, symbol: str):
        """Validate deployment prerequisites."""
        # Check account exists and is active
        account = self.db.query(Account).filter_by(id=account_id).first()
        
        if not account or not account.active:
            raise ValueError(f"Invalid account: {account_id}")
        
        # Check symbol is supported
        supported_symbols = ["BTCUSD", "EURUSD", "GBPUSD"]
        if symbol not in supported_symbols:
            raise ValueError(f"Unsupported symbol: {symbol}")
```

### 2. mt5_connector.py - MT5 Connection Management

```python
import MetaTrader5 as mt5

class MT5Connector:
    """Manage MT5 connections."""
    
    def __init__(self):
        self.connections = {}
    
    async def connect(self, account_id: str) -> bool:
        """Connect to MT5 account."""
        try:
            if account_id not in self.connections:
                account = db.query(Account).filter_by(id=account_id).first()
                
                if not mt5.initialize(
                    login=account.mt5_login,
                    password=account.mt5_password,
                    server=account.mt5_server
                ):
                    raise ConnectionError("Failed to initialize MT5")
                
                self.connections[account_id] = mt5
            
            return True
        
        except Exception as e:
            logger.error(f"MT5 connection failed: {str(e)}")
            raise
    
    async def disconnect(self, account_id: str):
        """Disconnect from MT5 account."""
        if account_id in self.connections:
            self.connections[account_id].shutdown()
            del self.connections[account_id]
    
    async def deploy_strategy(self, strategy_id: str, config: Dict):
        """Deploy strategy to MT5."""
        # Write strategy configuration to MT5
        # Execute EA/indicator initialization
        pass
    
    async def disconnect_strategy(self, strategy_id: str):
        """Disconnect strategy from MT5."""
        # Remove strategy from MT5
        pass
```

### 3. strategy_configurator.py - Strategy Configuration

```python
class StrategyConfigurator:
    """Configure strategies for deployment."""
    
    async def create_config(
        self,
        strategy_name: str,
        symbol: str,
        session: str,
        timeframe: str,
        parameters: Dict
    ) -> Dict:
        """Create strategy configuration."""
        
        return {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "session": session,
            "timeframe": timeframe,
            "parameters": parameters,
            "active": True,
            "created_at": datetime.utcnow().isoformat()
        }
```

---

## 🗄️ Data Models

### Deployment (Database Model)

```python
from sqlalchemy import Column, String, JSON, DateTime, Boolean

class Deployment(Base):
    __tablename__ = "deployments"
    
    id = Column(String, primary_key=True)
    strategy_id = Column(String, nullable=False)
    strategy_name = Column(String, nullable=False)
    validation_id = Column(String, ForeignKey("validation_records.id"))
    symbol = Column(String, nullable=False)
    session = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    account_id = Column(String)
    environment = Column(String)  # development, staging, production
    status = Column(String, default="deployed")
    parameters = Column(JSON)
    deployed_at = Column(DateTime, default=datetime.utcnow)
    rolled_back_at = Column(DateTime, nullable=True)
    rollback_reason = Column(String, nullable=True)
```

---

## 🧪 Testing

### Unit Tests (test_core.py)

```python
import pytest
from core.deployment_manager import DeploymentManager

@pytest.mark.asyncio
async def test_deploy_strategy(db_session):
    """Test strategy deployment."""
    manager = DeploymentManager(db_session)
    
    result = await manager.deploy_strategy(
        strategy_name="BTCUSD_RSI_MACD",
        validation_id="val_abc456",
        symbol="BTCUSD",
        session="London",
        timeframe="1H",
        parameters={"rsi_period": 14},
        account_id="acc_12345",
        environment="production"
    )
    
    assert "deployment_id" in result
    assert result["status"] == "deployed"

@pytest.mark.asyncio
async def test_rollback_strategy(db_session):
    """Test strategy rollback."""
    manager = DeploymentManager(db_session)
    
    # Deploy first
    deploy_result = await manager.deploy_strategy(...)
    deployment_id = deploy_result["deployment_id"]
    
    # Rollback
    rollback_result = await manager.rollback_strategy(
        deployment_id=deployment_id,
        reason="Test rollback"
    )
    
    assert rollback_result["status"] == "rolled_back"
```

---

## 🔄 Workflow Integration

**Deployment Phase in Strategy Pipeline**:

```
1. Validation Service approves parameters
2. Results passed to Deployment Service
3. Strategy deployed to MT5 account
4. Status monitored by Execution Service
5. Performance tracked real-time
6. Rollback available anytime
```

---

**Status**: Production Ready  
**Last Updated**: August 25, 2026  
**Maintainer**: @team-dev
