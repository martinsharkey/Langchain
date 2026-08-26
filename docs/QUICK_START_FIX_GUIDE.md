# StrategyOps v2.0 - Quick Start Fix Guide

**Status**: Architecture designed ✅ | Implementation incomplete ❌ | Ready to fix ⏱️

---

## EXECUTIVE SUMMARY FOR IMMEDIATE ACTION

### Current State
- ✅ **Design**: 100% complete and correct
- ❌ **Implementation**: 65% complete (critical issues blocking)
- **Time to Operational**: ~4 hours (fixes + tests)

### The Problem
All 7 services fail to start with: `ModuleNotFoundError: No module named 'shared'`

**Root Cause**: Dockerfiles don't have access to the `shared/` directory during build

### The Fix (in order of importance)
1. **Fix docker-compose.yml** (5 min) - Change build contexts
2. **Fix all Dockerfiles** (30 min) - Copy shared/ directory
3. **Create __init__.py files** (2 min) - Python package markers
4. **Fix service responses** (30 min) - Match model definitions
5. **Update nginx.conf** (10 min) - Add auth service

**Total time**: ~1 hour to make all services work

---

## STEP-BY-STEP FIX INSTRUCTIONS

### STEP 1: Fix docker-compose.yml (5 minutes)

**File**: `docker-compose.yml`

**What to do**: Change ALL 7 service build blocks to use correct context

**Replace this** (appears 7 times):
```yaml
discovery-service:
  build:
    context: ./services/discovery-service
    dockerfile: Dockerfile
```

**With this**:
```yaml
discovery-service:
  build:
    context: .
    dockerfile: ./services/discovery-service/Dockerfile
```

**Repeat for**:
- optimization-service
- validation-service
- deployment-service
- orchestration-service
- execution-service
- auth-service

---

### STEP 2: Fix All Dockerfiles (30 minutes)

**Files to fix** (7 total):
- `services/discovery-service/Dockerfile`
- `services/optimization-service/Dockerfile`
- `services/validation-service/Dockerfile`
- `services/deployment-service/Dockerfile`
- `services/orchestration-service/Dockerfile`
- `services/execution-service/Dockerfile`
- `services/auth-service/Dockerfile`

**For each Dockerfile**, replace content with this template:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared module FIRST (critical for imports)
COPY shared ./shared

# Copy service requirements
COPY services/discovery-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/discovery-service/app ./app
COPY services/discovery-service/core ./core

# Set environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV LOG_LEVEL=INFO
ENV SERVICE_PORT=8001

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

**Customize per service**:
- Replace `discovery-service` with actual service name
- Change port (8001 → 8002, 8003, etc.)
- Keep SERVICE_PORT matching EXPOSE port

---

### STEP 3: Create Python Package Markers (2 minutes)

**Run this command**:
```bash
cd C:\Users\MartinSharkey\Documents\Langchain\langchain

# Create all __init__.py files
type nul > services/discovery-service/app/__init__.py
type nul > services/discovery-service/core/__init__.py
type nul > services/optimization-service/app/__init__.py
type nul > services/optimization-service/core/__init__.py
type nul > services/validation-service/app/__init__.py
type nul > services/validation-service/core/__init__.py
type nul > services/deployment-service/app/__init__.py
type nul > services/deployment-service/core/__init__.py
type nul > services/orchestration-service/app/__init__.py
type nul > services/orchestration-service/core/__init__.py
type nul > services/execution-service/app/__init__.py
type nul > services/execution-service/core/__init__.py
type nul > services/auth-service/app/__init__.py
type nul > services/auth-service/core/__init__.py
```

Or use File Explorer to create empty files in each app/ and core/ directory.

---

### STEP 4: Fix Response Models (30 minutes)

**File 1**: `services/discovery-service/app/main.py`

Find this (around line 51):
```python
response = DiscoveryResponse(
    job_id=job_id,
    status=JobStatus.RUNNING,
    symbol=request.symbol,
    session=request.session,
    discovered_strategies=[],  # ← REMOVE THIS LINE
)
```

Replace with:
```python
response = DiscoveryResponse(
    job_id=job_id,
    status=JobStatus.RUNNING,
    symbol=request.symbol,
    session=request.session,
)
```

---

**File 2**: `services/optimization-service/app/main.py`

Find this (around line 53):
```python
response = OptimizationResponse(
    job_id=job_id,
    status=JobStatus.RUNNING,
    symbol=request.symbol,
    strategy_name=request.strategy_name,
    best_floor=None,
    trials=[],
)
```

Replace with:
```python
response = OptimizationResponse(
    job_id=job_id,
    status=JobStatus.RUNNING,
    symbol=request.symbol,
    session=request.session,
    tuned_params={},
    improvement_pct=0.0
)
```

---

**File 3**: `services/deployment-service/app/main.py`

Find this (around line 48):
```python
response = DeploymentResponse(
    job_id=request.job_id,
    status=JobStatus.COMPLETED,
    strategy_id=request.strategy_id,
    strategy_name=request.strategy_name,
    symbol=request.symbol,
    deployment_status="deployed"
)
```

