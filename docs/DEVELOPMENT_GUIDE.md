# Development Guide

Complete guide for setting up, developing, testing, and deploying StrategyOps v2.0.

---

## Prerequisites

### System Requirements
- **OS**: Windows 10/11, macOS 11+, or Linux (Ubuntu 20.04+)
- **Docker Desktop**: Latest version with WSL 2 (Windows) or native (Mac/Linux)
- **Python**: 3.10 or higher
- **Node.js**: 18+ (for dashboard)
- **Git**: Latest version
- **RAM**: Minimum 8GB (16GB recommended)
- **Disk**: 50GB free space

### Required Software
```bash
# macOS
brew install docker python@3.10 nodejs git

# Ubuntu/WSL
sudo apt-get install docker.io python3.10 python3.10-dev nodejs git

# Windows (with Chocolatey)
choco install docker-desktop python nodejs git
```

---

## Environment Setup

### 1. Clone Repository
```bash
git clone https://github.com/martinsharkey/Langchain.git
cd langchain/langchain
```

### 2. Copy Environment Files
```bash
cp .env.example .env
```

**Edit `.env` with your configuration**:
```ini
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/strategyops
REDIS_URL=redis://localhost:6379

# MT5 Configuration
MT5_LOGIN=your_mt5_login
MT5_PASSWORD=your_mt5_password
MT5_SERVER=your_mt5_server

# API Configuration
API_PORT=8000
LOG_LEVEL=INFO

# Monitoring
PROMETHEUS_ENABLED=true
JAEGER_ENABLED=true
```

### 3. Docker Setup

**Start all services**:
```bash
docker compose up -d
```

**Verify services are running**:
```bash
docker compose ps
```

**Expected output**:
```
NAME                    STATUS
discovery-service       Up (healthy)
optimization-service    Up (healthy)
validation-service      Up (healthy)
deployment-service      Up (healthy)
orchestration-service   Up (healthy)
execution-service       Up (healthy)
postgres                Up (healthy)
redis                   Up (healthy)
```

### 4. Initialize Database
```bash
docker compose exec postgres psql -U postgres -d strategyops -f init-db.sql
```

---

## Project Structure

```
langchain/
├── services/                    # Microservices
│   ├── discovery-service/       # Strategy discovery
│   ├── optimization-service/    # Parameter optimization
│   ├── validation-service/      # Walk-forward validation
│   ├── deployment-service/      # Live deployment
│   ├── orchestration-service/   # Workflow coordination
│   └── execution-service/       # Trade execution
│
├── dashboard/                   # Backend API for UI
│   ├── app/
│   ├── core/
│   └── tests/
│
├── dashboard-frontend/          # React UI
│   ├── src/
│   ├── public/
│   └── package.json
│
├── src/                         # Shared source code
│   ├── models/                  # Data models
│   ├── schemas/                 # API schemas
│   ├── utils/                   # Utilities
│   └── integrations/            # External integrations
│
├── tests/                       # Test suite
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   ├── e2e/                     # End-to-end tests
│   └── performance/             # Performance tests
│
├── docs/                        # Documentation
├── infrastructure/              # Docker, k8s configs
├── tools/                       # Utility scripts
└── archive/                     # Legacy code
```

---

## Local Development

### Starting Individual Services

**Discovery Service**:
```bash
cd services/discovery-service
python -m uvicorn app.main:app --reload --port 8001
```

**Optimization Service**:
```bash
cd services/optimization-service
python -m uvicorn app.main:app --reload --port 8002
```

**Dashboard Frontend**:
```bash
cd dashboard-frontend
npm install
npm start  # Runs on http://localhost:3000
```

### Using Make Commands (Recommended)

**See all commands**:
```bash
make help
```

**Common development commands**:
```bash
make dev              # Start all services
make logs            # View all service logs
make test            # Run full test suite
make lint            # Run code linting
make format          # Format code
```

---

## Development Workflow

### Creating a New Feature

#### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
```

#### 2. Edit Service Code

**Example: Adding endpoint to Discovery Service**:

```python
# services/discovery-service/app/api.py
from fastapi import APIRouter, HTTPException
from ..core import discovery_engine

router = APIRouter(prefix="/discover", tags=["discovery"])

