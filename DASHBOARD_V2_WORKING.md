# Dashboard v2 - Working & Ready

## Status: ✅ FULLY WORKING

The dashboard is **fully functional and ready to use immediately**.

## Quick Start

### Option 1: Test First (Recommended)
```bash
cd langchain
python test_dashboard.py
```

You should see:
```
✅ ALL TESTS PASSED

Dashboard is ready at:
   http://localhost:5000/v2

To start the server, run:
   python app.py
```

### Option 2: Start Server
```bash
cd langchain
python app.py
```

Then open browser: **http://localhost:5000/v2**

## What You'll See

### Dashboard Shows:
- **Header KPIs**: Total Strategies (4), Validated (4), Avg PF (1.18), Best PF (1.45)
- **Strategies Table**: OsMA_Confluence, Bollinger_OsMA with metrics
- **Click to Details**: Side panel shows backtest results, regime edges, live performance
- **Edge Discovery Page**: Vectorbt validation status per symbol

### Sample Data Included
The dashboard comes with sample strategy data in `data/strategy_config.json`:
- **XAUUSD**: OsMA_Confluence (PF: 1.45, WR: 52%)
- **BTCUSD**: Bollinger_OsMA (PF: 1.18, WR: 59%) + OsMA_Confluence fallback
- **GER40**: OsMA_Confluence (PF: 1.01, WR: 48%)

## File Locations

| What | Where |
|------|-------|
| **Dashboard HTML** | `dashboard/templates/dashboard_v2.html` |
| **Backend API** | `src/dashboard/api_v2.py` + `routes_v2.py` |
| **Sample Config** | `data/strategy_config.json` |
| **Test Script** | `test_dashboard.py` |
| **Old Dashboard** | `dashboard/templates/dashboard.html` (still works at /) |

## Architecture

```
Browser (http://localhost:5000/v2)
        ↓
   Flask App
        ↓
   ├─ Serves: dashboard_v2.html (HTML/CSS/JS)
   └─ API Routes: /api/v2/* (JSON)
        ↓
   Backend aggregates data from:
   ├─ strategy_config.json
   ├─ edge_weights.json (if present)
   └─ trading_experience.db (if present)
```

## Routes Available

| Route | Purpose | Status |
|-------|---------|--------|
| `GET /v2` | Dashboard HTML | ✅ Working |
| `GET /api/v2/strategies` | List all strategies | ✅ Working |
| `GET /api/v2/summary` | KPI summary | ✅ Working |
| `GET /api/v2/vectorbt/discovery` | Edge discovery status | ✅ Working |
| `GET /api/v2/backtest/results` | Backtest data | ✅ Working |
| `GET /` | Old dashboard | ✅ Still works |

## Testing Directly

```bash
# Test dashboard HTML loads
curl http://localhost:5000/v2

# Test API
curl http://localhost:5000/api/v2/summary

# Pretty-print API response
curl http://localhost:5000/api/v2/strategies | python -m json.tool
```

## Features

✅ **Strategy Comparison**
- Table with all metrics (PF, WR, Sharpe, Trades)
- Click-to-detail side panel
- Filter by validated status

✅ **Live Data**
- Reads from strategy_config.json
- Shows backtest results (PF, win rate, Sharpe ratio)
- Shows regime edges per strategy
- Shows live performance if trades exist

✅ **Professional UI**
- Dark theme
- Responsive layout
- Color-coded metrics (green for good, red for bad)
- Auto-refresh every 30 seconds

✅ **Zero Build Step**
- Vanilla JavaScript
- CDN-based libraries (Axios, Chart.js)
- Works immediately

## Troubleshooting

### Dashboard loads but shows no data
- ✅ This is normal! Sample config is in `data/strategy_config.json`
- Once edge_discovery runs, it auto-generates this file
- You can also manually create it (example provided)

### Getting errors in browser console
1. Open Developer Tools (F12)
2. Go to Console tab
3. Look for red errors
4. Check Network tab for failed API calls

### API returns 404 errors
- Make sure Flask app is running
- Check URL is: `http://localhost:5000/v2`
- Not: `http://localhost:5000/v2/api/v2/...` (no /v2 twice)

### No strategies showing
- This is expected on first run
- Add test data: see `data/strategy_config.json` structure
- Or run edge_discovery to auto-generate

## How It Works

1. **You start Flask app**: `python app.py`
2. **Dashboard loads**: Browser opens `http://localhost:5000/v2`
3. **Page initializes**: JavaScript loads and queries `/api/v2/strategies`
4. **API processes**: Backend reads `strategy_config.json` and `edge_weights.json`
5. **Data displayed**: Dashboard renders strategy table with metrics
6. **Auto-refresh**: KPIs update every 30 seconds

## Data Sources

The dashboard reads from (all optional, graceful fallback):

| Source | Format | Purpose |
|--------|--------|---------|
| `strategy_config.json` | JSON | Strategy metadata + performance |
| `edge_weights.json` | JSON | Vectorbt discoveries |
| `trading_experience.db` | SQLite | Live trade history |
| `bot_status.json` | JSON | Engine state (optional) |

If a source is missing, the dashboard gracefully shows available data.

## Integration with Your System

The dashboard automatically integrates with:
- ✅ Edge discovery pipeline (reads generated config)
- ✅ Optuna optimization (shows study links, trial counts)
- ✅ Trading engine (reads live trades from DB)
- ✅ Vectorbt backtesting (reads validation results)

As your edge_discovery runs and generates new data, the dashboard updates automatically.

## Next Steps

### To See Real Data:
1. Run edge_discovery sweep
2. Dashboard auto-generates `strategy_config.json`
3. Refresh browser → See live metrics

### To Add Features:
- **Charts**: Chart.js is already included (CDN)
- **Export**: Add CSV/PDF download buttons
- **Alerts**: Add toast notifications
- **Optimization Page**: Add Optuna trial visualization
- **Live Page**: Add account state panel

## Examples

### Run Test
```bash
python test_dashboard.py
```

### Start Dashboard
```bash
python app.py
# Then: http://localhost:5000/v2
```

### Query API
```bash
# Get all strategies
curl http://localhost:5000/api/v2/strategies | python -m json.tool

# Get summary KPIs
curl http://localhost:5000/api/v2/summary

# Get discovery status  
curl http://localhost:5000/api/v2/vectorbt/discovery
```

## Success Checklist

- ✅ Test script passes (shows "ALL TESTS PASSED")
- ✅ Flask app starts without errors
- ✅ Dashboard loads at http://localhost:5000/v2
- ✅ Strategies table shows data
- ✅ Click strategy → Details appear
- ✅ Header KPIs show numbers
- ✅ API endpoints respond with JSON

---

**The dashboard is ready. Open it now!**

```bash
python app.py
# Then: http://localhost:5000/v2
```
