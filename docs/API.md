# API Documentation

Complete REST API reference for all StrategyOps v2.0 microservices.

---

## Discovery Service API

**Base URL**: `http://localhost:8001`

### Endpoints

#### Start Discovery
```http
POST /discover/start
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "backtest_period": "1y",
  "indicators": ["Bollinger_Bands", "OsMA", "ADX"],
  "lookback_period": 100
}
```

**Response (202 Accepted)**:
```json
{
  "task_id": "disc_abc123def456",
  "status": "queued",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "created_at": "2026-08-25T10:00:00Z"
}
```

---

#### Check Discovery Status
```http
GET /discover/status/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "disc_abc123def456",
  "status": "in_progress",
  "progress": 0.45,
  "current_indicator": "Bollinger_Bands",
  "indicators_completed": 1,
  "indicators_total": 3,
  "estimated_completion": "2026-08-25T10:15:00Z"
}
```

**Status Values**: `queued`, `in_progress`, `complete`, `failed`, `cancelled`

---

#### Get Discovery Results
```http
GET /discover/results/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "disc_abc123def456",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "backtest_period": "1y",
  "discoveries": [
    {
      "rank": 1,
      "indicators": ["Bollinger_Bands", "OsMA"],
      "performance": {
        "profit_factor": 1.67,
        "win_rate": 0.58,
        "total_return": 0.23,
        "max_drawdown": -0.12,
        "sharpe_ratio": 1.45,
        "trades": 245
      },
      "parameters": {
        "bb_period": 20,
        "bb_deviation": 2.0,
        "osma_fast": 12,
        "osma_slow": 26,
        "osma_signal": 9
      }
    },
    {
      "rank": 2,
      "indicators": ["ADX", "OsMA"],
      "performance": {
        "profit_factor": 1.52,
        "win_rate": 0.55,
        "total_return": 0.19,
        "max_drawdown": -0.15,
        "sharpe_ratio": 1.23,
        "trades": 198
      },
      "parameters": {
        "adx_period": 14,
        "osma_fast": 12,
        "osma_slow": 26,
        "osma_signal": 9
      }
    }
  ],
  "completed_at": "2026-08-25T10:12:30Z"
}
```

---

#### Stop Discovery
```http
POST /discover/stop/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "disc_abc123def456",
  "status": "cancelled",
  "message": "Discovery cancelled successfully"
}
```

---

## Optimization Service API

**Base URL**: `http://localhost:8002`

### Endpoints

#### Start Optimization
```http
POST /optimize/start
Content-Type: application/json

{
  "discovery_task_id": "disc_abc123def456",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "indicators": ["Bollinger_Bands", "OsMA"],
  "optimization_algorithm": "tpe",
  "n_trials": 100,
  "timeout_seconds": 3600,
  "parameter_ranges": {
    "bb_period": [10, 50],
    "bb_deviation": [1.0, 3.0],
    "osma_fast": [8, 14],
    "osma_slow": [20, 30],
    "osma_signal": [7, 12]
  }
}
```

**Response (202 Accepted)**:
```json
{
  "task_id": "opt_xyz789",
  "status": "queued",
  "symbol": "BTCUSD",
  "session": "London",
  "n_trials": 100,
  "created_at": "2026-08-25T10:30:00Z"
}
```

---

#### Check Optimization Status
```http
GET /optimize/status/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "opt_xyz789",
  "status": "in_progress",
  "progress": 0.62,
  "trials_completed": 62,
  "trials_total": 100,
  "best_profit_factor": 1.89,
  "best_trial": 18,
  "estimated_completion": "2026-08-25T11:30:00Z"
}
```

---

#### Get Optimization Results
```http
GET /optimize/results/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "opt_xyz789",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "optimization_algorithm": "tpe",
  "trials_completed": 100,
  "best_trial": {
    "trial_id": 18,
    "parameters": {
      "bb_period": 22,
      "bb_deviation": 2.1,
      "osma_fast": 11,
      "osma_slow": 25,
      "osma_signal": 8
    },
    "metrics": {
      "profit_factor": 1.89,
      "win_rate": 0.61,
      "total_return": 0.31,
      "max_drawdown": -0.10,
      "sharpe_ratio": 1.78
    }
  },
  "trial_history": [
    {
      "trial_id": 1,
      "profit_factor": 1.23,
      "timestamp": "2026-08-25T10:31:00Z"
    },
    ...
  ],
  "completed_at": "2026-08-25T11:25:00Z"
}
```

---

#### Compare Parameter Sets
```http
POST /optimize/compare
Content-Type: application/json

{
  "parameter_sets": [
    {
      "name": "Best Trial",
      "parameters": {"bb_period": 22, "bb_deviation": 2.1, ...}
    },
    {
      "name": "Manual Config",
      "parameters": {"bb_period": 20, "bb_deviation": 2.0, ...}
    }
  ],
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15"
}
```

