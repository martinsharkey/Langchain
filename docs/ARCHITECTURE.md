# Architecture Documentation

## System Overview

StrategyOps v2.0 is a microservices-based platform for algorithmic trading strategy discovery, optimization, validation, and deployment. The system is built using a service-oriented architecture with 7 independent services communicating via HTTP APIs.

---

## Microservices Architecture

### Core Services (6 active services)

#### 1. **Discovery Service** (Port 8001)
**Purpose**: Strategy and indicator discovery through historical backtesting

**Responsibilities**:
- Execute vectorbt backtests across multiple timeframes
- Identify profitable indicators and their combinations
- Generate discovery reports with performance metrics
- Support per-symbol and per-session strategy discovery

**Technology Stack**:
- Python 3.10+
- FastAPI
- VectorBT for backtesting
- NumPy/Pandas for data processing

**Key Endpoints**:
```
POST   /discover/start           - Start discovery for symbol/session
GET    /discover/status/{task_id} - Check discovery progress
GET    /discover/results/{task_id} - Retrieve discovery results
POST   /discover/stop/{task_id}   - Cancel active discovery
```

---

#### 2. **Optimization Service** (Port 8002)
**Purpose**: Parameter optimization using Optuna

**Responsibilities**:
- Optimize discovered indicator parameters using Optuna
- Support multiple optimization algorithms
- Per-session parameter tuning
- Integration with vectorbt for validation

**Technology Stack**:
- Python 3.10+
- FastAPI
- Optuna for hyperparameter optimization
- Integration with Discovery Service

**Key Endpoints**:
```
POST   /optimize/start           - Start parameter optimization
GET    /optimize/status/{task_id} - Check optimization progress
GET    /optimize/results/{task_id} - Retrieve optimized parameters
POST   /optimize/stop/{task_id}   - Cancel active optimization
```

---

#### 3. **Validation Service** (Port 8003)
**Purpose**: Walk-forward validation and performance analysis

**Responsibilities**:
- Perform walk-forward validation on optimized parameters
- Generate detailed performance reports
- Verify profitability improvements (PF increase)
- Support before/after comparison analysis

**Technology Stack**:
- Python 3.10+
- FastAPI
- VectorBT validation engine
- Statistical analysis tools

**Key Endpoints**:
```
POST   /validate/walkforward      - Start walk-forward validation
GET    /validate/status/{task_id} - Check validation progress
GET    /validate/results/{task_id} - Retrieve validation results
POST   /validate/compare          - Compare parameter sets
```

---

#### 4. **Deployment Service** (Port 8004)
**Purpose**: Strategy deployment to live trading

**Responsibilities**:
- Deploy validated strategies to live trading
- Manage strategy versions and rollbacks
- Configure per-session deployment parameters
- Monitor deployment health and status

**Technology Stack**:
- Python 3.10+
- FastAPI
- MT5 integration for live trading
- Configuration management

**Key Endpoints**:
```
POST   /deploy/strategy          - Deploy strategy to live trading
GET    /deploy/status/{strategy_id} - Check deployment status
POST   /deploy/rollback/{version} - Rollback to previous version
GET    /deploy/active            - List active deployments
```

---

#### 5. **Orchestration Service** (Port 8005)
**Purpose**: Workflow coordination and task orchestration

**Responsibilities**:
- Coordinate multi-service workflows
- Manage discovery → optimization → validation → deployment pipelines
- Handle task queuing and dependencies
- Provide workflow status and reporting

**Technology Stack**:
- Python 3.10+
- FastAPI
- Celery for task distribution
- Redis for state management

**Key Endpoints**:
```
POST   /workflows/start          - Start complete pipeline
GET    /workflows/status/{workflow_id} - Check workflow progress
GET    /workflows/results/{workflow_id} - Get final results
POST   /workflows/cancel/{workflow_id} - Cancel workflow
```

---

#### 6. **Execution Service** (Port 8006)
**Purpose**: Live trade execution and monitoring

**Responsibilities**:
- Execute trades based on signal generation
- Manage risk controls and position sizing
- Monitor live trading performance
- Generate execution logs and reports

**Technology Stack**:
- Python 3.10+
- FastAPI
- MT5 trading API
- Real-time data streaming

**Key Endpoints**:
```
POST   /execute/trade            - Execute trade
GET    /execute/positions        - Get current positions
POST   /execute/close/{position_id} - Close position
GET    /execute/performance      - Get trading performance
```

---

#### 7. **Auth Service** (Port 8007)
**Purpose**: Authentication and authorization (optional)

**Responsibilities**:
- User authentication
- API key management
- Permission enforcement
- Session management

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User/Client Interface                     │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────▼────────────┐
            │  API Gateway (Port 8000)│
            └────────────┬────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
    ┌────────┐      ┌────────┐      ┌────────┐
    │Discovery│      │Optimize│      │Validate│
    │Service  │      │Service │      │Service │
    │(8001)   │      │(8002)  │      │(8003)  │
    └────┬────┘      └────┬───┘      └────┬───┘
         │                │               │
         └────────────────┼───────────────┘
                          │
         ┌────────────────┼──────────────┐
         │                │              │
         ▼                ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │Orchestrat│   │Deploymen │   │Execution │
    │Service   │   │Service   │   │Service   │
    │(8005)    │   │(8004)    │   │(8006)    │
    └──────────┘   └──────────┘   └──────────┘
         │                │              │
         └────────────────┼──────────────┘
                          │
            ┌─────────────▼──────────┐
            │  Mt5 Trading Platform  │
            └────────────────────────┘