Replace with:
```python
response = DeploymentResponse(
    job_id=request.job_id,
    status=JobStatus.COMPLETED,
    symbol=request.symbol,
    session=request.session,
    deployment_path="",
    approved_sessions=[],
    rejected_sessions=[]
)
```

---

**File 4**: `services/execution-service/app/main.py`

Find this (around line 48):
```python
response = ExecutionResponse(
    trade_id=request.trade_id,
    status=JobStatus.COMPLETED,
    symbol=request.symbol,
    execution_status="open"
)
```

Replace with:
```python
response = ExecutionResponse(
    job_id=request.trade_id,
    status=JobStatus.COMPLETED,
    symbol=request.symbol,
    session=request.session,
    action_result={}
)
```

---

### STEP 5: Add Auth Service to Nginx (10 minutes)

**File**: `nginx.conf`

**Add upstream** (after line 17, before first location block):
```nginx
upstream auth_backend {
    server auth-service:8007;
}
```

**Add location routes** (after discovery routes, around line 60):
```nginx
# Auth Service Routes
location /api/v1/auth/ {
    proxy_pass http://auth_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_request_buffering off;
}
```

---

## VERIFY THE FIXES WORK

### Step 1: Stop current services
```bash
cd C:\Users\MartinSharkey\Documents\Langchain\langchain
wsl docker compose down
```

### Step 2: Rebuild services (5 min)
```bash
wsl docker compose build
```

**Expected output**: All 7 services should build successfully
```
 build completed
 ✅ discovery-service built
 ✅ optimization-service built
 ✅ validation-service built
 ✅ deployment-service built
 ✅ orchestration-service built
 ✅ execution-service built
 ✅ auth-service built
```

### Step 3: Start services (2 min)
```bash
wsl docker compose up -d
```

**Expected output**: All services starting
```
discovery-service     Started
optimization-service  Started
validation-service    Started
deployment-service    Started
orchestration-service Started
execution-service     Started
auth-service          Started
api-gateway           Started
```

### Step 4: Check service status
```bash
wsl docker compose ps
```

**Expected**: All services showing "Up" (not "Restarting")
```
NAME                    IMAGE                             STATUS
discovery-service       langchain-discovery-service       Up (healthy)
optimization-service    langchain-optimization-service    Up (healthy)
validation-service      langchain-validation-service      Up (healthy)
deployment-service      langchain-deployment-service      Up (healthy)
orchestration-service   langchain-orchestration-service   Up (healthy)
execution-service       langchain-execution-service       Up (healthy)
auth-service            langchain-auth-service            Up (healthy)
api-gateway             nginx:latest                      Up
```

### Step 5: Test health endpoints
```bash
# Test through API gateway
wsl curl http://localhost:8000/api/v1/discovery/health
wsl curl http://localhost:8000/api/v1/optimization/health
wsl curl http://localhost:8000/api/v1/validation/health
wsl curl http://localhost:8000/api/v1/deployment/health
wsl curl http://localhost:8000/api/v1/orchestration/health
wsl curl http://localhost:8000/api/v1/execution/health
wsl curl http://localhost:8000/api/v1/auth/health
```

**Expected**: All return 200 OK with `{"status": "healthy"}`

---

## WHAT TO DO NEXT

Once all fixes applied and services running:

1. **Run Test Suite** (see `ARCHITECTURE_REVIEW_AND_TESTING_PLAN.md`)
   - Phase 1: Infrastructure tests
   - Phase 2: API contract tests
   - Phase 3: End-to-end workflow tests
   - Phase 4: Performance tests

2. **Create Test Collection**
   - Postman collection for all endpoints
   - Automated test suite

3. **Document APIs**
   - OpenAPI/Swagger docs
   - Endpoint examples

4. **Deploy to Staging**
   - Kubernetes ready (k8s/ directory exists)
   - Helm charts ready

---

## TROUBLESHOOTING

### "ModuleNotFoundError: No module named 'shared'"
→ Dockerfile fix not applied correctly
→ Check: `docker compose logs discovery-service` for exact error
→ Verify: `COPY shared ./shared` is in Dockerfile BEFORE service code

### "build context error"
→ Check docker-compose.yml `context:` is `.` not `./services/X`
→ Check `dockerfile:` path is correct relative to root

### Service exits immediately
→ Check: `docker compose logs SERVICE_NAME`
→ Look for Python import errors
→ Ensure all __init__.py files created

### "No module named 'requests' in health check"
→ Health check uses requests library
→ Add to requirements.txt: `requests==2.31.0`
→ Rebuild: `docker compose build SERVICE_NAME`

---

## SUMMARY

| Task | Time | Status |
|------|------|--------|
| Fix docker-compose.yml | 5 min | ⏳ Pending |
| Fix 7 Dockerfiles | 30 min | ⏳ Pending |
| Create __init__.py files | 2 min | ⏳ Pending |
| Fix response models | 30 min | ⏳ Pending |
| Update nginx.conf | 10 min | ⏳ Pending |
| **Total fixes** | **~77 min** | |
| Build & test | 10 min | ⏳ Pending |
| **TOTAL TO OPERATIONAL** | **~90 min** | |

After fixes: 8 hours of testing, then production ready.

