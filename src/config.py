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
SYMBOL = "XAUUSD"         # Base/primary symbol (broker suffix resolved at runtime)
TIMEFRAME = "H1"          # Primary timeframe for analysis
ENTRY_TIMEFRAME = "M15"   # Timeframe for entry signals
RISK_PERCENT = float(os.getenv("XAUUSD_RISK_PERCENT", "1.0"))
MAX_POSITION_SIZE = float(os.getenv("XAUUSD_MAX_POSITION_SIZE", "0.1"))
MIN_RISK_REWARD_RATIO = 2.0

# ─── Multi-Symbol Trading ───────────────────────────────────
# Base symbols the bot may trade. Broker-specific suffixes (e.g. -ECN, .crp)
# are resolved at runtime by the BrokerAdapter, which selects the TRADABLE
# variant (trade_mode == full). Comma-separated env override supported.
#
# Expanded to a diverse, liquid, tight-spread set across asset classes to plug
# the learning gap and identify what works per instrument:
#   XAUUSD (gold), XAGUSD (silver) - metals
#   BTCUSD, ETHUSD               - crypto (also covered by CryptoRTI)
#   EURUSD, AUDUSD, USDCAD       - FX majors (tight spreads, distinct behaviour)
#   GER40                        - equity index (regime diversity)
# MAX_OPEN_POSITIONS caps total simultaneous exposure across all symbols.
TRADING_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv(
        "TRADING_SYMBOLS",
        "XAUUSD,XAGUSD,BTCUSD,ETHUSD,EURUSD,AUDUSD,USDCAD,GER40"
    ).split(",")
    if s.strip()
]
# Symbols to DISABLE (skip for new entries) without editing the full list.
# XAGUSD (silver) is disabled by default: realised data showed it was the
# single biggest bleeder (net -45.4, avg loss ~5x avg win) — pause it until the
# exit/giveback fix is proven, then re-enable by setting DISABLED_SYMBOLS="".
DISABLED_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("DISABLED_SYMBOLS", "XAGUSD").split(",")
    if s.strip()
]
TRADING_SYMBOLS = [s for s in TRADING_SYMBOLS if s not in DISABLED_SYMBOLS]

# ─── Scalping Mode ──────────────────────────────────────────
# When enabled, the bot trades small, frequent, tight trades to accumulate a
# large sample of real closed outcomes quickly (for learning). Uses 0.01 lots.
SCALP_MODE = os.getenv("SCALP_MODE", "true").lower() in ("true", "1", "yes")
SCALP_LOT = float(os.getenv("SCALP_LOT", "0.01"))
SCALP_TP_POINTS = int(os.getenv("SCALP_TP_POINTS", "400"))   # take-profit distance in points
SCALP_SL_POINTS = int(os.getenv("SCALP_SL_POINTS", "300"))   # stop-loss floor (points) when ATR unavailable
# Backtest-tuned exit system (focused pockets, WITH manager, out-of-sample):
# SL = 1.0*ATR, RR = 2.0, giveback = 0.55  ->  PF 1.35 @ 50% WR. These three
# were tuned TOGETHER because the manager's giveback and the TP interact.
SCALP_SL_ATR_MULT = float(os.getenv("SCALP_SL_ATR_MULT", "1.0"))
SCALP_TP_RR = float(os.getenv("SCALP_TP_RR", "2.0"))
SCALP_GIVEBACK_FRAC = float(os.getenv("SCALP_GIVEBACK_FRAC", "0.6"))
# Peak profit (as a multiple of entry-timeframe ATR) before the giveback guard
# arms. Realised data showed arming at 0.5*ATR cut winners into scratches
# (only 5 TP hits vs 198 early closes); 1.5*ATR lets trades reach TP.
SCALP_GIVEBACK_ARM_ATR = float(os.getenv("SCALP_GIVEBACK_ARM_ATR", "1.5"))
# PROFIT-RETENTION RATCHET (fixes the observed leak: gold trades hit £5+ then
# round-tripped). Once peak profit >= SCALP_RETAIN_ARM_ATR * ATR, the trade must
# keep at least SCALP_RETAIN_FLOOR_FRAC of that peak — an absolute, ratcheting
# floor that fires BEFORE the looser giveback guard. Arms earlier (0.8*ATR) and
# protects harder (keep >=50%) so winners still run but can't hand the move back.
SCALP_RETAIN_FLOOR_FRAC = float(os.getenv("SCALP_RETAIN_FLOOR_FRAC", "0.5"))
SCALP_RETAIN_ARM_ATR = float(os.getenv("SCALP_RETAIN_ARM_ATR", "0.35"))
# FOCUSED mode: trade only validated high-edge (strategy x regime) pockets
# instead of the broad ensemble vote. Backtest: PF 1.24 vs 1.04.
FOCUSED_MODE = os.getenv("FOCUSED_MODE", "true").lower() in ("true", "1", "yes")
SCALP_CONFIDENCE_MIN = float(os.getenv("SCALP_CONFIDENCE_MIN", "0.45"))  # lower bar to build sample
SCALP_TARGET_TRADES = int(os.getenv("SCALP_TARGET_TRADES", "100"))       # learning goal
SCALP_MAX_OPEN_PER_SYMBOL = int(os.getenv("SCALP_MAX_OPEN_PER_SYMBOL", "1"))
SCALP_CYCLE_SECONDS = int(os.getenv("SCALP_CYCLE_SECONDS", "15"))         # loop cadence
# #53 exit-leak fix: manage OPEN POSITIONS this often (fast sub-tick between full
# cycles) so intra-cycle peaks are protected by the ratchet/trail/reversal.
SCALP_MANAGE_SECONDS = int(os.getenv("SCALP_MANAGE_SECONDS", "2"))

