# StrategyOps v2.0 - COMPLETE DOCUMENTATION INDEX

**Status**: 90% Production Ready  
**Last Updated**: August 25, 2026  
**Total Documentation**: 60+ pages, 50,000+ words  

---

## 📚 QUICK NAVIGATION

### 🚀 Getting Started (5 minutes)
1. **[TEAM_ONBOARDING_GUIDE.md](docs/TEAM_ONBOARDING_GUIDE.md)** - Start here! 5-minute setup guide
2. **[WORKSPACE_RULES.md](WORKSPACE_RULES.md)** - File placement rules (MANDATORY)
3. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development workflow

### 🏗️ Architecture & Design
1. **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design overview
2. **[ADRs/](architecture/ADRs/)** - Architecture Decision Records
3. **[services/__lld__.md](services/__lld__.md)** - Microservices overview

### 📖 Module Documentation
1. **[src/core/__lld__.md](src/core/__lld__.md)** - Data models and core logic
2. **[src/config/__lld__.md](src/config/__lld__.md)** - Configuration management
3. **[src/integrations/__lld__.md](src/integrations/__lld__.md)** - External integrations (MT5, DB)
4. **[src/utils/__lld__.md](src/utils/__lld__.md)** - Helper functions and utilities

### 🔧 Service Documentation
Each service has complete documentation:

1. **[Discovery Service](services/discovery-service/__lld__.md)** (Port 8001)
   - Strategy discovery via backtesting
   - Indicator combinations testing
   - Performance ranking

2. **[Optimization Service](services/optimization-service/__lld__.md)** (Port 8002)
   - Parameter optimization with Optuna
   - Bayesian search
   - Constraint handling

3. **[Validation Service](services/validation-service/__lld__.md)** (Port 8003)
   - Walk-forward validation
   - Overfitting detection
   - Out-of-sample testing

4. **[Deployment Service](services/deployment-service/__lld__.md)** (Port 8004)
   - Live strategy deployment
   - MT5 integration
   - Rollback procedures

5. **[Orchestration Service](services/orchestration-service/__lld__.md)** (Port 8005)
   - Workflow coordination
   - Task scheduling
   - Service communication

6. **[Execution Service](services/execution-service/__lld__.md)** (Port 8006)
   - Live trade execution
   - Position management
   - Real-time monitoring

### 📋 Operations & Deployment
1. **[DEPLOYMENT_PROCEDURES.md](docs/DEPLOYMENT_PROCEDURES.md)** - All deployment procedures
2. **[DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)** - Detailed development guide
3. **[docker-compose.yml](docker-compose.yml)** - Local development setup
4. **[infrastructure/](infrastructure/)** - Production infrastructure

### 🛠️ Tools & Scripts
1. **[Makefile](Makefile)** - 40+ development commands
2. **[pre-commit-validate.py](tools/pre-commit-validate.py)** - File placement enforcement
3. **[tools/](tools/)** - Development utilities

---

## 📊 DOCUMENTATION BY PURPOSE

### For New Team Members
**Start Here** → **TEAM_ONBOARDING_GUIDE.md** (5 minutes)
- Environment setup
- Quick start
- First contribution

Then read:
- WORKSPACE_RULES.md (file placement)
- CONTRIBUTING.md (development workflow)

### For Developers Writing Code
- **Module code?** → Read corresponding `src/*/_ _lld__.md`
- **Service code?** → Read `services/{service}/__lld__.md`
- **API endpoints?** → Read `services/{service}/API_SPEC.md`
- **Database queries?** → Read `{service}/models/__lld__.md`

### For DevOps/Operations
**Start Here** → **DEPLOYMENT_PROCEDURES.md**
- Local deployment
- Staging deployment (Kubernetes)
- Production deployment
- Rollback procedures
- Troubleshooting

Then:
- Review `infrastructure/` directory
- Check `docker-compose.yml` for local setup
- Review `Dockerfile` in each service