**Response (200 OK)**:
```json
{
  "comparison": [
    {
      "name": "Best Trial",
      "profit_factor": 1.89,
      "win_rate": 0.61,
      "total_return": 0.31,
      "max_drawdown": -0.10
    },
    {
      "name": "Manual Config",
      "profit_factor": 1.67,
      "win_rate": 0.58,
      "total_return": 0.23,
      "max_drawdown": -0.12
    }
  ]
}
```

---

## Validation Service API

**Base URL**: `http://localhost:8003`

### Endpoints

#### Start Walk-Forward Validation
```http
POST /validate/walkforward
Content-Type: application/json

{
  "optimization_task_id": "opt_xyz789",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "parameters": {
    "bb_period": 22,
    "bb_deviation": 2.1,
    "osma_fast": 11,
    "osma_slow": 25,
    "osma_signal": 8
  },
  "in_sample_period": "6m",
  "out_of_sample_period": "3m"
}
```

**Response (202 Accepted)**:
```json
{
  "task_id": "val_pqr123",
  "status": "queued",
  "symbol": "BTCUSD",
  "created_at": "2026-08-25T12:00:00Z"
}
```

---

#### Check Validation Status
```http
GET /validate/status/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "val_pqr123",
  "status": "in_progress",
  "progress": 0.38,
  "windows_completed": 2,
  "windows_total": 5,
  "in_sample_pf": 1.89,
  "out_of_sample_pf": 1.72,
  "pf_degradation": 0.09
}
```

---

#### Get Validation Results
```http
GET /validate/results/{task_id}
```

**Response (200 OK)**:
```json
{
  "task_id": "val_pqr123",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "validation_status": "PASSED",
  "summary": {
    "in_sample_pf": 1.89,
    "out_of_sample_pf": 1.72,
    "pf_degradation": 0.09,
    "pf_improvement": 0.13,
    "original_pf": 1.52
  },
  "windows": [
    {
      "window_id": 1,
      "in_sample_metrics": {
        "profit_factor": 1.95,
        "win_rate": 0.62,
        "trades": 156,
        "total_return": 0.28
      },
      "out_of_sample_metrics": {
        "profit_factor": 1.78,
        "win_rate": 0.59,
        "trades": 89,
        "total_return": 0.19
      }
    },
    ...
  ],
  "passed": true,
  "reason": "PF improved by 13% vs original parameters",
  "completed_at": "2026-08-25T12:45:00Z"
}
```

---

## Deployment Service API

**Base URL**: `http://localhost:8004`

### Endpoints

#### Deploy Strategy
```http
POST /deploy/strategy
Content-Type: application/json

{
  "validation_task_id": "val_pqr123",
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "parameters": {
    "bb_period": 22,
    "bb_deviation": 2.1,
    "osma_fast": 11,
    "osma_slow": 25,
    "osma_signal": 8
  },
  "risk_config": {
    "max_position_size": 1.0,
    "stop_loss_pips": 50,
    "take_profit_pips": 150
  },
  "environment": "production"
}
```

**Response (201 Created)**:
```json
{
  "deployment_id": "dep_mnc456",
  "strategy_id": "strat_001",
  "version": 1,
  "status": "deployed",
  "symbol": "BTCUSD",
  "environment": "production",
  "deployed_at": "2026-08-25T13:00:00Z",
  "deployed_by": "system"
}
```

---

#### Check Deployment Status
```http
GET /deploy/status/{deployment_id}
```

**Response (200 OK)**:
```json
{
  "deployment_id": "dep_mnc456",
  "strategy_id": "strat_001",
  "version": 1,
  "status": "active",
  "symbol": "BTCUSD",
  "environment": "production",
  "health": {
    "last_update": "2026-08-25T13:15:00Z",
    "uptime": 900,
    "errors": 0,
    "warnings": 0
  },
  "metrics": {
    "signals_generated": 45,
    "trades_executed": 12,
    "winning_trades": 8,
    "current_pnl": 245.50
  }
}
```

---

#### Get Active Deployments
```http
GET /deploy/active
```

**Response (200 OK)**:
```json
{
  "deployments": [
    {
      "deployment_id": "dep_mnc456",
      "strategy_id": "strat_001",
      "symbol": "BTCUSD",
      "session": "London",
      "status": "active",
      "deployed_at": "2026-08-25T13:00:00Z"
    },
    {
      "deployment_id": "dep_rst789",
      "strategy_id": "strat_002",
      "symbol": "EURUSD",
      "session": "New York",
      "status": "active",
      "deployed_at": "2026-08-24T15:30:00Z"
    }
  ]
}
```

---

#### Rollback Deployment
```http
POST /deploy/rollback/{deployment_id}
Content-Type: application/json

{
  "target_version": 0,
  "reason": "Performance degradation"
}
```

**Response (200 OK)**:
```json
{
  "deployment_id": "dep_mnc456",
  "status": "rolled_back",
  "previous_version": 1,
  "current_version": 0,
  "rolled_back_at": "2026-08-25T13:30:00Z"
}
```

---

## Orchestration Service API

**Base URL**: `http://localhost:8005`

### Endpoints

