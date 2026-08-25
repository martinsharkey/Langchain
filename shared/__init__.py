"""
StrategyOps v2.0: Shared Layer

Provides models, interfaces, and utilities shared across all microservices.
"""

from shared.models import (
    JobStatus,
    ApprovalStatus,
    DiscoveryRequest,
    DiscoveryResponse,
    OptimizationRequest,
    OptimizationResponse,
    ValidationRequest,
    ValidationResponse,
    DeploymentRequest,
    DeploymentResponse,
    ExecutionRequest,
    ExecutionResponse,
    IDiscoveryService,
    IOptimizationService,
    IValidationService,
    IDeploymentService,
    IExecutionService,
    StrategyOpsException,
    ServiceError,
    ValidationError,
    ConfigurationError,
    DataError,
)

__all__ = [
    "JobStatus",
    "ApprovalStatus",
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
    "IDiscoveryService",
    "IOptimizationService",
    "IValidationService",
    "IDeploymentService",
    "IExecutionService",
    "StrategyOpsException",
    "ServiceError",
    "ValidationError",
    "ConfigurationError",
    "DataError",
]

__version__ = "2.0.0"
