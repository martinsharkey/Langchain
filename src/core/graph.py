"""
LangGraph state graph definition for the multi-agent trading system.
Defines the state structure and routing logic for the agent team.
"""

from typing import Annotated, TypedDict, Literal, Optional
from typing_extensions import NotRequired
from langgraph.graph import MessagesState
from langgraph.managed import IsLastStep


# ─── Extended Agent State ───────────────────────────────────

class TradingState(MessagesState):
    """Extended state for the trading bot with additional fields."""
    
    # Environment status
    environment_ready: bool = False
    
    # Team status
    team_members: list[str] = []
    active_agent: Optional[str] = None
    
    # Trading status
    trading_active: bool = False
    current_position: Optional[dict] = None
    portfolio: dict = {}
    
    # Strategy
    current_strategy: Optional[str] = None
    strategy_params: dict = {}
    
    # Performance
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    profit_loss: float = 0.0
    
    # Control
    phase: str = "init"  # init, setup, team_building, research, strategy, execution, reflection
    iteration: int = 0
    max_iterations: int = 100


# ─── Agent Routing ──────────────────────────────────────────

def route_based_on_phase(state: TradingState) -> str:
    """
    Route to the appropriate agent based on the current phase.
    This allows the main agent to delegate to sub-agents.
    """
    phase = state.get("phase", "init")
    
    if phase == "setup":
        return "env_setup_agent"
    elif phase == "research":
        return "research_agent"
    elif phase == "strategy":
        return "strategy_agent"
    elif phase == "risk_check":
        return "risk_agent"
    elif phase == "execution":
        return "execution_agent"
    elif phase == "reflection":
        return "main_agent"  # Main agent handles reflection
    else:
        return "main_agent"


def should_continue(state: TradingState) -> Literal["continue", "end"]:
    """Determine if the trading loop should continue."""
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 100)
    
    if iteration >= max_iterations:
        return "end"
    
    # Check for stop conditions
    portfolio = state.get("portfolio", {})
    drawdown = portfolio.get("drawdown", 0)
    if drawdown > 20:  # Stop if drawdown exceeds 20%
        return "end"
    
    return "continue"
