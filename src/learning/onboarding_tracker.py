"""
Onboarding progress tracker — visible, persistent status for the PATIENT per-symbol
onboarding workflow (DataManager primary, MT5 fallback).

Onboarding is not about speed; it is about acquiring the BEST data and running a full
backtest + forward-test + OsMA-cycle SL + parameter-strength search. That can take many
minutes to >30 min per symbol, so it runs in the BACKGROUND (never blocks trading) and its
progress is tracked here so we can always see where each symbol is.

Status is written to data/onboarding_status.json and logged. Stages:
  pending -> loading_data -> backtesting -> forward_testing -> sampling_cycles
  -> baseline_set  (or) fallback_mt5 -> ... -> baseline_set  (or) failed
"""
from __future__ import annotations
import os
import json
import time
import threading
from datetime import datetime, timezone

from src.utils.logger import get_logger

logger = get_logger("onboarding")


class OnboardingTracker:
    def __init__(self, path: str = None):
        try:
            from src import config
            base = config.DATA_DIR
        except Exception:
            base = os.path.join(os.getcwd(), "data")
        self.path = path or os.path.join(base, "onboarding_status.json")
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            if os.path.exists(self.path):
                with open(self.path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def update(self, symbol: str, stage: str, **fields):
        """Record a stage transition for a symbol (thread-safe, persisted, logged)."""
        sym = symbol.upper()
        with self._lock:
            store = self._load()
            rec = store.get(sym, {"symbol": sym, "history": []})
            rec["stage"] = stage
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec["updated_ts"] = time.time()
            for k, v in fields.items():
                rec[k] = v
            rec["history"] = (rec.get("history", []) + [{"stage": stage, "t": time.time(), **fields}])[-40:]
            store[sym] = rec
            try:
                tmp = self.path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(store, f, indent=1)
                os.replace(tmp, self.path)
            except Exception as e:
                logger.debug(f"onboarding status write skip: {e}")
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        logger.warning(f"[ONBOARD:{sym}] {stage} {extra}".rstrip())

    def status(self, symbol: str = None):
        store = self._load()
        if symbol:
            return store.get(symbol.upper())
        return store

    def is_done(self, symbol: str) -> bool:
        rec = self.status(symbol)
        return bool(rec and rec.get("stage") == "baseline_set")

    def in_progress(self, symbol: str) -> bool:
        rec = self.status(symbol)
        return bool(rec and rec.get("stage") not in (None, "baseline_set", "failed", "pending"))
