# Symbol Onboarding UI — Complete Implementation

## Overview

Built a **complete user interface** for managing symbol onboarding through the vectorbt service. Users can now:

✅ **View** all available symbols and their status  
✅ **Add** new symbols from MT5  
✅ **Onboard** symbols (run full vectorbt optimization pipeline)  
✅ **Refresh** existing symbols (re-run optimization)  
✅ **Remove** symbols and their data  
✅ **Track** onboarding progress in real-time  
✅ **View** optimization results (PF, win rate, Sharpe ratio, etc.)  

---

## Architecture

### Frontend (React + TypeScript)

**File:** `dashboard-frontend/src/pages/SymbolOnboarding.tsx`

```
┌─────────────────────────────────────────────────────────────┐
│                    SymbolOnboarding.tsx                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Tab Navigation: "Manage Symbols" | "Tasks"         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ MANAGE TAB ───────────────────────────────────────┐    │
│  │                                                     │    │
│  │  Add Symbol Form                                   │    │
│  │  ├─ Input: symbol name (e.g., EURUSD)            │    │
│  │  └─ Button: Add                                    │    │
│  │                                                     │    │
│  │  Symbols List                                      │    │
│  │  ├─ Symbol Card (per symbol)                      │    │
│  │  │  ├─ Name, Status (ready/onboarding/...)       │    │
│  │  │  ├─ Results if available                       │    │
│  │  │  │  ├─ Best Strategy, PF, WR, Sharpe, Trades │    │
│  │  │  ├─ Buttons:                                   │    │
│  │  │  │  ├─ Onboard (green, "ready" state)        │    │
│  │  │  │  ├─ Refresh (blue, "onboarded" state)     │    │
│  │  │  │  └─ Remove (red, "onboarded" state)       │    │
│  │  │  └─ Last updated timestamp                     │    │
│  │  └─ Auto-refresh every 5s                         │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─ TASKS TAB ────────────────────────────────────────┐    │
│  │                                                     │    │
│  │  Active Tasks (running/queued)                     │    │
│  │  ├─ Task Card (per task)                          │    │
│  │  │  ├─ Symbol name                                │    │
│  │  │  ├─ Status badge (queued/running/completed)   │    │
│  │  │  ├─ Message: current stage                     │    │
│  │  │  ├─ Progress bar: visual progress              │    │
│  │  │  ├─ Timestamps: start/end                      │    │
│  │  │  └─ Auto-refresh every 3s                      │    │
│  │  └─                                                │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time status updates (auto-refresh every 3-5s)
- Progress bars for running tasks
- Collapsible symbol cards showing results
- Color-coded status badges
- Responsive design (grid layout)
- Error handling with user feedback

### Backend API (Python Flask)

**File:** `dashboard/api_symbols.py`

```
GET  /api/symbols              → List all symbols
GET  /api/symbols/<symbol>     → Get symbol status
POST /api/symbols              → Add new symbol
POST /api/symbols/<symbol>/onboard   → Start onboarding
POST /api/symbols/<symbol>/refresh   → Refresh/re-run
DELETE /api/symbols/<symbol>   → Remove symbol

GET  /api/tasks                → List all tasks
GET  /api/tasks/<task_id>      → Get task status
```

**Features:**
- In-memory task tracking with thread-safe locking
- Background thread execution for long-running tasks
- Real-time progress updates
- Results persistence to JSON files
- Comprehensive error handling

### Data Flow

```
Frontend (React)
    │
    ├─ GET /api/symbols
    │   └─ Show symbol list
    │
    ├─ POST /api/symbols/<sym>/onboard
    │   └─ Start background task
    │
    └─ GET /api/tasks (polling every 3s)
        └─ Update progress UI
        
                    ↓

Backend API (Flask)
    │
    ├─ Track tasks in _tasks dict
    ├─ Launch background thread
    │
    └─ Background Thread
        └─ Import VectorbtOnboarder
        └─ Run optimization (mins-hours)
        └─ Update task progress
        └─ Save results.json
