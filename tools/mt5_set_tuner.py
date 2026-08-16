"""
Tune GoldShark_M5_Engine settings via JSON, emit an MT5 .set file.

MT5 .set files are plain 'key=value' text (one per line). For inputs, MT5 also
accepts the tester triplet lines (key=value||start||step||stop||enabled) but a
simple key=value is valid for live-attach and tester load.

Usage:
    python tools/mt5_set_tuner.py            # writes default .set into the terminal
    python tools/mt5_set_tuner.py my.json    # reads overrides from my.json

The JSON is a flat object of {InputName: value}. Unknown keys are rejected so a
typo can't silently do nothing. Booleans -> true/false, others -> str().
"""
from __future__ import annotations
import json
import os
import sys

# The EA's input names and their validated M5 defaults (source of truth).
EA_NAME = "GoldShark_M5_Engine"
DEFAULT_SETTINGS = {
    # general
    "InpMagic": 950705,
    "InpLots": 0.01,
    "InpEntryTF": "PERIOD_M1",
    "InpExitTF": "PERIOD_M5",
    # entry gate
    "InpEMAPeriod": 13,
    "InpMinATR": 1.40,
    "InpLongBullsMin": 1.00,
    "InpLongBearsMin": -1.00,
    "InpMinOsMALong": 0.00,
    "InpShortBearsMax": -1.00,
    "InpShortBullsMin": -1.00,
    "InpMaxOsMAShort": 0.00,
    # exits
    "InpMfeActivationPts": 20.0,
    "InpMfeRunnerThreshold": 50.0,
    "InpScalpTrailPts": 15.0,
    "InpRunnerTrailPts": 30.0,
    "InpBreakEvenArmPts": 20.0,
    "InpBreakEvenLockPts": 2.0,
    "InpTimeDecayMins": 90,
    "InpHardStopLossPts": 400.0,
    "InpUseExhaustion": True,
}

# ENUM_TIMEFRAMES map: .set files store enum inputs as their integer value.
TF_ENUM = {
    "PERIOD_M1": 1, "PERIOD_M5": 5, "PERIOD_M15": 15, "PERIOD_M30": 30,
    "PERIOD_H1": 16385, "PERIOD_H4": 16388, "PERIOD_D1": 16408,
}

TERMINAL_ID = "AF276BA08BA46D66D2E12F7799A55E5B"  # VT Markets live terminal
PRESETS_DIR = os.path.join(
    os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal", TERMINAL_ID, "MQL5", "Presets"
)


def _fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value in TF_ENUM:
        return str(TF_ENUM[value])
    return str(value)


def build_set(overrides: dict | None = None) -> str:
    settings = dict(DEFAULT_SETTINGS)
    if overrides:
        unknown = [k for k in overrides if k not in DEFAULT_SETTINGS]
        if unknown:
            raise ValueError(f"Unknown input(s): {unknown}. Valid: {sorted(DEFAULT_SETTINGS)}")
        settings.update(overrides)
    lines = [f"; {EA_NAME} settings (generated)"]
    for k, v in settings.items():
        lines.append(f"{k}={_fmt(v)}")
    return "\n".join(lines) + "\n"


def write_set(overrides: dict | None = None, out_path: str | None = None) -> str:
    content = build_set(overrides)
    if out_path is None:
        os.makedirs(PRESETS_DIR, exist_ok=True)
        out_path = os.path.join(PRESETS_DIR, f"{EA_NAME}.set")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


if __name__ == "__main__":
    overrides = None
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            overrides = json.load(f)
    path = write_set(overrides)
    print(f"Wrote .set -> {path}")
    print(build_set(overrides))
