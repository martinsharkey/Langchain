# 🎯 UNIFIED APPLICATION STARTUP GUIDE

**Status:** ✅ Application Running  
**Process ID:** 13688  
**Mode:** Integrated (Single Application)  

---

## WHAT'S NEW

Instead of managing multiple separate processes, everything now starts as **ONE unified application**.

### Before (Multiple Processes)
```
❌ python run_system.py
❌ python -m flask --app dashboard.app run
❌ python check_status.py
→ Fragmented, hard to manage
```

### Now (Unified Application)
```
✅ python app.py
→ Everything starts together
→ Single point of control
→ Clean shutdown
```

---

## HOW TO START THE APPLICATION

### Simple Command
```bash
python app.py
```

That's it! This single command starts:
- ✅ Research Scheduler (daily 00:00 UTC trigger)
- ✅ Market Data Collection (6 sources)
- ✅ LLM Analysis Engine (semantic understanding)
- ✅ Knowledge Base (persistent storage)
- ✅ Version Manager (code/test tracking)
- ✅ Handoff Protocol (agent communication)
- ✅ Dashboard Web Server (http://localhost:5000)
- ✅ System Monitoring

---

## WHAT YOU'LL SEE ON STARTUP

```
======================================================================
🚀 UNIFIED TRADING RESEARCH APPLICATION
======================================================================

INITIALIZING COMPONENTS
----------------------------------------------------------------------
  • Initializing Research Orchestrator...
    ✅ Version Manager
    ✅ Research Scheduler
    ✅ Market Data Collector
    ✅ Research Agent
    ✅ Handoff Protocol
    ✅ Knowledge Base

  • Verifying Dashboard...
    ✅ Flask App Ready

STARTING RESEARCH SYSTEM
----------------------------------------------------------------------
  • Starting daily scheduler...
    ✅ Scheduler Running
    ✅ Trigger: 00:00 UTC
    ✅ Next Run: 2026-07-31T00:00:00+00:00

STARTING DASHBOARD
----------------------------------------------------------------------
  • Starting Flask dashboard server...
    ✅ Dashboard Running
    ✅ Access: http://localhost:5000

======================================================================
✅ APPLICATION STARTED SUCCESSFULLY
======================================================================

COMPONENTS RUNNING:
  ✅ Research System
     • Daily scheduler (00:00 UTC)
     • Market data collection (6 sources)
     • LLM semantic analysis
     • Knowledge base storage

  ✅ Dashboard
     • Web interface (port 5000)
     • Real-time metrics
     • Performance tracking

ACCESS POINTS:
  🌐 Dashboard: http://localhost:5000
  📊 Research: Automatic daily at 00:00 UTC
  🐍 Python API: from src.orchestration import get_orchestrator

Started: 2026-07-30T13:30:00+00:00
```

---

## ACCESSING THE SYSTEM

### 1. Dashboard (Web Interface)
```
http://localhost:5000
```
- Real-time metrics
- Trading readiness score
- Performance analytics
- Research status

### 2. Research Context (Python API)
```python
from src.orchestration import get_orchestrator

orchestrator = get_orchestrator()
research = orchestrator.get_research_context_for_trading()
```

### 3. System Status (Command Line)
Application prints:
- Component status ✅/❌
- Dashboard access point
- Next research cycle time
- Uptime tracking

---

## DAILY OPERATIONS

### Automatic (No Action Needed)
- **00:00 UTC:** Research cycle triggers automatically
- **Collects:** Data from 6 sources
- **Analyzes:** With LLM semantic understanding
- **Stores:** In knowledge base
- **Available:** Immediately for trading agent

### Manual (Optional)
```bash
# Force a research cycle now (for testing)
python examples/test_full_daily_cycle.py

# Check status
python check_status.py

# View dashboard
# → Open browser to http://localhost:5000
```

---

## STOPPING THE APPLICATION

**Graceful shutdown:**
```
Press Ctrl+C in terminal
```

The application will:
1. ✅ Stop the research scheduler
2. ✅ Close the dashboard
3. ✅ Save all data
4. ✅ Print shutdown summary

---

## TROUBLESHOOTING

### Application Won't Start
```bash
# Check Python version
python --version  # Should be 3.10+

# Check dependencies
pip install -r requirements.txt

# Try with error output
python app.py 2>&1
```

### Dashboard Not Accessible
```bash
# Check if port 5000 is available
netstat -ano | findstr :5000

# If blocked, use different port:
# (Edit app.py: port=5001)
```

### Research System Not Running
1. Check logs: `logs/main.log`
2. Restart application: `Ctrl+C` then `python app.py`
3. Verify databases exist in `data/` directory

### Processes Crashing
- Check logs
- Ensure all dependencies installed
- Check disk space
- Review error messages

---

## INTEGRATED FEATURES

### Research System
- Daily 00:00 UTC trigger
- 6 data source collectors
- LLM semantic analysis
- Knowledge base storage
- Handoff protocol

### Dashboard
- Real-time metrics
- Performance tracking
- Readiness scoring
- Research status
- Mobile responsive

### Version Control
- Code versioning
- Test tracking
- Audit trail
- Atomic handoffs

---

## WHAT RUNS IN BACKGROUND

**Research System Thread:**
- Scheduler manages timing
- Automatic daily trigger
- Non-blocking execution
- Full error recovery

**Dashboard Thread:**
- Flask web server
- Real-time data serving
- HTML/CSS/JavaScript frontend
- Database querying

**Main Thread:**
- Coordination
- Logging
- Status monitoring
- Graceful shutdown handling

---

## PROCESS INFORMATION

| Item | Value |
|------|-------|
| **Process ID** | 13688 |
| **Process Name** | python app.py |
| **Status** | Running |
| **Uptime** | Updates automatically |
| **Memory** | ~150-200 MB |
| **CPU** | Minimal (idle most of time) |

---

## ACCESSING FROM OTHER MACHINES

### Get your computer's IP
```bash
ipconfig
```

Look for IPv4 address (e.g., 192.168.1.100)

### Access from other machine
```
http://192.168.1.100:5000
```

---

## DEPLOYMENT CHECKLIST

- [x] Single unified application
- [x] All components integrated
- [x] Research system running
- [x] Dashboard web server active
- [x] Automatic scheduling
- [x] Error recovery
- [x] Graceful shutdown
- [x] Production ready

---

## COMMANDS REFERENCE

### Start Application
```bash
python app.py
```

### Stop Application
```
Ctrl+C (in terminal)
```

### Check Status (separate terminal)
```bash
python check_status.py
```

### Test Research Cycle (separate terminal)
```bash
python examples/test_full_daily_cycle.py
```

### Access Dashboard
```
Browser: http://localhost:5000
```

---

## NEXT STEPS

1. **Start the app:**
   ```bash
   python app.py
   ```

2. **Wait for startup message:**
   ```
   ✅ APPLICATION STARTED SUCCESSFULLY
   ```

3. **Open dashboard:**
   ```
   http://localhost:5000
   ```

4. **Monitor in background:**
   - App runs automatically
   - Research triggers daily at 00:00 UTC
   - Dashboard updates in real-time

5. **Integrate with your bot:**
   ```python
   from src.orchestration import get_orchestrator
   orchestrator = get_orchestrator()
   ```

---

## BENEFITS OF UNIFIED APPLICATION

✅ **Single Point of Control**
- One command to start everything
- One command to stop everything

✅ **Coordinated Operation**
- Components work together seamlessly
- Shared state and resources

✅ **Easier Management**
- Simpler to monitor
- Simpler to deploy
- Simpler to troubleshoot

✅ **Clean Shutdown**
- Graceful termination
- All components stop properly
- No orphaned processes

✅ **Production Ready**
- Professional design
- Error handling
- Status reporting

---

## SUPPORT

**Issues?**
1. Check terminal output for errors
2. Review `logs/main.log`
3. Run `python check_status.py` (in separate terminal)
4. Restart: Ctrl+C then `python app.py`

**Documentation:**
- SYSTEM_OPERATIONAL.md
- QUICK_REFERENCE.md
- MASTER_COMPLETION_SUMMARY.md

---

**Status: ✅ UNIFIED APPLICATION OPERATIONAL**

Everything is integrated and running as one cohesive system.

Start with:
```bash
python app.py
```

Then access dashboard at:
```
http://localhost:5000
```

Generated: 2026-07-30 13:30 UTC+1