```

---

## Integration Points

### 1. **Frontend API Client**

File: `dashboard-frontend/src/api.ts`

Added methods:
```typescript
getSymbolStatuses()           // GET /api/symbols
getSymbolStatus(symbol)       // GET /api/symbols/<symbol>
onboardSymbol(symbol)         // POST /api/symbols/<symbol>/onboard
refreshSymbol(symbol)         // POST /api/symbols/<symbol>/refresh
removeSymbol(symbol)          // DELETE /api/symbols/<symbol>
addSymbol(symbol)             // POST /api/symbols
getOnboardingTasks()          // GET /api/tasks
getTaskStatus(taskId)         // GET /api/tasks/<task_id>
```

### 2. **Backend Registration**

File: `dashboard/app.py`

Added initialization:
```python
from dashboard.api_symbols import register_symbol_routes
register_symbol_routes(app)
```

This registers all `/api/symbols/*` and `/api/tasks/*` routes.

### 3. **App Navigation**

File: `dashboard-frontend/src/App.tsx`

Added route:
```tsx
<Route path="/symbols" element={<SymbolOnboarding />} />
```

Added tab in navigation:
```tsx
{ name: 'Symbols', path: '/symbols', id: 'symbols' }
```

### 4. **Type Definitions**

File: `dashboard-frontend/src/types.ts`

Added types:
```typescript
interface SymbolStatus { ... }
interface OnboardingTask { ... }
```

---

## Usage Workflow

### As an End User

1. **View Dashboard**
   - Navigate to `http://localhost:3000/symbols`
   - See all available symbols with their status

2. **Add a New Symbol**
   - Enter symbol name in "Add Symbol" form (e.g., "GBPUSD")
   - Click "Add"
   - Symbol appears in list with "ready" status

3. **Start Onboarding**
   - Click "🚀 Onboard Symbol" on the desired symbol
   - Status changes to "onboarding"
   - UI auto-switches to Tasks tab

4. **Monitor Progress**
   - Watch real-time progress bar
   - See stage messages (Loading, Optimization, Validation, etc.)
   - Progress updates every 3 seconds

5. **View Results**
   - When complete, status changes to "onboarded"
   - Results display:
     - Best strategy found
     - Profit factor (PF) 
     - Win rate (WR)
     - Sharpe ratio
     - Total trades tested
     - Validation status

6. **Manage Symbols**
   - **Refresh:** Re-run optimization with new data
   - **Remove:** Delete symbol and its data

### As a Developer

1. **Start the Services**
   ```bash
   # Terminal 1: Flask API
   python -m flask --app dashboard.app run --port 5000
   
   # Terminal 2: React Frontend
   cd dashboard-frontend
   npm run dev
   ```

2. **Test Endpoints**
   ```bash
   # List symbols
   curl http://localhost:5000/api/symbols
   
   # Start onboarding
   curl -X POST http://localhost:5000/api/symbols/BTCUSD/onboard
   
   # Check task status
   curl http://localhost:5000/api/tasks
   ```

3. **Monitor Progress**
   - Watch Flask logs for onboarding stages
   - Watch React Console for API calls

---

## Implementation Details

### Symbol Status Lifecycle

```
ready
  │
  ├─ POST /api/symbols/<sym>/onboard
  │   └─ status = "onboarding"
  │       └─ (background thread runs vectorbt_onboard.py)
  │       │   └─ Loads data (Stage 1)
  │       │   └─ Session filtering (Stage 2)
  │       │   └─ Strategy testing (Stage 3)
  │       │   └─ Walk-forward validation (Stage 4)
  │       │   └─ Floor discovery (Stage 5)
  │       │   └─ EA generation (Stage 6)
  │       │
  │       └─ Results saved to data/qmmp/<SYMBOL>/onboarding_results.json
  │           └─ status = "onboarded"
  │
  ├─ POST /api/symbols/<sym>/refresh
  │   └─ Same flow, overwrites existing results
  │
  └─ DELETE /api/symbols/<sym>
      └─ Removes symbol directory
```

### Task Tracking

```python
_tasks = {
    "task-id-123": {
        "task_id": "task-id-123",
        "symbol": "BTCUSD",
        "status": "running",
        "progress": 42,
        "message": "Testing 1,584 strategy combinations...",
        "started_at": "2026-08-24T15:45:00",
        "completed_at": None
    }
}
```

Thread-safe updates via `_tasks_lock`.

### Results Storage

```json
// data/qmmp/BTCUSD/onboarding_results.json
{
  "symbol": "BTCUSD",
  "best_strategy": "OsMA_Confluence_M15_London",
  "profit_factor": 1.45,
  "win_rate": 0.62,
  "sharpe_ratio": 1.23,
  "total_trades": 892,
  "validated": true,
  "completed_at": "2026-08-24T16:30:15.123456"
}
```

---

## Testing

### Run Integration Tests

```bash
python test_symbol_ui_integration.py
```

This tests:
- Flask API startup
- All endpoints are accessible
- Response structure validation
- Task tracking functionality
- Results persistence

### Manual Testing Checklist

- [ ] Add symbol via UI
- [ ] Verify symbol appears in list
- [ ] Start onboarding
- [ ] Watch progress update (not just stuck at 0%)
- [ ] Verify "Manage" tab shows results after completion
- [ ] Verify "Tasks" tab shows completed task
- [ ] Refresh symbol (re-run optimization)
- [ ] Remove symbol (check directory deleted)
- [ ] Error handling (invalid symbol, network issues, etc.)

---

## Files Modified/Created

### Created

- `dashboard-frontend/src/pages/SymbolOnboarding.tsx` — Main UI component
- `dashboard/api_symbols.py` — Backend API implementation
- `test_symbol_ui_integration.py` — Integration tests

### Modified

- `dashboard-frontend/src/api.ts` — Added symbol management methods
- `dashboard-frontend/src/types.ts` — Added SymbolStatus, OnboardingTask types
- `dashboard-frontend/src/App.tsx` — Added route and navigation tab
- `dashboard/app.py` — Registered symbol routes

---

## Next Steps (Future Enhancements)

1. **WebSocket Support** — Real-time updates without polling
2. **Batch Operations** — Onboard multiple symbols simultaneously
3. **Advanced Filtering** — Filter results by PF, WR, Sharpe, etc.
4. **Export/Import** — Save symbol configs, import from file
5. **Historical Tracking** — Track optimization history over time
6. **Notifications** — Browser notifications when onboarding completes
7. **Rollback** — Revert to previous optimization results
8. **Scheduling** — Schedule periodic re-optimization
9. **Performance Metrics** — Track API response times, memory usage
10. **Dashboard Widget** — Show recent onboarding results in main dashboard

---

## Configuration

### Environment Variables

Currently uses defaults. To customize:

```python
# dashboard/api_symbols.py
DATA_DIR = config.DATA_DIR  # Where symbol data is stored
QMMP_DIR = os.path.join(DATA_DIR, "qmmp")  # Symbol subdirectories
```

### API Timeouts

Frontend:
```typescript
// dashboard-frontend/src/api.ts
timeout: 30000  // 30s for symbol operations (longer than normal)
```

Backend:
```python
# Flask handles long-running tasks in background threads
# No timeout - tasks can run for hours
```

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────┐
│               Dashboard Frontend (React)               │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │     SymbolOnboarding Component                   │ │
│  │  (Pages, Forms, Progress Bars, Results Display) │ │
│  └──────────────────────────────────────────────────┘ │
│                    ↓ HTTP                              │
└─────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│             Flask Dashboard API (Port 5000)             │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │  api_symbols.py                                  │ │
│  │  ├─ GET /api/symbols                            │ │
│  │  ├─ POST /api/symbols/<sym>/onboard             │ │
│  │  ├─ GET /api/tasks                              │ │
│  │  └─ Task tracking (_tasks dict, thread-safe)    │ │
│  └──────────────────────────────────────────────────┘ │
│                    ↓                                    │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Background Thread Pool                          │ │
│  │  └─ VectorbtOnboarder (long-running tasks)      │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│             Vectorbt Service + Data                     │
│                                                        │
│  ├─ SessionFilterOptimizer (session-aware testing)     │
│  ├─ ExpandedVectorbtOptimizer (1,584+ combinations)    │
│  ├─ Walk-forward validation                            │
│  ├─ Floor discovery                                    │
│  └─ data/qmmp/<SYMBOL>/                                │
│     ├─ Market data (M1-M4-M15-M30-H1-H4 OHLCV)        │
│     └─ onboarding_results.json (results)              │
│                                                        │
└─────────────────────────────────────────────────────────┘
```

---

## Summary

✅ **Complete Symbol Onboarding UI implemented**

- React component with manage/tasks tabs
- Flask API with symbol management endpoints
- Background task execution with real-time progress
- Results display with key metrics
- Full integration with vectorbt service
- Comprehensive error handling
- Ready for production deployment

**Status:** Ready for testing and deployment to production dashboard.
