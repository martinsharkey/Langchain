"""
Discovery Service Configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional


class DiscoverySettings(BaseSettings):
    """Discovery service settings."""
    
    # Service
    SERVICE_NAME: str = "discovery-service"
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8001
    
    # Database
    DATABASE_URL: str = "sqlite:///./discovery.db"
    
    # Discovery parameters
    MIN_TRADES_FOR_VALID_BACKTEST: int = 10
    MAX_STRATEGIES_TO_TEST: Optional[int] = None
    BACKTEST_TIMEOUT_SECONDS: int = 300
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = DiscoverySettings()
