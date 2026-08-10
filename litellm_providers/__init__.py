"""
litellm_providers — Standalone multi-provider LLM router.

A drop-in package that provides automatic fallback across 15+ free LLM providers
using LiteLLM. Configure API keys in .env, and the router handles the rest.

Quick start:
    from litellm_providers import get_llm, get_configured_providers
    
    llm = get_llm()
    response = llm.invoke("Hello!")
    
    print(f"Active providers: {get_configured_providers()}")

Install from GitHub:
    pip install git+https://github.com/martinsharkey/langchain.git
"""

from .provider_router import (
    get_llm,
    get_groq_llm,
    get_analytical_llm,
    get_creative_llm,
    mark_provider_failed,
    get_configured_providers,
    get_provider_count,
    PROVIDERS,
)

__version__ = "1.0.0"
__all__ = [
    "get_llm",
    "get_groq_llm",
    "get_analytical_llm",
    "get_creative_llm",
    "mark_provider_failed",
    "get_configured_providers",
    "get_provider_count",
    "PROVIDERS",
]
