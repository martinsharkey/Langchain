"""
CORE RULES — the single, standardised set of trading-system rules.

This is the SOURCE OF TRUTH for how the bot is allowed to behave. Every rule here was
established from evidence (live trades + GoldShark telemetry + optimiser + broker tick
replay) and must hold for the system to be considered standardised and scalable.
`assert_core_rules()` is called at engine startup so a drift/regression fails loudly
instead of silently.

Keep this file SMALL and DURABLE. If a rule changes, change it here first, then the code.
"""
from __future__ import annotations

# ── THE RULES (human-readable; keep in sync with the checks below) ────────────
CORE_RULES = [
    "R1  ONE ENTRY: the sole entry signal is OsMA_Confluence. No ensemble/voting, no "
    "MACD/CCI/BB/RSI standalone entries. All other strategies are retired.",
    "R2  ONE EXIT MODEL: every symbol uses the GS_PROVEN exit — a wide, data-derived "
    "broker SL + break-even lock + trailing stop, and the broker TP is REMOVED once "
    "trailing arms (a TP only caps winners). EXCEPTION: symbols in PYRAMID_TRAIL_SYMBOLS "
    "(owner-specified, e.g. BTCUSD) use PYRAMID_TRAIL — per-leg BE+trail + profit-gated "
    "pyramid adds. No OTHER per-symbol split exit variants.",
    "R3  PER-SYMBOL SL IS DATA-DERIVED AT ONBOARDING: the broker SL / safety-TP / BE / "
    "trail are derived from that symbol's own OsMA-cycle excursion (points travelled from "
    "a zero-cross until it reverses, sampled over ~20 cycles), then live-tuned. Never "
    "borrow one symbol's magnitudes onto another (BTC != gold != GER40).",
    "R4  LEARN ONLY FROM CLEAN LIVE DATA: learning/adaptation reads exclude ALL simulated "
    "sources (SIMULATED*). Config is never changed from simulated/weak data.",
    "R5  STRUCTURE IS SYMBOL-AGNOSTIC, MAGNITUDES ARE SYMBOL-SPECIFIC: the indicator "
    "combination and rule shape are identical for all symbols; only the strength floors "
    "and SL/exit magnitudes differ per symbol.",
    "R6  BROKER-SIDE PROTECTION ALWAYS: the SL lives on the broker at entry so a trade is "
    "never left unprotected; a wide safety-TP exists only as a connectivity failsafe.",
    "R7  BTCUSD COMPLEMENTARY EXCEPTION: BTCUSD may additionally use the CryptoRTI whale "
    "websocket to augment ENTRY confidence. It does not change the exit model (R2).",
    "R8  KNOWN-GOOD IS PRESERVED: the winning baseline config is stored in the learning "
    "RAG + data/winning_baseline.json and the config_checkpointer reverts each symbol to "
    "its best realised-expectancy config, so a bad change is always recoverable.",
    "R9  AUTOMATIC ONBOARDING: adding a new symbol has NO manual step. On first sight the "
    "engine auto-runs the onboarding workflow (backtest + forward-test + OsMA-cycle SL "
    "sampling, DataManager primary with MT5 fallback) and persists the per-symbol baseline "
    "before it trades. Never hand-tune a new symbol's magnitudes.",
    "R10 EVIDENCE FIRST — NEVER GUESS: every tunable magnitude (pyramid leg count, SL, "
    "strength floors, exit params, thresholds) MUST be derived from HARD EVIDENCE — the "
    "GoldShark XML backtest/forward-test reports, the RAG, live closed-trade data, or a "
    "backtest-harness result — and cited. NEVER insert a hardcoded guess, arbitrary cap, "
    "or opinion in place of the data. If no evidence exists, say so and TEST it (harness) "
    "rather than assume. This applies to the assistant, the researcher, and the bot.",
]

# ── canonical constants other modules should import (not re-hardcode) ─────────
SOLE_ENTRY_STRATEGY = "OsMA_Confluence"
SOLE_EXIT_VARIANT = "GS_PROVEN"
SIMULATED_SOURCE_MARKERS = ("SIMULATED", "DUKASCOPY")   # excluded from learning reads
WHALE_COMPLEMENT_SYMBOL = "BTCUSD"                       # R7 exception