### For Architects/Tech Leads
- **ARCHITECTURE.md** - System design
- **ADRs/** - Decision records
- **services/__lld__.md** - Service patterns
- **WORKSPACE_RULES.md** - Governance model

### For API Integration
- **[docs/API.md](docs/API.md)** - Complete API reference
- Each `services/{service}/API_SPEC.md` - Service-specific API
- Example requests in each service's `__lld__.md`

---

## 🗂️ DOCUMENTATION STRUCTURE

```
langchain/
├── WORKSPACE_RULES.md               ← File placement rules (START HERE)
├── CONTRIBUTING.md                  ← Development workflow
├── README.md                        ← Project README
│
├── docs/
│   ├── TEAM_ONBOARDING_GUIDE.md    ← 5-min quick start (START HERE)
│   ├── DEVELOPMENT_GUIDE.md        ← Detailed guide
│   ├── ARCHITECTURE.md              ← System design
│   ├── API.md                       ← API reference
│   ├── DEPLOYMENT_PROCEDURES.md    ← All deployments
│   ├── SESSION_2_COMPLETION_SUMMARY.md
│   └── images/                      ← Documentation images
│
├── architecture/
│   ├── ADRs/
│   │   ├── 001-microservices-architecture.md
│   │   ├── 002-service-communication.md
│   │   └── ...
│   └── STANDARDS.md                 ← Coding standards
│
├── src/
│   ├── core/__lld__.md              ← Data models documentation
│   ├── config/__lld__.md            ← Config management documentation
│   ├── integrations/__lld__.md      ← Integration documentation
│   ├── utils/__lld__.md             ← Utilities documentation
│   └── (actual code)
│
├── services/
│   ├── __lld__.md                   ← Services overview
│   ├── discovery-service/
│   │   ├── __lld__.md               ← Service documentation
│   │   ├── API_SPEC.md              ← Service API
│   │   ├── app/__lld__.md           ← API layer design
│   │   ├── core/__lld__.md          ← Logic design
│   │   ├── models/__lld__.md        ← Data models
│   │   └── (actual code)
│   ├── optimization-service/
│   │   └── (same structure)
│   ├── validation-service/
│   │   └── (same structure)
│   ├── deployment-service/
│   │   └── (same structure)
│   ├── orchestration-service/
│   │   └── (same structure)
│   └── execution-service/
│       └── (same structure)
│
├── tests/
│   ├── unit/                        ← Fast unit tests
│   ├── integration/                 ← Service integration tests
│   └── e2e/                         ← Complete workflow tests
│
├── infrastructure/
│   ├── docker-compose.yml           ← Local development
│   ├── k8s/                         ← Kubernetes manifests
│   └── terraform/                   ← Infrastructure as Code
│
├── tools/
│   ├── pre-commit-validate.py       ← Enforcement script
│   └── (other utilities)
│
└── Makefile                         ← 40+ development commands
```

---

## 🎯 DOCUMENTATION COMPLETENESS

| Component | Status | % | Location |
|-----------|--------|---|----------|
| Core Architecture | ✅ Complete | 100% | ARCHITECTURE.md |
| Module Design | ✅ Complete | 100% | src/*/\_\_lld\_\_.md |
| Service Design | ✅ Complete | 100% | services/*/__lld__.md |
| API Documentation | ✅ Complete | 100% | docs/API.md + API_SPEC.md |
| Deployment | ✅ Complete | 100% | DEPLOYMENT_PROCEDURES.md |
| Development Guide | ✅ Complete | 100% | DEVELOPMENT_GUIDE.md |
| Team Onboarding | ✅ Complete | 100% | TEAM_ONBOARDING_GUIDE.md |
| Code Standards | ✅ Complete | 100% | CONTRIBUTING.md |
| Governance | ✅ Complete | 100% | WORKSPACE_RULES.md |
| Testing Framework | ✅ Complete | 100% | tests/ |
| Database Models | ✅ Complete | 100% | services/*/models/__lld__.md |
| API Gateway | ⏳ Pending | 0% | - |
| Performance Tests | ⏳ Pending | 0% | - |

---

## 🚀 READING ORDER BY ROLE

### Backend Developer
1. TEAM_ONBOARDING_GUIDE.md (5 min)
2. WORKSPACE_RULES.md (5 min)
3. CONTRIBUTING.md (10 min)
4. Relevant service __lld__.md (15 min)
5. DEVELOPMENT_GUIDE.md (20 min)
**Total**: 55 minutes to full productivity

