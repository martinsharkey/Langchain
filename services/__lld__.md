# LOW LEVEL DESIGN - services/ Module Overview

**Module**: Microservices  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active

---

## 📋 Module Overview

The `services/` directory contains all 6 independent microservices that form the core of the StrategyOps platform. Each service is a complete, self-contained application with its own API, business logic, and data models.

### Module Responsibilities
- ✅ Provide independent services
- ✅ Standardized service structure
- ✅ Clear API contracts
- ✅ Service-level documentation

---

## 🏗️ Standardized Service Architecture

Every service follows this structure:

```
services/{service-name}/
├── app/                     # API layer
│   ├── __init__.py
│   ├── main.py             # FastAPI application
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py       # API endpoints
│   │   └── schemas.py      # Request/response schemas
│   └── __lld__.md          # API design
│
├── core/                    # Business logic
│   ├── __init__.py
│   ├── engine.py           # Main engine/processor
│   ├── algorithms.py       # Algorithms and logic
│   └── __lld__.md          # Logic design
│
├── models/                  # Data models
│   ├── __init__.py
│   ├── database.py         # SQLAlchemy models
│   └── __lld__.md          # Data design
│
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_core.py
│   └── conftest.py
│
├── __lld__.md              # Service design
├── API_SPEC.md             # Service API specification
├── Dockerfile              # Container definition
├── requirements.txt        # Dependencies
└── README.md               # Service README
```

---

## 🔄 Services Overview

### 1. Discovery Service (Port 8001)
**Purpose**: Strategy discovery through backtesting  
**Technology**: VectorBT, NumPy, Pandas  
**Key Files**:
- `app/api/routes.py` - `/discover/start`, `/discover/status`, `/discover/results`
- `core/discovery_engine.py` - Backtesting engine
- `__lld__.md` - Service design details

### 2. Optimization Service (Port 8002)
**Purpose**: Parameter optimization  
**Technology**: Optuna, SciPy  
**Key Files**:
- `app/api/routes.py` - `/optimize/start`, `/optimize/status`, `/optimize/results`
- `core/optuna_optimizer.py` - Optimization engine
- `__lld__.md` - Service design details

### 3. Validation Service (Port 8003)
**Purpose**: Walk-forward validation  
**Technology**: VectorBT, Statistical Analysis  
**Key Files**:
- `app/api/routes.py` - `/validate/walkforward`, `/validate/results`
- `core/validation_engine.py` - Validation logic
- `__lld__.md` - Service design details

### 4. Deployment Service (Port 8004)
**Purpose**: Live strategy deployment  
**Technology**: MT5 Integration, Configuration  
**Key Files**:
- `app/api/routes.py` - `/deploy/strategy`, `/deploy/status`, `/deploy/rollback`
- `core/deployment_manager.py` - Deployment logic
- `__lld__.md` - Service design details

### 5. Orchestration Service (Port 8005)
**Purpose**: Workflow coordination  
**Technology**: Celery, Redis, State Management  
**Key Files**:
- `app/api/routes.py` - `/workflows/start`, `/workflows/status`
- `core/orchestrator.py` - Workflow coordination
- `__lld__.md` - Service design details

### 6. Execution Service (Port 8006)
**Purpose**: Live trade execution  
**Technology**: MT5 API, Real-time Data  
**Key Files**:
- `app/api/routes.py` - `/execute/trade`, `/execute/positions`
- `core/execution_engine.py` - Trade execution
- `__lld__.md` - Service design details

---

## 📋 Service Development Standards

### 1. Project Structure
Each service MUST follow the standardized structure exactly.

### 2. API Specification
Each service MUST have:
- `API_SPEC.md` documenting all endpoints
- OpenAPI/Swagger documentation
- Request/response examples

### 3. Documentation
Each service MUST have:
- `__lld__.md` - Service design
- `app/__lld__.md` - API design
- `core/__lld__.md` - Logic design
- `models/__lld__.md` - Data design

### 4. Health Checks
Each service MUST provide:
- `GET /health` endpoint
- Database health check
- External dependency health checks

### 5. Logging
Each service MUST use:
- Structured JSON logging
- Log levels: DEBUG, INFO, WARNING, ERROR
- Correlation IDs for tracing

### 6. Error Handling
Each service MUST:
- Return consistent error responses
- Include error codes and messages
- Log all errors with context

### 7. Testing
Each service MUST have:
- Unit tests (tests/test_core.py)
- Integration tests (tests/test_api.py)
- 80%+ code coverage
- Fixtures in conftest.py

---

## 🔗 Service Communication

### Service-to-Service Calls
```python
import httpx

async def call_discovery_service(symbol: str) -> dict:
    """Call discovery service."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://discovery-service:8001/discover/start",
            json={"symbol": symbol},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
```

### Common Response Format
```python
{
    "task_id": "disc_abc123",
    "status": "queued|in_progress|complete|failed",
    "data": {...},
    "error": None
}
```

---

## 🚀 Service Deployment

Each service can be deployed independently:

```bash
# Build service image
docker build -f services/discovery-service/Dockerfile \
  -t langchain-discovery-service:1.0.0 \
  services/discovery-service

# Run service
docker run -p 8001:8001 \
  -e DATABASE_URL=postgresql://... \
  langchain-discovery-service:1.0.0
```

---

## 📊 Service Scaling

Each service can be scaled independently:

```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: discovery-service
spec:
  replicas: 3
  autoscaling:
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

---

## 🧪 Service Testing

Each service has its own test suite:

```bash
cd services/discovery-service

# Run unit tests
pytest tests/test_core.py -v

# Run integration tests
pytest tests/test_api.py -v

# Run with coverage
pytest --cov=app --cov=core tests/

# Run specific test
pytest tests/test_api.py::TestDiscoveryAPI::test_start_discovery -v
```

---

## 📞 Creating a New Service

1. Copy existing service structure to `services/new-service/`
2. Update `service_name` in code
3. Update port number (8007+)
4. Create `__lld__.md` files
5. Create `API_SPEC.md`
6. Implement core logic
7. Add tests
8. Update docker-compose.yml
9. Update infrastructure/k8s/

---

**Status**: Active  
**All Services**: Production Ready
