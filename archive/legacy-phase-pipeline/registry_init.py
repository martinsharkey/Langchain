"""
Strategy Registry Initialization

Registers all built-in strategies at application startup.

Status: IMPLEMENTATION (Day 4)
"""

import logging

logger = logging.getLogger(__name__)


def register_all_strategies():
    """
    Register all built-in strategies with the global registry.
    
    Called at application startup to populate STRATEGY_REGISTRY.
    """
    from src.strategy_interface import STRATEGY_REGISTRY
    
    strategies_registered = []
    strategies_failed = []
    
    # Register RSI strategies
    try:
        from src.strategies.rsi14 import RSI14Strategy
        STRATEGY_REGISTRY.register(RSI14Strategy())
        strategies_registered.append("RSI14")
    except Exception as e:
        strategies_failed.append(("RSI14", str(e)))
        logger.error(f"Failed to register RSI14: {e}")
    
    # Register Stochastic strategies
    try:
        from src.strategies.stochastic14 import Stochastic14Strategy
        STRATEGY_REGISTRY.register(Stochastic14Strategy())
        strategies_registered.append("Stochastic14")
    except Exception as e:
        strategies_failed.append(("Stochastic14", str(e)))
        logger.error(f"Failed to register Stochastic14: {e}")
    
    # TODO: Register OsMA_Confluence (Day 5)
    # TODO: Register MACD strategies
    # TODO: Register Bollinger Bands strategies
    # TODO: Register ATR strategies
    # ... additional strategies as implemented
    
    logger.info(f"Strategies registered: {len(strategies_registered)}")
    if strategies_failed:
        logger.warning(f"Strategies failed to register: {len(strategies_failed)}")
        for name, error in strategies_failed:
            logger.warning(f"  {name}: {error}")
    
    return strategies_registered, strategies_failed


def get_strategy_summary():
    """
    Get summary of all registered strategies.
    
    Returns:
        Dict with counts and lists by type
    """
    from src.strategy_interface import STRATEGY_REGISTRY
    
    all_strategies = STRATEGY_REGISTRY.list_strategies()
    all_types = STRATEGY_REGISTRY.get_all_types()
    
    summary = {
        'total': len(all_strategies),
        'by_type': {}
    }
    
    for strategy_type in all_types:
        strategies = STRATEGY_REGISTRY.list_strategies_by_type(strategy_type)
        summary['by_type'][strategy_type] = {
            'count': len(strategies),
            'strategies': strategies
        }
    
    return summary


__all__ = [
    'register_all_strategies',
    'get_strategy_summary',
]
