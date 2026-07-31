"""
ReflectionAgent (L4) — the ReAct-style "think about failures" loop.

After N closed losers (or on a schedule) it:
  1. OBSERVE: pulls recent closed trades + the IndicatorScorer evidence
     (which indicators separate winners/losers, worst sessions/regimes).
  2. THINK + FORM A QUESTION: builds a focused analytical prompt.
  3. ACT (query LLM): asks for a concrete, testable hypothesis — an indicator
     swap / combination / filter / session or regime avoidance.
  4. RECORD: stores the hypothesis (status='proposed') so the StrategySynthesizer
     can turn it into a candidate strategy and the Backtester can validate it.

It NEVER changes live trading rules directly — it only proposes. This is the
guardrail that keeps reflection honest (no acting on un-validated LLM opinions).

Hypotheses live in their own table so status is trackable:
  proposed -> testing -> promoted | rejected
"""

from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from src import config
from src.utils.logger import get_logger
from src.learning.indicator_scorer import IndicatorScorer

logger = get_logger("reflection_agent")

HYPOTHESES_DB = os.path.join(config.DATA_DIR, "hypotheses.db")


class HypothesisStore:
    def __init__(self, db_path: str = HYPOTHESES_DB):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                symbol TEXT,
                question TEXT,
                hypothesis TEXT,
                proposed_strategies TEXT,   -- JSON list of existing strategy names to combine
                proposed_filter TEXT,        -- e.g. "adx<25" / "avoid session late_ny"
                rationale TEXT,
                status TEXT DEFAULT 'proposed',   -- proposed|testing|promoted|rejected
                backtest_json TEXT,
                updated_at TEXT
            )
        """)
        conn.commit(); conn.close()

    def add(self, symbol, question, hypothesis, strategies, filt, rationale) -> int:
        conn = sqlite3.connect(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("""
            INSERT INTO hypotheses (created_at, symbol, question, hypothesis,
                proposed_strategies, proposed_filter, rationale, status, updated_at)
            VALUES (?,?,?,?,?,?,?, 'proposed', ?)
        """, (now, symbol, question, hypothesis, json.dumps(strategies or []),
              filt or "", rationale or "", now))
        hid = cur.lastrowid
        conn.commit(); conn.close()
        return hid

    def get_by_status(self, status: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM hypotheses WHERE status=? ORDER BY id DESC", (status,)).fetchall()]
        conn.close()
        return rows

    def recent(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM hypotheses ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
        conn.close()
        return rows

    def set_status(self, hid: int, status: str, backtest: Optional[dict] = None):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE hypotheses SET status=?, backtest_json=?, updated_at=? WHERE id=?",
                     (status, json.dumps(backtest) if backtest else None,
                      datetime.now(timezone.utc).isoformat(), hid))
        conn.commit(); conn.close()

    def already_proposed(self, symbol: str, hypothesis: str) -> bool:
        """Avoid looping on the same idea."""
        conn = sqlite3.connect(self.db_path)
        n = conn.execute(
            "SELECT COUNT(*) FROM hypotheses WHERE symbol=? AND hypothesis=?",
            (symbol, hypothesis)).fetchone()[0]
        conn.close()
        return n > 0


class ReflectionAgent:
    def __init__(self, experience_db, registry, store: Optional[HypothesisStore] = None):
        self.experience_db = experience_db
        self.registry = registry
        self.scorer = IndicatorScorer(experience_db)
        self.store = store or HypothesisStore()

    def reflect(self, symbol: str, min_sample: int = 8) -> Optional[dict]:
        """
        Run one reflection pass for a symbol. Returns the stored hypothesis dict
        or None (insufficient data / LLM unavailable / duplicate).
        """
        evidence = self.scorer.score(symbol=symbol, min_sample=min_sample)
        if evidence.get("insufficient"):
            logger.info(f"Reflection[{symbol}]: insufficient sample "
                        f"({evidence.get('sample')}/{evidence.get('needed')})")
            return None

        question = self._form_question(symbol, evidence)
        llm_out = self._ask_llm(symbol, evidence, question)
        if not llm_out:
            return None

        hypothesis = llm_out.get("hypothesis", "").strip()
        if not hypothesis or self.store.already_proposed(symbol, hypothesis):
            logger.info(f"Reflection[{symbol}]: no new hypothesis")
            return None

        hid = self.store.add(
            symbol=symbol, question=question, hypothesis=hypothesis,
            strategies=llm_out.get("strategies"), filt=llm_out.get("filter"),
            rationale=llm_out.get("rationale"),
        )
        logger.info(f"Reflection[{symbol}] hypothesis #{hid}: {hypothesis}")
        return {"id": hid, **llm_out, "question": question}

    # ── THINK: build a focused question from the evidence ──
    def _form_question(self, symbol: str, ev: dict) -> str:
        top = ev.get("indicator_ranking", [])[:4]
        worst_sess = ev.get("worst_sessions", [])
        worst_reg = ev.get("worst_regimes", [])
        wr = round(ev["wins"] / ev["sample"] * 100, 1) if ev.get("sample") else 0
        return (
            f"For {symbol}, our recent win rate is {wr}% over {ev['sample']} trades. "
            f"The most discriminating indicators (win vs loss) are {top}. "
            f"Worst sessions: {worst_sess}. Worst regimes: {worst_reg}. "
            f"What single, testable change (an indicator swap, an added filter, or "
            f"avoiding a session/regime) is most likely to improve entry quality?"
        )

    # ── ACT: query the LLM for a concrete hypothesis ──
    def _ask_llm(self, symbol: str, ev: dict, question: str) -> Optional[dict]:
        try:
            from src.core.llm import get_llm
            llm = get_llm(temperature=0.3)
        except Exception as e:
            logger.info(f"Reflection[{symbol}]: LLM unavailable ({e})")
            return None

        available = self.registry.get_names()
        prompt = (
            "You are a quantitative trading researcher. Analyze the evidence and "
            "propose ONE concrete, testable hypothesis to improve entry quality.\n\n"
            f"QUESTION: {question}\n\n"
            f"Available strategies to combine (choose from these EXACT names): {available}\n"
            f"Indicator win/loss separation (higher = more informative): "
            f"{ev.get('indicator_ranking')}\n"
            f"Per-session win rates: {ev.get('by_session')}\n"
            f"Per-regime win rates: {ev.get('by_regime')}\n\n"
            "Respond ONLY as compact JSON with keys:\n"
            '{"hypothesis": "<one sentence>", '
            '"strategies": ["<existing strategy names to combine, 1-3>"], '
            '"filter": "<optional gate e.g. adx<25 or avoid_session:late_ny or '
            'avoid_regime:volatile, else empty>", '
            '"rationale": "<why, referencing the evidence>"}'
        )
        try:
            resp = llm.invoke(prompt)
            from src.core.llm import extract_text
            raw = extract_text(resp)
            # strip markdown code fences if present (```json ... ```)
            if "```" in raw:
                import re
                fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
                if fenced:
                    raw = fenced.group(1).strip()
            # extract JSON object
            start = raw.find("{"); end = raw.rfind("}")
            if start >= 0 and end > start:
                blob = raw[start:end + 1]
                data = None
                try:
                    data = json.loads(blob)
                except Exception:
                    # tolerate single-quoted / Python-dict-style JSON from the LLM
                    try:
                        import ast
                        data = ast.literal_eval(blob)
                    except Exception:
                        data = None
                if isinstance(data, dict):
                    # keep only valid strategy names
                    strat = [s for s in (data.get("strategies") or []) if s in available]
                    data["strategies"] = strat
                    return data
            logger.info(f"Reflection[{symbol}] no parseable hypothesis in LLM response")
        except Exception as e:
            logger.warning(f"Reflection[{symbol}] LLM parse failed: {e}")
        return None