# ─── Multi-Timeframe Alignment ──────────────────────────────────────
# Before a fast (1m) entry, require that higher timeframes don't clearly oppose
# the trade direction. Keeps scalps aligned with the broader trend.
MTF_ALIGNMENT_ENABLED = os.getenv("MTF_ALIGNMENT_ENABLED", "true").lower() in ("true", "1", "yes")
MTF_ALIGNMENT_TFS = [s.strip() for s in os.getenv("MTF_ALIGNMENT_TFS", "M15,H1,H4").split(",") if s.strip()]
# A counter-trend signal this confident is allowed through the MTF gate, so the
# bot can take the other side on strong setups instead of only ever trend-trading.
MTF_COUNTERTREND_MIN_CONF = float(os.getenv("MTF_COUNTERTREND_MIN_CONF", "0.7"))
# Confidence penalty applied PER opposing higher timeframe when a signal is
# counter-trend (quality modifier instead of a hard block). A strong signal can
# still clear SCALP_CONFIDENCE_MIN after the penalty; a weak one is filtered out.
MTF_COUNTERTREND_PENALTY = float(os.getenv("MTF_COUNTERTREND_PENALTY", "0.12"))
# Directional-balance guard (#3): the bot showed a persistent LONG bias (buy
# trades ~4x sell volume and far more loss). When enabled, if a symbol's recent
# realised win rate for the PROPOSED direction is materially worse than the
# other direction, trim that direction's confidence so weak trades on the
# losing side are filtered. Symmetric (works for long OR short skew), evidence-
# driven, and only engages once there is a real per-direction sample.
DIRECTIONAL_BALANCE_ENABLED = os.getenv("DIRECTIONAL_BALANCE_ENABLED", "true").lower() in ("true", "1", "yes")
DIRECTIONAL_BALANCE_MIN_SAMPLE = int(os.getenv("DIRECTIONAL_BALANCE_MIN_SAMPLE", "10"))
DIRECTIONAL_BALANCE_PENALTY = float(os.getenv("DIRECTIONAL_BALANCE_PENALTY", "0.1"))
# When an open trade is offside but HTF still aligns (a 'blip'), widen the stop
# by this many ATR (once) so it survives the wick instead of getting stopped out.
HTF_WICK_WIDEN_ATR = float(os.getenv("HTF_WICK_WIDEN_ATR", "1.5"))

# ─── Trading Mode ───────────────────────────────────────────
# Controls how far the bot is allowed to act on its decisions.
# This is the master safety gate for the whole system.
#
#   OBSERVE    — Analyze and log decisions ONLY. No orders, no trade
#                records written. Pure dry-run for building confidence.
#   PAPER      — Simulate fills using real live prices/spread. Positions
#                and outcomes are tracked as PAPER (clearly labelled),
#                but no real order is sent to the broker.
#   LIVE_MICRO — Place REAL orders, hard-capped to micro lots (0.01).
#   LIVE       — Place REAL orders using full configured sizing.
#
# Default is the safest mode. Promotion between modes is gated by the
# readiness system + explicit human approval (see REPAIR_PLAN.md).
_VALID_TRADING_MODES = ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE")
TRADING_MODE = os.getenv("TRADING_MODE", "OBSERVE").strip().upper()
if TRADING_MODE not in _VALID_TRADING_MODES:
    TRADING_MODE = "OBSERVE"

