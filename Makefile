.PHONY: help install dev test lint format clean docs build up down logs

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "$(BLUE)StrategyOps v2.0 - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Environment Setup:$(NC)"
	@echo "  make install          Install all dependencies"
	@echo "  make dev              Start development environment"
	@echo "  make clean            Remove build artifacts and cache"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  make test             Run all tests with coverage"
	@echo "  make test-unit        Run unit tests only (fast)"
	@echo "  make test-integration Run integration tests"
	@echo "  make test-e2e         Run end-to-end tests"
	@echo "  make test-watch       Run tests in watch mode"
	@echo ""
	@echo "$(GREEN)Code Quality:$(NC)"
	@echo "  make lint             Run all linters"
	@echo "  make format           Format code with black and isort"
	@echo "  make type-check       Check type hints with mypy"
	@echo "  make security-check   Check for security issues"
	@echo ""
	@echo "$(GREEN)Documentation:$(NC)"
	@echo "  make docs             Build documentation"
	@echo "  make docs-serve       Serve documentation locally"
	@echo ""
	@echo "$(GREEN)Docker:$(NC)"
	@echo "  make up               Start all services (docker-compose)"
	@echo "  make down             Stop all services"
	@echo "  make logs             View service logs"
	@echo "  make restart          Restart all services"
	@echo "  make build            Build all service images"
	@echo ""
	@echo "$(GREEN)Database:$(NC)"
	@echo "  make db-migrate       Run database migrations"
	@echo "  make db-seed          Seed database with test data"
	@echo "  make db-reset         Reset database"
	@echo ""
	@echo "$(GREEN)Utilities:$(NC)"
	@echo "  make version          Show version information"
	@echo "  make check-all        Run all checks (lint, type, test)"

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

install: ## Install all project dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	@echo "$(GREEN)Dependencies installed successfully$(NC)"

dev: up ## Start full development environment (services + watchers)
	@echo "$(BLUE)Starting development environment...$(NC)"
	@echo "Services starting..."
	docker compose up -d
	@echo "$(GREEN)Development environment ready!$(NC)"
	@echo "API Gateway: http://localhost:8000"
	@echo "Discovery Service: http://localhost:8001"

clean: ## Remove build artifacts and cache directories
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	@echo "$(GREEN)Cleanup complete$(NC)"

# ============================================================================
# TESTING
# ============================================================================

test: ## Run all tests with coverage report
	@echo "$(BLUE)Running all tests with coverage...$(NC)"
	pytest --cov=src --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)Tests complete! HTML report: htmlcov/index.html$(NC)"

test-unit: ## Run unit tests only (fast)
	@echo "$(BLUE)Running unit tests...$(NC)"
	pytest tests/unit/ -v --cov=src
	@echo "$(GREEN)Unit tests complete$(NC)"

test-integration: ## Run integration tests (requires services)
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration/ -v -m integration
	@echo "$(GREEN)Integration tests complete$(NC)"

test-e2e: ## Run end-to-end tests (slow)
	@echo "$(BLUE)Running E2E tests...$(NC)"
	pytest tests/e2e/ -v -m e2e
	@echo "$(GREEN)E2E tests complete$(NC)"

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	ptw tests/unit/ -- -v

test-coverage: ## Generate detailed coverage report
	@echo "$(BLUE)Generating coverage report...$(NC)"
	pytest --cov=src --cov-report=html --cov-report=term-missing --cov-fail-under=80
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(NC)"

# ============================================================================
# CODE QUALITY
# ============================================================================

lint: format-check type-check security-check ## Run all linters (format, type, security)
	@echo "$(GREEN)All checks passed!$(NC)"

format-check: ## Check code formatting with black
	@echo "$(BLUE)Checking code formatting...$(NC)"
	black --check --diff src/ tests/ services/
	@echo "$(GREEN)Format check passed$(NC)"

format: ## Format code with black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	black src/ tests/ services/
	isort src/ tests/ services/
	@echo "$(GREEN)Code formatted successfully$(NC)"

type-check: ## Check type hints with mypy
	@echo "$(BLUE)Checking type hints...$(NC)"
	mypy src/ --ignore-missing-imports --check-untyped-defs
	@echo "$(GREEN)Type checking passed$(NC)"

security-check: ## Check for security issues with bandit
	@echo "$(BLUE)Checking security...$(NC)"
	bandit -r src/ -v
	@echo "$(GREEN)Security check passed$(NC)"

lint-flake8: ## Run flake8 linter
	@echo "$(BLUE)Running flake8...$(NC)"
	flake8 src/ tests/ services/ --max-line-length=100 --extend-ignore=E203,W503
	@echo "$(GREEN)Flake8 check passed$(NC)"

lint-pylint: ## Run pylint linter
	@echo "$(BLUE)Running pylint...$(NC)"
	pylint src/ --disable=C0111,R0913 || true
	@echo "$(GREEN)Pylint check complete$(NC)"

# ============================================================================
# DOCUMENTATION
# ============================================================================

