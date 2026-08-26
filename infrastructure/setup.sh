#!/bin/bash
set -e

# ============================================================
# LangChain ReAct Agent - XAUUSD MT5 Trading Bot
# Setup Script
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  LangChain XAUUSD Trading Bot - Setup"
echo "============================================"
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found. Please install Python 3.11+."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
echo "  Found Python $PYTHON_VERSION"

# Compare version using Python itself (avoids bc dependency)
PYTHON_OK=$($PYTHON_CMD -c "import sys; v=sys.version_info; print('ok' if v.major==3 and v.minor>=10 else 'bad')")
if [ "$PYTHON_OK" != "ok" ]; then
    echo "ERROR: Python 3.10+ required. Found $PYTHON_VERSION"
    exit 1
fi
echo "  ✓ Python version OK"
echo ""

# Create virtual environment
echo "[2/5] Creating virtual environment..."
if [ -d "venv" ]; then
    echo "  Virtual environment already exists. Skipping..."
else
    $PYTHON_CMD -m venv venv
    echo "  ✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "[3/5] Activating virtual environment..."
source venv/bin/activate
echo "  ✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "[4/5] Upgrading pip..."
pip install --upgrade pip --quiet
echo "  ✓ pip upgraded"
echo ""

# Install dependencies
echo "[5/5] Installing dependencies..."
pip install -r requirements.txt --quiet
echo "  ✓ Dependencies installed"
echo ""

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "[+] Creating .env file from template..."
    cp .env.example .env
    echo "  ✓ .env created — please edit it with your API keys"
    echo ""
fi

# Create necessary directories
mkdir -p logs
mkdir -p data

echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Groq API key and MT5 credentials"
echo "  2. Activate the environment: source venv/bin/activate"
echo "  3. Run the agent: python src/main.py"
echo ""
