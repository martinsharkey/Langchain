# LOW LEVEL DESIGN - Orchestration Service

**Service**: Workflow Coordination & Orchestration  
**Port**: 8005  
**Technology**: Celery, Redis, State Management, FastAPI  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready

---

## 📋 Service Overview

The Orchestration Service coordinates the entire strategy development and deployment workflow. It manages task scheduling, state transitions, error handling, and service communication to ensure smooth progression from discovery through live trading.

### Service Responsibilities
- ✅ Coordinate workflow steps
- ✅ Manage task scheduling
- ✅ Handle state transitions
- ✅ Error handling and retries
- ✅ Service communication
- ✅ Workflow monitoring
- ✅ Pipeline status tracking

---

## 🏗️ Service Architecture

```
services/orchestration-service/
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
│   ├── orchestrator.py         # Main orchestration logic
│   ├── workflow_manager.py     # Workflow management
│   ├── state_machine.py        # State transitions
│   ├── service_caller.py       # Service communication
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

### POST /workflows/start
**Start a complete strategy pipeline**

Request:
```json
{
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "start_date": "2024-01-01",
  "end_date": "2026-08-25",
  "target_account": "acc_12345"
}
```

Response:
```json
{
  "workflow_id": "wf_abc123",
  "status": "started",
  "current_step": "discovery",
  "created_at": "2026-08-25T15:00:00Z"
}
```

### GET /workflows/status/{workflow_id}
**Check workflow progress**

Response:
```json
{
  "workflow_id": "wf_abc123",
  "status": "in_progress",
  "current_step": "optimization",
  "progress": 35,
  "steps": [
    {
      "name": "discovery",
      "status": "complete",
      "task_id": "disc_xyz",
      "completed_at": "2026-08-25T15:45:00Z"
    },
    {
      "name": "optimization",
      "status": "in_progress",
      "task_id": "opt_xyz",
      "progress": 45
    },
    {
      "name": "validation",
      "status": "pending"
    },
    {
      "name": "deployment",
      "status": "pending"
    }
  ]
}
```

### GET /workflows/results/{workflow_id}
**Get complete workflow results**

Response:
```json
{
  "workflow_id": "wf_abc123",
  "status": "complete",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "results": {
    "discovered_indicators": ["RSI", "MACD"],
    "best_parameters": {"rsi_period": 14},
    "validation_approved": true,
    "deployed_strategy_id": "strat_123456"
  },
  "total_duration_seconds": 7200,
  "completed_at": "2026-08-25T17:00:00Z"
}
```

### GET /health
**Health check**

Response:
```json
{
  "status": "healthy",
  "redis": "connected",
  "celery": "ready",
  "services": {
    "discovery": "online",
    "optimization": "online",
    "validation": "online",
    "deployment": "online"
  }
}
```

---

## 📦 Core Components

### 1. orchestrator.py - Main Orchestration Logic

```python
import logging
from typing import Dict
from core.workflow_manager import WorkflowManager
from core.state_machine import StateMachine
from core.service_caller import ServiceCaller

logger = logging.getLogger(__name__)

class Orchestrator:
    """Main orchestration engine."""
    
    def __init__(self, db_session, redis_client):
        self.db = db_session
        self.redis = redis_client
        self.workflow_mgr = WorkflowManager(db_session)
        self.state_machine = StateMachine()
        self.service_caller = ServiceCaller()
    
    async def start_workflow(
        self,
        symbol: str,
        session: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        target_account: str
    ) -> Dict:
        """Start complete strategy pipeline."""
        
        logger.info(f"Starting workflow: {symbol}/{session}/{timeframe}")
        
        # Create workflow record
        workflow_id = f"wf_{symbol}_{session}_{timeframe}_{int(time.time())}"
        
        workflow = Workflow(
            id=workflow_id,
            symbol=symbol,
            session=session,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            target_account=target_account,
            status="started"
        )
        
        self.db.add(workflow)
        self.db.commit()
        
        # Start discovery phase
        try:
            discovery_result = await self.service_caller.call_discovery(
                symbol=symbol,
                session=session,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )
            
            # Store discovery task
            workflow.discovery_task_id = discovery_result["task_id"]
            workflow.status = "discovery_running"
            self.db.commit()
            
            # Schedule optimization phase to run after discovery
            await self._schedule_next_phase(workflow_id, "optimization")
            
            logger.info(f"Workflow started: {workflow_id}")
            
            return {
                "workflow_id": workflow_id,
                "status": "started",
                "current_step": "discovery"
            }
        
        except Exception as e:
            logger.error(f"Workflow start failed: {str(e)}")
            workflow.status = "failed"
            workflow.error_message = str(e)
            self.db.commit()
            raise
    
    async def check_status(self, workflow_id: str) -> Dict:
        """Check workflow status."""
        
        workflow = self.db.query(Workflow).filter_by(id=workflow_id).first()
        
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        steps = []
        
        # Check discovery
        if workflow.discovery_task_id:
            discovery_status = await self.service_caller.get_discovery_status(
                workflow.discovery_task_id
            )
            steps.append({
                "name": "discovery",
                "status": discovery_status["status"],
                "task_id": workflow.discovery_task_id
            })
        
        # Check optimization
        if workflow.optimization_study_id:
            opt_status = await self.service_caller.get_optimization_status(
                workflow.optimization_study_id
            )
            steps.append({
                "name": "optimization",
                "status": opt_status["status"],
                "task_id": workflow.optimization_study_id
            })
        
        # Similar for validation and deployment...
        
        return {
            "workflow_id": workflow_id,
            "status": workflow.status,
            "current_step": self._get_current_step(workflow),
            "steps": steps
        }
    
    async def _schedule_next_phase(self, workflow_id: str, next_phase: str):
        """Schedule next workflow phase."""
        # Use Celery to schedule next task
        from celery import current_app
        
        current_app.send_task(
            f'tasks.run_{next_phase}',
            args=(workflow_id,),
            countdown=5  # Start after 5 seconds
        )
    
    def _get_current_step(self, workflow) -> str:
        """Get current workflow step."""
        if workflow.status == "discovery_running":
            return "discovery"
        elif workflow.status == "optimization_running":
            return "optimization"
        elif workflow.status == "validation_running":
            return "validation"
        elif workflow.status == "deployment_running":
            return "deployment"
        return "completed"