```

---

## Communication Patterns

### Synchronous (REST API)
- Service-to-service HTTP calls
- Discovery → Optimization requests
- Validation → Deployment checks
- Status and result queries

### Asynchronous (Event-Driven)
- Task queuing (Celery)
- Workflow status updates
- Completion notifications
- Error handling

---

## Data Models

### Strategy Configuration
```python
{
    "symbol": "BTCUSD",
    "session": "London",
    "timeframe": "M15",
    "indicators": ["Bollinger_Bands", "OsMA"],
    "parameters": {
        "bb_period": 20,
        "bb_deviation": 2,
        "osma_fast": 12,
        "osma_slow": 26
    },
    "performance_metrics": {
        "profit_factor": 1.45,
        "win_rate": 0.62,
        "drawdown": -0.15
    }
}
```

### Workflow State
```python
{
    "workflow_id": "wf_abc123",
    "status": "discovery",
    "stages": {
        "discovery": {"status": "complete", "results": {...}},
        "optimization": {"status": "in_progress", "progress": 0.45},
        "validation": {"status": "pending"},
        "deployment": {"status": "pending"}
    },
    "created_at": "2026-08-25T10:00:00Z",
    "updated_at": "2026-08-25T11:30:00Z"
}
```

---

## Database Schema

### Core Tables

#### strategies
```sql
- id (PK)
- name
- symbol
- session
- timeframe
- indicators
- parameters (JSON)
- performance_metrics (JSON)
- status
- created_at
- updated_at
```

#### optimization_runs
```sql
- id (PK)
- strategy_id (FK)
- optimizer_type
- parameters (JSON)
- results (JSON)
- status
- started_at
- completed_at
```

#### validation_results
```sql
- id (PK)
- optimization_run_id (FK)
- validation_type
- metrics (JSON)
- passed
- created_at
```

#### deployments
```sql
- id (PK)
- strategy_id (FK)
- version
- environment
- status
- deployed_at
- deployed_by
```

---

## Deployment Architecture

### Docker Compose (Development)
- 6 microservices in containers
- PostgreSQL database
- Redis cache/queue
- Nginx reverse proxy
- Prometheus monitoring

### Kubernetes (Production)
- Service mesh (future)
- Auto-scaling
- Load balancing
- Self-healing
- Rolling updates

---

## Service Dependencies

```
discovery-service
  ├── No service dependencies
  └── Data: Historical OHLCV data, indicators

optimization-service
  ├── Depends on: discovery-service (for baseline discovery)
  └── Data: Discovery results, optimization algorithms

validation-service
  ├── Depends on: discovery-service, optimization-service
  └── Data: Optimized parameters, historical data

deployment-service
  ├── Depends on: validation-service
  └── Data: Validated parameters, MT5 configuration

orchestration-service
  ├── Depends on: All services
  └── Responsibility: Coordination and workflow management

execution-service
  ├── Depends on: deployment-service (for strategy parameters)
  └── Data: Live market data, position information
```

---

## Performance Characteristics

### Discovery Service
- Processing time: 5-30 minutes per symbol/timeframe
- Backtest period: Configurable (default: 1 year)
- Parallelization: Multi-threading within vectorbt

### Optimization Service
- Study duration: 30-120 minutes
- Trials per study: 50-500 (configurable)
- Parallelization: Multi-processing

### Validation Service
- Walk-forward window: 3-6 months
- Computation time: 5-15 minutes
- Memory usage: Depends on data volume

### Execution Service
- Trade execution latency: <100ms
- Market data update frequency: Real-time
- Position monitoring: Continuous

---

## Scalability Strategy

### Horizontal Scaling
- Discovery service: Scale by symbol/timeframe distribution
- Optimization service: Scale by strategy distribution
- Validation service: Scale by result volume
- Execution service: Multi-instance load balancing

### Vertical Scaling
- Increase CPU/memory for large backtests
- Optimize database queries for large result sets
- Cache frequently accessed data

---

## Security Architecture

### API Authentication
- JWT tokens for authentication
- API keys for service-to-service calls
- Rate limiting per user/key

### Data Protection
- TLS for all inter-service communication
- Encrypted database connections
- Secrets management (environment variables)

### Access Control
- Role-based access control (RBAC)
- Service-to-service authorization
- Audit logging

---

## Monitoring and Observability

### Metrics
- Service health (CPU, memory, response time)
- Business metrics (discovery success rate, optimization convergence)
- Performance metrics (P95 latency, error rate)

### Logging
- Structured logging (JSON)
- Centralized log aggregation
- Debug/info/warning/error levels

### Tracing
- Distributed tracing across services
- Request correlation IDs
- Performance bottleneck identification

---

**Document Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready
