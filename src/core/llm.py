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
    "extract_text",
]


def extract_text(resp) -> str:
    """
    Robustly extract plain text from an LLM response, regardless of provider.

    Some providers (e.g. Anthropic-style) return `.content` as a LIST of content
    blocks (dicts with a 'text' key) rather than a string. Calling .strip() on
    that list crashes ('list' object has no attribute 'strip'). This normalises
    all shapes to a single string.
    """
    if resp is None:
        return ""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", block.get("content", ""))))
            else:
                parts.append(str(block))
        return " ".join(p for p in parts if p).strip()
    return str(content).strip()