# Micro-lot cap applied when TRADING_MODE == "LIVE_MICRO"
LIVE_MICRO_MAX_LOT = float(os.getenv("LIVE_MICRO_MAX_LOT", "0.01"))
# ── GROWTH ENGINE (compounding + capital extraction) ──
# User model: aggressive compounding from L100; once balance hits GROWTH_EXTRACT_AT,
# "extract" the original stake (GROWTH_INITIAL_CAPITAL) so from then on only PROFIT is
# ever at risk ("never actually lose money"). Sizing = (balance - withdrawn)/BalancePerLot
# * 0.01. Disabled by default (pure-entry proving phase); turn on when ready to grow.
GROWTH_ENABLED = os.getenv("GROWTH_ENABLED", "false").lower() in ("true", "1", "yes")
GROWTH_INITIAL_CAPITAL = float(os.getenv("GROWTH_INITIAL_CAPITAL", "100.0"))
GROWTH_EXTRACT_AT = float(os.getenv("GROWTH_EXTRACT_AT", "1000.0"))   # bank the stake here
GROWTH_BALANCE_PER_LOT = float(os.getenv("GROWTH_BALANCE_PER_LOT", "31.0"))  # pass5469: L31/0.01
GROWTH_MAX_LOT = float(os.getenv("GROWTH_MAX_LOT", "5.0"))            # broker/sanity ceiling
# GROWTH_PYRAMID_MAX is DATA-DERIVED (R10), not a guess. Evidence: GoldShark optimiser
# forward-tested passes (data/reprodata/goldshark13/optimiser_reports): realistic runs
# 363016 Dukascopy (fwd-profitable median 5, max 15) and 1176166 tick (median 10, max 20);
# best forward-profit passes cluster 3-8 legs. Set to the cleanest realistic run's
# forward-validated ceiling (15). The 42-50 leg passes are optimiser range artifacts
# (£1M-on-£100 compounding blow-ups) and are NOT used.
GROWTH_PYRAMID_MAX = int(os.getenv("GROWTH_PYRAMID_MAX", "15"))       # add-to-winner legs (evidence-derived)
GROWTH_PYRAMID_MAX_EVIDENCE = os.getenv(
    "GROWTH_PYRAMID_MAX_EVIDENCE",
    "goldshark XML fwd-tested: duka363016 median5/max15, tick1176166 median10/max20, best 3-8")
GROWTH_DAILY_LOSS_HALT_PCT = float(os.getenv("GROWTH_DAILY_LOSS_HALT_PCT", "30.0"))  # circuit breaker
# BASKET management (multi-leg pyramids): trail the COMBINED value so the basket runs.
# Close the whole basket if combined profit gives back this fraction of its combined peak,
# once the peak passes the arm (points). GoldShark-style InpBasketGivebackPct/PeakThreshold.
GROWTH_BASKET_GIVEBACK_PCT = float(os.getenv("GROWTH_BASKET_GIVEBACK_PCT", "0.35"))
GROWTH_BASKET_ARM_POINTS = float(os.getenv("GROWTH_BASKET_ARM_POINTS", "200.0"))


def is_live_mode() -> bool:
    """True if the current mode places REAL orders on the broker."""
    return TRADING_MODE in ("LIVE_MICRO", "LIVE")


