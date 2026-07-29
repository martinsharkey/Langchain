"""
Utility helper functions for the trading bot.
"""

import os
import subprocess
import sys
from typing import Optional


def ensure_venv() -> bool:
    """Check if we're running inside the project's virtual environment."""
    return sys.prefix != sys.base_prefix


def get_venv_path() -> Optional[str]:
    """Get the path to the virtual environment if it exists."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    venv_path = os.path.join(base_dir, "venv")
    if os.path.isdir(venv_path):
        return venv_path
    return None


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 120) -> tuple[int, str, str]:
    """
    Run a shell command and return (return_code, stdout, stderr).
    
    Args:
        command: The shell command to execute.
        cwd: Working directory (defaults to project root).
        timeout: Timeout in seconds.
    
    Returns:
        Tuple of (return_code, stdout, stderr).
    """
    if cwd is None:
        cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def format_currency(value: float, decimals: int = 2) -> str:
    """Format a number as currency."""
    return f"${value:,.{decimals}f}"


def format_pips(value: float) -> str:
    """Format a value in pips."""
    return f"{value:.1f} pips"
