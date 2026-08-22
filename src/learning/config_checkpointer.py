"""
ConfigCheckpointer — ReAct-style revert-to-best + learn-from-failure (#27/#25).

The learning loop was shown to be net-harmful: it kept tuning in a degrading
direction and never reverted (e.g. XAUUSD +0.117 -> -0.669 expectancy). A blunt
kill-switch (freeze all learning) is one answer, but the smarter answer the trader
asked for is:

  1. CHECKPOINT the MOST PROFITABLE configuration per symbol (keyed on REALISED
     live expectancy, not backtest PF).
  2. OBSERVE: after the loop changes a symbol's config, score the recent realised
     trades under the new config against the best-known checkpoint.
  3. REVERT: if the new config is meaningfully WORSE, restore the best-known
     config automatically (reason -> act).
  4. LEARN FROM FAILURE: record the reverted config as a "tried and failed"
     direction (in the local knowledge store) so the loop does NOT repeat it and
     biases future search away from it.

This module is deliberately dependency-light and editor-agnostic (portable for the
standalone/VPS build). It persists checkpoints + failed directions to disk under
data/ and, if a KnowledgeStore is provided, also records failures semantically.

A "config" here is the tunable state that affects a symbol's live behaviour:
indicator/exit params (from ParameterOptimizer) plus the management giveback and
any per-symbol overrides. The caller supplies the current config dict and the
recent realised expectancy; this module decides keep vs revert.
"""

from __future__ import annotations

import os
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("config_checkpointer")

CHECKPOINT_PATH = os.path.join(config.DATA_DIR, "config_checkpoints.json")


def _config_fingerprint(cfg: dict) -> str:
    """Stable id for a config so we can recognise a repeated (failed) direction."""
    try:
        blob = json.dumps(cfg, sort_keys=True, default=str)
    except Exception:
        blob = str(sorted(cfg.items()))
    # Issue #129: SHA256[:16] instead of MD5[:12] to reduce collision risk.
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class Checkpoint:
    symbol: str
    config: dict
    expectancy: float          # realised expectancy/trade that justified this
    n: int                     # sample size behind the expectancy
    fingerprint: str
    updated_at: float = field(default_factory=time.time)


