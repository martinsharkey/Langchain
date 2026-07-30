"""
Central configuration for the LangChain XAUUSD Trading Bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ─── API-Key-Free LLM Providers (no signup needed) ──────────
# Kilo Gateway works WITHOUT any API key. Just set the USE_ flag to "true".
# It is tried first (Tier 0) since it costs nothing and needs no account.

# Kilo Gateway — 200 req/hour per IP, no account required
# Free models: Nemotron 3 Super 120B, Ling 3.0 Flash, Laguna S 2.1
USE_KILO_GATEWAY = os.getenv("USE_KILO_GATEWAY", "true").lower() in ("true", "1", "yes")

# ─── LLM Provider API Keys ──────────────────────────────────
# At least ONE of these is recommended. The more configured, the more
# free tokens available via LiteLLM automatic fallback.

# Groq (primary - fastest LPU inference, 1,000 RPD free)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Google Gemini (very generous free tier: 15-30 RPM, 1,500 RPD)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Cerebras (ultra-fast: ~2,600 tok/s, 1M tokens/day free)
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")

# Mistral AI (~1B tokens/month free, Experiment plan)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# OpenRouter (~22 free models, 20 RPM, 200 RPD)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# SambaNova (20 RPM, 200K tokens/day, ultra-fast RDU)
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")

# Cohere (1,000 req/month, 20 RPM)
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# Cloudflare Workers AI (10,000 neurons/day)
CLOUDFLARE_API_KEY = os.getenv("CLOUDFLARE_API_KEY", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")

# NVIDIA NIM (40 RPM, free with developer program)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# HuggingFace Inference (100K credits/month)
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")

# GitHub Models (free for all GitHub users, 50 RPD)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Together AI (free research models)
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# DeepSeek (5M free tokens, 30-day trial)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# AI21 Labs (trial credits)
AI21_API_KEY = os.getenv("AI21_API_KEY", "")

# xAI / Grok ($25 signup credit)
XAI_API_KEY = os.getenv("XAI_API_KEY", "")

# ─── MetaTrader 5 ───────────────────────────────────────────
_mt5_account_str = os.getenv("MT5_ACCOUNT", "0")
try:
    MT5_ACCOUNT = int(_mt5_account_str)
except (ValueError, TypeError):
    MT5_ACCOUNT = 0
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# ─── Trading Parameters ─────────────────────────────────────
SYMBOL = "XAUUSD"
TIMEFRAME = "H1"          # Primary timeframe for analysis
ENTRY_TIMEFRAME = "M15"   # Timeframe for entry signals
RISK_PERCENT = float(os.getenv("XAUUSD_RISK_PERCENT", "1.0"))
MAX_POSITION_SIZE = float(os.getenv("XAUUSD_MAX_POSITION_SIZE", "0.1"))
MIN_RISK_REWARD_RATIO = 2.0

# ─── Agent Configuration ────────────────────────────────────
AGENT_TEMPERATURE = 0.7
AGENT_MAX_ITERATIONS = 25
AGENT_MAX_TOKENS = 4096

# ─── Paths ──────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

# ─── Validation ─────────────────────────────────────────────
def validate_config() -> list[str]:
    """Check configuration and return list of missing/invalid settings."""
    warnings = []

    # Check LLM providers (at least one API key OR key-free flag required)
    llm_keys = [
        ("GROQ_API_KEY", GROQ_API_KEY),
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("CEREBRAS_API_KEY", CEREBRAS_API_KEY),
        ("MISTRAL_API_KEY", MISTRAL_API_KEY),
        ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
        ("SAMBANOVA_API_KEY", SAMBANOVA_API_KEY),
        ("COHERE_API_KEY", COHERE_API_KEY),
        ("CLOUDFLARE_API_KEY", CLOUDFLARE_API_KEY),
        ("NVIDIA_API_KEY", NVIDIA_API_KEY),
        ("HUGGINGFACE_API_KEY", HUGGINGFACE_API_KEY),
        ("GITHUB_TOKEN", GITHUB_TOKEN),
        ("TOGETHER_API_KEY", TOGETHER_API_KEY),
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
        ("AI21_API_KEY", AI21_API_KEY),
        ("XAI_API_KEY", XAI_API_KEY),
    ]
    configured_llms = [name for name, val in llm_keys if val]
    key_free_enabled = USE_KILO_GATEWAY
    if not configured_llms and not key_free_enabled:
        warnings.append(
            "No LLM API keys configured! Set at least GROQ_API_KEY in .env file, "
            "or set USE_KILO_GATEWAY=true for API-key-free access. "
            "See .env.example for all supported providers."
        )
    elif key_free_enabled and not configured_llms:
        warnings.append(
            "Using API-key-free Kilo Gateway provider. "
            "This has lower rate limits (200 req/hr). "
            "Configure GROQ_API_KEY for better reliability."
        )

    # MT5 configuration - REQUIRED (no simulation mode)
    if MT5_ACCOUNT == 0:
        raise ValueError(
            "CRITICAL: MT5_ACCOUNT environment variable is not set or invalid.\n"
            "The trading bot requires a live MT5 account to operate.\n"
            "Set MT5_ACCOUNT in your .env file (e.g., MT5_ACCOUNT=1176166)"
        )
    if not MT5_PASSWORD:
        raise ValueError(
            "CRITICAL: MT5_PASSWORD environment variable is not set.\n"
            "The trading bot requires MT5 credentials to connect.\n"
            "Set MT5_PASSWORD in your .env file."
        )
    if not MT5_SERVER:
        raise ValueError(
            "CRITICAL: MT5_SERVER environment variable is not set.\n"
            "The trading bot requires MT5 server name to connect.\n"
            "Set MT5_SERVER in your .env file (e.g., MT5_SERVER=VTMarkets-Demo)"
        )

    return warnings
