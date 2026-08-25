#!/bin/bash

# StrategyOps V2.0 - macOS Development Setup Script
# Run this script on your Mac to set up the complete development environment

set -e

echo "=========================================="
echo "StrategyOps V2.0 - macOS Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}Error: This script must be run on macOS${NC}"
    exit 1
fi

echo "Detected macOS: $(sw_vers -productVersion)"
echo ""

# Step 1: Install Homebrew
echo -e "${YELLOW}Step 1: Installing Homebrew...${NC}"
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo -e "${GREEN}✓ Homebrew already installed${NC}"
fi

# Add brew to PATH for Apple Silicon Macs
if [[ $(arch) == "arm64" ]]; then
    export PATH="/opt/homebrew/bin:$PATH"
fi

echo ""

# Step 2: Install Docker
echo -e "${YELLOW}Step 2: Installing Docker Desktop...${NC}"
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker Desktop..."
    brew install --cask docker
    
    # Start Docker daemon
    open -a Docker
    echo "Please wait for Docker to start (this may take a minute)..."
    sleep 30
    
    # Wait for Docker to be ready
    while ! docker ps &> /dev/null; do
        echo "Waiting for Docker to be ready..."
        sleep 5
    done
else
    echo -e "${GREEN}✓ Docker already installed${NC}"
fi

echo ""

# Step 3: Install Docker Compose (if not included)
echo -e "${YELLOW}Step 3: Verifying Docker Compose...${NC}"
if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓ Docker Compose is available${NC}"
else
    echo "Installing Docker Compose..."
    brew install docker-compose
fi

echo ""

# Step 4: Install Python 3.11
echo -e "${YELLOW}Step 4: Installing Python 3.11...${NC}"
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11 not found. Installing..."
    brew install python@3.11
    
    # Create symlink if needed
    ln -sf /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 || true
else
    echo -e "${GREEN}✓ Python 3.11 already installed${NC}"
fi

echo ""

# Step 5: Install PostgreSQL (optional, for local development)
echo -e "${YELLOW}Step 5: Installing PostgreSQL...${NC}"
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL not found. Installing via Homebrew..."
    brew install postgresql
    
    # Start PostgreSQL
    brew services start postgresql
    
    echo "Creating default database user..."
    createuser -U postgres strategyops 2>/dev/null || true
    
else
    echo -e "${GREEN}✓ PostgreSQL already installed${NC}"
fi

echo ""

# Step 6: Install Git (usually pre-installed on macOS)
echo -e "${YELLOW}Step 6: Verifying Git...${NC}"
if ! command -v git &> /dev/null; then
    echo "Git not found. Installing..."
    brew install git
else
    echo -e "${GREEN}✓ Git already installed${NC}"
fi

echo ""

# Step 7: Install additional tools
echo -e "${YELLOW}Step 7: Installing additional tools...${NC}"
brew install curl wget htop

echo ""

# Step 8: Verify Python packages
echo -e "${YELLOW}Step 8: Verifying Python environment...${NC}"
python3 --version
pip3 --version

echo ""

# Step 9: Create virtual environment
echo -e "${YELLOW}Step 9: Creating Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
source venv/bin/activate

echo ""

# Step 10: Install Python dependencies
echo -e "${YELLOW}Step 10: Installing Python dependencies...${NC}"
pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt 2>/dev/null || pip install pytest requests pytest-cov black flake8

echo ""

# Step 11: Verify Docker setup
echo -e "${YELLOW}Step 11: Verifying Docker setup...${NC}"
docker ps > /dev/null 2>&1 && echo -e "${GREEN}✓ Docker is working${NC}" || echo -e "${RED}✗ Docker is not responding${NC}"
docker compose version > /dev/null 2>&1 && echo -e "${GREEN}✓ Docker Compose is working${NC}" || echo -e "${RED}✗ Docker Compose is not available${NC}"

echo ""

# Step 12: Pull Docker images
echo -e "${YELLOW}Step 12: Pulling Docker images...${NC}"
docker pull nginx:alpine
docker pull postgres:15-alpine
docker pull python:3.11-slim
docker pull prom/prometheus:latest
docker pull grafana/grafana:latest

echo ""

# Step 13: Create .env file
echo -e "${YELLOW}Step 13: Setting up environment file...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file (please edit with your settings)${NC}"
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

echo ""

# Summary
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Start services: docker-compose up -d"
echo "3. Verify services: curl http://localhost:8000/health"
echo "4. Access API Gateway: http://localhost:8000"
echo "5. View logs: docker-compose logs -f"
echo ""
echo "Optional - Local development:"
echo "- Activate venv: source venv/bin/activate"
echo "- Run tests: pytest tests/"
echo "- Lint code: black services/"
echo ""
echo "PostgreSQL:"
if [ -x "$(command -v psql)" ]; then
    echo "- Start: brew services start postgresql"
    echo "- Stop: brew services stop postgresql"
    echo "- Status: brew services list"
fi
echo ""
echo "=========================================="
