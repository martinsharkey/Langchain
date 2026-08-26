# LOW LEVEL DESIGN - src/config Module

**Module**: Configuration Management  
**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active

---

## 📋 Module Overview

The `src/config` module manages all application configuration, environment variables, and settings across different deployment environments (local, staging, production).

### Module Responsibilities
- ✅ Load environment variables
- ✅ Validate configuration
- ✅ Provide configuration to all services
- ✅ Support multi-environment setup

---

## 🏗️ Module Architecture

```
src/config/
├── __init__.py              # Module exports
├── settings.py              # Pydantic settings
├── environment.py           # Environment variable parsing
└── __lld__.md              # This document
```

---

## 📦 Components

### 1. settings.py - Configuration Management

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings."""
    
    # Server
    app_name: str = "StrategyOps v2.0"
    app_version: str = "2.0.0"
    debug: bool = False
    environment: str = "production"
    
    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 40
    
    # Redis
    redis_url: str
    redis_cache_ttl: int = 3600
    
    # Services
    discovery_service_url: str = "http://localhost:8001"
    optimization_service_url: str = "http://localhost:8002"
    validation_service_url: str = "http://localhost:8003"
    deployment_service_url: str = "http://localhost:8004"
    orchestration_service_url: str = "http://localhost:8005"
    execution_service_url: str = "http://localhost:8006"
    
    # Trading
    max_leverage: float = 10.0
    min_profit_factor: float = 1.5
    max_drawdown: float = -0.20
    
    # Timeouts
    discovery_timeout: int = 1800
    optimization_timeout: int = 3600
    validation_timeout: int = 900
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()
```

### 2. environment.py - Environment Variable Parsing

```python
import os
from typing import Optional

def get_env(key: str, default: Optional[str] = None) -> str:
    """Get environment variable with validation."""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

def get_env_int(key: str, default: Optional[int] = None) -> int:
    """Get integer environment variable."""
    value = os.getenv(key)
    if value is None:
        if default is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return default
    return int(value)

def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")
```

### 3. __init__.py - Module Exports

```python
"""Configuration module exports."""

from .settings import Settings, settings
from .environment import get_env, get_env_int, get_env_bool

__all__ = [
    "Settings",
    "settings",
    "get_env",
    "get_env_int",
    "get_env_bool",
]
```

---

## 🔄 Usage Examples

### Using Settings
```python
from src.config import settings

# Access configuration
db_url = settings.database_url
redis_url = settings.redis_url
debug = settings.debug

# Use in services
if settings.debug:
    logging.basicConfig(level=logging.DEBUG)
```

### Environment Validation
```python
from src.config import get_env, get_env_int

# Get required env var
api_key = get_env("API_KEY")

# Get with default
environment = get_env("ENVIRONMENT", "production")

# Get integer
port = get_env_int("PORT", 8000)
```

---

## 🧪 Testing

**Location**: `tests/unit/test_config.py`

```python
def test_settings_load():
    """Test settings load correctly."""
    from src.config import settings
    assert settings.app_name == "StrategyOps v2.0"
    assert settings.debug is False

def test_settings_validation():
    """Test settings validation."""
    with pytest.raises(ValidationError):
        Settings(database_url="")  # Required field
```

---

**Status**: Production Ready