class ConfigCheckpointer:
    """Per-symbol best-known-config store with revert + failed-direction memory."""

    def __init__(self, knowledge_store=None, path: Optional[str] = None,
                 min_sample: Optional[int] = None, revert_margin: float = 0.05,
                 failure_ttl_days: int = 90):
        """
        knowledge_store: optional KnowledgeStore for semantic failure memory.
        min_sample: min closed trades in the eval window before revert can fire.
        revert_margin: how much worse (expectancy units) than the checkpoint the
          current config must be before we revert (a noise band).
        """
        self.path = path or CHECKPOINT_PATH
        self.ks = knowledge_store
        self.min_sample = (min_sample if min_sample is not None
                           else getattr(config, "LEARNING_REVERT_MIN_SAMPLE", 15))
        self.revert_margin = revert_margin
        self.failure_ttl_days = failure_ttl_days
        self._state = self._load()  # {symbol: {"best": {...}, "failed": {fp: {...}}}}

    # ── persistence ──
    def _load(self) -> dict:
        try:
            if os.path.exists(self.path):
                with open(self.path) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"checkpoint load failed: {e}")
        return {}

    def _persist(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"checkpoint persist failed: {e}")

    def _sym(self, symbol: str) -> dict:
        return self._state.setdefault(symbol.upper(), {"best": None, "failed": {}})

    # ── best-known config ──
    def best_config(self, symbol: str) -> Optional[dict]:
        b = self._sym(symbol).get("best")
        return dict(b["config"]) if b else None

    def best_expectancy(self, symbol: str) -> Optional[float]:
        b = self._sym(symbol).get("best")
        return b["expectancy"] if b else None

    def maybe_checkpoint(self, symbol: str, cfg: dict, expectancy: float, n: int) -> bool:
        """
        Record `cfg` as the new best-known config for `symbol` IF its realised
        expectancy beats the stored best (and the sample is meaningful).
        Returns True if a new checkpoint was saved.
        """
        if n < self.min_sample:
            return False
        s = self._sym(symbol)
        cur_best = s.get("best")
        if cur_best is None or expectancy > cur_best["expectancy"]:
            cp = Checkpoint(symbol=symbol.upper(), config=dict(cfg),
                            expectancy=round(expectancy, 4), n=int(n),
                            fingerprint=_config_fingerprint(cfg))
            s["best"] = asdict(cp)
            self._persist()
            logger.info(f"[CHECKPOINT] {symbol}: new best-known config "
                        f"(exp={expectancy:.4f} over n={n}) fp={cp.fingerprint}")
            return True
        return False

    def is_failed(self, symbol: str, cfg: dict) -> bool:
        """True if this exact config was already tried and recorded as failed."""
        return _config_fingerprint(cfg) in self._sym(symbol).get("failed", {})

    def evaluate(self, symbol: str, current_cfg: dict, current_expectancy: float,
                 n: int) -> dict:
        """
        The ReAct observe->reflect->act step. Compare the CURRENT config's realised
        expectancy against the best-known checkpoint. Decide:

          * "checkpointed" — current is a new best (saved).
          * "revert"       — current is materially worse; caller should restore
                             best_config(symbol). We record current as a failed
                             direction and learn from it.
          * "hold"         — within the noise band or not enough sample; keep going.

        Returns {"action", "reason", "best_config"(if revert), ...}.
        """
        s = self._sym(symbol)
        best = s.get("best")

        # not enough data yet to judge
        if n < self.min_sample:
            return {"action": "hold", "reason": f"sample {n}<{self.min_sample}"}

        # no checkpoint yet -> current becomes the baseline best
        if best is None:
            self.maybe_checkpoint(symbol, current_cfg, current_expectancy, n)
            return {"action": "checkpointed", "reason": "first baseline"}

        # STALENESS GUARD (fix: the best-known was trapping the bot on a lucky-window
        # config). If the best-known config is now itself LOSING (negative recent
        # expectancy), the stored 'best' was a favourable-period artifact — DEMOTE
        # it so a new config can take over instead of reverting to a config that no
        # longer works. Issue #130: demote preemptively regardless of whether we are
        # currently on it.
        if current_expectancy <= 0 and best["expectancy"] > 0:
            logger.warning(
                f"[STALE-BEST] {symbol}: best-known (exp {best['expectancy']:.4f}) is now "
                f"LOSING live (exp {current_expectancy:.4f}) — demoting the stale checkpoint "
                f"so a better config can take over (was a favourable-window artifact).")
            s["best"] = None
            self._persist()
            return {"action": "demoted_stale_best",
                    "reason": "best-known no longer profitable live; cleared"}

        # current improved on best -> new checkpoint
        if current_expectancy > best["expectancy"]:
            self.maybe_checkpoint(symbol, current_cfg, current_expectancy, n)
            return {"action": "checkpointed", "reason": "new best expectancy"}

        # current materially worse than best -> revert + learn — BUT never revert to
        # a best-known that is itself losing (negative): that just re-traps us.
        if current_expectancy < best["expectancy"] - self.revert_margin:
            if _config_fingerprint(current_cfg) == best["fingerprint"]:
                return {"action": "hold", "reason": "already on best config"}
            if best["expectancy"] <= 0:
                # the 'best' is itself unprofitable — don't force a revert to it;
                # let the current exploration continue / a new best emerge.
                return {"action": "hold", "reason": "best-known is itself losing; not reverting"}
            self._record_failure(symbol, current_cfg, current_expectancy, best["expectancy"])
            logger.warning(
                f"[REVERT] {symbol}: current config exp={current_expectancy:.4f} is worse than "
                f"best-known {best['expectancy']:.4f} (margin>{self.revert_margin}). Reverting to "
                f"best-known config fp={best['fingerprint']} and recording the failed direction."
            )
            return {"action": "revert", "reason": "degraded vs best-known",
                    "best_config": dict(best["config"]),
                    "from_expectancy": current_expectancy,
                    "to_expectancy": best["expectancy"]}

        return {"action": "hold", "reason": "within noise band of best"}

    def _record_failure(self, symbol: str, cfg: dict, exp: float, best_exp: float):
        """Remember a config that degraded live results so it isn't retried."""
        fp = _config_fingerprint(cfg)
        s = self._sym(symbol)
        s.setdefault("failed", {})[fp] = {
            "config": dict(cfg),
            "expectancy": round(exp, 4),
            "worse_than_best_by": round(best_exp - exp, 4),
            "recorded_at": time.time(),
        }
        self._persist()
        # semantic memory so the reflection loop learns from it too
        if self.ks is not None:
            try:
                self.ks.remember(
                    key=f"failed_config_{symbol.upper()}_{fp}",
                    kind="correction",
                    topic=f"tuning failure {symbol.upper()}",
                    source="config_checkpointer",
                    text=(f"On {symbol.upper()} the config {json.dumps(cfg, default=str)} produced "
                          f"realised expectancy {exp:.4f}, WORSE than the best-known {best_exp:.4f}. "
                          f"This tuning direction was reverted; do NOT re-apply it. Prefer the "
                          f"best-known config and try a different tuning method."),
                )
            except Exception as e:
                logger.debug(f"knowledge failure-record skip: {e}")

    def failed_fingerprints(self, symbol: str) -> list[str]:
        return list(self._sym(symbol).get("failed", {}).keys())

    def clear_old_failures(self, days: int = None) -> int:
        """Issue #133: expire failed-direction memory so a regime change can retry
        an old direction after enough time has passed."""
        cutoff = time.time() - (days if days is not None else self.failure_ttl_days) * 86400
        cleared = 0
        for sym, s in self._state.items():
            failed = s.get("failed", {})
            stale = [fp for fp, rec in failed.items() if rec.get("recorded_at", 0) < cutoff]
            for fp in stale:
                failed.pop(fp, None)
                cleared += 1
        if cleared:
            self._persist()
            logger.info(f"[CHECKPOINT] cleared {cleared} stale failed directions "
                        f"older than {self.failure_ttl_days}d")
        return cleared

    def snapshot(self) -> dict:
        """Compact view for the dashboard/status."""
        out = {}
        for sym, s in self._state.items():
            best = s.get("best")
            out[sym] = {
                "best_expectancy": best["expectancy"] if best else None,
                "best_fingerprint": best["fingerprint"] if best else None,
                "best_n": best["n"] if best else None,
                "failed_directions": len(s.get("failed", {})),
            }
        return out