#### Start Complete Pipeline
```http
POST /workflows/start
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "session": "London",
  "timeframe": "M15",
  "pipeline": "discovery-optimization-validation-deployment",
  "discovery_config": {
    "backtest_period": "1y",
    "indicators": ["Bollinger_Bands", "OsMA"]
  },
  "optimization_config": {
    "n_trials": 100,
    "algorithm": "tpe"
  },
  "validation_config": {
    "in_sample_period": "6m",
    "out_of_sample_period": "3m"
  }
}
```

**Response (202 Accepted)**:
```json
{
  "workflow_id": "wf_abc123",
  "status": "queued",
  "pipeline": "discovery-optimization-validation-deployment",
  "created_at": "2026-08-25T14:00:00Z"
}
```

---

#### Check Workflow Status
```http
GET /workflows/status/{workflow_id}
```

**Response (200 OK)**:
```json
{
  "workflow_id": "wf_abc123",
  "status": "in_progress",
  "current_stage": "optimization",
  "overall_progress": 0.35,
  "stages": {
    "discovery": {
      "status": "complete",
      "progress": 1.0,
      "task_id": "disc_abc123def456",
      "completed_at": "2026-08-25T14:15:00Z"
    },
    "optimization": {
      "status": "in_progress",
      "progress": 0.62,
      "task_id": "opt_xyz789",
      "estimated_completion": "2026-08-25T15:00:00Z"
    },
    "validation": {
      "status": "pending",
      "progress": 0.0
    },
    "deployment": {
      "status": "pending",
      "progress": 0.0
    }
  }
}
```

---

#### Get Workflow Results
```http
GET /workflows/results/{workflow_id}
```

**Response (200 OK)**:
```json
{
  "workflow_id": "wf_abc123",
  "status": "complete",
  "summary": {
    "symbol": "BTCUSD",
    "session": "London",
    "timeframe": "M15",
    "started_at": "2026-08-25T14:00:00Z",
    "completed_at": "2026-08-25T16:30:00Z",
    "duration_seconds": 9000
  },
  "results": {
    "discovery": {
      "indicators": ["Bollinger_Bands", "OsMA"],
      "profit_factor": 1.67,
      "win_rate": 0.58
    },
    "optimization": {
      "best_profit_factor": 1.89,
      "best_trial": 18,
      "parameters": {...}
    },
    "validation": {
      "status": "PASSED",
      "pf_improvement": 0.13
    },
    "deployment": {
      "deployment_id": "dep_mnc456",
      "status": "active",
      "version": 1
    }
  }
}
```

---

## Execution Service API

**Base URL**: `http://localhost:8006`

### Endpoints

#### Execute Trade
```http
POST /execute/trade
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "direction": "buy",
  "volume": 0.1,
  "entry_price": 45250.50,
  "stop_loss": 45100.00,
  "take_profit": 45500.00,
  "strategy_id": "strat_001",
  "signal_id": "sig_xyz123"
}
```

**Response (201 Created)**:
```json
{
  "trade_id": "tradeexec_001",
  "symbol": "BTCUSD",
  "direction": "buy",
  "volume": 0.1,
  "entry_price": 45250.50,
  "status": "executed",
  "executed_at": "2026-08-25T16:45:00Z"
}
```

---

#### Get Current Positions
```http
GET /execute/positions
```

**Response (200 OK)**:
```json
{
  "positions": [
    {
      "trade_id": "tradeexec_001",
      "symbol": "BTCUSD",
      "direction": "buy",
      "volume": 0.1,
      "entry_price": 45250.50,
      "current_price": 45380.00,
      "profit_loss": 129.50,
      "profit_loss_pct": 0.0029,
      "opened_at": "2026-08-25T16:45:00Z"
    }
  ]
}
```

---

#### Get Trading Performance
```http
GET /execute/performance
```

**Response (200 OK)**:
```json
{
  "summary": {
    "total_trades": 145,
    "winning_trades": 89,
    "losing_trades": 56,
    "win_rate": 0.614,
    "profit_factor": 1.67,
    "total_pnl": 2345.50,
    "max_drawdown": -0.08
  },
  "daily": [
    {
      "date": "2026-08-25",
      "trades": 12,
      "pnl": 245.30,
      "win_rate": 0.67
    }
  ]
}
```

---

## Error Responses

### Standard Error Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid parameter range",
    "details": {
      "field": "parameter_ranges.bb_period",
      "issue": "Upper bound (50) less than lower bound (100)"
    },
    "timestamp": "2026-08-25T10:00:00Z"
  }
}
```

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| VALIDATION_ERROR | 400 | Invalid input parameters |
| NOT_FOUND | 404 | Resource not found |
| CONFLICT | 409 | Resource already exists |
| INTERNAL_ERROR | 500 | Server error |
| SERVICE_UNAVAILABLE | 503 | Service temporarily unavailable |
| TIMEOUT | 504 | Operation timeout |

---

## Rate Limiting

All endpoints are rate limited:
- **Burst**: 100 requests per minute
- **Sustained**: 1000 requests per hour
- **Headers**: 
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`

---

**API Version**: 2.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready
