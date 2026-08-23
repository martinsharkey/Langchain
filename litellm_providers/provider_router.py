"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    LiteLLM Multi-Provider Router                            ║
║                                                                             ║
║  A standalone, drop-in module that provides automatic LLM fallback across   ║
║  15+ free-tier providers using LiteLLM. Includes Kilo Gateway which works   ║
║  WITHOUT any API key — just set USE_KILO_GATEWAY=true.                      ║
║                                                                             ║
║  Usage:                                                                     ║
║      from litellm_providers import get_llm, get_configured_providers         ║
║      llm = get_llm()                                                        ║
║      response = llm.invoke("Hello!")                                        ║
║                                                                             ║
║  Configure API keys in .env (at least one recommended):                     ║
║      GROQ_API_KEY=gsk_...              (primary, fastest)                   ║
║      GEMINI_API_KEY=AIza...            (very generous free tier)            ║
║      CEREBRAS_API_KEY=...              (1M tokens/day, ultra-fast)          ║
║      MISTRAL_API_KEY=...               (~1B tokens/month free)              ║
║      OPENROUTER_API_KEY=...            (~22 free models, 200 RPD)           ║
║      SAMBANOVA_API_KEY=...             (200K tokens/day)                    ║
║      COHERE_API_KEY=...                (1,000 req/month)                    ║
║      CLOUDFLARE_API_KEY=...            (10K neurons/day)                    ║
║      NVIDIA_API_KEY=...                (40 RPM, free dev program)           ║
║      HUGGINGFACE_API_KEY=...           (100K credits/month)                 ║
║      GITHUB_TOKEN=...                  (free for GitHub users)              ║
  ║      TOGETHER_API_KEY=...              (free research models)               ║
  ║      DEEPSEEK_API_KEY=...              (5M free tokens)                     ║
  ║      AI21_API_KEY=...                  (trial credits)                      ║
  ║      XAI_API_KEY=...                   (Grok, $25 signup credit)            ║
  ║      IBM_ADVANTAGE_API_KEY=...         (free tier: Haiku, Llama Maverick,   ║
  ║                         Gemma, Granite via /v1 OpenAI-compatible endpoint) ║
║                                                                             ║
  ║  API-key-free provider (no signup needed, just set USE_ flag):              ║
  ║      USE_KILO_GATEWAY=true             (200 req/hr per IP, no account)      ║
  ║                                                                             ║
  ║  IBM Advantage Models (free tier, OpenAI-compatible /v1 endpoint):          ║
  ║      IBM_ADVANTAGE_API_KEY=...         (global key for all models)         ║
  ║      IBM_ADVANTAGE_BASE_URL=https://api.nextgen-beta.ica.ibm.com/ica/v1   ║
  ║                                                                             ║
  ║  Provider priority (lower weight = tried first):                            ║
  ║    Tier 0: Kilo Gateway (API-key-free, always available)                    ║
  ║    Tier 1: Groq (fastest LPU inference)                                     ║
  ║    Tier 2: Gemini, Cerebras, Mistral (generous free tiers)                  ║
  ║    Tier 3: IBM Advantage Models, OpenRouter, SambaNova, Cohere (good free)  ║
  ║    Tier 4: Cloudflare, NVIDIA, HuggingFace, GitHub (moderate)               ║
  ║    Tier 5: Together, DeepSeek, AI21, xAI (trial/credit-based)               ║
║                                                                             ║
║  Copy this single file into any project to use it standalone.               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import time
import random
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_litellm import ChatLiteLLM

logger = logging.getLogger("litellm_providers")

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL LiteLLM COMPATIBILITY SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
# LiteLLM only honours `modify_params` / `drop_params` from the `litellm` module
# globals (or a top-level call kwarg). Passing them nested inside
# ChatLiteLLM(model_kwargs={"litellm_settings": {...}}) is SILENTLY IGNORED, which
# is why Bedrock kept raising:
#   "Bedrock doesn't support tool calling without `tools=` param specified.
#    Pass `tools=` param OR set `litellm.modify_params = True`."
#
# Setting these once at import fixes it for every provider:
#   modify_params=True -> LiteLLM injects a dummy tool when a provider requires
#                         `tools=` for tool-calling (Bedrock/Anthropic style).
#   drop_params=True   -> LiteLLM drops params a given provider doesn't support
#                         instead of erroring (e.g. temperature/top_p on models
#                         that reject them).
try:
    import litellm as _litellm

    _litellm.modify_params = True
    _litellm.drop_params = True
    logger.info("LiteLLM compatibility set: modify_params=True, drop_params=True")