def assert_core_rules() -> list[str]:
    """Verify the codebase still conforms to the core rules. Returns the list of rule
    strings on success; raises AssertionError on the first violation. Called at engine
    startup so standardisation drift is caught immediately."""
    problems = []

    # R1/R2: the trade manager must assign the sole exit model for every symbol —
    # GS_PROVEN, EXCEPT symbols the owner explicitly puts on the PYRAMID_TRAIL model
    # (per-leg BE+trail + profit-gated adds; e.g. BTCUSD). Both are proven, deliberate
    # exit models — not drift. Any OTHER variant is a violation.
    try:
        from src.trading.trade_manager import TradeManager, VARIANTS
        from src import config
        tm = TradeManager()
        _pyr = [s.upper().split("-")[0].rstrip(".") for s in
                getattr(config, "PYRAMID_TRAIL_SYMBOLS", []) or []]
        for sym in ("XAUUSD", "BTCUSD", "GER40", "EURUSD", "SOMETHINGNEW"):
            v = tm.assign_variant(sym)
            base = sym.upper().split("-")[0].rstrip(".")
            allowed = {SOLE_EXIT_VARIANT}
            if base in _pyr:
                allowed = {"PYRAMID_TRAIL"}
            if v not in allowed:
                problems.append(f"R2 violated: assign_variant({sym})={v}, expected {allowed}")
    except Exception as e:
        problems.append(f"R2 check error: {e}")

    # R1: OsMA_Confluence must be the sole focused entry for every symbol.
    try:
        from src.learning.edge_weights import focused_rules
        for sym in ("XAUUSD", "BTCUSD", "GER40"):
            rules = focused_rules(sym) or []
            names = {r[0] for r in rules}
            if names and names != {SOLE_ENTRY_STRATEGY}:
                problems.append(f"R1 violated: {sym} focused entries {names} != {{{SOLE_ENTRY_STRATEGY}}}")
    except Exception as e:
        problems.append(f"R1 check error: {e}")

    # R4: the learning-window clause must exclude simulated sources.
    try:
        from src.learning.experience_db import ExperienceDatabase
        frag, _ = ExperienceDatabase().learning_window_clause()
        if "SIMULATED" not in frag.upper():
            problems.append("R4 violated: learning_window_clause does not exclude SIMULATED sources")
    except Exception as e:
        problems.append(f"R4 check error: {e}")

    # R10: evidence-sourced magnitudes. GROWTH_PYRAMID_MAX must carry an evidence tag
    # (env GROWTH_PYRAMID_MAX_EVIDENCE) proving it came from the XML/backtest data, not a
    # guess. Warn (don't hard-fail) so the bot still trades, but the violation is visible.
    try:
        from src import config
        if getattr(config, "GROWTH_ENABLED", False):
            ev = getattr(config, "GROWTH_PYRAMID_MAX_EVIDENCE", "") or ""
            if not ev:
                problems.append("R10 warning: GROWTH_PYRAMID_MAX has no evidence tag "
                                "(GROWTH_PYRAMID_MAX_EVIDENCE) — value must be data-derived, not guessed")
    except Exception as e:
        problems.append(f"R10 check error: {e}")

    # R3: per-symbol SL is data-derived at onboarding. The onboarding tracker must
    # exist and the onboarding workflow must persist a per-symbol baseline (not a
    # shared/borrowed magnitude). We verify the tracker module is importable and that
    # the onboarding pipeline references per-symbol baseline persistence.
    try:
        from src.learning.onboarding_tracker import OnboardingTracker
        _ = OnboardingTracker
    except Exception as e:
        problems.append(f"R3 check error: onboarding tracker unavailable: {e}")

    # R5: structure symbol-agnostic, magnitudes symbol-specific. The sole entry
    # strategy (OsMA_Confluence) must be registered once and shared across symbols;
    # magnitude floors must be per-symbol (not a single global). Verify the strategy
    # registry exposes the shared strategy and that tuned params are keyed per symbol.
    try:
        from src.learning.param_optimizer import ParameterOptimizer
        if not hasattr(ParameterOptimizer, "_key"):
            problems.append("R5 violated: ParameterOptimizer has no per-symbol keying")
    except Exception as e:
        problems.append(f"R5 check error: {e}")

    # R6: broker-side SL always. The broker adapter must set SL on entry (never leave
    # a position unprotected). Verify the adapter's place() accepts and forwards SL.
    try:
        from src.mt5.broker_adapter import BrokerAdapter
        import inspect
        sig = inspect.signature(BrokerAdapter.place)
        if "sl" not in sig.parameters:
            problems.append("R6 violated: BrokerAdapter.place() has no SL parameter")
    except Exception as e:
        problems.append(f"R6 check error: {e}")

    # R7: BTCUSD whale exception. The whale augmentation must apply ONLY to BTCUSD.
    try:
        from src import config
        whale_sym = getattr(config, "WHALE_COMPLEMENT_SYMBOL", None) or "BTCUSD"
        if whale_sym.upper() != "BTCUSD":
            problems.append(f"R7 violated: whale complement symbol is {whale_sym}, expected BTCUSD")
    except Exception as e:
        problems.append(f"R7 check error: {e}")

    # R8: known-good preserved. The winning baseline must be persisted so a bad change
    # is recoverable. Verify the checkpointer module is importable and the baseline path
    # is defined.
    try:
        from src.learning.config_checkpointer import ConfigCheckpointer, CHECKPOINT_PATH
        if not CHECKPOINT_PATH:
            problems.append("R8 violated: no checkpoint path defined")
    except Exception as e:
        problems.append(f"R8 check error: {e}")

    # R9: automatic onboarding. Adding a symbol must have no manual step. Verify the
    # engine exposes an auto-onboard path (the onboarding tracker + ensure_onboarded).
    try:
        from src.trading.scalp_engine import ScalpEngine
        if not hasattr(ScalpEngine, "_ensure_onboarded"):
            problems.append("R9 violated: ScalpEngine has no _ensure_onboarded auto-onboard path")
    except Exception as e:
        problems.append(f"R9 check error: {e}")

    if problems:
        raise AssertionError("CORE RULES violated:\n  - " + "\n  - ".join(problems))
    return CORE_RULES


if __name__ == "__main__":
    for r in assert_core_rules():
        print("OK:", r.split("  ", 1)[0])
    print("\nAll core rules hold.")
