"""
Base sub-agent class for the LangChain multi-agent trading system.
Each sub-agent is a specialized ReAct agent with its own tools and system prompt.
Includes automatic retry with provider fallback on rate limit errors.
"""

import time
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from src.core.llm import get_llm, mark_provider_failed
from src.utils.logger import get_logger

logger = get_logger("agents.base")

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class BaseSubAgent:
    """
    Base class for all sub-agents in the trading system.
    
    Each sub-agent has:
    - A specialized system prompt defining its role
    - A set of tools it can use
    - A LangGraph ReAct agent loop
    - Automatic retry with provider fallback on rate limit errors
    """
    
    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list[BaseTool],
        temperature: float = 0.3,
    ):
        """
        Initialize a sub-agent.
        
        Args:
            name: Agent name (e.g., "research_agent").
            system_prompt: System prompt defining the agent's role.
            tools: List of tools available to this agent.
            temperature: LLM temperature for this agent.
        """
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.temperature = temperature
        self._app = None
        self._config = {"configurable": {"thread_id": f"{name}_thread"}}
        
        logger.info(f"Initialized sub-agent: {name}")
    
    def build(self, provider_override: Optional[str] = None):
        """Build the LangGraph agent application."""
        llm = get_llm(temperature=self.temperature, provider_override=provider_override)
        llm_with_tools = llm.bind_tools(self.tools)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])
        
        def agent_node(state: MessagesState) -> dict:
            messages = prompt.invoke({"messages": state["messages"]})
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        
        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", tools_condition)
        workflow.add_edge("tools", "agent")
        
        memory = MemorySaver()
        self._app = workflow.compile(checkpointer=memory)
        
        logger.info(f"Built agent graph: {self.name}")
        return self._app
    
    @property
    def app(self):
        """Get the compiled LangGraph application, building it if needed."""
        if self._app is None:
            self.build()
        return self._app
    
    def run(self, task: str) -> str:
        """
        Run the sub-agent on a specific task.
        Automatically retries with a different provider on rate limit errors.
        
        Args:
            task: The task description for the agent.
        
        Returns:
            The agent's response as a string.
        """
        from langchain_core.messages import HumanMessage
        
        logger.info(f"Running sub-agent '{self.name}' with task: {task[:100]}...")
        
        last_error = ""
        
        for attempt in range(MAX_RETRIES):
            try:
                # Rebuild app on retry to get a fresh provider
                if attempt > 0:
                    logger.info(f"Retry {attempt+1}/{MAX_RETRIES} for '{self.name}'...")
                    time.sleep(RETRY_DELAY * attempt)
                    self._app = None  # Force rebuild with new provider
                
                events = self.app.stream(
                    {"messages": [HumanMessage(content=task)]},
                    self._config,
                    stream_mode="values",
                )
                
                # Collect all responses
                response = ""
                for event in events:
                    if "messages" in event:
                        last_msg = event["messages"][-1]
                        if hasattr(last_msg, "content") and last_msg.content:
                            content = last_msg.content
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
                                response = "\n".join(texts)
                            else:
                                response = content
                
                logger.info(f"Sub-agent '{self.name}' completed task")
                return response or "(no response)"
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate_limit" in error_str.lower() or "rate limit" in error_str.lower():
                    logger.warning(f"Rate limit hit for '{self.name}' on attempt {attempt+1}: {error_str[:100]}")
                    # Mark current provider as failed so next retry picks a different one
                    if self._app is not None:
                        mark_provider_failed(f"sub_agent_{self.name}")
                    continue
                
                # Non-rate-limit error — don't retry
                logger.error(f"Error in sub-agent '{self.name}': {error_str[:200]}")
                return f"Error in sub-agent '{self.name}': {error_str}"
        
        # All retries exhausted
        error_msg = f"Error in sub-agent '{self.name}' after {MAX_RETRIES} retries: {last_error[:200]}"
        logger.error(error_msg)
        return error_msg
