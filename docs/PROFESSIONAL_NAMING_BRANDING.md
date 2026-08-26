# PROFESSIONAL NAMING & BRANDING STRATEGY

**Date:** 2026-08-25
**Scope:** Product naming, component naming, professional brand identity

---

## CURRENT vs. RECOMMENDED NAMING

### Product Level

| Current | Recommended | Why |
|---------|-------------|-----|
| ScalpEngine | **StrategyOps** | Professional, descriptive, SaaS-ready |
| - | *Tagline:* "Intelligent Strategy Operations Platform" | Value proposition |

### Service Components

| Component | Current | Recommended |
|-----------|---------|-------------|
| Phase 1 | Discovery Service | Strategy Discovery Engine |
| Phase 2 | Tuning Service | Parameter Optimization Engine |
| Phase 3 | Validation Service | Risk Validator |
| Phase 4 | Deployment Service | Configuration Deployment Manager |
| Phase 5 (New) | - | Trading Execution Engine |
| Orchestrator | Complete Pipeline | Workflow Orchestrator |

### Technical Components

| Current | Recommended | Context |
|---------|-------------|---------|
| tuned_params.json | strategy_configuration.json | More professional |
| entry_floors | entry_thresholds | Industry standard |
| exit_params | exit_configuration | Clearer intent |
| BaseStrategy | StrategyInterface | More professional |
| STRATEGY_REGISTRY | StrategyManager | Clearer responsibility |
| ScalpEngine | ExecutionKernel | Professional tier name |

### Domain & Brand

**Primary:** strategyops.io (recommended)
**Secondary:** strategyops.ai
**GitHub:** github.com/strategyops/core

---

## BRAND IDENTITY

### StrategyOps Brand Promise

**Mission:** "Democratizing intelligent trading strategy development"

**Vision:** "The enterprise platform for strategy discovery, optimization, and execution"

**Core Values:**
- Intelligent (AI-driven)
- Reliable (production-grade)
- Accessible (professional UI)
- Scalable (service-oriented)
- Transparent (explainable AI)

### Logo Concept

```
[S] Overlapping circles (strategy layers)
STRATEGYOPS
Intelligent Trading Operations
```

### Taglines

1. "Discover. Optimize. Deploy. Execute." (process-focused)
2. "Intelligent Strategy Operations" (value-focused)
3. "Enterprise Strategy Automation" (target-focused)

---

## DOCUMENTATION NAMING

### User-Facing Documentation

```
StrategyOps User Guide
├─ Getting Started with StrategyOps
├─ Dashboard Tour
├─ Strategy Discovery Guide
├─ Parameter Optimization Guide
├─ Deployment & Execution
├─ FAQ
└─ Support

StrategyOps API Reference
├─ Discovery API
├─ Optimization API
├─ Validation API
├─ Deployment API
└─ Execution API
```

### Internal Documentation

```
StrategyOps Architecture
├─ System Overview
├─ Service Architecture
├─ Data Flow
├─ Integration Patterns
└─ Deployment Architecture

StrategyOps Developer Guide
├─ Adding Strategies
├─ Adding Services
├─ Testing
├─ CI/CD Pipeline
└─ Contribution Guidelines
```

---

## CODE NAMING UPDATES

### Package Structure

```python
# Current
from src.phase1_discovery import run_phase1_discovery

# Recommended
from strategyops.services.discovery import DiscoveryService
from strategyops.services.discovery.api import discovery_routes
```

### API Naming

```python
# Current
@app.post("/phase1/discover")
def discover_strategies():
    pass

# Recommended
@app.post("/api/v1/discovery/start")
def start_strategy_discovery():
    pass

# Current
@app.post("/phase4/deploy")
def deploy_config():
    pass

# Recommended
@app.post("/api/v1/deployment/execute")
def execute_deployment():
    pass
```

### Variable Naming

```python
# Current
exit_params = {
    'sl_atr_mult': 1.5,
    'tp_ratio': 2.5
}

# Recommended
exit_configuration = {
    'stop_loss_multiplier': 1.5,
    'take_profit_ratio': 2.5
}

# Current
entry_floors = {'min_strength': 0.3}

# Recommended
entry_thresholds = {'minimum_signal_strength': 0.3}
```

---

## DIRECTORY STRUCTURE WITH PROFESSIONAL NAMING

### Current Structure

```
src/
├─ phase_integration.py
├─ phase1_discovery.py
├─ phase2_tuning.py
├─ phase3_validation.py
├─ phase4_deployment.py
└─ complete_pipeline.py
```

### Recommended Structure

