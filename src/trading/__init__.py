"""Trading engine package (real execution + scalping loop)."""

from src.trading.scalp_engine import ScalpEngine, run_scalp_engine

__all__ = ["ScalpEngine", "run_scalp_engine"]
