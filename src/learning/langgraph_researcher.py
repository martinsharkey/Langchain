"""
LangGraph cognitive loop — the formal Observe -> Reason -> Act -> Adopt state
machine that sits ABOVE the fast execution engine.

This does NOT re-implement the learning logic. It is a thin, explicit LangGraph
orchestration layer over the proven `ContinualResearcher` so the cognitive loop
is a first-class, inspectable state graph (per the LangGraph directive) while the
underlying, battle-tested methods keep doing the actual work. If langgraph is
unavailable it degrades to a plain sequential call of the same nodes.

Nodes:
  observe : review per-symbol LIVE_MICRO outcomes (MFE/MAE) + rejected-signal
            telemetry from the experience DB.
  reason  : query knowledge (NotebookLM -> local RAG -> MQL5) to form a
            parameter hypothesis grounded in the observed weakness.
  act     : run the REAL-TICK walk-forward / edge sweep (never 1-min OHLC).
  adopt   : the ConfigCheckpointer keeps the change only if it beats the
            baseline out-of-sample; otherwise it reverts.

The heavy lifting is delegated to ContinualResearcher.daily_cycle(); this layer
adds the explicit graph, per-node telemetry, and a clean seam for future nodes.
"""

import logging
from typing import Optional, TypedDict

logger = logging.getLogger("langgraph_researcher")


class ResearchState(TypedDict, total=False):
    symbols: list
    observations: dict
    hypotheses: dict
    validation: dict
    adopted: dict
    notes: list


class LangGraphResearcher:
    def __init__(self, continual_researcher):
        self.cr = continual_researcher
        self._graph = None
        try:
            self._graph = self._build_graph()
            logger.info("LangGraph cognitive loop compiled (observe->reason->act->adopt)")
        except Exception as e:
            logger.warning(f"LangGraph unavailable; using sequential fallback: {e}")
            self._graph = None

    # ── graph construction ──
    def _build_graph(self):
        from langgraph.graph import StateGraph, END

        g = StateGraph(ResearchState)
        g.add_node("observe", self._observe)
        g.add_node("reason", self._reason)
        g.add_node("act", self._act)
        g.add_node("adopt", self._adopt)
        g.set_entry_point("observe")
        g.add_edge("observe", "reason")
        g.add_edge("reason", "act")
        g.add_edge("act", "adopt")
        g.add_edge("adopt", END)
        return g.compile()

    # ── nodes (delegate to the proven researcher primitives) ──
    def _observe(self, state: ResearchState) -> ResearchState:
        obs = {}
        for sym in state.get("symbols", []):
            try:
                obs[sym] = self.cr.review_symbol(sym)
            except Exception as e:
                logger.debug(f"observe {sym} skip: {e}")
        # fold in rejected-signal telemetry (blocked-run vs whipsaw) when present
        try:
            db = getattr(self.cr, "db", None)
            if db is not None and hasattr(db, "rejected_summary"):
                for sym in state.get("symbols", []):
                    rej = db.rejected_summary(base_symbol=sym, limit=200)
                    if sym in obs:
                        obs[sym]["rejected"] = rej
        except Exception as e:
            logger.debug(f"rejected telemetry skip: {e}")
        state["observations"] = obs
        return state

    def _reason(self, state: ResearchState) -> ResearchState:
        hyp = {}
        for sym in state.get("symbols", []):
            try:
                res = self.cr.research_symbol(sym)
                hyp[sym] = res.get("hypothesis")
            except Exception as e:
                logger.debug(f"reason {sym} skip: {e}")
        state["hypotheses"] = hyp
        return state

    def _act(self, state: ResearchState) -> ResearchState:
        # The real-tick validation + edge sweep lives inside daily_cycle; we invoke
        # it here so the "act" node performs the authoritative backtest step.
        try:
            state["validation"] = self.cr.daily_cycle(state.get("symbols", []))
        except Exception as e:
            logger.warning(f"act (daily_cycle) failed: {e}")
            state["validation"] = {}
        return state

    def _adopt(self, state: ResearchState) -> ResearchState:
        # Adoption/revert is enforced by the ConfigCheckpointer inside daily_cycle;
        # we surface the result for observability.
        state["adopted"] = state.get("validation", {})
        return state

    # ── public entrypoint used by the engine's adaptive thread ──
    def run_cycle(self, symbols: list) -> dict:
        state: ResearchState = {"symbols": symbols}
        if self._graph is not None:
            try:
                out = self._graph.invoke(state)
                return out.get("adopted", {})
            except Exception as e:
                logger.warning(f"LangGraph invoke failed, falling back: {e}")
        # sequential fallback — identical behaviour, no graph
        self._observe(state)
        self._reason(state)
        self._act(state)
        self._adopt(state)
        return state.get("adopted", {})