except Exception as _e:  # pragma: no cover - litellm always present via langchain_litellm
    logger.warning(f"Could not set litellm global compatibility flags: {_e}")

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; user must set env vars manually

# Default model for Groq
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.7"))

# ═══════════════════════════════════════════════════════════════════════════════
#  PROVIDER REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each entry: (model_name, env_var_or_flag, priority_weight, requires_api_key, api_base)
#   - model_name:      The LiteLLM model identifier (provider/model)
#   - env_var_or_flag: The env var name for the API key (or USE_ flag for key-free)
#   - weight:          Lower = tried first. Random shuffle within same weight.
#   - requires_api_key: True = needs API key in env var; False = uses USE_ flag
#   - api_base:        Optional custom API base URL (for OpenAI-compatible gateways)
#
# To add a new provider, just append to this list. No other code changes needed.
# ═══════════════════════════════════════════════════════════════════════════════

# Kilo Gateway base URL (OpenAI-compatible, no API key needed)
KILO_API_BASE = "https://api.kilo.ai/api/gateway/v1"

# IBM Advantage Models base URL (OpenAI-compatible /v1 endpoint)
IBM_ADVANTAGE_BASE_URL = "https://api.nextgen-beta.ica.ibm.com/ica/v1"

PROVIDERS = [
    # ═══ Tier 0: Primary paid/provisioned API keys (fastest, most reliable) ═══
    # DeepSeek — 5M free tokens, excellent quality, provisioned API key
    ("deepseek/deepseek-chat", "DEEPSEEK_API_KEY", 0, True, None),

    # ═══ Tier 1: API-key-free fallback (no signup needed, just set USE_ flag) ═══
    # Kilo Gateway — 200 req/hour per IP, no account required
    # Uses openai/ prefix with custom api_base for LiteLLM compatibility.
    ("openai/kilo-auto/free", "USE_KILO_GATEWAY", 1, False, KILO_API_BASE),
    ("openai/nvidia/nemotron-3-super-120b-a12b:free", "USE_KILO_GATEWAY", 1, False, KILO_API_BASE),
    ("openai/poolside/laguna-s-2.1:free", "USE_KILO_GATEWAY", 1, False, KILO_API_BASE),
    ("openai/nvidia/nemotron-3-ultra-550b-a55b:free", "USE_KILO_GATEWAY", 1, False, KILO_API_BASE),
    ("openai/openrouter/free", "USE_KILO_GATEWAY", 1, False, KILO_API_BASE),

    # ═══ Tier 2: Secondary API-key providers ═══
    ("groq/" + GROQ_MODEL, "GROQ_API_KEY", 2, True, None),

    # ═══ Tier 3: Excellent free tiers (no credit card) ═══
    ("gemini/gemini-2.0-flash-exp", "GEMINI_API_KEY", 3, True, None),
    ("cerebras/gpt-oss-120b", "CEREBRAS_API_KEY", 3, True, None),
    ("mistral/mistral-large-2407", "MISTRAL_API_KEY", 3, True, None),
    ("gemini/gemini-1.5-pro", "GEMINI_API_KEY", 3, True, None),

    # ═══ Tier 3b: IBM Advantage Models (free tier, OpenAI-compatible /v1 endpoint) ═══
    # All 4 models use the same IBM_ADVANTAGE_API_KEY + IBM_ADVANTAGE_BASE_URL.
    # Model names use ibm/ prefix so they're clearly identifiable in logs and the router.
    ("ibm/claude-haiku-4-5", "IBM_ADVANTAGE_API_KEY", 3, True, IBM_ADVANTAGE_BASE_URL),
    ("ibm/meta-llama/llama-4-maverick-17b-128e-instruct-fp8", "IBM_ADVANTAGE_API_KEY", 3, True, IBM_ADVANTAGE_BASE_URL),
    ("ibm/gemma-4-26b-a4b-it", "IBM_ADVANTAGE_API_KEY", 3, True, IBM_ADVANTAGE_BASE_URL),
    ("ibm/granite-4-h-small", "IBM_ADVANTAGE_API_KEY", 3, True, IBM_ADVANTAGE_BASE_URL),

    # ═══ Tier 4: Good free tiers (no credit card) ═══
    ("openrouter/meta-llama/llama-3.3-70b-instruct:free", "OPENROUTER_API_KEY", 4, True, None),
    ("sambanova/Meta-Llama-3.3-70B-Instruct", "SAMBANOVA_API_KEY", 4, True, None),
    ("cohere/command-r", "COHERE_API_KEY", 4, True, None),

    # ═══ Tier 5: Moderate free tiers ═══
    ("cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast", "CLOUDFLARE_API_KEY", 5, True, None),
    ("nvidia/meta/llama-3.3-70b-instruct", "NVIDIA_API_KEY", 5, True, None),
    ("huggingface/meta-llama/Llama-3.3-70B-Instruct", "HUGGINGFACE_API_KEY", 5, True, None),
    ("github/gpt-4o-mini", "GITHUB_TOKEN", 5, True, None),

    # ═══ Tier 6: Trial/credit-based (use when others exhausted) ═══
    ("together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY", 6, True, None),
    ("ai21/jamba-1.5-large", "AI21_API_KEY", 6, True, None),
    ("xai/grok-beta", "XAI_API_KEY", 6, True, None),
]

