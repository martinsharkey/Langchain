# LOW LEVEL DESIGN - Optimization Service

**Service**: Parameter Optimization via Optuna  
**Port**: 8002  
**Technology**: Optuna, SciPy, NumPy, FastAPI  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready

---

## 📋 Service Overview

The Optimization Service tunes trading strategy parameters using Optuna's Bayesian optimization. For each indicator discovered by the Discovery Service, this service finds the optimal parameter values (e.g., RSI period, MACD periods, Bollinger Bands deviation) that maximize profit factor while maintaining acceptable risk metrics.

### Service Responsibilities
- ✅ Run Optuna optimization studies
- ✅ Find optimal parameters per indicator
- ✅ Constrain by risk limits (max drawdown, min profit factor)
- ✅ Track optimization history
- ✅ Generate optimization reports
- ✅ Store optimized parameters for validation

---

## 🏗️ Service Architecture

```
services/optimization-service/
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
│   ├── optimization_engine.py  # Main optimization logic
│   ├── optuna_manager.py       # Optuna study management
│   ├── objective_functions.py  # Optimization objectives
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

### POST /optimize/start
**Start an optimization study**

Request:
```json
{
  "discovery_task_id": "disc_abc123xyz",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "indicators": ["RSI", "MACD"],
  "n_trials": 100,
  "constraints": {
    "min_profit_factor": 1.5,
    "max_drawdown": -0.20
  }
}
```

Response:
```json
{
  "study_id": "opt_xyz789",
  "status": "running",
  "created_at": "2026-08-25T15:00:00Z"
}
```

### GET /optimize/status/{study_id}
**Check optimization progress**

Response:
```json
{
  "study_id": "opt_xyz789",
  "status": "in_progress",
  "completed_trials": 45,
  "total_trials": 100,
  "best_value": 2.8,
  "best_params": {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26
  }
}
```

### GET /optimize/results/{study_id}
**Get optimization results**

Response:
```json
{
  "study_id": "opt_xyz789",
  "status": "complete",
  "best_params": {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "rsi_threshold_buy": 35,
    "rsi_threshold_sell": 65
  },
  "best_metrics": {
    "profit_factor": 2.8,
    "win_rate": 0.65,
    "max_drawdown": -0.18,
    "score": 0.92
  },
  "trials": 100,
  "duration_seconds": 3600
}
```

### GET /health
**Health check**

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "optuna": "ready"
}
```

---

## 📦 Core Components

### 1. optimization_engine.py - Main Optimization Logic

```python
import logging
from typing import Dict, Any
import optuna
from core.optuna_manager import OptunaManager
from core.objective_functions import create_objective

logger = logging.getLogger(__name__)

class OptimizationEngine:
    """Main optimization engine."""
    
    def __init__(self, db_session):
        self.db = db_session
        self.optuna_manager = OptunaManager(db_session)
    
    async def run_optimization(
        self,
        discovery_task_id: str,
        symbol: str,
        session: str,
        timeframe: str,
        indicators: List[str],
        n_trials: int = 100,
        constraints: Dict = None
    ) -> Dict:
        """Run complete optimization study."""
        
        logger.info(f"Starting optimization: {symbol}/{session}/{timeframe}")
        
        # Create study
        study_id = await self.optuna_manager.create_study(
            discovery_task_id=discovery_task_id,
            symbol=symbol,
            session=session,
            timeframe=timeframe,
            n_trials=n_trials
        )
        
        # Get objective function
        objective_fn = create_objective(
            symbol=symbol,
            indicators=indicators,
            constraints=constraints or {}
        )
        
        try:
            # Create and optimize study
            study = optuna.create_study(
                direction="maximize",
                study_name=study_id,
                storage=self.optuna_manager.get_storage()
            )
            
            study.optimize(objective_fn, n_trials=n_trials)
            
            # Store best params
            best_params = study.best_params
            best_value = study.best_value
            
            await self.optuna_manager.store_results(
                study_id=study_id,
                best_params=best_params,
                best_value=best_value,
                trials=len(study.trials)
            )
            
            logger.info(f"Optimization complete: {study_id}")
            
            return {
                "study_id": study_id,
                "best_params": best_params,
                "best_value": best_value,
                "trials": len(study.trials)
            }
        
        except Exception as e:
            logger.error(f"Optimization failed: {str(e)}")
            await self.optuna_manager.mark_failed(study_id)
            raise
```

### 2. objective_functions.py - Optimization Objectives

```python
import numpy as np
from typing import Dict, List

def create_objective(
    symbol: str,
    indicators: List[str],
    constraints: Dict
) -> callable:
    """Create objective function for optimization."""
    
    def objective(trial: optuna.Trial) -> float:
        """Objective function to maximize."""
        
        # Suggest parameters based on indicators
        params = {}
        
        for indicator in indicators:
            if indicator == "RSI":
                params["rsi_period"] = trial.suggest_int("rsi_period", 5, 30)
                params["rsi_threshold_buy"] = trial.suggest_int("rsi_threshold_buy", 10, 40)
                params["rsi_threshold_sell"] = trial.suggest_int("rsi_threshold_sell", 60, 90)
            
            elif indicator == "MACD":
                params["macd_fast"] = trial.suggest_int("macd_fast", 5, 15)
                params["macd_slow"] = trial.suggest_int("macd_slow", 20, 35)
                params["macd_signal"] = trial.suggest_int("macd_signal", 5, 15)
            
            elif indicator == "Bollinger Bands":
                params["bb_period"] = trial.suggest_int("bb_period", 10, 30)
                params["bb_deviation"] = trial.suggest_float("bb_deviation", 1.0, 3.0)
        
        # Backtest with these parameters
        metrics = run_backtest_with_params(symbol, params)
        
        # Check constraints
        if metrics['profit_factor'] < constraints.get('min_profit_factor', 1.5):
            return -np.inf
        
        if metrics['max_drawdown'] < constraints.get('max_drawdown', -0.20):
            return -np.inf
        
        # Return composite score
        score = (
            0.4 * metrics['profit_factor'] +
            0.3 * metrics['win_rate'] +
            0.2 * (1 + metrics['max_drawdown']) +  # Less drawdown = higher score
            0.1 * (metrics['trades'] / 100)  # More trades = higher score
        )
        
        return score
    
    return objective
```

