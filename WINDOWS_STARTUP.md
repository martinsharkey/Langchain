# StrategyOps V2.0 - WINDOWS LAPTOP STARTUP GUIDE

**Status:** SETUP IN PROGRESS - Follow these steps to get running

---

## What's Done ✅

1. ✅ Python 3.12 verified
2. ✅ Git verified
3. ✅ Virtual environment created at `venv/`
4. ✅ All Python dependencies installed
5. ✅ All project files ready

## What You Need to Do ⏳

1. **Install Docker Desktop** (required)
2. **Start Docker Desktop**
3. **Run Docker Compose**
4. **Verify services running**

---

## STEP 1: Install Docker Desktop (5 minutes)

### Easiest Method: Download & Install

1. Go to: **https://www.docker.com/products/docker-desktop**
2. Click **"Download for Windows"**
3. Run the installer file
4. Accept all defaults
5. When asked about WSL 2, **enable it**
6. **Restart your computer when prompted**

### Alternative: PowerShell Command
```powershell
winget install Docker.DockerDesktop
```

**Done?** Restart your computer.

---

## STEP 2: Verify Docker Installation (2 minutes)

Open PowerShell and run:

```powershell
docker --version
docker compose version
docker ps
```

You should see:
- Docker version (e.g., "Docker version 27.0.0")
- Docker Compose version (e.g., "v2.28.0")
- Empty container list (no error)

**If you see errors:** Docker isn't running yet. Start Docker Desktop from Start Menu and wait 60 seconds.

---

## STEP 3: Launch StrategyOps Services (5 minutes)

### Navigate to Project
```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"
```

### Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` prefix in your terminal.

### Build Services (First Time Only - Takes ~5 minutes)
```powershell
docker compose build
```

This downloads and builds all 7 services. You'll see lots of text, which is normal.

### Start Services
```powershell
docker compose up -d
```

The `-d` means "detached" (runs in background).

### Verify All Services Started
```powershell
docker compose ps
```

You should see output like:
```
NAME                    STATUS              PORTS
discovery-service       Up 3 seconds        0.0.0.0:8001->8001/tcp
optimization-service    Up 3 seconds        0.0.0.0:8002->8002/tcp
validation-service      Up 3 seconds        0.0.0.0:8003->8003/tcp
deployment-service      Up 2 seconds        0.0.0.0:8004->8004/tcp
orchestration-service   Up 2 seconds        0.0.0.0:8005->8005/tcp
execution-service       Up 2 seconds        0.0.0.0:8006->8006/tcp
api-gateway             Up 3 seconds        0.0.0.0:8000->8000/tcp
auth-service            Up 2 seconds        0.0.0.0:8007->8007/tcp
```

**Congratulations! 🎉 All services are running!**

---

## STEP 4: Test Services (2 minutes)

### Test API Gateway Health
```powershell
curl http://localhost:8000/health
```

Expected output:
```json
{"status":"healthy","service":"gateway"}
```

### Test Individual Services
```powershell
curl http://localhost:8001/health  # Discovery
curl http://localhost:8002/health  # Optimization
curl http://localhost:8003/health  # Validation
curl http://localhost:8004/health  # Deployment
curl http://localhost:8005/health  # Orchestration
curl http://localhost:8006/health  # Execution
curl http://localhost:8007/health  # Auth
```

All should return: `{"status":"healthy","service":"..."}`

### View Logs
```powershell
# All services
docker compose logs -f

# Specific service
docker compose logs -f discovery-service

# Exit logs: Press Ctrl+C
```

---

## STEP 5: Use the System

### List Available Strategies
```powershell
curl http://localhost:8000/api/v1/discovery/strategies
```

### Get Validation Rules
```powershell
curl http://localhost:8000/api/v1/validation/rules
```

### Run Tests
```powershell
pytest tests/ -v
```

### View Code Quality
```powershell
black --check services/
flake8 services/
```

---

## Common Tasks

### View Logs (Troubleshooting)
```powershell
# All service logs
docker compose logs -f

# Last 100 lines of specific service
docker compose logs --tail=100 discovery-service

# Stop viewing logs
Ctrl+C
```

### Restart a Service
```powershell
docker compose restart discovery-service
```

### Rebuild a Service (After Code Changes)
```powershell
docker compose build discovery-service
docker compose up -d discovery-service
```

### Stop All Services
```powershell
docker compose down
```

### Stop and Remove Everything (Clean Start)
```powershell
docker compose down -v
docker compose build
docker compose up -d
```

### Run Tests with Coverage
```powershell
pytest tests/ --cov=services --cov-report=html
```

---

