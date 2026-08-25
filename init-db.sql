-- StrategyOps Database Initialization Script
-- Creates all tables and indexes for production environment

-- Discovery Service Tables
CREATE TABLE IF NOT EXISTS discovery_strategies (
    id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    pf FLOAT NOT NULL,
    wr FLOAT NOT NULL,
    sharpe FLOAT NOT NULL,
    trades INTEGER NOT NULL,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_discovery_symbol (symbol),
    INDEX idx_discovery_session (session)
);

-- Optimization Service Tables
CREATE TABLE IF NOT EXISTS optimization_trials (
    id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    trial_number INTEGER NOT NULL,
    floor_value FLOAT NOT NULL,
    pf FLOAT NOT NULL,
    wr FLOAT NOT NULL,
    sharpe FLOAT NOT NULL,
    trades INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_optimization_symbol (symbol)
);

CREATE TABLE IF NOT EXISTS optimization_results (
    id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    best_floor FLOAT NOT NULL,
    best_pf FLOAT NOT NULL,
    num_trials INTEGER NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_optimization_result_symbol (symbol)
);

-- Validation Service Tables
CREATE TABLE IF NOT EXISTS validation_results (
    id VARCHAR(255) PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    is_valid BOOLEAN NOT NULL,
    pf FLOAT NOT NULL,
    wr FLOAT NOT NULL,
    sharpe FLOAT NOT NULL,
    trades INTEGER NOT NULL,
    edge_percentage FLOAT NOT NULL,
    rules_passed TEXT,
    rules_failed TEXT,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_validation_symbol (symbol)
);

-- Deployment Service Tables
CREATE TABLE IF NOT EXISTS deployed_strategies (
    id VARCHAR(255) PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    floor_value FLOAT NOT NULL,
    deployed_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    metrics TEXT,
    error_message TEXT,
    INDEX idx_deployed_symbol (symbol),
    INDEX idx_deployed_status (status)
);

CREATE TABLE IF NOT EXISTS strategy_snapshots (
    id VARCHAR(255) PRIMARY KEY,
    strategy_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    state_data TEXT NOT NULL,
    reason VARCHAR(50) NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES deployed_strategies(id),
    INDEX idx_snapshot_strategy (strategy_id)
);

-- Orchestration Service Tables
CREATE TABLE IF NOT EXISTS workflow_pipelines (
    id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    session VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    current_stage VARCHAR(50) NOT NULL,
    stages_completed TEXT,
    error_message TEXT,
    INDEX idx_workflow_symbol (symbol),
    INDEX idx_workflow_status (status)
);

CREATE TABLE IF NOT EXISTS workflow_jobs (
    id VARCHAR(255) PRIMARY KEY,
    workflow_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    session VARCHAR(20) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    results TEXT,
    error_message TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflow_pipelines(id),
    INDEX idx_job_workflow (workflow_id),
    INDEX idx_job_status (status)
);

-- Execution Service Tables
CREATE TABLE IF NOT EXISTS live_trades (
    id VARCHAR(255) PRIMARY KEY,
    strategy_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    entry_price FLOAT NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    size FLOAT NOT NULL,
    direction VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    exit_price FLOAT,
    exit_time TIMESTAMP,
    pnl FLOAT,
    pnl_percent FLOAT,
    stop_loss FLOAT,
    take_profit FLOAT,
    FOREIGN KEY (strategy_id) REFERENCES deployed_strategies(id),
    INDEX idx_trade_strategy (strategy_id),
    INDEX idx_trade_symbol (symbol),
    INDEX idx_trade_status (status)
);

CREATE TABLE IF NOT EXISTS execution_stats (
    id VARCHAR(255) PRIMARY KEY,
    strategy_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    session VARCHAR(20) NOT NULL,
    trades_open INTEGER DEFAULT 0,
    trades_closed INTEGER DEFAULT 0,
    trades_winning INTEGER DEFAULT 0,
    total_pnl FLOAT DEFAULT 0.0,
    total_pnl_percent FLOAT DEFAULT 0.0,
    win_rate FLOAT DEFAULT 0.0,
    avg_win FLOAT,
    avg_loss FLOAT,
    max_consecutive_wins INTEGER DEFAULT 0,
    max_consecutive_losses INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES deployed_strategies(id),
    UNIQUE KEY unique_strategy_exec (strategy_id),
    INDEX idx_execution_symbol (symbol)
);

-- Authentication Service Tables
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_username (username),
    INDEX idx_user_email (email)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_apikey_user (user_id),
    INDEX idx_apikey_hash (key_hash)
);

-- Audit Log Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255),
    service VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    status VARCHAR(20) NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_service (service),
    INDEX idx_audit_created (created_at)
);

-- Performance Metrics Table
CREATE TABLE IF NOT EXISTS performance_metrics (
    id VARCHAR(255) PRIMARY KEY,
    service VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_metrics_service (service),
    INDEX idx_metrics_timestamp (timestamp)
);

-- Create default admin user (password: admin123)
INSERT INTO users (id, username, email, password_hash, is_active, is_admin)
VALUES (
    'usr_admin_001',
    'admin',
    'admin@strategyops.local',
    'admin123',
    TRUE,
    TRUE
) ON DUPLICATE KEY UPDATE id=id;

-- Create performance metrics index
CREATE INDEX idx_metrics_service_time ON performance_metrics(service, timestamp);