# ─── Learning safety (#27/#23/#25) ──────────────────────────
# The self-learning loop was shown to be net-HARMFUL on the accumulated sample
# (it degraded XAUUSD from +0.117 to -0.669 expectancy). These flags make
# "always learning" SAFE: adaptation can be frozen, and changes that harm live
# realised expectancy can be reverted to a best-known checkpoint.
#
# LEARNING_ADAPTATION_ENABLED=false freezes the harmful online mutations
# (strategy weight updates, personality/giveback reclassification, adaptive
# strategy synthesis/optimizer) while STILL trading, reconciling real outcomes,
# and recording data. i.e. the bot keeps learning DATA but stops auto-tuning
# itself until the tuning is proven safe.
LEARNING_ADAPTATION_ENABLED = os.getenv("LEARNING_ADAPTATION_ENABLED", "true").lower() in ("true", "1", "yes")
# CONTINUAL-LEARNING WINDOW: the pre-fix era (ensemble grab-bag, exact-cross-starved,
# phantom-MFE) poisoned expectancy. The learners must learn from CURRENT behaviour.
#  - LEARNING_REGIME_BREAK: ISO timestamp; trades AT/BEFORE it are excluded from all
#    learning reads (a clean slate after the entry/exit fixes). Empty = no cut.
#  - LEARNING_WINDOW_DAYS: rolling recency window; only trades within the last N days
#    feed the learners, so learning always favours recent behaviour. 0 = no window.
LEARNING_REGIME_BREAK = os.getenv("LEARNING_REGIME_BREAK", "2026-08-04T08:00:00")
LEARNING_WINDOW_DAYS = int(os.getenv("LEARNING_WINDOW_DAYS", "5"))
# Restrict learning to the sole entry strategy (OsMA_Confluence) after cutover so the
# retired ensemble era never trains the bot. NULL strategy rows inside the window are
# kept (pre-attribution). Set false to learn across all strategies.
LEARNING_OSMA_ONLY = os.getenv("LEARNING_OSMA_ONLY", "true").lower() in ("true", "1", "yes")
# Auto-revert: when a symbol's recent realised expectancy degrades vs its
# best-known checkpoint by more than this (in expectancy units), restore the
# checkpoint config and mark the change as a failed direction.
LEARNING_AUTO_REVERT_ENABLED = os.getenv("LEARNING_AUTO_REVERT_ENABLED", "true").lower() in ("true", "1", "yes")
# Minimum closed trades in the evaluation window before revert can trigger.
LEARNING_REVERT_MIN_SAMPLE = int(os.getenv("LEARNING_REVERT_MIN_SAMPLE", "15"))


# ─── Demo vs Live realism ───────────────────────────────────
# Demo accounts fill with ~0 slippage and often tighter spread than a real live
# account. To avoid over-fitting to unrealistically clean demo fills, backtests
# and (optionally) paper simulation add a realism haircut: an assumed extra
# spread + slippage in points applied per trade. Set to demo-realistic values;
# raise for live-account modelling. The engine records account type so we always
# know whether results came from demo or live.
ASSUMED_SLIPPAGE_POINTS = float(os.getenv("ASSUMED_SLIPPAGE_POINTS", "2"))
BACKTEST_SPREAD_HAIRCUT = float(os.getenv("BACKTEST_SPREAD_HAIRCUT", "1.0"))  # x live spread
# Detected at runtime from MT5 (account_info.trade_mode: 0=demo,1=contest,2=real)
ACCOUNT_IS_DEMO = None  # set by the engine on connect


# ─── Risk Management (Phase 3) ──────────────────────────────
# The master safety layer. All limits are % of the START-OF-DAY balance so they
# scale automatically: 50% of a £100 demo is £50; 50% (or a tighter live value)
# of a £50k account is a substantial, balance-relative figure.
#
# Daily-loss halt: when the day's realized loss reaches this % of the day's
# opening balance, the bot stops opening new trades until the daily reset
# (so "the bot can go again" next session/day).
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "50"))   # 50% for demo
# For a live account you'll want this much tighter, e.g. 2–5%.
LIVE_DAILY_LOSS_LIMIT_PCT = float(os.getenv("LIVE_DAILY_LOSS_LIMIT_PCT", "5"))

MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "6"))          # across all symbols
MAX_SPREAD_POINTS = float(os.getenv("MAX_SPREAD_POINTS", "0"))         # 0 = disabled; per-symbol override better
MIN_FREE_MARGIN = float(os.getenv("MIN_FREE_MARGIN", "10"))            # refuse if below

# Magic number stamped on the bot's own orders. Positions with a DIFFERENT magic
# (or 0) are treated as MANUAL trades and adopted/managed by the bot too.
BOT_MAGIC = int(os.getenv("BOT_MAGIC", "987654"))
# Pending trades older than this with no findable closing deal are marked
# 'unknown' so they stop skewing win/loss statistics.
PENDING_STALE_HOURS = float(os.getenv("PENDING_STALE_HOURS", "48"))

# ─── Adaptive Intelligence (L4 reflect / L5 synthesize / L6 backtest) ──
# How often (in engine cycles) to run the adaptive self-improvement pass, and
# the minimum closed-trade sample per symbol before reflection is meaningful.
ADAPTIVE_EVERY_CYCLES = int(os.getenv("ADAPTIVE_EVERY_CYCLES", "240"))  # ~1h at 15s cycles
ADAPTIVE_MIN_SAMPLE = int(os.getenv("ADAPTIVE_MIN_SAMPLE", "10"))

