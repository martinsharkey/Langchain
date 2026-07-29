"""
Multi-provider LLM client configuration using LiteLLM.

This module is a thin re-export wrapper around the standalone `litellm_providers`
package. The actual provider logic lives in `litellm_providers/provider_router.py`,
which can be copied into any project for reuse.

Supports 15+ free-tier LLM providers with automatic fallback.
Automatically rotates between providers when rate limits are hit.

Configure providers in .env file (at least one required):
    GROQ_API_KEY=gsk_...              (primary, fastest)
    GEMINI_API_KEY=AIza...            (very generous free tier)
    CEREBRAS_API_KEY=...              (1M tokens/day, ultra-fast)
    MISTRAL_API_KEY=...               (~1B tokens/month free)
    OPENROUTER_API_KEY=...            (~22 free models, 200 RPD)
    SAMBANOVA_API_KEY=...             (200K tokens/day)
    COHERE_API_KEY=...                (1,000 req/month)
    CLOUDFLARE_API_KEY=...            (10K neurons/day)
    NVIDIA_API_KEY=...                (40 RPM, free dev program)
    HUGGINGFACE_API_KEY=...           (100K credits/month)
    GITHUB_TOKEN=...                  (free for GitHub users)
    TOGETHER_API_KEY=...              (free research models)
    DEEPSEEK_API_KEY=...              (5M free tokens)
    AI21_API_KEY=...                  (trial credits)
    XAI_API_KEY=...                   (Grok, $25 signup credit)

For standalone reuse in other projects:
    pip install git+https://github.com/martinsharkey/langchain.git
    from litellm_providers import get_llm, get_configured_providers
"""

# Re-export everything from the standalone litellm_providers package
from litellm_providers import (
    get_llm,
    get_groq_llm,
    get_analytical_llm,
    get_creative_llm,
    mark_provider_failed,
    get_configured_providers,
    get_provider_count,
    PROVIDERS,
)

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
