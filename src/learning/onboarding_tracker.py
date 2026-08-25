"""Onboarding progress tracker for vectorbt pipeline."""
from __future__ import annotations
import os
import json
import time
import threading
from datetime import datetime, timezone

from src.utils.logger import get_logger

logger = get_logger("onboarding")

# Module-level path that can be patched by tests
BASE_PATH = None


class OnboardingTracker:
    """Track onboarding progress per symbol."""
    
    def __init__(self, path: str = None):
        global BASE_PATH
        try:
            from src import config
            base = config.DATA_DIR
        except Exception:
            base = os.path.join(os.getcwd(), "data")
        
        # Allow test patching via BASE_PATH
        if BASE_PATH:
            base = BASE_PATH
        
        self.path = path or os.path.join(base, "onboarding_status.json")
        self._lock = threading.Lock()

    def _load(self) -> dict:
        """Load onboarding status from file."""
        try:
            if os.path.exists(self.path):
                with open(self.path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def update(self, symbol: str, stage: str, **fields):
        """Record a stage transition for a symbol."""
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
        """Get onboarding status."""
        store = self._load()
        if symbol:
            return store.get(symbol.upper())
        return store

    def is_done(self, symbol: str) -> bool:
        """Check if onboarding is complete."""
        rec = self.status(symbol)
        return bool(rec and rec.get("stage") == "baseline_set")

    def in_progress(self, symbol: str) -> bool:
        """Check if onboarding is in progress."""
        rec = self.status(symbol)
        return bool(rec and rec.get("stage") not in (None, "baseline_set", "failed", "pending"))
