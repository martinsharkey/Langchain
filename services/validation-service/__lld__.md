# LOW LEVEL DESIGN - Validation Service

**Service**: Walk-Forward Validation  
**Port**: 8003  
**Technology**: VectorBT, Statistical Analysis, FastAPI  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready

---

## 📋 Service Overview

The Validation Service performs walk-forward validation on optimized trading parameters. It tests whether parameters tuned on historical data maintain profitability on out-of-sample data, ensuring strategies aren't overfitted. Walk-forward validation divides data into optimization and test periods, simulating real trading conditions.

### Service Responsibilities
- ✅ Perform walk-forward validation
- ✅ Test out-of-sample performance
- ✅ Detect overfitting
- ✅ Generate validation reports
- ✅ Approve/reject parameters
- ✅ Store validation results

---

## 🏗️ Service Architecture

```
services/validation-service/
├── app/                         # API Layer
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # Endpoints
│   │   └── schemas.py          # Request/response models
│   └── __lld__.md              # API design
│
├── core/                        # Business Logic
│   ├── __init__.py
│   ├── validation_engine.py    # Main validation logic
│   ├── walkforward_analyzer.py # Walk-forward analysis
│   ├── overfitting_detector.py # Overfitting detection
│   └── __lld__.md              # Logic design
│
├── models/                      # Data Models
│   ├── __init__.py
│   ├── database.py             # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   └── __lld__.md              # Data design
│
├── tests/
│   ├── __init__.py
│   ├── test_api.py             # 15+ endpoint tests
│   ├── test_core.py            # 20+ logic tests
│   └── conftest.py             # Fixtures
│
├── __lld__.md                  # THIS FILE
├── API_SPEC.md                 # API specification
├── Dockerfile                  # Container definition
├── requirements.txt            # Dependencies
└── README.md                   # Service README
```

---

## 🔌 API Endpoints

### POST /validate/walkforward
**Start walk-forward validation**

Request:
```json
{
  "optimization_study_id": "opt_xyz789",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "1H",
  "best_params": {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26
  },
  "start_date": "2024-01-01",
  "end_date": "2026-08-25",
  "window_size_days": 90
}
```

Response:
```json
{
  "validation_id": "val_abc456",
  "status": "running",
  "created_at": "2026-08-25T15:00:00Z"
}
```

### GET /validate/status/{validation_id}
**Check validation progress**

Response:
```json
{
  "validation_id": "val_abc456",
  "status": "in_progress",
  "completed_windows": 5,
  "total_windows": 12,
  "progress": 42,
  "current_window": "Window 6: 2025-02-01 to 2025-04-30"
}
```

### GET /validate/results/{validation_id}
**Get validation results**

Response:
```json
{
  "validation_id": "val_abc456",
  "status": "complete",
  "approved": true,
  "overfitting_detected": false,
  "metrics": {
    "in_sample_pf": 2.8,
    "out_of_sample_pf": 2.5,
    "pf_degradation": 0.11,
    "in_sample_wr": 0.65,
    "out_of_sample_wr": 0.63,
    "degradation_pct": 3.1
  },
  "recommendations": "Parameters approved. Less than 15% degradation detected.",
  "windows": 12
}
```

### GET /health
**Health check**

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "vectorbt": "ready"
}
```

---

## 📦 Core Components

### 1. validation_engine.py - Main Validation Logic

```python
import logging
from typing import Dict, List
import pandas as pd
from core.walkforward_analyzer import WalkForwardAnalyzer
from core.overfitting_detector import OverfittingDetector

logger = logging.getLogger(__name__)

class ValidationEngine:
    """Main validation engine."""
    
    def __init__(self, db_session):
        self.db = db_session
        self.wf_analyzer = WalkForwardAnalyzer()
        self.overfit_detector = OverfittingDetector()
    
    async def run_validation(
        self,
        optimization_study_id: str,
        symbol: str,
        session: str,
        timeframe: str,
        best_params: Dict,
        start_date: str,
        end_date: str,
        window_size_days: int = 90
    ) -> Dict:
        """Run complete walk-forward validation."""
        
        logger.info(f"Starting validation: {symbol}/{session}/{timeframe}")
        
        # Get historical data
        data = await self.fetch_market_data(symbol, start_date, end_date)
        
        # Create windows
        windows = self.wf_analyzer.create_windows(
            data=data,
            window_size_days=window_size_days
        )
        
        all_results = {
            "in_sample": [],
            "out_of_sample": []
        }
        
        # Test each window
        for i, (opt_data, test_data) in enumerate(windows):
            logger.info(f"Testing window {i+1}/{len(windows)}")
            
            # Optimize on first window
            if i == 0:
                in_sample = await self.backtest_with_params(
                    data=opt_data,
                    params=best_params,
                    symbol=symbol
                )
                all_results["in_sample"].append(in_sample)
            
            # Test on out-of-sample
            out_of_sample = await self.backtest_with_params(
                data=test_data,
                params=best_params,
                symbol=symbol
            )
            all_results["out_of_sample"].append(out_of_sample)
        
        # Analyze results
        analysis = self.wf_analyzer.analyze(all_results)
        
        # Detect overfitting
        overfit_detected = self.overfit_detector.detect(analysis)
        
        # Approve/reject
        approved = not overfit_detected and analysis['avg_oos_pf'] > 1.5
        
        logger.info(f"Validation complete. Approved: {approved}")
        
        return {
            "approved": approved,
            "overfitting_detected": overfit_detected,
            "analysis": analysis,
            "windows": len(windows)
        }
    
    async def fetch_market_data(self, symbol: str, start: str, end: str):
        """Fetch historical market data."""
        # Implementation fetches data from MT5 or historical DB
        pass
    
    async def backtest_with_params(
        self,
        data: pd.DataFrame,
        params: Dict,
        symbol: str
    ) -> Dict:
        """Backtest with given parameters."""
        # Implementation uses VectorBT to backtest
        pass
