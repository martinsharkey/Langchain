# StrategyOps v2.0 - Visual Architecture Guide

## System Architecture Overview

```
API Gateway (Nginx:8000) 
    ↓
    ├─→ Discovery Service (8001)
    ├─→ Optimization Service (8002)
    ├─→ Validation Service (8003)
    ├─→ Deployment Service (8004)
    ├─→ Orchestration Service (8005)
    ├─→ Execution Service (8006)
    └─→ Auth Service (8007)

All connected via Docker Network: strategyops
All using Shared Models Layer for communication
```

## Service Workflow Pipeline

```
DISCOVERY (Vectorbt)
  ↓ Find indicators for symbol/session
  
OPTIMIZATION (Optuna)
  ↓ Tune parameters for discovered indicators
  
VALIDATION (Walk-Forward)
  ↓ Test parameters, calculate profit factor
  
DEPLOYMENT
  ↓ Deploy to paper or live trading
  
EXECUTION
  ↓ Execute trades based on signals
```

## Docker Architecture

```
Services: 7 total (+ 1 API Gateway)
Base Image: Python 3.11-slim
Orchestration: docker-compose.yml
Network: strategyops (bridge)
Volume: None (future enhancement)

Each service:
  ├── FastAPI application
  ├── Health check endpoint
  ├── Shared model imports
  └── Proper error handling
```

## Critical Path to Production

```
Stage 1: Fix Architecture (1.5 hours)
├── Update docker-compose.yml contexts
├── Update all 7 Dockerfiles
├── Create 14 __init__.py files
├── Fix 4 service response models
└── Update nginx.conf

Stage 2: Verify & Test (8 hours)
├── Infrastructure tests (2h)
├── API contract tests (3h)
├── End-to-end tests (2h)
├── Performance tests (1h)
└── Documentation (ongoing)

Stage 3: Production Ready (4 hours)
├── Create Postman collection
├── Write API documentation
├── Prepare deployment guide
└── Staging deployment

Total: ~13.5 hours from now to production
```

## What's Working

- All 7 services scaffolded and designed
- Shared models comprehensive
- API Gateway configured
- Docker infrastructure prepared
- Database schemas complete
- Health checks configured

## What Needs Fixes

1. Shared module import path (all services)
2. Docker build contexts (7 files)
3. Python package markers (14 files)
4. Response model mismatches (4 services)
5. Auth service integration (1 file)

## Success Criteria

- All services running and healthy
- Discovery to Deployment workflow functional
- Per-session parameters applied correctly
- 100% test pass rate
- Response time &lt;500ms

See QUICK_START_FIX_GUIDE.md to begin fixes.