@router.post("/start")
async def start_discovery(config: DiscoveryConfig):
    """Start strategy discovery process"""
    try:
        task_id = discovery_engine.discover(
            symbol=config.symbol,
            session=config.session,
            timeframe=config.timeframe,
            indicators=config.indicators
        )
        return {"task_id": task_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### 3. Write Tests

```python
# services/discovery-service/tests/test_discovery_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture
def discovery_config():
    return {
        "symbol": "BTCUSD",
        "session": "London",
        "timeframe": "M15",
        "indicators": ["Bollinger_Bands", "OsMA"]
    }

def test_start_discovery(discovery_config):
    response = client.post("/discover/start", json=discovery_config)
    assert response.status_code == 202
    assert "task_id" in response.json()
    assert response.json()["status"] == "queued"

def test_invalid_config():
    invalid_config = {"symbol": ""}  # Missing required fields
    response = client.post("/discover/start", json=invalid_config)
    assert response.status_code == 422  # Validation error
```

#### 4. Test Locally

```bash
# Run tests for specific service
cd services/discovery-service
pytest -v

# Run with coverage
pytest --cov=app tests/
```

#### 5. Format and Lint

```bash
# Format code
black .
isort .

# Check linting
flake8 .
pylint app/
```

#### 6. Commit and Push

```bash
git add .
git commit -m "feat: add new discovery endpoint"
git push origin feature/your-feature-name
```

---

## Testing

### Unit Tests

**Run all unit tests**:
```bash
pytest tests/unit/ -v
```

**Run specific test**:
```bash
pytest tests/unit/test_discovery.py::test_start_discovery -v
```

**With coverage**:
```bash
pytest tests/unit/ --cov=src --cov-report=html
```

### Integration Tests

**Run integration tests**:
```bash
pytest tests/integration/ -v

# Must have Docker services running
docker compose up -d
pytest tests/integration/ -v
```

### End-to-End Tests

**Run full pipeline**:
```bash
pytest tests/e2e/ -v

# Runs complete discovery → optimization → validation → deployment workflow
```

### Performance Tests

**Run performance benchmarks**:
```bash
pytest tests/performance/ -v --benchmark-only
```

---

## Code Style and Standards

### Python Code Style

**Follow PEP 8** with the following configurations:

**pyproject.toml**:
```toml
[tool.black]
line-length = 100
target-version = ["py310"]

[tool.isort]
profile = "black"
line_length = 100

[tool.pylint]
max-line-length = 100
disable = ["C0111", "R0913"]
```

### Type Hints

**Use type hints for all functions**:
```python
from typing import Dict, List, Optional
from models import DiscoveryResult

def process_discovery(
    results: List[DiscoveryResult],
    filter_pf: Optional[float] = None
) -> Dict[str, DiscoveryResult]:
    """Process discovery results with optional filtering"""
    ...
```

### Documentation

**Use docstrings for all modules, classes, and functions**:
```python
def calculate_profit_factor(trades: List[Trade]) -> float:
    """
    Calculate profit factor from trade list.
    
    Args:
        trades: List of Trade objects with pnl values
        
    Returns:
        float: Profit factor (gross profit / gross loss)
        
    Raises:
        ValueError: If no trades provided
        
    Examples:
        >>> trades = [Trade(pnl=100), Trade(pnl=-50)]
        >>> calculate_profit_factor(trades)
        2.0
    """
    ...
```

---

## Debugging

### View Service Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f discovery-service

# Last 100 lines
docker compose logs --tail=100 discovery-service
```

### Enable Debug Mode

**Set in .env**:
```ini
LOG_LEVEL=DEBUG
```

### Python Debugger

```python
import pdb

def debug_discovery():
    pdb.set_trace()  # Execution pauses here
    # Inspect variables in interactive debugger
```

### VS Code Debugging

**Create `.vscode/launch.json`**:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Discovery Service",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--port", "8001"
      ],
      "jinja": true,
      "cwd": "${workspaceFolder}/services/discovery-service"
    }
  ]
}
```

---

## Common Development Tasks

### Adding a New Microservice

1. **Create service directory**:
```bash
mkdir -p services/new-service/{app,core,tests}
```

2. **Create basic structure**:
```bash
# app/__init__.py
# app/main.py (FastAPI application)
# app/api.py (Endpoints)
# core/engine.py (Business logic)
# requirements.txt
# Dockerfile
# tests/__init__.py
```

3. **Create Dockerfile**:
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
```

4. **Update docker-compose.yml**:
```yaml
services:
  new-service:
    build: ./services/new-service
    ports:
      - "8007:8007"
    environment:
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Running Load Tests

```bash
# Install load testing tool
pip install locust

# Create locustfile.py
# Run tests
locust -f locustfile.py --host=http://localhost:8001
```

---

## Troubleshooting

### Services Won't Start

**Check logs**:
```bash
docker compose logs discovery-service
```

**Restart services**:
```bash
docker compose down
docker compose up -d
```

### Port Conflicts

**Find process using port**:
```bash
# Linux/Mac
lsof -i :8001

# Windows
netstat -ano | findstr :8001
```

**Kill process**:
```bash
kill -9 <PID>  # Linux/Mac
taskkill /PID <PID> /F  # Windows
```

### Database Connection Issues

**Check database status**:
```bash
docker compose logs postgres
```

**Reset database**:
```bash
docker compose down
docker compose up -d postgres
docker compose exec postgres psql -U postgres -d strategyops -f init-db.sql
```

### Out of Memory

**Increase Docker resources**:
1. Open Docker Desktop settings
2. Resources → Memory: Increase to 8GB+
3. Restart Docker

---

## Continuous Integration

### GitHub Actions Workflow

**`.github/workflows/ci.yml`**:
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ --cov
      - run: black --check .
      - run: flake8 .
```

---

## Performance Optimization Tips

1. **Use async/await** for I/O operations:
```python
async def fetch_data(self):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

2. **Cache frequently accessed data**:
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_indicator_values(symbol: str, period: int):
    ...
```

3. **Use connection pooling** for database:
```python
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40
)
```

4. **Profile code**:
```bash
python -m cProfile -s cumulative app.py
```

---

**Guide Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready
