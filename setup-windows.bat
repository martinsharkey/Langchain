@echo off
REM StrategyOps V2.0 - Windows Setup Script
REM This script will install all required dependencies and set up your dev environment
REM Run as Administrator: right-click cmd.exe -> Run as administrator, then run this script

echo ==========================================
echo StrategyOps V2.0 - Windows Setup
echo ==========================================
echo.
echo This script will:
echo 1. Check and install Chocolatey
echo 2. Install Docker Desktop
echo 3. Install Python dependencies
echo 4. Create virtual environment
echo 5. Start Docker services
echo.

REM Check if running as Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator
    echo Please run Command Prompt as Administrator
    pause
    exit /b 1
)

echo [1/5] Checking Chocolatey...
where choco >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing Chocolatey...
    @"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
    echo Chocolatey installed successfully
) else (
    echo Chocolatey already installed
)
echo.

echo [2/5] Checking Docker Desktop...
where docker >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing Docker Desktop...
    choco install docker-desktop -y
    echo.
    echo IMPORTANT: Docker Desktop has been installed
    echo Please:
    echo 1. Restart your computer
    echo 2. Start Docker Desktop from Start Menu
    echo 3. Wait for Docker to fully start
    echo 4. Run this script again
    pause
    exit /b 0
) else (
    echo Docker is already installed
    docker --version
)
echo.

echo [3/5] Checking Python...
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing Python 3.11...
    choco install python311 -y
) else (
    echo Python is already installed
    python --version
)
echo.

echo [4/5] Setting up Python Virtual Environment...
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created
) else (
    echo Virtual environment already exists
)
echo.

echo [5/5] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install pytest requests pytest-cov black flake8 isort pyyaml
echo Dependencies installed
echo.

echo ==========================================
echo Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo 1. Make sure Docker Desktop is running
echo 2. Navigate to: C:\Users\MartinSharkey\Documents\Langchain\langchain
echo 3. Run: docker compose up -d
echo 4. Test: curl http://localhost:8000/health
echo.
echo Quick commands:
echo   docker compose up -d              Start services
echo   docker compose down               Stop services
echo   docker compose ps                 List services
echo   docker compose logs -f            View logs
echo   docker compose logs -f ^<service^>  View service logs
echo.
pause