# ═══════════════════════════════════════════════════════════════════════════════
#  RATE LIMIT TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

_last_rate_limit_time = 0
_current_provider_index = 0
_failed_providers: set = set()
_provider_cooldowns: dict = {}  # model_name -> cooldown_until timestamp


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Dummy API key for OpenAI-compatible gateways that don't require authentication.
# The OpenAI Python client requires a non-empty api_key string, so we provide
# this dummy key for key-free providers like Kilo Gateway.
DUMMY_API_KEY = "sk-no-key-required"


def _get_available_providers() -> list[tuple]:
    """
    Return providers that are available (API key configured OR key-free flag set),
    sorted by priority with random shuffle within each tier.

    Key-free providers (requires_api_key=False) are included when their USE_ flag
    is set to "true" (case-insensitive) or "1". If no USE_ flag is set at all,
    they default to ENABLED so the bot always has at least some LLM access.

    For key-free providers that use an OpenAI-compatible api_base, a dummy API key
    (DUMMY_API_KEY) is passed to satisfy the OpenAI Python client's requirement
    for a non-empty api_key string. The gateway ignores the dummy key.
    """
    available = []
    for entry in PROVIDERS:
        model, env_var, weight, requires_api_key, api_base = entry

        if requires_api_key:
            # Standard API-key provider: check if key is set
            api_key = os.getenv(env_var, "")
            if api_key:
                available.append((model, env_var, weight, api_key, api_base))
        else:
            # Key-free provider: check USE_ flag (default: enabled)
            flag = os.getenv(env_var, "").strip().lower()
            if flag in ("", "true", "1", "yes"):
                # Key-free providers use a dummy API key to satisfy the
                # OpenAI Python client. The gateway ignores the dummy key.
                available.append((model, env_var, weight, DUMMY_API_KEY, api_base))

    if not available:
        logger.warning(
            "No providers available! Set at least GROQ_API_KEY in .env, "
            "or set USE_KILO_GATEWAY=true for API-key-free access. "
            "See provider_router.py docstring for all supported providers."
        )
        # Last resort: try Groq even without key (will fail gracefully)
        available.append((f"groq/{GROQ_MODEL}", "GROQ_API_KEY", 1, os.getenv("GROQ_API_KEY", ""), None))

    # Sort by weight
    available.sort(key=lambda x: x[2])

    # Shuffle within same weight groups for load distribution
    result = []
    i = 0
    while i < len(available):
        j = i
        while j < len(available) and available[j][2] == available[i][2]:
            j += 1
        group = available[i:j]
        random.shuffle(group)
        result.extend(group)
        i = j

    return result


