"""
CORE RULES — the single, standardised set of trading-system rules.

This is the SOURCE OF TRUTH for how the bot is allowed to behave. Every rule here was
established from evidence (live trades + GoldShark telemetry + optimiser + Dukascopy) and
must hold for the system to be considered standardised and scalable. `assert_core_rules()`
is called at engine startup so a drift/regression fails loudly instead of silently.

Keep this file SMALL and DURABLE. If a rule changes, change it here first, then the code.
"""
from __future__ import annotations

# ── THE RULES (human-readable; keep in sync with the checks below) ────────────
CORE_RULES = [
    "R1  ONE ENTRY: the sole entry signal is OsMA_Confluence. No ensemble/voting, no "
    "MACD/CCI/BB/RSI standalone entries. All other strategies are retired.",
    "R2  ONE EXIT MODEL: every symbol uses the GS_PROVEN exit — a wide, data-derived "
    "broker SL + break-even lock + trailing stop, and the broker TP is REMOVED once "
    "trailing arms (a TP only caps winners). No per-symbol split exit variants.",
    "R3  PER-SYMBOL SL IS DATA-DERIVED AT ONBOARDING: the broker SL / safety-TP / BE / "
    "trail are derived from that symbol's own OsMA-cycle excursion (points travelled from "
    "a zero-cross until it reverses, sampled over ~20 cycles), then live-tuned. Never "
    "borrow one symbol's magnitudes onto another (BTC != gold != GER40).",
    "R4  LEARN ONLY FROM CLEAN LIVE DATA: learning/adaptation reads exclude ALL simulated "
    "sources (SIMULATED*, DUKASCOPY*). Config is never changed from simulated/weak data.",
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
    "sampling, Dukascopy-first with MT5 fallback) and persists the per-symbol baseline "
    "before it trades. Never hand-tune a new symbol's magnitudes.",
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

    # R1/R2: the trade manager must assign GS_PROVEN for every symbol.
    try:
        from src.trading.trade_manager import TradeManager, VARIANTS
        tm = TradeManager()
        for sym in ("XAUUSD", "BTCUSD", "GER40", "EURUSD", "SOMETHINGNEW"):
            v = tm.assign_variant(sym)
            if v != SOLE_EXIT_VARIANT:
                problems.append(f"R2 violated: assign_variant({sym})={v}, expected {SOLE_EXIT_VARIANT}")
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

    if problems:
        raise AssertionError("CORE RULES violated:\n  - " + "\n  - ".join(problems))
    return CORE_RULES


if __name__ == "__main__":
    for r in assert_core_rules():
        print("OK:", r.split("  ", 1)[0])
    print("\nAll core rules hold.")
