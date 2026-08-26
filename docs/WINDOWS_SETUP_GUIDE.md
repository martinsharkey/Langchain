# StrategyOps V2.0 - Windows Development Setup Guide

## Prerequisites

Before starting, ensure you have Windows 10/11 with administrator access.

---

## Step 1: Install Docker Desktop for Windows

### Option A: Direct Download
1. Visit https://www.docker.com/products/docker-desktop
2. Download "Docker Desktop for Windows"
3. Run the installer
4. Follow the installation wizard
5. Restart your computer when prompted

### Option B: Using Chocolatey
```powershell
# Run PowerShell as Administrator
choco install docker-desktop
```

### Option C: Using Windows Package Manager
```powershell
winget install Docker.DockerDesktop
```

### Verify Installation
```powershell
docker --version
docker compose version
docker ps
```

---

## Step 2: Install Git for Windows

### Download
1. Visit https://git-scm.com/download/win
2. Download the latest installer
3. Run the installer (accept defaults)

### Or use Chocolatey
```powershell
choco install git
```

### Verify
```powershell
git --version
```

---

## Step 3: Install Python 3.11

### Option A: Official Python Installer
1. Visit https://www.python.org/downloads/
2. Download Python 3.11
3. Run installer
4. **IMPORTANT: Check "Add Python to PATH"**
5. Click "Install Now"

### Option B: Using Chocolatey
```powershell
choco install python311
```

### Option C: Using Windows Package Manager
```powershell
winget install Python.Python.3.11
```

### Verify Installation
```powershell
python --version
pip --version
```

---

## Step 4: Clone StrategyOps Repository

```powershell
# Navigate to desired location
cd C:\Users\YourUsername\Documents

# Clone the repository
git clone https://github.com/yourorg/strategyops-v2.git
cd strategyops-v2
```

---

## Step 5: Quick Start (Automated Setup)

### Run Setup Script
```powershell
# Run the setup script
.\setup-windows.ps1
```

If you get execution policy error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup-windows.ps1
```

---

## Step 6: Manual Setup (If Script Fails)

### 6.1 Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 6.2 Install Python Dependencies
```powershell
pip install --upgrade pip
pip install pytest requests pytest-cov black flake8 isort
```

### 6.3 Verify Docker
```powershell
docker ps
docker compose version
```

### 6.4 Create Environment File
```powershell
Copy-Item .env.example .env
# Edit .env with your settings
```

---

## Step 7: Start Development Environment

### Option A: SQLite (Quick Start - No Database Install)
```powershell
# Build and start all services
docker compose build
docker compose up -d

# Verify services are running
docker compose ps

# Check health
curl http://localhost:8000/health
```

### Option B: PostgreSQL (Full Environment)
```powershell
# Start with PostgreSQL
docker compose -f docker-compose-prod.yml up -d

# Verify
docker compose -f docker-compose-prod.yml ps

# Check Grafana
Start-Process "http://localhost:3000"
```

---

## Step 8: Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| **API Gateway** | http://localhost:8000 | Main entry point |
| **Discovery** | http://localhost:8001/health | Strategy discovery |
| **Optimization** | http://localhost:8002/health | Floor optimization |
| **Validation** | http://localhost:8003/health | Pre-deployment checks |
| **Deployment** | http://localhost:8004/health | State management |
| **Orchestration** | http://localhost:8005/health | Workflow coordination |
| **Execution** | http://localhost:8006/health | Trade management |
| **Auth** | http://localhost:8007/health | Authentication |
| **Prometheus** | http://localhost:9090 | Metrics (prod only) |
| **Grafana** | http://localhost:3000 | Dashboards (prod only) |

---

## Step 9: Common Operations

### View Logs
```powershell
# All services
docker compose logs -f

# Specific service
docker compose logs -f discovery-service

# Last 100 lines
docker compose logs --tail=100 discovery-service
```

### Stop Services
```powershell
docker compose down
```

### Restart Services
```powershell
docker compose restart
```

### Rebuild Services
```powershell
docker compose build --no-cache
docker compose up -d
```

### Remove Everything (Clean Slate)
```powershell
docker compose down -v
```

---

## Step 10: Run Tests

### Unit Tests
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=services --cov-report=html
```

### Integration Tests
```powershell
# Make sure Docker services are running
docker compose up -d

# Run integration tests
pytest tests/test_integration.py -v
```

---

## Step 11: Development Workflow

### 1. Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### 2. Make Code Changes
- Edit files in `services/`
- Services will auto-reload if using dev mode

### 3. Format Code
```powershell
black services/
```

### 4. Lint Code
```powershell
flake8 services/
```