```

### 2. walkforward_analyzer.py - Walk-Forward Analysis

```python
import pandas as pd
from typing import Tuple, List, Dict

class WalkForwardAnalyzer:
    """Analyze walk-forward validation results."""
    
    def create_windows(
        self,
        data: pd.DataFrame,
        window_size_days: int = 90,
        step_size_days: int = 30
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Create walk-forward windows."""
        windows = []
        
        total_days = (data.index[-1] - data.index[0]).days
        test_size_days = 30
        
        current_start = 0
        
        while current_start + window_size_days + test_size_days <= len(data):
            opt_end = current_start + window_size_days
            test_end = opt_end + test_size_days
            
            opt_data = data.iloc[current_start:opt_end]
            test_data = data.iloc[opt_end:test_end]
            
            windows.append((opt_data, test_data))
            
            current_start += step_size_days
        
        return windows
    
    def analyze(self, results: Dict) -> Dict:
        """Analyze walk-forward results."""
        in_sample = results['in_sample']
        out_of_sample = results['out_of_sample']
        
        return {
            "avg_is_pf": sum(r['pf'] for r in in_sample) / len(in_sample),
            "avg_oos_pf": sum(r['pf'] for r in out_of_sample) / len(out_of_sample),
            "is_std_pf": self._std_dev([r['pf'] for r in in_sample]),
            "oos_std_pf": self._std_dev([r['pf'] for r in out_of_sample]),
            "pf_degradation": self._calculate_degradation(in_sample, out_of_sample),
        }
    
    def _calculate_degradation(self, in_sample, out_of_sample) -> float:
        """Calculate performance degradation."""
        avg_is = sum(r['pf'] for r in in_sample) / len(in_sample)
        avg_oos = sum(r['pf'] for r in out_of_sample) / len(out_of_sample)
        
        if avg_is == 0:
            return 0
        
        return (avg_is - avg_oos) / avg_is
    
    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
```

### 3. overfitting_detector.py - Overfitting Detection

```python
class OverfittingDetector:
    """Detect overfitting in validation results."""
    
    def detect(self, analysis: Dict) -> bool:
        """Detect if overfitting occurred."""
        
        # Check if degradation is excessive
        if analysis['pf_degradation'] > 0.30:  # >30% degradation
            return True
        
        # Check if out-of-sample is highly volatile
        if analysis['oos_std_pf'] > analysis['is_std_pf'] * 2:
            return True
        
        # Check if out-of-sample profit factor is too low
        if analysis['avg_oos_pf'] < 1.3:
            return True
        
        return False
```

---

## 🗄️ Data Models

### ValidationRecord (Database Model)

```python
from sqlalchemy import Column, String, Float, JSON, DateTime, Boolean

class ValidationRecord(Base):
    __tablename__ = "validation_records"
    
    id = Column(String, primary_key=True)
    optimization_study_id = Column(String, ForeignKey("optimization_studies.id"))
    symbol = Column(String, nullable=False)
    session = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    status = Column(String, default="running")
    approved = Column(Boolean, default=False)
    overfitting_detected = Column(Boolean, default=False)
    metrics = Column(JSON)
    windows = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

---

## 🧪 Testing

### Unit Tests (test_core.py)

```python
import pytest
from core.validation_engine import ValidationEngine

@pytest.mark.asyncio
async def test_validation_run(db_session):
    """Test validation execution."""
    engine = ValidationEngine(db_session)
    
    result = await engine.run_validation(
        optimization_study_id="opt_xyz789",
        symbol="BTCUSD",
        session="London",
        timeframe="1H",
        best_params={"rsi_period": 14},
        start_date="2024-01-01",
        end_date="2026-08-25"
    )
    
    assert "approved" in result
    assert "overfitting_detected" in result
    assert "analysis" in result

def test_overfitting_detection():
    """Test overfitting detection."""
    from core.overfitting_detector import OverfittingDetector
    
    detector = OverfittingDetector()
    
    # High degradation
    analysis = {
        "pf_degradation": 0.50,
        "oos_std_pf": 1.0,
        "is_std_pf": 0.5,
        "avg_oos_pf": 2.0
    }
    
    assert detector.detect(analysis) is True
```

### Integration Tests (test_api.py)

```python
@pytest.mark.asyncio
async def test_validate_walkforward(client):
    """Test validation start endpoint."""
    response = await client.post(
        "/validate/walkforward",
        json={
            "optimization_study_id": "opt_xyz789",
            "symbol": "BTCUSD",
            "session": "London",
            "timeframe": "1H",
            "best_params": {"rsi_period": 14},
            "start_date": "2024-01-01",
            "end_date": "2026-08-25"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "validation_id" in data
    assert data["status"] == "running"
```

---

## 🔄 Workflow Integration

**Validation Phase in Strategy Pipeline**:

```
1. Optimization Service completes, provides best parameters
2. Results passed to Validation Service
3. Walk-forward validation tests parameters on out-of-sample data
4. If approved and no overfitting detected, passed to Deployment Service
5. If overfitting detected, rejected or requires reoptimization
```

---

## 📊 Performance Characteristics

- **Typical Validation Time**: 30-60 minutes (for 10-15 windows)
- **Windows Tested**: 10-15 per validation
- **Memory Usage**: 2-4 GB
- **CPU Usage**: 50% (less intensive than optimization)
- **Max Concurrent**: 3-5 validations

---

**Status**: Production Ready  
**Last Updated**: August 25, 2026  
**Maintainer**: @team-dev
