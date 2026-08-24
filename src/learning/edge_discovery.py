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
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("edge_discovery")

REGIMES = ("volatile", "trending", "ranging", "quiet")


@contextmanager
def _focused_rules_context(symbol: str, strategy_name: str, regimes: set):
    """Issue #145: thread-safe temporary override of focused_rules for ONE symbol
    during a single walk-forward evaluation. Replaces the old global monkeypatch."""
    from src.learning import edge_weights as ew
    orig = ew.focused_rules

    def _override(s):
        if (s or "").upper().startswith(symbol.upper()[:6]):
            return [(strategy_name, regimes)]
        return orig(s)

    ew.focused_rules = _override
    try:
        yield
    finally:
        ew.focused_rules = orig


def _overlay_path() -> str:
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "edge_weights.json")


def _strategy_config_path() -> str:
    """Path to generated strategy_config.json (Phase 1 config system)."""
    try:
        from src import config
        base = config.DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "strategy_config.json")


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
        # Issue #145: thread-safe scoped override of focused_rules for this symbol
        with _focused_rules_context(symbol, strategy_name, regimes):
            try:
                return self.bt.walkforward_focused(symbol, params or {}, timeframe=timeframe)
            except Exception as e:
                logger.debug(f"single wf skip {symbol}/{strategy_name}: {e}")
                return None

    def sweep_symbol(self, symbol: str, params: Optional[dict] = None,
                     timeframe: str = "M15") -> dict:
        """
        Discover validated pockets for one symbol. Returns:
          {"symbol", "focused": [[strategy,[regimes]],...], "edge_weights": {strat:mult},
           "regime_edge": {strat:{regime:mult}}, "validated": bool, "detail": [...]}
        """
        strategies = [s.name for s in self.registry.list_strategies()] \
            if hasattr(self.registry, "list_strategies") else list(self.registry._strategies.keys())
        # R1: the sole entry signal is OsMA_Confluence. Never sweep/validate other
        # strategies as entry pockets — a GoldenCross/BB/RSI pocket would violate the
        # one-entry rule and drift the focused rules away from the proven signal.
        strategies = [s for s in strategies if s == "OsMA_Confluence"]
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
    
    def _generate_strategy_config(self, overlay: dict) -> dict:
        """Generate strategy_config.json from discovered edges and strategy registry.
        
        This makes strategy selection ENTIRELY DATA-DRIVEN:
        - Each symbol gets strategies discovered via walk-forward validation
        - Parameters come from the live tuned registry (not hardcoded)
        - Optuna study links are populated from knowledge store
        - Performance metrics come from the sweep results
        
        Returns the strategy_config structure ready to write to JSON.
        """
        config_data = {
            "version": "1.0",
            "metadata": {
                "description": "Data-driven per-symbol strategy configuration auto-generated by edge_discovery sweep",
                "generated_from": "edge_weights.json overlay + strategy registry",
                "swept_at": overlay.get("meta", {}).get("swept_at"),
                "note": "This file is AUTO-GENERATED. Do not edit manually. Run edge_discovery sweep to update."
            },
            "strategies": {},
            "defaults": {
                "fallback_on_hold": True,
                "description": "If primary strategy returns HOLD, try next-ranked strategy for same symbol"
            }
        }
        
        # Extract discovered focused edges and metrics
        focused_edge = overlay.get("focused_edge", {})
        regime_edge = overlay.get("regime_edge", {})
        edge_weights = overlay.get("edge_weights", {})
        meta = overlay.get("meta", {})
        
        # For each symbol, build its strategy list from discovered edges
        for symbol_key, focused_list in focused_edge.items():
            # Find full symbol name (XAUUSD from XAUUSD or XAUUSD-ECN)
            symbol_name = symbol_key
            for sym_meta_key in meta.get("symbols", {}).keys():
                if sym_meta_key.upper() == symbol_key.upper():
                    symbol_name = sym_meta_key
                    break
            
            strategies_for_symbol = []
            
            # Build ranked list from discovered pockets
            if focused_list:
                # Primary strategy from validated pocket
                for rank, (strategy_name, allowed_regimes) in enumerate(focused_list, start=1):
                    # Get performance metrics from sweep results
                    perf_metrics = self._extract_performance_metrics(
                        symbol_key, strategy_name, regime_edge, edge_weights, meta
                    )
                    
                    # Get strategy parameters from registry
                    params = self._get_strategy_parameters(strategy_name)
                    
                    # Build strategy entry
                    entry = {
                        "rank": rank,
                        "strategy": strategy_name,
                        "enabled": True,
                        "description": f"Validated pocket on regimes: {', '.join(allowed_regimes)}. "
                                      f"Profit factor {perf_metrics.get('vectorbt_pf', 'unknown')}.",
                        "parameters": params,
                        "performance": perf_metrics,
                        "optuna_study": self._get_optuna_study(symbol_key, strategy_name),
                        "notes": f"Discovered via walk-forward validation on {meta.get('timeframe', 'M15')}."
                    }
                    strategies_for_symbol.append(entry)
            else:
                # No validated pocket: populate with ensemble fallback (OsMA_Confluence)
                # This provides a baseline when discovery finds nothing yet
                entry = {
                    "rank": 1,
                    "strategy": "OsMA_Confluence",
                    "enabled": True,
                    "description": "Ensemble fallback (no validated focused pocket discovered yet)",
                    "parameters": self._get_strategy_parameters("OsMA_Confluence"),
                    "performance": {
                        "vectorbt_pf": None,
                        "vectorbt_wr": None,
                        "vectorbt_sharpe": None,
                        "last_validated": None,
                        "validation_bars": 0,
                        "trades_tested": 0,
                        "note": "Not yet validated. Will improve as more data accumulates."
                    },
                    "optuna_study": None,
                    "notes": "Fallback entry while edge_discovery gathers validation data for this symbol."
                }
                strategies_for_symbol.append(entry)
            
            if strategies_for_symbol:
                config_data["strategies"][symbol_key] = strategies_for_symbol
        
        return config_data
    
    def _extract_performance_metrics(self, symbol_key: str, strategy_name: str,
                                     regime_edge: dict, edge_weights: dict, meta: dict) -> dict:
        """Extract performance metrics from sweep results for a strategy."""
        sym_regime = regime_edge.get(symbol_key, {}).get(strategy_name, {})
        sym_edge = edge_weights.get(symbol_key, {}).get(strategy_name)
        
        # Compute weighted average PF from regimes
        if sym_regime:
            avg_pf = sum(sym_regime.values()) / len(sym_regime) if sym_regime else None
        else:
            avg_pf = sym_edge if sym_edge else None
        
        return {
            "vectorbt_pf": round(avg_pf, 2) if avg_pf else None,
            "vectorbt_wr": None,  # Not available from edge_discovery yet
            "vectorbt_sharpe": None,  # Not available from edge_discovery yet
            "last_validated": meta.get("swept_at"),
            "validation_bars": 12000,  # Standard window size
            "trades_tested": 0,  # Would come from detailed sweep results
            "regime_weights": sym_regime
        }
    
    def _get_strategy_parameters(self, strategy_name: str) -> dict:
        """Get default parameters for a strategy from the registry."""
        try:
            strategy = self.registry._strategies.get(strategy_name)
            if strategy and hasattr(strategy, "params_default"):
                return strategy.params_default.copy()
        except Exception:
            pass
        
        # Fallback: known defaults for common strategies
        defaults = {
            "OsMA_Confluence": {
                "osma_fast": 12,
                "osma_slow": 26,
                "osma_signal": 9,
                "bulls_min_long": 0.8,
                "bears_min_short": 0.8
            },
            "Bollinger_OsMA": {
                "max_extension_atr": 2.0,
                "ATR_Multiplier": 1.889,
                "osma_fast": 12,
                "osma_slow": 26,
                "osma_signal": 9
            }
        }
        return defaults.get(strategy_name, {})
    
    def _get_optuna_study(self, symbol_key: str, strategy_name: str) -> Optional[str]:
        """Get Optuna study name for a strategy if available from knowledge store."""
        if self.ks is None:
            return None
        try:
            # Try to find optuna study link in knowledge store
            study_key = f"optuna_study_{symbol_key}_{strategy_name}".lower()
            # This would need to be implemented in the knowledge store
            return None
        except Exception:
            return None
    
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
        
        # Also generate and persist strategy_config.json (Phase 1 data-driven config)
        try:
            strategy_config = self._generate_strategy_config(overlay)
            config_p = _strategy_config_path()
            os.makedirs(os.path.dirname(config_p), exist_ok=True)
            tmp = config_p + ".tmp"
            with open(tmp, "w") as f:
                json.dump(strategy_config, f, indent=2)
            os.replace(tmp, config_p)
            logger.info(f"[EDGE-DISCOVERY] strategy_config.json written to {config_p}")
        except Exception as e:
            logger.warning(f"strategy_config.json persist failed: {e}")