```

### 2. workflow_manager.py - Workflow Management

```python
class WorkflowManager:
    """Manage workflow state and transitions."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def transition_state(
        self,
        workflow_id: str,
        new_status: str,
        task_result: Dict = None
    ):
        """Transition workflow to new state."""
        
        workflow = self.db.query(Workflow).filter_by(id=workflow_id).first()
        
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        # Update status
        workflow.status = new_status
        
        # Store results if provided
        if task_result:
            if "discovery" in new_status:
                workflow.discovery_result = task_result
            elif "optimization" in new_status:
                workflow.optimization_result = task_result
            elif "validation" in new_status:
                workflow.validation_result = task_result
            elif "deployment" in new_status:
                workflow.deployment_result = task_result
        
        self.db.commit()
```

### 3. service_caller.py - Service Communication

```python
import httpx
from typing import Dict

class ServiceCaller:
    """Call other services."""
    
    async def call_discovery(
        self,
        symbol: str,
        session: str,
        timeframe: str,
        start_date: str,
        end_date: str
    ) -> Dict:
        """Call Discovery Service."""
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://discovery-service:8001/discover/start",
                json={
                    "symbol": symbol,
                    "session": session,
                    "timeframe": timeframe,
                    "start_date": start_date,
                    "end_date": end_date
                },
                timeout=30.0
            )
            
            response.raise_for_status()
            return response.json()
    
    async def get_discovery_status(self, task_id: str) -> Dict:
        """Get discovery status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://discovery-service:8001/discover/status/{task_id}",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    # Similar methods for optimization, validation, deployment...
```

---

## 🗄️ Data Models

### Workflow (Database Model)

```python
from sqlalchemy import Column, String, JSON, DateTime

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    session = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_date = Column(String)
    end_date = Column(String)
    target_account = Column(String)
    
    status = Column(String, default="started")
    
    discovery_task_id = Column(String)
    optimization_study_id = Column(String)
    validation_id = Column(String)
    deployment_id = Column(String)
    
    discovery_result = Column(JSON)
    optimization_result = Column(JSON)
    validation_result = Column(JSON)
    deployment_result = Column(JSON)
    
    error_message = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

---

## 🧪 Testing

### Unit Tests (test_core.py)

```python
import pytest
from core.orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_workflow_start(db_session, redis_client):
    """Test workflow start."""
    orchestrator = Orchestrator(db_session, redis_client)
    
    result = await orchestrator.start_workflow(
        symbol="BTCUSD",
        session="London",
        timeframe="1H",
        start_date="2024-01-01",
        end_date="2026-08-25",
        target_account="acc_12345"
    )
    
    assert "workflow_id" in result
    assert result["status"] == "started"

@pytest.mark.asyncio
async def test_workflow_status(db_session, redis_client):
    """Test workflow status check."""
    orchestrator = Orchestrator(db_session, redis_client)
    
    result = await orchestrator.start_workflow(...)
    workflow_id = result["workflow_id"]
    
    status = await orchestrator.check_status(workflow_id)
    
    assert status["workflow_id"] == workflow_id
    assert "steps" in status
```

---

## 🔄 Workflow Phases

**Complete Pipeline**:

```
1. DISCOVERY (30-60 min)
   ├── Backtest indicators
   ├── Rank by performance
   └── Pass to optimization

2. OPTIMIZATION (1-2 hours)
   ├── Tune parameters
   ├── Constrain by risk limits
   └── Pass to validation

3. VALIDATION (30-60 min)
   ├── Walk-forward validation
   ├── Detect overfitting
   └── Approve/Reject

4. DEPLOYMENT (5 min)
   ├── Connect to MT5
   ├── Deploy strategy
   └── Monitor execution

TOTAL TIME: 3-5 hours from start to live trading
```

---

**Status**: Production Ready  
**Last Updated**: August 25, 2026  
**Maintainer**: @team-dev