### Frontend Developer
1. TEAM_ONBOARDING_GUIDE.md (5 min)
2. docs/API.md (15 min)
3. services/*/API_SPEC.md (20 min)
4. CONTRIBUTING.md (10 min)
5. Example code in __lld__.md files (15 min)
**Total**: 65 minutes to full productivity

### DevOps Engineer
1. TEAM_ONBOARDING_GUIDE.md (5 min)
2. DEPLOYMENT_PROCEDURES.md (30 min)
3. infrastructure/ directory (20 min)
4. docker-compose.yml (10 min)
5. services/*/Dockerfile (15 min)
**Total**: 80 minutes to full productivity

### QA/Test Engineer
1. TEAM_ONBOARDING_GUIDE.md (5 min)
2. tests/ directory structure (10 min)
3. DEVELOPMENT_GUIDE.md - testing section (15 min)
4. Service __lld__.md - test examples (20 min)
**Total**: 50 minutes to full productivity

### Tech Lead/Architect
1. ARCHITECTURE.md (30 min)
2. ADRs/ directory (20 min)
3. services/__lld__.md (20 min)
4. WORKSPACE_RULES.md (10 min)
5. Each service __lld__.md (30 min)
**Total**: 110 minutes to full knowledge

---

## 📞 FINDING SPECIFIC INFORMATION

### How do I...?

**...set up my environment?**
→ TEAM_ONBOARDING_GUIDE.md

**...understand the file structure?**
→ WORKSPACE_RULES.md

**...write code that fits the standards?**
→ CONTRIBUTING.md + relevant src/*/\_\_lld\_\_.md

**...understand how Discovery Service works?**
→ services/discovery-service/__lld__.md

**...understand all 6 services?**
→ services/__lld__.md (overview) + each service's __lld__.md

**...deploy to production?**
→ DEPLOYMENT_PROCEDURES.md

**...find API endpoints?**
→ docs/API.md + services/{service}/API_SPEC.md

**...understand the database schema?**
→ services/{service}/models/__lld__.md

**...run tests?**
→ DEVELOPMENT_GUIDE.md (testing section) + Makefile

**...understand workflow orchestration?**
→ services/orchestration-service/__lld__.md

**...track real-time execution?**
→ services/execution-service/__lld__.md

---

## ✅ DOCUMENTATION QUALITY STANDARDS

Every documentation file includes:

✅ **Clear Purpose** - What this document covers  
✅ **Quick Start** - Get started in 5 minutes  
✅ **Architecture** - System/module design  
✅ **Components** - All components documented  
✅ **Code Examples** - 50+ examples per module  
✅ **API Endpoints** - All endpoints with examples  
✅ **Database Models** - Schema with relationships  
✅ **Testing** - Unit and integration test examples  
✅ **Deployment** - How to deploy/use  
✅ **Troubleshooting** - Common issues and fixes  

---

## 🎓 LEARNING RESOURCES

### External Tools & Frameworks

**FastAPI**
- [Official Docs](https://fastapi.tiangolo.com/)
- Examples in every service __lld__.md

**VectorBT**
- Examples in discovery-service/__lld__.md
- Used for backtesting

**Optuna**
- Examples in optimization-service/__lld__.md
- Used for parameter optimization

**Pydantic**
- Examples in every service __lld__.md
- Used for data validation

**SQLAlchemy**
- Examples in every service __lld__.md
- Used for database ORM

**Celery**
- Examples in orchestration-service/__lld__.md
- Used for task scheduling

**MetaTrader5**
- Examples in src/integrations/__lld__.md
- Used for trading platform integration

---

## 🔄 CONTINUOUS IMPROVEMENT

This documentation is living. To update:

1. **Report Issue** → Create GitHub issue
2. **Propose Update** → Reference this index
3. **Submit PR** → Update relevant __lld__.md
4. **Get Reviewed** → Tech lead reviews
5. **Merged** → Automatically deployed

---

## 📈 DOCUMENTATION METRICS

- **Total Pages**: 60+
- **Total Words**: 50,000+
- **Code Examples**: 250+
- **API Endpoints**: 40+
- **Database Models**: 12+
- **Services**: 6 (100% documented)
- **Modules**: 5 (100% documented)
- **Procedures**: 25+
- **Standards**: 15+
- **Decision Records**: 5+

---

**This index is your gateway to complete StrategyOps v2.0 documentation.**

**Start with TEAM_ONBOARDING_GUIDE.md and build from there.**

**Ready to contribute?** Fork, read docs, submit PR.

---

*Last Updated: August 25, 2026*  
*Status: Complete and Current*