## Service Information

### What Services Do

| Service | Port | Purpose |
|---------|------|---------|
| **API Gateway** | 8000 | Main entry point, routes requests |
| **Discovery** | 8001 | Finds profitable strategies |
| **Optimization** | 8002 | Optimizes entry floors |
| **Validation** | 8003 | Validates strategies before deployment |
| **Deployment** | 8004 | Manages live strategy state |
| **Orchestration** | 8005 | Coordinates workflows |
| **Execution** | 8006 | Manages live trades |
| **Auth** | 8007 | Handles authentication |

### API Endpoints

```
GET  /health                                     Health check
GET  /api/v1/discovery/strategies                List strategies
POST /api/v1/discovery/start                     Start discovery
GET  /api/v1/discovery/{job_id}/status          Get job status
GET  /api/v1/discovery/{job_id}/results         Get results

POST /api/v1/optimization/start                 Start optimization
GET  /api/v1/optimization/{job_id}/status       Get status

GET  /api/v1/validation/rules                   Get validation rules
POST /api/v1/validation/start                   Start validation

POST /api/v1/deployment/deploy                  Deploy strategy
GET  /api/v1/deployment/{id}/state              Get strategy state

POST /api/v1/orchestration/workflow/create      Create workflow
GET  /api/v1/orchestration/workflow/{id}/status Get workflow status

POST /api/v1/execution/trade/open               Open trade
GET  /api/v1/execution/strategy/{id}/stats      Get execution stats

POST /api/v1/auth/login                         User login
POST /api/v1/auth/register                      Register user
```

---

## Troubleshooting

### Services Not Starting
```powershell
# Check Docker is running
docker ps

# Check for errors
docker compose logs

# Restart Docker Desktop:
# 1. Right-click Docker icon in system tray
# 2. Click "Quit Docker Desktop"
# 3. Wait 10 seconds
# 4. Start Docker Desktop again from Start Menu
# 5. Wait 1 minute
# 6. Try again: docker compose up -d
```

### Port 8000 Already in Use
```powershell
# Find process using port
netstat -ano | findstr :8000

# Kill it (replace PID with actual number)
taskkill /PID 1234 /F

# Or edit docker-compose.yml and change ports
```

### Can't Connect to Services
```powershell
# Verify services are running
docker compose ps

# Check if port is open
curl http://localhost:8000

# If not responding, restart
docker compose restart

# Check logs for errors
docker compose logs
```

### Python Virtual Environment Issues
```powershell
# Verify venv is activated (should see (venv) prompt)
.\venv\Scripts\Activate.ps1

# If issues, recreate venv
rmdir venv -Force -Recurse
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

---

## File Locations

| Path | Purpose |
|------|---------|
| `C:\Users\MartinSharkey\Documents\Langchain\langchain` | Project root |
| `services/` | 7 microservices |
| `docker-compose.yml` | Development config (SQLite) |
| `docker-compose-prod.yml` | Production config (PostgreSQL) |
| `venv/` | Python virtual environment |
| `tests/` | Integration tests |
| `DEPLOYMENT_GUIDE.md` | Full documentation |
| `QUICK_REFERENCE.md` | Quick commands |

---

## Next: Development

### Make Code Changes
1. Edit files in `services/`
2. Services auto-reload changes
3. Check logs: `docker compose logs -f <service>`

### Run Tests
```powershell
.\venv\Scripts\Activate.ps1
pytest tests/ -v
```

### Format Code
```powershell
black services/
```

---

## QUICK START SUMMARY

```powershell
# 1. Install Docker Desktop (see STEP 1)
# 2. Start Docker Desktop from Start Menu

# 3. Navigate to project
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"

# 4. Activate venv
.\venv\Scripts\Activate.ps1

# 5. Build services (first time only)
docker compose build

# 6. Start services
docker compose up -d

# 7. Test
curl http://localhost:8000/health

# 8. View logs
docker compose logs -f
```

---

## Questions?

- **How do I stop services?** `docker compose down`
- **How do I view logs?** `docker compose logs -f <service>`
- **How do I run tests?** `pytest tests/ -v`
- **How do I restart?** `docker compose restart`
- **How do I rebuild?** `docker compose build && docker compose up -d`

---

## Status

Current: **READY TO LAUNCH**

- ✅ Python environment set up
- ✅ Dependencies installed
- ⏳ Waiting for Docker Desktop installation
- ⏳ Ready to start services

**Next Action:** Install Docker Desktop (see STEP 1)

---

**You're all set! Follow the steps above and you'll have StrategyOps running on your Windows laptop in ~20 minutes total. 🚀**
