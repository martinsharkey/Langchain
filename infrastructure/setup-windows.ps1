# StrategyOps V2.0 - Windows Development Setup Script
# Run as Administrator: powershell -ExecutionPolicy Bypass -File setup-windows.ps1

param(
    [switch]$SkipDocker = $false,
    [switch]$SkipPython = $false,
    [switch]$SkipGit = $false
)

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Error { Write-Host $args -ForegroundColor Red }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Info { Write-Host $args -ForegroundColor Cyan }

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator"
    Write-Info "Please run PowerShell as Administrator and try again"
    exit 1
}

Write-Info "=========================================="
Write-Info "StrategyOps V2.0 - Windows Setup"
Write-Info "=========================================="
Write-Host ""

# Get Windows version
$osVersion = [System.Environment]::OSVersion.VersionString
Write-Info "Windows Version: $osVersion"
Write-Host ""

# Step 1: Verify/Install Chocolatey
Write-Warning "Step 1: Checking Chocolatey..."
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Write-Success "✓ Chocolatey installed"
} else {
    Write-Success "✓ Chocolatey already installed"
}
Write-Host ""

# Step 2: Install Git
if (-not $SkipGit) {
    Write-Warning "Step 2: Checking Git..."
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Info "Installing Git for Windows..."
        choco install git -y
        Write-Success "✓ Git installed"
    } else {
        Write-Success "✓ Git already installed"
    }
    Write-Host ""
}

# Step 3: Install Python 3.11
if (-not $SkipPython) {
    Write-Warning "Step 3: Checking Python 3.11..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Info "Installing Python 3.11..."
        choco install python311 -y
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        Write-Success "✓ Python 3.11 installed"
    } else {
        Write-Success "✓ Python already installed"
        python --version
    }
    Write-Host ""
}

# Step 4: Install Docker Desktop
if (-not $SkipDocker) {
    Write-Warning "Step 4: Checking Docker Desktop..."
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Info "Installing Docker Desktop..."
        choco install docker-desktop -y
        Write-Warning "Docker Desktop installed. Please start Docker Desktop manually and wait for it to start."
        Write-Warning "Then run this script again or proceed with the next steps."
        Read-Host "Press Enter once Docker Desktop has started"
    } else {
        Write-Success "✓ Docker Desktop already installed"
        docker --version
        docker compose version
    }
    Write-Host ""
}

# Step 5: Verify Docker is running
Write-Warning "Step 5: Verifying Docker..."
$dockerRunning = $false
try {
    $null = docker ps -q
    Write-Success "✓ Docker is running"
    $dockerRunning = $true
} catch {
    Write-Error "Docker is not running. Please start Docker Desktop."
}
Write-Host ""

# Step 6: Create Python Virtual Environment
Write-Warning "Step 6: Setting up Python Virtual Environment..."
if (-not (Test-Path "venv")) {
    Write-Info "Creating virtual environment..."
    python -m venv venv
    Write-Success "✓ Virtual environment created"
} else {
    Write-Success "✓ Virtual environment already exists"
}
Write-Host ""

# Step 7: Activate Virtual Environment and Install Dependencies
Write-Warning "Step 7: Installing Python dependencies..."
& ".\venv\Scripts\Activate.ps1"
pip install --upgrade pip setuptools wheel
pip install pytest requests pytest-cov black flake8 isort pyyaml

Write-Success "✓ Python dependencies installed"
Write-Host ""

# Step 8: Create .env file
Write-Warning "Step 8: Setting up environment file..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Success "✓ Created .env file from .env.example"
        Write-Warning "Please edit .env with your configuration"
    } else {
        Write-Error "No .env.example file found"
    }
} else {
    Write-Success "✓ .env file already exists"
}
Write-Host ""

# Step 9: Pull Docker Images
if ($dockerRunning) {
    Write-Warning "Step 9: Pulling Docker images..."
    Write-Info "This may take a few minutes..."
    
    docker pull nginx:alpine
    docker pull python:3.11-slim
    docker pull postgres:15-alpine
    docker pull prom/prometheus:latest
    docker pull grafana/grafana:latest
    
    Write-Success "✓ Docker images downloaded"
} else {
    Write-Warning "Step 9: Skipping Docker image download (Docker not running)"
}
Write-Host ""

# Step 10: Summary
Write-Success "=========================================="
Write-Success "Setup Complete!"
Write-Success "=========================================="
Write-Host ""
Write-Info "Next steps:"
Write-Info "1. Edit .env file with your settings"
Write-Info "2. Start services: docker compose up -d"
Write-Info "3. Verify services: curl http://localhost:8000/health"
Write-Info "4. View logs: docker compose logs -f"
Write-Host ""
Write-Info "Common commands:"
Write-Info "  docker compose up -d           # Start services"
Write-Info "  docker compose down            # Stop services"
Write-Info "  docker compose logs -f         # View logs"
Write-Info "  docker compose ps              # List containers"
Write-Host ""
Write-Info "Testing:"
Write-Info "  .\venv\Scripts\Activate.ps1    # Activate virtual environment"
Write-Info "  pytest tests/ -v               # Run tests"
Write-Host ""
Write-Info "Documentation:"
Write-Info "  - WINDOWS_SETUP_GUIDE.md       # This guide"
Write-Info "  - DEPLOYMENT_GUIDE.md          # Full deployment guide"
Write-Info "  - QUICK_REFERENCE.md           # Quick commands"
Write-Host ""
Write-Success "=========================================="
Write-Success "Ready to code! 🚀"
Write-Success "=========================================="
