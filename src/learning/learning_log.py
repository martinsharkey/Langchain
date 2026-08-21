"""
LearningLog (#45.1) — GitHub-visible record of what the learning loop changed & why.

The raw learning state (tuned_params.json, edge_weights.json, checkpoints) is
gitignored runtime state. This produces a human-readable, git-diffable DIGEST of
what the system actually DID — so you can look at GitHub and see "what got tuned,
when, why, and whether the metric it moved actually improved."

STRICTLY DOWNSTREAM / REPORTING ONLY: it never gates or influences a live trading
decision. If it errors, it logs and skips — never blocks a cycle.

Writes a rolling, most-recent-first `LEARNING_LOG.md` at the repo root (capped;
older entries archived to data/learning_log_archive/). Each entry records:
  - WHAT changed: symbol, param(s) old -> new
  - WHY: the trigger (checkpoint / revert / pattern-lock / exit-calibration /
    optimizer / dynamic-fixer / onnx-retrain / whale / edge-discovery)
  - METRIC: the before/after number it was meant to move (expectancy/PF/AUC/...)
Also records DISCOVERIES (findings with no param change, e.g. "whale edge marginal").

Committing LEARNING_LOG.md to git is done by an external cadence (the researcher /
a scheduled task), not here — this module only maintains the file safely.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("learning_log")


def _repo_root() -> str:
    # this file is src/learning/learning_log.py -> repo root is two up
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resolve_learning_log_path(data_dir: str) -> str:
    """Return the canonical LEARNING_LOG.md path, checking both the repo root
    (where the writer stores it) and data_dir (where the dashboard may look).
    Prefers the repo-root file if it exists; otherwise falls back to data_dir.
    """
    candidates = [
        os.path.join(_repo_root(), "LEARNING_LOG.md"),
        os.path.join(data_dir, "LEARNING_LOG.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


class LearningLog:
    def __init__(self, path: str = None, max_entries: int = 400):
        self.path = path or os.path.join(_repo_root(), "LEARNING_LOG.md")
        self.max_entries = max_entries

    def _entry(self, kind: str, symbol: str, what: str, why: str, metric: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        sym = f"`{symbol}`" if symbol else "-"
        parts = [f"- **{ts}** [{kind}] {sym}", what]
        if why:
            parts.append(f"-- why: {why}")
        if metric:
            parts.append(f"-- metric: {metric}")
        return " ".join(p for p in parts if p)

    def record(self, kind: str, symbol: str = "", what: str = "", why: str = "",
               metric: str = ""):
        """Prepend one entry (most-recent-first). Non-fatal."""
        try:
            line = self._entry(kind, symbol, what, why, metric)
            existing = ""
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as f:
                    existing = f.read()
            header, body = self._split(existing)
            lines = [l for l in body.splitlines() if l.strip().startswith("- ")]
            lines.insert(0, line)
            if len(lines) > self.max_entries:
                self._archive(lines[self.max_entries:])
                lines = lines[: self.max_entries]
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(header + "\n".join(lines) + "\n")
        except Exception as e:
            logger.debug(f"learning log record skip: {e}")

    # convenience wrappers for the common triggers
    def config_change(self, symbol, param_changes: dict, why: str, metric: str = ""):
        what = "config: " + ", ".join(f"{k} {v[0]}→{v[1]}" for k, v in param_changes.items())
        self.record("CONFIG", symbol, what, why, metric)

    def revert(self, symbol, why: str, metric: str = ""):
        self.record("REVERT", symbol, "reverted to best-known config", why, metric)

    def exit_lock(self, symbol, sl_atr, tp_rr, source, metric=""):
        self.record("EXIT-LOCK", symbol, f"exit set sl_atr {sl_atr} tp_rr {tp_rr}",
                    f"{source}", metric)

    def discovery(self, symbol, what: str, metric: str = ""):
        self.record("DISCOVERY", symbol, what, "", metric)

    def onnx(self, symbol, auc, kept: bool, n: int):
        self.record("ONNX", symbol, f"model retrained (kept={kept})",
                    "per-symbol chronological holdout", f"AUC {auc} over n={n}")

    def optimizer(self, symbol, tried: int, best_score: float, status: str, metric: str = ""):
        self.record("OPTIMIZER", symbol,
                    f"tried {tried} candidates, best score {best_score:.2f}",
                    status, metric)

    def validate(self, symbol, source: str, passed: bool, score: float,
                 forward_pf: float, reason: str, n_total: int = 0):
        what = ("PASS" if passed else "REJECT") + f" score {score:.2f} fwdPF {forward_pf:.2f}"
        self.record("VALIDATE", symbol, what, reason,
                    f"trades={n_total}" if n_total else "")

    def _split(self, text: str):
        title = ("# Learning & Adjustments Log\n\n"
                 "> Auto-generated digest of what the self-learning loop changed and why.\n"
                 "> Most-recent-first. Reporting only -- never gates a live decision (#45.1).\n\n")
        if text and text.lstrip().startswith("# Learning"):
            idx = text.find("\n- ")
            if idx != -1:
                return text[:idx + 1], text[idx + 1:]
            return text if text.endswith("\n\n") else text + "\n", ""
        return title, ""

    def _archive(self, old_lines):
        try:
            adir = os.path.join(_repo_root(), "data", "learning_log_archive")
            os.makedirs(adir, exist_ok=True)
            ap = os.path.join(adir, f"learning_log_{datetime.now(timezone.utc).strftime('%Y%m')}.md")
            with open(ap, "a", encoding="utf-8") as f:
                f.write("\n".join(old_lines) + "\n")
        except Exception:
            pass
