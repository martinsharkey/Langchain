"""QMMP Checkpoint Bridge (HLD A): translate live checkpoint configs into model.json.

The live adaptive loop (`scalp_engine.py` + `config_checkpointer.py`) and the
onboarding pipeline (`onboard_pipeline.py` → `ea_generator.py`) use different schemas.
This module bridges them by reading `data/config_checkpoints.json` and producing a
`model.json`-shaped dict that `ea_generator.py` can consume.

Key mapping decisions are flagged in the output so live-derived EAs are never
mistaken for historically-validated ones.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def _default_model(symbol: str, timeframe: str = "H1") -> dict:
    """Minimum viable model.json shell."""
    return {
        "symbol": symbol,
        "status": "LIVE_CHECKPOINT",
        "onboarded_at": str(datetime.now(timezone.utc).date()),
        "build": 0,
        "timeframe": timeframe,
        "path_timeframe": timeframe,
        "source": "live_checkpoint",
        "entry": {
            "signal": "OsMA zero-cross",
            "osma_params": {"fast": 12, "slow": 26, "signal": 9},
        },
        "floors": {
            "osma_mag": {},
            "ema_align": {},
            "bulls": {},
            "bears": "OFF (live checkpoint)",
            "atr": {},
        },
        "exit": {
            "sl": 628348,
            "be": 11057,
            "trail": 11057,
            "add": 11057,
            "early": 0.15,
            "max_legs": 4,
        },
        "money_management": {
            "gbp_per_001": 50.0,
            "lot_cap_per_account": 100,
            "base_balance": 5000.0,
        },
    }


def _load_existing_model(symbol: str, output_dir: str | None = None) -> tuple[dict, str]:
    """Load existing model.json to preserve/increment build counter."""
    if output_dir is None:
        output_dir = os.path.join("data", "qmmp", symbol.upper())
    model_path = os.path.join(output_dir, "model.json")
    if os.path.exists(model_path):
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                return json.load(f), model_path
        except Exception:
            pass
    return {}, model_path


def _global_to_session_floors(live_config: dict) -> tuple[dict, list[str]]:
    """Map live global thresholds to per-session floor dicts.

    The live gate uses global continuous thresholds (e.g. `osma_min_long`, `bulls_min_long`)
    rather than per-session buckets. We apply the live value uniformly across all three
    sessions as a starting approximation.

    Returns (floors_dict, approximation_notes).
    """
    floors: dict[str, Any] = {}
    notes: list[str] = []

    SESSIONS = ("Asian", "London", "NewYork")

    # OsMA magnitude floor
    osma_min = live_config.get("osma_min_long", 0.0)
    if osma_min and float(osma_min) > 0:
        floors["osma_mag"] = {s: float(osma_min) for s in SESSIONS}
        notes.append(f"osma_mag floors set uniformly from live osma_min_long={osma_min} (no per-session split in live gate)")

    # EMA alignment floor
    ema_slope = live_config.get("min_ema_slope", 0.0)
    if ema_slope and float(ema_slope) > 0:
        floors["ema_align"] = {s: float(ema_slope) for s in SESSIONS}
        notes.append(f"ema_align floors set uniformly from live min_ema_slope={ema_slope} (no per-session split in live gate)")

    # Bulls/Bears power floors (direction-aware)
    bulls_long = live_config.get("bulls_min_long", 0.0)
    bulls_short = live_config.get("bulls_max_short", 0.0)
    bears_long = live_config.get("bears_min_long", 0.0)
    bears_short = live_config.get("bears_max_short", 0.0)

    if bulls_long and float(bulls_long) > 0:
        floors["bulls"] = {}
        for s in SESSIONS:
            floors["bulls"][f"{s}_long"] = float(bulls_long)
            # use actual short-side key if present; otherwise mirror
            short_val = float(bulls_short) if bulls_short else -float(bulls_long)
            floors["bulls"][f"{s}_short"] = short_val
        notes.append(f"bulls floors: long={bulls_long}, short={bulls_short if bulls_short else '-mirrored from long'} (live gate is direction-aware)")

    if bears_long and float(bears_long) > 0:
        if "bears" not in floors:
            floors["bears"] = {}
        for s in SESSIONS:
            floors["bears"][f"{s}_long"] = -float(bears_long) if bears_long else 0.0
            # use actual short-side key if present; otherwise mirror
            short_val = float(bears_short) if bears_short else float(bears_long)
            floors["bears"][f"{s}_short"] = short_val
        notes.append(f"bears floors: long={-float(bears_long) if bears_long else 0}, short={bears_short if bears_short else bears_long} (live gate is direction-aware)")

    # ATR floor
    atr_min = live_config.get("atr_min", 0.0)
    if atr_min and float(atr_min) > 0:
        floors["atr"] = {s: float(atr_min) for s in SESSIONS}
        notes.append(f"atr floors set uniformly from live atr_min={atr_min} (no per-session split in live gate)")

    return floors, notes


def _map_exit_params(live_config: dict) -> dict:
    """Map live exit param names to model.json exit block names."""
    return {
        "sl": float(live_config.get("hard_sl_points", 628348)),
        "be": float(live_config.get("be_trigger_pts", 11057)),
        "trail": float(live_config.get("trail_points", 11057)),
        "add": float(live_config.get("be_trigger_pts", 11057)),  # add = be_trigger_pts if not separate
        "early": 0.15,
        "max_legs": 4,
    }


def _map_osma_params(live_config: dict) -> dict:
    """Map live OsMA param names to model.json entry.osma_params block."""
    return {
        "fast": int(live_config.get("osma_fast", 12)),
        "slow": int(live_config.get("osma_slow", 26)),
        "signal": int(live_config.get("osma_signal", 9)),
    }


def build_model_from_checkpoint(
    symbol: str,
    checkpoint: dict | None = None,
    checkpoint_path: str = "data/config_checkpoints.json",
    min_sample: int = 30,
    min_expectancy: float = 0.0,
    timeframe: str = "H1",
) -> dict:
    """Read a live checkpoint and produce a model.json-shaped dict suitable for `ea_generator.py`.

    Args:
        symbol: Symbol to bridge (e.g. "XAUUSD", "BTCUSD").
        checkpoint: Pre-loaded checkpoint dict. If None, read from `checkpoint_path`.
        checkpoint_path: Path to `config_checkpoints.json` (used only if `checkpoint` is None).
        min_sample: Minimum closed trades required before live checkpoint is considered reliable.
        min_expectancy: Minimum realised expectancy required (per trade, GBP).
        timeframe: Timeframe to tag the model with (default H1 for crypto, M15 for gold).

    Returns:
        model.json-shaped dict, or raises ValueError if checkpoint is unreliable.
    """
    if checkpoint is None:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)

    best = checkpoint.get(symbol.upper(), checkpoint.get(symbol, {})).get("best", {})
    if not best:
        raise ValueError(f"No checkpoint found for symbol={symbol}")

    live_cfg = best.get("config", {})
    expectancy = best.get("expectancy", best.get("exp", 0.0))
    n = best.get("n", best.get("sample_size", 0))

    if n < min_sample:
        raise ValueError(f"Checkpoint sample too small: n={n} < min_sample={min_sample}")
    if expectancy < min_expectancy:
        raise ValueError(f"Checkpoint expectancy too low: {expectancy} < min_expectancy={min_expectancy}")

    model = _default_model(symbol, timeframe)

    # Entry / OsMA params
    model["entry"]["osma_params"] = _map_osma_params(live_cfg)

    # Floors — map live global thresholds to per-session buckets
    floors, notes = _global_to_session_floors(live_cfg)
    model["floors"] = floors
    model["floors_detail"] = {
        k: {"value": v, "summary": "from live checkpoint (global->session approximation)", "source": "live_checkpoint"}
        for k, v in floors.items()
    }

    # Exit params
    model["exit"] = _map_exit_params(live_cfg)

    # Money management
    model["money_management"] = {
        "gbp_per_001": float(live_cfg.get("bal_per_lot", 50.0)),
        "lot_cap_per_account": 100,
        "base_balance": 5000.0,
    }

    # Provenance
    model["source"] = "live_checkpoint"
    model["checkpoint_meta"] = {
        "expectancy": expectancy,
        "sample_size": n,
        "checkpointed_at": best.get("ts", best.get("timestamp", "")),
        "approximations": notes + [
            "add spacing approximated as be_trigger_pts (no separate live key for pyramid add distance)"
        ],
        "warning": (
            "This model.json was derived from a live checkpoint, not from historical walk-forward. "
            "Per-session floors are approximated by applying live global thresholds uniformly. "
            "Validate thoroughly before live use."
        ),
    }

    return model


def write_model_from_checkpoint(
    symbol: str,
    output_dir: str | None = None,
    checkpoint_path: str = "data/config_checkpoints.json",
    min_sample: int = 30,
    min_expectancy: float = 0.0,
    timeframe: str | None = None,
) -> tuple[str, dict]:
    """Convenience wrapper: build model.json from checkpoint and write to disk.

    Returns (path_to_model_json, model_dict).
    """
    model = build_model_from_checkpoint(
        symbol,
        checkpoint_path=checkpoint_path,
        min_sample=min_sample,
        min_expectancy=min_expectancy,
        timeframe=timeframe or "H1",
    )

    if output_dir is None:
        output_dir = os.path.join("data", "qmmp", symbol.upper())

    os.makedirs(output_dir, exist_ok=True)

    # Preserve/increment build counter from existing model.json
    existing, _ = _load_existing_model(symbol, output_dir)
    prev_build = int(existing.get("build", 0) or 0)
    model["build"] = prev_build + 1

    out_path = os.path.join(output_dir, "model.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)

    return out_path, model