```
strategyops/
├─ core/                              # Core interfaces & contracts
│  ├─ __init__.py
│  ├─ models.py                       # Dataclasses
│  ├─ interfaces.py                   # Abstract interfaces
│  └─ constants.py                    # Constants
│
├─ session_management/                # Session selection
│  ├─ __init__.py
│  ├─ session_provider.py
│  ├─ utc_mapper.py
│  └─ constants.py
│
├─ strategy_management/               # Strategy interface
│  ├─ __init__.py
│  ├─ strategy.py                     # BaseStrategy
│  ├─ registry.py                     # StrategyManager
│  └─ builders.py                     # Strategy builders
│
├─ services/                          # Microservices
│  ├─ discovery/                      # Strategy Discovery Service
│  │  ├─ __init__.py
│  │  ├─ engine.py
│  │  ├─ api.py
│  │  └─ models.py
│  │
│  ├─ optimization/                   # Parameter Optimization Service
│  │  ├─ __init__.py
│  │  ├─ engine.py
│  │  ├─ api.py
│  │  └─ models.py
│  │
│  ├─ validation/                     # Risk Validator Service
│  │  ├─ __init__.py
│  │  ├─ engine.py
│  │  ├─ api.py
│  │  └─ models.py
│  │
│  ├─ deployment/                     # Deployment Manager Service
│  │  ├─ __init__.py
│  │  ├─ engine.py
│  │  ├─ api.py
│  │  └─ models.py
│  │
│  ├─ execution/                      # Trading Execution Service
│  │  ├─ __init__.py
│  │  ├─ engine.py
│  │  ├─ api.py
│  │  └─ models.py
│  │
│  └─ orchestration/                  # Workflow Orchestrator Service
│     ├─ __init__.py
│     ├─ orchestrator.py
│     ├─ api.py
│     └─ models.py
│
├─ integrations/                      # Third-party integrations
│  ├─ langchain_ai/                   # LangChain AI
│  ├─ broker_adapters/                # Broker connections
│  └─ message_queue/                  # Message queue (Kafka/RabbitMQ)
│
├─ persistence/                       # Data persistence
│  ├─ database.py
│  ├─ repositories.py
│  └─ migrations/
│
└─ common/                            # Shared utilities
   ├─ logging.py
   ├─ config.py
   ├─ schemas.py
   └─ exceptions.py
```

---

## API NAMING CONVENTIONS

### Endpoint Structure

```
# Pattern: /api/{version}/{resource}/{action}

# Discovery Service
GET    /api/v1/discovery/strategies              # List available strategies
POST   /api/v1/discovery/start                   # Start discovery
GET    /api/v1/discovery/{job_id}/status        # Get discovery status
GET    /api/v1/discovery/{job_id}/results       # Get discovery results

# Optimization Service
POST   /api/v1/optimization/start                # Start optimization
GET    /api/v1/optimization/{job_id}/status     # Get optimization status
GET    /api/v1/optimization/{job_id}/results    # Get tuned parameters

# Validation Service
POST   /api/v1/validation/start                  # Start validation
GET    /api/v1/validation/{job_id}/status       # Get validation status
GET    /api/v1/validation/{job_id}/decision     # Get approval decision

# Deployment Service
POST   /api/v1/deployment/execute                # Execute deployment
GET    /api/v1/deployment/status                # Get deployment status
GET    /api/v1/deployment/config                # Get deployed config

# Execution Service (formerly ScalpEngine)
GET    /api/v1/execution/status                 # Get live trading status
GET    /api/v1/execution/performance            # Get live P&L
POST   /api/v1/execution/pause                  # Pause trading
POST   /api/v1/execution/resume                 # Resume trading
GET    /api/v1/execution/trades                 # Get trade history
```

---

## CONFIGURATION FILE NAMING

```yaml
# Current
tuned_params.json

# Recommended
strategy_configuration.json
config:
  symbol: "XAUUSD"
  version: 2
  generated_at: "2026-08-25T22:00:00Z"
  session_strategies:
    asian:
      strategy_name: "RSI14"
      indicator_parameters:
        period: 14
      entry_thresholds:
        minimum_signal_strength: 0.35
      exit_configuration:
        stop_loss_multiplier: 1.5
        take_profit_ratio: 2.5
```

---

## ENVIRONMENT VARIABLE NAMING

```bash
# Current
OPTUNA_TRIALS=500
BROKER_API_KEY=xxx

# Recommended
STRATEGYOPS_DISCOVERY_TRIALS=500
STRATEGYOPS_OPTIMIZATION_TRIALS=500
STRATEGYOPS_BROKER_DUKASCOPY_API_KEY=xxx
STRATEGYOPS_LANGCHAIN_API_KEY=xxx
STRATEGYOPS_DATABASE_URL=postgresql://...
STRATEGYOPS_MESSAGE_QUEUE_URL=amqp://...
```

---

## SUMMARY TABLE

| Entity | Current | Recommended | Category |
|--------|---------|-------------|----------|
| Product | ScalpEngine | StrategyOps | Brand |
| Package | src | strategyops | Code |
| Service 1 | Phase 1 | DiscoveryService | Architecture |
| Service 2 | Phase 2 | OptimizationService | Architecture |
| Service 3 | Phase 3 | ValidationService | Architecture |
| Service 4 | Phase 4 | DeploymentService | Architecture |
| Service 5 | - | ExecutionService | Architecture |
| Config | tuned_params.json | strategy_configuration.json | Data |
| Domain | - | strategyops.io | Brand |

---

## TRANSITION PLAN

### Phase 1: Internal Naming (Week 1)
- Update code naming
- Update documentation
- Update variable names

### Phase 2: API Naming (Week 2)
- Update endpoint names
- Update response schemas
- Update error messages

### Phase 3: Brand Launch (Week 3)
- Register domain
- Launch website
- Announce product

---

## PROFESSIONAL PRESENTATION

### Elevator Pitch

"StrategyOps is an intelligent trading strategy operations platform that automates discovery, optimization, and deployment of trading strategies. Using AI-powered analysis and production-grade architecture, StrategyOps helps traders discover optimal strategies, fine-tune parameters, validate performance, and execute with confidence."

### One-Liner

"StrategyOps: Intelligent Strategy Operations for Professional Traders"

### Positioning

**Market:** Professional traders, hedge funds, prop trading firms
**Value:** AI-driven strategy discovery, optimization, and deployment
**Differentiation:** Production-grade architecture, enterprise-ready, fully documented