### 3. optuna_manager.py - Optuna Study Management

```python
import optuna
from optuna.storages import SQLAlchemyStorage

class OptunaManager:
    """Manage Optuna studies."""
    
    def __init__(self, db_session, db_url: str):
        self.db = db_session
        self.db_url = db_url
    
    def get_storage(self):
        """Get Optuna storage backend."""
        return SQLAlchemyStorage(
            url=self.db_url,
            engine_kwargs={"pool_pre_ping": True}
        )
    
    async def create_study(
        self,
        discovery_task_id: str,
        symbol: str,
        session: str,
        timeframe: str,
        n_trials: int
    ) -> str:
        """Create new optimization study."""
        study_id = f"opt_{symbol}_{session}_{timeframe}_{int(time.time())}"
        
        # Store in database
        study_record = OptimizationStudy(
            id=study_id,
            discovery_task_id=discovery_task_id,
            symbol=symbol,
            session=session,
            timeframe=timeframe,
            n_trials=n_trials,
            status="running"
        )
        
        self.db.add(study_record)
        self.db.commit()
        
        return study_id
    
    async def store_results(
        self,
        study_id: str,
        best_params: Dict,
        best_value: float,
        trials: int
    ):
        """Store optimization results."""
        study = self.db.query(OptimizationStudy).filter_by(id=study_id).first()
        
        if study:
            study.status = "complete"
            study.best_params = best_params
            study.best_value = best_value
            study.completed_trials = trials
            study.completed_at = datetime.utcnow()
            
            self.db.commit()
```

---

## 🗄️ Data Models

### OptimizationStudy (Database Model)

```python
from sqlalchemy import Column, String, Float, JSON, DateTime, Integer

class OptimizationStudy(Base):
    __tablename__ = "optimization_studies"
    
    id = Column(String, primary_key=True)
    discovery_task_id = Column(String, ForeignKey("discovery_tasks.id"))
    symbol = Column(String, nullable=False)
    session = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    status = Column(String, default="running")
    n_trials = Column(Integer)
    completed_trials = Column(Integer, default=0)
    best_params = Column(JSON)
    best_value = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

---

## 🧪 Testing

### Unit Tests (test_core.py)

```python
import pytest
from core.optimization_engine import OptimizationEngine

@pytest.fixture
def optimization_engine(db_session):
    return OptimizationEngine(db_session)

@pytest.mark.asyncio
async def test_optimization_run(optimization_engine):
    """Test optimization execution."""
    result = await optimization_engine.run_optimization(
        discovery_task_id="disc_abc123",
        symbol="BTCUSD",
        session="London",
        timeframe="1H",
        indicators=["RSI", "MACD"],
        n_trials=10
    )
    
    assert "study_id" in result
    assert "best_params" in result
    assert result["best_params"] is not None

def test_objective_function():
    """Test objective function creation."""
    from core.objective_functions import create_objective
    
    objective = create_objective(
        symbol="BTCUSD",
        indicators=["RSI"],
        constraints={"min_profit_factor": 1.5}
    )
    
    assert callable(objective)
```

### Integration Tests (test_api.py)

```python
@pytest.mark.asyncio
async def test_optimize_start(client):
    """Test optimization start endpoint."""
    response = await client.post(
        "/optimize/start",
        json={
            "discovery_task_id": "disc_abc123",
            "symbol": "BTCUSD",
            "session": "London",
            "timeframe": "1H",
            "indicators": ["RSI", "MACD"],
            "n_trials": 10
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "study_id" in data
    assert data["status"] == "running"

@pytest.mark.asyncio
async def test_optimize_results(client):
    """Test optimization results endpoint."""
    # Start optimization
    start_response = await client.post(
        "/optimize/start",
        json={
            "discovery_task_id": "disc_abc123",
            "symbol": "BTCUSD",
            "indicators": ["RSI"]
        }
    )
    study_id = start_response.json()["study_id"]
    
    # Wait for completion
    await asyncio.sleep(2)
    
    # Get results
    response = await client.get(f"/optimize/results/{study_id}")
    assert response.status_code == 200
```

---

## 🔄 Workflow Integration

**Optimization Phase in Strategy Pipeline**:

```
1. Discovery Service completes, identifies viable indicators
2. Results passed to Optimization Service
3. Optuna tests parameter combinations (100+ trials)
4. Best parameters selected based on profit factor + constraints
5. Results passed to Validation Service for walk-forward testing
```

---

## 📊 Performance Characteristics

- **Typical Optimization Time**: 1-2 hours (for 100 trials)
- **Trials Per Study**: 50-200
- **Memory Usage**: 4-8 GB per optimization
- **CPU Usage**: 100% (fully parallelized across trials)
- **Max Concurrent**: 2-3 studies (depends on hardware)

---

**Status**: Production Ready  
**Last Updated**: August 25, 2026  
**Maintainer**: @team-dev