### 5. Run Tests
```powershell
pytest services/ -v
```

### 6. View Logs
```powershell
docker compose logs -f <service-name>
```

---

## Troubleshooting

### Docker Won't Start
```powershell
# Check Docker status
docker ps

# If error, restart Docker Desktop
# Or restart Docker service
Restart-Service docker

# Check Docker logs
$env:USERPROFILE\.docker\daemon.json
```

### Port Already in Use
```powershell
# Find process using port
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID <PID> /F

# Or change port in docker-compose.yml
```

### Insufficient Disk Space
```powershell
# Clean up Docker
docker system prune -a

# Remove unused volumes
docker volume prune

# Remove unused networks
docker network prune
```

### Python Virtual Environment Issues
```powershell
# Recreate virtual environment
rmdir venv -Force -Recurse
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### PostgreSQL Connection Issues
```powershell
# Check if PostgreSQL is running (prod mode)
docker compose -f docker-compose-prod.yml ps postgres

# Check logs
docker compose -f docker-compose-prod.yml logs postgres

# Restart PostgreSQL
docker compose -f docker-compose-prod.yml restart postgres
```

---

## Performance Tips

### 1. Allocate More RAM to Docker
- Open Docker Desktop settings
- Go to Resources
- Increase Memory to 4-8 GB (depending on your system)
- Increase CPUs to 4+

### 2. Use WSL 2
- Ensures Docker Desktop runs in Linux VM (better performance)
- Should be default on Windows 11

### 3. Optimize Storage
- Store project on local SSD, not network drive
- Avoid OneDrive/Dropbox for Docker volumes

### 4. Enable File Sharing
- Docker Desktop → Preferences → Resources → File Sharing
- Add your project directory

---

## Environment Variables

Edit `.env` file with your settings:

```
# Database
DATABASE_URL=postgresql://strategyops:password@postgres:5432/strategyops

# Services
LOG_LEVEL=INFO
SERVICE_HOST=0.0.0.0

# Auth
JWT_SECRET_KEY=your-secret-key-change-in-production

# Environment
ENVIRONMENT=development
```

---

## IDE Setup (Visual Studio Code)

### 1. Install Extensions
- Python
- Docker
- REST Client
- PostgreSQL

### 2. Python Interpreter
- Ctrl+Shift+P → "Python: Select Interpreter"
- Choose `./venv/Scripts/python.exe`

### 3. Run Tests in VS Code
- Terminal → New Terminal
- Activate venv: `.\venv\Scripts\Activate.ps1`
- Run: `pytest tests/ -v`

### 4. Docker Integration
- Open Docker extension in sidebar
- Monitor running containers
- View logs directly

---

## Useful Commands Reference

```powershell
# Services Management
docker compose up -d                    # Start services
docker compose down                     # Stop services
docker compose restart <service>        # Restart service
docker compose rebuild <service>        # Rebuild service
docker compose pull                     # Pull latest images
docker compose logs -f <service>        # View logs

# Docker Management
docker ps                               # List running containers
docker images                           # List images
docker volume ls                        # List volumes
docker network ls                       # List networks
docker system prune                     # Clean up unused resources

# Testing
pytest tests/ -v                        # Run all tests
pytest tests/test_integration.py -v     # Run integration tests
pytest --cov=services tests/            # With coverage

# Code Quality
black services/                         # Format code
flake8 services/                        # Lint code
isort services/                         # Sort imports

# Development
python -m venv venv                     # Create virtual environment
.\venv\Scripts\Activate.ps1             # Activate venv
pip install -r requirements-dev.txt     # Install dependencies
pip freeze > requirements.txt           # Export dependencies
```

---

## Next Steps

1. **Run Setup Script**
   ```powershell
   .\setup-windows.ps1
   ```

2. **Start Services**
   ```powershell
   docker compose up -d
   ```

3. **Verify Health**
   ```powershell
   curl http://localhost:8000/health
   ```

4. **Explore APIs**
   - Open browser: http://localhost:8000
   - Or use REST Client: `GET http://localhost:8001/health`

5. **Read Documentation**
   - See `DEPLOYMENT_GUIDE.md`
   - See `QUICK_REFERENCE.md`
   - See `README.md`

---

## Support

**Issues?**
- Check Docker Desktop logs: `%USERPROFILE%\.docker\daemon.json`
- Check service logs: `docker compose logs -f`
- Review troubleshooting section above

**Documentation:**
- `DEPLOYMENT_GUIDE.md` - Complete guide
- `QUICK_REFERENCE.md` - Quick commands
- `README.md` - Service overview

---

**Ready to code! 🚀**
