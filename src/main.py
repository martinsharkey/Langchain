"""DEPRECATED (#46) -- legacy full-agent architecture. NOT used at runtime; app.py + scalp_engine are the live path. Kept for reference only; do not revive without fixing src/core/agent.py (I2) and re-testing. """
#!/usr/bin/env python3
"""
LangChain ReAct Agent â€” XAUUSD MetaTrader 5 Trading Bot
with Meta-Strategy Learning System

This is the main entry point for the autonomous trading agent.
The agent:
1. Builds its environment (venv, dependencies)
2. Creates a team of specialized sub-agents
3. Analyzes XAUUSD market data
4. Uses a meta-strategy system with 7 strategies + RAG learning
5. Dynamically selects the best strategy for current market conditions
6. Executes trades on MetaTrader 5
7. Learns from every trade via vector store (ChromaDB) + experience DB
8. Reflects on performance and self-improves

Usage:
    python src/main.py
    
Environment:
    - Requires at least one LLM API key in .env file (Groq, Gemini, etc.)
    - MetaTrader 5 running under Wine (macOS) or natively (Windows)
    - Python 3.10+
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import validate_config, SYMBOL, DATA_DIR, TRADING_MODE, is_live_mode
from src.core.agent import create_main_agent
from src.core.llm import get_groq_llm, get_configured_providers
from src.mt5.connector import get_connector
from src.mt5.data import get_rates, get_last_price
from src.mt5.account import get_account_info
from src.strategies.xauusd_strategy import XAUUSDStrategy
from src.agents.env_setup_agent import create_env_setup_agent
from src.agents.research_agent import create_research_agent
from src.agents.strategy_agent import create_strategy_agent
from src.agents.risk_agent import create_risk_agent
from src.agents.execution_agent import create_execution_agent
from src.utils.logger import get_logger, console

# â”€â”€â”€ Learning Module Imports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from src.learning.vector_store import PatternVectorStore
from src.learning.strategy_registry import StrategyRegistry
from src.learning.pattern_matcher import PatternMatcher
from src.learning.experience_db import ExperienceDatabase
from src.learning.meta_strategy_agent import MetaStrategyAgent
from src.learning.knowledge_base import KnowledgeBase
from src.learning.curiosity_agent import CuriosityAgent

logger = get_logger("main")


# â”€â”€â”€ FIX #3: OPEN POSITION CLASS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class OpenPosition:
    """
    Track an open trading position for outcome calculation.
    
    Monitors whether trade has hit stop loss, take profit, or timeout.
    Calculates real P&L when position closes.
    """
    
    def __init__(self, 
                 trade_id: str,
                 action: str,  # "buy" or "sell"
                 entry_price: float,
                 entry_time: datetime,
                 stop_loss: float,
                 take_profit: float,
                 position_size: float,
                 decision: dict):
        self.trade_id = trade_id
        self.action = action
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position_size = position_size
        self.decision = decision
        
    def check_if_closed(self, current_price: float) -> tuple[bool, str, float]:
        """
        Check if position should be closed.
        
        Returns:
            (is_closed, reason, profit_loss)
            reason: "tp" (take profit), "sl" (stop loss), "timeout", or None
            profit_loss: P&L in dollars
        """
        if self.action == "buy":
            if current_price >= self.take_profit:
                pnl = (current_price - self.entry_price) * self.position_size
                return True, "tp", pnl
            elif current_price <= self.stop_loss:
                pnl = (current_price - self.entry_price) * self.position_size
                return True, "sl", pnl
        else:  # sell
            if current_price <= self.take_profit:
                pnl = (self.entry_price - current_price) * self.position_size
                return True, "tp", pnl
            elif current_price >= self.stop_loss:
                pnl = (self.entry_price - current_price) * self.position_size
                return True, "sl", pnl
        
        # Check timeout (24 hours)
        elapsed = (datetime.now() - self.entry_time).total_seconds() / 3600
        if elapsed > 24:
            pnl = self._calculate_pnl(current_price)
            return True, "timeout", pnl
        
        return False, None, 0.0
    
    def _calculate_pnl(self, exit_price: float) -> float:
        """Calculate P&L for exit price."""
        if self.action == "buy":
            return (exit_price - self.entry_price) * self.position_size
        else:
            return (self.entry_price - exit_price) * self.position_size


class TradingBot:
    """
    Main trading bot orchestrator.
    
    Manages the lifecycle of the agent team, the meta-strategy learning system,
    and the trading loop. Includes self-reflection and improvement mechanisms.
    ALL actions are logged with full visibility.
    """
    
    def __init__(self):
        self.main_agent = None
        self.connector = None
        self.strategy = None          # Legacy single-strategy (kept for backward compat)
        self.meta_strategy = None     # Meta-strategy agent with RAG learning
        self.curiosity_agent = None   # NEW: Curiosity-driven knowledge acquisition
        self.team = {}
        self.running = False
        self.iteration = 0
        self.max_iterations = 100
        self.performance_history = []
        self.status_path = os.path.join(DATA_DIR, "bot_status.json")
        
        # â† FIX #3: Position tracking
        self.open_positions = []  # Track open trades for outcome calculation
        
        # Learning module instances
        self.vector_store = None
        self.strategy_registry = None
        self.pattern_matcher = None
        self.experience_db = None
        self.knowledge_base = None    # NEW: Persistent knowledge store
        
        console.print("\n[bold cyan]â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—[/bold cyan]")
        console.print("[bold cyan]â•‘[/bold cyan]  [bold yellow]XAUUSD Trading Bot â€” Meta-Strategy Learning System[/bold yellow]  [bold cyan]â•‘[/bold cyan]")
        console.print("[bold cyan]â•‘[/bold cyan]  [bold]Mission:[/bold] Learn to trade Gold through curiosity       [bold cyan]â•‘[/bold cyan]")
        console.print("[bold cyan]â•‘[/bold cyan]  [bold]LLM:[/bold] LiteLLM multi-provider (Kilo Gateway, Groq)     [bold cyan]â•‘[/bold cyan]")
        console.print("[bold cyan]â•‘[/bold cyan]  [bold]Learning:[/bold] 7 strategies + RAG + SQLite + Curiosity    [bold cyan]â•‘[/bold cyan]")
        console.print("[bold cyan]â•‘[/bold cyan]  [bold]Connection:[/bold] Live MT5 â€” Real market data             [bold cyan]â•‘[/bold cyan]")
        console.print("[bold cyan]â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•[/bold cyan]")
        console.print()
    
    # â”€â”€â”€ VISIBILITY: All steps are printed to console â”€â”€â”€â”€â”€â”€â”€
    
    def _print_step(self, step: str, status: str = "pending"):
        """Print a step with status indicator."""
        icons = {"running": "ðŸ”„", "done": "âœ…", "failed": "âŒ", "pending": "â³", "thinking": "ðŸ¤”"}
        icon = icons.get(status, "â€¢")
        console.print(f"  {icon} {step}")
    
    def _print_agent_thought(self, thought: str):
        """Print the agent's reasoning/thinking."""
        console.print(f"     [dim]{thought}[/dim]")
    
    def _print_code_block(self, label: str, code: str):
        """Print a code block that the agent wrote."""
        console.print(f"     [bold cyan]{label}:[/bold cyan]")
        for line in code.split('\n')[:10]:
            console.print(f"       [dim]{line}[/dim]")
        if len(code.split('\n')) > 10:
            console.print(f"       [dim]... ({len(code.split('\n')) - 10} more lines)[/dim]")
    
    def _print_tool_call(self, tool_name: str, args: dict):
        """Print a tool call the agent is making."""
        console.print(f"     [bold magenta]Tool:[/bold magenta] [yellow]{tool_name}[/yellow]")
        for k, v in args.items():
            v_str = str(v)[:100]
            console.print(f"       [dim]{k}: {v_str}[/dim]")
    
    def _print_trade_decision(self, decision: dict):
        """Print a trading decision."""
        if decision.get("action") == "buy":
            console.print(f"     [bold green]BUY SIGNAL[/bold green]")
        elif decision.get("action") == "sell":
            console.print(f"     [bold red]SELL SIGNAL[/bold red]")
        else:
            console.print(f"     [dim]HOLD (no clear signal)[/dim]")
        
        for k, v in decision.items():
            if v is not None and k != "action" and k not in ("all_strategy_signals", "rag_insights", "learning_insights", "ensemble_signal", "key_factors"):
                console.print(f"       [dim]{k}: {v}[/dim]")
    
    def _print_strategy_signals(self, signals: list[dict]):
        """Print all strategy signals in a compact table."""
        console.print(f"\n  [bold]All Strategy Signals:[/bold]")
        for s in signals:
            action_color = {
                "buy": "green",
                "sell": "red",
                "hold": "dim",
            }.get(s["action"], "dim")
            console.print(
                f"    [{action_color}]{s['strategy']:25s}[/{action_color}] "
                f"[{action_color}]{s['action']:5s}[/{action_color}]  "
                f"confidence={s['confidence']:.2f}"
            )
    
    def _print_rag_insights(self, insights: list[str]):
        """Print RAG insights."""
        if insights:
            console.print(f"\n  [bold]RAG Pattern Insights:[/bold]")
            for insight in insights:
                console.print(f"    [dim]â€¢ {insight}[/dim]")
    
    def _write_status(self, cycle_result: dict):
        """Write bot status to JSON file for dashboard consumption."""
        try:
            status = {
                "running": self.running,
                "cycle": self.iteration,
                "last_update": datetime.now().isoformat(),
                "current_signal": cycle_result.get("signal"),
                "account": None,
            }
            
            if self.connector:
                try:
                    acc = self.connector.get_account_info()
                    if acc:
                        status["account"] = acc
                except Exception:
                    pass
            
            os.makedirs(os.path.dirname(self.status_path), exist_ok=True)
            with open(self.status_path, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to write bot status: {e}")
    
    # â”€â”€â”€ PHASES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    def check_environment(self) -> bool:
        """Check if the environment is properly configured."""
        console.print("\n[bold]Phase 1: Environment Check[/bold]")
        console.print("  " + "â”€" * 50)
        self._print_step("Checking configuration...", "running")
        
        warnings = validate_config()
        if warnings:
            for w in warnings:
                console.print(f"    [yellow]{w}[/yellow]")
            console.print("  [red]Configuration errors detected[/red]")
        else:
            self._print_step("Configuration OK", "done")
        
        # Show configured LLM providers
        providers = get_configured_providers()
        if providers:
            console.print(f"  [green]Configured LLM providers: {', '.join(providers)}[/green]")
        else:
            console.print(f"  [yellow]No LLM providers configured. Set at least one API key in .env[/yellow]")
        
        return True
    
    def setup_environment(self):
        """Run the environment setup agent to verify everything is ready."""
        console.print("\n[bold]Phase 2: Environment Setup[/bold]")
        console.print("  " + "â”€" * 50)
        self._print_step("Running environment setup agent...", "running")
        
        env_agent = create_env_setup_agent()
        
        console.print("  [dim]â”Œâ”€ Agent Thinking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”[/dim]")
        result = env_agent.run(
            "Check the current environment state. Verify Python version, "
            "check if venv exists, verify dependencies are installed, "
            "and ensure all required directories exist. Report any issues."
        )
        console.print("  [dim]â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜[/dim]")
        
        # Show the agent's report
        for line in result.split('\n')[:15]:
            console.print(f"    {line}")
        
        self._print_step("Environment setup complete", "done")
    
    def build_team(self):
        """Create and initialize all sub-agents."""
        console.print("\n[bold]Phase 3: Building Agent Team[/bold]")
        console.print("  " + "â”€" * 50)
        
        self._print_step("Initializing sub-agents...", "running")
        
        team_members = {
            "research": ("ðŸ”¬ Research Agent", "Market analysis, technical indicators, trend identification"),
            "strategy": ("ðŸŽ¯ Strategy Agent", "Trading strategy design, backtesting, optimization"),
            "risk": ("ðŸ›¡ï¸ Risk Agent", "Position sizing, stop-loss calculation, risk assessment"),
            "execution": ("âš¡ Execution Agent", "Order placement, position monitoring, trade management"),
        }
        
        self.team = {}
        for name, (label, desc) in team_members.items():
            console.print(f"    [bold]{label}[/bold]")
            console.print(f"      Role: {desc}")
            
            if name == "research":
                self.team[name] = create_research_agent()
            elif name == "strategy":
                self.team[name] = create_strategy_agent()
            elif name == "risk":
                self.team[name] = create_risk_agent()
            elif name == "execution":
                self.team[name] = create_execution_agent()
            
            self._print_step(f"{label} ready", "done")
        
        console.print(f"\n  [bold green]Team assembled: {len(self.team)} agents ready[/bold green]")
    
    def connect_mt5(self) -> bool:
        """Connect to MetaTrader 5."""
        console.print("\n[bold]Phase 4: MT5 Connection[/bold]")
        console.print("  " + "â”€" * 50)
        self._print_step("Connecting to MetaTrader 5...", "running")
        
        self.connector = get_connector()
        
        try:
            connected = self.connector.initialize()
            
            if connected:
                account = self.connector.get_account_info()
                if account:
                    console.print(f"  [bold green]Connected to MT5[/bold green]")
                    console.print(f"    Account: {account.get('name', 'N/A')}")
                    console.print(f"    Balance: [bold]${account.get('balance', 0):,.2f}[/bold]")
                    console.print(f"    Equity: ${account.get('equity', 0):,.2f}")
                    console.print(f"    Leverage: 1:{account.get('leverage', 0)}")
        except ConnectionError as e:
            console.print(f"  [bold red]MT5 Connection Failed[/bold red]")
            console.print(f"    {str(e)}")
            return False
        
        self._print_step("MT5 connection established", "done")
        return connected
    
    def initialize_strategy(self):
        """Initialize the trading strategy and learning system."""
        console.print("\n[bold]Phase 5: Strategy & Learning Initialization[/bold]")
        console.print("  " + "â”€" * 50)
        
        # â”€â”€â”€ 5a: Legacy Strategy (kept for backward compat) â”€â”€â”€
        self._print_step("Loading XAUUSD trading strategy...", "running")
        self.strategy = XAUUSDStrategy()
        
        console.print(f"  [bold]Strategy:[/bold] {self.strategy.name}")
        console.print(f"  [bold]Parameters:[/bold]")
        for k, v in self.strategy.params.items():
            console.print(f"    {k}: {v}")
        
        # Test with simulated data
        console.print("\n  [dim]Running strategy smoke test...[/dim]")
        test_data = get_rates(SYMBOL, "H1", 100)
        test_signal = self.strategy.generate_signals(test_data)
        console.print(f"  Test signal: [bold]{test_signal.action.upper()}[/bold] (confidence: {test_signal.confidence:.2f})")
        self._print_step("Strategy initialized and tested", "done")
        
        # â”€â”€â”€ 5b: Meta-Strategy Learning System â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        console.print()
        self._print_step("Initializing meta-strategy learning system...", "running")
        
        console.print("  [bold]Learning Module Components:[/bold]")
        
        # Vector Store (ChromaDB)
        self._print_step("Pattern Vector Store (ChromaDB RAG)...", "running")
        self.vector_store = PatternVectorStore()
        console.print(f"    [dim]Stored patterns: {self.vector_store.pattern_count}[/dim]")
        self._print_step("Vector store ready", "done")
        
        # Strategy Registry
        self._print_step("Strategy Registry (7 strategies)...", "running")
        self.strategy_registry = StrategyRegistry()
        console.print(f"    [dim]Registered strategies: {self.strategy_registry.count}[/dim]")
        for s in self.strategy_registry.get_all():
            console.print(f"      â€¢ {s.name:25s} â€” {s.description}")
        self._print_step("Strategy registry ready", "done")
        
        # Pattern Matcher (RAG pipeline)
        self._print_step("Pattern Matcher (RAG pipeline)...", "running")
        self.pattern_matcher = PatternMatcher(self.vector_store)
        self._print_step("Pattern matcher ready", "done")
        
        # Experience Database (SQLite)
        self._print_step("Experience Database (SQLite)...", "running")
        self.experience_db = ExperienceDatabase()
        trade_count = self.experience_db.get_trade_count()
        console.print(f"    [dim]Historical trades: {trade_count}[/dim]")
        self._print_step("Experience database ready", "done")
        
        # Meta-Strategy Agent (the brain)
        self._print_step("Meta-Strategy Agent (LLM orchestrator)...", "running")
        self.meta_strategy = MetaStrategyAgent(
            vector_store=self.vector_store,
            strategy_registry=self.strategy_registry,
            pattern_matcher=self.pattern_matcher,
            experience_db=self.experience_db,
        )
        self._print_step("Meta-strategy agent ready", "done")
        
        # â”€â”€â”€ 5c: Curiosity-Driven Knowledge Base â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        console.print()
        self._print_step("Initializing curiosity-driven knowledge acquisition...", "running")
        
        console.print("  [bold]Knowledge Base & Curiosity Engine:[/bold]")
        
        # Knowledge Base (SQLite)
        self._print_step("Knowledge Base (SQLite Q&A store)...", "running")
        self.knowledge_base = KnowledgeBase()
        kb_summary = self.knowledge_base.get_knowledge_summary()
        console.print(f"    [dim]Existing knowledge entries: {kb_summary['total_entries']}[/dim]")
        console.print(f"    [dim]Topics covered: {kb_summary['total_topics']}[/dim]")
        self._print_step("Knowledge base ready", "done")
        
        # Curiosity Agent
        self._print_step("Curiosity Agent (autonomous learning)...", "running")
        self.curiosity_agent = CuriosityAgent(self.knowledge_base)
        pending = self.knowledge_base.get_pending_count()
        console.print(f"    [dim]Seed questions queued: {pending}[/dim]")
        self._print_step("Curiosity agent ready", "done")
        
        console.print(f"\n  [bold green]Learning system initialized: "
                      f"{self.strategy_registry.count} strategies, "
                      f"{self.vector_store.pattern_count} stored patterns, "
                      f"{trade_count} historical trades, "
                      f"{kb_summary['total_entries']} knowledge entries[/bold green]")
    
    def run_research(self) -> dict:
        """Run market research phase."""
        console.print("\n[bold cyan]Phase 6a: Market Research[/bold cyan]")
        console.print("  " + "â”€" * 50)
        self._print_step("Fetching XAUUSD market data...", "running")
        
        # Fetch market data
        data = get_rates(SYMBOL, "H1", 100)
        last_price = get_last_price(SYMBOL)
        
        if last_price:
            console.print(f"  [bold]Current XAUUSD Price:[/bold]")
            console.print(f"    Bid: [bold]${last_price.get('bid', 0):.2f}[/bold]")
            console.print(f"    Ask: [bold]${last_price.get('ask', 0):.2f}[/bold]")
            console.print(f"    Spread: {last_price.get('spread', 0):.0f} pips")
        
        console.print(f"  Data: {len(data)} candles (H1 timeframe)")
        
        # Calculate indicators using the legacy strategy
        self._print_step("Calculating technical indicators...", "running")
        indicators = self.strategy.calculate_indicators(data)
        
        console.print(f"  [bold]Technical Snapshot:[/bold]")
        console.print(f"    Trend: [bold]{indicators.get('trend', 'N/A').upper()}[/bold]")
        console.print(f"    RSI (14): {indicators.get('rsi', 0):.1f}")
        console.print(f"    ATR (14): ${indicators.get('atr', 0):.2f}")
        
        if indicators.get('support_levels'):
            console.print(f"    Support: ${indicators['support_levels'][0]:.2f}" if indicators['support_levels'] else "    Support: N/A")
        if indicators.get('resistance_levels'):
            console.print(f"    Resistance: ${indicators['resistance_levels'][0]:.2f}" if indicators['resistance_levels'] else "    Resistance: N/A")
        
        # Inject knowledge from curiosity agent into research
        knowledge_context = ""
        if self.curiosity_agent:
            knowledge_context = self.curiosity_agent.get_knowledge_for_symbol(SYMBOL)
            if knowledge_context and "No knowledge acquired" not in knowledge_context:
                console.print(f"\n  [bold]Knowledge Base Context Available:[/bold]")
                # Show a brief summary of what we know
                kb_summary = self.knowledge_base.get_knowledge_summary()
                console.print(f"    Topics: {kb_summary['total_topics']} | "
                              f"Entries: {kb_summary['total_entries']} | "
                              f"Pending questions: {kb_summary['pending_questions']}")
        
        # Run research agent
        self._print_step("Research agent analyzing market...", "running")
        research_agent = self.team["research"]
        
        console.print("  [dim]â”Œâ”€ Research Agent Analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”[/dim]")
        
        # Format the OHLCV data as a compact string for the agent to analyze
        data_preview = "\n".join(
            f"  {d['time']}: O={d['open']:.2f} H={d['high']:.2f} L={d['low']:.2f} C={d['close']:.2f} V={d['volume']}"
            for d in data[-20:]  # Last 20 candles for context
        )
        
        analysis = research_agent.run(
            f"Analyze {SYMBOL} market data.\n\n"
            f"## Market Data (from MT5 integration)\n"
            f"Current price: Bid=${last_price.get('bid', 0):.2f}, Ask=${last_price.get('ask', 0):.2f}, "
            f"Spread={last_price.get('spread', 0):.0f} pips\n"
            f"Total candles: {len(data)} (H1 timeframe)\n\n"
            f"### Technical Indicators (pre-calculated)\n"
            f"Trend: {indicators.get('trend')}\n"
            f"RSI(14): {indicators.get('rsi', 0):.1f}\n"
            f"ATR(14): ${indicators.get('atr', 0):.2f}\n"
            f"Support levels: {indicators.get('support_levels', [])}\n"
            f"Resistance levels: {indicators.get('resistance_levels', [])}\n\n"
            f"### Last 20 OHLCV Candles\n"
            f"```\n{data_preview}\n```\n\n"
            f"Use Python REPL to perform detailed analysis on this data. "
            f"Provide a structured market analysis with trading recommendations.\n\n"
            f"{'### Knowledge Base Context\n' + knowledge_context if knowledge_context else ''}"
        )
        console.print("  [dim]â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜[/dim]")
        
        # Show key insights from research
        for line in analysis.split('\n')[:8]:
            if line.strip():
                console.print(f"    {line.strip()}")
        
        self._print_step("Market research complete", "done")
        
        return {
            "data": data,
            "last_price": last_price,
            "indicators": indicators,
            "analysis": analysis,
        }
    
    def run_strategy_design(self, research: dict) -> dict:
        """
        Run strategy design and signal generation using the meta-strategy system.
        
        This replaces the old single-strategy approach with the full
        meta-strategy pipeline: 7 strategies + RAG + LLM evaluation.
        """
        console.print("\n[bold cyan]Phase 6b: Meta-Strategy Signal Generation[/bold cyan]")
        console.print("  " + "â”€" * 50)
        
        indicators = research.get("indicators", {})
        data = research.get("data", [])
        
        if not indicators or not self.meta_strategy:
            console.print("  [yellow]Meta-strategy not available, using legacy strategy[/yellow]")
            return self._legacy_strategy_design(research)
        
        # â”€â”€â”€ Stage 1: Run all strategies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._print_step("Running all 7 strategies...", "running")
        all_signals = self.strategy_registry.run_all_strategies(indicators)
        
        # Show all strategy signals
        signals_display = [
            {
                "strategy": name,
                "action": s.action,
                "confidence": s.confidence,
                "reason": s.reason,
            }
            for name, s in all_signals
        ]
        self._print_strategy_signals(signals_display)
        
        # Show ensemble signal
        ensemble = self.strategy_registry.get_ensemble_signal(indicators, min_agreement=2)
        console.print(f"\n  [bold]Ensemble Signal:[/bold] {ensemble.action.upper()} "
                      f"(confidence={ensemble.confidence:.2f})")
        console.print(f"    [dim]{ensemble.reason}[/dim]")
        
        # â”€â”€â”€ Stage 2: RAG Pattern Matching â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._print_step("Querying RAG pattern store for similar historical conditions...", "running")
        rag_analysis = self.pattern_matcher.analyze_current_market(indicators)
        self._print_rag_insights(rag_analysis.get("insights", []))
        
        console.print(f"    Historical win rate in similar conditions: "
                      f"[bold]{rag_analysis.get('historical_win_rate', 50):.1f}%[/bold] "
                      f"({rag_analysis.get('winning_patterns', 0)}W/{rag_analysis.get('losing_patterns', 0)}L)")
        
        # â”€â”€â”€ Stage 3: Meta-Strategy Decision â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._print_step("Meta-strategy agent evaluating all signals...", "running")
        
        decision = self.meta_strategy.decide(
            indicators=indicators,
            market_data=data,
            min_confidence=0.5,
        )
        
        # â”€â”€â”€ Display Decision â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        console.print(f"\n  [bold]Meta-Strategy Decision:[/bold]")
        self._print_trade_decision(decision)
        
        if decision.get("reasoning"):
            console.print(f"    [dim]Reasoning: {decision['reasoning'][:200]}[/dim]")
        
        if decision.get("strategy_combination"):
            console.print(f"    [dim]Strategy combo: {', '.join(decision['strategy_combination'])}[/dim]")
        
        # Also run the legacy strategy for comparison
        legacy_signal = self.strategy.generate_signals(data) if self.strategy else None
        if legacy_signal:
            console.print(f"\n  [dim]Legacy strategy comparison: {legacy_signal.action.upper()} "
                          f"(confidence={legacy_signal.confidence:.2f})[/dim]")
        
        self._print_step("Signal generation complete", "done")
        
        return {
            "signal": decision,  # The meta-strategy decision
            "indicators": indicators,  # â† FIX #1: Pass full indicators
            "legacy_signal": legacy_signal,
            "all_signals": signals_display,
            "ensemble": {
                "action": ensemble.action,
                "confidence": ensemble.confidence,
                "reason": ensemble.reason,
            },
            "rag_analysis": rag_analysis,
            "strategy_analysis": "",  # Kept for backward compat
        }
    
    def _legacy_strategy_design(self, research: dict) -> dict:
        """Fallback to legacy single-strategy approach."""
        self._print_step("Generating trading signals (legacy)...", "running")
        
        if self.strategy and research.get("data"):
            signal = self.strategy.generate_signals(research["data"])
            
            console.print(f"\n  [bold]Signal Decision:[/bold]")
            self._print_trade_decision({
                "action": signal.action,
                "confidence": f"{signal.confidence:.1%}",
                "price": f"${signal.price:.2f}" if signal.price else "N/A",
                "stop_loss": f"${signal.stop_loss:.2f}" if signal.stop_loss else "N/A",
                "take_profit": f"${signal.take_profit:.2f}" if signal.take_profit else "N/A",
                "reason": signal.reason[:150],
            })
            
            if signal.action != "hold":
                self._print_step("Strategy agent evaluating signal...", "running")
                strategy_agent = self.team["strategy"]
                
                console.print("  [dim]â”Œâ”€ Strategy Agent Evaluation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”[/dim]")
                strategy_analysis = strategy_agent.run(
                    f"Review this trading signal for {SYMBOL}: "
                    f"Action: {signal.action}, Confidence: {signal.confidence:.2f}, "
                    f"Price: ${signal.price:.2f}, SL: ${signal.stop_loss}, TP: ${signal.take_profit}. "
                    f"Reason: {signal.reason}. "
                    f"Evaluate if this is a good trade and suggest any adjustments."
                )
                console.print("  [dim]â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜[/dim]")
                
                for line in strategy_analysis.split('\n')[:6]:
                    if line.strip():
                        console.print(f"    {line.strip()}")
            else:
                strategy_analysis = ""
            
            self._print_step("Signal generation complete", "done")
            
            return {
                "signal": {
                    "action": signal.action,
                    "confidence": signal.confidence,
                    "price": signal.price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "strategy_used": self.strategy.name,
                    "strategy_combination": [],
                    "reasoning": signal.reason,
                },
                "legacy_signal": signal,
                "all_signals": [],
                "ensemble": None,
                "rag_analysis": None,
                "strategy_analysis": strategy_analysis if signal.action != "hold" else "",
            }
        
        return {
            "signal": {"action": "hold", "confidence": 0.0, "reasoning": "No data available"},
            "legacy_signal": None,
            "all_signals": [],
            "ensemble": None,
            "rag_analysis": None,
            "strategy_analysis": "",
        }
    
    def run_risk_check(self, strategy_result: dict) -> dict:
        """Run risk management phase."""
        console.print("\n[bold cyan]Phase 6c: Risk Management[/bold cyan]")
        console.print("  " + "â”€" * 50)
        
        signal = strategy_result.get("signal", {})
        action = signal.get("action", "hold")
        
        if not signal or action == "hold":
            console.print("  [dim]No trade to assess â€” skipping risk check[/dim]")
            return {"approved": False, "reason": "No trade signal"}
        
        self._print_step("Assessing trade risk...", "running")
        
        # Get account info
        account = get_account_info()
        console.print(f"  [bold]Account:[/bold] Balance ${account.get('balance', 10000):,.2f}")
        
        # Calculate risk metrics
        price = signal.get("price", 0)
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")
        confidence = signal.get("confidence", 0)
        
        if stop_loss and price:
            risk_pips = abs(price - stop_loss)
            reward_pips = abs(take_profit - price) if take_profit else 0
            rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
            position_size = self._calculate_position_size(account, risk_pips)
            risk_amount = account.get('balance', 10000) * 0.01
            
            console.print(f"\n  [bold]Risk Assessment:[/bold]")
            console.print(f"    Risk per trade: 1% (${risk_amount:.2f})")
            console.print(f"    Stop loss distance: {risk_pips:.1f} points")
            console.print(f"    Take profit distance: {reward_pips:.1f} points")
            console.print(f"    Risk:Reward ratio: [bold]{rr_ratio:.2f}[/bold]")
            console.print(f"    Recommended position size: [bold]{position_size:.2f} lots[/bold]")
            
            # Run risk agent
            self._print_step("Risk agent reviewing trade...", "running")
            risk_agent = self.team["risk"]
            
            console.print("  [dim]â”Œâ”€ Risk Agent Assessment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”[/dim]")
            risk_assessment = risk_agent.run(
                f"Assess risk for this {SYMBOL} trade:\n"
                f"Action: {action}\n"
                f"Entry: ${price:.2f}\n"
                f"Stop Loss: ${stop_loss:.2f}\n"
                f"Take Profit: ${take_profit:.2f}\n"
                f"Account Balance: ${account.get('balance', 10000):.2f}\n"
                f"Risk per trade: 1%\n"
                f"Calculate position size and approve or reject this trade."
            )
            console.print("  [dim]â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜[/dim]")
            
            for line in risk_assessment.split('\n')[:6]:
                if line.strip():
                    console.print(f"    {line.strip()}")
            
            # Decision
            approved = rr_ratio >= 2.0 and confidence >= 0.5
            if approved:
                console.print(f"\n  [bold green]TRADE APPROVED[/bold green]")
            else:
                console.print(f"\n  [bold yellow]TRADE REJECTED[/bold yellow]")
                if rr_ratio < 2.0:
                    console.print(f"    Reason: Risk:Reward ratio ({rr_ratio:.2f}) below minimum (2.0)")
                if confidence < 0.5:
                    console.print(f"    Reason: Confidence ({confidence:.1%}) below threshold (50%)")
            
            self._print_step("Risk assessment complete", "done")
            
            return {
                "approved": approved,
                "risk_pips": risk_pips,
                "reward_pips": reward_pips,
                "rr_ratio": rr_ratio,
                "position_size": position_size,
                "risk_assessment": risk_assessment,
            }
        
        return {"approved": False, "reason": "Missing SL or price"}
    
    def _calculate_position_size(self, account: dict, risk_pips: float) -> float:
        """Calculate position size based on account balance and risk."""
        balance = account.get("balance", 10000)
        risk_amount = balance * 0.01  # 1% risk
        
        if risk_pips > 0:
            size = risk_amount / (risk_pips * 10)
            size = max(round(size, 2), 0.01)
            return min(size, 0.1)
        
        return 0.01
    
    
    # â† FIX #3: CHECK CLOSED POSITIONS
    def _check_closed_positions(self):
        """Check if any open positions have hit TP, SL, or timeout."""
        if not self.open_positions:
            return
        
        console.print("\n[bold cyan]Checking for closed positions...[/bold cyan]")
        
        # Get current price
        try:
            current_price_data = get_last_price(SYMBOL)
            if current_price_data:
                current_price = current_price_data.get("bid", 0)
            else:
                current_price = 0
        except Exception as e:
            logger.error(f"Could not get current price: {e}")
            return
        
        console.print(f"  Current {SYMBOL} price: ${current_price:.2f}")
        
        closed_positions = []
        still_open = []
        
        for position in self.open_positions:
            is_closed, reason, pnl = position.check_if_closed(current_price)
            
            if is_closed:
                console.print(f"\n  [bold yellow]Position Closed:[/bold yellow] {position.trade_id}")
                console.print(f"    Reason: {reason.upper()}")
                console.print(f"    Entry: ${position.entry_price:.2f}")
                console.print(f"    Exit: ${current_price:.2f}")
                console.print(f"    P&L: ${pnl:.2f} ({'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAKEVEN'})")
                
                # Record the outcome in learning system
                if self.meta_strategy:
                    self.meta_strategy.record_outcome(
                        decision=position.decision,
                        profit_loss=pnl,
                        exit_price=current_price,
                        exit_reason=reason,
                        indicators=position.decision.get("indicators"),
                    )
                
                closed_positions.append(position)
            else:
                still_open.append(position)
        
        # Update tracking
        self.open_positions = still_open
        
        if closed_positions:
            console.print(f"\n  [bold green]Closed {len(closed_positions)} position(s)[/bold green]")
        
        # Summary
        if self.open_positions:
            console.print(f"  [dim]Still tracking {len(self.open_positions)} open position(s)[/dim]")
    
    def execute_trade(self, risk_result: dict, strategy_result: dict) -> dict:
        """
        Act on an approved decision, honoring the configured TRADING_MODE.

        Phase 0 (current): OBSERVE is fully honest â€” it logs the decision but
        writes NO trade record and opens NO position, so the learning system is
        never fed phantom data. PAPER/LIVE order placement is wired in Phase 1
        via the BrokerAdapter; until then those modes explicitly report that
        real execution is not yet enabled rather than fabricating a fill.
        """
        console.print("\n[bold cyan]Phase 6d: Trade Execution[/bold cyan]")
        console.print("  " + "â”€" * 50)
        console.print(f"  [dim]Trading mode:[/dim] [bold]{TRADING_MODE}[/bold]")

        if not risk_result.get("approved"):
            console.print("  [yellow]Trade not approved â€” skipping execution[/yellow]")
            return {"executed": False, "reason": "Risk check failed", "mode": TRADING_MODE}

        signal = strategy_result.get("signal", {})
        if not signal or signal.get("action") == "hold":
            return {"executed": False, "reason": "No signal", "mode": TRADING_MODE}

        action = signal.get("action")
        price = signal.get("price", 0)
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")
        strategy_used = signal.get("strategy_used", "unknown")
        strategy_combo = signal.get("strategy_combination", [])
        position_size = risk_result.get("position_size", 0.01)

        console.print(f"\n  [bold]Decision Details:[/bold]")
        console.print(f"    Symbol: {SYMBOL}")
        console.print(f"    Action: [bold]{'BUY' if action == 'buy' else 'SELL'}[/bold]")
        console.print(f"    Volume: {position_size} lots")
        console.print(f"    Entry: ${price:.2f}")
        console.print(f"    Stop Loss: ${stop_loss:.2f}" if stop_loss else "    Stop Loss: N/A")
        console.print(f"    Take Profit: ${take_profit:.2f}" if take_profit else "    Take Profit: N/A")
        console.print(f"    Strategy: {strategy_used}")
        if strategy_combo:
            console.print(f"    Strategy combo: {', '.join(strategy_combo)}")

        # â”€â”€ OBSERVE mode: analyze only, never write a trade or open a position â”€â”€
        if TRADING_MODE == "OBSERVE":
            console.print(
                "  [yellow]OBSERVE mode:[/yellow] decision logged only. "
                "No order placed, no trade recorded, no position tracked."
            )
            self._print_step("Observation recorded (no execution)", "done")
            return {
                "executed": False,
                "observed": True,
                "mode": TRADING_MODE,
                "action": action,
                "size": position_size,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "strategy_used": strategy_used,
                "strategy_combination": strategy_combo,
            }

        # â”€â”€ PAPER / LIVE_MICRO / LIVE: real placement arrives in Phase 1 â”€â”€
        # Until the BrokerAdapter is wired, do NOT fabricate a fill or write a
        # phantom outcome. Report honestly that execution is not yet enabled.
        console.print(
            f"  [yellow]{TRADING_MODE} mode:[/yellow] order placement is not yet "
            "enabled (Phase 1 BrokerAdapter pending). No real order sent."
        )
        self._print_step("Execution deferred to Phase 1 broker adapter", "done")
        return {
            "executed": False,
            "pending_execution_layer": True,
            "mode": TRADING_MODE,
            "action": action,
            "size": position_size,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "strategy_used": strategy_used,
            "strategy_combination": strategy_combo,
        }
    
    def reflect_and_improve(self, cycle_result: dict):
        """Reflect on the trading cycle and identify improvements."""
        console.print("\n[bold cyan]Phase 7: Reflection & Improvement[/bold cyan]")
        console.print("  " + "â”€" * 50)
        
        self.performance_history.append(cycle_result)
        
        # Calculate performance metrics
        trades = [h for h in self.performance_history if h.get("trade", {}).get("executed")]
        signals_generated = sum(1 for h in self.performance_history
                               if h.get("signal") and h["signal"].get("action", "hold") != "hold")
        
        console.print(f"  [bold]Cycle #{self.iteration} Performance:[/bold]")
        console.print(f"    Total cycles run: {self.iteration}")
        console.print(f"    Signals generated: {signals_generated}")
        console.print(f"    Trades executed: {len(trades)}")
        
        # Show learning system stats
        if self.vector_store:
            console.print(f"\n  [bold]Learning System Status:[/bold]")
            console.print(f"    Patterns stored: {self.vector_store.pattern_count}")
            console.print(f"    Trades in experience DB: {self.experience_db.get_trade_count() if self.experience_db else 0}")
        
        # Every 5 iterations, run deep reflection
        if self.iteration % 5 == 0 and self.iteration > 0:
            console.print(f"\n  [bold]Deep Reflection Cycle (every 5 iterations)[/bold]")
            
            winning = sum(1 for t in trades if t.get("profit", 0) > 0)
            losing = sum(1 for t in trades if t.get("profit", 0) < 0)
            win_rate = (winning / len(trades) * 100) if trades else 0
            
            console.print(f"    Win rate: {win_rate:.1f}% ({winning}W/{losing}L)")
            
            # Show learning insights if available
            if self.experience_db:
                insights = self.experience_db.get_learning_insights()
                if insights:
                    console.print(f"\n    [bold]Learning Insights:[/bold]")
                    for insight in insights[:5]:
                        console.print(f"      â€¢ {insight}")
            
            # Show strategy recommendations
            if self.meta_strategy:
                recommendations = self.meta_strategy.get_strategy_recommendations()
                if recommendations:
                    console.print(f"\n    [bold]Strategy Recommendations:[/bold]")
                    for rec in recommendations[:5]:
                        console.print(f"      â€¢ {rec['strategy']}: {rec['win_rate']:.1f}% win rate "
                                      f"({rec['total_trades']} trades)")
            
            # Auto-adjust strategy if performance is poor
            if self.strategy and len(trades) >= 5:
                if win_rate < 40:
                    old_conf = self.strategy.params["min_confidence"]
                    self.strategy.params["min_confidence"] = max(old_conf - 0.05, 0.4)
                    console.print(f"    [yellow]Low win rate â€” adjusted min_confidence: {old_conf} â†’ {self.strategy.params['min_confidence']}[/yellow]")
                elif win_rate > 70:
                    old_conf = self.strategy.params["min_confidence"]
                    self.strategy.params["min_confidence"] = min(old_conf + 0.05, 0.8)
                    console.print(f"    [green]High win rate â€” tightened min_confidence: {old_conf} â†’ {self.strategy.params['min_confidence']}[/green]")
        
        # â”€â”€â”€ Phase 7b: Curiosity Learning Cycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.curiosity_agent:
            console.print(f"\n  [bold]Phase 7b: Curiosity-Driven Learning[/bold]")
            console.print("  " + "â”€" * 50)
            self._print_step("Asking questions to build trading knowledge...", "running")
            
            curiosity_results = self.curiosity_agent.run_learning_cycle()
            
            if curiosity_results["questions_asked"] > 0:
                console.print(f"    [green]Asked {curiosity_results['questions_asked']} question(s)[/green]")
                console.print(f"    [green]Stored {curiosity_results['knowledge_stored']} knowledge entr(ies)[/green]")
                if curiosity_results["follow_ups_generated"] > 0:
                    console.print(f"    [yellow]Generated {curiosity_results['follow_ups_generated']} follow-up question(s)[/yellow]")
                
                # Show knowledge base stats
                kb_summary = self.knowledge_base.get_knowledge_summary()
                console.print(f"    [dim]Knowledge base: {kb_summary['total_entries']} entries across "
                              f"{kb_summary['total_topics']} topics "
                              f"({kb_summary['pending_questions']} pending questions)[/dim]")
            else:
                pending = self.knowledge_base.get_pending_count()
                if pending > 0:
                    console.print(f"    [dim]â³ {pending} questions still pending in queue[/dim]")
                else:
                    console.print(f"    [dim]All questions answered â€” knowledge base complete[/dim]")
            
            if curiosity_results["errors"]:
                for err in curiosity_results["errors"][:2]:
                    console.print(f"    [red]{err[:100]}...[/red]")
            
            self._print_step("Curiosity learning complete", "done")
        
        self._print_step("Reflection complete", "done")
    
    def run_trading_cycle(self) -> dict:
        """Run one complete trading cycle."""
        self.iteration += 1
        
        console.print(f"\n{'='*60}")
        console.print(f"[bold]TRADING CYCLE #{self.iteration}[/bold]")
        console.print(f"{'='*60}")
        console.print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        console.print()
        
        # â† FIX #3: Check for closed positions at start of cycle
        self._check_closed_positions()
        
        # Phase 6a: Research
        research = self.run_research()
        
        # Phase 6b: Strategy (meta-strategy system)
        strategy_result = self.run_strategy_design(research)
        
        # Phase 6c: Risk Check
        risk_result = self.run_risk_check(strategy_result)
        
        # Phase 6d: Execute
        trade_result = self.execute_trade(risk_result, strategy_result)
        
        # Phase 7: Reflect
        cycle_result = {
            "cycle": self.iteration,
            "timestamp": datetime.now().isoformat(),
            "signal": strategy_result.get("signal"),
            "risk": risk_result,
            "trade": trade_result,
            "profit": 0,
        }
        
        self.reflect_and_improve(cycle_result)
        self._write_status(cycle_result)
        
        return cycle_result
    
    def run(self):
        """Main entry point â€” run the trading bot."""
        console.print("""
[bold yellow]â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘     XAUUSD Trading Bot â€” Meta-Strategy Learning     â•‘
â•‘     Mission: Learn to trade Gold through curiosity      â•‘
â•‘     LLM: LiteLLM multi-provider (Kilo Gateway, Groq)   â•‘
â•‘     Learning: 7 strategies + RAG + SQLite + Curiosity   â•‘
â•‘     Connection: Live MT5 â€” Real market data           â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
[/bold yellow]        """)
        
        # Phase 1: Check environment
        if not self.check_environment():
            console.print("[red]Environment check failed. Please fix configuration.[/red]")
            return
        
        # Phase 2: Setup environment
        self.setup_environment()
        
        # Phase 3: Build team
        self.build_team()
        
        # Phase 4: Connect to MT5
        self.connect_mt5()
        
        # Phase 5: Initialize strategy + learning system
        self.initialize_strategy()
        
        # Phase 6-7: Trading loop
        self.running = True
        console.print(f"\n[bold green]Trading bot started! Running up to {self.max_iterations} cycles...[/bold green]")
        console.print(f"[dim]   Press Ctrl+C to stop at any time[/dim]")
        
        try:
            while self.running and self.iteration < self.max_iterations:
                cycle_result = self.run_trading_cycle()
                
                # Wait between cycles
                if self.iteration < self.max_iterations:
                    wait_time = 3
                    console.print(f"\n[dim]â³ Waiting {wait_time}s before next cycle... (Ctrl+C to stop)[/dim]")
                    time.sleep(wait_time)
        
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Bot stopped by user[/yellow]")
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}", exc_info=True)
            console.print(f"\n[red]Fatal error: {str(e)}[/red]")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shut down the bot with summary."""
        console.print(f"\n{'='*60}")
        console.print("[bold]SESSION SUMMARY[/bold]")
        console.print(f"{'='*60}")
        
        self.running = False
        
        # Close MT5 connection
        if self.connector:
            self.connector.shutdown()
        
        # Print summary
        trades = [h for h in self.performance_history if h.get("trade", {}).get("executed")]
        signals = [h for h in self.performance_history
                  if h.get("signal") and h["signal"].get("action", "hold") != "hold"]
        
        console.print(f"\n  [bold]Session Statistics:[/bold]")
        console.print(f"    Total cycles: {self.iteration}")
        console.print(f"    Signals generated: {len(signals)}")
        console.print(f"    Trades executed: {len(trades)}")
        console.print(f"    Team members: {len(self.team)}")
        
        # Learning system summary
        if self.vector_store:
            console.print(f"\n  [bold]Learning System Summary:[/bold]")
            console.print(f"    Patterns in vector store: {self.vector_store.pattern_count}")
            console.print(f"    Trades in experience DB: {self.experience_db.get_trade_count() if self.experience_db else 0}")
            
            if self.meta_strategy:
                summary = self.meta_strategy.get_learning_summary()
                console.print(f"    Overall win rate: {summary.get('overall_win_rate', 0):.1f}%")
                console.print(f"    Total P&L: ${summary.get('performance', {}).get('total_profit_loss', 0):.2f}")
                
                if summary.get("insights"):
                    console.print(f"\n    [bold]Learning Insights:[/bold]")
                    for insight in summary["insights"][:5]:
                        console.print(f"      â€¢ {insight}")
        
        # Curiosity agent summary
        if self.curiosity_agent:
            curiosity_summary = self.curiosity_agent.get_learning_summary()
            console.print(f"\n  [bold]Curiosity-Driven Learning Summary:[/bold]")
            console.print(f"    Questions asked: {curiosity_summary['total_questions_asked']}")
            console.print(f"    Knowledge entries: {curiosity_summary['knowledge_entries']}")
            console.print(f"    Topics covered: {curiosity_summary['topics_covered']}")
            if curiosity_summary['topic_breakdown']:
                console.print(f"    [dim]Topics:[/dim]")
                for tb in curiosity_summary['topic_breakdown'][:8]:
                    console.print(f"      â€¢ {tb['topic']}: {tb['count']} entries "
                                  f"(avg confidence: {tb['avg_conf']:.0%})")
            if curiosity_summary['pending_questions'] > 0:
                console.print(f"    [yellow]â³ {curiosity_summary['pending_questions']} questions still pending[/yellow]")
        
        console.print(f"\n  [bold]Agent Team:[/bold]")
        for name in self.team:
            console.print(f"    {name.replace('_', ' ').title()} Agent")
        
        console.print(f"\n[green]Bot shutdown complete[/green]")
        console.print(f"[dim]Logs saved to: logs/ directory[/dim]")
        console.print()


def main():
    """Entry point."""
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()

