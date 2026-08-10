"""
Automated per-symbol edge discovery (#31).

Replaces the hand-written static tables in edge_weights.py with a runtime sweep:
for each configured symbol, backtest each registered strategy (solo) across
regimes using the SAME walk-forward gate the ParameterOptimizer uses, keep only
pockets that GENERALIZE (PF >= 1 in every window), and persist the result to
data/edge_weights.json (the overlay edge_weights.py merges over its static seed).

Safety (matches existing design, non-negotiable):
  - nothing is written for a symbol unless a pocket clears the walk-forward gate;
  - a symbol with no validated pocket gets an EMPTY focused entry (engine falls
    back to the weighted ensemble) and is visibly marked "no validated edge yet";
  - never a looser bar for "new" symbols than the optimizer/post-mortem use;
  - SymbolGovernor remains the live safety net regardless of sweep output.

This module does NOT change how already-validated symbols trade; it only produces
the overlay so NEW symbols get the same treatment gold got, automatically.
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("edge_discovery")

REGIMES = ("volatile", "trending", "ranging", "quiet")


def _overlay_path() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "edge_weights.json")


class EdgeDiscovery:
    """Sweep each strategy x regime per symbol through the walk-forward gate."""

    def __init__(self, registry, backtester, min_pf: float = 1.15,
                 knowledge_store=None):
        """
        registry: StrategyRegistry (source of strategies + regime detection).
        backtester: Backtester (walk-forward engine).
        min_pf: minimum robust (min-window) PF for a pocket to be KEPT. This is
          the SAME order as the optimizer's generalizes gate (PF>=1 per window);
          min_pf adds a margin so we keep only real edges, not PF~1.0 noise.
        """
        self.registry = registry
        self.bt = backtester
        self.min_pf = min_pf
        self.ks = knowledge_store

    def _walkforward_single(self, symbol: str, strategy_name: str, regimes: set,
                            params: dict, timeframe: str) -> Optional[dict]:
        """
        Walk-forward a SINGLE strategy restricted to `regimes` by temporarily
        overriding focused_rules for this symbol. Reuses backtester.walkforward_focused
        so the gate + exit model are identical to live tuning. Returns its metrics.
        """
        from src.learning import edge_weights as ew
        # monkeypatch focused_rules for the duration of this one backtest
        orig = ew.focused_rules
        ew.focused_rules = lambda s: [(strategy_name, regimes)] if (s or "").upper().startswith(symbol.upper()[:6]) else orig(s)
        try:
            return self.bt.walkforward_focused(symbol, params or {}, timeframe=timeframe)
        except Exception as e:
            logger.debug(f"single wf skip {symbol}/{strategy_name}: {e}")
            return None
        finally:
            ew.focused_rules = orig

    def sweep_symbol(self, symbol: str, params: Optional[dict] = None,
                     timeframe: str = "M15") -> dict:
        """
        Discover validated pockets for one symbol. Returns:
          {"symbol", "focused": [[strategy,[regimes]],...], "edge_weights": {strat:mult},
           "regime_edge": {strat:{regime:mult}}, "validated": bool, "detail": [...]}
        """
        strategies = [s.name for s in self.registry.list_strategies()] \
            if hasattr(self.registry, "list_strategies") else list(self.registry._strategies.keys())
        focused, edge_w, regime_e, detail = [], {}, {}, []
        for name in strategies:
            best_regimes = set()
            for regime in REGIMES:
                res = self._walkforward_single(symbol, name, {regime}, params, timeframe)
                if not res or not res.get("generalizes"):
                    continue
                score = res.get("score", 0.0)  # min-window PF (robust)
                if score >= self.min_pf:
                    best_regimes.add(regime)
                    regime_e.setdefault(name, {})[regime] = round(min(score, 3.0), 2)
                    detail.append({"strategy": name, "regime": regime,
                                   "min_pf": score, "pfs": res.get("pfs")})
            if best_regimes:
                focused.append([name, sorted(best_regimes)])
                # edge weight ~ scaled by best regime PF (capped)
                best_pf = max(regime_e[name].values())
                edge_w[name] = round(min(1.0 + (best_pf - 1.0) * 2.0, 2.5), 2)
        validated = len(focused) > 0
        result = {"symbol": symbol.upper(), "focused": focused, "edge_weights": edge_w,
                  "regime_edge": regime_e, "validated": validated, "detail": detail,
                  "swept_at": datetime.now(timezone.utc).isoformat()}
        if self.ks is not None:
            try:
                if validated:
                    self.ks.remember(
                        key=f"edge_discovery_{symbol.upper()}", kind="finding",
                        topic=f"edge discovery {symbol.upper()}", source="edge_discovery",
                        text=(f"{symbol.upper()} validated pockets (walk-forward PF>={self.min_pf}): "
                              f"{focused}. Edge weights {edge_w}."))
                else:
                    self.ks.remember(
                        key=f"edge_discovery_{symbol.upper()}", kind="finding",
                        topic=f"edge discovery {symbol.upper()}", source="edge_discovery",
                        text=(f"{symbol.upper()}: NO strategy pocket cleared the walk-forward gate "
                              f"(PF>={self.min_pf}). Trade generic ensemble at reduced size / mark "
                              f"'no validated edge yet' until more data or a new technique."))
            except Exception:
                pass
        return result

    def sweep_all(self, symbols: list[str], params_by_symbol: Optional[dict] = None,
                  timeframe: str = "M15", persist: bool = True) -> dict:
        """Sweep every symbol and (optionally) persist the merged overlay to disk."""
        params_by_symbol = params_by_symbol or {}
        overlay = {"edge_weights": {}, "regime_edge": {}, "focused_edge": {},
                   "meta": {"swept_at": datetime.now(timezone.utc).isoformat(),
                            "min_pf": self.min_pf, "timeframe": timeframe, "symbols": {}}}
        for sym in symbols:
            r = self.sweep_symbol(sym, params_by_symbol.get(sym), timeframe)
            key = sym.upper()[:6]  # prefix key (XAUUSD from XAUUSD-ECN)
            if r["edge_weights"]:
                overlay["edge_weights"][key] = r["edge_weights"]
            if r["regime_edge"]:
                overlay["regime_edge"][key] = r["regime_edge"]
            # always write a focused entry (empty = no validated edge -> ensemble)
            overlay["focused_edge"][key] = r["focused"]
            overlay["meta"]["symbols"][key] = {"validated": r["validated"],
                                               "pockets": len(r["focused"])}
            logger.info(f"[EDGE-DISCOVERY] {sym}: validated={r['validated']} "
                        f"pockets={len(r['focused'])}")
        if persist:
            self._persist(overlay)
        return overlay

    def _persist(self, overlay: dict):
        try:
            p = _overlay_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w") as f:
                json.dump(overlay, f, indent=2)
            os.replace(tmp, p)
            logger.info(f"[EDGE-DISCOVERY] overlay written to {p}")
            # hot-reload so the live engine picks it up without restart
            try:
                from src.learning import edge_weights as ew
                ew.reload_overlay()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"edge overlay persist failed: {e}")
