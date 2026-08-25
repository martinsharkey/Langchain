# StrategyOps V2.0 - Microservices Architecture

This is the microservices implementation of StrategyOps, refactored from the monolithic v1.0 codebase.

## Quick Start

### Prerequisites
- Docker & Docker Compose 20.10+
- Python 3.11+
- 2GB RAM minimum

### Launch Services

```bash
# Build and start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Check API Gateway health
curl http://localhost:8000/health
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f discovery-service
docker-compose logs -f optimization-service
docker-compose logs -f validation-service
```

### Stop Services

```bash
docker-compose down
```

---

## Services

### 1. Discovery Service (Port 8001)
Finds profitable strategies for a given symbol/session/timeframe.

**Key Endpoints:**
- `POST /api/v1/discovery/start` - Start discovery job
- `GET /api/v1/discovery/{job_id}/status` - Get job status
- `GET /api/v1/discovery/{job_id}/results` - Get discovered strategies
- `GET /api/v1/discovery/strategies` - List available strategies

**Example:**
```bash
curl -X POST http://localhost:8001/api/v1/discovery/start \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "discovery-001",
    "symbol": "XAUUSD",
    "timeframe": "M15",
    "session": "london",
    "entry_floors": {"london": 0.6}
  }'
```

### 2. Optimization Service (Port 8002)
Optimizes floor values for discovered strategies via grid search.

**Key Endpoints:**
- `POST /api/v1/optimization/start` - Start optimization job
- `GET /api/v1/optimization/{job_id}/status` - Get job status
- `GET /api/v1/optimization/{job_id}/results` - Get optimized floors

**Example:**
```bash
curl -X POST http://localhost:8002/api/v1/optimization/start \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "optim-001",
    "symbol": "XAUUSD",
    "strategy_name": "OsMA_Confluence",
    "session": "london",
    "timeframe": "M15"
  }'
```

### 3. Validation Service (Port 8003)
Validates strategies before deployment against predefined rules.

**Key Endpoints:**
- `POST /api/v1/validation/start` - Start validation job
- `GET /api/v1/validation/{job_id}/status` - Get job status
- `GET /api/v1/validation/{job_id}/results` - Get validation results
- `GET /api/v1/validation/rules` - Get validation thresholds

**Validation Rules:**
- Profit Factor ≥ 1.3
- Win Rate ≥ 45%
- Sharpe Ratio ≥ 1.0
- Minimum Trades ≥ 10
- Max Consecutive Losses ≤ 5
- Edge Percentage ≥ 2.0%

### 4. API Gateway (Port 8000)
Routes requests to backend services via Nginx.

**Routes:**
- `/api/v1/discovery/*` → Discovery Service (8001)
- `/api/v1/optimization/*` → Optimization Service (8002)
- `/api/v1/validation/*` → Validation Service (8003)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           Client Requests                    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   API Gateway        │
        │  (Nginx:8000)        │
        └──┬───────────┬──────┬┘
           │           │      │
           ▼           ▼      ▼
        ┌────┐    ┌───────┐ ┌────────┐
        │Disc│    │Optim  │ │Validat│
        │overy    │ization│ │ ion   │
        └────┘    └───────┘ └────────┘
         :8001     :8002     :8003
```

---

## Development

### Running Services Locally (Without Docker)

```bash
# Install shared dependencies
pip install -r shared/requirements.txt

# Discovery Service
cd services/discovery-service
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001

# Optimization Service (in new terminal)
cd services/optimization-service
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8002

# Validation Service (in new terminal)
cd services/validation-service
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8003
```

### Running Tests

```bash
# Discovery Service Tests
cd services/discovery-service
pytest tests/ -v

# Optimization Service Tests
cd services/optimization-service
pytest tests/ -v

# Validation Service Tests
cd services/validation-service
pytest tests/ -v
```

### Building Docker Images Manually

```bash
# Build individual service images
docker build -t strategyops-discovery:latest services/discovery-service/
docker build -t strategyops-optimization:latest services/optimization-service/
docker build -t strategyops-validation:latest services/validation-service/
```

---

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key environment variables:
- `LOG_LEVEL` - Logging level (INFO, DEBUG, WARNING, ERROR)
- `DISCOVERY_MIN_TRADES` - Minimum trades for valid backtest
- `OPTIMIZATION_NUM_TRIALS` - Number of optimization trials
- `ENVIRONMENT` - development or production

---

## Monitoring

### Health Checks

All services expose `/health` endpoint:

```bash
curl http://localhost:8001/health  # Discovery
curl http://localhost:8002/health  # Optimization
curl http://localhost:8003/health  # Validation
curl http://localhost:8000/health  # API Gateway
```

### Logs

Each service logs to stdout. Docker Compose captures logs:

```bash
docker-compose logs discovery-service
docker-compose logs optimization-service
docker-compose logs validation-service
```

---

## Troubleshooting

### Services won't start
```bash
# Check Docker daemon
docker ps

# View startup logs
docker-compose logs

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

### API Gateway returns 502
```bash
# Verify backend services are healthy
docker-compose ps

# Check service logs
docker-compose logs discovery-service
docker-compose logs optimization-service
```

### Port already in use
```bash
# Change ports in docker-compose.yml
# Or kill process on port
lsof -i :8001  # Find process on port 8001
kill -9 <PID>   # Kill process
```

---

## Next Phase (Phase 2)

Coming soon:
- Deployment Service (state management)
- Orchestration Service (job coordination)
- Execution Service (live trading)
- PostgreSQL database integration
- Authentication & authorization
- Observability (Prometheus, Grafana)

---

## Project Structure

```
.
├── services/
│   ├── discovery-service/
│   │   ├── app/
│   │   ├── core/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── optimization-service/
│   │   ├── app/
│   │   ├── core/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── validation-service/
│       ├── app/
│       ├── core/
│       ├── tests/
│       ├── Dockerfile
│       └── requirements.txt
├── shared/
│   └── models/
│       └── __init__.py
├── docker-compose.yml
├── nginx.conf
├── .env.example
└── README.md
```

---

## License

Internal - StrategyOps Project

## Support

For issues, open a ticket in the project management system or contact the backend team.
