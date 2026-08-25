"""
Database Models for all StrategyOps Services

Uses SQLAlchemy ORM for PostgreSQL persistence across all microservices.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timezone
import json

Base = declarative_base()


# ==================== DISCOVERY SERVICE ====================

class DiscoveryStrategy(Base):
    """Discovered strategy record."""
    __tablename__ = "discovery_strategies"
    
    id = Column(String(255), primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    session = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    pf = Column(Float, nullable=False)
    wr = Column(Float, nullable=False)
    sharpe = Column(Float, nullable=False)
    trades = Column(Integer, nullable=False)
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'strategy_name': self.strategy_name,
            'pf': self.pf,
            'wr': self.wr,
            'sharpe': self.sharpe,
            'trades': self.trades
        }


# ==================== OPTIMIZATION SERVICE ====================

class OptimizationTrial(Base):
    """Optimization trial result."""
    __tablename__ = "optimization_trials"
    
    id = Column(String(255), primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    session = Column(String(20), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    timeframe = Column(String(10), nullable=False)
    trial_number = Column(Integer, nullable=False)
    floor_value = Column(Float, nullable=False)
    pf = Column(Float, nullable=False)
    wr = Column(Float, nullable=False)
    sharpe = Column(Float, nullable=False)
    trades = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class OptimizationResult(Base):
    """Optimization result summary."""
    __tablename__ = "optimization_results"
    
    id = Column(String(255), primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    session = Column(String(20), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    timeframe = Column(String(10), nullable=False)
    best_floor = Column(Float, nullable=False)
    best_pf = Column(Float, nullable=False)
    num_trials = Column(Integer, nullable=False)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==================== VALIDATION SERVICE ====================

class ValidationResult(Base):
    """Strategy validation result."""
    __tablename__ = "validation_results"
    
    id = Column(String(255), primary_key=True)
    strategy_name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    session = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    is_valid = Column(Boolean, nullable=False)
    pf = Column(Float, nullable=False)
    wr = Column(Float, nullable=False)
    sharpe = Column(Float, nullable=False)
    trades = Column(Integer, nullable=False)
    edge_percentage = Column(Float, nullable=False)
    rules_passed = Column(Text, nullable=True)  # JSON list
    rules_failed = Column(Text, nullable=True)  # JSON list
    validated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==================== DEPLOYMENT SERVICE ====================

class DeployedStrategy(Base):
    """Live deployed strategy."""
    __tablename__ = "deployed_strategies"
    
    id = Column(String(255), primary_key=True)
    strategy_name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    session = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False)  # active, paused, stopped, error
    floor_value = Column(Float, nullable=False)
    deployed_at = Column(DateTime, nullable=False)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    metrics = Column(Text, nullable=True)  # JSON dict
    error_message = Column(Text, nullable=True)


class StrategySnapshot(Base):
    """Point-in-time strategy snapshot."""
    __tablename__ = "strategy_snapshots"
    
    id = Column(String(255), primary_key=True)
    strategy_id = Column(String(255), ForeignKey('deployed_strategies.id'), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    state_data = Column(Text, nullable=False)  # JSON
    reason = Column(String(50), nullable=False)  # pre_optimization, pre_tuning, backup


# ==================== ORCHESTRATION SERVICE ====================

class WorkflowPipeline(Base):
    """Workflow pipeline orchestration."""
    __tablename__ = "workflow_pipelines"
    
    id = Column(String(255), primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    session = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # active, paused, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    current_stage = Column(String(50), nullable=False)  # discovery, optimization, validation, deployment
    stages_completed = Column(Text, nullable=True)  # JSON list
    error_message = Column(Text, nullable=True)


class WorkflowJob(Base):
    """Job within a workflow."""
    __tablename__ = "workflow_jobs"
    
    id = Column(String(255), primary_key=True)
    workflow_id = Column(String(255), ForeignKey('workflow_pipelines.id'), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    session = Column(String(20), nullable=False)
    stage = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # pending, running, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    results = Column(Text, nullable=True)  # JSON
    error_message = Column(Text, nullable=True)


# ==================== EXECUTION SERVICE ====================

class LiveTrade(Base):
    """Live trade record."""
    __tablename__ = "live_trades"
    
    id = Column(String(255), primary_key=True)
    strategy_id = Column(String(255), ForeignKey('deployed_strategies.id'), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    size = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # long, short
    status = Column(String(20), nullable=False)  # pending, open, closed, cancelled, error
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)


class StrategyExecutionStats(Base):
    """Strategy execution statistics."""
    __tablename__ = "execution_stats"
    
    id = Column(String(255), primary_key=True)
    strategy_id = Column(String(255), ForeignKey('deployed_strategies.id'), nullable=False)
    symbol = Column(String(20), nullable=False)
    session = Column(String(20), nullable=False)
    trades_open = Column(Integer, default=0)
    trades_closed = Column(Integer, default=0)
    trades_winning = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    total_pnl_percent = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    avg_win = Column(Float, nullable=True)
    avg_loss = Column(Float, nullable=True)
    max_consecutive_wins = Column(Integer, default=0)
    max_consecutive_losses = Column(Integer, default=0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ==================== AUTH SERVICE ====================

class User(Base):
    """User account."""
    __tablename__ = "users"
    
    id = Column(String(255), primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class APIKey(Base):
    """API key for service authentication."""
    __tablename__ = "api_keys"
    
    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used = Column(DateTime, nullable=True)


# ==================== DATABASE INITIALIZATION ====================

def init_db(database_url: str):
    """Initialize database with all tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Get database session."""
    Session = sessionmaker(bind=engine)
    return Session()


__all__ = [
    'Base',
    'DiscoveryStrategy',
    'OptimizationTrial',
    'OptimizationResult',
    'ValidationResult',
    'DeployedStrategy',
    'StrategySnapshot',
    'WorkflowPipeline',
    'WorkflowJob',
    'LiveTrade',
    'StrategyExecutionStats',
    'User',
    'APIKey',
    'init_db',
    'get_session'
]
