"""
Main ReAct Agent definition for the XAUUSD trading bot.
This agent is the orchestrator that builds its team and manages the trading loop.
Includes verbose logging so you can see the agent's thinking process.
Uses LiteLLM for multi-provider LLM support with automatic fallback.
"""

import json
import time

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from src.core.llm import get_llm, mark_provider_failed
from src.core.tools import get_all_tools
from src.utils.logger import get_logger, console

logger = get_logger("agent")

MAX_RETRIES = 3

# ─── System Prompt ──────────────────────────────────────────

MAIN_AGENT_SYSTEM_PROMPT = """You are the **Orchestrator Agent** — the leader of a team of AI agents.

## YOUR MISSION
Your mission is to build and lead a team of specialized sub-agents to create the most intelligent XAUUSD (Gold vs USD) trading application using MetaTrader 5.

## YOUR CAPABILITIES
You have access to tools that let you:
1. `execute_shell_command` — Run shell commands (create files, run scripts, install packages)
2. `python_repl` — Execute Python code (calculations, analysis, backtesting)
3. `read_file` — Read file contents
4. `write_file` — Write content to files (create/modify code)
5. `list_files` — List files in a directory

## YOUR TEAM
You will recruit and manage these sub-agents:
1. **Environment Setup Agent** — Creates the development environment
2. **Research Agent** — Analyzes market data and identifies patterns
3. **Strategy Agent** — Designs and backtests trading strategies
4. **Risk Management Agent** — Calculates position sizing and risk parameters
5. **Execution Agent** — Places and manages trades on MT5

## YOUR WORKFLOW
1. **Phase 1: Environment** — First, ensure the environment is ready (venv, deps)
2. **Phase 2: Team Building** — Create the sub-agent code files for your team
3. **Phase 3: Research** — Analyze XAUUSD market conditions
4. **Phase 4: Strategy** — Design and backtest a trading strategy
5. **Phase 5: Execute** — Start the trading loop with risk management
6. **Phase 6: Reflect** — Analyze performance and improve

## IMPORTANT RULES
- Always verify your work before proceeding to the next phase
- Use Python REPL for calculations and analysis
- Create well-structured, documented code files
- Implement proper error handling in all code
- Start with paper trading / simulation before real trading
- Never risk more than 1-2% of account per trade
- Always use stop losses
- Document your decisions and reasoning

## XAUUSD (GOLD) TRADING NOTES
- Gold is highly sensitive to USD strength, interest rates, and geopolitical events
- Best trading sessions: London and New York overlap (12:00-16:00 GMT)
- Common strategies: trend following, support/resistance, breakout
- Typical spread: 20-40 pips (varies by broker)
- High volatility around economic news releases

Begin by checking the current environment state, then proceed step by step.
"""


def create_main_agent():
    """
    Create the main ReAct agent with LangGraph.
    Uses LiteLLM for multi-provider support with automatic fallback.
    
    Returns:
        A compiled LangGraph application that runs the agent.
    """
    logger.info("Creating main agent...")
    
    # Get the LLM (LiteLLM auto-selects from available providers)
    llm = get_llm()
    tools = get_all_tools()
    
    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # Create the prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", MAIN_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    # Define the agent node with verbose logging and rate limit handling
    def agent_node(state: MessagesState) -> dict:
        """Process messages and decide next action."""
        messages = prompt.invoke({"messages": state["messages"]})
        
        # Log what the agent is thinking (last user message)
        last_human = None
        for m in reversed(state["messages"]):
            if hasattr(m, 'type') and m.type == 'human':
                last_human = m.content[:200]
                break
        
        if last_human:
            logger.info(f"🤔 Agent processing: \"{last_human}...\"")
        
        # Try with retry on rate limit
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = llm_with_tools.invoke(messages)
                
                # Log what the agent decided to do
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    for tc in response.tool_calls:
                        logger.info(f"🔧 Agent decided to use tool: {tc['name']}")
                        logger.info(f"   Args: {json.dumps(tc['args'], default=str)[:300]}")
                elif hasattr(response, 'content') and response.content:
                    content = response.content
                    # Handle structured content (list of content blocks from OpenAI-compatible APIs)
                    if isinstance(content, list):
                        texts = []
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    texts.append(block.get("text", ""))
                                elif block.get("type") == "thinking":
                                    texts.append(block.get("thinking", ""))
                            elif isinstance(block, str):
                                texts.append(block)
                        content = "\n".join(texts)
                    logger.info(f"💬 Agent response: {str(content)[:200]}...")
                
                return {"messages": [response]}
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                if "429" in error_str or "rate_limit" in error_str.lower():
                    logger.warning(f"⏱️ Rate limit on attempt {attempt+1}/{MAX_RETRIES}")
                    mark_provider_failed("main_agent")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2 * (attempt + 1))
                        # Re-create LLM to get a different provider
                        nonlocal_llm = get_llm()
                        llm_with_tools = nonlocal_llm.bind_tools(tools)
                    continue
                
                # Non-rate-limit error
                logger.error(f"❌ Agent error: {error_str[:200]}")
                raise
        
        # All retries exhausted
        error_msg = f"Rate limit exceeded after {MAX_RETRIES} retries: {last_error[:200]}"
        logger.error(f"❌ {error_msg}")
        return {"messages": [AIMessage(content=f"I encountered a rate limit error. Please try again later or configure additional API keys in .env. Error: {last_error[:100]}")]}
    
    # Build the graph
    workflow = StateGraph(MessagesState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    
    # Add edges
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
    )
    workflow.add_edge("tools", "agent")
    
    # Set up memory (checkpointing)
    memory = MemorySaver()
    
    # Compile
    app = workflow.compile(checkpointer=memory)
    logger.info("✅ Main agent created successfully")
    
    return app