docs: ## Build documentation (requires sphinx)
	@echo "$(BLUE)Building documentation...$(NC)"
	cd docs && sphinx-build -b html . _build/html
	@echo "$(GREEN)Documentation built: docs/_build/html/index.html$(NC)"

docs-serve: docs ## Serve documentation locally
	@echo "$(BLUE)Serving documentation at http://localhost:8888...$(NC)"
	python -m http.server 8888 --directory docs/_build/html

docs-clean: ## Clean documentation build
	@echo "$(BLUE)Cleaning documentation...$(NC)"
	rm -rf docs/_build/
	@echo "$(GREEN)Documentation cleaned$(NC)"

# ============================================================================
# DOCKER OPERATIONS
# ============================================================================

up: ## Start all Docker services
	@echo "$(BLUE)Starting Docker services...$(NC)"
	docker compose -f infrastructure/docker-compose.yml up -d
	@echo "$(GREEN)Services started$(NC)"
	@echo "Waiting for services to be healthy..."
	@sleep 5
	docker compose -f infrastructure/docker-compose.yml ps

down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker compose -f infrastructure/docker-compose.yml down
	@echo "$(GREEN)Services stopped$(NC)"

restart: down up ## Restart all Docker services

logs: ## Show Docker service logs (tail -f)
	@echo "$(BLUE)Showing service logs (Ctrl+C to exit)...$(NC)"
	docker compose -f infrastructure/docker-compose.yml logs -f

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=discovery-service)
	@echo "$(BLUE)Showing $(SERVICE) logs...$(NC)"
	docker compose -f infrastructure/docker-compose.yml logs -f $(SERVICE)

build: ## Build all Docker service images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker compose -f infrastructure/docker-compose.yml build --no-cache
	@echo "$(GREEN)Images built successfully$(NC)"

ps: ## Show running services
	@echo "$(BLUE)Running services:$(NC)"
	docker compose -f infrastructure/docker-compose.yml ps

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	alembic upgrade head
	@echo "$(GREEN)Migrations complete$(NC)"

db-seed: ## Seed database with test data
	@echo "$(BLUE)Seeding database...$(NC)"
	python scripts/seed_database.py
	@echo "$(GREEN)Database seeded$(NC)"

db-reset: ## Reset database to clean state
	@echo "$(BLUE)Resetting database...$(NC)"
	alembic downgrade base
	alembic upgrade head
	@echo "$(GREEN)Database reset complete$(NC)"

db-shell: ## Open PostgreSQL shell
	@echo "$(BLUE)Opening PostgreSQL shell...$(NC)"
	docker compose exec postgres psql -U postgres -d strategyops

# ============================================================================
# UTILITIES
# ============================================================================

version: ## Show version information
	@echo "$(BLUE)StrategyOps v2.0 - Version Information$(NC)"
	@echo "Git: $$(git describe --tags 2>/dev/null || echo 'unknown')"
	@echo "Python: $$(python --version)"
	@echo "Docker: $$(docker --version)"
	@echo "Docker Compose: $$(docker compose version)"

check-all: format-check lint-flake8 type-check test ## Run all checks (format, lint, type, test)
	@echo "$(GREEN)✓ All checks passed!$(NC)"

setup-pre-commit: ## Install pre-commit hooks
	@echo "$(BLUE)Setting up pre-commit hooks...$(NC)"
	pre-commit install
	pre-commit run --all-files
	@echo "$(GREEN)Pre-commit hooks installed$(NC)"

setup-venv: ## Create Python virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	python -m venv venv
	@echo "$(GREEN)Virtual environment created. Activate with: source venv/bin/activate$(NC)"

requirements: ## Update requirements files
	@echo "$(BLUE)Updating requirements...$(NC)"
	pip freeze > requirements.txt
	@echo "$(GREEN)Requirements updated$(NC)"

shell: ## Open Python shell with project context
	@echo "$(BLUE)Opening Python shell...$(NC)"
	python

# ============================================================================
# DEVELOPMENT SHORTCUTS
# ============================================================================

dev-discovery: ## Start discovery service in development mode
	@echo "$(BLUE)Starting discovery service...$(NC)"
	cd services/discovery-service && python -m uvicorn app.main:app --reload --port 8001

dev-optimization: ## Start optimization service in development mode
	@echo "$(BLUE)Starting optimization service...$(NC)"
	cd services/optimization-service && python -m uvicorn app.main:app --reload --port 8002

dev-all: ## Start all services in development mode (requires multiple terminals)
	@echo "$(YELLOW)Run these commands in separate terminals:$(NC)"
	@echo "  Terminal 1: make dev-discovery"
	@echo "  Terminal 2: make dev-optimization"
	@echo "  Terminal 3: make dev-validation"
	@echo "  Terminal 4: make dev-deployment"
	@echo "  Terminal 5: make dev-orchestration"
	@echo "  Terminal 6: make dev-execution"

# ============================================================================
# GIT OPERATIONS
# ============================================================================

git-status: ## Show git status
	git status

git-log: ## Show recent git commits
	@echo "$(BLUE)Recent commits:$(NC)"
	git log --oneline -10

# ============================================================================
# MISCELLANEOUS
# ============================================================================

.SILENT: help
