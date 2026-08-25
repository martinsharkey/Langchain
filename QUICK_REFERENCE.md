## StrategyOps V2.0 - Quick Reference

### Launch Services

```bash
# Validate architecture
python validate_architecture.py

# Build all services
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Service Ports

| Service | Port | Health | API Base |
|---------|------|--------|----------|
| API Gateway | 8000 | /health | /api/v1/* |
| Discovery | 8001 | /health | /api/v1/discovery |
| Optimization | 8002 | /health | /api/v1/optimization |
| Validation | 8003 | /health | /api/v1/validation |

### API Examples

**Discovery Service**
```bash
# List available strategies
curl http://localhost:8000/api/v1/discovery/strategies

# Start discovery
curl -X POST http://localhost:8000/api/v1/discovery/start \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "disc-001",
    "symbol": "XAUUSD",
    "timeframe": "M15",
    "session": "london",
    "entry_floors": {"london": 0.6}
  }'

# Check status
curl http://localhost:8000/api/v1/discovery/disc-001/status

# Get results
curl http://localhost:8000/api/v1/discovery/disc-001/results
```

**Optimization Service**
```bash
# Start optimization
curl -X POST http://localhost:8000/api/v1/optimization/start \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "optim-001",
    "symbol": "XAUUSD",
    "strategy_name": "RSI14",
    "session": "london",
    "timeframe": "M15"
  }'

# Get results
curl http://localhost:8000/api/v1/optimization/optim-001/results
```

**Validation Service**
```bash
# Get validation rules
curl http://localhost:8000/api/v1/validation/rules

# Start validation
curl -X POST http://localhost:8000/api/v1/validation/start \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "val-001",
    "symbol": "XAUUSD",
    "strategy_name": "RSI14",
    "session": "london"
  }'

# Get results
curl http://localhost:8000/api/v1/validation/val-001/results
```

### Validation Rules

- **Profit Factor**: >= 1.3
- **Win Rate**: >= 45%
- **Sharpe Ratio**: >= 1.0
- **Minimum Trades**: >= 10
- **Max Consecutive Losses**: <= 5
- **Edge Percentage**: >= 2.0%

### Troubleshooting

```bash
# Check if services are running
docker-compose ps

# View detailed logs
docker-compose logs discovery-service
docker-compose logs optimization-service
docker-compose logs validation-service

# Restart services
docker-compose restart

# Rebuild services
docker-compose build --no-cache

# Check API Gateway
curl -v http://localhost:8000/health
```

### File Structure

```
.
├── services/
│   ├── discovery-service/
│   │   ├── app/main.py
│   │   ├── core/discovery_engine.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── optimization-service/
│   │   ├── app/main.py
│   │   ├── core/optimization_engine.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── validation-service/
│       ├── app/main.py
│       ├── core/validation_engine.py
│       ├── Dockerfile
│       └── requirements.txt
├── shared/
│   └── models/__init__.py
├── docker-compose.yml
├── nginx.conf
├── .env.example
├── validate_architecture.py
└── README.md
```

### Key Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /health | Service health check |
| POST | /api/v1/discovery/start | Start discovery job |
| GET | /api/v1/discovery/{id}/status | Get discovery status |
| GET | /api/v1/discovery/{id}/results | Get discovery results |
| GET | /api/v1/discovery/strategies | List available strategies |
| POST | /api/v1/optimization/start | Start optimization job |
| GET | /api/v1/optimization/{id}/status | Get optimization status |
| GET | /api/v1/optimization/{id}/results | Get optimization results |
| POST | /api/v1/validation/start | Start validation job |
| GET | /api/v1/validation/{id}/status | Get validation status |
| GET | /api/v1/validation/{id}/results | Get validation results |
| GET | /api/v1/validation/rules | Get validation rules |

### Documentation Files

- `README.md` - Main documentation
- `V2.0_ARCHITECTURE_STRUCTURE.md` - Architecture design
- `V2.0_PHASE1_KICKOFF.md` - Phase 1 initiation
- `V2.0_PHASE1_COMPLETION.md` - Phase 1 summary
- `PHASE1_FINAL_HANDOFF.md` - Handoff document
- `PHASE1_STATUS.txt` - Status report

### For More Information

See `README.md` for comprehensive documentation on:
- Service details
- API usage
- Configuration
- Development setup
- Troubleshooting
- Project roadmap
