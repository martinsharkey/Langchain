"""
LangGraph TRADE SUPERVISOR — the intelligent per-trade cognitive loop.

Unlike langgraph_researcher.py (which runs the BACKGROUND daily parameter-tuning
loop), this StateGraph runs on an OPEN position and decides, by reasoning across
ALL indicators + higher-timeframe alignment + this symbol's learned experience,
what to do with the trade RIGHT NOW:

    Observe -> Recall -> Reason -> Decide  =>  HOLD | TIGHTEN | EXIT | ADD_LEG | CUT_ALL

Design contract (matches PYRAMID_BASKET_DESIGN.md safety invariants):
  * The graph REASONS and returns a structured decision. It NEVER sends orders.
  * The engine's fast/deterministic layer executes the decision and still owns the
    stop-loss, group reversal-cut and drawdown-halt every tick regardless.
  * Throttled: called only when the trade manager says a review is due.
  * Degrades honestly: if langgraph or the LLM is unavailable, returns a rules
    fallback decision (HOLD) and the caller logs rules-only.

The context (indicators / HTF / experience / basket legs / profit) is gathered by
the engine and passed in as `ctx`, so this module has no engine dependency and is
unit-testable in isolation.
"""

import logging
from typing import Optional, TypedDict, Callable

logger = logging.getLogger("langgraph_supervisor")

VALID = ("HOLD", "TIGHTEN", "EXIT", "ADD_LEG", "CUT_ALL")


class TradeState(TypedDict, total=False):
    ctx: dict            # gathered context (indicators, htf, profit, legs, ...)
    observation: str     # compact human-readable snapshot
    recall: str          # learned experience for this symbol/context
    decision: str        # one of VALID
    reason: str


class LangGraphTradeSupervisor:
    def __init__(self, llm_getter: Callable, extract_text: Callable,
                 recall_fn: Optional[Callable] = None):
        """llm_getter(temperature) -> llm ; extract_text(resp) -> str ;
        recall_fn(query, n) -> list (optional experience recall)."""
        self._get_llm = llm_getter
        self._extract = extract_text
        self._recall = recall_fn
        self._graph = None
        try:
            self._graph = self._build_graph()
            logger.info("LangGraph trade supervisor compiled (observe->recall->reason->decide)")
        except Exception as e:
            logger.warning(f"LangGraph supervisor unavailable; sequential fallback: {e}")
            self._graph = None

    def _build_graph(self):
        from langgraph.graph import StateGraph, END
        g = StateGraph(TradeState)
        g.add_node("observe", self._observe)
        g.add_node("recall", self._recall_node)
        g.add_node("reason", self._reason)
        g.set_entry_point("observe")
        g.add_edge("observe", "recall")
        g.add_edge("recall", "reason")
        g.add_edge("reason", END)
        return g.compile()

    # ── nodes ──
    def _observe(self, state: TradeState) -> TradeState:
        c = state["ctx"]
        state["observation"] = (
            f"Symbol {c.get('symbol')} side {c.get('action')} legs {c.get('n_legs')} | "
            f"profit {c.get('profit_pts'):.0f}pts atr {c.get('atr_pts'):.0f} "
            f"spread {c.get('spread_pts'):.0f} atBE {c.get('at_be')} | "
            f"OsMA {c.get('osma_closed')}/{c.get('osma_prev')} "
            f"MACD {c.get('macd_line')}/{c.get('macd_signal')} "
            f"Bulls {c.get('bulls')} Bears {c.get('bears')} RSI {c.get('rsi')} | "
            f"HTF {c.get('htf_txt')}"
        )
        return state

    def _recall_node(self, state: TradeState) -> TradeState:
        state["recall"] = ""
        if self._recall is not None:
            try:
                sym = state["ctx"].get("base_symbol") or state["ctx"].get("symbol")
                hits = self._recall(
                    f"{sym} hold runner vs exit early when OsMA/MACD aligned; "
                    f"basket add safe?", 1)
                if hits:
                    state["recall"] = f"Learned: {str(hits[0])[:200]}"
            except Exception:
                pass
        return state

    def _reason(self, state: TradeState) -> TradeState:
        c = state["ctx"]
        can_add = bool(c.get("can_add_leg"))
        add_line = ("You MAY answer ADD_LEG if this is a confirmed runner (all legs "
                    "green, newest at breakeven + past the add trigger, HTF aligned). "
                    if can_add else "")
        prompt = (
            "You are an intelligent trade supervisor on an OPEN position. Reason across "
            "ALL indicators + higher-timeframe alignment + the learned note, then reply "
            "with EXACTLY one token: HOLD, TIGHTEN, EXIT"
            + (", ADD_LEG, CUT_ALL.\n" if can_add else ", CUT_ALL.\n")
            + f"OBSERVATION: {state.get('observation')}\n{state.get('recall','')}\n"
            + add_line +
            "Guidance: HOLD if momentum still confirmed (OsMA+MACD aligned, dominant "
            "power our way, HTF aligned) and it's still running. TIGHTEN if strongly in "
            "profit but momentum fading. EXIT if the move looks exhausted/reversing. "
            "CUT_ALL if a basket is reversing against all legs."
        )
        decision, reason = "HOLD", "default"
        try:
            llm = self._get_llm(temperature=0.2)
            text = (self._extract(llm.invoke(prompt)) or "").upper()
            for k in ("CUT_ALL", "ADD_LEG", "EXIT", "TIGHTEN", "HOLD"):
                if k in text:
                    decision = k; reason = "llm"; break
            if decision == "ADD_LEG" and not can_add:
                decision = "HOLD"   # never allow an add the engine hasn't cleared
        except Exception as e:
            reason = f"llm-unavailable ({e})"
        state["decision"] = decision
        state["reason"] = reason
        return state

    # ── public entrypoint ──
    def decide(self, ctx: dict) -> dict:
        """Return {'decision': <one of VALID>, 'reason': str}. Never raises."""
        state: TradeState = {"ctx": ctx}
        try:
            if self._graph is not None:
                out = self._graph.invoke(state)
                return {"decision": out.get("decision", "HOLD"), "reason": out.get("reason", "")}
            # sequential fallback (identical logic, no graph)
            self._observe(state); self._recall_node(state); self._reason(state)
            return {"decision": state.get("decision", "HOLD"), "reason": state.get("reason", "")}
        except Exception as e:
            logger.debug(f"supervisor decide fallback: {e}")
            return {"decision": "HOLD", "reason": f"error:{e}"}
