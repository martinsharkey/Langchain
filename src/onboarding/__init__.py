"""Symbol onboarding pipeline.

Single authoritative pipeline for onboarding an MT5 symbol:
discovery (VectorBT + ta-lib + pandas_ta) -> Optuna tuning -> walk-forward validation.

The orchestrator (OnboardingOrchestrator) is the entry point for the wizard.
"""

from src.onboarding.orchestrator import OnboardingOrchestrator, INIT_CASH
from src.onboarding.pipeline import OnboardingPipeline, onboard

__all__ = ["OnboardingOrchestrator", "OnboardingPipeline", "onboard", "INIT_CASH"]
