"""
Shared tool definitions for the LangChain ReAct agent and its sub-agents.
These tools give the agent the ability to interact with the system.

Uses StructuredTool for proper schema generation compatible with Groq API.
"""

import os
import subprocess
import sys
import json
from typing import Optional, Type, Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from src.utils.logger import get_logger

logger = get_logger("tools")


# ─── Shell Command Tool ─────────────────────────────────────

def execute_shell_command_func(command: str, timeout: int = 60) -> str:
    """
    Execute a shell command and return the output.
    Use this to run system commands, create files, install packages, etc.
    
    Args:
        command: The shell command to execute.
        timeout: Timeout in seconds (default: 60).
    """
    logger.info(f"⚡ Executing shell command: {command[:200]}...")
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout[:3000]}"
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr[:2000]}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        logger.info(f"✅ Shell command completed (exit: {result.returncode})")
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        logger.warning(f"⏱️ Shell command timed out after {timeout}s")
        return f"Command timed out after {timeout}s"
    except Exception as e:
        logger.error(f"❌ Shell command error: {str(e)}")
        return f"Error: {str(e)}"


execute_shell_command = StructuredTool.from_function(
    func=execute_shell_command_func,
    name="execute_shell_command",
    description="Execute a shell command and return the output. Use this to run system commands, create files, install packages, etc.",
    args_schema=None,
)


# ─── Python REPL Tool ───────────────────────────────────────

def python_repl_func(code: str) -> str:
    """
    Execute Python code and return the output.
    Use this for calculations, data analysis, backtesting, etc.
    
    Args:
        code: Python code to execute.
    """
    logger.info(f"🐍 Executing Python REPL ({len(code)} chars)")
    try:
        import io
        import sys
        from contextlib import redirect_stdout, redirect_stderr
        
        # Capture output
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Create a restricted globals dict with common imports
        restricted_globals = {
            "__builtins__": __builtins__,
        }
        
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            try:
                exec(code, restricted_globals)
            except Exception as e:
                return f"Error: {type(e).__name__}: {str(e)}"
        
        output = ""
        if stdout_capture.getvalue():
            output += stdout_capture.getvalue()
        if stderr_capture.getvalue():
            output += f"\nSTDERR:\n{stderr_capture.getvalue()}"
        
        logger.info(f"✅ Python REPL completed ({len(output)} chars output)")
        return output or "(no output)"
    except Exception as e:
        logger.error(f"❌ Python REPL error: {str(e)}")
        return f"REPL Error: {str(e)}"


python_repl = StructuredTool.from_function(
    func=python_repl_func,
    name="python_repl",
    description="Execute Python code and return the output. Use this for calculations, data analysis, backtesting, etc. The code runs in the current environment with access to installed packages.",
    args_schema=None,
)


# ─── File Operations Tools ──────────────────────────────────

def read_file_func(path: str) -> str:
    """
    Read the contents of a file.
    Use this to inspect existing code, configuration files, or data.
    
    Args:
        path: Path to the file to read.
    """
    logger.info(f"📖 Reading file: {path}")
    try:
        with open(path, "r") as f:
            content = f.read()
        truncated = len(content) > 5000
        result = content[:5000] if truncated else content
        if truncated:
            result += "\n... (truncated, file is larger)"
        logger.info(f"✅ Read {len(content)} bytes from {path}")
        return result
    except Exception as e:
        logger.error(f"❌ Error reading file: {str(e)}")
        return f"Error reading file: {str(e)}"


read_file = StructuredTool.from_function(
    func=read_file_func,
    name="read_file",
    description="Read the contents of a file. Use this to inspect existing code, configuration files, or data.",
    args_schema=None,
)


def write_file_func(path: str, content: str) -> str:
    """
    Write content to a file. Creates directories if needed.
    Use this to create or modify code files, configuration, etc.
    
    Args:
        path: Path to write the file to.
        content: Content to write to the file.
    """
    logger.info(f"✏️ Writing file: {path} ({len(content)} bytes)")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        logger.info(f"✅ Successfully wrote {len(content)} bytes to {path}")
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        logger.error(f"❌ Error writing file: {str(e)}")
        return f"Error writing file: {str(e)}"


write_file = StructuredTool.from_function(
    func=write_file_func,
    name="write_file",
    description="Write content to a file. Creates directories if needed. Use this to create or modify code files, configuration, etc.",
    args_schema=None,
)


def list_files_func(path: str = ".") -> str:
    """
    List files in a directory.
    Use this to explore the project structure.
    
    Args:
        path: Directory to list (default: current directory).
    """
    logger.info(f"📂 Listing files in: {path}")
    try:
        files = os.listdir(path)
        files = [os.path.join(path, f) for f in files]
        
        # Format nicely
        result = []
        for f in sorted(files):
            if os.path.isdir(f):
                result.append(f"📁 {f}/")
            else:
                size = os.path.getsize(f)
                result.append(f"📄 {f} ({size} bytes)")
        
        output = "\n".join(result) if result else "(empty directory)"
        logger.info(f"✅ Listed {len(result)} items in {path}")
        return output
    except Exception as e:
        logger.error(f"❌ Error listing files: {str(e)}")
        return f"Error listing files: {str(e)}"


list_files = StructuredTool.from_function(
    func=list_files_func,
    name="list_files",
    description="List files in a directory. Use this to explore the project structure.",
    args_schema=None,
)


# ─── All Tools List ─────────────────────────────────────────

def get_all_tools() -> list[BaseTool]:
    """Return all available tools for the main agent."""
    return [
        execute_shell_command,
        python_repl,
        read_file,
        write_file,
        list_files,
    ]


def get_env_setup_tools() -> list[BaseTool]:
    """Tools for the environment setup agent."""
    return [
        execute_shell_command,
        read_file,
        write_file,
        list_files,
    ]


def get_research_tools() -> list[BaseTool]:
    """Tools for the research agent."""
    return [
        python_repl,
    ]


def get_execution_tools() -> list[BaseTool]:
    """Tools for the execution agent."""
    return [
        python_repl,
        execute_shell_command,
    ]