# ─── Autonomous parameter optimizer (self-learning) ──
# The bot mutates indicator params (EMA/OsMA/RSI/CCI periods, SL/RR) per symbol,
# backtests each walk-forward, and keeps only validated improvements. Runs on the
# adaptive cadence. Iterations kept modest so it never blocks trading for long.
OPTIMIZER_ENABLED = os.getenv("OPTIMIZER_ENABLED", "true").lower() in ("true", "1", "yes")
OPTIMIZER_ITERATIONS = int(os.getenv("OPTIMIZER_ITERATIONS", "30"))  # directed coord-search budget/run (covers strength floors + periods)
# Frequency-starvation guard: if a config change drops fire-rate below MIN_FIRE_PCT
# over >= MIN_EVALS evaluations (trading stopped), revert to the last firing config /
# relax the tightest lever — so a change that prevents trading self-corrects.
FREQ_STARVE_MIN_EVALS = int(os.getenv("FREQ_STARVE_MIN_EVALS", "300"))
FREQ_STARVE_MIN_FIRE_PCT = float(os.getenv("FREQ_STARVE_MIN_FIRE_PCT", "0.3"))

# ─── Researcher -> action feedback ──────────────────────────
# Pause new entries on a symbol the PerformanceResearcher flags as bleeding.
# Symbol auto-pause: judged on a RECENT window (not polluted all-time pool), and
# only when BOTH signals are bad (poor recent win rate AND negative recent P&L).
# Prevents quarantining healthy symbols / stopping trading entirely.
SYMBOL_PAUSE_WINDOW = int(os.getenv("SYMBOL_PAUSE_WINDOW", "20"))    # last N closed trades
SYMBOL_PAUSE_MIN_TRADES = int(os.getenv("SYMBOL_PAUSE_MIN_TRADES", "15"))
SYMBOL_PAUSE_PNL = float(os.getenv("SYMBOL_PAUSE_PNL", "-15"))       # recent pnl <= this -> pause (bleeding)
SYMBOL_PAUSE_WINRATE = float(os.getenv("SYMBOL_PAUSE_WINRATE", "25"))  # recent WR < this -> pause (catastrophic)
SYMBOL_PAUSE_HEALTHY_WR = float(os.getenv("SYMBOL_PAUSE_HEALTHY_WR", "45"))  # never pause if WR >= this
# TRAINING MODE: on a demo account we WANT the bot to keep trading + learning even
# on symbols with poor recent history (that is how it gathers the sample to improve
# and to validate a new strategy). When true, the SymbolGovernor pause is ADVISORY
# only — it still records failure reports + de-prioritises, but does NOT hard-block
# new entries. Set false on a live/real account to let the governor freeze bleeders.
# (A dashboard toggle for this is deferred to a future roadmap feature.)
GOVERNOR_PAUSE_BLOCKS_ENTRIES = os.getenv("GOVERNOR_PAUSE_BLOCKS_ENTRIES", "false").lower() in ("true", "1", "yes")
# #20 same-level re-entry guard: block a new entry in the same direction within
# this many ATRs of an existing open position on the symbol (stops repeated
# same-level re-entries like GER40 6x at one price). Set 0 to disable.
REENTRY_MIN_ATR_GAP = float(os.getenv("REENTRY_MIN_ATR_GAP", "0.75"))
# #41: how often (in cycles) to re-measure per-symbol excursion + re-lock the
# MACD-leads-OsMA exit config LIVE (continuous, not once/day). ~40 cycles.
EXIT_CALIBRATION_CYCLES = int(os.getenv("EXIT_CALIBRATION_CYCLES", "40"))
# #43: conservative authority for the (not-yet-validated) CryptoRTI whale boost.
# Small until validate_whale_backtest shows a clear whale_active edge, then raise.
WHALE_BOOST_MAX = float(os.getenv("WHALE_BOOST_MAX", "0.06"))   # max confidence boost
WHALE_SCALE_MAX = float(os.getenv("WHALE_SCALE_MAX", "0.5"))    # max extra lot fraction
# Persisted kill switch file — create/toggle from dashboard or by touching the file.
KILL_SWITCH_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "KILL_SWITCH"
)


def effective_daily_loss_pct() -> float:
    """Daily loss limit % for the current mode (tighter on live)."""
    return LIVE_DAILY_LOSS_LIMIT_PCT if TRADING_MODE == "LIVE" else DAILY_LOSS_LIMIT_PCT


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
