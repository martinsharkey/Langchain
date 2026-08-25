# LiteLLM Providers

**A standalone, drop-in multi-provider LLM router with automatic fallback across 15+ free LLM providers — including Kilo Gateway which works WITHOUT any API key.**

Configure one API key or many — the router handles provider selection, rate-limit tracking, cooldowns, and automatic fallback so your app keeps running even when individual providers hit their free-tier limits.

## Quick Install

```bash
# From GitHub (recommended for reuse across projects)
pip install git+https://github.com/martinsharkey/langchain.git

# Or copy the single file into your project
cp litellm_providers/provider_router.py your-project/
```

## Usage

```python
from litellm_providers import get_llm, get_configured_providers

# Get an LLM — auto-selects best available provider
llm = get_llm()
response = llm.invoke("What is the capital of France?")
print(response.content)

# See which providers you have configured
print(f"Active providers: {get_configured_providers()}")

# Force a specific provider
llm = get_llm(provider_override="cerebras")

# Analytical vs creative modes
analytical = get_llm(temperature=0.2)  # deterministic
creative = get_llm(temperature=0.8)    # creative
```

## Configuration

Create a `.env` file in your project root. **You don't need any API key** — just set the USE_ flag:

```bash
# ═══ Tier 0: API-key-free (no signup needed!) ═══
USE_KILO_GATEWAY=true     # 200 req/hr per IP, no account

# ═══ Tier 1: Primary (API key) ═══
GROQ_API_KEY=gsk_your_key_here

# ═══ Tier 2: Excellent free tiers ═══
GEMINI_API_KEY=AIza_your_key_here
CEREBRAS_API_KEY=your_key_here
MISTRAL_API_KEY=your_key_here

# ═══ Tier 3: Good free tiers ═══
OPENROUTER_API_KEY=your_key_here
SAMBANOVA_API_KEY=your_key_here
COHERE_API_KEY=your_key_here

# ═══ Tier 4: Moderate free tiers ═══
CLOUDFLARE_API_KEY=your_key_here
NVIDIA_API_KEY=your_key_here
HUGGINGFACE_API_KEY=your_key_here
GITHUB_TOKEN=your_token_here

# ═══ Tier 5: Trial/credit-based ═══
TOGETHER_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
AI21_API_KEY=your_key_here
XAI_API_KEY=your_key_here
```

The more keys you configure, the more free tokens you get. The router automatically:
1. Tries providers in priority order (Tier 0 → Tier 5)
2. Shuffles randomly within each tier for load distribution
3. Tracks rate limits and applies cooldowns (default 30s)
4. Falls back to the next provider when one is exhausted
5. Resets all cooldowns after 60s of no failures

## Supported Providers

| Tier | Provider | Free Tier | Rate Limit | API Key Needed? |
|------|----------|-----------|------------|-----------------|
| 0 | **Kilo Gateway** | 200 req/hr per IP | 200 req/hr | **No** |
| 1 | **Groq** | 1,000 req/day | 30 RPM | Yes |
| 2 | **Google Gemini** | 1,500 RPD | 15-30 RPM | Yes |
| 2 | **Cerebras** | 1M tokens/day | 30 RPM | Yes |
| 2 | **Mistral AI** | ~1B tokens/month | 1 RPS | Yes |
| 3 | **OpenRouter** | ~22 free models | 20 RPM, 200 RPD | Yes |
| 3 | **SambaNova** | 200K tokens/day | 20 RPM | Yes |
| 3 | **Cohere** | 1,000 req/month | 20 RPM | Yes |
| 4 | **Cloudflare** | 10K neurons/day | Varies | Yes |
| 4 | **NVIDIA NIM** | 40 RPM | Free dev program | Yes |
| 4 | **HuggingFace** | 100K credits/month | Varies | Yes |
| 4 | **GitHub Models** | 50 RPD | 10 RPM | Yes |
| 5 | **Together AI** | Free research models | Varies | Yes |
| 5 | **DeepSeek** | 5M tokens (30 day) | Standard | Yes |
| 5 | **AI21 Labs** | Trial credits | Varies | Yes |
| 5 | **xAI/Grok** | $25 credit | Varies | Yes |

## API Reference

### `get_llm(model=None, temperature=0.7, max_tokens=4096, provider_override=None) -> BaseChatModel`
Create a LangChain chat model with automatic provider fallback.

### `get_groq_llm(model, temperature, max_tokens) -> BaseChatModel`
Convenience wrapper for Groq (routes through multi-provider).

### `get_analytical_llm() -> BaseChatModel`
Low-temperature LLM (0.2) for deterministic tasks.

### `get_creative_llm() -> BaseChatModel`
Higher-temperature LLM (0.8) for creative tasks.

### `mark_provider_failed(model_name, cooldown_seconds=30)`
Mark a provider as rate-limited. Call when you catch a rate limit error.

### `get_configured_providers() -> list[str]`
List all currently configured (API key present) providers.

### `get_provider_count() -> int`
Number of configured providers.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
│  llm = get_lll() → llm.invoke("...")                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              LiteLLM Provider Router                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │  Groq    │  │  Gemini  │  │ Cerebras │  │  ... 15+   │  │
│  │ (Tier 1) │  │ (Tier 2) │  │ (Tier 2) │  │  providers │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬─────┘  │
│       │              │             │                │        │
│       └──────────────┴─────────────┴────────────────┘        │
│                         │                                    │
│              Auto-fallback on rate limit                      │
└──────────────────────────────────────────────────────────────┘
```

## License

MIT — use it anywhere, in any project.
