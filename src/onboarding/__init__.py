"""Symbol onboarding pipeline.

Single authoritative pipeline for onboarding an MT5 symbol:
discovery (VectorBT + ta-lib + pandas_ta) -> Optuna tuning -> walk-forward validation.
"""

from src.onboarding.pipeline import OnboardingPipeline, onboard

__all__ = ["OnboardingPipeline", "onboard"]