def get_llm(
    model: Optional[str] = None,
    temperature: float = AGENT_TEMPERATURE,
    max_tokens: int = 4096,
    provider_override: Optional[str] = None,
) -> BaseChatModel:
    """
    Create a LangChain chat model via LiteLLM with automatic provider fallback.

    Args:
        model: Override the full model name (e.g., "groq/llama-3.3-70b-versatile").
        temperature: Response creativity (0.0 = deterministic, 1.0 = creative).
        max_tokens: Maximum tokens in the response.
        provider_override: Force a specific provider prefix (e.g., "groq", "gemini").

    Returns:
        A configured ChatLiteLLM instance ready for .invoke().

    Example:
        llm = get_llm()
        response = llm.invoke("What is the capital of France?")

        # Force a specific provider
        llm = get_llm(provider_override="cerebras")
    """
    global _current_provider_index, _last_rate_limit_time

    providers = _get_available_providers()

    if model:
        logger.info(f"Using explicitly requested model: {model}")
        return ChatLiteLLM(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if provider_override:
        filtered = [p for p in providers if p[0].startswith(provider_override)]
        if filtered:
            providers = filtered

    # Reset failed providers after 60 seconds of no failures
    global _failed_providers
    if time.time() - _last_rate_limit_time > 60:
        _failed_providers.clear()

    # Clear expired cooldowns
    now = time.time()
    expired = [m for m, t in _provider_cooldowns.items() if t < now]
    for m in expired:
        _provider_cooldowns.pop(m, None)

    # Try providers in order, skipping failed/cooldown ones
    for i in range(len(providers)):
        idx = (_current_provider_index + i) % len(providers)
        model_name, env_key, weight, api_key, api_base = providers[idx]

        if model_name in _failed_providers:
            continue
        if model_name in _provider_cooldowns:
            continue

        logger.info(f"Selected LLM provider: {model_name}")
        _current_provider_index = (idx + 1) % len(providers)

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base

        return ChatLiteLLM(**kwargs)

    # All providers exhausted — reset and try primary
    logger.warning("All providers were rate-limited. Resetting and trying primary.")
    _failed_providers.clear()
    _provider_cooldowns.clear()
    model_name, env_key, weight, api_key, api_base = providers[0]

    kwargs = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    return ChatLiteLLM(**kwargs)


def mark_provider_failed(model_name: str, cooldown_seconds: int = 30):
    """
    Mark a provider as failed (e.g., rate limited).
    Call this when you catch a rate limit error from the LLM.

    Args:
        model_name: The model/provider that failed (e.g., "groq/llama-3.3-70b-versatile").
        cooldown_seconds: How long to wait before retrying (default: 30s).
    """
    global _last_rate_limit_time, _failed_providers, _provider_cooldowns
    _last_rate_limit_time = time.time()
    _failed_providers.add(model_name)
    _provider_cooldowns[model_name] = time.time() + cooldown_seconds
    logger.warning(
        f"Marked provider as failed (rate limited): {model_name} "
        f"(cooldown: {cooldown_seconds}s)"
    )


def get_configured_providers() -> list[str]:
    """
    Return a human-readable list of currently configured providers.
    Useful for logging, status displays, and debugging.
    """
    return [p[0] for p in _get_available_providers()]


def get_provider_count() -> int:
    """Return the number of currently configured providers."""
    return len(_get_available_providers())


# ═══════════════════════════════════════════════════════════════════════════════
#  CONVENIENCE WRAPPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_groq_llm(
    model: str = GROQ_MODEL,
    temperature: float = AGENT_TEMPERATURE,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """Get a Groq LLM (routes through LiteLLM multi-provider)."""
    return get_llm(
        model=f"groq/{model}",
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_analytical_llm() -> BaseChatModel:
    """Get a low-temperature LLM for analytical/execution tasks (temp=0.2)."""
    return get_llm(temperature=0.2)


def get_creative_llm() -> BaseChatModel:
    """Get a higher-temperature LLM for strategy/creative tasks (temp=0.8)."""
    return get_llm(temperature=0.8)


# ═══════════════════════════════════════════════════════════════════════════════
#  SELF-TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        LiteLLM Provider Router — Self Test                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    providers = get_configured_providers()
    print(f"📋 Configured providers ({len(providers)}):")
    for p in providers:
        print(f"   • {p}")
    print()

    print("🔧 Testing LLM creation...")
    llm = get_llm()
    print(f"   ✅ Created: {type(llm).__name__} (model={llm.model})")
    if hasattr(llm, 'api_base') and llm.api_base:
        print(f"   📡 API Base: {llm.api_base}")

    llm2 = get_analytical_llm()
    print(f"   ✅ Analytical LLM: {type(llm2).__name__}")

    llm3 = get_creative_llm()
    print(f"   ✅ Creative LLM: {type(llm3).__name__}")

    print()
    print("🎉 All tests passed!")
