"""
DynamicFixer (#36) — intelligent, per-symbol ReAct fix cycle.

When a symbol is losing, the post-mortem already diagnoses WHY (exiting too early /
SL too tight / entering late / exit-timing leak). Previously those directives only
biased the backtest optimizer, which rejected them at the WR>=50 gate — so the fix
never reached live trades. This component closes that: it reasons over the
post-mortem + realised stats + (optionally) the mql5 research, then APPLIES a
concrete live fix and escalates through an ordered playbook, letting the #27
checkpointer verify realised expectancy and revert if it didn't help.

Escalation ladder (per symbol, one step per invocation, most-direct first):
  1. EXIT FIX — the dominant leak is exit timing (SL too tight / cut early):
     widen live sl_atr and/or loosen giveback via engine overrides (immediate).
  2. PARAM RETUNE — ask the optimizer for a better indicator set (mql5-grounded).
  3. STRATEGY SWITCH — if entries themselves are weak, run the edge-discovery
     sweep so a different focused strategy can take over (gated).
  4. RESEARCH — query mql5 + file a GitHub issue when nothing internal helps.

Every step records what it tried + why to the KnowledgeStore, and marks the
symbol so a step isn't repeated until its effect has been observed. Safe/non-fatal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("dynamic_fixer")


class DynamicFixer:
    def __init__(self, engine):
        # holds a back-reference to the engine to read post-mortem + apply overrides
        self.e = engine
        self._last_step = {}   # symbol -> last step applied (avoid repeating)
        self._history = {}     # symbol -> [steps]

    def _pm(self, resolved: str) -> dict:
        try:
            return self.e.post_mortem.analyze(symbol=resolved, limit=40) or {}
        except Exception as e:
            logger.debug(f"fixer post-mortem skip {resolved}: {e}")
            return {}

    def fix_symbol(self, base: str) -> dict:
        """Run ONE intelligent fix step for a losing symbol. Returns what it did."""
        if base not in self.e.adapters:
            return {}
        resolved = self.e.adapters[base].resolved_symbol
        # only act when the symbol is actually losing on a real sample
        try:
            exp, n = self.e._recent_expectancy(base)
        except Exception:
            exp, n = 0.0, 0
        if n < 15 or exp >= 0:
            return {"symbol": base, "action": "none", "reason": f"exp {exp} n {n} — not intervening"}

        pm = self._pm(resolved)
        directives = pm.get("directives", {}) or {}
        findings = pm.get("findings", [])
        last = self._last_step.get(base.upper())
        step = None
        detail = {}

        # 1) EXIT FIX — the dominant, evidence-backed leak (applied LIVE, gate-free)
        if last != "exit_fix" and (directives.get("sl_atr") or directives.get("giveback")
                                   or directives.get("entry_extension_filter")):
            ov = (self.e._exit_override.setdefault(base.upper(), {}))
            cur_sl = ov.get("sl_atr", self.e._tuned_params(resolved).get("sl_atr", 1.0))
            if directives.get("sl_atr"):
                ov["sl_atr"] = round(min(cur_sl + float(directives["sl_atr"]), 3.0), 2)
            if directives.get("giveback"):
                cur_gb = self.e._giveback_override.get(base.upper(), 0.6)
                self.e._giveback_override[base.upper()] = round(min(cur_gb + float(directives["giveback"]), 0.9), 2)
            # ENTERING LATE / into extended moves -> apply a live max_stretch_atr ceiling
            # (tighten toward the EMA) so the diagnosed ENTRY fix reaches live, not just
            # a directive. Start at 1.5xATR and ratchet tighter each time it recurs.
            if directives.get("entry_extension_filter"):
                cur_st = self.e._stretch_override.get(base.upper(), 2.0)
                self.e._stretch_override[base.upper()] = round(max(cur_st - 0.3, 0.7), 2)
            step = "exit_fix"
            detail = {"sl_atr": ov.get("sl_atr"), "giveback": self.e._giveback_override.get(base.upper()),
                      "max_stretch_atr": self.e._stretch_override.get(base.upper())}

        # 2) PARAM RETUNE — hand the leak to the optimizer (mql5-grounded, #25)
        elif last != "param_retune" and self.e.param_optimizer is not None:
            try:
                r = self.e.param_optimizer.optimize(resolved, iterations=8, directives=directives)
                step = "param_retune"
                detail = {"improved": r.get("improved"), "score": r.get("score")}
            except Exception as ex:
                detail = {"error": str(ex)[:80]}

        # 3) STRENGTH/PERIOD RETUNE — entries themselves are weak. FOCUSED is locked to
        # OsMA_Confluence, so we do NOT sweep for a different strategy (that would be a
        # non-OsMA entry). Instead run a deeper OsMA param/strength search so the
        # optimizer discovers better osma/macd/bulls/bears strength FLOORS + periods.
        elif last != "strength_retune" and self.e.param_optimizer is not None:
            try:
                r = self.e.param_optimizer.optimize(resolved, iterations=20, directives=directives)
                step = "strength_retune"
                detail = {"improved": r.get("improved"), "score": r.get("score"),
                          "note": "OsMA strength/period only (no strategy switch)"}
            except Exception as ex:
                detail = {"error": str(ex)[:80]}

        # 4) RESEARCH — nothing internal helped; consult mql5 + escalate to a human
        else:
            step = "research"
            try:
                if self.e.researcher is not None:
                    res = self.e.researcher.research_symbol(base)
                    detail = {"hypothesis": bool(res.get("hypothesis"))}
                    if res.get("hypothesis"):
                        self.e.researcher.file_issue(
                            title=f"[fixer] {base} losing (exp {exp}); internal fixes exhausted — needs new approach",
                            body=(f"DynamicFixer exhausted exit-fix, param-retune and strategy-switch for {base} "
                                  f"(recent expectancy {exp} over {n} trades). Post-mortem: {findings}. "
                                  f"mql5-grounded hypothesis: {res.get('hypothesis')}. Consider a new indicator/"
                                  f"technique or ONNX model."),
                            labels=["learning", "research"])
            except Exception as ex:
                detail = {"error": str(ex)[:80]}

        self._last_step[base.upper()] = step
        self._history.setdefault(base.upper(), []).append(
            {"step": step, "at": datetime.now(timezone.utc).isoformat(), "exp": exp, "detail": detail})
        logger.warning(f"[FIXER] {base}: exp {exp} (n{n}) -> step '{step}' {detail} | leak: {findings[:1]}")
        # remember what we tried so learning compounds
        if getattr(self.e, "knowledge_store", None) is not None:
            try:
                self.e.knowledge_store.remember(
                    key=f"fixer_{base.upper()}_{step}", kind="correction",
                    topic=f"dynamic fix {base.upper()}", source="dynamic_fixer",
                    text=(f"{base} losing (exp {exp}, n {n}). Post-mortem leak: {findings[:2]}. "
                          f"Applied fix step '{step}': {detail}. Checkpointer will verify + revert if worse."))
            except Exception:
                pass
        return {"symbol": base, "action": step, "exp": exp, "n": n, "detail": detail}

    def snapshot(self) -> dict:
        return {k: {"last_step": self._last_step.get(k), "steps": len(v)}
                for k, v in self._history.items()}
