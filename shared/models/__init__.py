"""
StrategyOps Shared Models

Core data models and service interfaces for all microservices.
Version: 2.0
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from enum import Enum
import uuid
from datetime import datetime


# ============================================================================
# ENUMS
# ============================================================================

class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    """Strategy approval status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


# ============================================================================
# DISCOVERY SERVICE MODELS
# ============================================================================

@dataclass
class DiscoveryRequest:
    """Discovery service request."""
    symbol: str
    timeframe: str
    session: str
    entry_floors: Dict[str, float]
    max_strategies: Optional[int] = None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DiscoveryResponse:
    """Discovery service response."""
    job_id: str
    status: JobStatus
    symbol: str
    session: str
    discovered_strategies: List[Dict[str, Any]] = field(default_factory=list)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ============================================================================
# OPTIMIZATION SERVICE MODELS
# ============================================================================

@dataclass
class OptimizationRequest:
    """Optimization service request."""
    symbol: str
    session: str
    strategy_name: str
    baseline_params: Dict[str, float]
    baseline_pf: float
    trials: int = 500
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizationResponse:
    """Optimization service response."""
    job_id: str
    status: JobStatus
    symbol: str
    session: str
    tuned_params: Dict[str, float]
    improvement_pct: float = 0.0
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ============================================================================
# VALIDATION SERVICE MODELS
# ============================================================================

@dataclass
class ValidationRequest:
    """Validation service request."""
    symbol: str
    session: str
    strategy_name: str
    tuned_params: Dict[str, float]
    baseline_pf: float
    improvement_threshold: float = 0.02
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ValidationResponse:
    """Validation service response."""
    job_id: str
    status: JobStatus
    symbol: str
    session: str
    approval_status: ApprovalStatus
    approval_reason: Optional[str] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ============================================================================
# DEPLOYMENT SERVICE MODELS
# ============================================================================

@dataclass
class DeploymentRequest:
    """Deployment service request."""
    symbol: str
    validations: Dict[str, ValidationResponse]  # per session
    output_path: str
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DeploymentResponse:
    """Deployment service response."""
    job_id: str
    status: JobStatus
    symbol: str
    deployment_path: str
    approved_sessions: List[str] = field(default_factory=list)
    rejected_sessions: List[str] = field(default_factory=list)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ============================================================================
# EXECUTION SERVICE MODELS
# ============================================================================

@dataclass
class ExecutionRequest:
    """Execution service request."""
    symbol: str
    session: str
    action: str  # "start", "pause", "resume", "stop"
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResponse:
    """Execution service response."""
    job_id: str
    status: JobStatus
    symbol: str
    session: str
    action_result: Dict[str, Any] = field(default_factory=dict)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ============================================================================
# SERVICE INTERFACES
# ============================================================================

class IDiscoveryService(ABC):
    """Discovery service interface."""
    
    @abstractmethod
    async def discover(self, request: DiscoveryRequest) -> DiscoveryResponse:
        """Discover strategies for a session."""
        pass
    
    @abstractmethod
    async def get_status(self, job_id: str) -> DiscoveryResponse:
        """Get discovery job status."""
        pass


class IOptimizationService(ABC):
    """Optimization service interface."""
    
    @abstractmethod
    async def optimize(self, request: OptimizationRequest) -> OptimizationResponse:
        """Optimize strategy parameters."""
        pass
    
    @abstractmethod
    async def get_status(self, job_id: str) -> OptimizationResponse:
        """Get optimization job status."""
        pass


class IValidationService(ABC):
    """Validation service interface."""
    
    @abstractmethod
    async def validate(self, request: ValidationRequest) -> ValidationResponse:
        """Validate optimized strategy."""
        pass
    
    @abstractmethod
    async def get_status(self, job_id: str) -> ValidationResponse:
        """Get validation job status."""
        pass


class IDeploymentService(ABC):
    """Deployment service interface."""
    
    @abstractmethod
    async def deploy(self, request: DeploymentRequest) -> DeploymentResponse:
        """Deploy validated strategies."""
        pass
    
    @abstractmethod
    async def get_status(self, job_id: str) -> DeploymentResponse:
        """Get deployment job status."""
        pass


class IExecutionService(ABC):
    """Execution service interface."""
    
    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute trading action."""
        pass
    
    @abstractmethod
    async def get_status(self, job_id: str) -> ExecutionResponse:
        """Get execution job status."""
        pass


# ============================================================================
# EXCEPTIONS
# ============================================================================

class StrategyOpsException(Exception):
    """Base exception for StrategyOps."""
    pass


class ServiceError(StrategyOpsException):
    """Service-level error."""
    pass


class ValidationError(StrategyOpsException):
    """Validation error."""
    pass


class ConfigurationError(StrategyOpsException):
    """Configuration error."""
    pass


class DataError(StrategyOpsException):
    """Data-related error."""
    pass


__all__ = [
    # Enums
    "JobStatus",
    "ApprovalStatus",
    
    # Request/Response
    "DiscoveryRequest",
    "DiscoveryResponse",
    "OptimizationRequest",
    "OptimizationResponse",
    "ValidationRequest",
    "ValidationResponse",
    "DeploymentRequest",
    "DeploymentResponse",
    "ExecutionRequest",
    "ExecutionResponse",
    
    # Interfaces
    "IDiscoveryService",
    "IOptimizationService",
    "IValidationService",
    "IDeploymentService",
    "IExecutionService",
    
    # Exceptions
    "StrategyOpsException",
    "ServiceError",
    "ValidationError",
    "ConfigurationError",
    "DataError",
]
