# StrategyOps V2.0 - Windows Setup Guide (For Your Machine)

**Status:** ✅ Virtual Environment Created & Dependencies Installed

---

## Your System Status

✅ Python 3.12 installed  
✅ Git installed  
✅ Virtual environment created: `C:\Users\MartinSharkey\Documents\Langchain\langchain\venv`  
✅ Python dependencies installed  
⏳ Docker Desktop - NEEDS INSTALLATION  

---

## Step 1: Install Docker Desktop (Required)

Docker Desktop is the only remaining requirement.

### Option A: Download & Install Manually
1. **Visit:** https://www.docker.com/products/docker-desktop
2. **Click:** "Download for Windows"
3. **Run the installer** (Docker Desktop Installer.exe)
4. Follow the installation wizard
5. **IMPORTANT:** When asked, enable "WSL 2" (Windows Subsystem for Linux 2)
6. **Restart your computer** when installation completes

### Option B: Use PowerShell (Requires Admin)
```powershell
winget install Docker.DockerDesktop
```

### Verify Installation
Once installed, open PowerShell and run:
```powershell
docker --version
docker compose version
docker ps
```

You should see output like:
```
Docker version 27.0.0, build abc1234
Docker Compose version v2.28.0
(no containers running)
```

---

## Step 2: Start Docker Desktop

1. Click **Start Menu**
2. Search for **"Docker"**
3. Click **"Docker Desktop"**
4. **Wait 30-60 seconds** for Docker to fully start
5. You should see Docker icon in system tray

---

## Step 3: Launch StrategyOps Services

Open PowerShell and navigate to the project:

```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Build all Docker images (first time only - takes ~5 minutes)
docker compose build

# Start all services (takes ~30 seconds)
docker compose up -d

# Verify all services are running
docker compose ps
```

You should see output like:
```
NAME                    STATUS
discovery-service       Up 2 seconds
optimization-service    Up 2 seconds
validation-service      Up 2 seconds
deployment-service      Up 2 seconds
orchestration-service   Up 2 seconds
execution-service       Up 2 seconds
api-gateway             Up 2 seconds
```

---

## Step 4: Verify Services Are Running

### Test Health Checks
```powershell
# Test API Gateway
curl http://localhost:8000/health

# Test individual services
curl http://localhost:8001/health  # Discovery
curl http://localhost:8002/health  # Optimization
curl http://localhost:8003/health  # Validation
```

Expected response:
```json
{"status": "healthy", "service": "..."}
```

### View Logs
```powershell
# All logs
docker compose logs -f

# Specific service
docker compose logs -f discovery-service
```

### Check Running Containers
```powershell
docker ps
```

---

## Step 5: Test API Endpoints

### List Discovery Strategies
```powershell
curl http://localhost:8000/api/v1/discovery/strategies
```

### Try Start Discovery Job
```powershell
# Create a file: test-discovery.ps1
$body = @{
    job_id = "test_001"
    symbol = "XAUUSD"
    timeframe = "M15"
    session = "london"
    entry_floors = @{ london = 0.6 }
} | ConvertTo-Json

curl -X POST http://localhost:8000/api/v1/discovery/start `
    -ContentType "application/json" `
    -Body $body
```

---

## Common Commands

```powershell
# Start virtual environment
.\venv\Scripts\Activate.ps1

# Build services (first time)
docker compose build

# Start services
docker compose up -d

# Stop services
docker compose down

# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f discovery-service

# List running containers
docker compose ps

# Restart a service
docker compose restart discovery-service

# Rebuild a service
docker compose build discovery-service
docker compose up -d discovery-service

# Remove everything and start fresh
docker compose down -v
docker compose build
docker compose up -d
```

---

## Accessing Services

| Service | Port | URL |
|---------|------|-----|
| **API Gateway** | 8000 | http://localhost:8000 |
| **Discovery** | 8001 | http://localhost:8001/health |
| **Optimization** | 8002 | http://localhost:8002/health |
| **Validation** | 8003 | http://localhost:8003/health |
| **Deployment** | 8004 | http://localhost:8004/health |
| **Orchestration** | 8005 | http://localhost:8005/health |
| **Execution** | 8006 | http://localhost:8006/health |
| **Auth** | 8007 | http://localhost:8007/health |

---

## Development Workflow

### 1. Terminal 1: Activate venv and watch logs
```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"
.\venv\Scripts\Activate.ps1
docker compose logs -f
```

### 2. Terminal 2: Run commands/tests
```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"
.\venv\Scripts\Activate.ps1

# Run tests
pytest tests/ -v

# Run specific test
pytest tests/test_integration.py -v

# Code quality
black services/
flake8 services/
```

### 3. Terminal 3: Make API calls
```powershell
# Test services
curl http://localhost:8001/health

# Or use REST Client extension in VS Code
# File: test.http
GET http://localhost:8001/health
```

---

## Troubleshooting

### Docker Won't Start
```powershell
# Restart Docker service
Restart-Service docker

# Or restart Docker Desktop:
# 1. Close Docker Desktop (right-click icon in tray)
# 2. Open Docker Desktop again from Start Menu
# 3. Wait 1 minute for it to fully start
```

### Port Already in Use
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID 1234 /F

# Or change ports in docker-compose.yml
```

### Virtual Environment Issues
```powershell
# Recreate venv
rmdir venv -Force -Recurse
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install pytest requests pytest-cov black flake8 isort pyyaml PyJWT sqlalchemy psycopg2-binary
```

### Containers Not Starting
```powershell
# Check logs
docker compose logs

# Rebuild everything
docker compose down -v
docker compose build --no-cache
docker compose up -d

# Check service logs
docker compose logs discovery-service
```

---

## Next Steps

1. ✅ **Complete:** Python & dependencies installed
2. ⏳ **TODO:** Install Docker Desktop (see Step 1)
3. ⏳ **TODO:** Start Docker Desktop
4. ⏳ **TODO:** Run `docker compose up -d`
5. ⏳ **TODO:** Test services with `curl http://localhost:8000/health`

---

## Full Setup Completion Checklist

- [ ] Docker Desktop installed
- [ ] Docker Desktop running
- [ ] `docker compose up -d` successful
- [ ] All 7 services showing "Up" status
- [ ] Health checks returning `{"status": "healthy"}`
- [ ] Can reach http://localhost:8000
- [ ] Can make API calls to services
- [ ] Tests running successfully: `pytest tests/ -v`

---

## Files in Your Project

```
C:\Users\MartinSharkey\Documents\Langchain\langchain\
├── services/                      # 7 microservices
│   ├── discovery-service/
│   ├── optimization-service/
│   ├── validation-service/
│   ├── deployment-service/
│   ├── orchestration-service/
│   ├── execution-service/
│   └── auth-service/
├── docker-compose.yml             # Development setup (SQLite)
├── docker-compose-prod.yml        # Production setup (PostgreSQL)
├── nginx.conf                     # API Gateway config
├── venv/                          # Virtual environment (created)
├── DEPLOYMENT_GUIDE.md            # Full documentation
├── QUICK_REFERENCE.md             # Quick commands
└── setup-windows.bat              # Windows setup script
```

---

## Ready?

Once Docker is installed and running:

```powershell
cd "C:\Users\MartinSharkey\Documents\Langchain\langchain"
.\venv\Scripts\Activate.ps1
docker compose up -d
curl http://localhost:8000/health
```

**You're ready to code! 🚀**
